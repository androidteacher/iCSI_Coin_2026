import argparse
import json
import socket
import time
import sys

# Configure logging? No, CLI should be simple stdout.

def rpc_call(url, method, params=None):
    import requests
    headers = {'content-type': 'application/json'}
    payload = {
        "method": method,
        "params": params or [],
        "jsonrpc": "2.0",
        "id": 1,
    }
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers, auth=('user', 'pass'))
        response.raise_for_status()
        return response.json().get('result')
    except Exception as e:
        print(f"RPC Error: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="iCSI Coin CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # getinfo
    subparsers.add_parser("getinfo", help="Get node info")
    
    # getpeerinfo
    subparsers.add_parser("getpeerinfo", help="Get connected peers")
    
    # getblockcount
    subparsers.add_parser("getblockcount", help="Get current block height")
    
    # addnode <ip>:<port>
    addnode_parser = subparsers.add_parser("addnode", help="Add a peer")
    addnode_parser.add_argument("node", help="Node address (IP:Port)")
    
    args = parser.parse_args()
    
    url = "http://127.0.0.1:9342" # Default user-node RPC port
    
    if args.command == "getinfo":
        print(rpc_call(url, "getinfo"))
    elif args.command == "getpeerinfo":
        print(json.dumps(rpc_call(url, "getpeerinfo"), indent=2))
    elif args.command == "getblockcount":
        print(rpc_call(url, "getblockcount"))
    elif args.command == "addnode":
        print(rpc_call(url, "addnode", [args.node]))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
