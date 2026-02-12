# Concept: Difficulty, Bits, and Binary

## 1. What are we hashing?
Mining isn't just hashing "some data." The miner constructs a very specific 80-byte structure called the **Block Header**.

This header contains:
1.  **Version** (4 bytes)
2.  **Previous Block Hash** (32 bytes)
3.  **Merkle Root** (32 bytes - Summary of all transactions)
4.  **Timestamp** (4 bytes)
5.  **Bits** (4 bytes - The Difficulty Target)
6.  **Nonce** (4 bytes - The variable we change)

### The Process
The miner takes this 80-byte structure and pushes it through the hashing algorithm (in iCSI Coin's case, Scrypt).

`Scrypt( Header + Nonce ) -> 256-bit Output`

## 2. The Output: Hex vs Binary
The output is a 256-bit number, usually represented as a hexadecimal string. To understand "Difficulty," we have to look at the **Binary** representation of that hex string.

**The Rule**: The hash must be numerically *smaller* than the Target. This creates the "Leading Zero" requirement.

### Attempt 1: The Fail
Let's say our Target requires at least **one leading zero** (in binary).

We try `Nonce: 100`.
Hash Output: `cde123...`

Let's look at that first Hex digit: **`C`**
In Binary, Hex `C` is `1100`.

*   **First Bit**: `1`
*   **Result**: The hash starts with a `1`. It is too large.
*   **Outcome**: **REJECTED.**

### Attempt 2: The Success
The miner increments the Nonce to `101` and hashes again.
Hash Output: `6ca1...`

Let's look at that first Hex digit: **`6`**
In Binary, Hex `6` is `0110`.

*   **First Bit**: `0`
*   **Result**: The hash starts with a `0`. It is small enough!
*   **Outcome**: **ACCEPTED!** (50 Coins Baby!)

## 3. Why "Adding a Zero" is Exponential
In the example above, we only needed 1 leading bit to be zero (a 50% chance).

However, usually, we need many leading zeros in Hex (e.g., `0000abc...`).
Each `0` in Hex represents **four** zeros in binary (`0000`).

*   One Hex `0` = 1/16 chance.
*   Two Hex `00` = 1/256 chance.
*   Three Hex `000` = 1/4096 chance.

This is why increasing the difficulty by requiring just one more hex zero makes the mining process 16 times harder.
