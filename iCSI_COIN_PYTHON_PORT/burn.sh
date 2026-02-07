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
echo "Wiping blockchain data..."
sudo rm -rf /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/seed_nodes/data
sudo rm -rf ~/.icsicoin

echo "Synchronizing Source Code..."
rm -rf /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/seed_nodes/icsicoin
cp -r /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node/icsicoin /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/seed_nodes/

echo "Synchronizing Entrypoint..."
cp /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node/icsi_coin_server.py /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/seed_nodes/icsi_coin_server.py
cp /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node/requirements.txt /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/seed_nodes/requirements.txt


docker compose -f /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/seed_nodes/docker-compose.yml up -d
docker compose -f /home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT/end_user_node/docker-compose.yml up -d
