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

To learn how to spawn a new chain with a custom genesis block, please refer to the [Blockchain Reset Scripts Documentation](https://github.com/androidteacher/iCSI_Coin_2026/blob/main/iCSI_COIN_PYTHON_PORT/BLOCKCHAIN_RESET_SCRIPTS/README.md).
