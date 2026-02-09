# Chain Merging and Reorganization: Preserving Consensus

## Introduction
In a distributed blockchain network, multiple nodes may mine blocks simultaneously. Due to network latency, one part of the network might receive Block A first, while another part receives Block B. Both blocks are valid, but they build on the same parent, creating a **Fork**.

If nodes cannot agree on which chain is the "true" history, the network splits, and the currency becomes unusable (a "partition"). **Chain Reorganization ("Reorg")** is the mechanism nodes use to resolve these conflicts and converge on a single, shared truth.

## The Problem: Forks and Orphans

### 1. The Fork
Imagine the chain is at Height 100.
- **Node A** mines a block at Height 101 (Hash `0xAAA...`).
- **Node B** mines a different block at Height 101 (Hash `0xBBB...`).

Both blocks are valid. Neighbors of Node A add `0xAAA` to their chain. Neighbors of Node B add `0xBBB`. The network is now split.

### 2. The Resolution (Longest Chain Rule)
To resolve this, blockchains follow the **Longest Chain Rule** (or more accurately, **Most Cumulative Work**).
- If a new block comes in on top of `0xBBB` (making it Height 102), that chain is now longer.
- Nodes that were following `0xAAA` (Height 101) must switch to the `0xBBB` -> `0xCCC` chain (Height 102).

This switching process is called **Chain Reorganization**.

---

## How It Works: The Logic

We have implemented a robust reorg mechanism in the `ChainManager`. Here is the step-by-step logic your node follows when it discovers a longer chain.

### Step 1: Fork Detection
When a new block arrives, we check its parent.
- If the parent is our current "Best Block" (Tip), we just extend the chain.
- If the parent is **not** our current tip, but we know the parent exists, we have found a **Fork**.
- We compare the height of this new fork against our current chain.
    - If `New Chain Height > Current Chain Height`, we trigger a **Reorg**.

### Step 2: Finding the Common Ancestor
We trace backwards from the new block and backwards from our current tip until we find the block where they diverge.
- **Example**:
    - Current Chain: Genesis -> Block A -> Block B (Tip)
    - New Chain: Genesis -> Block A -> Block C -> Block D (New Tip)
    - **Common Ancestor**: Block A.

### Step 3: Rolling Back (Disconnecting)
To switch tracks, we must "undo" the blocks that are no longer part of the main chain.
- We **Disconnect** Block B.
- **Critical Challenge**: When Block B was connected, it spent some UTXOs (Unspent Transaction Outputs) and created new ones.
- **The Fix**:
    1.  **Remove Outputs**: Delete the UTXOs created by Block B.
    2.  **Restore Inputs**: Look up the original UTXOs that Block B spent and put them back into the database. *This requires a Transaction Index (`tx_index`) to find where those old coins came from.*

### Step 4: Rolling Forward (Connecting)
Now that we are back at the Common Ancestor (Block A), we can safely add the new blocks.
- **Connect** Block C. (Verify transactions, spend inputs, create outputs).
- **Connect** Block D.

The node is now in sync with the longest chain.

---

## Why This Is Essential

Without this logic, a node that acts quickly (mines a block) but has slow internet (broadcasts it late) would permanently diverge from the rest of the network. It would be stuck on its own "island" blockchain, rejecting the valid blocks from the rest of the world because they don't match its local history.

**Key Takeaways for Cyber Students:**
1.  **Consensus is Dynamic**: The "truth" can change. A transaction with 1 confirmation is not final; it could be reorged out. This is why exchanges wait for 6+ confirmations.
2.  **State Management**: Rolling back a blockchain is effectively time travel. You must be able to perfectly reconstruct the state of the ledger (UTXO set) as it was in the past.
3.  **Attack Vector**: A "51% Attack" exploits this mechanism. An attacker secretly mines a longer chain and then releases it, forcing the entire network to reorg and potentially erasing (double-spending) confirmed transactions.
