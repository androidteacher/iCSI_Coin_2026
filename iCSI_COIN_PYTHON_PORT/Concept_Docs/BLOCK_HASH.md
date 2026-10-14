# Understanding the Block Hash

## What is the Block Hash?

The **Block Hash** you see in the explorer (e.g., `9dfc7a1e9c2057bf2a8de8cc70964a4469aca94be0a759efc89a2ce1da1edfa5`) is the unique digital fingerprint — the **identity** — of a block. It is the **double-SHA256** of the block's 80-byte header.

> **Important:** in iCSI Coin this *identity* hash is **not** the value the mining puzzle checks. The Proof-of-Work puzzle hashes the same header with a **different algorithm — scrypt** — and that scrypt result is what must beat the target. So the Block Hash shown in the explorer can start with any digit; its leading zeros tell you nothing about difficulty. (iCSI Coin uses scrypt for Proof of Work, like Litecoin; Bitcoin uses double-SHA256 for both.)

## How is it produced?

The miner constructs a candidate block by gathering pending transactions and creating a **Block Header**.
- A Block Header is a valid data structure that can be hashed repeatedly.

The node computes **two different hashes** from that header:

```
Identity (the "Block Hash" in the explorer):   SHA256(SHA256(Block Header))
Proof-of-Work hash (what the puzzle checks):    scrypt(Block Header, N=1024, r=1, p=1)
```

The miner requests "work" (via `getwork` / `getblocktemplate`), then repeatedly changes the **Nonce** in the header and recomputes the **scrypt** hash until that scrypt hash is below the target.

##  How many leading zeros are required?

The rule of mining is simple: **The scrypt Proof-of-Work hash must be numerically smaller than the Target.**
- If the **Target** is `0000ffff...`, (The first 4 bits must be zeros) then a hash starting with `00006788...` is valid.
- If the **Target** is `00000000...`, (Seven zeros) then a hash starting with `00006788...` is **invalid**.

The easiest way to visualize this is by looking at the **leading zeros** of the hash.
*   **Hard Difficulty**: The hash must start with many zeros (e.g., `00000000...`).
*   **Easy Difficulty**: The hash can start with fewer zeros.

### Example: reading leading zeros (on the Proof-of-Work hash)

Remember to judge difficulty from the **scrypt Proof-of-Work hash**, not the explorer's Block Hash. Suppose a block's winning scrypt hash started with `6788...`:

1.  **Convert the first Hex character to Binary:**
    *   The character is **`6`**.
    *   In Binary, `6` is **`0110`**.

2.  **Count the Leading Zeros:**
    *   `0110` has **1 leading zero**.

3.  **Conclusion:**
    That hash cleared a target that needed only about **1 leading zero** — an extremely low difficulty.

**This means the Mining Difficulty was extremely low.** Finding a hash that starts with a `0` bit is basically a coin flip (50% chance), so a miner finds one almost instantly. (The explorer's Block Hash, by contrast, is only an identifier — it is not required to have any leading zeros, which is why the examples above start with `9` and `6`.)

In contrast, Bitcoin's current difficulty requires a hash starting with roughly **19 zeros** in Hex, which is **76 zeros** in Binary. That is typically trillions of times harder to find.
