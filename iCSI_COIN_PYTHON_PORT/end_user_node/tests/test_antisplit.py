"""
Regression tests for the cross-subnet "split-brain" fixes.

These lock in the behaviors that keep every node on one chain:
  - operator-configured --addnode/--connect nodes are tracked as permanent anchors
  - the sync watchdog never tears the whole network down (no soft reset)
  - discovered peers persist to disk and reload
  - the "all-known INV -> request next batch" sync path no longer NameErrors
"""
import unittest
import inspect
import tempfile
import shutil
import os
from unittest.mock import MagicMock
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock scrypt (consensus imports it at module load)
sys.modules['scrypt'] = MagicMock()

from icsicoin.network.manager import NetworkManager


class TestAntiSplit(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp(prefix="test_antisplit_")
        self.manager = NetworkManager(
            port=9333, bind_address='127.0.0.1',
            add_nodes=['10.0.0.5:9333'],
            connect_nodes=['10.0.0.5:9333', '192.168.1.9:9334'],
            rpc_port=9332, data_dir=self.data_dir,
        )

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_anchors_deduped_from_add_and_connect(self):
        # The duplicate 10.0.0.5:9333 appears once; order preserved.
        self.assertEqual(self.manager.anchor_nodes,
                         ['10.0.0.5:9333', '192.168.1.9:9334'])

    def test_parse_node_addr(self):
        self.assertEqual(self.manager._parse_node_addr('1.2.3.4:9335'), ('1.2.3.4', 9335))
        self.assertEqual(self.manager._parse_node_addr('1.2.3.4'), ('1.2.3.4', 9333))

    def test_single_block_index_handle(self):
        # The old duplicate "block_Index" typo handle is gone.
        self.assertTrue(hasattr(self.manager, 'block_index'))
        self.assertFalse(hasattr(self.manager, 'block_Index'))

    def test_watchdog_has_no_soft_reset(self):
        src = inspect.getsource(self.manager.sync_worker)
        self.assertNotIn('self.disconnect_all_peers()', src,
                         "Sync watchdog must not tear down all peers on silence")
        self.assertIn('reconnect_anchors', src)
        self.assertIn('broadcast_getblocks', src)

    def test_inv_continue_sync_has_no_nameerror(self):
        src = inspect.getsource(self.manager.process_message_loop)
        self.assertNotIn('inventory[-1]', src,
                         "INV continue-sync path must reference `items`, not undefined `inventory`")

    def test_known_peers_persist_round_trip(self):
        self.manager.known_peers.update({('1.1.1.1', 9333), ('2.2.2.2', 9334)})
        self.manager.save_known_peers()
        self.assertTrue(os.path.exists(self.manager.peers_file))

        other = NetworkManager(
            port=9999, bind_address='127.0.0.1',
            add_nodes=[], connect_nodes=[], rpc_port=9998, data_dir=self.data_dir,
        )
        other.load_known_peers()
        self.assertIn(('1.1.1.1', 9333), other.known_peers)
        self.assertIn(('2.2.2.2', 9334), other.known_peers)


if __name__ == '__main__':
    unittest.main()
