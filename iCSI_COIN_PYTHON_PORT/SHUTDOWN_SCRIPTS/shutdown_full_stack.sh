#!/bin/bash

# Define Project Roots (Relative to script location)
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/.."
USER_NODE_ROOT="$PROJECT_ROOT/end_user_node"

# Resolve the Docker Compose command: prefer the v2 plugin ("docker compose"),
# fall back to the legacy standalone binary ("docker-compose") on older systems.
if sudo docker compose version >/dev/null 2>&1; then
    DC="sudo docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="sudo docker-compose"
else
    echo "ERROR: Neither 'docker compose' (v2 plugin) nor 'docker-compose' (legacy) is installed." >&2
    exit 1
fi

echo "=================================================="
echo "   Stopping iCSI Coin FULL STACK"
echo "=================================================="

# 1. Stop End User Node & Explorer
echo "[1/2] Stopping End User Node & Explorer..."
if [ -d "$USER_NODE_ROOT" ]; then
    cd "$USER_NODE_ROOT"
    if $DC down; then
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
    if $DC -f docker-compose-seeds.yml down; then
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
