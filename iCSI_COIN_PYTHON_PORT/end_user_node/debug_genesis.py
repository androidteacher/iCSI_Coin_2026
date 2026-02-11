import sys
sys.path.insert(0, "/app")
import logging
logging.basicConfig(level=logging.INFO)
from icsicoin.storage.databases import BlockIndexDB, ChainStateDB
from icsicoin.storage.blockstore import BlockStore
from icsicoin.core.chain import ChainManager
import os

data_dir = "/app/wallet_data"
print(f"Data Dir: {data_dir}")
store = BlockStore(data_dir)
index = BlockIndexDB(data_dir)
state = ChainStateDB(data_dir)
print("DBs initialized.")

chain = ChainManager(store, index, state)
print("ChainManager initialized.")

best = index.get_best_block()
print(f"Initial Best Block: {best}")

genesis_hash = chain.genesis_block.get_hash().hex()
print(f"Calculated Genesis Hash: {genesis_hash}")

info = index.get_block_info(genesis_hash)
print(f"Genesis in Index? {info}")

if not best and not info:
    print("Attempting Forced Genesis Init...")
    chain._initialize_genesis()
    best_after = index.get_best_block()
    print(f"After Init - Best Block: {best_after}")
else:
    print("Genesis already present (or partially).")
