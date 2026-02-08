#!/bin/bash

# Define Project Roots
PROJECT_ROOT="/home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT"
USER_NODE_ROOT="$PROJECT_ROOT/end_user_node"

echo "=================================================="
echo "   Starting iCSI Coin FULL STACK (Seeds + Node)"
echo "=================================================="

# 1. Start Seeds, Admin Node, and STUN Server
echo "[1/2] Starting Seeds and STUN..."
cd "$PROJECT_ROOT"
if sudo docker compose -f docker-compose-seeds.yml up -d --build; then
    echo " -> Seeds Started Successfully."
else
    echo " -> FAILED to start Seeds."
    exit 1
fi

# 2. Start End User Node & Explorer
echo "[2/2] Starting End User Node & Explorer..."
cd "$USER_NODE_ROOT"
if sudo docker compose up -d --build; then
    echo " -> User Node Started Successfully."
else
    echo " -> FAILED to start User Node."
    exit 1
fi

echo "=================================================="
echo "   Stack Startup Complete!"
echo "   - Seeds: Running"
echo "   - STUN: Running"
echo "   - User Node: Running (http://localhost:8080)"
echo "   - Explorer: Running (http://localhost:8080/explorer)"
echo "=================================================="
