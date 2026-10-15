# Update and Restart Node

This directory contains utility scripts to update and restart the node.

## Scripts

### 1. `update_end_user_node.sh`
**Use this to pull the latest changes and restart your node.**
- **Scope:** Pulls git changes for the entire project and rebuilds/restarts the `end_user_node`.
- **Effect:** Your node is stopped, its code is updated and rebuilt, and it is started again. It briefly goes offline during the rebuild.
- **Usage:**
  ```bash
  cd UPDATE_AND_RESTART_NODE
  ./update_end_user_node.sh
  ```

## Important Notes
- **Good News:** This script --will not-- destroy any data. Your blockchain and wallet live in the `end_user_node/wallet_data` bind mount, which survives the stop/rebuild. (Back up that wallet anyway!)
- **This script runs `git pull`.** If you created your own chain with `create_new_chain.sh` (which deletes the `.git` folder), the pull will fail because the project is no longer a git repository — run the startup/shutdown scripts to rebuild instead, or re-point this at your own repo.
- **Why it stops the container first:** The script runs `down` before `up --build`. This avoids a known crash in the legacy `docker-compose` (v1) — `KeyError: 'ContainerConfig'` — that happens when it tries to recreate a running container in place after the image was rebuilt. Creating fresh containers sidesteps that bug (and works fine on Compose v2 too).
