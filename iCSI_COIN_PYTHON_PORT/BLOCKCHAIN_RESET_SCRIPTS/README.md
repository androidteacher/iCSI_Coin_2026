# Blockchain Reset Scripts

This directory contains utility scripts to reset the blockchain state for development and testing.

## Scripts

### 1. `clear_end_user_node.sh`
**Use this to reset ONLY your local node.**
- **Scope:** Deletes the `end_user_node`'s local blockchain data (`wallet_data/`).
- **Effect:** Your node will restart with a fresh wallet and re-sync from the seed nodes.
- **Usage:**
  ```bash
  cd BLOCKCHAIN_RESET_SCRIPTS
  ./clear_end_user_node.sh
  ```

### 2. `clear_stack.sh`
**Use this to reset the ENTIRE network (Seed Nodes + End User Node).**
- **Scope:** Deletes ALL blockchain data for seed nodes (`data_seed*`) AND the end user node.
- **Effect:** The entire blockchain is wiped. A new Genesis Block will be generated. All nodes will start from height 0.
- **Usage:**
  ```bash
  cd BLOCKCHAIN_RESET_SCRIPTS
  ./clear_stack.sh
  ```

## Important Notes
- **WARNING:** These scripts **PERMANENTLY DELETE** wallet data. Back up any important wallets before running.
- You may be prompted for your `sudo` password to delete protected Docker volumes.
- Ensure you have `docker` and `docker compose` installed.
