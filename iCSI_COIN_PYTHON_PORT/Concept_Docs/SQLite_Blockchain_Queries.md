# SQLite Blockchain Queries

This document contains a collection of useful SQLite queries for inspecting the `iCSI Coin` blockchain state directly from the database files.
These commands are intended to be run from the project root directory, assuming the standard node data l`ocation: `end_user_node/wallet_data/`.

## Database Files

*   **`block_index.sqlite`**: Stores metadata about every block seen (height, hash, previous hash, file size).
*   **`chainstate.sqlite`**: Stores the current Unspent Transaction Output (UTXO) set. This represents the current "state" of user balances.

---

## 1. Economic Statistics

### Calculate Total Coin Supply
Sums up the value of all unspent outputs in the database.
*Note: The value is stored in 'satoshis' (integers). We divide by 100,000,000 to get the coin amount.*

```bash
sqlite3 end_user_node/wallet_data/chainstate.sqlite "SELECT SUM(amount) / 100000000.0 FROM utxo;"
```

### "Rich List" - Top Addresses by Balance
This is an approximation. We group by the `script_pubkey` to see which script owns the most UTXOs.
These are the top 10 holders on your node's view of the network.

```bash
sqlite3 end_user_node/wallet_data/chainstate.sqlite "SELECT HEX(script_pubkey), COUNT(*) as utxo_count, SUM(amount)/100000000.0 as balance FROM utxo GROUP BY script_pubkey ORDER BY balance DESC LIMIT 10;"
```

---

## 2. Blockchain Statistics

### Total Transactions Indexed
Count of all transactions currently indexed by your node.

```bash
sqlite3 end_user_node/wallet_data/block_index.sqlite "SELECT COUNT(*) FROM tx_index;"
```

### Total Blockchain Data Size
The sum of the size (in bytes) of all blocks on disk.

```bash
sqlite3 end_user_node/wallet_data/block_index.sqlite "SELECT SUM(length) FROM block_index;"
```

### Average Block Size
The average size (in bytes) of a block.

```bash
sqlite3 end_user_node/wallet_data/block_index.sqlite "SELECT AVG(length) FROM block_index;"
```

---

## 3. Node Health & Debugging

### Check Current Sync Height
Returns the highest block number currently indexed by your node.

```bash
sqlite3 end_user_node/wallet_data/block_index.sqlite "SELECT MAX(height) FROM block_index;"
```

### Check for Forks / Multiple Tips
If your node sees multiple blocks at the same height (a fork), this query will show them.

```bash
sqlite3 end_user_node/wallet_data/block_index.sqlite "SELECT height, COUNT(*) as count FROM block_index GROUP BY height HAVING count > 1 ORDER BY height DESC LIMIT 10;"
```

### List Orphan Blocks
Orphan blocks are valid blocks whose parent is unknown or missing.

```bash
sqlite3 end_user_node/wallet_data/block_index.sqlite "SELECT * FROM block_index WHERE prev_hash NOT IN (SELECT block_hash FROM block_index) AND height > 0;"
```

### Inspect Specific Block by Height
Get the hash and file location of a specific block (e.g., Block 5000).

```bash
sqlite3 end_user_node/wallet_data/block_index.sqlite "SELECT * FROM block_index WHERE height = 5000;"
```
