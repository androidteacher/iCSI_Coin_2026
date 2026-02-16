# Understanding the Block Hash

## What is the Block Hash?

The **Block Hash** you see in the explorer (e.g., `9dfc7a1e9c2057bf2a8de8cc70964a4469aca94be0a759efc89a2ce1da1edfa5`) is the unique digital fingerprint of a block. It is the result of the "Proof of Work" puzzle that miners must solve to add a block to the blockchain.

## How is it produced?

The miner constructs a candidate block by gathering pending transactions and creating a **Block Header**. 
- A Block Header is a valid data structure that can be hashed repeatedly.

The miner runs the following formula repeatedly, changing the **Nonce** each time:

```
SHA256(SHA256(Block Header + Nonce)) = Candidate Block Hash
```

This process is what happens when a miner requests "work" (often called `getwork` or `getblocktemplate` in technical terms) and starts hashing a valid **block header**.

##  How many leading zeros are required?

The rule of mining is simple: **The resulting Hash must be numerically smaller than the Target.**
- If the **Target** is `0000ffff...`, (The first 4 bits must be zeros) then a hash starting with `00006788...` is valid.
- If the **Target** is `00000000...`, (Seven zeros) then a hash starting with `00006788...` is **invalid**.

The easiest way to visualize this is by looking at the **leading zeros** of the hash.
*   **Hard Difficulty**: The hash must start with many zeros (e.g., `00000000...`).
*   **Easy Difficulty**: The hash can start with fewer zeros.

### Your Example: A Hash Starting with `6`

If you see a Block Hash like `6788...`:

1.  **Convert the first Hex character to Binary:**
    *   The character is **`6`**.
    *   In Binary, `6` is **`0110`**.

2.  **Count the Leading Zeros:**
    *   `0110` has **1 leading zero**.

3.  **Conclusion:**
    This block required a hash with only **1 leading zero** (or potentially even 0, depending on the exact target, but `0110` satisfies a "starts with 0" requirement).

**This means the Mining Difficulty was extremely low.** To find a hash that starts with `0...` (in binary) is basically a coin flip (50% chance). A miner could find this almost instantly.

In contrast, Bitcoin's current difficulty requires a hash starting with roughly **19 zeros** in Hex, which is **76 zeros** in Binary. That is typically trillions of times harder to find.
