# iCSI Coin - Seed Node Cluster

This directory contains the configuration and source code for running the initial seed nodes of the iCSI Coin network.

## Purpose
Seed nodes act as the backbone of the P2P network, providing initial entry points for new nodes (peers) to discover the network. This configuration spins up 3 interconnected seed nodes.

## Usage

### Prerequisites
*   Docker
*   Docker Compose

### Starting the Cluster
Run the following command in this directory:

```bash
docker compose up -d --build
```

### Components
*   **seed-node-1**: Primary seed, binds to port `9333`.
*   **seed-node-2**: Peers with node-1, binds to port `9334`.
*   **seed-node-3**: Peers with node-1, binds to port `9335`.

### Networking
These nodes are exposed on the host machine on ports 9333, 9334, and 9335. Other nodes can connect to them using the host's IP address and these ports.
