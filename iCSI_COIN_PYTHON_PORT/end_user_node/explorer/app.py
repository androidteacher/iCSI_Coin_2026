from flask import Flask, render_template, request, abort
import sqlite3
import os
import binascii
import struct
import time
from datetime import datetime

app = Flask(__name__)

# Config
DATA_DIR = "/app/data" # Mount point for blockchain data

def get_db_connection():
    conn = sqlite3.connect(os.path.join(DATA_DIR, 'block_index.sqlite'))
    conn.row_factory = sqlite3.Row
    return conn

def read_block_raw(file_num, offset, length):
    filename = os.path.join(DATA_DIR, 'blocks', f'blk{file_num:05d}.dat')
    try:
        with open(filename, 'rb') as f:
            f.seek(offset)
            return f.read(length)
    except FileNotFoundError:
        return None

@app.template_filter('timestamp_to_time')
def timestamp_to_time(s):
    return datetime.fromtimestamp(s).strftime('%Y-%m-%d %H:%M:%S')

@app.route('/')
def index():
    conn = get_db_connection()
    # Get latest blocks
    cursor = conn.execute("SELECT * FROM block_index ORDER BY height DESC LIMIT 20")
    blocks = cursor.fetchall()
    conn.close()
    return render_template('index.html', blocks=blocks)

@app.route('/block/<block_hash>')
def block_detail(block_hash):
    conn = get_db_connection()
    block_info = conn.execute("SELECT * FROM block_index WHERE block_hash = ?", (block_hash,)).fetchone()
    conn.close()
    
    if not block_info:
        abort(404)
        
    # Read raw block
    file_num = block_info['file_num']
    offset = block_info['offset']
    # Length in DB might be 0 if not updated correctly? Phase 2 said we store length.
    # If not, we can read header first. But let's assume we have length or read enough.
    length = block_info['length']
    
    raw_data = read_block_raw(file_num, offset, length)
    if not raw_data:
        abort(500, description="Block data not found on disk")
        
    # Parse Block
    from icsicoin.core.primitives import Block
    import io
    
    try:
        block_obj = Block.deserialize(io.BytesIO(raw_data))
    except Exception as e:
        app.logger.error(f"Failed to deserialize block: {e}")
        abort(500, description=f"Failed to deserialize block: {e}")
        
    # Formatting for Template
    # We need to extract readable data
    transactions = []
    
    for tx in block_obj.vtx:
        tx_data = {
            'txid': tx.get_hash().hex(),
            'inputs': [],
            'outputs': []
        }
        
        for vin in tx.vin:
            is_coinbase = (vin.prev_hash == b'\x00'*32 and vin.prev_index == 0xffffffff)
            tx_data['inputs'].append({
                'is_coinbase': is_coinbase,
                'prev_hash': vin.prev_hash.hex(),
                'prev_index': vin.prev_index
            })
            
        for vout in tx.vout:
             tx_data['outputs'].append({
                 'amount': vout.amount,
                 'script_pubkey': vout.script_pubkey.hex()
             })
             
        transactions.append(tx_data)

    return render_template('block.html', 
                           block=block_info,
                           block_hash=block_hash,
                           prev_hash=block_obj.header.prev_block.hex(),
                           merkle_root=block_obj.header.merkle_root.hex(),
                           timestamp=datetime.fromtimestamp(block_obj.header.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
                           bits=block_obj.header.bits,
                           nonce=block_obj.header.nonce,
                           tx_count=len(transactions),
                           transactions=transactions)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
