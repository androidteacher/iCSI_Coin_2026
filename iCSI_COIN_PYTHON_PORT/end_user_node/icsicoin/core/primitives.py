import io
import time
from .serialization import (
    encode_uint32, decode_uint32,
    encode_uint64, decode_uint64,
    encode_varint, decode_varint,
    encode_varstr, decode_varstr,
    serialize_list, deserialize_list
)
from .hashing import double_sha256, hash_to_hex

class TxIn:
    def __init__(self, prev_hash=b'\x00'*32, prev_index=0xffffffff, script_sig=b'', sequence=0xffffffff):
        self.prev_hash = prev_hash
        self.prev_index = prev_index
        self.script_sig = script_sig
        self.sequence = sequence

    def serialize(self):
        return (
            self.prev_hash +
            encode_uint32(self.prev_index) +
            encode_varstr(self.script_sig) +
            encode_uint32(self.sequence)
        )

    @classmethod
    def deserialize(cls, f):
        prev_hash = f.read(32)
        if len(prev_hash) < 32: raise EOFError("TxIn prev_hash")
        prev_index = decode_uint32(f)
        script_sig = decode_varstr(f)
        sequence = decode_uint32(f)
        return cls(prev_hash, prev_index, script_sig, sequence)

    def __repr__(self):
        return f"TxIn({hash_to_hex(self.prev_hash)}:{self.prev_index})"

class TxOut:
    def __init__(self, amount=0, script_pubkey=b''):
        self.amount = amount
        self.script_pubkey = script_pubkey

    def serialize(self):
        return (
            encode_uint64(self.amount) +
            encode_varstr(self.script_pubkey)
        )

    @classmethod
    def deserialize(cls, f):
        amount = decode_uint64(f)
        script_pubkey = decode_varstr(f)
        return cls(amount, script_pubkey)

    def __repr__(self):
        return f"TxOut({self.amount})"

class Transaction:
    def __init__(self, version=1, vin=None, vout=None, locktime=0):
        self.version = version
        self.vin = vin if vin is not None else []
        self.vout = vout if vout is not None else []
        self.locktime = locktime

    def serialize(self):
        return (
            encode_uint32(self.version) +
            serialize_list(self.vin, lambda x: x.serialize()) +
            serialize_list(self.vout, lambda x: x.serialize()) +
            encode_uint32(self.locktime)
        )

    @classmethod
    def deserialize(cls, f):
        version = decode_uint32(f)
        vin = deserialize_list(f, TxIn.deserialize)
        vout = deserialize_list(f, TxOut.deserialize)
        locktime = decode_uint32(f)
        return cls(version, vin, vout, locktime)

    def get_hash(self):
        return double_sha256(self.serialize())

    def is_coinbase(self):
        if len(self.vin) != 1:
            return False
        # Coinbase input: prev_hash = 0 (32 bytes), prev_index = 0xffffffff
        vin = self.vin[0]
        return vin.prev_hash == b'\x00'*32 and vin.prev_index == 0xffffffff

    @property
    def txid(self):
        return hash_to_hex(self.get_hash())

class BlockHeader:
    def __init__(self, version=1, prev_block=b'\x00'*32, merkle_root=b'\x00'*32, timestamp=None, bits=0x1d00ffff, nonce=0):
        self.version = version
        self.prev_block = prev_block
        self.merkle_root = merkle_root
        self.timestamp = timestamp if timestamp is not None else int(time.time())
        self.bits = bits
        self.nonce = nonce

    def serialize(self):
        return (
            encode_uint32(self.version) +
            self.prev_block +
            self.merkle_root +
            encode_uint32(self.timestamp) +
            encode_uint32(self.bits) +
            encode_uint32(self.nonce)
        )

    @classmethod
    def deserialize(cls, f):
        version = decode_uint32(f)
        prev_block = f.read(32)
        merkle_root = f.read(32)
        timestamp = decode_uint32(f)
        bits = decode_uint32(f)
        nonce = decode_uint32(f)
        return cls(version, prev_block, merkle_root, timestamp, bits, nonce)

    def get_hash(self):
        # Note: In real setup this uses scrypt, but header hash structure is same
        # We will need the scrypt binding in a separate function for PoW check
        return double_sha256(self.serialize())

    @property
    def hash(self):
        return hash_to_hex(self.get_hash())

    @property
    def difficulty(self):
        """Calculate difficulty from bits (compact target)."""
        # Extract 3 most significant bytes as coefficient
        exponent = self.bits >> 24
        coefficient = self.bits & 0xffffff
        target = coefficient * (256**(exponent - 3))
        
        # Genesis target (0x1f099996) usually implies Diff 1, but standard Bitcoin/Litecoin uses 0x1d00ffff for Diff 1.
        # iCSI Coin presumably uses standard Diff 1 for calculation.
        # Difficulty = (Target_1 / Target_Current)
        # Target_1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
        # (Compact: 0x1d00ffff)
        
        target_1 = 0xffff * (256**(0x1d - 3))
        if target == 0: return 0
        return target_1 / target

class Block:
    def __init__(self, header=None, vtx=None):
        self.header = header if header else BlockHeader()
        self.vtx = vtx if vtx is not None else []

    def serialize(self):
        return (
            self.header.serialize() +
            serialize_list(self.vtx, lambda x: x.serialize())
        )

    @classmethod
    def deserialize(cls, f):
        header = BlockHeader.deserialize(f)
        vtx = deserialize_list(f, Transaction.deserialize)
        return cls(header, vtx)

    def get_hash(self):
        return self.header.get_hash()

    @property
    def hash(self):
        return self.header.hash
