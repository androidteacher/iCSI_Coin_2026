import unittest
import os
import shutil
import tempfile
import sys

# Adjust path to import icsicoin
sys.path.append('/home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node')

from icsicoin.storage.blockstore import BlockStore
from icsicoin.storage.databases import BlockIndexDB, ChainStateDB

class TestStorage(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for data
        self.test_dir = tempfile.mkdtemp()
        self.block_store = BlockStore(self.test_dir)
        self.block_index = BlockIndexDB(self.test_dir)
        self.chain_state = ChainStateDB(self.test_dir)

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    def test_block_store_write_read(self):
        # Create dummy block data
        block_data = b'\xAA\xBB\xCC\xDD' * 10
        
        # Write block
        loc = self.block_store.write_block(block_data)
        file_num, offset = loc
        
        # Read block back
        read_data = self.block_store.read_block(file_num, offset, len(block_data))
        self.assertEqual(block_data, read_data)
        
        # Verify file exists
        file_path = self.block_store.get_file_path(file_num)
        self.assertTrue(os.path.exists(file_path))

    def test_block_index_db(self):
        # Add block info
        block_hash = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
        self.block_index.add_block(block_hash, 0, 100, 80, "0000...0000", 1)
        
        # Retrieve block info
        info = self.block_index.get_block_info(block_hash)
        self.assertIsNotNone(info)
        self.assertEqual(info['file_num'], 0)
        self.assertEqual(info['offset'], 100)
        
        # Update height
        self.block_index.set_height(block_hash, 5)
        info = self.block_index.get_block_info(block_hash)
        self.assertEqual(info['height'], 5)

    def test_chain_state_db(self):
        txid = "a1b2c3d4e5f6"
        vout = 0
        amount = 50000000
        script = b'\x76\xa9\x14...'
        
        # Add UTXO
        self.chain_state.add_utxo(txid, vout, amount, script)
        
        # Get UTXO
        utxo = self.chain_state.get_utxo(txid, vout)
        self.assertIsNotNone(utxo)
        self.assertEqual(utxo['amount'], amount)
        self.assertEqual(utxo['script_pubkey'], script)
        
        # Remove UTXO
        self.chain_state.remove_utxo(txid, vout)
        utxo = self.chain_state.get_utxo(txid, vout)
        self.assertIsNone(utxo)

if __name__ == '__main__':
    unittest.main()
