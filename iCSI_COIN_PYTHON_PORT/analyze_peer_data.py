
import sys
import os
import struct
from icsicoin.core.block import Block
import io

def parse_blocks(filename):
    if not os.path.exists(filename):
        print(f"File {filename} not found.")
        return

    print(f"Analyzing {filename}...")
    with open(filename, "rb") as f:
        count = 0
        last_block = None
        while True:
            # Read magic (4 bytes) and size (4 bytes)
            header = f.read(8)
            if len(header) < 8:
                break
            
            magic, size = struct.unpack("<4sI", header)
            
            # Read block data
            block_data = f.read(size)
            if len(block_data) < size:
                break
                
            # Parse block
            block_stream = io.BytesIO(block_data)
            try:
                block = Block.deserialize(block_stream)
                count += 1
                last_block = block
                
                # Check specific heights if relevant
                # Note: We can't know height easily without traversing from Genesis or having an index.
                # But we can print the hash of the last block found.
            except Exception as e:
                print(f"Error parsing block {count}: {e}")
                break
                
    if last_block:
        print(f"Total Blocks Found: {count}")
        print(f"Last Block Hash: {last_block.get_hash().hex()}")
        print(f"Last Block Prev: {last_block.header.prev_block.hex()}")
        # We can't determine absolute height without context, but count gives a hint if it starts from 0.

if __name__ == "__main__":
    if len(sys.argv) > 1:
        parse_blocks(sys.argv[1])
    else:
        parse_blocks("blk00000.dat")
