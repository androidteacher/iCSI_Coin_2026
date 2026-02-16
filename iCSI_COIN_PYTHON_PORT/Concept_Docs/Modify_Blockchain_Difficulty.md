# Blockchain Difficulty — iCSI Coin

## How Difficulty Works

Mining difficulty controls **how hard it is to find a valid block**. The miner repeatedly hashes a block header with different nonce values until the resulting hash is **has a certain number of leading zeros**. More Zeros = harder mining = longer block times.

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

## Where to Change Difficulty (You would need to do this before running your first node)

You must update **all 3 files** and then wipe blockchain data with `clear_stack.sh`.

### File 1: Genesis Block (REQUIRED)

```
end_user_node/icsicoin/core/chain.py  →  line ~40
```

```python
bits=0x1d00ffff,  # ← Change this value
```

This defines the difficulty of the **genesis block** — the starting point for the entire chain.

### File 2: Web Server Default (REQUIRED)

```
end_user_node/icsicoin/web/server.py  →  line ~180
```

```python
bits = 0x1d00ffff  # ← Must match genesis
```

This is the fallback difficulty shown in the UI when no blocks exist yet.

### File 3: RPC Block Template (REQUIRED)

```
end_user_node/icsicoin/rpc/rpc_server.py  →  line ~127
```

```python
"bits": 0x1d00ffff,  # ← Must match genesis
```

This is the difficulty sent to the miner when constructing new blocks.

> **⚠ All 3 values MUST match.** After changing, run `clear_stack.sh` to wipe all blockchain data and rebuild.

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
# From project root:
bash clear_stack.sh
# Type YES when prompted
```

This stops all containers, deletes all blockchain/wallet data, and rebuilds everything with the new genesis block.
