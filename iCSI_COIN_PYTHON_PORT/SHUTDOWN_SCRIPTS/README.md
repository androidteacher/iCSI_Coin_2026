# Shutdown Scripts

This directory contains utility scripts to safely stop the iCSI Coin network components.

## Scripts

### 1. `shutdown_full_stack.sh`
**Use this to stop the ENTIRE network (Seed Nodes + End User Node).**
- **Scope:** Stops all docker containers for seed nodes (`docker-compose-seeds.yml`) AND the end user node.
- **Effect:** All blockchain services will stop. Data and images are preserved.
- **Usage:**
  ```bash
  cd SHUTDOWN_SCRIPTS
  ./shutdown_full_stack.sh
  ```

### 2. `shutdown_user_node.sh`
**Use this to stop ONLY your local node.**
- **Scope:** Stops the `end_user_node`'s docker containers.
- **Effect:** Your local node will stop. Seed nodes (if running on this machine) are unaffected.
- **Usage:**
  ```bash
  cd SHUTDOWN_SCRIPTS
  ./shutdown_user_node.sh
  ```

## Important Notes
- You may be prompted for your `sudo` password to stop Docker containers.
- Ensure you have `docker` and `docker compose` installed.
