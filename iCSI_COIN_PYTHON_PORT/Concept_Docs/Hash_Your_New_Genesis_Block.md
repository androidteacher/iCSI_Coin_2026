# Concept: Hash Your New Genesis Block

## 1. The "Avalanche" Effect
In a blockchain, every block header contains a **Merkle Root** (summary of transactions) and a **Timestamp**.

If you change **ANYTHING** in the Genesis Block:
*   Changing the **Message** ("iCSI Coin is...") -> Changes the Transaction Hash -> Changes the Merkle Root -> Changes the Block Header.
*   Changing the **Timestamp** -> Changes the Block Header.

## 2. The Problem
The moment the Block Header changes, the **Proof of Work (PoW)** becomes invalid.
The old `Nonce` (e.g., `2083236893`) combined with the *new* header will likely result in a hash that is **way above the target** (i.e., not enough leading zeros).

The node will reject your new Genesis Block saying "High Hash" or "Insufficient PoW".

## 3. The Solution: Re-Mine the Genesis
To fix this, you must run a script to find a **New Nonce** that, when combined with your new header parameters, results in a valid Scrypt hash.

## 4. The Genesis Miner Script
Save the following code as `genesis_miner.py` in your `end_user_node` directory (next to `miner.py`) and run it.

```python
#!/usr/bin/env python3
import time
import struct
import binascii
import scrypt
from icsicoin.core.primitives import BlockHeader, Transaction, TxIn, TxOut
from icsicoin.consensus.merkle import get_merkle_root

# --- CONFIGURATION (MUST MATCH YOUR chain.py) ---
TIMESTAMP = 1231006505
BITS = 0x1f099996
MESSAGE = b'iCSI_COIN is a wholly owned Subsidiary of BeckCoin. Trademark: Beckmeister Industries.'
# ------------------------------------------------

def mine_genesis():
    print(f"[-] Preparing Genesis Block...")
    print(f"[-] Message: {MESSAGE}")
    print(f"[-] Timestamp: {TIMESTAMP}")
    print(f"[-] Bits: {hex(BITS)}")

    # 1. Create the Genesis Transaction
    tx = Transaction(
        vin=[TxIn(b'\x00'*32, 0xffffffff, MESSAGE, 0xffffffff)],
        vout=[TxOut(5000000000, b'\x00'*25)]
    )

    # 2. Convert Bits to Target
    exponent = BITS >> 24
    coefficient = BITS & 0xffffff
    target = coefficient * (256**(exponent - 3))
    print(f"[-] Target: {target}")

    # 3. Calculate Merkle Root
    merkle_root = get_merkle_root([tx])
    print(f"[-] Merkle Root: {binascii.hexlify(merkle_root).decode()}")

    # 4. Mine
    print(f"[*] Starting Mining (Scrypt)...")
    nonce = 0
    start = time.time()
    
    while True:
        # Construct Header (manually or via object)
        # Version(4) + Prev(32) + Merkle(32) + Time(4) + Bits(4) + Nonce(4)
        header = BlockHeader(1, b'\x00'*32, merkle_root, TIMESTAMP, BITS, nonce)
        header_bytes = header.serialize()
        
        # Scrypt Hash
        pow_hash = scrypt.hash(header_bytes, header_bytes, N=1024, r=1, p=1, buflen=32)
        pow_int = int.from_bytes(pow_hash, 'little')
        
        if pow_int <= target:
            print(f"\n[+] FOUND VALID NONCE!")
            print(f"    Nonce: {nonce}")
            print(f"    Scrypt Hash: {binascii.hexlify(pow_hash).decode()}")
            print(f"    Block Hash (SHA256): {binascii.hexlify(header.get_hash()).decode()}")
            break
        
        nonce += 1
        if nonce % 100000 == 0:
            print(f"    Scanning... Nonce {nonce} ({nonce/(time.time()-start):.2f} H/s)", end='\r')

if __name__ == "__main__":
    mine_genesis()
```

## 5. Where to Insert the Result
Once the script prints the `Nonce`, update `icsicoin/core/chain.py`:

```python
    def _create_genesis_block(self):
        # ...
        header = BlockHeader(
             version=1,
             prev_block=b'\x00'*32,
             merkle_root=merkle_root,
             timestamp=1231006505,   # <--- Ensure this matches your script
             bits=0x1f099996,        # <--- Ensure this matches your script
             nonce=YOUR_NEW_NONCE    # <--- INSERT NEW NONCE HERE
        )
        return Block(header, [tx])
```

**Note**: You do not need to insert the Hash itself. The code calculates the hash dynamically using your new valid Nonce.
