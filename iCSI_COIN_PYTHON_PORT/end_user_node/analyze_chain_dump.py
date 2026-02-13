import sys
import os
import struct
import datetime

# Add /app to path to find icsicoin
sys.path.insert(0, "/app")

from icsicoin.core.block import Block

def analyze_file(filepath):
    print(f"Analyzing {filepath}...")
    
    blocks = []
    
    try:
        with open(filepath, "rb") as f:
            while True:
                # Read Magic (4 bytes)
                magic = f.read(4)
                if not magic:
                    break
                if len(magic) < 4:
                    print("Unexpected end of file (magic)")
                    break
                    
                # Read Size (4 bytes)
                size_bytes = f.read(4)
                if len(size_bytes) < 4:
                     print("Unexpected end of file (size)")
                     break
                
                block_size = struct.unpack("<I", size_bytes)[0]
                
                # Read Block Data
                block_data = f.read(block_size)
                if len(block_data) < block_size:
                    print(f"Unexpected end of file (block data). Expected {block_size}, got {len(block_data)}")
                    break
                    
                try:
                    block = Block.parse(block_data)
                    blocks.append(block)
                except Exception as e:
                    print(f"Failed to parse block at index {len(blocks)}: {e}")
                    break
                    
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return

    print(f"Total Blocks Parsed: {len(blocks)}")
    
    if not blocks:
        return

    last_block = blocks[-1]
    print("\n--- Last Block Details ---")
    print(f"Height (Index): {len(blocks) - 1}") # Approx height if starts at 0
    print(f"Hash: {last_block.get_hash().hex()}")
    print(f"Prev Hash: {last_block.header.prev_block_hash.hex()}")
    print(f"Timestamp: {last_block.header.timestamp} ({datetime.datetime.fromtimestamp(last_block.header.timestamp)})")
    print(f"Nonce: {last_block.header.nonce}")
    print(f"TX Count: {len(last_block.transactions)}")
    print(f"Size: {len(last_block.serialize())} bytes")

    # Check previous few blocks for timing
    if len(blocks) > 5:
        print("\n--- Recent Block Timings ---")
        for i in range(len(blocks) - 5, len(blocks)):
            b = blocks[i]
            ts = b.header.timestamp
            hash_hex = b.get_hash().hex()
            print(f"Block {i}: {datetime.datetime.fromtimestamp(ts)} | {hash_hex[:16]}...")

if __name__ == "__main__":
    # Path is relative to where we run it, but mapped in docker
    # The user said file is in iCSI_Coin_2026/blk00000.dat. 
    # In container, we will map it or read it.
    # Actually, we will run this LOCALLY on the host if we can, or in container?
    # User machine has python? Probably. 
    # But `icsicoin` lib is in `end_user_node`.
    # I'll try to run it on host using the local path to lib.
    
    target_file = sys.argv[1] if len(sys.argv) > 1 else "blk00000.dat"
    analyze_file(target_file)
