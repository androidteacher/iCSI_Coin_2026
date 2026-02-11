
import sys
import os
import io

# Add project root to path
sys.path.append("/home/josh/Antigrav_projects/Working_Coin/iCSI_Coin_2026/iCSI_COIN_PYTHON_PORT/end_user_node")

from icsicoin.core.primitives import Block

START_HASH = "ba058bd5" # Local Tip
END_HASH = "912194a6"   # One of the received orphans

def analyze_blk(file_path):
    print(f"Tracing path from {START_HASH} to {END_HASH} in {file_path}...")
    
    blocks = []
    try:
        with open(file_path, 'rb') as f:
            while True:
                start_pos = f.tell()
                try:
                    if not f.read(1): break
                    f.seek(start_pos)
                    blocks.append(Block.deserialize(f))
                except: break
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    block_map = {b.get_hash().hex(): b for b in blocks}
    
    # Verify both exist
    start_block = None
    end_block = None
    
    for h, b in block_map.items():
        if h.startswith(START_HASH): start_block = b
        if h.startswith(END_HASH): end_block = b
        
    if not start_block:
        print(f"Start block {START_HASH} not found.")
        return
    if not end_block:
        print(f"End block {END_HASH} not found.")
        return
        
    print(f"Start: {start_block.get_hash().hex()}")
    print(f"End:   {end_block.get_hash().hex()}")
    
    # Trace back from End to Start?
    # Or Start to End?
    # Since blocks point to prev, we trace back from End.
    
    curr = end_block
    path = []
    found_connection = False
    
    while True:
        path.append(curr)
        h = curr.get_hash().hex()
        prev = curr.header.prev_block.hex()
        
        if h == start_block.get_hash().hex():
            found_connection = True
            break
            
        if prev == start_block.get_hash().hex():
            found_connection = True
            break
            
        if prev in block_map:
            curr = block_map[prev]
        else:
            print(f"Hit unknown parent {prev} at height {len(path)}")
            break
            
        if len(path) > 1000:
            print("Path too long, stopping.")
            break
            
    if found_connection:
        print(f"\nPath found! Length: {len(path)} blocks missing/ahead.")
        print("Missing Blocks (from Start -> End):")
        for b in reversed(path):
            print(f"  {b.get_hash().hex()} (Prev: {b.header.prev_block.hex()[:8]}...)")
    else:
        print("\nNo direct path found from End to Start. They might be on different forks.")
        # Trace parents of Start to see common ancestor?
        pass

if __name__ == "__main__":
    analyze_blk("blk00000.dat")
