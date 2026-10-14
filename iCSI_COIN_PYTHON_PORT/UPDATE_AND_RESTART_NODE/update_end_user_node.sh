#!/bin/bash
set -u

# Resolve paths from this script's own location so it works from any directory.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
COMPOSE_FILE="$SCRIPT_DIR/../end_user_node/docker-compose.yml"

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
git -C "$SCRIPT_DIR" pull

echo "Stopping the current node containers..."
# Bring the stack DOWN before rebuilding. The legacy docker-compose (v1) crashes
# with "KeyError: 'ContainerConfig'" when it tries to recreate a container in
# place after the image was rebuilt; creating fresh containers avoids that bug
# entirely (and it also works fine on Compose v2). Your blockchain + wallet live
# in the ./wallet_data bind mount, so 'down' does NOT delete any of your data.
$DC -f "$COMPOSE_FILE" down

echo "Rebuilding and restarting end user node container..."
$DC -f "$COMPOSE_FILE" up -d --build

echo "Process Complete!"
