#!/bin/bash

# Define Project Roots
PROJECT_ROOT="/home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT"
USER_NODE_ROOT="$PROJECT_ROOT/end_user_node"

echo "=================================================="
echo "   Stopping iCSI Coin USER NODE ONLY"
echo "=================================================="

# Stop End User Node & Explorer
echo "Stopping End User Node & Explorer..."
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

echo "=================================================="
echo "   User Node Shutdown Complete!"
echo "   (Images preserved)"
echo "=================================================="
