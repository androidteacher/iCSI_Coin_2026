# iCSI Coin - End User Node

This directory contains the configuration and source code for running a User Node with a web-based configuration interface.

## Purpose
The User Node is a client that connects to the iCSI Coin network. It includes a "Dark Cyber" themed web interface that allows real-time configuration of connections and monitoring of discovered peers.

## Usage

### Prerequisites
*   Docker
*   Docker Compose

### Starting the Node
Run the following command in this directory:

```bash
docker compose up -d --build
```

### Web Interface
Once running, access the configuration panel at:
**http://localhost:8080**

### connecting to the Network
1.  Open the Web Interface.
2.  Enter the `IP:Port` of the Seed Nodes you wish to connect to.
    *   *Default*: `192.168.231.32:9333` (This is likely the host IP if running seeds on the same machine).
3.  Click **Initialize Connection**.
4.  View effective connections by clicking **[ DISCOVERED NODES ]**.

## Features
*   **Dynamic Peering**: Connect to any node via the web UI.
*   **Real-time Monitoring**: View active connections and status updates live.
*   **Persistent Identity**: The node generates a unique identity on startup.
