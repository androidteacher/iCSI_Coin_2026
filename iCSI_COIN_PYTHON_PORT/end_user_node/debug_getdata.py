import asyncio
import struct
import time
import json
import binascii

MAGIC_VALUE = 0xfbc0b6db
PEER_IP = '192.168.229.31'
PEER_PORT = 9341

class Message:
    def __init__(self, command, payload):
        self.command = command
        self.payload = payload

    def serialize(self):
        magic = struct.pack('<I', MAGIC_VALUE)
        command_padded = self.command.encode('ascii') + b'\x00' * (12 - len(self.command))
        payload_len = struct.pack('<I', len(self.payload))
        import hashlib
        checksum = hashlib.sha256(hashlib.sha256(self.payload).digest()).digest()[:4]
        return magic + command_padded + payload_len + checksum + self.payload

    @staticmethod
    def serialize_net_addr(services, ip, port):
        res = b''
        res += struct.pack('<Q', services)
        prefix = b'\x00' * 10 + b'\xff' * 2
        parts = ip.split('.')
        ip_bytes = bytes([int(x) for x in parts])
        res += prefix + ip_bytes
        res += struct.pack('>H', port)
        return res

    @staticmethod
    def serialize_var_int(i):
        if i < 0xfd: return struct.pack('B', i)
        elif i <= 0xffff: return b'\xfd' + struct.pack('<H', i)
        return b'\xfe' + struct.pack('<I', i)

def create_version_msg():
    # Payload: Version(4), Services(8), Timestamp(8), AddrRecv(26), AddrFrom(26), Nonce(8), UA(VarStr), Height(4), Relay(1)
    payload = struct.pack('<IQQ', 70015, 1, int(time.time()))
    # Use dummy addresses
    payload += Message.serialize_net_addr(1, '127.0.0.1', 8333) # Recv
    payload += Message.serialize_net_addr(1, '127.0.0.1', 9333) # From
    payload += struct.pack('<Q', 12345) # Nonce
    ua = b'/DebugNode:0.1/'
    payload += Message.serialize_var_int(len(ua)) + ua
    payload += struct.pack('<I', 0) # Start Height 0 to force sync
    payload += b'\x01'
    return Message('version', payload).serialize()

def create_getblocks_msg(genesis_hash):
    msg = {
        "type": "getblocks",
        "locator": [genesis_hash]
    }
    return json.dumps(msg).encode('utf-8')

def create_getdata_msg(inv_items):
    msg = {
        "type": "getdata",
        "inventory": inv_items
    }
    return json.dumps(msg).encode('utf-8')


async def debug_peer():
    print(f"Connecting to {PEER_IP}:{PEER_PORT}...")
    try:
        reader, writer = await asyncio.open_connection(PEER_IP, PEER_PORT)
        print("Connected!")
        
        # 1. Send Version (Claim Height 0 to force sync)
        v_msg = create_version_msg() # Uses Height 100 in original, let's keep it or change?
                                     # If we want to receive blocks, we should be behind?
                                     # Actually, sending getblocks explicitly asks for blocks regardless of height.
        writer.write(v_msg)
        await writer.drain()
        print("Sent VERSION")
        
        GENESIS_HASH = "0b3b4f0815e0324c866dece998eedcd4b3e82ca0afdb5e8f7baef34a007b53e3"
        
        while True:
            header = await reader.read(24)
            if not header:
                print("Connection closed by peer (EOF)")
                break
            
            if len(header) < 24:
                print(f"Partial header: {header.hex()}")
                break
                
            magic, command, length, checksum = struct.unpack('<I12sI4s', header)
            cmd_str = command.split(b'\x00')[0].decode('ascii', errors='ignore')
            print(f"RECV Command: {cmd_str}, Length: {length}")
            
            payload = b''
            if length > 0:
                payload = await reader.readexactly(length)
                # print(f"RECV Payload ({len(payload)} bytes)")
            
            if cmd_str == 'version':
                writer.write(Message('verack', b'').serialize())
                await writer.drain()
                
            elif cmd_str == 'verack':
                print("Handshake Complete. Sending GETBLOCKS...")
                msg = create_getblocks_msg(GENESIS_HASH)
                writer.write(msg)
                await writer.drain()
                
            elif cmd_str == 'getblocks':
                 try:
                     # Parse JSON
                     data = json.loads(payload.decode('utf-8'))
                     locator = data.get('locator', [])
                     print(f"RECV GETBLOCKS with {len(locator)} hashes.")
                     if locator:
                         print(f"Peer's Genesis (Last Locator): {locator[-1]}")
                         print(f"Peer's Tip (First Locator): {locator[0]}")
                         
                         # Use their genesis to ask for blocks
                         peer_genesis = locator[-1]
                         peer_tip = locator[0]
                         print(f"Re-sending GETBLOCKS with Peer's Genesis: {peer_genesis}")
                         # msg = create_getblocks_msg(peer_genesis)
                         # writer.write(msg)
                         # await writer.drain()
                         
                         print(f"Directly requesting Peer's Tip Block: {peer_tip}")
                         req_items = [{"type": "block", "hash": peer_tip}]
                         msg = create_getdata_msg(req_items)
                         writer.write(msg)
                         await writer.drain()
                         
                 except Exception as e:
                     print(f"Failed to parse getblocks: {e}")
                     
            elif cmd_str == 'inv':
                # Parse INV
                # VarInt count
                offset = 0
                count, offset = Message.parse_var_int(payload, offset) # Need to port parse_var_int or use struct
                # Wait, I didn't include parse_var_int in this script properly for reading payload
                # Let's assume JSON for INV?
                # iCSI Code uses JSON for 'inv' payload!
                # Wait, does it?
                # manager.py:481: data = json.loads(payload.decode('utf-8'))
                # YES. iCSI uses JSON for most messages except raw P2P handshake structure?
                # Let's check manager.py parse loop again.
                # It parses HEADER (binary).
                # But 'inv' handler does json.loads(payload).
                
                try:
                    data = json.loads(payload.decode('utf-8'))
                    print(f"INV JSON: {data}")
                    inventory = data.get('inventory', [])
                    if inventory:
                        # Request the first block
                        first_hash = inventory[0]['hash']
                        print(f"Requesting Block {first_hash}...")
                        
                        # Manager.py:532 handles GETDATA. It expects JSON too!
                        # msg = { "type": "getdata", "inventory": [...] }
                        
                        req = {
                            "type": "getdata",
                            "inventory": [{"type": "block", "hash": first_hash}]
                        }
                        json_payload = json.dumps(req).encode('utf-8')
                        out_msg = Message('getdata', json_payload)
                        writer.write(out_msg.serialize())
                        await writer.drain()
                        
                except Exception as e:
                    print(f"Failed to parse INV as JSON: {e}")
                    # Maybe it's binary?
                    print(f"Payload Hex: {payload.hex()}")

            elif cmd_str == 'block':
                print(f"RECV BLOCK! Size: {len(payload)}")
                try:
                    data = json.loads(payload.decode('utf-8'))
                    print("Block JSON Valid.")
                    if 'payload' in data:
                        print(f"Block Payload Length: {len(data['payload'])}")
                except:
                    print("Block JSON Invalid or Binary?")
                    
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(debug_peer())
