import sqlite3
import struct
import io
import os
import sys

# Constants
BLOCK_INDEX_DB = "wallet_data/block_index.sqlite"
BLOCK_STORE_DIR = "wallet_data/blocks"

def debug_hashrate():
    if not os.path.exists(BLOCK_INDEX_DB):
        print(f"Error: {BLOCK_INDEX_DB} not found.")
        return

    conn = sqlite3.connect(f"file:{BLOCK_INDEX_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get Best Block
    cursor.execute("SELECT * FROM block_index ORDER BY height DESC LIMIT 1")
    best = cursor.fetchone()
    
    if not best:
        print("Error: No blocks in index.")
        return

    print(f"Best Block Height: {best['height']}")
    print(f"Best Block Hash: {best['block_hash']}")
    
    height = best['height']
    if height < 2:
        print("Height < 2. Hashrate should be 0.0.")
        return

    # Determine window
    blocks = 10
    if height < 10:
        blocks = height
    
    start_height = height - blocks
    print(f"Window: {blocks} blocks (Height {start_height} to {height})")

    # Get Headers for Start and End
    def get_header_time_and_diff(h):
        cursor.execute("SELECT * FROM block_index WHERE height = ?", (h,))
        row = cursor.fetchone()
        if not row:
            return None, None
        
        # We need to read the file to get timestamp if not in DB
        # Check DB columns first
        if 'timestamp' in row.keys():
             return row['timestamp'], row.get('bits', 0)
        
        # Read from disk
        file_num = row['file_num']
        offset = row['offset']
        
        blk_file = f"{BLOCK_STORE_DIR}/blk{file_num:05d}.dat"
        if not os.path.exists(blk_file):
            print(f"Missing block file: {blk_file}")
            return None, None
            
        with open(blk_file, 'rb') as f:
            f.seek(offset)
            header_bytes = f.read(80)
            
        # Parse timestamp (4 bytes at offset 68)
        # and bits (4 bytes at offset 72)
        # Header: Version(4) Prev(32) Merkle(32) Time(4) Bits(4) Nonce(4)
        ts_bytes = header_bytes[68:72]
        bits_bytes = header_bytes[72:76]
        
        timestamp = struct.unpack('<I', ts_bytes)[0]
        bits = struct.unpack('<I', bits_bytes)[0]
        
        return timestamp, bits

    end_ts, end_bits = get_header_time_and_diff(height)
    start_ts, start_bits = get_header_time_and_diff(start_height)
    
    print(f"End Time: {end_ts}, Start Time: {start_ts}")
    
    if end_ts is None or start_ts is None:
        print("Error reading timestamps.")
        return

    time_delta = end_ts - start_ts
    print(f"Time Delta: {time_delta}s")

    if time_delta <= 0:
        print("Time Delta <= 0. Hashrate 0.")
        return
        
    avg_time = time_delta / blocks
    print(f"Avg Time per Block: {avg_time:.2f}s")
    
    # Calculate Diff
    def bits_to_target(bits):
        exponent = bits >> 24
        coefficient = bits & 0xffffff
        return coefficient * (256**(exponent - 3))
        
    target = bits_to_target(end_bits)
    difficulty = 0xFFFF * 2**208 / target # Standard formula estimate
    # Actually just use Formula: (Difficulty * 2^32) / avg_time
    # Where difficulty is standard bitcoin difficulty?
    # No, the code uses `difficulty = header.difficulty` which is likely `get_difficulty(bits)`
    
    # Let's use the code's formula: (Difficulty * 2^32) / avg_time
    # Wait, `difficulty` in that formula is usually the relative difficulty (1 = genesis).
    # Genesis bits = 0x1d00ffff (Bitcoin) -> Diff 1.
    # iCSI bits = 0x1f099996.
    
    # Let's verify what `header_tip.difficulty` returns in the codebase.
    # primitives.BlockHeader
    # We can't import easily, so let's just assume we want `work / time`.
    # Work = 2**256 / (target + 1)
    # Total Work = Sum(Work) over blocks?
    # Or Average Hashrate = Work / Time.
    
    # Code used: (difficulty * 2^32) / avg_time
    # This implies `difficulty` is the standard "difficulty" number.
    
    genesis_target = bits_to_target(0x1d00ffff) # Standard? Or icsi?
    # icsi chain.py says: 0x1f099996
    
    # Just print raw values for now
    print(f"End Bits: {end_bits}")
    
    # Estimated Hashrate
    # H/s = (2**256 / (target + 1)) * blocks / time_delta
    
    work = (2**256) / (target + 1)
    hashrate = work * blocks / time_delta
    
    print(f"Calculated Hashrate: {hashrate:.2f} H/s")

if __name__ == "__main__":
    debug_hashrate()
