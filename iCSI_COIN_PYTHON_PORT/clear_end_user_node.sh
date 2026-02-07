#!/bin/bash
# ============================================================================
#  clear_end_user_node.sh — END USER NODE RESET (Local Only)
# ============================================================================
#
#  USE THIS ON A REMOTE NODE that wants to wipe its local blockchain
#  and wallet data, then reconnect fresh to the seed network.
#
#  THIS SCRIPT WILL DELETE:
#  ─────────────────────────────────────────────────────────────────────────
#  1. END USER NODE DATA (all files inside wallet_data/):
#       • wallet_data/blocks/        — Downloaded blockchain blocks
#       • wallet_data/chainstate/    — UTXO set (unspent transaction outputs)
#       • wallet_data/blockindex.sqlite — Block index database
#       • wallet_data/chainstate.sqlite — Chain state database
#       • wallet_data/wallet.dat     — ⚠ YOUR WALLET & PRIVATE KEYS ⚠
#       • wallet_data/debug.log      — Node debug log
#
#  ⚠  WARNING: This PERMANENTLY deletes your wallet!
#     Export/backup your wallet BEFORE running this if you have funds.
#
#  THIS SCRIPT WILL ALSO:
#  ─────────────────────────────────────────────────────────────────────────
#  • Stop and remove the end user node containers (user-node + explorer)
#  • Rebuild and restart them with a clean state
#
#  AFTER RUNNING: The node will sync the blockchain from seed nodes
#  and generate a new wallet automatically.
#  ============================================================================

set -e

# Auto-detect project root (directory this script lives in)
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/end_user_node/docker-compose.yml"
DATA_DIR="$PROJECT_ROOT/end_user_node/wallet_data"

echo ""
echo "================================================================"
echo "  🗑  END USER NODE RESET — iCSI Coin"
echo "================================================================"
echo ""
echo "  ⚠  THIS WILL DELETE YOUR LOCAL BLOCKCHAIN & WALLET DATA"
echo "     Location: $DATA_DIR"
echo ""
echo "  Files to be deleted:"

# Show what exists before deleting
if [ -d "$DATA_DIR" ]; then
    echo "  ─────────────────────────────────────────"
    ls -la "$DATA_DIR" 2>/dev/null | tail -n +2 | while read line; do
        echo "      $line"
    done
    echo "  ─────────────────────────────────────────"
else
    echo "      (directory does not exist — nothing to delete)"
fi

echo ""
read -p "  Type 'YES' to confirm: " confirm
if [ "$confirm" != "YES" ]; then
    echo "  Aborted."
    exit 0
fi

echo ""

# ── Step 1: Stop containers ──────────────────────────────────────────
echo "[1/3] Stopping end user node containers..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
echo "      ✔ Containers stopped"

# ── Step 2: Delete persistent data ───────────────────────────────────
echo "[2/3] Deleting wallet_data/..."
sudo rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR"
echo "      ✔ Data wiped (fresh wallet_data/ created)"

# ── Step 3: Rebuild & restart ────────────────────────────────────────
echo "[3/3] Building & starting End User Node..."
docker compose -f "$COMPOSE_FILE" up -d --build
echo "      ✔ End user node running"

echo ""
echo "================================================================"
echo "  ✅  END USER NODE RESET COMPLETE"
echo "================================================================"
echo ""
echo "  Web Interface:  http://localhost:8080"
echo "  Your node will auto-sync with the seed network."
echo "  A new wallet will be generated on first boot."
echo ""
echo "================================================================"
