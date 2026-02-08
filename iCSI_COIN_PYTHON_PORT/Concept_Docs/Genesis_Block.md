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

## How to Edit

1.  Open `end_user_node/icsicoin/core/chain.py`.
2.  Find the string inside the `TxIn` constructor (starts with `b'...'`).
3.  Replace the text with your desired message.
    - **Note:** The message must be bytes (prefixed with `b`) or encoded to bytes.

## ⚠️ CRITICAL: Reset Required

Changing the Genesis Block changes its hash. Since every subsequent block builds upon the previous hash, **modifying the Genesis Block invalidates the entire existing blockchain.**

To make your changes take effect, you **MUST start a new blockchain**:

1.  **Stop your node**: `docker compose down`
2.  **Delete existing data**:
    ```bash
    # WARNING: This deletes your wallet too! Back up wallet.dat if you have funds.
    sudo rm -rf end_user_node/wallet_data/*
    ```
3.  **Rebuild and Start**:
    ```bash
    cd end_user_node
    docker compose up -d --build
    ```

The node will automatically generate the new Genesis Block with your custom message upon startup.
