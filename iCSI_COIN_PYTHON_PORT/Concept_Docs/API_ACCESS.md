# iCSI Coin - API Access Guide

This document describes the API endpoints available on an iCSI Coin node. These endpoints allow you to interact with the blockchain, manage wallets, control mining, and query network status programmatically.

**Base URL:** `http://localhost:<PORT>`
- **Default Port:** `5000` (for the first node), `5001`, etc.

---

## 🔐 Authentication
Most API endpoints require authentication if a password has been set up on the node.
*   **Cookie Auth:** The web interface uses session cookies.
*   **API Auth:** For scripts, it's recommended to handle the session cookie returned by `/api/auth/login`.

### Login
Authenticates a session.
- **URL:** `/api/auth/login`
- **Method:** `POST`
- **Data:** `{"username": "user", "password": "password"}`

```bash
# Login and save cookie to 'cookies.txt'
curl -c cookies.txt -X POST http://localhost:5000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "securepassword"}'
```

### Setup (First Time Only)
Sets the admin credentials if not already configured.
- **URL:** `/api/auth/setup`
- **Method:** `POST`
- **Data:** `{"username": "user", "password": "password"}`

---

## 💰 Wallet API

### List Wallets
Returns all wallets managed by this node, including their balances.
- **URL:** `/api/wallet/list`
- **Method:** `GET`

```bash
curl -b cookies.txt http://localhost:5000/api/wallet/list
```

### Create Wallet
Generates a new keypair and adds it to the wallet.
- **URL:** `/api/wallet/create`
- **Method:** `POST`
- **Data:** `{"name": "My New Wallet"}`

```bash
curl -b cookies.txt -X POST http://localhost:5000/api/wallet/create \
     -H "Content-Type: application/json" \
     -d '{"name": "Savings"}'
```

### Send Coins
Sends coins from the selected wallet to a destination address.
- **URL:** `/api/wallet/send`
- **Method:** `POST`
- **Data:** `{"from": "SOURCE_ADDRESS", "to": "DEST_ADDRESS", "amount": 10.5}`

```bash
curl -b cookies.txt -X POST http://localhost:5000/api/wallet/send \
     -H "Content-Type: application/json" \
     -d '{
           "from": "16Ue...source...",
           "to": "1Box...dest...", 
           "amount": 50
         }'
```

### Rename Wallet
Updates the display name of a wallet.
- **URL:** `/api/wallet/rename`
- **Method:** `POST`
- **Data:** `{"address": "ADDRESS", "name": "New Name"}`

---

## ⛏️ Mining API

### Start Mining
Starts the internal CPUMiner on the node.
- **URL:** `/api/miner/start`
- **Method:** `POST`
- **Data:** `{"target_address": "ADDRESS_TO_RECEIVE_REWARDS"}`

```bash
curl -b cookies.txt -X POST http://localhost:5000/api/miner/start \
     -H "Content-Type: application/json" \
     -d '{"target_address": "1MyWalletAddress..."}'
```

### Stop Mining
Stops the internal miner.
- **URL:** `/api/miner/stop`
- **Method:** `POST`

### Get Miner Status
Returns the current status (running/stopped) and the last few lines of miner logs.
- **URL:** `/api/miner/status`
- **Method:** `GET`

---

## 🌐 Network API

### List Peers
Returns a list of all known peers and their status.
- **URL:** `/api/peers`
- **Method:** `GET`

```bash
curl http://localhost:5000/api/peers
```

### Connect to Node
Manually connects to a specific seed node IP.
- **URL:** `/api/connect`
- **Method:** `POST`
- **Data:** `{"seed_ip": "192.168.1.100"}`

### Get Network Stats
Returns current block height, difficulty, and next halving info.
- **URL:** `/api/stats`
- **Method:** `GET`

### Reset Node
**WARNING:** Wipes the blockchain data and wallet from the node (factory reset).
- **URL:** `/api/reset`
- **Method:** `POST`

---

## 📦 Blockchain Explorer API

### Get Blocks
Returns a paginated list of recent blocks.
- **URL:** `/api/explorer/blocks`
- **Method:** `GET`
- **Params:** `?page=1&limit=20`

### Get Block Details
Returns full details for a specific block hash.
- **URL:** `/api/explorer/block/{block_hash}`
- **Method:** `GET`

### Get Address Balance
Returns the balance and UTXO count for any address on the network.
- **URL:** `/api/explorer/balance/{address}`
- **Method:** `GET`

```bash
curl http://localhost:5000/api/explorer/balance/1CheckingBalanceAddress...
```

---

## 🛠️ Utilities

### Download Miner (Public)
Downloads a ZIP file containing the standalone python miner script.
- **URL:** `/api/miner/download`
- **Method:** `GET`

### Download Backup (Authenticated)
Downloads a ZIP file containing the node's data directory and wallet keys.
- **URL:** `/api/data/download`
- **Method:** `GET`
- **Requires:** `cookie`

### Run NAT Test (Authenticated)
Triggers a STUN test to verify if the node is reachable from the outside.
- **URL:** `/api/stun/test`
- **Method:** `POST`

