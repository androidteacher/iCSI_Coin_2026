#!/bin/bash

# Define Project Roots
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
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
echo "   Starting iCSI Coin FULL STACK (Seeds + Node)"
echo "=================================================="

# 1. Start Seeds, Admin Node, and STUN Server
echo "[1/2] Starting Seeds and STUN..."
cd "$PROJECT_ROOT"
if $DC -f docker-compose-seeds.yml up -d --build; then
    echo " -> Seeds Started Successfully."
else
    echo " -> FAILED to start Seeds."
    exit 1
fi

# 2. Start End User Node & Explorer
echo "[2/2] Starting End User Node & Explorer..."
cd "$USER_NODE_ROOT"
if $DC up -d --build; then
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
