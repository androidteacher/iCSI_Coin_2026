# Chain Merging and Reorganization: Preserving Consensus

## Introduction
In a distributed blockchain network, multiple nodes may mine blocks simultaneously. Due to network latency, one part of the network might receive Block A first, while another part receives Block B. Both blocks are valid, but they build on the same parent, creating a **Fork**.

If nodes did not have a mechanism to determine which chain is the "true" history, the network would split into two or more chains, and the currency would become unusable (a "partition"). **Chain Reorganization ("Reorg")** is the mechanism nodes use to resolve these conflicts and converge on a single, shared truth.

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


## Why This Is Essential

Without this logic, a node that acts quickly (mines a block) but has slow internet (broadcasts it late) would permanently diverge from the rest of the network. It would be stuck on its own "island" blockchain, rejecting the valid blocks from the rest of the world because they don't match its local history.

