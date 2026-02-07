import unittest
import io
import sys
import os

# Adjust path to import icsicoin
sys.path.append('/home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node')

from icsicoin.core.serialization import encode_varint, decode_varint
from icsicoin.core.primitives import Transaction, TxIn, TxOut, Block, BlockHeader

class TestSerialization(unittest.TestCase):
    def test_varint(self):
        cases = [
            (0, b'\x00'),
            (0xfc, b'\xfc'),
            (0xfd, b'\xfd\xfd\x00'),
            (0xffff, b'\xfd\xff\xff'),
            (0x10000, b'\xfe\x00\x00\x01\x00'),
        ]
        for val, encoded in cases:
            self.assertEqual(encode_varint(val), encoded)
            f = io.BytesIO(encoded)
            self.assertEqual(decode_varint(f), val)

    def test_transaction(self):
        tx = Transaction()
        tx.vin.append(TxIn(prev_hash=b'\x01'*32, prev_index=0))
        tx.vout.append(TxOut(amount=5000000000, script_pubkey=b'\x76\xa9'))
        
        serialized = tx.serialize()
        f = io.BytesIO(serialized)
        tx2 = Transaction.deserialize(f)
        
        self.assertEqual(tx.version, tx2.version)
        self.assertEqual(len(tx.vin), len(tx2.vin))
        self.assertEqual(tx2.vin[0].prev_hash, b'\x01'*32)
        self.assertEqual(tx2.vout[0].amount, 5000000000)

    def test_block(self):
        block = Block()
        block.header.nonce = 12345
        tx = Transaction()
        block.vtx.append(tx)
        
        serialized = block.serialize()
        f = io.BytesIO(serialized)
        block2 = Block.deserialize(f)
        
        self.assertEqual(block.header.nonce, block2.header.nonce)
        self.assertEqual(len(block.vtx), 1)

if __name__ == '__main__':
    unittest.main()
