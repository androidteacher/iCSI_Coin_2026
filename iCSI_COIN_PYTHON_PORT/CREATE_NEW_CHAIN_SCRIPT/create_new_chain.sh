#!/bin/bash
# ============================================================================
#  create_new_chain.sh  —  Fork iCSI Coin into a brand-new chain
# ============================================================================
#  See README.md in this folder for the full why / when / what.
#
#  WARNING: This script DELETES the project's .git folder so you can start a
#  fresh git repository AND a fresh blockchain. A complete backup .tar of the
#  whole project is written next to the project folder BEFORE anything is
#  changed or deleted. Proceed with caution.
# ============================================================================

set -u

# ── Resolve paths from this script's own location ──
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"          # .../iCSI_Coin_2026
PARENT="$( cd "$PROJECT_ROOT/.." && pwd )"                 # folder that contains the project
PROJECT_NAME="$( basename "$PROJECT_ROOT" )"
BACKUP_TAR="$PARENT/iCSI_Coin_2026_Backup.tar"

NODE="$PROJECT_ROOT/iCSI_COIN_PYTHON_PORT/end_user_node"
VALIDATION="$NODE/icsicoin/consensus/validation.py"
MESSAGES="$NODE/icsicoin/network/messages.py"
CHAIN="$NODE/icsicoin/core/chain.py"

# ── Sanity checks ──
for f in "$VALIDATION" "$MESSAGES" "$CHAIN"; do
    [ -f "$f" ] || { echo "ERROR: expected file not found:"; echo "  $f"; echo "Run this from inside the iCSI_Coin_2026 project."; exit 1; }
done
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required but was not found."; exit 1; }
command -v tar     >/dev/null 2>&1 || { echo "ERROR: tar is required but was not found."; exit 1; }

# ── The big warning ──
echo "============================================================"
echo "   CREATE A NEW iCSI COIN CHAIN   —   READ CAREFULLY"
echo "============================================================"
echo "This script will:"
echo "  * Write a one-time BACKUP of the ENTIRE project to:"
echo "        $BACKUP_TAR"
echo "    (made BEFORE anything is changed or deleted)"
echo "  * Ask you for new chain settings (block time, difficulty"
echo "    interval, halving interval, genesis message)."
echo "  * Change the network 'magic bytes' to a new RANDOM value."
echo "  * >>> DELETE the project's .git folder <<<   (proceed with caution!)"
echo ""
echo "Deleting .git removes this project's git history so you can"
echo "re-initialize it as a BRAND-NEW repository and start a BRAND-NEW"
echo "chain (from block 0) with your students."
echo "============================================================"
echo ""

# ── Read the current values out of the source ──
CUR_BLOCKTIME="$(grep -E '^TARGET_BLOCK_TIME_SECONDS' "$VALIDATION" | grep -oE '[0-9]+' | head -1)"
CUR_DIFF="$(grep -E '^DIFFICULTY_ADJUSTMENT_INTERVAL' "$VALIDATION" | grep -oE '[0-9]+' | head -1)"
CUR_HALVING="$(grep -E 'ICSI_HALVING_INTERVAL' "$VALIDATION" | grep -oE '"[0-9]+"' | tr -d '"' | head -1)"
CUR_MAGIC="$(grep -E '^MAGIC_VALUE' "$MESSAGES" | grep -oE '0[xX][0-9A-Fa-f]+' | head -1)"
CUR_MSG="$(python3 - "$CHAIN" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
m = re.search(r"0xffffffff,\s*b'((?:\\.|[^'\\])*)',\s*0xffffffff\)", s)
print(m.group(1) if m else "")
PY
)"

# ── Helper: ask for a positive integer; blank keeps the current value ──
ask_int() {
    local prompt="$1" cur="$2" ans
    while true; do
        read -r -p "$prompt" ans
        if [ -z "$ans" ]; then echo "$cur"; return; fi
        if printf '%s' "$ans" | grep -qE '^[1-9][0-9]*$'; then echo "$ans"; return; fi
        echo "  Please enter a positive whole number (or press Enter to keep $cur)." >&2
    done
}

# ── 1. Block time ──
echo "Current target block time: ${CUR_BLOCKTIME} seconds per block."
BLOCKTIME="$(ask_int "How often (in seconds) would you like blocks to be mined? [${CUR_BLOCKTIME}]: " "$CUR_BLOCKTIME")"
echo ""

# ── 2. Difficulty adjustment interval ──
echo "Current difficulty adjustment interval: ${CUR_DIFF} blocks."
DIFF_INTERVAL="$(ask_int "How many blocks between difficulty adjustments? [${CUR_DIFF}]: " "$CUR_DIFF")"
echo ""

# ── 3. Halving interval ──
echo "Current block-reward halving interval: ${CUR_HALVING} blocks."
HALVING="$(ask_int "How many blocks between reward halvings? [${CUR_HALVING}]: " "$CUR_HALVING")"
echo ""

# ── 4. Genesis secret message ──
echo "Current genesis block secret message:"
echo "    \"${CUR_MSG}\""
read -r -p "Enter a NEW genesis message (or press Enter to keep the current one): " NEW_MSG
if [ -z "$NEW_MSG" ]; then GENESIS_MSG="$CUR_MSG"; else GENESIS_MSG="$NEW_MSG"; fi
echo ""

# ── Summary + final confirmation ──
echo "------------------------------------------------------------"
echo "  New chain settings:"
echo "    Block time          : ${BLOCKTIME} s"
echo "    Difficulty interval : ${DIFF_INTERVAL} blocks"
echo "    Halving interval    : ${HALVING} blocks"
echo "    Genesis message     : \"${GENESIS_MSG}\""
echo "    Magic bytes         : a NEW RANDOM value (shown after you confirm)"
echo "------------------------------------------------------------"
echo ""
echo "I will now change the 'magic bytes' and delete the .git folder, which"
echo "will allow you to push this to GitHub and start a new chain with a"
echo "group of students. (A full backup is written first.)"
echo ""
read -r -p "Are you ready? Type YES or NO: " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted. Nothing was changed or deleted."
    exit 0
fi
echo ""

# ── Backup FIRST, before any change or deletion ──
echo "Creating backup: $BACKUP_TAR ..."
if tar -cf "$BACKUP_TAR" -C "$PARENT" "$PROJECT_NAME"; then
    echo " -> Backup created (includes the current .git and all data)."
else
    echo "ERROR: backup failed. Nothing else was changed. Aborting."
    exit 1
fi
echo ""

# ── Generate a new RANDOM magic value ──
NEW_MAGIC="$(python3 -c 'import random; print("0x%08X" % random.randint(0x10000000, 0xFFFFFFFF))')"

# ── Apply the edits to the source files (robust, via python) ──
export VALIDATION MESSAGES CHAIN BLOCKTIME DIFF_INTERVAL HALVING NEW_MAGIC GENESIS_MSG
if ! python3 - <<'PY'
import os, re, sys

def edit(path, subs):
    s = open(path).read()
    for pattern, repl in subs:
        s, n = re.subn(pattern, repl, s, count=1)
        if n != 1:
            sys.exit("ERROR: could not locate the value to update in %s\n  (pattern: %s)" % (path, pattern))
    open(path, "w").write(s)

V = os.environ["VALIDATION"]; M = os.environ["MESSAGES"]; C = os.environ["CHAIN"]
bt = os.environ["BLOCKTIME"]; di = os.environ["DIFF_INTERVAL"]; hv = os.environ["HALVING"]
magic = os.environ["NEW_MAGIC"]; msg = os.environ["GENESIS_MSG"]

# Consensus numbers in validation.py
edit(V, [
    (r"(?m)^(TARGET_BLOCK_TIME_SECONDS = )\d+",       lambda m: m.group(1) + bt),
    (r"(?m)^(DIFFICULTY_ADJUSTMENT_INTERVAL = )\d+",  lambda m: m.group(1) + di),
    (r'(ICSI_HALVING_INTERVAL", ")\d+(")',            lambda m: m.group(1) + hv + m.group(2)),
])

# Network magic in messages.py
edit(M, [
    (r"(?m)^(MAGIC_VALUE = )0[xX][0-9A-Fa-f]+", lambda m: m.group(1) + magic),
])

# Genesis coinbase message in chain.py -> build a safe python bytes literal
def to_bytes_literal(s):
    out = []
    for b in s.encode("utf-8"):
        if b == 0x5c:   out.append("\\\\")   # backslash
        elif b == 0x27: out.append("\\'")    # single quote
        elif 32 <= b < 127: out.append(chr(b))
        else: out.append("\\x%02x" % b)      # non-printable / non-ASCII
    return "b'" + "".join(out) + "'"

lit = to_bytes_literal(msg)
edit(C, [
    (r"(0xffffffff,\s*)b'(?:\\.|[^'\\])*'(\s*,\s*0xffffffff\))", lambda m: m.group(1) + lit + m.group(2)),
])
print("Source files updated.")
PY
then
    echo ""
    echo "ERROR: failed to update the source files. Nothing was deleted."
    echo "Your backup is safe at: $BACKUP_TAR"
    exit 1
fi

echo ""
echo "New magic bytes: $NEW_MAGIC   (was: $CUR_MAGIC)"
echo ""

# ── Delete the .git folder ──
if [ -d "$PROJECT_ROOT/.git" ]; then
    echo "Deleting .git folder..."
    rm -rf "$PROJECT_ROOT/.git"
    echo " -> .git removed. This is no longer a git repository."
else
    echo "(No .git folder found — nothing to delete.)"
fi
echo ""

# ── Final instructions ──
cat <<EOF
============================================================
  NEW CHAIN READY
============================================================
Your project is now a fresh, un-tracked copy configured for a new chain:
  * block time          = ${BLOCKTIME}s
  * difficulty interval = ${DIFF_INTERVAL} blocks
  * halving interval    = ${HALVING} blocks
  * magic bytes         = ${NEW_MAGIC}
  * genesis message     = "${GENESIS_MSG}"

Backup of the ORIGINAL project: ${BACKUP_TAR}

NEXT STEPS

  1. Make it a new git repository:
       cd "${PROJECT_ROOT}"
       git init
       git add .
       git commit -m "Initial commit - new iCSI Coin chain"

  2. (Optional) push to a NEW GitHub repo for your students to clone:
       git remote add origin <your-new-repo-URL>
       git branch -M main
       git push -u origin main

  3. Wipe any OLD blockchain data so every node builds the NEW genesis
     (block 0) with the new magic + settings:
       cd "${PROJECT_ROOT}/iCSI_COIN_PYTHON_PORT/BLOCKCHAIN_RESET_SCRIPTS"
       ./clear_stack.sh            # full stack
       #  or  ./clear_end_user_node.sh   # a single node

  4. Start the new chain:
       cd "${PROJECT_ROOT}/iCSI_COIN_PYTHON_PORT/STARTUP_SCRIPTS"
       ./start_full_stack.sh      # or ./start_user_node.sh

  IMPORTANT: Every node (and every student's clone) must use these exact
  same values -- they are consensus rules. That is why you set them here
  ONCE, before sharing the new repository.
============================================================
EOF
