#!/bin/bash

# Define paths
PROJECT_ROOT="/home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT"

echo "----------------------------------------------------------------"
echo "🔥 BURNING DOWN THE HOUSE (Resetting iCSI Coin Network) 🔥"
echo "----------------------------------------------------------------"

# 1. Stop Containers
echo "[+] Stopping containers..."
docker compose -f $PROJECT_ROOT/docker-compose-seeds.yml down --remove-orphans
docker compose -f $PROJECT_ROOT/end_user_node/docker-compose.yml down --remove-orphans
# Force stop any stragglers
docker stop $(docker ps -aq) 2>/dev/null
docker rm $(docker ps -aq) 2>/dev/null

# 2. Prune Networks
echo "[+] Pruning networks..."
docker network prune -f

# 3. Wipe Data
echo "[+] Wiping persistent data..."
# Wipe seed data (mounted from end_user_node/data_seed*)
sudo rm -rf $PROJECT_ROOT/end_user_node/data_seed*
sudo rm -rf $PROJECT_ROOT/end_user_node/data_admin

# Wipe user wallet data (preserve directory structure)
echo "[+] Wiping user wallet data..."
sudo rm -rf $PROJECT_ROOT/end_user_node/wallet_data/*
# Ensure directory exists
mkdir -p $PROJECT_ROOT/end_user_node/wallet_data

# 4. Start Seeds
echo "[+] Starting Seed Cluster (Seeds 1-3 + Admin + STUN)..."
docker compose -f $PROJECT_ROOT/docker-compose-seeds.yml up -d --build

echo "[+] Waiting 15s for seeds to stabilize..."
sleep 15

# 5. Start User Node
echo "[+] Starting User Node..."
docker compose -f $PROJECT_ROOT/end_user_node/docker-compose.yml up -d --build

echo "----------------------------------------------------------------"
echo "✅ SYSTEM RESET COMPLETE"
echo "----------------------------------------------------------------"
echo "Web Interface: http://localhost:8080"
echo "Seed One RPC:  http://localhost:9337"
echo "User Node RPC: http://localhost:9342"
echo "----------------------------------------------------------------"
