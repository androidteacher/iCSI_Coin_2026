# Useful Commands

This document contains a collection of useful commands for managing, debugging, and interacting with the iCSI Coin node.

## Network Connectivity

### Manually Connect to a Peer (`-addnode`)

If your node is not automatically discovering a specific peer, or if you need to bridge two separate networks, you can force a connection using the `-addnode` argument. This limits the node to *only* connecting to the specified peer (and any peers it discovers from them) or adds it to the list of persistent nodes to maintain.

> **Note on Auto-Discovery**: The node now supports **Active LAN Discovery**. If it finds itself isolated for more than 60 seconds, it will automatically scan your local subnet (e.g., `192.168.229.x`) for other nodes on port 9333. Manual connection should only be needed for cross-network peering.

**Command Structure (New! Runtime Supported):**
You can now add a peer **without restarting** by using the new `addnode` RPC command.

```bash
curl --data-binary '{"jsonrpc": "1.0", "id":"curltest", "method": "addnode", "params": ["<target_ip>:<port>"]}' -H 'content-type: text/plain;' http://user:password@127.0.0.1:9332/
```

**Example:**
To connect to `192.168.229.149:9333` from *within* the container (or from host mapped port):

```bash
docker exec -it <container_id> curl --data-binary '{"jsonrpc": "1.0", "id":"curltest", "method": "addnode", "params": ["192.168.229.149:9333"]}' -H 'content-type: text/plain;' http://user:password@127.0.0.1:9332/
```

**What this does:**
1.  Executes the python script inside the running Docker container.
2.  Passes the `-addnode` flag, telling the `NetworkManager` to immediately attempt a connection to `192.168.229.149` on port `9333`.
3.  If successful, the nodes will exchange version messages and begin synchronizing blocks.
