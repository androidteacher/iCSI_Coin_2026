# Blockchain Difficulty — iCSI Coin

## How Difficulty Works

Mining difficulty controls **how hard it is to find a valid block**. The miner repeatedly hashes a block header with different nonce values until the resulting hash is **numerically below the target** — which, in practice, means it starts with a certain number of leading zero bits. More zeros = harder mining = longer block times. (See [BLOCK_HASH.md](BLOCK_HASH.md) for how leading zeros, hex digits, and bits relate.)

## The `bits` Value (Compact Target Format)

Difficulty is stored as a 4-byte integer called **`bits`** using Bitcoin's compact target encoding:

```
bits = 0xEECCCCCC
         │ └─────── Coefficient (3 bytes)
         └───────── Exponent (1 byte)
```

**Formula:**

```
Target = Coefficient × 256^(Exponent - 3)
```

### Key Rules

- **Lower exponent** = exponentially harder (each step down = 256× harder)
- **Lower coefficient** = linearly harder within the same exponent
- The **decimal representation** of `bits` is NOT a linear difficulty scale

---

## Where to Change Difficulty (do this before running your first node)

Difficulty now **retargets dynamically** (`calculate_next_bits()` in `consensus/validation.py`), and the web UI and RPC block template both read the difficulty from that function automatically. So you only change the **starting** difficulty, which lives in **two places that must hold the same value**, then wipe the chain.

### Place 1: The difficulty constant (REQUIRED)

```
end_user_node/icsicoin/consensus/validation.py  →  GENESIS_BITS
```

```python
GENESIS_BITS = 0x1f099996   # ← starting difficulty used for all early blocks; change this
```

### Place 2: The genesis block header (REQUIRED — must match Place 1)

```
end_user_node/icsicoin/core/chain.py  →  _create_genesis_block()  (the BlockHeader `bits=`)
```

```python
bits=0x1f099996,   # ← must be the SAME value as GENESIS_BITS above
```

> **Both values MUST match.** If they differ, the genesis block's difficulty disagrees with the retarget rule and the node rejects its own chain.
>
> You do **NOT** need to edit `web/server.py` or `rpc/rpc_server.py` — they call `calculate_next_bits()` and get the right value automatically. (The current value in the code is `0x1f099996`.)

---

## Example Difficulty Values

| Bits (Hex) | Decimal | Exponent | Coefficient | Relative Difficulty | Estimated Block Time* |
|---|---|---|---|---|---|
| `0x1f0fffff` | 520,945,663 | 31 | 0x0fffff | 1× (baseline) | ~1 second |
| `0x1f019999` | 520,177,049 | 31 | 0x019999 | ~10× | ~2-3 seconds |
| `0x1e00ffff` | 503,382,015 | 30 | 0x00ffff | ~16× | ~5-10 seconds |
| `0x1e003fff` | 503,332,863 | 30 | 0x003fff | ~256× | ~15-30 seconds |
| `0x1e000fff` | 503,320,575 | 30 | 0x000fff | ~1,024× | ~1-2 minutes |
| **`0x1d00ffff`** | **486,604,799** | **29** | **0x00ffff** | **~4,096×** | **~5-10 minutes** |
| `0x1d003fff` | 486,555,647 | 29 | 0x003fff | ~65,536× | ~1-2 hours |
| `0x1c00ffff` | 469,827,583 | 28 | 0x00ffff | ~1,048,576× | ~Days |

*\* Block times are rough estimates for a single CPU miner. Multiple miners reduce block time proportionally.*

---

## Quick Reference: Adjusting Block Time

If blocks are coming **too fast**, pick a value **further down** the table (lower hex value).

If blocks are coming **too slow**, pick a value **further up** the table (higher hex value).

### Fine-Tuning Within an Exponent

To make small adjustments without changing the exponent, adjust the coefficient:

```
0x1d00ffff  →  Easiest at exponent 29 (coeff = 65535)
0x1d007fff  →  2× harder             (coeff = 32767)
0x1d003fff  →  4× harder             (coeff = 16383)
0x1d001fff  →  8× harder             (coeff = 8191)
0x1d000fff  →  16× harder            (coeff = 4095)
0x1d0000ff  →  256× harder           (coeff = 255)
```

### Jumping Exponents

Each exponent drop = **256× harder**:

```
0x1f______  →  Exponent 31 (easiest)
0x1e______  →  Exponent 30 (256× harder)
0x1d______  →  Exponent 29 (65,536× harder)
0x1c______  →  Exponent 28 (16,777,216× harder)
```

---

## Reset Procedure

After changing difficulty:

```bash
# From the project root:
cd iCSI_COIN_PYTHON_PORT/BLOCKCHAIN_RESET_SCRIPTS
./clear_stack.sh
# Type YES when prompted
```

This stops all containers, deletes all blockchain/wallet data, and rebuilds everything with the new genesis block.
