# Update and Restart Node

This directory contains utility scripts to update and restart the node.

## Scripts

### 1. `update_end_user_node.sh`
**Use this to pull the latest changes and restart your node.**
- **Scope:** Pulls git changes for the entire project and rebuilds/restarts the `end_user_node`.
- **Effect:** Your node will briefly go offline, update its code, and restart.
- **Usage:**
  ```bash
  cd UPDATE_AND_RESTART_NODE
  ./update_end_user_node.sh
  ```

## Important Notes
- **Good News:** This script --will not-- destroy any data. (Back up that wallet anyway!)
