# How to Create Your Own Coin (It's Easy!)

This guide explains how to take the existing **iCSI Coin** codebase and turn it into your own independent cryptocurrency.

## The Concept: Network Isolation

The most critical part of creating a new coin is ensuring your nodes **only talk to each other** and not to the original network. 

When two nodes connect, the very first thing they send is a **Version Message**. But before that message can even be read, every packet starts with a 4-byte **Magic Value**.

### What happens if the Magic Value is wrong?
If a node receives a message with a Magic Value that doesn't match its own:
1.  It attempts to read the header.
2.  It sees "garbage" (because the first 4 bytes are wrong).
3.  It **immediately disconnects**.

This simple mechanism is rigorous enough to completely isolate your new blockchain from the old one.

---

## Step-by-Step Directions

### 1. Fork the Repository
Create your own copy of the code and initialize it as a new project.

```bash
# 1. Clone the existing repository
git clone https://github.com/YourUsername/iCSI_Coin_2026.git

# 2. Rename the folder
mv iCSI_Coin_2026 MyNewCoin

# 3. Enter the folder
cd MyNewCoin

# 4. Remove the old git history (start fresh)
rm -rf .git

# 5. Initialize your new repository
git init
git add .
git commit -m "Initial commit of MyNewCoin"
```

### 2. Rename the Coin (Optional but Recommended)
To rebrand the UI, logs, and internal references from `iCSICoin` to your new name, use a simple find-and-replace command.

**Using `sed` (Linux/Mac):**
```bash
# Replace 'iCSICoin' with 'MyNewCoin' in all files
grep -rli 'iCSICoin' . | xargs sed -i 's/iCSICoin/MyNewCoin/g'
```

### 3. Change the Magic Value (The "Hard Fork")
This is the single line of code that creates your new universe.

1.  **File**: `iCSI_COIN_PYTHON_PORT/end_user_node/icsicoin/network/messages.py`
2.  **Line**: ~9
3.  **Code**:
    ```python
    MAGIC_VALUE = 0xB10C2026  # <--- CHANGE THIS VALUE
    ```
4.  **Action**: Change it to any unique 4-byte hex value (e.g., `0xdeadbeef`).

> **Note:** iCSI Coin ships with its *own* magic value (`0xB10C2026`), not Litecoin's. That means this codebase is already isolated from the real Litecoin network. You only need to change the value to isolate your coin from **other iCSI Coin forks** (or from an earlier chain of your own).

**That's it!** You have now created a new network.

### 4. Change the Genesis Block (Optional)
While the Magic Value isolates the network, your blockchain will still look for the original "Genesis Block" (Block 0) unless you change it.

1.  **File**: `iCSI_COIN_PYTHON_PORT/end_user_node/icsicoin/core/chain.py`
2.  **Line**: ~22
3.  **Code Block**:
    ```python
    def _create_genesis_block(self):
        """Creates the hardcoded Genesis Block object"""
        # ... imports ...
        
        # Create Genesis with standard params
        tx = Transaction(
             # CHANGE THE TEXT BELOW MESSAGE to something unique!
             vin=[TxIn(b'\x00'*32, 0xffffffff, b'My New Coin Genesis Message: Hello World!', 0xffffffff)],
             vout=[TxOut(5000000000, b'\x00'*25)] 
        )
        
        # ... hash calculation ...
        
        header = BlockHeader(
             # ...
             timestamp=1231006505, # Change timestamp to NOW
             bits=0x1f099996, 
             nonce=2083236893      # You will need to mine a valid nonce for this hash!
        )
        return Block(header, [tx])
    ```

**Note**: If you change the Genesis Block parameters, the **Genesis Hash** will change. Every node creates this genesis block from the hardcoded values and inserts it directly, so each node must use the **exact same** `_create_genesis_block()` code — any difference means your nodes build different chains and never agree.

> **Proof of Work & the genesis block:** The genesis block is written directly into the database and is **not** PoW-validated, so you do **not** need to mine a valid nonce for genesis specifically. However, every block *after* genesis now has its Proof of Work enforced (scrypt hash must meet the `bits` target), so your miners must actually do the work to extend the chain. Keeping the matching nonce for genesis is still good practice if you want a "clean" genesis hash.

[Click Here for A script that will hash your new genesis block](../iCSI_COIN_PYTHON_PORT/Concept_Docs/Hash_Your_New_Genesis_Block.md)

### 5. Change the Difficulty Settings (Optional)
Want faster blocks? Want difficulty to adjust less often?

1.  **File**: `iCSI_COIN_PYTHON_PORT/end_user_node/icsicoin/consensus/validation.py`
2.  **Line**: ~58
3.  **Code**:
    ```python
    DIFFICULTY_ADJUSTMENT_INTERVAL = 20000     # Retarget every 20,000 blocks
    TARGET_BLOCK_TIME_SECONDS = 60             # Target: 60 seconds per block
    ```
4.  **Action**:
    *   Change `DIFFICULTY_ADJUSTMENT_INTERVAL` to a larger/smaller number to change how often the network difficulty updates.
    *   Change `TARGET_BLOCK_TIME_SECONDS` to change how fast you want blocks to be mined on average.

### 6. Change the Economics: Halving & Coinbase Maturity (Optional)
These control the money supply and when mined coins become spendable. They live just below the difficulty settings:

1.  **File**: `iCSI_COIN_PYTHON_PORT/end_user_node/icsicoin/consensus/validation.py`
2.  **Line**: ~69
3.  **Code**:
    ```python
    COIN = 100_000_000                                                   # base units per 1 coin
    INITIAL_BLOCK_SUBSIDY = 50 * COIN                                    # 50 coins at height 0
    HALVING_INTERVAL = int(os.getenv("ICSI_HALVING_INTERVAL", "20000"))  # blocks between halvings
    COINBASE_MATURITY = int(os.getenv("ICSI_COINBASE_MATURITY", "20"))   # blocks before mined coins are spendable
    ```

You can tune these **without editing code** by setting environment variables (great for a classroom demo), for example in `iCSI_COIN_PYTHON_PORT/docker-compose-seeds.yml` under a service's `environment:` key:

```yaml
    environment:
      - ICSI_HALVING_INTERVAL=20000    # how many blocks between each "halving" of the reward
      - ICSI_COINBASE_MATURITY=20      # how many blocks before a freshly-mined coin can be spent
```

**Why these matter for a lesson:**
*   **Halving** is the programmatic scarcity mechanism — every `HALVING_INTERVAL` blocks the block reward is cut in half (50 → 25 → 12.5 …). This is a **block count**, not a time: how long a halving takes = `HALVING_INTERVAL` × how fast blocks are actually mined. With CPU miners at the easy starting difficulty, blocks come very fast (well under a second each), so the interval must be large to make a halving last hours. The default of `20000` works out to roughly ~6 hours with a handful of CPU miners — much better than the Bitcoin-scale `210000` (~73 days at a 30s target), while still letting students watch halvings happen. Raise it if halvings still feel too quick on your hardware.
*   **Coinbase maturity** is why you can't instantly spend a coin you just mined. The default of `20` (~10 minutes) lets students spend within a class while still teaching the concept; Bitcoin uses `100`.

> **Keep every node identical.** `HALVING_INTERVAL`, `COINBASE_MATURITY`, the difficulty settings, the genesis block, and the magic value are all **consensus rules**. If two nodes disagree on any of them, they will reject each other's blocks and split into separate chains. Make sure every node in your network uses the same values.

---
**Reference**: See the [`Concept_Docs`](../iCSI_COIN_PYTHON_PORT/Concept_Docs) folder for deeper explanations — including [`Modify_Blockchain_Difficulty.md`](../iCSI_COIN_PYTHON_PORT/Concept_Docs/Modify_Blockchain_Difficulty.md), [`Blockchain_Spending_and_Maturity.md`](../iCSI_COIN_PYTHON_PORT/Concept_Docs/Blockchain_Spending_and_Maturity.md), and [`Hash_Your_New_Genesis_Block.md`](../iCSI_COIN_PYTHON_PORT/Concept_Docs/Hash_Your_New_Genesis_Block.md).
