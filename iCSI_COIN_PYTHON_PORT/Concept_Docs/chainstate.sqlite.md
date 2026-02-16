# Concept: The Chainstate Database (chainstate.sqlite)

## 0. High Level Summary (The "Why")
**Purpose:** To provide instant balance information without scanning the entire history of the blockchain.
**How it works:** Think of this database as a ledger of "Active Coins".
*   When a coin is mined or received, it is **added** to this list.
*   When a coin is spent, it is **subtracted** (deleted) from the sender's list and **added** (as a new coin) to the receiver's list.

By keeping this list, the node can instantly answer "How much money does X wallet have?" by simply summing up your active coins in this database, rather than re-reading thousands of old blocks.

## 1. Overview
The **Chainstate Database** (`chainstate.sqlite`) is the "brain" of the iCSI Coin node. While the blockchain (blocks 0 to 10,000+) is the *history* of every transaction that ever happened, the **Chainstate** is a snapshot of *right now*.

It tracks only one thing: **UTXOs (Unspent Transaction Outputs)**.
If a coin is in this database, it is "alive" and spendable. If it is not in this database, it either never existed or has already been spent.


## 2. Step-by-Step Lifecycle

### Scenario A: A Miner Mines a Coin (Creation)
When a miner finds a block, they include a special **Coinbase Transaction** (e.g., `txid: a1b2...`) that pays them the block reward (e.g., 50 Coins).

1.  **Block Validation**: The node accepts the new block.
2.  **Database Update**: The node invokes `ChainStateDB.add_utxo()`.
3.  **Result**: A new row is inserted.
    *   `txid`: `a1b2...`
    *   `vout_index`: `0`
    *   `amount`: `5000000000`
    *   `script_pubkey`: `[Miner's Public Key Hash]`
    *   `is_coinbase`: `1` (True)

*The miner now has a balance because this row exists.*

### Scenario B: The Miner Spends the Coin (Destruction & Creation)
The miner wants to send 20 Coins to **Alice**.
New Transaction (`txid: c3d4...`):
*   **Input**: Refers to `a1b2...` index `0` (The mined coin).
*   **Output 0**: 20 Coins to Alice.
*   **Output 1**: 30 Coins back to Miner (Change).

When this block is processed, the database performs an **Atomic Swap**:

1.  **Remove Input (The Spend)**:
    The node looks at the input (`a1b2...:0`) and runs:
    ```sql
    DELETE FROM utxo WHERE txid='a1b2...' AND vout_index=0;
    ```
    *The 50 Coin UTXO is gone forever. It is now "spent history" and only exists in the raw block files, not the chainstate.*

2.  **Add Outputs (The Receive)**:
    The node creates new rows for the new owners:
    *   **Row 1 (Alice)**: `txid: c3d4...`, `index: 0`, `amount: 20`, `owner: Alice`.
    *   **Row 2 (Miner)**: `txid: c3d4...`, `index: 1`, `amount: 30`, `owner: Miner`.

## 4. Why This Makes Balances Fast
Without this database, to calculate Alice's balance, we would have to scan 100,000 blocks, summing up every reception and subtracting every spend. This is O(History) complexity—extremely slow.

With `chainstate.sqlite`, we only check the list of currently valid coins. The complexity is O(UTXOs), which is millions of times faster.

### The Query (Manual/Explorer)
When you type an address into the blockchain explorer, it ignores the history and asks: *"What coins does this person hold RIGHT NOW?"*

It runs a query similar to this:

```sql
SELECT SUM(amount) 
FROM utxo 
WHERE script_pubkey = X'[YOUR_ADDRESS_BYTES_IN_HEX]';
```

If the result is `Null` or `0`, the balance is zero. If rows exist, it sums them up instantly to give you the `Confirmed Balance`.
