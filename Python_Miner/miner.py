#!/usr/bin/env python3
import sys
import time
import json
import requests
import binascii
import struct
import argparse
import logging
import scrypt

# Add current directory to path to allow importing icsicoin modules if needed
# But for a standalone miner, ideally it should be self-contained OR explicitly use the library.
# Let's try to make it slightly self-contained for the PoW part, but use primitives for serialization if available
# to avoid duplicating logic.
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from icsicoin.core.primitives import Block, BlockHeader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Miner")

def rpc_call(url, method, params=None, session=None):
    headers = {'content-type': 'application/json'}
    payload = {
        "method": method,
        "params": params or [],
        "jsonrpc": "2.0",
        "id": 1,
    }
    try:
        if session:
            response = session.post(url, data=json.dumps(payload), headers=headers)
        else:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"RPC Error: {e}")
        return None

def bits_to_target(bits):
    exponent = bits >> 24
    coefficient = bits & 0xffffff
    return coefficient * (256**(exponent - 3))

def mine(url, user, password, address=None, threads=1):
    logger.info(f"Starting miner on {url}")
    if address:
        logger.info(f"Mining to address: {address}")
    else:
        logger.info("Mining to Node's default wallet")
    
    # Session for keep-alive
    session = requests.Session()
    session.auth = (user, password)
    
    while True:
        # 1. Get Work
        params = []
        if address:
            params.append({"mining_address": address})
            
        resp = rpc_call(url, "getblocktemplate", params=params, session=session)
        if not resp or resp.get('error'):
            logger.error(f"Failed to get work: {resp.get('error') if resp else 'No response'}")
            time.sleep(5)
            continue
            
        template = resp['result']
        height = template['height']
        target_str = template['target']
        target = int(target_str, 16)
        
        # 2. Construct Block
        # We need to construct a Block object to verify/submit, OR just a Header to mine.
        # RPC returns:
        # previousblockhash (hex)
        # curtime (int)
        # bits (int)
        # transactions (hex list)
        # merkle_root (hex)
        
        prev_hash = binascii.unhexlify(template['previousblockhash'])
        merkle_root = binascii.unhexlify(template['merkle_root'])
        timestamp = template['curtime']
        bits = template['bits']
        version = template['version']
        
        # Construct Header
        header = BlockHeader(version, prev_hash, merkle_root, timestamp, bits, 0)
        
        # Mining Loop
        logger.info(f"Mining Block {height} with difficulty {bits}...")
        start_time = time.time()
        hashes = 0
        
        found = False
        # Simple loop
        # max_nonce = 0xFFFFFFFF
        # Let's respect extra nonce/time rolling but for now just nonce rolling.
        for nonce in range(0, 10000000): # Try 10M hashes then refresh template
            header.nonce = nonce
            
            # Hash
            # In Phase 3 validation we used scrypt(header_bytes)
            header_bytes = header.serialize()
            pow_hash = scrypt.hash(header_bytes, header_bytes, N=1024, r=1, p=1, buflen=32)
            
            pow_int = int.from_bytes(pow_hash, 'little')
            
            if pow_int <= target:
                logger.info(f"FOUND BLOCK! Nonce: {nonce}, Hash: {binascii.hexlify(pow_hash).decode()}")
                found = True
                break
                
            hashes += 1
            if hashes % 100000 == 0:
                 print(f"Hashrate: {hashes / (time.time() - start_time):.2f} H/s", end='\r')
                 
        if found:
            # 3. Submit
            # Construct full block
            # We need to parse transactions from hex to Tx objects
            from icsicoin.core.primitives import Transaction
            import io
            
            txs = []
            for tx_hex in template['transactions']:
                tx_bytes = binascii.unhexlify(tx_hex)
                txs.append(Transaction.deserialize(io.BytesIO(tx_bytes)))
                
            block = Block(header, txs)
            block_hex = binascii.hexlify(block.serialize()).decode('utf-8')
            
            submit_resp = rpc_call(url, "submitblock", [block_hex], session=session)
            if submit_resp and submit_resp.get('result') == 'accepted':
                logger.info(f"Block accepted! Height: {height}")
            else:
                logger.error(f"Block rejected at Height {height}!")
                logger.error(f"Block Context: PrevHash={binascii.hexlify(prev_hash).decode()[:16]}..., Time={timestamp}, Merkle={binascii.hexlify(merkle_root).decode()[:16]}...")
                if submit_resp:
                     logger.error(f"Node Response: {submit_resp}")
                else:
                     logger.error("Node Response: None (Network Error?)")
                
            # Sleep a bit to avoid race or spam
            time.sleep(0.5) 
        else:
             logger.info("Nonce exhausted/Refresh needed. Getting new template.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:9340", help="RPC URL")
    parser.add_argument("--user", default="user", help="RPC User")
    parser.add_argument("--pass", dest="password", default="pass", help="RPC Password")
    parser.add_argument("--address", help="Wallet address to mine rewards to")
    args = parser.parse_args()
    
    mine(args.url, args.user, args.password, args.address)
