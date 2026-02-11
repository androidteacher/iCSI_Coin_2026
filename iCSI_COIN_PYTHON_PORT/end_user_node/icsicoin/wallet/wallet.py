import os
import ecdsa
import hashlib
import binascii
import json
import logging

logger = logging.getLogger("Wallet")

class Wallet:
    def __init__(self, data_dir):
        self.wallet_path = os.path.join(data_dir, "wallet.dat")
        self.keys = [] # List of (private_key_hex, public_key_hex, address)
        self.load()

    def load(self):
        if os.path.exists(self.wallet_path):
            try:
                with open(self.wallet_path, "r") as f:
                    data = json.load(f)
                    self.keys = data.get("keys", [])
                    logger.info(f"Loaded {len(self.keys)} keys from wallet.")
            except Exception as e:
                logger.error(f"Failed to load wallet: {e}")
        else:
            logger.info("No wallet found, creating new one.")
            self.get_new_address() # Generate at least one key

    def save(self):
        try:
            with open(self.wallet_path, "w") as f:
                json.dump({"keys": self.keys}, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save wallet: {e}")

    def get_new_address(self):
        # Generate ECDSA Key Pair (SECP256k1)
        sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        vk = sk.verifying_key
        
        private_key_hex = binascii.hexlify(sk.to_string()).decode('utf-8')
        public_key_bytes = vk.to_string() # Uncompressed? 
        # For compatibility with our script.py which mostly ignored compression flags or assumed raw 64 bytes?
        # Let's check script.py usage. It used vk.to_string() which is 64 bytes for SECP256k1.
        # But usually we prepend 0x04 for uncompressed.
        # Let's stick to simple raw bytes for now unless script.py expects otherwise.
        
        public_key_hex = binascii.hexlify(public_key_bytes).decode('utf-8')
        
        # Address Generation: RIPEMD160(SHA256(PubKey))
        sha256_bpk = hashlib.sha256(public_key_bytes).digest()
        try:
             ripemd160 = hashlib.new('ripemd160')
        except:
             # Fallback if ripemd160 not available in hashlib (common in some openssl builds)
             # But likely available.
             ripemd160 = hashlib.new('ripemd160', sha256_bpk)
             
        ripemd160.update(sha256_bpk)
        pubkey_hash = ripemd160.digest()
        
        address = binascii.hexlify(pubkey_hash).decode('utf-8')
        
        self.keys.append({
            "priv": private_key_hex,
            "pub": public_key_hex,
            "addr": address
        })
        self.save()
        logger.info(f"Generated new address: {address}")
        return address

    def get_addresses(self):
        return [k['addr'] for k in self.keys]

    def get_key_by_address(self, address):
        for k in self.keys:
            if k['addr'] == address:
                return k
        return None

    def get_address_balance(self, address, chain_state, mempool=None):
        """Calculate balance for a single address, optionally including mempool pending state."""
        pubkey_hash = binascii.unhexlify(address)
        script = b'\x76\xa9\x14' + pubkey_hash + b'\x88\xac'
        
        # 1. Get Confirmed UTXOs
        utxos = chain_state.get_utxos_by_script(script)
        
        balance = 0
        
        if mempool:
            # Build set of spent outpoints in mempool
            # optimized: This should be passed in or cached if calling in loop? 
            # For now, simplistic iteration.
            mempool_spent = set()
            mempool_outputs = []
            
            for tx in mempool.get_all_transactions():
                tx_hash = tx.get_hash().hex()
                # Inputs spent
                for vin in tx.vin:
                    mempool_spent.add((vin.prev_hash.hex(), vin.prev_index))
                # Outputs created for this addr
                for i, vout in enumerate(tx.vout):
                    if vout.script_pubkey == script:
                        balance += vout.amount

            # Filter confirmed UTXOs
            for u in utxos:
                # Handle types
                u_txid = u['txid']
                if isinstance(u_txid, bytes):
                    u_txid = u_txid.decode('utf-8') # or hex encode depending on DB
                    # The DB returns hex string usually? 
                    # databases.py: cursor.execute("SELECT txid, vout..."). txid is TEXT?
                    # Let's assume hex string.
                    # Wait, earlier debug prints suggested confusion. 
                    # If DB returns bytes (blob), we need hex.
                    # Attempt safe conversion
                    try:
                         # verify if it's already hex
                         binascii.unhexlify(u_txid) 
                         # It IS hex string
                    except:
                         # It is bytes?
                         u_txid = binascii.hexlify(u_txid).decode('utf-8')

                if (u_txid, u['vout']) in mempool_spent:
                    continue # Spent in mempool
                balance += u['amount']
        else:
            # Simple sum
            balance = sum([u['amount'] for u in utxos])
            
        return balance

    def get_balance(self, chain_state):
        """Calculate total balance by scanning UTXOs for all keys."""
        total = 0
        for key in self.keys:
            total += self.get_address_balance(key['addr'], chain_state)
        return total

    def create_transaction(self, to_addr, amount, chain_state, current_height, fee=1000, mempool=None):
        """Create a signed transaction sending 'amount' to 'to_addr'."""
        # 1. Collect UTXOs
        from icsicoin.core.primitives import Transaction, TxIn, TxOut
        
        needed = amount + fee
        collected = 0
        inputs = []
        my_keys = {k['addr']: k for k in self.keys}
        
        # Iterate all my addresses to find funds
        change_addr_str = None
        
        had_skips_due_to_maturity = False

        for key in self.keys:
            addr = key['addr']
            pubkey_hash = binascii.unhexlify(addr)
            script = b'\x76\xa9\x14' + pubkey_hash + b'\x88\xac'
            
            utxos = chain_state.get_utxos_by_script(script)
            
            # --- MEMPOOL OUT-OF-BAND LOGIC ---
            if mempool:
                # 1. Filter out UTXOs that are already spent in mempool
                # optimize: build set of spent (hash, index)
                # This should be done once outside the loop for efficiency, but let's do it inline or prep.
                pass 
                
        # Optimization: Pre-calculate mempool impacts
        mempool_spent = set()
        mempool_outputs = [] # List of (txid, vout, amount, script_pubkey)
        
        if mempool:
             for tx in mempool.get_all_transactions():
                 tx_hash = tx.get_hash().hex()
                 # Inputs spent
                 for vin in tx.vin:
                     mempool_spent.add((vin.prev_hash.hex(), vin.prev_index))
                     # Also handle byte/str discrepancy if prev_hash is bytes
                     # vin.prev_hash is bytes usually
                     
                 # Outputs created
                 for i, vout in enumerate(tx.vout):
                     mempool_outputs.append({
                         'txid': tx_hash,
                         'vout': i,
                         'amount': vout.amount,
                         'script_pubkey': vout.script_pubkey,
                         'is_coinbase': tx.is_coinbase(),
                         'block_height': current_height + 1 # Unconfirmed
                     })

        for key in self.keys:
            addr = key['addr']
            pubkey_hash = binascii.unhexlify(addr)
            script = b'\x76\xa9\x14' + pubkey_hash + b'\x88\xac'
            
            # Get Confirmed UTXOs
            metrics_utxos = chain_state.get_utxos_by_script(script)
            
            # Mix in Mempool Outputs for THIS address
            # (Zero-conf chaining)
            for mout in mempool_outputs:
                if mout['script_pubkey'] == script:
                     # Add to candidate list
                     # Format must match get_utxos_by_script result
                     metrics_utxos.append(mout)
            
            if not metrics_utxos:
                continue
                
            if change_addr_str is None:
                change_addr_str = addr # Send change back to first address with funds
                
            for u in metrics_utxos:
                # CHECK IF SPENT IN MEMPOOL
                # DEBUG
                print(f"DEBUG: Checking UTXO: {u['txid']} type: {type(u['txid'])} vout: {u['vout']}", flush=True)
                print(f"DEBUG: Mempool Spent: {mempool_spent}", flush=True)
                
                if (u['txid'], u['vout']) in mempool_spent:
                     print("DEBUG: SKIPPING SPENT UTXO", flush=True)
                     continue
                     
                # CHECK IF SPENT IN MEMPOOL (Bytes Key compatibility)
                # u['txid'] from DB is hex string? check databases.py. Yes, hex string.
                # our mempool_spent set has (hex_str, int).
                if isinstance(u['txid'], bytes):
                    print("DEBUG: Handling bytes txid", flush=True) 
                    txid_str = u['txid'].decode('utf-8')
                    if (txid_str, u['vout']) in mempool_spent:
                         print("DEBUG: SKIPPING SPENT UTXO (Bytes decoded)", flush=True)
                         continue
                    # Also try hex conversion if it's raw bytes
                    try:
                        txid_hex = binascii.hexlify(u['txid']).decode('utf-8')
                        if (txid_hex, u['vout']) in mempool_spent:
                            print("DEBUG: SKIPPING SPENT UTXO (Hexified)", flush=True)
                            continue
                    except: pass
                
                # Check Coinbase Maturity (100 blocks)
                # Coinbase Maturity Check (100 blocks)
                if u.get('is_coinbase', False):
                    # Depth = current_height - block_height + 1? 
                    # Usually: if height is 100 and mined at 100, depth is 1.
                    # Mined at 100, can spend at 200 (100 blocks later)? 
                    # "100 confirmations" usually means depth >= 100.
                    # so if mined at H, can spend at H+100?
                    # Rule: "Coinbase transaction outputs can only be spent after they have received at least 100 confirmations."
                    # If mined at height H, it has 1 confirmation. at H+99 it has 100.
                    # So current_height - u['block_height'] + 1 >= 100
                    depth = current_height - u.get('block_height', 0) + 1
                    if depth < 100:
                        had_skips_due_to_maturity = True
                        continue

                collected += u['amount']
                # Create Unsigned Input
                # We need script_sig logic. 
                # For signing, we temporarily put empty script_sig or public key?
                # Standard practice: Leave blank, then sign.
                inputs.append({
                    'txid': binascii.unhexlify(u['txid']),
                    'vout': u['vout'],
                    'amount': u['amount'],
                    'script_pubkey': script,
                    'key': key # Private key needed for signing
                })
                
                if collected >= needed:
                    break
            if collected >= needed:
                break
                
        if collected < needed:
            if had_skips_due_to_maturity:
                raise ValueError("You have to wait for the blockchain to mature.")
            raise ValueError(f"Insufficient funds. Have {collected}, need {needed}")
            
        # 2. Outputs
        outputs = []
        # Target
        to_pubkey_hash = binascii.unhexlify(to_addr)
        to_script = b'\x76\xa9\x14' + to_pubkey_hash + b'\x88\xac'
        outputs.append(TxOut(amount, to_script))
        
        # Change
        change = collected - needed
        if change > 0:
            change_pubkey_hash = binascii.unhexlify(change_addr_str)
            change_script = b'\x76\xa9\x14' + change_pubkey_hash + b'\x88\xac'
            outputs.append(TxOut(change, change_script))
            
        # 3. Construct Tx
        tx_ins = [TxIn(inp['txid'], inp['vout']) for inp in inputs]
        tx = Transaction(vin=tx_ins, vout=outputs)
        
        # 4. Sign Inputs
        # This requires SIGHASH_ALL logic which might be in validation.py or need to be implemented here.
        # We need `get_signature_hash` method on Transaction? 
        # Or reuse validation logic.
        # In `validation.py`, we check signature.
        # We need the reverse: Generate signature.
        # SIGHASH_ALL: Serialize Tx with current input script replaced by sub-script (script_pubkey of UTXO)
        
        from icsicoin.core.hashing import double_sha256
        import struct
        
        for i, inp in enumerate(inputs):
            # Sign for input i
            # 1. Get Preimage
            # Simplistic SIGHASH_ALL implementation
            # (Matches validation logic ideally)
            
            # Clone tx for signing
            # Set scripts for all inputs to empty, EXCEPT current one set to script_pubkey
            # (This is the classic Bitcoin SIGHASH_ALL procedure)
            
            tmp_tx_ins = []
            for j, tx_in in enumerate(tx.vin):
                if i == j:
                     script = inp['script_pubkey']
                else:
                     script = b''
                tmp_tx_ins.append(TxIn(tx_in.prev_hash, tx_in.prev_index, script, tx_in.sequence))
            
            tmp_tx = Transaction(vin=tmp_tx_ins, vout=tx.vout, locktime=tx.locktime)
            msg = tmp_tx.serialize() + struct.pack("<I", 1) # Append SIGHASH_ALL (1)
            sighash = double_sha256(msg)
            
            # 2. Sign
            priv_key_hex = inp['key']['priv']
            sk = ecdsa.SigningKey.from_string(binascii.unhexlify(priv_key_hex), curve=ecdsa.SECP256k1)
            sig = sk.sign_digest(sighash, sigencode=ecdsa.util.sigencode_der_canonize)
            
            # 3. Append HashType
            sig += b'\x01' # SIGHASH_ALL
            
            # 4. Build ScriptSig: <Sig> <PubKey>
            pub_key_bytes = binascii.unhexlify(inp['key']['pub'])
            
            # Push opcodes (simple length prefix)
            def push_data(data):
                l = len(data)
                if l < 0x4c:
                    return bytes([l]) + data
                elif l <= 0xff:
                    return b'\x4c' + bytes([l]) + data
                # ... assume small for keys
                return bytes([l]) + data

            script_sig = push_data(sig) + push_data(pub_key_bytes)
            
            # 5. Update Tx Input
            tx.vin[i].script_sig = script_sig
            
        return tx
