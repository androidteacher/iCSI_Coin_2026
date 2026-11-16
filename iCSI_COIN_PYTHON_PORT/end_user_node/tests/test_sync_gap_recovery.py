"""
Regression tests for the "fresh node stalls part-way through sync" failure.

What went wrong, in order:
  1. A reorg left the winning branch flagged as side-chain (status 2), so those
     heights disappeared from every height lookup on that node.
  2. A node syncing from it was sent inventories with a hole at each such height
     and saw every later block as an orphan.
  3. Orphan recovery re-requested blocks that were already on their way, so one
     hole became thousands of duplicate downloads.
  4. Connection handlers waited on peers that had stopped reading, so the flood
     froze the connection -- and then every other handler that touched it.

Each test below pins one link of that chain.
"""
import asyncio
import binascii
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from icsicoin.storage.blockstore import BlockStore
from icsicoin.storage.databases import BlockIndexDB, ChainStateDB
from icsicoin.core.chain import ChainManager
from icsicoin.core.primitives import Block, BlockHeader
from icsicoin.network import manager as manager_module
from icsicoin.network.manager import NetworkManager
from icsicoin.network.messages import Message


def make_block(prev_hash_hex, salt):
    """A structurally valid, transaction-less block. `salt` makes siblings distinct."""
    header = BlockHeader(prev_block=bytes.fromhex(prev_hash_hex), merkle_root=b'\x00' * 32,
                         timestamp=1_700_000_000 + salt, nonce=salt)
    return Block(header, [])


def make_chain(prev_hash_hex, length, salt_base=0):
    blocks = []
    for i in range(length):
        block = make_block(prev_hash_hex, salt_base + i)
        blocks.append(block)
        prev_hash_hex = block.get_hash().hex()
    return blocks


def bhash(block):
    return block.get_hash().hex()


class ChainTestCase(unittest.TestCase):
    """Real SQLite index + block store in a temp dir; consensus validation stubbed."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self._validate = patch('icsicoin.core.chain.validate_block', return_value=(True, 'Valid'))
        self._validate.start()
        self.block_store = BlockStore(self.test_dir)
        self.block_index = BlockIndexDB(self.test_dir)
        self.chain_state = ChainStateDB(self.test_dir)
        self.chain = ChainManager(self.block_store, self.block_index, self.chain_state)
        self.genesis = self.block_index.get_best_block()['block_hash']

    def tearDown(self):
        self._validate.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def status(self, block):
        return self.block_index.get_block_info(bhash(block))['status']

    def set_status(self, block, status):
        self.block_index.update_block_status(bhash(block), status)


class TestReorgStatus(ChainTestCase):
    def test_reorg_marks_whole_winning_branch_as_main_chain(self):
        a1 = make_block(self.genesis, 1)          # first tip at height 1
        b1 = make_block(self.genesis, 2)          # competing block at height 1
        b2 = make_block(bhash(b1), 3)             # extends the competitor -> reorg

        self.assertTrue(self.chain.process_block(a1)[0])
        self.assertTrue(self.chain.process_block(b1)[0])      # stored as a side-chain block
        self.assertEqual(self.status(b1), 2)
        self.assertTrue(self.chain.process_block(b2)[0])      # reorg onto b1 -> b2

        self.assertEqual(self.block_index.get_best_block()['block_hash'], bhash(b2))
        self.assertEqual(self.status(a1), 2, "losing tip must be demoted")
        self.assertEqual(self.status(b2), 3)
        # The bug: b1 stayed at status 2, leaving height 1 with no main-chain block.
        self.assertEqual(self.status(b1), 3, "block on the winning branch must be promoted")
        self.assertEqual(self.block_index.get_block_hash_by_height(1), bhash(b1))
        self.assertEqual(self.chain.get_main_chain_hashes(1, 2), [bhash(b1), bhash(b2)])

    def test_deep_reorg_promotes_every_intermediate_block(self):
        old = make_chain(self.genesis, 3, salt_base=100)
        new = make_chain(self.genesis, 5, salt_base=200)
        for block in old:
            self.assertTrue(self.chain.process_block(block)[0])
        for block in new:
            self.assertTrue(self.chain.process_block(block)[0])

        self.assertEqual(self.block_index.get_best_block()['height'], 5)
        self.assertEqual([self.status(b) for b in new], [3] * 5)
        self.assertEqual([self.status(b) for b in old], [2] * 3)
        for height, block in enumerate(new, start=1):
            self.assertEqual(self.block_index.get_block_hash_by_height(height), bhash(block))


class TestIndexRepair(ChainTestCase):
    def build(self, length=6):
        blocks = make_chain(self.genesis, length)
        for block in blocks:
            self.assertTrue(self.chain.process_block(block)[0])
        return blocks

    def test_repair_restores_flags_left_by_an_older_build(self):
        blocks = self.build(6)
        # Reproduce what the old reorg code left on disk: main-chain blocks at status 2.
        self.set_status(blocks[1], 2)   # height 2
        self.set_status(blocks[3], 2)   # height 4
        self.assertIsNone(self.block_index.get_block_hash_by_height(2))
        self.assertIsNone(self.block_index.get_block_hash_by_height(4))

        self.assertEqual(self.block_index.repair_main_chain_status(), (2, 0))

        for height, block in enumerate(blocks, start=1):
            self.assertEqual(self.block_index.get_block_hash_by_height(height), bhash(block))
        # Idempotent.
        self.assertEqual(self.block_index.repair_main_chain_status(), (0, 0))

    def test_repair_runs_automatically_at_startup(self):
        blocks = self.build(5)
        self.set_status(blocks[2], 2)   # height 3
        # "Restart the node" on the same data directory.
        ChainManager(BlockStore(self.test_dir), BlockIndexDB(self.test_dir), ChainStateDB(self.test_dir))
        self.assertEqual(self.block_index.get_block_hash_by_height(3), bhash(blocks[2]))

    def test_repair_demotes_stale_blocks_flagged_as_main_chain(self):
        blocks = self.build(4)
        stale = make_block(bhash(blocks[0]), 999)          # sibling at height 2
        self.assertTrue(self.chain.process_block(stale)[0])
        self.set_status(stale, 3)                           # wrongly flagged as main chain
        self.assertEqual(self.block_index.repair_main_chain_status(), (0, 1))
        self.assertEqual(self.status(stale), 2)
        self.assertEqual(self.block_index.get_block_hash_by_height(2), bhash(blocks[1]))

    def test_repair_leaves_index_alone_if_chain_cannot_be_walked(self):
        blocks = self.build(4)
        self.set_status(blocks[1], 2)
        with self.block_index._connect() as conn:    # cut the chain below the tip
            conn.execute("UPDATE block_index SET prev_hash = ? WHERE block_hash = ?",
                         ('ff' * 32, bhash(blocks[2])))
            conn.commit()
        self.assertIsNone(self.block_index.repair_main_chain_status())
        self.assertEqual(self.status(blocks[1]), 2, "must not guess when the walk fails")

    def test_inventory_lookup_has_no_gap_even_with_wrong_flags(self):
        blocks = self.build(8)
        self.set_status(blocks[2], 2)   # height 3
        self.set_status(blocks[6], 2)   # height 7
        expected = [bhash(b) for b in blocks]
        self.assertEqual(self.block_index.get_main_chain_hashes(1, 8), expected)
        self.assertEqual(self.block_index.get_main_chain_hashes(3, 5), expected[2:5])
        self.assertEqual(self.block_index.get_main_chain_hashes(5, 4), [])


class TestOrphanPool(ChainTestCase):
    def test_long_orphan_run_connects_without_hitting_recursion_limit(self):
        # 1,200 consecutive orphans behind one missing block. The old recursive
        # resolver used two Python frames per block and blew the 1,000-frame limit.
        blocks = make_chain(self.genesis, 1201)
        for block in blocks[1:]:
            self.assertEqual(self.chain.process_block(block), (False, "Orphan block"))
        self.assertEqual(len(self.chain.orphan_blocks), 1200)

        self.assertTrue(self.chain.process_block(blocks[0])[0])

        self.assertEqual(self.block_index.get_best_block()['height'], 1201)
        self.assertEqual(self.chain.orphan_blocks, {})
        self.assertEqual(self.chain.orphan_dep, {})

    def test_resent_orphan_is_not_queued_twice(self):
        blocks = make_chain(self.genesis, 3)
        for _ in range(5):
            self.chain.process_block(blocks[2])
        self.assertEqual(len(self.chain.orphan_dep[bhash(blocks[1])]), 1)

    def test_find_missing_ancestor_names_the_one_block_to_fetch(self):
        blocks = make_chain(self.genesis, 6)
        self.chain.process_block(blocks[0])
        for block in blocks[2:]:               # blocks[1] (height 2) never arrives
            self.chain.process_block(block)
        for block in blocks[2:]:
            self.assertEqual(self.chain.find_missing_ancestor(bhash(block)), bhash(blocks[1]))
        self.assertEqual(self.chain.get_missing_parents(), [bhash(blocks[1])])
        self.assertIsNone(self.chain.find_missing_ancestor(bhash(blocks[0])))

    def test_drop_orphans_waiting_on_releases_the_whole_run(self):
        blocks = make_chain(self.genesis, 6)
        for block in blocks[2:]:
            self.chain.process_block(block)
        self.assertEqual(self.chain.drop_orphans_waiting_on(bhash(blocks[1])), 4)
        self.assertEqual(self.chain.orphan_blocks, {})
        self.assertEqual(self.chain.orphan_dep, {})


# ───────────────────────── network layer ─────────────────────────

class FakeTransport:
    def __init__(self):
        self.closing = False
        self.buffered = 0
        self.aborted = False

    def is_closing(self):
        return self.closing

    def get_write_buffer_size(self):
        return self.buffered

    def abort(self):
        self.aborted = True
        self.closing = True


class FakeWriter:
    """Stands in for asyncio.StreamWriter. `stuck=True` models a peer that has
    stopped reading: drain() never returns."""

    def __init__(self, peer=('10.0.0.1', 9341), stuck=False):
        self.transport = FakeTransport()
        self.peer = peer
        self.stuck = stuck
        self.sent = bytearray()

    def write(self, data):
        self.sent += data

    async def drain(self):
        if self.stuck:
            await asyncio.Event().wait()

    def close(self):
        self.transport.closing = True

    async def wait_closed(self):
        return None

    def get_extra_info(self, _name):
        return self.peer

    def messages(self):
        """Decode everything written so far into [(command, payload_dict_or_None)]."""
        out, data, pos = [], bytes(self.sent), 0
        while pos + 24 <= len(data):
            _magic, command, length, _checksum = Message.parse_header(data[pos:pos + 24])
            payload = data[pos + 24:pos + 24 + length]
            try:
                decoded = json.loads(payload.decode('utf-8'))
            except Exception:
                decoded = None
            out.append((command, decoded))
            pos += 24 + length
        return out

    def commands(self):
        return [command for command, _ in self.messages()]

    def requested_blocks(self):
        """Every block hash asked for via GETDATA, in order, duplicates included."""
        return [item['hash'] for command, body in self.messages() if command == 'getdata'
                for item in body['inventory'] if item['type'] == 'block']


def inv_message(hashes):
    body = {"type": "inv", "inventory": [{"type": "block", "hash": h} for h in hashes]}
    return Message('inv', json.dumps(body).encode('utf-8'))


def block_message(block):
    body = {"type": "block", "payload": binascii.hexlify(block.serialize()).decode('ascii')}
    return Message('block', json.dumps(body).encode('utf-8'))


def getdata_message(hashes):
    body = {"type": "getdata", "inventory": [{"type": "block", "hash": h} for h in hashes]}
    return Message('getdata', json.dumps(body).encode('utf-8'))


def getblocks_message(locator):
    return Message('getblocks', json.dumps({"type": "getblocks", "locator": locator}).encode('utf-8'))


class NetworkTestCase(unittest.TestCase):
    PEER = ('10.0.0.1', 9341)

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self._validate = patch('icsicoin.core.chain.validate_block', return_value=(True, 'Valid'))
        self._validate.start()
        self.manager = NetworkManager(port=9333, bind_address='127.0.0.1', add_nodes=[],
                                      connect_nodes=[], rpc_port=9332, data_dir=self.test_dir)
        self.manager.running = True
        self.chain = self.manager.chain_manager
        self.genesis = self.manager.block_index.get_best_block()['block_hash']

    def tearDown(self):
        self._validate.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def deliver(self, writer, messages, addr=None, peer_height=10_000):
        """Run the real per-connection message loop over `messages`, then EOF."""
        addr = addr or self.PEER
        self.manager.banned_peers.clear()
        self.manager.peer_disconnect_counts.clear()
        self.manager.peers.add(addr)
        self.manager.active_connections[addr] = writer
        self.manager.peer_stats[addr] = {'height': peer_height}
        reader = asyncio.StreamReader()
        for message in messages:
            reader.feed_data(message.serialize())
        reader.feed_eof()
        await self.manager.process_message_loop(reader, writer, addr)
        await asyncio.sleep(0)      # let the post-disconnect retry task run

    def connect_blocks(self, blocks):
        for block in blocks:
            self.assertTrue(self.chain.process_block(block)[0])


class TestNoDuplicateRequests(NetworkTestCase):
    def test_repeated_inv_requests_each_block_once(self):
        hashes = [bhash(b) for b in make_chain(self.genesis, 5)]
        writer = FakeWriter()
        asyncio.run(self.deliver(writer, [inv_message(hashes)] * 4))
        self.assertEqual(writer.requested_blocks(), hashes,
                         "blocks already on their way must not be requested again")

    def test_second_peer_is_not_asked_for_blocks_already_requested(self):
        hashes = [bhash(b) for b in make_chain(self.genesis, 5)]
        first, second = FakeWriter(('10.0.0.1', 9341)), FakeWriter(('10.0.0.2', 9341))

        async def scenario():
            # Keep the first peer "connected" so its requests stay in flight.
            self.manager.active_connections[('10.0.0.1', 9341)] = first
            self.manager._mark_block_requested(hashes[0], ('10.0.0.1', 9341))
            for h in hashes[1:]:
                self.manager._mark_block_requested(h, ('10.0.0.1', 9341))
            await self.deliver(second, [inv_message(hashes)], addr=('10.0.0.2', 9341))
        asyncio.run(scenario())
        self.assertEqual(second.requested_blocks(), [])

    def test_blocks_a_dropped_peer_owed_us_can_be_requested_again(self):
        hashes = [bhash(b) for b in make_chain(self.genesis, 3)]
        first, second = FakeWriter(('10.0.0.1', 9341)), FakeWriter(('10.0.0.2', 9341))

        async def scenario():
            await self.deliver(first, [inv_message(hashes)], addr=('10.0.0.1', 9341))   # then EOF
            await self.deliver(second, [inv_message(hashes)], addr=('10.0.0.2', 9341))
        asyncio.run(scenario())
        self.assertEqual(first.requested_blocks(), hashes)
        self.assertEqual(second.requested_blocks(), hashes)

    def test_parked_orphans_are_not_requested_again(self):
        blocks = make_chain(self.genesis, 6)
        for block in blocks[1:]:                     # blocks[0] missing -> all orphans
            self.chain.process_block(block)
        writer = FakeWriter()
        asyncio.run(self.deliver(writer, [inv_message([bhash(b) for b in blocks[1:]])]))
        self.assertEqual(writer.requested_blocks(), [])

    def test_block_stays_in_flight_until_it_has_been_processed(self):
        # Between arriving and being indexed a block is in neither the index nor the
        # orphan pool. Another connection must still see it as accounted for.
        block = make_chain(self.genesis, 1)[0]

        async def scenario():
            await self.manager.sync_lock.acquire()           # some other block is being processed
            task = asyncio.create_task(self.deliver(FakeWriter(), [block_message(block)]))
            await asyncio.sleep(0.05)                        # block received, waiting its turn
            seen_as_in_flight = self.manager._block_in_flight(bhash(block))
            self.manager.sync_lock.release()
            await task
            return seen_as_in_flight
        self.assertTrue(asyncio.run(scenario()))
        self.assertFalse(self.manager._block_in_flight(bhash(block)))
        self.assertEqual(self.manager.block_index.get_best_block()['height'], 1)

    def test_identical_getblocks_is_not_repeated(self):
        writer = FakeWriter()

        async def scenario():
            self.assertTrue(await self.manager.send_getblocks(writer))
            self.assertFalse(await self.manager.send_getblocks(writer))
            self.assertFalse(await self.manager.send_getblocks(writer))
            # A different peer, or a new tip, is a different request.
            self.assertTrue(await self.manager.send_getblocks(FakeWriter(('10.0.0.2', 9341))))
            self.connect_blocks(make_chain(self.genesis, 1))
            self.assertTrue(await self.manager.send_getblocks(writer))
            self.assertTrue(await self.manager.send_getblocks(writer, force=True))
        asyncio.run(scenario())
        self.assertEqual(writer.commands(), ['getblocks', 'getblocks', 'getblocks'])


class TestHoleInPeerInventory(NetworkTestCase):
    """A peer running the old code skips one height in its inventory. The syncing
    node must fetch that one block and carry on, without amplifying requests."""

    def test_batch_behind_a_hole_triggers_exactly_one_parent_fetch(self):
        blocks = make_chain(self.genesis, 42)
        hole = blocks[1]                                  # height 2 is never advertised
        writer = FakeWriter()
        batch = [block_message(b) for b in [blocks[0]] + blocks[2:]]
        # The peer also repeats its (holed) inventory, as it does when asked again.
        holed_inv = inv_message([bhash(b) for b in [blocks[0]] + blocks[2:]])

        asyncio.run(self.deliver(writer, batch + [holed_inv, holed_inv]))

        self.assertEqual(self.manager.block_index.get_best_block()['height'], 1)
        self.assertEqual(len(self.chain.orphan_blocks), 40)
        self.assertEqual(writer.requested_blocks(), [bhash(hole)],
                         "40 orphans behind one hole must produce ONE request, for the hole")
        # Old behaviour: every 11th orphan re-sent getblocks (3 times here).
        self.assertLessEqual(writer.commands().count('getblocks'), 1)

    def test_sync_completes_once_the_missing_block_arrives(self):
        blocks = make_chain(self.genesis, 42)
        first, second = FakeWriter(), FakeWriter()

        async def scenario():
            await self.deliver(first, [block_message(b) for b in [blocks[0]] + blocks[2:]])
            await self.deliver(second, [block_message(blocks[1])])
        asyncio.run(scenario())

        self.assertEqual(self.manager.block_index.get_best_block()['height'], 42)
        self.assertEqual(self.chain.orphan_blocks, {})

    def test_watchdog_re_requests_a_parent_whose_request_was_lost(self):
        blocks = make_chain(self.genesis, 6)
        first, second = FakeWriter(('10.0.0.1', 9341)), FakeWriter(('10.0.0.2', 9341))

        async def scenario():
            # Orphans arrive, parent is requested, then that peer disappears.
            await self.deliver(first, [block_message(b) for b in [blocks[0]] + blocks[2:]],
                               addr=('10.0.0.1', 9341))
            self.assertEqual(first.requested_blocks(), [bhash(blocks[1])])
            # Only another peer is connected now; the watchdog pass must ask it.
            self.manager.active_connections[('10.0.0.2', 9341)] = second
            self.manager.peer_stats[('10.0.0.2', 9341)] = {'height': 10_000}
            self.assertEqual(await self.manager.request_missing_parents(), 1)
            self.assertEqual(await self.manager.request_missing_parents(), 0)   # now in flight
        asyncio.run(scenario())
        self.assertEqual(second.requested_blocks(), [bhash(blocks[1])])

    def test_unfetchable_parent_is_given_up_and_its_orphans_released(self):
        blocks = make_chain(self.genesis, 6)
        writer = FakeWriter()

        async def scenario():
            await self.deliver(writer, [block_message(b) for b in blocks[2:]])
            self.manager.active_connections[self.PEER] = writer
            writer.transport.closing = False
            for _ in range(manager_module.BACKFILL_MAX_ATTEMPTS + 2):
                self.manager.block_requests.clear()          # simulate each request timing out
                await self.manager.request_missing_parents()
        asyncio.run(scenario())
        self.assertEqual(self.chain.orphan_blocks, {})
        self.assertLessEqual(writer.requested_blocks().count(bhash(blocks[1])),
                             manager_module.BACKFILL_MAX_ATTEMPTS)

    def test_far_ahead_orphans_fall_back_to_bulk_sync(self):
        # A fresh tip announced while we are far behind: each fetched parent is
        # itself an orphan. After a bounded number of steps, stop stepping back.
        blocks = make_chain(self.genesis, 60)
        writer = FakeWriter()
        backwards = [block_message(b) for b in reversed(blocks[20:])]     # tip first
        asyncio.run(self.deliver(writer, backwards))
        self.assertLessEqual(len(writer.requested_blocks()), manager_module.BACKFILL_MAX_PER_WINDOW)
        self.assertGreaterEqual(writer.commands().count('getblocks'), 1)


class TestServingSide(NetworkTestCase):
    def test_inventory_reply_has_no_hole_when_a_flag_is_wrong(self):
        blocks = make_chain(self.genesis, 8)
        self.connect_blocks(blocks)
        self.manager.block_index.update_block_status(bhash(blocks[3]), 2)     # height 4
        writer = FakeWriter()
        asyncio.run(self.deliver(writer, [getblocks_message([self.genesis])]))
        invs = [body for command, body in writer.messages() if command == 'inv']
        self.assertEqual(len(invs), 1)
        self.assertEqual([item['hash'] for item in invs[0]['inventory']], [bhash(b) for b in blocks])

    def test_request_for_unknown_block_does_not_drop_the_peer(self):
        blocks = make_chain(self.genesis, 3)
        self.connect_blocks(blocks)
        writer = FakeWriter()
        asyncio.run(self.deliver(writer, [getdata_message(['ab' * 32, bhash(blocks[0]), bhash(blocks[2])])]))
        self.assertEqual(writer.commands(), ['block', 'block'])
        self.assertFalse(writer.transport.aborted)


class TestStuckPeerCannotFreezeTheNode(NetworkTestCase):
    def test_block_relay_does_not_wait_on_a_peer_that_stopped_reading(self):
        blocks = make_chain(self.genesis, 3)
        stuck = FakeWriter(('10.0.0.9', 9341), stuck=True)
        healthy = FakeWriter(('10.0.0.8', 9341))
        source = FakeWriter()

        async def scenario():
            self.manager.active_connections[('10.0.0.9', 9341)] = stuck
            self.manager.active_connections[('10.0.0.8', 9341)] = healthy
            # Before the fix this never returned: the handler awaited the stuck
            # peer's drain() after relaying the first block.
            await asyncio.wait_for(
                self.deliver(source, [block_message(b) for b in blocks], peer_height=3), timeout=5)
        asyncio.run(scenario())

        self.assertEqual(self.manager.block_index.get_best_block()['height'], 3)
        self.assertEqual(healthy.commands().count('inv'), 3)
        self.assertEqual(stuck.commands().count('inv'), 3)          # queued, not awaited
        self.assertEqual(source.commands().count('inv'), 0)         # not echoed to sender

    def test_broadcasts_and_watchdog_requests_do_not_wait_either(self):
        stuck = FakeWriter(('10.0.0.9', 9341), stuck=True)
        block = make_block(self.genesis, 1)

        async def scenario():
            self.manager.active_connections[('10.0.0.9', 9341)] = stuck
            await asyncio.wait_for(self.manager.announce_new_block(block), timeout=2)
            await asyncio.wait_for(self.manager.send_getblocks(stuck), timeout=2)
            await asyncio.wait_for(self.manager.broadcast_getblocks(), timeout=2)
        asyncio.run(scenario())
        self.assertIn('inv', stuck.commands())
        self.assertIn('getblocks', stuck.commands())

    def test_one_connection_registered_twice_gets_one_copy(self):
        writer = FakeWriter()
        self.manager.active_connections[('10.0.0.1', 51000)] = writer    # source port
        self.manager.active_connections[('10.0.0.1', 9341)] = writer     # listening port
        self.assertEqual(self.manager.broadcast_nowait(inv_message(['aa' * 32]).serialize()), 1)
        self.assertEqual(writer.commands(), ['inv'])

    def test_peer_with_a_huge_unsent_backlog_is_dropped(self):
        writer = FakeWriter()
        writer.transport.buffered = manager_module.MAX_SEND_BUFFER + 1
        self.assertFalse(self.manager.send_nowait(writer, b'x', self.PEER))
        self.assertTrue(writer.transport.aborted)
        self.assertFalse(self.manager.send_nowait(writer, b'x', self.PEER))   # already closing

    def test_bulk_reply_gives_up_on_a_peer_that_stops_reading(self):
        writer = FakeWriter(stuck=True)

        async def scenario():
            with patch.object(manager_module, 'SEND_STALL_TIMEOUT', 0.05):
                return await asyncio.wait_for(self.manager.send_reply(writer, b'x', self.PEER), timeout=2)
        self.assertFalse(asyncio.run(scenario()))
        self.assertTrue(writer.transport.aborted)

    def test_closing_a_connection_with_unsent_data_does_not_hang(self):
        writer = FakeWriter()
        writer.transport.buffered = 4096

        async def never_closes():
            await asyncio.Event().wait()
        writer.wait_closed = never_closes

        async def scenario():
            with patch('icsicoin.network.manager.asyncio.wait_for', wraps=asyncio.wait_for):
                await asyncio.wait_for(self.manager._close_writer(writer), timeout=10)
        asyncio.run(scenario())
        self.assertTrue(writer.transport.aborted)


if __name__ == '__main__':
    unittest.main()
