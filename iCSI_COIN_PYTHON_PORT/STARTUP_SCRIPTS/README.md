# Startup Scripts

This directory contains utility scripts to start the iCSI Coin network components.

## Scripts

### 1. `start_full_stack.sh`
**Use this to start the ENTIRE network (Seed Nodes + user Node).**
- **Scope:** Starts all docker containers for seed nodes and the end user node.
- **Effect:** Seeds, STUN server, and User Node/Explorer will start.
- **Usage:**
  ```bash
  cd STARTUP_SCRIPTS
  ./start_full_stack.sh
  ```

### 2. `start_user_node.sh`
**Use this to start ONLY your local node.**
- **Scope:** Starts the `end_user_node`'s docker containers.
- **Effect:** Your local node and explorer will start.
- **Usage:**
  ```bash
  cd STARTUP_SCRIPTS
  ./start_user_node.sh
  ```

## Important Notes
- These scripts will automatically **build** the docker images if changes are detected.
- You may be prompted for your `sudo` password to start Docker containers.
- Ensure you have `docker` and `docker compose` installed.
