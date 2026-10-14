"""
Functional tests for the Phase 3 consensus rules: block subsidy/halving (integer math),
coinbase maturity, transaction fees, and the coinbase payout cap.

These use REAL primitives and a REAL ChainStateDB. PoW (scrypt) is bypassed with
check_proof_of_work=False so the economic rules can be tested without mining.
"""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from icsicoin.consensus import validation as V
from icsicoin.consensus.validation import (
    get_block_subsidy, validate_transaction, validate_block,
    COIN, INITIAL_BLOCK_SUBSIDY, HALVING_INTERVAL, COINBASE_MATURITY,
)
from icsicoin.consensus.merkle import get_merkle_root
from icsicoin.core.primitives import Transaction, TxIn, TxOut, Block, BlockHeader
from icsicoin.storage.databases import ChainStateDB


def make_coinbase(amount, script=b'\x76\xa9\x14' + b'\x11' * 20 + b'\x88\xac', tag=b'cb'):
    return Transaction(
        vin=[TxIn(b'\x00' * 32, 0xffffffff, tag, 0xffffffff)],
        vout=[TxOut(amount, script)],
    )


def make_block(txs, bits=V.GENESIS_BITS):
    header = BlockHeader(version=1, prev_block=b'\x00' * 32,
                         merkle_root=get_merkle_root(txs),
                         timestamp=1_700_000_000, bits=bits, nonce=0)
    return Block(header, txs)


class TestSubsidy(unittest.TestCase):
    def test_halving_is_integer_bitshift(self):
        self.assertEqual(get_block_subsidy(0), INITIAL_BLOCK_SUBSIDY)
        self.assertEqual(get_block_subsidy(HALVING_INTERVAL - 1), INITIAL_BLOCK_SUBSIDY)
        self.assertEqual(get_block_subsidy(HALVING_INTERVAL), INITIAL_BLOCK_SUBSIDY // 2)
        self.assertEqual(get_block_subsidy(2 * HALVING_INTERVAL), INITIAL_BLOCK_SUBSIDY // 4)
        # Eventually rounds to zero, never negative / never a float.
        self.assertEqual(get_block_subsidy(64 * HALVING_INTERVAL), 0)
        for h in (0, HALVING_INTERVAL, 5 * HALVING_INTERVAL):
            self.assertIsInstance(get_block_subsidy(h), int)


class TestTxRules(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="test_consensus_")
        self.cs = ChainStateDB(self.d)
        self.script = b'\x76\xa9\x14' + b'\x22' * 20 + b'\x88\xac'

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _spend(self, prev_txid_hex, amount_out):
        return Transaction(
            vin=[TxIn(bytes.fromhex(prev_txid_hex), 0, b'sig', 0xffffffff)],
            vout=[TxOut(amount_out, self.script)],
        )

    def test_fee_is_input_minus_output(self):
        txid = "aa" * 32
        self.cs.add_utxo(txid, 0, 10_000, self.script, block_height=1, is_coinbase=0)
        tx = self._spend(txid, 9_000)
        ok, reason, fee = validate_transaction(tx, self.cs)
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1_000)

    def test_cannot_spend_more_than_inputs(self):
        txid = "bb" * 32
        self.cs.add_utxo(txid, 0, 5_000, self.script, block_height=1, is_coinbase=0)
        ok, reason, fee = validate_transaction(self._spend(txid, 6_000), self.cs)
        self.assertFalse(ok)

    def test_immature_coinbase_rejected(self):
        txid = "cc" * 32
        self.cs.add_utxo(txid, 0, INITIAL_BLOCK_SUBSIDY, self.script, block_height=10, is_coinbase=1)
        # Spending just before maturity (height - block_height < COINBASE_MATURITY).
        spend_height = 10 + COINBASE_MATURITY - 1
        ok, reason, _ = validate_transaction(self._spend(txid, 1_000), self.cs, height=spend_height)
        self.assertFalse(ok)
        self.assertIn("immature", reason.lower())

    def test_mature_coinbase_spendable(self):
        txid = "dd" * 32
        self.cs.add_utxo(txid, 0, INITIAL_BLOCK_SUBSIDY, self.script, block_height=10, is_coinbase=1)
        spend_height = 10 + COINBASE_MATURITY
        ok, reason, _ = validate_transaction(self._spend(txid, 1_000), self.cs, height=spend_height)
        self.assertTrue(ok, reason)


class TestCoinbaseCap(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="test_cbcap_")
        self.cs = ChainStateDB(self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_coinbase_at_subsidy_accepted(self):
        h = 5
        block = make_block([make_coinbase(get_block_subsidy(h))])
        ok, reason = validate_block(block, self.cs, height=h, chain_manager=None,
                                    check_proof_of_work=False)
        self.assertTrue(ok, reason)

    def test_coinbase_over_subsidy_rejected(self):
        h = 5
        block = make_block([make_coinbase(get_block_subsidy(h) + 1)])
        ok, reason = validate_block(block, self.cs, height=h, chain_manager=None,
                                    check_proof_of_work=False)
        self.assertFalse(ok)
        self.assertIn("coinbase", reason.lower())

    def test_halved_subsidy_enforced(self):
        # At/above the halving boundary the cap drops to half -- paying the old amount fails.
        h = HALVING_INTERVAL
        block = make_block([make_coinbase(INITIAL_BLOCK_SUBSIDY)])  # old (pre-halving) amount
        ok, reason = validate_block(block, self.cs, height=h, chain_manager=None,
                                    check_proof_of_work=False)
        self.assertFalse(ok)


if __name__ == '__main__':
    unittest.main()


class TestProofOfWork(unittest.TestCase):
    """Uses the REAL scrypt hash (single evaluations, no mining loop).

    Other test modules replace sys.modules['scrypt'] with a MagicMock at import time,
    which leaks into validation's module-global `scrypt`. Pin the real module here so
    this test is independent of suite ordering.
    """

    def setUp(self):
        import importlib
        self._old_scrypt = V.scrypt
        sys.modules.pop('scrypt', None)
        V.scrypt = importlib.import_module('scrypt')

    def tearDown(self):
        V.scrypt = self._old_scrypt

    def _header(self, bits, nonce=0):
        return BlockHeader(version=1, prev_block=b'\x00' * 32,
                           merkle_root=b'\x00' * 32, timestamp=1_700_000_000,
                           bits=bits, nonce=nonce)

    def test_impossible_target_rejected(self):
        # bits=0x03000001 -> target = 1*256^0 = 1 : no realistic hash is <= 1.
        hard = 0x03000001
        self.assertEqual(V.bits_to_target(hard), 1)
        for nonce in range(6):
            self.assertFalse(V.check_pow(self._header(hard, nonce)))

    def test_near_max_target_accepted(self):
        # bits=0x2000ffff -> target ~ 0xffff * 256^29 : essentially every hash passes.
        easy = 0x2000ffff
        self.assertTrue(any(V.check_pow(self._header(easy, n)) for n in range(8)))

    def test_validate_block_runs_pow(self):
        # A block whose header does not meet its own (impossible) target is rejected by
        # validate_block even in the context-free (height=None) path.
        tx = make_coinbase(get_block_subsidy(1))
        blk = make_block([tx], bits=0x03000001)  # impossible target
        ok, reason = validate_block(blk, None)
        self.assertFalse(ok)
        self.assertIn("proof of work", reason.lower())
