import socket
import json
import struct
import hashlib
import binascii
import time

def create_message(command, payload):
    magic = 0xD9B4BEF9
    cmd = command.encode('ascii') + b'\x00' * (12 - len(command))
    length = len(payload)
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return struct.pack('<I12sI4s', magic, cmd, length, checksum) + payload

def main():
    # Connect to Seed Node 1 (Miner)
    # Port 9333 is the internal port, map verifying with docker logs shows it binds to 0.0.0.0:9333 (Host mode)
    # Wait, logs show "RPC Server on 9337" and P2P on 9333.
    target_ip = '127.0.0.1'
    target_port = 9333 

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((target_ip, target_port))
        print(f"Connected to {target_ip}:{target_port}")

        # 1. VERSION Handshake
        version_payload = json.dumps({
            "version": 1,
            "services": 1,
            "timestamp": int(time.time()),
            "addr_recv": {"ip": target_ip, "port": target_port, "services": 1},
            "addr_from": {"ip": "127.0.0.1", "port": 9999, "services": 1},
            "nonce": 12345,
            "user_agent": "/Satoshi:0.1/",
            "start_height": 0
        }).encode('utf-8')
        
        s.sendall(create_message('version', version_payload))
        print("Sent VERSION")

        # Read Response loop
        while True:
            header = s.recv(24)
            if not header or len(header) < 24:
                print("Connection closed or short read")
                break
                
            magic, cmd, length, checksum = struct.unpack('<I12sI4s', header)
            cmd = cmd.strip(b'\x00').decode('ascii')
            payload = s.recv(length)
            
            print(f"Received: {cmd}")
            
            if cmd == 'version':
                # Send VERACK
                s.sendall(create_message('verack', b''))
                print("Sent VERACK")
            
            elif cmd == 'verack':
                # Handshake complete! Now send GETDATA
                # Use a hash we saw in the logs (Seed 1 mined block 30)
                # Hash: 3ad44b165fa265b7eb078f4d75b9e56ea0ac48ad11db5b2f89e22d6d268c0600
                block_hash = "3ad44b165fa265b7eb078f4d75b9e56ea0ac48ad11db5b2f89e22d6d268c0600" 
                inv_payload = json.dumps({
                    "inventory": [
                        {"type": "block", "hash": block_hash}
                    ]
                }).encode('utf-8')
                
                s.sendall(create_message('getdata', inv_payload))
                print(f"Sent GETDATA for {block_hash}")

            elif cmd == 'block':
                print("SUCCESS! Received BLOCK payload.")
                break
                
            elif cmd == 'inv':
                print("Received INV (ignoring)")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        s.close()

if __name__ == "__main__":
    main()
