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
# Bring any existing containers DOWN before rebuilding. The legacy docker-compose
# (v1) crashes with "KeyError: 'ContainerConfig'" when it recreates a container in
# place after the image was rebuilt; creating fresh containers avoids that bug (and
# works fine on Compose v2 too). Your data lives in bind mounts, so this is safe.
$DC -f docker-compose-seeds.yml down --remove-orphans 2>/dev/null || true
if $DC -f docker-compose-seeds.yml up -d --build; then
    echo " -> Seeds Started Successfully."
else
    echo " -> FAILED to start Seeds."
    exit 1
fi

# 2. Start End User Node & Explorer
echo "[2/2] Starting End User Node & Explorer..."
cd "$USER_NODE_ROOT"
$DC down --remove-orphans 2>/dev/null || true
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
