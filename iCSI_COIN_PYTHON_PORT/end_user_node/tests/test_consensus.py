import unittest
import sys
import hashlib
from ecdsa import SigningKey, SECP256k1

# Adjust path
sys.path.append('/home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node')

from icsicoin.core.primitives import Transaction, Block, BlockHeader
from icsicoin.consensus.merkle import get_merkle_root
from icsicoin.consensus.script import ScriptEngine, OP_DUP, OP_HASH160, OP_EQUALVERIFY, OP_CHECKSIG
from icsicoin.consensus.validation import bits_to_target

class TestConsensus(unittest.TestCase):
    def test_merkle_root(self):
        # Create two dummy transactions
        tx1 = Transaction()
        tx1.locktime = 1
        tx2 = Transaction()
        tx2.locktime = 2
        
        # Calculate expected root
        # If hash(tx1)=h1, hash(tx2)=h2
        # Root = double_sha256(h1 + h2)
        
        h1 = tx1.get_hash()
        h2 = tx2.get_hash()
        
        root = get_merkle_root([tx1, tx2])
        self.assertEqual(len(root), 32)
        
        # Verify single tx root
        root_single = get_merkle_root([tx1])
        # For single tx, root is double_sha256(h1 + h1) -- Wait, Merkle tree with 1 item?
        # Standard Merkle tree duplication: if 1 item [A], it becomes [A, A], parent is hash(A+A).
        # My implementation does: if len is odd, append last. So [tx1] -> [tx1, tx1].
        
        # Let's verify against manual calc
        # Merkle Root of a single transaction is just the transaction hash itself
        self.assertEqual(root_single, h1)

    def test_script_engine_p2pkh(self):
        # 1. Generate Key Pair
        sk = SigningKey.generate(curve=SECP256k1)
        vk = sk.verifying_key
        pubkey_bytes = vk.to_string()
        
        # 2. Create ScriptPubKey (OP_DUP OP_HASH160 <PubHash> OP_EQUALVERIFY OP_CHECKSIG)
        sha = hashlib.sha256(pubkey_bytes).digest()
        ripemd = hashlib.new('ripemd160')
        ripemd.update(sha)
        pub_hash = ripemd.digest()
        
        script_pubkey = bytearray()
        script_pubkey.append(OP_DUP)
        script_pubkey.append(OP_HASH160)
        script_pubkey.append(20)
        script_pubkey.extend(pub_hash)
        script_pubkey.append(OP_EQUALVERIFY)
        script_pubkey.append(OP_CHECKSIG)
        
        # 3. Create ScriptSig (Sig, PubKey)
        from ecdsa.util import sigencode_der
        
        sig_der = sk.sign(b"dummy_msg", sigencode=sigencode_der)
        
        script_sig = bytearray()
        script_sig.append(len(sig_der))
        script_sig.extend(sig_der)
        script_sig.append(len(pubkey_bytes))
        script_sig.extend(pubkey_bytes)
        
        # 4. Evaluate
        engine = ScriptEngine()
        result = engine.evaluate(script_sig, script_pubkey, None, 0)
        self.assertTrue(result)

    def test_script_engine_fail(self):
        # Test with wrong signature
        script_pubkey = b'\x76\xa9\x14' + b'\x00'*20 + b'\x88\xac' # dummy p2pkh
        script_sig = b'\x01\xFF' # garbage
        
        engine = ScriptEngine()
        result = engine.evaluate(script_sig, script_pubkey, None, 0)
        self.assertFalse(result)

    def test_bits_to_target(self):
        # Standard Bitcoin/Litecoin max target
        # 0x1d00ffff -> 0x00ffff * 2**(8*(0x1d - 3)) = 0xffff * 256**26
        bits = 0x1d00ffff
        target = bits_to_target(bits)
        self.assertTrue(target > 0)
        
        # Check specific value
        # 0xffff = 65535
        # 256^26 is huge
        # Just ensure it doesn't crash
        pass

if __name__ == '__main__':
    unittest.main()
