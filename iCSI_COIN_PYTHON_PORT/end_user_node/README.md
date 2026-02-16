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


