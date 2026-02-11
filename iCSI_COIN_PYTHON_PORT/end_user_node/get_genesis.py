import sys
import os
sys.path.append(os.getcwd())

from icsicoin.core.primitives import Block, BlockHeader, Transaction, TxIn, TxOut
from icsicoin.consensus.merkle import get_merkle_root

# Create Genesis with standard params
tx = Transaction(
     vin=[TxIn(b'\x00'*32, 0xffffffff, b'iCSI_COIN is a wholly owned Subsidiary of BeckCoin. Trademark: Beckmeister Industries.', 0xffffffff)],
     vout=[TxOut(5000000000, b'\x00'*25)] # Empty/burned output for genesis
)

merkle_root = get_merkle_root([tx])

header = BlockHeader(
     version=1,
     prev_block=b'\x00'*32,
     merkle_root=merkle_root,
     timestamp=1231006505,
     bits=0x1f099996, # 6x easier than original (dynamic retarget adjusts)
     nonce=2083236893
)
block = Block(header, [tx])
print(block.get_hash().hex())
