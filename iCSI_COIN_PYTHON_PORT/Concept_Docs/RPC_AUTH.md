# RPC Authentication

The iCSI Coin Node RPC interface supports HTTP Basic Authentication.

By default, the node is configured with:
- **Username**: `user`
- **Password**: `pass`

## Enforcing Authentication
By default, the node **ignores** authentication to maintain backward compatibility. You can enforce authentication via the "RPC Auth" menu in the dashboard.

1. Click **RPC Auth** in the top navigation bar.
2. Check **Enforce Username/Password**.
3. (Optional) Change the Username or Password.
4. Click **Save Configuration**.

Once enforced, any request without valid credentials will receive a `401 Unauthorized` response.

## Connecting with Miner
If authentication is enforced, your miner must provide the correct credentials. 

### Standalone Miner (`miner.py`)
Use the `--user` and `--pass` arguments:

```bash
python3 miner.py --url http://127.0.0.1:9340 --user myuser --pass mypassword
```

### cURL Example
To manually interact with the RPC interface using `curl`, use the `-u` flag:

```bash
curl -u myuser:mypassword --data-binary '{"jsonrpc": "1.0", "id": "curltest", "method": "getinfo", "params": []}' -H 'content-type: text/plain;' http://127.0.0.1:9340/
```
