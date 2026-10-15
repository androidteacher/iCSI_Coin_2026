#!/usr/bin/env bash
#
# iCSI Coin — Web Installer
# Installs the prerequisites (curl, git), clones the project, and launches a node.
# Typical usage:  curl -fsSL <URL>/install.sh | bash
#
set -e

# --- Pretty output helpers ---
info() { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }
ok()   { printf '\033[1;32m  ✔\033[0m %s\n' "$1"; }
err()  { printf '\n\033[1;31mERROR:\033[0m %s\n' "$1" >&2; }

# --- Use sudo only when needed/available (apt requires root) ---
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
elif command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
else
    err "This installer needs root privileges to install packages, but 'sudo' was not found."
    err "Re-run as root, or install 'sudo' first."
    exit 1
fi

# --- Require apt (Debian/Ubuntu) ---
if ! command -v apt-get >/dev/null 2>&1; then
    err "'apt-get' was not found. This installer supports Debian/Ubuntu-based systems only."
    err "Install 'curl' and 'git' with your system's package manager, then re-run the clone/launch steps manually."
    exit 1
fi

# --- 1. Update package lists ---
info "Updating package lists (apt update)..."
if ! $SUDO apt-get update -y; then
    err "'apt update' failed. curl and git are required to continue, and they could not be fetched."
    err "Check your internet connection and that your apt sources are valid, then run this installer again."
    exit 1
fi
ok "Package lists updated."

# --- 2. Install prerequisites: curl + git ---
info "Installing prerequisites: curl and git..."
if ! $SUDO apt-get install -y curl git; then
    err "Failed to install 'curl' and/or 'git' via apt."
    err "These are required to download and set up iCSI Coin. Resolve the apt error shown above, then run this installer again."
    exit 1
fi

# --- Confirm they are actually available now ---
for cmd in curl git; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        err "'$cmd' still isn't available after installation — cannot continue."
        err "Try installing it manually (sudo apt install $cmd) and run this installer again."
        exit 1
    fi
done
ok "curl and git are installed."

# --- 3. Clone the repository ---
info "Cloning the iCSI Coin repository..."
if [ -d iCSI_Coin_2026 ]; then
    ok "Folder 'iCSI_Coin_2026' already exists — skipping clone."
elif ! git clone https://github.com/androidteacher/iCSI_Coin_2026.git; then
    err "Failed to clone the repository. Check your internet connection and try again."
    exit 1
fi

# --- 4. Enter the project folder ---
cd iCSI_Coin_2026 || { err "Could not enter the 'iCSI_Coin_2026' folder."; exit 1; }

# --- 5. Set everything up and launch your node ---
info "Launching your node (START_NODE.sh)..."
./START_NODE.sh
