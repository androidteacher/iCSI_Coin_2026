#!/bin/bash
# ============================================================================
#  clear_stack.sh — FULL NETWORK RESET (Seed Nodes + Local End User Node)
# ============================================================================
#
#  USE THIS ON THE SEED HOST to start a completely fresh blockchain.
#
#  THIS SCRIPT WILL DELETE:
#  ─────────────────────────────────────────────────────────────────────────
#  1. SEED NODE DATA (blockchain, chainstate, wallets for each seed):
#       • end_user_node/data_seed1/   — Seed Node 1 (P2P 9333)
#       • end_user_node/data_seed2/   — Seed Node 2 (P2P 9334)
#       • end_user_node/data_seed3/   — Seed Node 3 (P2P 9335)
#       • end_user_node/data_admin/   — Admin Node  (P2P 9336)
#
#  2. LOCAL END USER NODE DATA (blockchain, chainstate, wallets):
#       • end_user_node/wallet_data/  — User Node   (P2P 9341)
#
#  THIS SCRIPT WILL ALSO:
#  ─────────────────────────────────────────────────────────────────────────
#  • Stop and remove ALL containers from both docker-compose files
#  • Prune orphaned Docker networks
#  • Rebuild and restart the seed cluster (Seeds 1-3, Admin, STUN)
#  • Rebuild and restart the local end user node + explorer
#
#  AFTER RUNNING: All nodes start mining on a brand new genesis block.
#  ============================================================================

set -e

# Auto-detect project root (directory this script lives in)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

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

echo ""
echo "================================================================"
echo "  🔥  FULL STACK RESET — iCSI Coin Network  🔥"
echo "================================================================"
echo ""
echo "  ⚠  THIS WILL DESTROY ALL BLOCKCHAIN DATA ON THIS HOST"
echo "     Including: seed node data, user node wallet, and chainstate"
echo ""
read -p "  Type 'YES' to confirm: " confirm
if [ "$confirm" != "YES" ]; then
    echo "  Aborted."
    exit 0
fi

echo ""

# ── Step 1: Stop all containers ──────────────────────────────────────
echo "[1/5] Stopping containers..."
$DC -f "$PROJECT_ROOT/docker-compose-seeds.yml" down --remove-orphans 2>/dev/null || true
$DC -f "$PROJECT_ROOT/end_user_node/docker-compose.yml" down --remove-orphans 2>/dev/null || true
echo "      ✔ Containers stopped"

# ── Step 2: Prune networks ──────────────────────────────────────────
echo "[2/5] Pruning Docker networks..."
docker network prune -f > /dev/null 2>&1
echo "      ✔ Networks pruned"

# ── Step 3: Delete all persistent data ───────────────────────────────
echo "[3/5] Deleting persistent data..."
echo "      → Removing: data_seed1/"
sudo rm -rf "$PROJECT_ROOT/end_user_node/data_seed1"
echo "      → Removing: data_seed2/"
sudo rm -rf "$PROJECT_ROOT/end_user_node/data_seed2"
echo "      → Removing: data_seed3/"
sudo rm -rf "$PROJECT_ROOT/end_user_node/data_seed3"
echo "      → Removing: data_admin/"
sudo rm -rf "$PROJECT_ROOT/end_user_node/data_admin"
echo "      → Removing: wallet_data/ (end user node)"
sudo rm -rf "$PROJECT_ROOT/end_user_node/wallet_data"
mkdir -p "$PROJECT_ROOT/end_user_node/wallet_data"
echo "      ✔ All data wiped"

# ── Step 4: Rebuild & start seed cluster ─────────────────────────────
echo "[4/5] Building & starting Seed Cluster..."
$DC -f "$PROJECT_ROOT/docker-compose-seeds.yml" up -d --build
echo "      ✔ Seed cluster running (Seeds 1-3 + Admin + STUN)"
echo "      ⏳ Waiting 15s for seeds to stabilize..."
sleep 15

# ── Step 5: Rebuild & start end user node ────────────────────────────
echo "[5/5] Building & starting End User Node..."
$DC -f "$PROJECT_ROOT/end_user_node/docker-compose.yml" up -d --build
echo "      ✔ End user node running"

echo ""
echo "================================================================"
echo "  ✅  STACK RESET COMPLETE — Fresh Blockchain Active"
echo "================================================================"
echo ""
echo "  Web Interface:  http://localhost:8080"
echo "  Admin Web:      http://localhost:5000"
echo "  Seed 1 RPC:     http://localhost:9337"
echo "  User Node RPC:  http://localhost:9342"
echo ""
echo "================================================================"
