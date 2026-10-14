# Create a New Chain

This folder contains **`create_new_chain.sh`** — a one-time "fork" tool that turns
this copy of iCSI Coin into a **brand-new, independent blockchain** that starts
from **block 0**.

> ## ⚠️ This script DELETES the `.git` folder
> It removes this project's git history so you can re-initialize it as a fresh
> repository. **A complete backup `.tar` of the whole project is written next to
> the project folder *before* anything is changed or deleted.** Proceed with care.

---

## Why would an instructor create a new chain?

A blockchain is only "new" when its nodes refuse to talk to the old nodes and
start counting from block 0 again. You'd want a fresh chain when:

- **Starting a new class or semester** and you want a clean ledger, unconnected
  to anything a previous group mined.
- **An old chain got "polluted"** — e.g. students left nodes running, someone's
  wallet dominates the balances, or the difficulty/economics drifted somewhere
  you don't want — and you'd rather start over than untangle it.
- **You want different economics** (block speed, how often difficulty adjusts,
  how often the reward halves) for a particular lesson.
- **You need isolation from other iCSI chains.** Two chains using the same
  network "magic bytes" can accidentally find and sync with each other. A new
  random magic value guarantees your chain is its own universe — old-magic nodes
  simply can't connect.

## What the script does (in order)

1. **Warns you** clearly about what's about to happen.
2. **Shows the current settings** and asks you for the new ones:
   - how often blocks should be mined (**target block time**),
   - how many blocks between **difficulty adjustments**,
   - how many blocks between **reward halvings**,
   - the **genesis block secret message** (press Enter to keep the current one).
   (Press Enter at any number prompt to keep the current value.)
3. **Asks you to confirm** with `YES` / `NO`. Typing anything other than `YES`
   aborts with no changes.
4. **Backs up the entire project** to `../iCSI_Coin_2026_Backup.tar` (next to the
   project folder) — this happens *before* any change or deletion.
5. **Changes the network magic bytes** to a new **random** value and tells you
   what it is.
6. **Applies your settings** to the source code:
   - `TARGET_BLOCK_TIME_SECONDS` and `DIFFICULTY_ADJUSTMENT_INTERVAL` in
     `icsicoin/consensus/validation.py`
   - the default `ICSI_HALVING_INTERVAL` in the same file
   - the genesis coinbase message in `icsicoin/core/chain.py`
   - `MAGIC_VALUE` in `icsicoin/network/messages.py`
7. **Deletes the `.git` folder.**
8. **Prints next steps** for `git init`, pushing to a new repo, resetting node
   data, and starting the new chain.

## How to run it

```bash
cd iCSI_COIN_PYTHON_PORT/CREATE_NEW_CHAIN_SCRIPT
./create_new_chain.sh
```

(If you get "Permission denied", run `chmod +x create_new_chain.sh` first.)

## After it finishes

The script prints the exact commands, but in short:

1. `git init`, `git add .`, `git commit` — make it a new repository.
2. (Optional) add a remote and `git push` to a new GitHub repo your students clone.
3. Run a **reset script** (`BLOCKCHAIN_RESET_SCRIPTS/clear_stack.sh`) so every node
   discards old data and builds the **new genesis block**.
4. Start mining with the **STARTUP_SCRIPTS**.

## Good to know

- **The genesis block does not need to be "mined."** It is written into the
  database directly and is *not* Proof-of-Work-validated, so changing the genesis
  message is safe — you do **not** need to find a special nonce. (Every block
  *after* genesis is fully PoW-checked.)
- **All of these settings are consensus rules.** Every node — including every
  student's clone — must run the *exact same* values, or nodes will reject each
  other's blocks and the network will split. That's why you set them here **once**
  and share the resulting repository.
- **Halving is counted in blocks, not time.** How long a halving takes =
  `halving interval` × how fast blocks are actually mined. With CPU miners at an
  easy difficulty, blocks are found in well under a second, so a large interval
  (e.g. 20,000) is needed to make a halving last hours.
- **Keep the backup.** `iCSI_Coin_2026_Backup.tar` is your safety net. To restore,
  extract it next to (or over) the project folder.
