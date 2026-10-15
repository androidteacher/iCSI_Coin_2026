# Modifying the Genesis Block

The Genesis Block is the first block in the blockchain (Block 0). It is hardcoded into the software and serves as the foundation for the entire chain.

## Location in Code

The Genesis Block definition is located in:
**`end_user_node/icsicoin/core/chain.py`**

Specifically, look for the `_create_genesis_block` method within the `ChainManager` class (Around **Line 28**):

```python
22:     def _create_genesis_block(self):
23:         """Creates the hardcoded Genesis Block object"""
24:         from icsicoin.core.primitives import Block, BlockHeader, Transaction, TxIn, TxOut
25:         from icsicoin.consensus.merkle import get_merkle_root
26:         
27:         # Create Genesis with standard params
28:         tx = Transaction(
29:              vin=[TxIn(b'\x00'*32, 0xffffffff, b'iCSI_COIN is a wholly owned Subsidiary of BeckCoin. Trademark: Beckmeister Industries.', 0xffffffff)],
30:              vout=[TxOut(5000000000, b'\x00'*25)] # Empty/burned output for genesis
31:         )
```

## Create Your Own Coin (Custom Genesis Block)

To spawn a whole new chain with a custom genesis block, see the [Create Your Own Coin guide](../../CREATE_YOUR_OWN_COIN_DIRECTIONS/Readme.md) — it covers both the automatic script and the manual route.

If you change the genesis message, timestamp, or difficulty by hand, you must also re-mine a valid nonce for the new header: see [Hash Your New Genesis Block](Hash_Your_New_Genesis_Block.md).
