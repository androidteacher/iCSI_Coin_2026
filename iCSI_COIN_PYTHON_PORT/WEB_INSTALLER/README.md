# Web Installer

This folder contains **`install.sh`** — a one-command web installer that prepares a
fresh Debian/Ubuntu machine and launches an iCSI Coin node.

## One-command install

```bash
curl -s https://raw.githubusercontent.com/androidteacher/iCSI_Coin_2026/refs/heads/main/iCSI_COIN_PYTHON_PORT/WEB_INSTALLER/install.sh | bash
```

## What it does (in order)

1. **Checks for root / sudo.** `apt` needs root, so the script uses `sudo`
   automatically when you aren't root. If neither root nor `sudo` is available, it
   stops with a clear message.
2. **Verifies this is a Debian/Ubuntu system** (that `apt-get` exists). If not, it
   tells you to install the prerequisites manually.
3. **Runs `apt update`** to refresh the package lists. If this fails, it stops and
   tells you to check your internet connection and apt sources, then re-run.
4. **Installs the prerequisites — `curl` and `git`** (`apt install -y curl git`).
   If the install fails, or the tools still aren't available afterward, it stops
   with a clear error. These two are required to download and set up iCSI Coin.
5. **Clones the repository** (`git clone …`). If an `iCSI_Coin_2026` folder already
   exists, it skips the clone instead of failing.
6. **Enters the project folder** and runs **`./START_NODE.sh`**, which installs
   Docker / Docker Compose and builds and starts your node.

Every step checks for failure and prints clear, color-coded output (`==>` progress,
`✔` success, `ERROR:` failure), so if something goes wrong you know exactly which
step failed and what to do about it.

## Requirements

- A **Debian/Ubuntu-based** Linux system (uses `apt`).
- Permission to install packages — run as **root**, or have **`sudo`** available.
- An internet connection.

> `curl` and `git` are installed for you by the script. (If you used the
> one-command install above, you already have `curl`.)

## Prefer to do it by hand?

```bash
# 1. Install the prerequisites
sudo apt update
sudo apt install -y curl git

# 2. Clone the repository
git clone https://github.com/androidteacher/iCSI_Coin_2026.git

# 3. Enter the project folder
cd iCSI_Coin_2026

# 4. Set everything up and launch your node
./START_NODE.sh
```

When it finishes, open **http://localhost:8080** to access your node and create a
username and password.
