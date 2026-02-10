
import sys
import os
import logging

# Add path to find modules
sys.path.append(os.getcwd())

# Mock logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("TestChain")

# Mock scrypt if missing
try:
    import scrypt
except ImportError:
    import types
    scrypt = types.ModuleType("scrypt")
    scrypt.hash = lambda *args, **kwargs: b'\x00'*32
    sys.modules["scrypt"] = scrypt

# Import necessary modules
try:
    from icsicoin.core.chain import ChainManager
    from icsicoin.storage.databases import BlockIndexDB, ChainStateDB 
    from icsicoin.storage.blockstore import BlockStore
    from icsicoin.storage.mempool import Mempool
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

class MockNetworkManager:
    def __init__(self):
        self.peers = []
        self.wallet = None # Mock wallet if needed

def test_hashrate():
    print("Initing DBs...")
    # Point to actual Data Dir
    data_dir = "wallet_data"
    
    try:
        block_index = BlockIndexDB(data_dir) # Constructor takes dir, not file path
        block_store = BlockStore(os.path.join(data_dir, "blocks"))
        chain_state = ChainStateDB(data_dir)
        mempool = Mempool()
        
        # Init Chain Manager
        chain = ChainManager(block_index, block_store, chain_state, mempool, MockNetworkManager())
        
        print("Calculating Hashrate...")
        hashrate = chain.get_network_hashrate(blocks=10)
        print(f"Result: {hashrate}")
        
        # Debug specifics
        tip = chain.block_index.get_best_block()
        print(f"\nTip: {tip}")
        if tip:
            print(f"Tip Height: {tip['height']}")
            
            # Manually run logic
            blocks = 10
            if tip['height'] < blocks:
                blocks = tip['height']
            
            start_height = tip['height'] - blocks
            print(f"Start Height: {start_height}, End Height: {tip['height']}")
            
            h_tip = chain.get_block_header(tip['height'])
            print(f"Header Top: {h_tip} (Timestamp: {h_tip.timestamp if h_tip else 'None'})")
            
            if not h_tip:
                 print("Attempting manual fetch for TIP...")
                 tip_idx = chain.block_index.get_block(tip['block_hash'])
                 if tip_idx:
                     h_tip = chain.block_store.read_block_header(tip_idx['file_num'], tip_idx['offset'])
                     print(f"  Manual Fetch Result: {h_tip}")

            h_start = chain.get_block_header(start_height)
            print(f"Header Start: {h_start} (Timestamp: {h_start.timestamp if h_start else 'None'})")
            
            if h_tip and h_start:
                delta = h_tip.timestamp - h_start.timestamp
                print(f"Time Delta: {delta}")
                diff = h_tip.difficulty
                print(f"Difficulty: {diff}")
                
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_hashrate()
