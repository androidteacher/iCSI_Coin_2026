#!/bin/bash
# ============================================================================
#  START_NODE.sh — One-command setup + launch for an iCSI Coin end-user node
# ============================================================================
#
#  For students / end users. After cloning the repo, just run:
#
#      ./START_NODE.sh
#
#  It will:
#    1. Update apt package lists
#    2. Install Docker (docker.io) and Docker Compose -- automatically handling
#       both the legacy 'docker-compose' package AND the newer 'docker compose'
#       plugin, so it won't fail just because your system packages Compose
#       differently
#    3. Build and start your node (via STARTUP_SCRIPTS/start_user_node.sh)
#    4. Tell you exactly where to open it in your browser
# ============================================================================

set -u

# Resolve where this script lives so it works no matter what directory you run it from.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
START_USER_NODE="$SCRIPT_DIR/iCSI_COIN_PYTHON_PORT/STARTUP_SCRIPTS/start_user_node.sh"

echo "=================================================="
echo "   iCSI Coin — Node Setup & Launch"
echo "=================================================="

# ── Step 1: Update apt package lists ─────────────────────────────────
echo ""
echo "[1/4] Updating package lists (sudo apt update)..."
sudo apt update

# ── Step 2: Install the Docker engine ────────────────────────────────
echo ""
echo "[2/4] Installing Docker engine (docker.io)..."
sudo apt install -y docker.io

# Make sure the Docker daemon is actually running (harmless if it already is).
sudo systemctl enable --now docker 2>/dev/null || true

# ── Step 3: Install Docker Compose (plugin OR legacy binary) ─────────
# Some systems ship Compose v2 as the 'docker compose' plugin; older ones use
# the standalone 'docker-compose' binary; and the apt package name differs
# between distro versions. Rather than fail, we try the options in order and
# only stop once a working Compose command exists.
echo ""
echo "[3/4] Ensuring Docker Compose is installed..."
if docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1; then
    echo "      Docker Compose is already available."
else
    echo "      Installing Docker Compose (trying available package names)..."
    sudo apt install -y docker-compose \
        || sudo apt install -y docker-compose-v2 \
        || sudo apt install -y docker-compose-plugin \
        || true
fi

# Verify that a Compose command now works; fail clearly if not.
if docker compose version >/dev/null 2>&1; then
    echo "      ✔ Using: docker compose (v2 plugin)"
elif command -v docker-compose >/dev/null 2>&1; then
    echo "      ✔ Using: docker-compose (legacy)"
else
    echo ""
    echo "ERROR: Docker Compose could not be installed automatically."
    echo "       (Tried: docker-compose, docker-compose-v2, docker-compose-plugin.)"
    echo "       Please install Docker Compose manually, then re-run ./START_NODE.sh"
    exit 1
fi

# ── Step 4: Build & start the end-user node ──────────────────────────
echo ""
echo "[4/4] Building & starting your node (this can take a few minutes the first time)..."
if ! bash "$START_USER_NODE"; then
    echo ""
    echo "ERROR: The node failed to start. See the output above for details."
    exit 1
fi

# ── Success! Make it impossible to miss. ─────────────────────────────
echo ""
echo ""
echo "############################################################"
echo "############################################################"
echo "##                                                        ##"
echo "##            ✅  YOUR iCSI COIN NODE IS RUNNING!          ##"
echo "##                                                        ##"
echo "##        Open your web browser and go to:                ##"
echo "##                                                        ##"
echo "##             >>>   http://localhost:8080   <<<          ##"
echo "##                                                        ##"
echo "##             to access your node!                       ##"
echo "##                                                        ##"
echo "############################################################"
echo "############################################################"
echo ""
echo "   (On first launch, create a username and password there.)"
echo ""
