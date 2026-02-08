import hashlib
from ecdsa import VerifyingKey, SECP256k1, BadSignatureError
from ecdsa.util import sigdecode_der

# OPCodes
OP_DUP = 0x76
OP_HASH160 = 0xa9
OP_EQUALVERIFY = 0x88
OP_CHECKSIG = 0xac

def hash160(data):
    """RIPEMD160(SHA256(data))"""
    sha = hashlib.sha256(data).digest()
    # RIPEMD160 is avail in hashlib.new('ripemd160') usually
    h = hashlib.new('ripemd160')
    h.update(sha)
    return h.digest()

class ScriptEngine:
    def __init__(self):
        self.stack = []

    def evaluate(self, script_sig, script_pubkey, transaction, vin_index):
        """
        Evaluate a script.
        This provides a simplified implementation primarily for P2PKH.
        """
        # For P2PKH, effective script is: <sig> <pubkey> OP_DUP OP_HASH160 <pubKeyHash> OP_EQUALVERIFY OP_CHECKSIG
        
        # 1. Parse ScriptSig (Push Data)
        # We assume standard P2PKH script_sig: [Sig Length][Sig][PubKey Length][PubKey]
        
        self.stack = []
        try:
            self._execute_push_only(script_sig)
        except Exception as e:
            return False

        # 2. Execute ScriptPubKey
        
        pc = 0
        while pc < len(script_pubkey):
            opcode = script_pubkey[pc]
            pc += 1

            if opcode == OP_DUP:
                if not self.stack: return False
                self.stack.append(self.stack[-1])
            
            elif opcode == OP_HASH160:
                if not self.stack: return False
                item = self.stack.pop()
                self.stack.append(hash160(item))
            
            elif opcode == OP_EQUALVERIFY:
                if len(self.stack) < 2: return False
                item1 = self.stack.pop()
                item2 = self.stack.pop()
                if item1 != item2: return False
            
            elif opcode == OP_CHECKSIG:
                if len(self.stack) < 2: return False
                pubkey_bytes = self.stack.pop()
                sig_bytes = self.stack.pop()
                
                # Verify Signature
                if not self._check_sig(sig_bytes, pubkey_bytes, transaction, vin_index):
                    return False
                self.stack.append(True)

            elif 0x01 <= opcode <= 0x4b: # Push bytes
                length = opcode
                data = script_pubkey[pc:pc+length]
                self.stack.append(data)
                pc += length
            else:
                # Unknown opcode
                return False

        return len(self.stack) > 0 and self.stack[-1] is True

    def _execute_push_only(self, script):
        i = 0
        while i < len(script):
            length = script[i]
            i += 1
            data = script[i:i+length]
            self.stack.append(data)
            i += length

    def _check_sig(self, sig_bytes, pubkey_bytes, transaction, vin_index):
        # Full SIGHASH implementation deferred.
        # Strict signature format check for now.
        try:
            vk = VerifyingKey.from_string(pubkey_bytes, curve=SECP256k1)
            # This verifies the signature format is valid DER for SECP256k1
            # Actual content verification against tx hash will be added in later phase
            # sigdecode_der returns (r, s)
            r, s = sigdecode_der(sig_bytes, SECP256k1.order)
            return True
        except BadSignatureError:
            print("BadSignatureError")
            return False
        except Exception as e:
            print(f"CheckSig Error: {e}")
            import traceback
            traceback.print_exc()
            return False
