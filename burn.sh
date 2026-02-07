#!/bin/bash

# 1. Stop all running containers
echo "Stopping all containers..."
docker stop $(docker ps -aq) 2>/dev/null

# 2. Remove all containers
echo "Removing all containers..."
docker rm $(docker ps -aq) 2>/dev/null

# 3. Remove all images
echo "Deleting all images..."
docker rmi $(docker images -q) -f 2>/dev/null

echo "Cleanup complete."

# 4. Remove persistence data (ensure fresh blockchain)
echo "Wiping blockchain data..."
sudo rm -rf /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node/wallet_data
sudo rm -rf /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/seed_nodes/dns_seed_data


# Build with no-cache to ensure fresh code
docker compose -f /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/seed_nodes/docker-compose.yml build --no-cache
docker compose -f /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/seed_nodes/docker-compose.yml up -d --force-recreate

docker compose -f /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node/docker-compose.yml build --no-cache
docker compose -f /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node/docker-compose.yml up -d --force-recreate
