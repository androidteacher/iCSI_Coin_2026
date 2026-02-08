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

    def get_balance(self, chain_state):
        """Calculate total balance by scanning UTXOs for all keys."""
        total = 0
        for key in self.keys:
            addr = key['addr']
            pubkey_hash = binascii.unhexlify(addr)
            # P2PKH Script: OP_DUP OP_HASH160 <pubKeyHash> OP_EQUALVERIFY OP_CHECKSIG
            script = b'\x76\xa9\x14' + pubkey_hash + b'\x88\xac'
            
            utxos = chain_state.get_utxos_by_script(script)
            for u in utxos:
                total += u['amount']
        return total

    def create_transaction(self, to_addr, amount, chain_state, fee=1000):
        """Create a signed transaction sending 'amount' to 'to_addr'."""
        # 1. Collect UTXOs
        from icsicoin.core.primitives import Transaction, TxIn, TxOut
        
        needed = amount + fee
        collected = 0
        inputs = []
        my_keys = {k['addr']: k for k in self.keys}
        
        # Iterate all my addresses to find funds
        change_addr_str = None
        
        for key in self.keys:
            addr = key['addr']
            pubkey_hash = binascii.unhexlify(addr)
            script = b'\x76\xa9\x14' + pubkey_hash + b'\x88\xac'
            
            utxos = chain_state.get_utxos_by_script(script)
            if not utxos:
                continue
                
            if change_addr_str is None:
                change_addr_str = addr # Send change back to first address with funds
                
            for u in utxos:
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
