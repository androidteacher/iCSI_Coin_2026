import threading
import time
import logging
import binascii
import requests
import json
import scrypt
from icsicoin.core.primitives import Block, BlockHeader, Transaction
import io

logger = logging.getLogger("MinerController")

class MinerController:
    def __init__(self, rpc_url, rpc_user, rpc_password):
        self.rpc_url = rpc_url
        self.rpc_auth = (rpc_user, rpc_password)
        self.mining_thread = None
        self.stop_event = threading.Event()
        self.target_address = None
        self.is_mining = False
        self.logs = [] # Simple in-memory log buffer
        self.hashrate = 0.0

    def set_credentials(self, user, password):
        self.rpc_auth = (user, password)
        self._log(f"Miner credentials updated for user: {user}")

    def start_mining(self, target_address):
        if self.is_mining:
            return False, "Already mining"
        
        self.target_address = target_address # Note: In current miner.py, address is implicitly whoever controls the node/RPC or the coinbases.
        # Wait, getblocktemplate usually creates a coinbase for the address in the wallet of the node, 
        # UNLESS we construct the coinbase ourselves.
        # The current miner.py does NOT construct coinbase. It takes 'transactions' from template which ALREADY includes coinbase.
        # So 'target_address' here is actually purely cosmetic UNLESS we modify getblocktemplate to accept a target address
        # OR we modify the miner to rebuild the coinbase.
        # Protocol: getblocktemplate usually supports a wallet address param OR we stick to the node's wallet.
        # For Phase 9, let's assume the NODE's wallet (RPC) gets the reward.
        # User selection of "Target Wallet" might be misleading if we don't pass it to the Node/RPC.
        # TODO: RPC `getblocktemplate` SHOULD support generating coinbase for specific address.
        # FOR NOW: We will log the warning that rewards go to Node Default Wallet.
        
        self.stop_event.clear()
        self.is_mining = True
        self.mining_thread = threading.Thread(target=self._mine_loop)
        self.mining_thread.daemon = True
        self.mining_thread.start()
        self._log(f"Mining started. Target: {target_address}")
        return True, "Mining started"

    def stop_mining(self):
        if not self.is_mining:
            return False, "Not mining"
        
        self.stop_event.set()
        self.is_mining = False
        if self.mining_thread:
            self.mining_thread.join(timeout=2.0)
        self._log("Mining stopped.")
        self.hashrate = 0.0
        return True, "Mining stopped"

    def get_status(self):
        return {
            "is_mining": self.is_mining,
            "hashrate": self.hashrate,
            "target": self.target_address,
            "logs": self.logs[-50:] # Last 50 lines
        }

    def _log(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        self.logs.append(entry)
        if len(self.logs) > 100:
            self.logs.pop(0)
        logger.info(f"MINER LOG: {msg}")

    def _rpc_call(self, method, params=None):
        payload = {
            "method": method,
            "params": params or [],
            "jsonrpc": "2.0",
            "id": 1,
        }
        try:
            response = requests.post(self.rpc_url, json=payload, auth=self.rpc_auth, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # self._log(f"RPC Error: {str(e)}")
            return None

    def _mine_loop(self):
        while not self.stop_event.is_set():
            # 1. Get Work
            params = []
            if self.target_address:
                params.append({"mining_address": self.target_address})
            resp = self._rpc_call("getblocktemplate", params)
            if not resp or resp.get('error'):
                self._log("Waiting for RPC/Work...")
                time.sleep(2)
                continue
                
            template = resp['result']
            height = template['height']
            target = int(template['target'], 16)
            bits = template['bits']
            
            # 2. Parse Header
            current_prev_hash_hex = template['previousblockhash'] # Keep for stale check
            prev_hash = binascii.unhexlify(current_prev_hash_hex)
            merkle_root = binascii.unhexlify(template['merkle_root'])
            timestamp = template['curtime']
            version = template['version']
            
            header = BlockHeader(version, prev_hash, merkle_root, timestamp, bits, 0)
            
            tx_count = len(template.get('transactions', []))
            self._log(f"Mining Block {height}... Tx Count: {tx_count} | Block_Difficulty: {bits}")
            
            start_time = time.time()
            last_report_time = start_time
            last_check_time = start_time
            hashes = 0
            
            # Nonce loop (chunked)
            # We use a large range, but we break out if we find it OR if stale
            for nonce in range(0, 1000000):
                if self.stop_event.is_set():
                    break
                    
                header.nonce = nonce
                header_bytes = header.serialize()
                pow_hash = scrypt.hash(header_bytes, header_bytes, N=1024, r=1, p=1, buflen=32)
                pow_int = int.from_bytes(pow_hash, 'little')
                hashes += 1
                
                now = time.time()
                
                # GIL YIELD: Sleep 0 every slice to let Asyncio network thread run
                # 10k hashes is a reasonable chunk size.
                if hashes % 10000 == 0:
                     time.sleep(0) 
                
                # Report hash rate every 10 seconds
                if now - last_report_time >= 10:
                    elapsed = now - start_time
                    rate = hashes / elapsed if elapsed > 0 else 0
                    self._log(f"⛏ Hash Rate: {rate:.1f} H/s | {hashes} hashes in {elapsed:.0f}s")
                    last_report_time = now
                    
                # STALE TIP CHECK: Every 2.0 seconds
                if now - last_check_time >= 2.0:
                    last_check_time = now
                    best_resp = self._rpc_call("getbestblockhash")
                    if best_resp and 'result' in best_resp:
                        network_tip = best_resp['result']
                        if network_tip != current_prev_hash_hex:
                            self._log(f"<span class='yellow'>STALE TIP DETECTED! Restarting...</span>")
                            break # Break nonce loop, get new template instantly

                if pow_int <= target:
                    self._log(f"<span class='green'>FOUND BLOCK! Nonce: {nonce}</span>")
                    
                    # Submit
                    txs = []
                    for tx_hex in template['transactions']:
                        tx_bytes = binascii.unhexlify(tx_hex)
                        txs.append(Transaction.deserialize(io.BytesIO(tx_bytes)))
                    block = Block(header, txs)
                    block_hex = binascii.hexlify(block.serialize()).decode('utf-8')
                    
                    submit_resp = self._rpc_call("submitblock", [block_hex])
                    if submit_resp and submit_resp['result'] == 'accepted':
                        self._log(f"<span class='cyan'>Block {height} ACCEPTED!</span>")
                        elapsed = time.time() - start_time
                        rate = hashes / elapsed if elapsed > 0 else 0
                        self._log(f"⛏ {hashes} hashes in {elapsed:.1f}s ({rate:.1f} H/s)")
                    else:
                        self._log(f"<span class='red'>Block Rejected</span>")
                    
                    break
                
                # No sleep here, we want max hashrate within the python limits
            
            # If loop finishes (not found) or we broke out (stale), we loop back to Get Work
