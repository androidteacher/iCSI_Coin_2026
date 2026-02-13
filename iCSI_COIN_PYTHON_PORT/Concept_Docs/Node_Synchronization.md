# Node Synchronization and Consensus Mechanism

This document outlines the step-by-step process a node uses to stay synchronized with the network, ensuring it has the longest valid chain. It also compares the implementation in `iCSI Coin` with the standard Bitcoin protocol.

## 1. How the Node Assesses its State

The node constantly evaluates if it is up-to-date through a **Sync Watchdog** and peer metadata tracking.

### Step-by-Step Assessment Process
1.  **Peer Handshake & Metadata Exchange**:
    *   When connecting to a peer, the node exchanges `VERSION` messages.
    *   This message contains the peer's current **Block Height**.
    *   The node stores this height in its `peer_stats` table.

2.  **The Sync Watchdog (Active Polling)**:
    *   A background task (`sync_worker`) runs every 10 seconds.
    *   It compares the **current local tip height** against the **maximum height reported by any connected peer**.
    *   If `Max Peer Height > Local Height`, the node determines it is behind and initiates a sync.
    *   *Stall Detection*: If the node hasn't received a new block in >20 seconds, the Watchdog triggers a preemptive synchronization request to the "Best Peer" (highest height) to kickstart the process.

## 2. Querying Neighbors (The "GetBlocks" Protocol)

Yes, the node actively asks questions of its neighbors to request missing data. This is done via the `getblocks` message.

### Interaction Flow
1.  **Initiation**:
    *   The node constructs a **Block Locator**. This is a list of block hashes from its own chain, starting dense at the tip (last 10 blocks) and becoming exponential (back to Genesis).
    *   It sends this locator in a `getblocks` message to a peer.

2.  **Peer Response**:
    *   The peer receives the locator and searches for a **Common Ancestor** (the last block both nodes share).
    *   Once found, the peer calculates which blocks the requesting node is missing (starting from `Ancestor + 1`).
    *   The peer sends an `INV` (Inventory) message containing the hashes of up to 500 subsequent blocks.

3.  **Data Retrieval**:
    *   The requesting node receives the `INV`.
    *   It filters out blocks it already has.
    *   For new blocks, it sends a `getdata` message to request the full block content.
    *   The peer responds with `BLOCK` messages containing the raw data.

## 3. Advertising & Broadcasting (Push Mechanism)

Yes, neighbors are responsible for advertising new blocks they find or validate. This ensures low-latency propagation.

### The Broadcast Mechanism
1.  **Block Acceptance**:
    *   When a node successfully validates and adds a new block to its chain (whether mined or received), it immediately triggers a relay.

2.  **Inventory Announcement (`INV`)**:
    *   The node creates an `INV` message containing the new block's hash.
    *   It sends this `INV` to **ALL** connected peers (flooding).

3.  **Recursion**:
    *   Peers receiving this `INV` will check if they have the block. If not, they request it via `getdata`.
    *   Once they validate it, they too will broadcast an `INV` to *their* peers, creating a network-wide propagation wave.

## 4. Comparison: iCSI Coin vs. Bitcoin

| Feature | iCSI Coin Implementation | Bitcoin Protocol (Reference) |
| :--- | :--- | :--- |
| **Initial Discovery** | Uses `VERSION` message to swap heights handshake. | Uses `VERSION` message to swap heights. |
| **Sync Trigger** | **Sync Watchdog**: Time-based polling (10s) + check for silence (>20s). Aggressively polls if behind. | **Passive/State-Based**: "Initial Block Download" (IBD) state. Only polls when tip is stale or peer announces new data. Less "chatty" than polling. |
| **Locator Construction** | **Dense-then-Exponential**: Standard implementation (Tip, -1, -2... -10, -20...). | **Dense-then-Exponential**: Effectively identical logic (prevents sending 1M hashes). |
| **Block Requests** | **Standard `getblocks` -> `INV` -> `getdata`**. | **Headers-First Sync**: Bitcoin requests *Headers* only (`getheaders`) first, validates the chain structure/PoW, *then* downloads blocks in parallel. This prevents DoS attacks with large invalid blocks. |
| **Propagation** | **Legacy `INV` Flood**: Announces block Hash to all. | **Compact Blocks (BIP 152)**: Tries to send minimal data (short IDs) assuming peers have the transactions in mempool. Falls back to INV/Block. |

## 5. Summary & Recommendations

**Current Status**:
The application faithfully mirrors the **classic** Bitcoin synchronization mechanism (pre-0.10). It uses the standard `getblocks` -> `INV` loop and correctly identifies the longest chain via peer metadata.

**Differences**:
The primary difference is the **Sync Watchdog**. Bitcoin relies more on "I am in IBD mode" states, whereas iCSI Coin uses a proactive timer (`time_since_last_block > 20s`) to ensure it never "sleeps" if it falls behind. This is robust but slightly more bandwidth-intensive.

**To Ensure Nodes Stay Up To Date (Recommendations)**:
1.  **Keep the Watchdog**: The current logic is effective for this scale. Ensure the `20s` silence threshold isn't too aggressive for slow connections.
2.  **Headers-First (Future)**: If blocks become large, implementing `getheaders` would allow nodes to prove the "longest chain" faster without downloading the full data first.
3.  **Connectivity**: Maximize peer count. The more peers a node has, the higher the probability one of them is at the true network tip.
