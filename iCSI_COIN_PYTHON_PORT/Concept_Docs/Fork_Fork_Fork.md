# Understanding Blockchain Forks

This document explains why you might see multiple blocks at the same height when querying the database, and what it means for the health of the iCSI Coin blockchain.

## The Query

The "Check for Forks" query checks the `block_index` table for any block heights that have more than one entry.

```sql
sqlite3 end_user_node/wallet_data/block_index.sqlite "SELECT height, COUNT(*) as count FROM block_index GROUP BY height HAVING count > 1 ORDER BY height DESC LIMIT 10;"
```

## The Data

You observed the following output:

```json
[
  { "height": 5492, "count": 2 },
  { "height": 5491, "count": 2 },
  { "height": 5490, "count": 2 },
  { "height": 5458, "count": 2 },
  { "height": 5440, "count": 2 },
  ...
]
```

## Explanation

### 1. What does this mean?
Seeing `count: 2` at a specific height means **two different miners found a valid block at the exact same height**, and your node received *both* of them.

This indicates a **Fork**.

### 2. Why does it happen?
In a Proof-of-Work system, miners are racing to solve a cryptographic puzzle. Occasionally, two miners solve the puzzle at roughly the same time.
*   **Miner A** finds a block at height 5490 and broadcasts it.
*   **Miner B** finds a different block at height 5490 and broadcasts it.
*   Your node hears about **Block A** first and adds it to the index.
*   Microseconds or seconds later, your node hears about **Block B**. It checks the proof-of-work, sees it is valid, and adds it to the index as well.

Now your node has *two* candidates for height 5490. This is a **Fork**.

### 3. How is it resolved? (The Longest Chain Rule)
The blockchain cannot split forever; everyone needs to agree on a single history. This is resolved by the **Longest Chain Rule** (or Cumulative Difficulty).

1.  The network is briefly split. Some nodes build on top of Block A, others on Block B.
2.  Eventually, a miner finds a new block at **Height 5491**.
3.  If they built on top of **Block A**, then the "A-Chain" is now longer (cumulative work is higher).
4.  The entire network switches to the "A-Chain".
5.  **Block B** becomes an **Orphan** (or Stale Block). It remains in your database (`block_index`), but it is not part of the active chain (`chainstate`).


**This is normal behavior.**

A decentralized blockchain *must* handle these conflicts. The fact that your node records both means it is correctly listening to the network. The fact that the chain continues (you are seeing higher heights) means the consensus rules are working: one chain effectively "won," and the other blocks were discarded (orphaned), but their history remains in your `block_index` table.
