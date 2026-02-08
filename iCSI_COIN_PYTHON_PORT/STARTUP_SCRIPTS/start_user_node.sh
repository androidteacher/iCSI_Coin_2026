#!/bin/bash

# Define Project Roots
PROJECT_ROOT="/home/josh/Antigrav_projects/iCSI_Coin/iCSI_COIN_PYTHON_PORT"
USER_NODE_ROOT="$PROJECT_ROOT/end_user_node"

echo "=================================================="
echo "   Starting iCSI Coin USER NODE ONLY"
echo "=================================================="

# Start End User Node & Explorer
echo "Starting End User Node & Explorer..."
cd "$USER_NODE_ROOT"

# Ensure we pull base image changes if any (or rely on build)
# The user wants to build.
if sudo docker compose up -d --build; then
    echo " -> User Node Started Successfully."
    echo ""
    echo "   - User Node: Running (http://localhost:8080)"
    echo "   - Explorer: Running (http://localhost:8080/explorer)"
else
    echo " -> FAILED to start User Node."
    exit 1
fi
