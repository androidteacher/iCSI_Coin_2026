#!/bin/bash

# Define Project Roots
PROJECT_ROOT="/home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT"
USER_NODE_ROOT="$PROJECT_ROOT/end_user_node"

echo "=================================================="
echo "   Stopping iCSI Coin FULL STACK"
echo "=================================================="

# 1. Stop End User Node & Explorer
echo "[1/2] Stopping End User Node & Explorer..."
if [ -d "$USER_NODE_ROOT" ]; then
    cd "$USER_NODE_ROOT"
    if sudo docker compose down; then
        echo " -> User Node Stopped."
    else
        echo " -> FAILED to stop User Node."
    fi
else
    echo " -> User Node directory not found: $USER_NODE_ROOT"
fi

# 2. Stop Seeds and STUN
echo "[2/2] Stopping Seeds and STUN..."
if [ -d "$PROJECT_ROOT" ]; then
    cd "$PROJECT_ROOT"
    if sudo docker compose -f docker-compose-seeds.yml down; then
        echo " -> Seeds Stopped."
    else
        echo " -> FAILED to stop Seeds."
    fi
else
    echo " -> Project Root directory not found: $PROJECT_ROOT"
fi

echo "=================================================="
echo "   Full Stack Shutdown Complete!"
echo "   (Images preserved)"
echo "=================================================="
