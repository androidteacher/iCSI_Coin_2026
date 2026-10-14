#!/bin/bash

# Resolve the Docker Compose command: prefer the v2 plugin ("docker compose"),
# fall back to the legacy standalone binary ("docker-compose") on older systems.
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    echo "ERROR: Neither 'docker compose' (v2 plugin) nor 'docker-compose' (legacy) is installed." >&2
    exit 1
fi

echo "Pulling latest changes from git..."
git pull
echo "Rebuilding end user node container..."
$DC -f ../end_user_node/docker-compose.yml up -d --build
echo "Process Complete!"
