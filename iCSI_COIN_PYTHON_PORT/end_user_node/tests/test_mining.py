import unittest
import shutil
import tempfile
import sys
import os
import json
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Adjust path
sys.path.append('/home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node')

from icsicoin.wallet.wallet import Wallet
from icsicoin.rpc.rpc_server import RPCServer
from icsicoin.core.chain import ChainManager
from icsicoin.core.mempool import Mempool
from icsicoin.core.primitives import Block
import binascii

class TestMining(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.wallet = Wallet(self.test_dir)
        
        # Mocks
        self.block_index = MagicMock()
        self.block_index.get_best_block.return_value = {'height': 100, 'block_hash': '00'*32}
        
        self.chain_manager = MagicMock()
        self.chain_manager.block_index = self.block_index
        self.chain_manager.process_block.return_value = True
        
        self.mempool = MagicMock()
        self.mempool.get_all_transactions.return_value = []
        
        self.network_manager = MagicMock()
        self.network_manager.peers = []
        
        self.rpc = RPCServer(9340, "user", "pass", "127.0.0.1", 
                             self.network_manager, self.chain_manager, self.mempool, self.wallet)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_wallet_address(self):
        addr = self.wallet.get_new_address()
        self.assertTrue(len(addr) > 0)
        self.assertEqual(len(self.wallet.get_addresses()), 2) # 1 from init + 1 new

    def test_getblocktemplate(self):
        # We need to simulate the request handler logic
        # It's async. 
        
        # Instead of spinning up full aiohttp, let's test the logic by calling a helper
        # OR extracting logic.
        # But wait, logic is inside handle_request. Refactoring is better practice but expensive now.
        # Let's mock the request object.
        pass

class MockRequest:
    def __init__(self, data):
        self._data = data
    async def json(self):
        return self._data

class AsyncTestMining(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.wallet = Wallet(self.test_dir)
        
        self.block_index = MagicMock()
        self.block_index.get_best_block.return_value = {'height': 100, 'block_hash': '00'*32}
        
        self.chain_manager = MagicMock()
        self.chain_manager.block_index = self.block_index
        self.chain_manager.process_block.return_value = True
        
        self.mempool = MagicMock()
        self.mempool.get_all_transactions.return_value = []
        
        self.network_manager = MagicMock()
        self.network_manager.peers = []
        
        self.rpc = RPCServer(9340, "user", "pass", "127.0.0.1", 
                             self.network_manager, self.chain_manager, self.mempool, self.wallet)

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)
        
    async def test_rpc_getblocktemplate(self):
        req = MockRequest({"method": "getblocktemplate", "id": 1})
        resp = await self.rpc.handle_request(req)
        # resp is web.Response. text is JSON string.
        resp_data = json.loads(resp.text)
        
        self.assertIsNone(resp_data['error'])
        result = resp_data['result']
        self.assertEqual(result['height'], 101)
        self.assertEqual(result['previousblockhash'], '00'*32)
        self.assertEqual(len(result['transactions']), 1) # Coinbase only

    async def test_rpc_submitblock(self):
        # Create a dummy block hex
        # Logic tries to deserialize. We need valid serialization.
        from icsicoin.core.primitives import Block
        b = Block()
        b_hex = binascii.hexlify(b.serialize()).decode('utf-8')
        
        req = MockRequest({"method": "submitblock", "params": [b_hex], "id": 2})
        resp = await self.rpc.handle_request(req)
        resp_data = json.loads(resp.text)
        
        self.assertIsNone(resp_data['error'])
        self.assertEqual(resp_data['result'], "accepted")
        self.chain_manager.process_block.assert_called_once()

if __name__ == '__main__':
    unittest.main()
