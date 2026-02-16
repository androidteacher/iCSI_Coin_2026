# The CPU Miner — How iCSI Coin Mining Works

## Overview

The miner is a background process that **creates new blocks** for the blockchain. It repeatedly guesses random numbers until it finds one that produces a hash meeting the network's difficulty requirement. When it finds a valid hash, it submits the new block to the node and earns the block reward (50 iCSI coins).

---

## Step-by-Step: What the Miner Does

### Step 1: Ask the Node for Work

The miner sends an **RPC request** to the node asking: *"What should the next block look like?"*

```
POST http://localhost:9342/
{
    "method": "getblocktemplate",
    "params": [{"mining_address": "abc123..."}]
}
```

The node responds with a **block template** containing:

| Field | Description |
|---|---|
| `previousblockhash` | Hash of the current chain tip (the block we're building on) |
| `merkle_root` | Hash of all transactions to include in this block |
| `bits` | The difficulty target (compact format) |
| `target` | The full 256-bit target number (hex) |
| `height` | Block number we're trying to mine |
| `curtime` | Current timestamp |
| `transactions` | List of transactions (including coinbase reward) |

### Step 2: Build the Block Header

The miner assembles an 80-byte **block header** from the template:

```
┌──────────┬──────────────────┬─────────────┬───────────┬──────┬───────┐
│ Version  │ Prev Block Hash  │ Merkle Root │ Timestamp │ Bits │ Nonce │
│ 4 bytes  │ 32 bytes         │ 32 bytes    │ 4 bytes   │ 4 b  │ 4 b   │
└──────────┴──────────────────┴─────────────┴───────────┴──────┴───────┘
```

Everything is fixed **except the nonce** — that's what the miner changes each attempt.

### Step 3: Hash and Check (The Mining Loop)

This is the core of mining. The miner does this over and over:

```
1. Set nonce = 0
2. Serialize the 80-byte header
3. Hash it using scrypt(header, header, N=1024, r=1, p=1)
4. Convert hash to a number
5. Is the number ≤ the target?
   → YES: We found a valid block! Go to Step 4.
   → NO:  Increment nonce, go back to step 2.
```

**In code** (`controller.py`, line ~128):

```python
header.nonce = nonce
header_bytes = header.serialize()
pow_hash = scrypt.hash(header_bytes, header_bytes, N=1024, r=1, p=1, buflen=32)
pow_int = int.from_bytes(pow_hash, 'little')

if pow_int <= target:
    # FOUND A VALID BLOCK!
```

### Step 4: Submit the Block

When a valid nonce is found, the miner:

1. Assembles the full block (header + all transactions)
2. Serializes it to hex
3. Sends it back to the node via RPC:

```
POST http://localhost:9342/
{
    "method": "submitblock",
    "params": ["0100000000000000...full_block_hex..."]
}
```

The node responds with `"accepted"` or an error.

---

## The Target and Leading Zeros

### What is "Difficulty"?

The **target** is a very large number (256-bit). The hash of a valid block must be **less than or equal to** this target.

Think of it like this:

```
Target:     0000000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
Valid Hash: 00000003A8B2C1D4E5F6... ✅ (starts with more zeros = smaller number)
Bad Hash:   0000001F82A3B4C5D6E7... ❌ (bigger than target)
```

**Lower target = more leading zeros required = harder to find = longer mining time.**

### The "Bits" Compact Format

The target is stored as a 4-byte `bits` value:

```
bits = 0x1F099996

  0x1F = Exponent (31)
  0x099996 = Coefficient

  Target = 0x099996 × 256^(31-3) = a very large number
```

See `Blockchain_Difficulty.md` for full details on adjusting this value.

---

## RPC Communication

The miner communicates with the node entirely through **JSON-RPC** over HTTP.

### RPC Endpoint

```
http://localhost:{RPC_PORT}/
```

Default RPC port for the user node: **9342**

### Authentication

Every RPC call uses HTTP Basic Auth:

```
Username: user
Password: password
```

### Two RPC Methods Used

#### `getblocktemplate` — Get Work

```json
{
    "method": "getblocktemplate",
    "params": [{"mining_address": "wallet_address_hex"}],
    "jsonrpc": "2.0",
    "id": 1
}
```

**Response:**

```json
{
    "result": {
        "version": 1,
        "previousblockhash": "abc123...",
        "curtime": 1770512398,
        "bits": 521145750,
        "height": 42,
        "coinbase_value": 5000000000,
        "transactions": ["hex_encoded_tx_1", "hex_encoded_tx_2"],
        "merkle_root": "def456...",
        "target": "00099996000000000000000000000000000000000000000000000000000000"
    }
}
```

#### `submitblock` — Submit a Mined Block

```json
{
    "method": "submitblock",
    "params": ["full_block_hex_data"],
    "jsonrpc": "2.0",
    "id": 1
}
```

**Response:**

```json
{
    "result": "accepted",
    "error": null
}
```

---

## The Hashing Algorithm: Scrypt

iCSI Coin uses **scrypt** (same as Litecoin), not SHA-256 (Bitcoin).

```python
scrypt.hash(data, salt, N=1024, r=1, p=1, buflen=32)
```

| Parameter | Value | Meaning |
|---|---|---|
| `data` | Block header bytes | What we're hashing |
| `salt` | Block header bytes | Same as data (Litecoin convention) |
| `N` | 1024 | CPU/Memory cost factor |
| `r` | 1 | Block size |
| `p` | 1 | Parallelization factor |
| `buflen` | 32 | Output: 32 bytes (256-bit hash) |

Scrypt is **memory-hard**, meaning it's designed to be difficult to accelerate with specialized hardware (ASICs), making CPU mining more competitive.

---

## Mining Lifecycle Summary

```
┌─────────────┐     getblocktemplate     ┌──────────┐
│   MINER     │ ──────────────────────→  │   NODE   │
│             │ ←────────────────────── │  (RPC)   │
│             │     block template       │          │
│             │                          │          │
│  hash loop  │                          │          │
│  nonce++    │                          │          │
│  check ≤    │                          │          │
│  target     │                          │          │
│             │                          │          │
│  FOUND! ────│──── submitblock ───────→ │          │
│             │ ←──── "accepted" ──────  │          │
└─────────────┘                          └──────────┘
```

---

## Key Code Locations

| File | What It Does |
|---|---|
| `icsicoin/mining/controller.py` | The miner — hash loop, RPC calls, nonce iteration |
| `icsicoin/rpc/rpc_server.py` | RPC server — handles `getblocktemplate` and `submitblock` |
| `icsicoin/consensus/validation.py` | Validates PoW — `bits_to_target()`, `calculate_next_bits()` |
| `icsicoin/core/primitives.py` | Block/Header data structures — `serialize()`, `deserialize()` |
