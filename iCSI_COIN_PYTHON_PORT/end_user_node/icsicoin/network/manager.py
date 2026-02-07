import asyncio
import logging
print("DEBUG: MANAGER.PY LOADED WITH CHANGES v10-client-fix")
import json
import time
import os
import random
from icsicoin.network.messages import (
    VersionMessage, VerackMessage, Message, MAGIC_VALUE, GetAddrMessage, AddrMessage,
    SignalMessage, RelayMessage, TestMessage
)
from icsicoin.storage.blockstore import BlockStore
from icsicoin.storage.databases import BlockIndexDB, ChainStateDB
from icsicoin.core.primitives import Transaction, Block
from icsicoin.consensus.validation import validate_block, validate_transaction
from icsicoin.core.chain import ChainManager
from icsicoin.core.mempool import Mempool
import binascii

try:
    from aioice import Connection, Candidate
except ImportError:
    Connection = None
    Candidate = None
    # Will fail if used, but safe for initial load


logger = logging.getLogger("NetworkManager")

class NetworkManager:
    def __init__(self, port, bind_address, add_nodes, connect_nodes, rpc_port, data_dir="data"): 
        # Configuration
        self.bind_address = bind_address
        self.port = port
        self.web_port = int(os.getenv('WEB_PORT', 9336)) # Default to 9336 if not set
        self.rpc_port = int(os.getenv('RPC_PORT', rpc_port))
        
        # Storage & Consensus
        # Expand user path
        self.data_dir = os.path.expanduser(data_dir)
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        self.block_store = BlockStore(self.data_dir)
        self.block_Index = BlockIndexDB(self.data_dir) # Typo fix: block_Index -> block_index if needed? No, databases.py usually uses CamelCase or snake? Assume snake based on usage below. Wait.
        # Usage below: self.block_index. 
        # Line 41: self.block_index = BlockIndexDB...
        self.block_index = BlockIndexDB(self.data_dir)
        self.chain_state = ChainStateDB(self.data_dir)
        
        # Brain
        self.mempool = Mempool()
        self.chain_manager = ChainManager(self.block_store, self.block_index, self.chain_state)

        
        self.add_nodes = add_nodes
        self.connect_nodes = connect_nodes
        self.peers = set() # (ip, port)
        self.known_peers = set() # Set of (ip, port)
        self.pending_peers = set() # Set of (host, port) tuples
        self.failed_peers = {} # (ip, port) -> {'timestamp': ts, 'error': str}
        self.peer_stats = {} # (ip, port) -> {'connected_at': ts, 'last_seen': ts}
        self.peer_logs = {} # (ip, port) -> list of strings
        self.tasks = set() # Keep strong references to background tasks
        self.server = None
        self.active_connections = {} # (ip, port) -> writer
        self.ice_connections = {} # (ip, port) -> aioice.Connection
        self.test_msg_count = 0
        self.running = False
        self.stun_ip = os.getenv('STUN_IP', '127.0.0.1')
        self.stun_port = int(os.getenv('STUN_PORT', 3478))
        self.external_ip = None
        self.sync_lock = asyncio.Lock()

    def configure_stun(self, ip, port):
        self.stun_ip = ip
        self.stun_port = int(port)
        logger.info(f"STUN Configuration Updated: {self.stun_ip}:{self.stun_port}")

    def log_peer_event(self, peer, direction, message_type, details=""):
        if peer not in self.peer_logs:
            self.peer_logs[peer] = []
        
        timestamp = time.strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] [{direction}] {message_type}: {details}"
        self.peer_logs[peer].append(log_entry)
        
        # Keep ring buffer of last 50 entries
        if len(self.peer_logs[peer]) > 50:
             self.peer_logs[peer].pop(0)

    async def start(self):
        self.running = True
        # Start listening server
        self.server = await asyncio.start_server(
            self.handle_client, self.bind_address, self.port
        )
        addr = self.server.sockets[0].getsockname()
        logger.info(f"Serving on {addr}")

        # Start background tasks
        t1 = asyncio.create_task(self.maintain_added_nodes())
        self.tasks.add(t1)
        t1.add_done_callback(self.tasks.discard)
        
        t2 = asyncio.create_task(self.discovery_worker())
        self.tasks.add(t2)
        t2.add_done_callback(self.tasks.discard)
        
        # If -connect is specified, we ONLY connect to those nodes
        if self.connect_nodes:
            logger.info(f"Connect-only mode active. Connecting to: {self.connect_nodes}")
            for node in self.connect_nodes:
                 t = asyncio.create_task(self.connect_to_peer(node))
                 self.tasks.add(t)
                 t.add_done_callback(self.tasks.discard)
        else:
             # Normal discovery mode
             pass
             
        # Periodic Peer Refresh (Ask seeds for new peers)
        t3 = asyncio.create_task(self.peer_refresh_worker())
        self.tasks.add(t3)
        t3.add_done_callback(self.tasks.discard)

        # Auto-NAT Discovery
        t4 = asyncio.create_task(self.auto_discovery_worker())
        self.tasks.add(t4)
        t4.add_done_callback(self.tasks.discard)

    async def stop(self):
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("Network manager stopped.")

    async def process_message_loop(self, reader, writer, addr):
        """Unified message processing loop for both inbound and outbound connections."""
        try:
            while self.running:
                # Read Header
                header_data = await reader.readexactly(24)
                if not header_data: break
                # logger.debug(f"Raw Header from {addr}: {binascii.hexlify(header_data)}")
                
                magic, command, length, checksum = Message.parse_header(header_data)
                
                # Read Payload
                if length > 0:
                     payload = await reader.readexactly(length)
                else:
                     payload = b''
                
                if addr in self.peer_stats:
                    self.peer_stats[addr]['last_seen'] = int(time.time())

                if command == 'verack':
                    logger.info(f"Received VERACK from {addr} - Handshake COMPLETE")
                    self.log_peer_event(addr, "RECV", "VERACK", "Handshake COMPLETE")
                    # Send getaddr to initiate discovery
                    writer.write(GetAddrMessage().serialize())
                    await writer.drain()
                    self.log_peer_event(addr, "SENT", "GETADDR", "Initiating discovery")
                    
                    # Start Initial Block Download (IBD)
                    await self.send_getblocks(writer)

                elif command == 'ping':
                    # TODO: Pong
                    pass
                
                elif command == 'getaddr':
                    logger.info(f"Received GETADDR from {addr}")
                    self.log_peer_event(addr, "RECV", "GETADDR", "Peer requested node list")
                    # Send known peers
                    peers_list = []
                    
                    # Helper to check if IP is advertisable (skip internal docker ranges)
                    def is_advertisable(ip):
                        if ip.startswith('127.'): return False
                        if ip == '0.0.0.0': return False
                        return True

                    # Add current connected peers
                    debug_advertised = []
                    
                    # 1. Add SELF if known
                    if self.external_ip:
                         peers_list.append({'ip': self.external_ip, 'port': self.port, 'services': 1, 'timestamp': int(time.time())})
                         debug_advertised.append(f"{self.external_ip}:{self.port} (SELF)")
                    elif self.bind_address != '0.0.0.0':
                         peers_list.append({'ip': self.bind_address, 'port': self.port, 'services': 1, 'timestamp': int(time.time())})
                         debug_advertised.append(f"{self.bind_address}:{self.port} (SELF)")

                    for ip, port in self.peers:
                        if is_advertisable(ip):
                             peers_list.append({'ip': ip, 'port': port, 'services': 1, 'timestamp': int(time.time())})
                             debug_advertised.append(f"{ip}:{port}")
                             
                    # Add discovered known peers (limit to 100)
                    for ip, port in list(self.known_peers)[:100]:
                         if (ip, port) not in self.peers and is_advertisable(ip):
                             peers_list.append({'ip': ip, 'port': port, 'services': 1, 'timestamp': int(time.time())})
                             debug_advertised.append(f"{ip}:{port}")
                    
                    if peers_list:
                        addr_msg = AddrMessage(peers_list)
                        writer.write(addr_msg.serialize())
                        await writer.drain()
                        logger.info(f"Sent ADDR with {len(peers_list)} peers to {addr}: {debug_advertised}")
                        self.log_peer_event(addr, "SENT", "ADDR", f"Sent nodes: {debug_advertised}")

                elif command == 'addr':
                    addresses = AddrMessage.parse(payload)
                     # Create a human-readable list of received nodes
                    received_nodes_str = ", ".join([f"{a['ip']}:{a['port']}" for a in addresses])
                    logger.info(f"Received ADDR from {addr} with {len(addresses)} nodes: [{received_nodes_str}]")
                    self.log_peer_event(addr, "RECV", "ADDR", f"Received {len(addresses)} nodes")
                    for a in addresses:
                        p = (a['ip'], a['port'])
                        # valid port check
                        if p[0] != '0.0.0.0' and p != (self.bind_address, self.port) and p[1] > 0:
                            self.known_peers.add(p)

                elif command == 'relay':
                    # Relay logic: Forward inner payload to target
                    try:
                        relay_msg = RelayMessage.parse(payload)
                        target = (relay_msg.target_ip, relay_msg.target_port)
                        logger.info(f"Received RELAY request from {addr} to {target}")
                        
                        if target in self.active_connections:
                            target_writer = self.active_connections[target]
                            target_writer.write(relay_msg.inner_payload)
                            await target_writer.drain()
                            logger.info(f"Relayed message to {target}")
                            self.log_peer_event(target, "SENT", "RELAY_FWD", f"Forwarded from {addr}")
                        else:
                            logger.warning(f"Cannot relay to {target}: Not connected")
                    except Exception as e:
                        logger.error(f"Relay error: {e}")

                elif command == 'signal':
                    # Signal logic: ICE negotiation message
                    try:
                        signal_msg = SignalMessage.parse(payload)
                        
                        # Use a global or mapped ICE connection. 
                        if Connection: # If aioice imported
                            if signal_msg.sdp:
                                logger.info(f"Processing ICE SDP Offer/Answer from {addr}")
                                # If we don't have a connection, this is an OFFER
                                # For PoC: Create a new connection as Controlled
                                stun_server = ("stun.l.google.com", 19302)
                                conn = Connection(ice_controlling=False, components=1, stun_server=stun_server)
                                await conn.set_remote_sdp(signal_msg.sdp)
                                
                                # Send Answer
                                await conn.gather_candidates()
                                answer_sdp = conn.local_sdp
                                
                                # Reply via Relay using Source Info from Signal
                                target_ip = signal_msg.source_ip
                                target_port = signal_msg.source_port
                                
                                if target_ip != '0.0.0.0' and target_port > 0:
                                    
                                    # Find the Relay connection (the socket 'addr' came from aka Seed)
                                    if addr in self.active_connections:
                                        writer = self.active_connections[addr]
                                        
                                        # Response Signal
                                        resp_signal = SignalMessage(target_ip=target_ip, target_port=target_port, 
                                                                    source_ip=self.bind_address, source_port=self.port,
                                                                    sdp=answer_sdp)
                                        
                                        # Relay
                                        relay = RelayMessage(target_ip=target_ip, target_port=target_port, inner_payload=resp_signal.serialize())
                                        writer.write(relay.serialize())
                                        await writer.drain()
                                        logger.info(f"Sent ICE Answer to {target_ip}:{target_port} via Relay")
                                    else:
                                        logger.warning("No active connection to Relay to send Answer")
                                else:
                                    logger.warning("Cannot reply to Signal: Source Unknown")

                            if signal_msg.candidate:
                                logger.info(f"Received ICE Candidate: {signal_msg.candidate}")
                        
                        self.log_peer_event(addr, "RECV", "SIGNAL", "Received ICE Signal")
                    except Exception as e:
                        logger.error(f"Signal error: {e}")
                
                elif command == 'test':
                    try:
                        test_msg = TestMessage.parse(payload)
                        self.test_msg_count += 1
                        logger.info(f"Received TEST MESSAGE from {addr}: {test_msg.content}")
                        self.log_peer_event(addr, "RECV", "TEST_MSG", f"Content: {test_msg.content}")
                    except Exception as e:
                        logger.error(f"Test message error: {e}")

                # --- Phase 4: JSON Bridge Handlers ---
                elif command == 'inv':
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        inventory = data.get('inventory', [])
                        logger.info(f"Received INV from {addr} with {len(inventory)} items")
                        
                        to_get = []
                        for item in inventory:
                            if item['type'] == 'block':
                                # Check if we have it
                                if not self.block_index.get_block_info(item['hash']):
                                    to_get.append(item)
                        
                        if to_get:
                            # Send getdata
                            msg = {
                                "type": "getdata",
                                "inventory": to_get
                            }
                            json_payload = json.dumps(msg).encode('utf-8')
                            out_msg = Message('getdata', json_payload)
                            writer.write(out_msg.serialize())
                            await writer.drain()
                            logger.info(f"Sent GETDATA for {len(to_get)} items to {addr}")

                    except Exception as e:
                        logger.error(f"INV error: {e}")

                elif command == 'getdata':
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        inventory = data.get('inventory', [])
                        logger.info(f"Received GETDATA from {addr}")
                        
                        for item in inventory:
                            if item['type'] == 'block':
                                # Retrieve block (logic deferred to finding it in blockstore)
                                # For Phase 4, we assume we rely on BlockIndex to find it
                                info = self.block_index.get_block_info(item['hash'])
                                if info:
                                    raw_block = self.block_store.read_block(info['file_num'], info['offset'], info['length'])
                                    # Encode to hex
                                    block_hex = binascii.hexlify(raw_block).decode('ascii')
                                    msg = {
                                        "type": "block",
                                        "payload": block_hex
                                    }
                                    json_payload = json.dumps(msg).encode('utf-8')
                                    out_msg = Message('block', json_payload)
                                    writer.write(out_msg.serialize())
                                    await writer.drain()
                                    logger.info(f"Sent BLOCK {item['hash']} to {addr}")
                    except Exception as e:
                        logger.error(f"GETDATA error: {e}")

                elif command == 'block':
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        block_hex = data.get('payload')
                        if block_hex:
                            block_bytes = binascii.unhexlify(block_hex)
                            # Deserialize
                            import io
                            f = io.BytesIO(block_bytes)
                            block = Block.deserialize(f)
                            
                            # Process via ChainManager
                            if self.chain_manager.process_block(block):
                                # Relay logic (simple flood)
                                inv_msg = {
                                    "type": "inv", 
                                    "inventory": [{"type": "block", "hash": block.get_hash().hex()}]
                                }
                                json_payload = json.dumps(inv_msg).encode('utf-8')
                                out_m = Message('inv', json_payload)
                                
                                # Broadcast to others
                                for peer_addr, peer_writer in self.active_connections.items():
                                    if peer_addr != addr: 
                                        try:
                                            peer_writer.write(out_m.serialize())
                                            await peer_writer.drain()
                                        except: pass
                                logger.info("Relayed BLOCK INV to peers")
                            else:
                                pass # Invalid or orphan (already logged by ChainManager)
                                
                    except Exception as e:
                        logger.error(f"BLOCK error: {e}")
                        import traceback
                        traceback.print_exc()

                elif command == 'tx':
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        tx_hex = data.get('payload')
                        if tx_hex:
                            tx_bytes = binascii.unhexlify(tx_hex)
                            import io
                            f = io.BytesIO(tx_bytes)
                            tx = Transaction.deserialize(f)
                            
                            # Validate & Add to Mempool
                            if validate_transaction(tx):
                                if self.mempool.add_transaction(tx):
                                    logger.info(f"Received Valid TX: {tx.get_hash().hex()}")
                                    
                                    # Relay 
                                    inv_msg = {
                                        "type": "inv", 
                                        "inventory": [{"type": "tx", "hash": tx.get_hash().hex()}]
                                    }
                                    json_payload = json.dumps(inv_msg).encode('utf-8')
                                    out_m = Message('inv', json_payload)
                                    for peer_addr, peer_writer in self.active_connections.items():
                                        if peer_addr != addr:
                                            try:
                                                peer_writer.write(out_m.serialize())
                                                await peer_writer.drain()
                                            except: pass
                                    # Added return to fix logging issue? No.
                            else:
                                logger.warning(f"Received INVALID TX from {addr}")
                    except Exception as e:
                        logger.error(f"TX error: {e}")

                elif command == 'getblocks':
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        locator = data.get('locator', [])
                        logger.info(f"Received GETBLOCKS from {addr} with {len(locator)} locators: {locator}")

                        # Find common ancestor
                        start_hash = None
                        start_info = None
                        for h in locator:
                            info = self.block_index.get_block_info(h)
                            if info:
                                start_hash = h
                                start_info = info
                                break
                        
                        if start_hash and start_info:
                            logger.info(f"Found common ancestor {start_hash} with {addr}")
                            
                            # Valid Ancestor Found
                            start_height = start_info['height']
                            best_info = self.block_index.get_best_block()
                            current_height = best_info['height'] if best_info else 0
                            
                            logger.info(f"SYNC LOGIC: Start Hash {start_hash} (Height {start_height}), Current Tip Height {current_height}")

                            inv_items = []
                            # Lock to prevent race condition during sync
                            # (Optional, but good practice)
                            end_height = min(current_height, start_height + 500)
                            for h_idx in range(start_height + 1, end_height + 1):
                                b_hash = self.chain_manager.get_block_hash(h_idx)
                                if b_hash:
                                    inv_items.append({"type": "block", "hash": b_hash})
                                else:
                                    logger.warning(f"SYNC WARNING: Block hash not found for height {h_idx}")
                            
                            if inv_items:
                                    inv_msg = {
                                        "type": "inv", 
                                        "inventory": inv_items
                                    }
                                    json_payload = json.dumps(inv_msg).encode('utf-8')
                                    out_msg = Message('inv', json_payload)
                                    writer.write(out_msg.serialize())
                                    await writer.drain()
                                    logger.info(f"Sent INV with {len(inv_items)} blocks to {addr}")
                        else:
                             pass # No common ancestor, ignore

                    except Exception as e:
                        logger.error(f"GETBLOCKS error: {e}")
                
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}")
            self.log_peer_event(addr, "ERR", "EXCEPTION", str(e))
        finally:
            logger.info(f"Closing connection to {addr}")
            self.log_peer_event(addr, "XXX", "DISCONNECT", "Connection closed")
            try:
                writer.close()
                await writer.wait_closed()
            except: pass
            
            # Try removing both variants based on addr ip/port
            self.peers.discard(addr)
            
            # Also cleanup from active connections if present
            if addr in self.active_connections:
                 del self.active_connections[addr]
            
            # If we tracked it with a different port (e.g. listening port), we might need to clean that too.
            # But process_message_loop takes 'addr' as the primary key.
            # In handle_client, 'addr' is the ephemeral socket address.
            # In connect_to_peer, 'addr' is the target address (listening port).
            
            # If handle_client passed ephemeral addr, we should clean up the mapped listening port too if known.
            # But handle_client logic did that in its finally block. 
            # We can leave that specific cleanup to the caller if needed, or try to be smart here.
            # For now, let's keep it simple: cleanup passed 'addr'.
            pass

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        logger.info(f"New incoming connection from {addr}")
        self.peer_stats[addr] = {'connected_at': int(time.time()), 'last_seen': int(time.time())}
        self.log_peer_event(addr, "IN", "CONNECTION", "Established incoming connection")
        
        # Temp var to store the actual listening port if provided
        remote_listening_port = addr[1]

        try:
            # 1. Expect Version Message
            # Read Header
            header_data = await reader.read(24)
            if len(header_data) < 24:
                return

            magic, command, length, checksum = Message.parse_header(header_data)
            if magic != MAGIC_VALUE:
                 logger.warning(f"Invalid magic from {addr}")
                 return
            
            payload = await reader.read(length)
            
            if command == 'version':
                logger.info(f"Received VERSION from {addr}")
                
                # Parse Version Message to get listening port
                try:
                    version_msg = VersionMessage.parse(payload)
                    remote_listening_port = version_msg.addr_from[2]
                    logger.info(f"Peer {addr[0]} reports listening on port {remote_listening_port}")
                except Exception as e:
                    logger.error(f"Failed to parse Version message: {e}")
                
                self.log_peer_event(addr, "RECV", "VERSION", f"Handshake initiated (Port {remote_listening_port})")
                
                # 2. Send Version
                my_version = VersionMessage()
                writer.write(my_version.serialize())
                await writer.drain()
                self.log_peer_event(addr, "SENT", "VERSION", "")
                
                # 3. Send Verack
                my_verack = VerackMessage()
                writer.write(my_verack.serialize())
                await writer.drain()
                self.log_peer_event(addr, "SENT", "VERACK", "")
                
            # 4. Expect Verack
            # (Simplification: We expect the next message to be verack, but tcp stream might bundle it)
            
            # Register peer using the reported listening port (if valid)
            # Prevent registering 0 or invalid ports
            # Register peer using the reported listening port (if valid)
            if remote_listening_port > 0:
                self.peers.add((addr[0], remote_listening_port))
                logger.info(f"Registered peer: {addr[0]}:{remote_listening_port}") 
            else:
                 self.peers.add(addr) 
                 logger.info(f"Registered peer (fallback): {addr}")
            
            # Register active connection
            self.active_connections[addr] = writer
            if remote_listening_port > 0:
                 self.active_connections[(addr[0], remote_listening_port)] = writer
            
            # Delegate to unified loop
            if remote_listening_port > 0:
                 self.active_connections[(addr[0], remote_listening_port)] = writer
            
            await self.process_message_loop(reader, writer, addr)
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}")
            self.log_peer_event(addr, "ERR", "EXCEPTION", str(e))
        finally:
            logger.info(f"Closing connection to {addr}")
            self.log_peer_event(addr, "XXX", "DISCONNECT", "Connection closed")
            writer.close()
            await writer.wait_closed()
            # Try removing both variants
            self.peers.discard(addr)
            if 'remote_listening_port' in locals() and remote_listening_port > 0:
                 self.peers.discard((addr[0], remote_listening_port))
                 if (addr[0], remote_listening_port) in self.active_connections:
                     del self.active_connections[(addr[0], remote_listening_port)]
                  
                 # Record as disconnected/failed so it appears in UI
                 self.failed_peers[(addr[0], remote_listening_port)] = {
                     'timestamp': int(time.time()), 
                     'error': 'Disconnected (Incoming)'
                 }
            else:
                 # Record ephemeral if handshake failed
                 self.failed_peers[addr] = {
                     'timestamp': int(time.time()), 
                     'error': 'Disconnected (Handshake Incomplete)'
                 }

    def remove_failed_peer(self, ip, port):
        key = (ip, port)
        if key in self.failed_peers:
            del self.failed_peers[key]
            
    def reset_data(self):
        self.peers.clear()
        self.known_peers.clear()
        self.pending_peers.clear()
        self.failed_peers.clear()
        self.peer_stats.clear()
        self.peer_logs.clear()
        logger.info("Experimental: Network data reset requested by user.")


    async def maintain_added_nodes(self):
        """Attempts to maintain connections to nodes specified by -addnode"""
        while self.running:
            for node in self.add_nodes:
                 # Check if we are already connected (simplistic check for now)
                 connected = any(p[0] == node for p in self.peers) # assuming node is ip string
                 # Better check needed for ip:port
                 host = node
                 port = 9333
                 if ":" in node:
                     host, port = node.split(":")
                     port = int(port)
                     
                 # Check if connected (either by list check or tuple check)
                 # Since we now store (ip, listening_port), this check is more robust
                 connected = (host, port) in self.peers
                 
                 if not connected:
                     t = asyncio.create_task(self.connect_to_peer(node))
                     self.tasks.add(t)
                     t.add_done_callback(self.tasks.discard)
            
            # Retry every 60 seconds
            await asyncio.sleep(60)

    async def discovery_worker(self):
        """Background task to discovery and connect to new peers"""
        while self.running:
            # If we have few peers and known peers available
            if len(self.peers) < 8 and self.known_peers:
                 # Try to connect to a random known peer
                 peer = random.choice(list(self.known_peers))
                 
                 # Check if already connected
                 if peer not in self.peers:
                      logger.info(f"Discovery: Attempting to connect to {peer}")
                      t = asyncio.create_task(self.connect_to_peer(f"{peer[0]}:{peer[1]}"))
                      self.tasks.add(t)
                      t.add_done_callback(self.tasks.discard)
            
            await asyncio.sleep(10)

    async def peer_refresh_worker(self):
        """Periodically requests updated peer lists from connected nodes"""
        while self.running:
            try:
                if self.active_connections:
                    # logger.info("Refreshing peer lists...")
                    for writer in list(self.active_connections.values()):
                        try:
                            writer.write(GetAddrMessage().serialize())
                            await writer.drain()
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"Refresh error: {e}")
            
            await asyncio.sleep(30) # Poll every 30 seconds

    async def announce_self(self):
        """Broadcasts our own external IP to all connected peers"""
        if not self.external_ip:
            return 
            
        logger.info(f"Announcing SELF ({self.external_ip}:{self.port}) to network...")
        
        # Create AddrMessage with just us
        myself = [{'ip': self.external_ip, 'port': self.port, 'services': 1, 'timestamp': int(time.time())}]
        addr_msg = AddrMessage(myself)
        serialized_msg = addr_msg.serialize()
        
        count = 0
        if self.active_connections:
            for writer in list(self.active_connections.values()):
                try:
                    writer.write(serialized_msg)
                    await writer.drain()
                    count += 1
                except Exception:
                    pass
        
        logger.info(f"Announced SELF to {count} peers")

    async def send_getblocks(self, peer_writer):
        """Sends getblocks message to peer with our chain tip locator"""
        try:
            # Create locator: Current Tip + Genesis (to always find common ground)
            best_info = self.block_index.get_best_block()
            tip_hash = best_info['block_hash'] if best_info else self.chain_manager.genesis_block.get_hash().hex()
            
            genesis_hash = self.chain_manager.genesis_block.get_hash().hex()
            
            locator = [tip_hash]
            if tip_hash != genesis_hash:
                locator.append(genesis_hash)
            
            msg = {
                "type": "getblocks",
                "locator": locator
            }
            json_payload = json.dumps(msg).encode('utf-8')
            out_msg = Message('getblocks', json_payload)
            
            peer_writer.write(out_msg.serialize())
            await peer_writer.drain()
            logger.info(f"Sent GETBLOCKS (Locator: {locator}) to peer")
        except Exception as e:
            logger.error(f"Error sending getblocks: {e}")

    async def announce_new_block(self, block):
        """Broadcasts a new block inventory to all peers"""
        block_hash = block.get_hash().hex()
        logger.info(f"Announcing new block {block_hash} to peers...")
        
        inv_msg = {
            "type": "inv", 
            "inventory": [{"type": "block", "hash": block_hash}]
        }
        json_payload = json.dumps(inv_msg).encode('utf-8')
        out_msg = Message('inv', json_payload)
        
        count = 0
        for peer_addr, peer_writer in self.active_connections.items():
            try:
                peer_writer.write(out_msg.serialize())
                await peer_writer.drain()
                count += 1
            except Exception:
                pass
        
        logger.info(f"Announced block {block_hash} to {count} peers")

    async def auto_discovery_worker(self):
        """Attempts to resolve public IP via STUN on startup"""
        logger.info("Starting Auto-NAT Discovery...")
        retry_delay = 10
        while self.running:
            # We check periodically, but less often if we already have an IP
            # (Though IP might change, so re-checking is good)
            
            current_ip = self.external_ip
            stun_ip = getattr(self, 'stun_ip', os.getenv('STUN_IP', '127.0.0.1'))
            stun_port = getattr(self, 'stun_port', int(os.getenv('STUN_PORT', 3478)))
            
            # Only log if we don't have an IP or debug is on, to reduce noise
            if not current_ip:
                logger.info(f"Auto-Discovery: Testing STUN against {stun_ip}:{stun_port}...")
            
            try:
                success, msg = await self.test_stun_connection(stun_ip, stun_port)
                
                if success:
                    if not current_ip:
                         logger.info(f"Auto-Discovery Successful: {msg}")
                         # IP found! Announce ourselves to all connected peers immediately
                         await self.announce_self()
                    # self.external_ip is set inside test_stun_connection
                    retry_delay = 300 # Re-check every 5 mins
                else:
                    if not current_ip:
                        logger.warning(f"Auto-Discovery Failed: {msg}. Retrying in {retry_delay}s")
                    retry_delay = min(retry_delay * 2, 300) # Backoff
            except Exception as e:
                logger.error(f"Auto-Discovery Exception: {e}")
                
            await asyncio.sleep(retry_delay)

    async def connect_to_peer(self, node_address):
        host = node_address
        port = 9333 # Default port
        
        if ":" in node_address:
            host, port = node_address.split(":")
            port = int(port)
        
        target = (host, port)
        # Fix self-connection loop
        if self.external_ip and host == self.external_ip and port == self.port:
            logger.info(f"Skipping connection to SELF (External IP match): {host}:{port}")
            return
        if host in ('127.0.0.1', 'localhost', '0.0.0.0') and port == self.port:
            logger.info(f"Skipping connection to SELF (Localhost match): {host}:{port}")
            return
        # Avoid duplicate connection attempts
        if target in self.peers or target in self.pending_peers:
            return 
        
        # Also check if we are connected to this host on any port? 
        # No, because host might have multiple nodes? Unlikely for P2P but ok.

        self.pending_peers.add(target)
        # Clear previous failure if any
        if target in self.failed_peers:
            del self.failed_peers[target]
            
        logger.info(f"Attempting to connect to peer: {host}:{port}")
        self.log_peer_event(target, "OUT", "CONNECT", "Attempting connection...")
        
        try:
            reader, writer = await asyncio.open_connection(host, port)
            addr = writer.get_extra_info('peername')
            logger.info(f"TCP Connected to {addr}")
            self.log_peer_event(addr, "OUT", "CONNECT", "TCP Connection Established")
            
            # Update stats
            self.peer_stats[addr] = {'connected_at': int(time.time()), 'last_seen': int(time.time())}

            # 1. Send Version
            # We must advertise our own listening port so the remote node knows how to dial us back.
            # Using external_ip if available, otherwise 127.0.0.1 placeholder
            my_ip = self.external_ip if self.external_ip else '127.0.0.1'
            version_msg = VersionMessage(addr_from_port=self.port, addr_from_ip=my_ip)
            writer.write(version_msg.serialize())
            await writer.drain()
            logger.info(f"Sent VERSION to {addr}")
            self.log_peer_event(addr, "SENT", "VERSION", "Handshake initiated")
            
            # Recv Version
            header_data = await reader.read(24)
            if len(header_data) < 24: return 
            
            magic, command, length, checksum = Message.parse_header(header_data)
            if command == 'version':
                payload = await reader.read(length)
                logger.info(f"Received VERSION from {addr}")
                self.log_peer_event(addr, "RECV", "VERSION", "")
                
                # Send Verack
                writer.write(VerackMessage().serialize())
                await writer.drain()
                logger.info(f"Sent VERACK to {addr}")
                self.log_peer_event(addr, "SENT", "VERACK", "")
            
            # Recv Verack
            header_data = await reader.read(24)
            if len(header_data) < 24: return
            
            magic, command, length, checksum = Message.parse_header(header_data)
            if command == 'verack':
                 logger.info(f"Received VERACK from {addr} - Handshake COMPLETE")
                 self.log_peer_event(addr, "RECV", "VERACK", "Handshake COMPLETE")
                 # Send GetAddr
                 writer.write(GetAddrMessage().serialize())
                 await writer.drain()
                 self.log_peer_event(addr, "SENT", "GETADDR", "Initiating discovery")
                 
                 # Start Initial Block Download (IBD)
                 await self.send_getblocks(writer)
            
            # Outbound connections: we know the target port because we dialed it.
            # So register 'target' as the peer, not the random internal source port.
            self.peers.add(target)
            self.active_connections[target] = writer
            
            # Remove from pending once connected
            self.pending_peers.discard(target)
            
            # Delegate to unified loop
            # Here 'target' is (ip, port) of the listener, which is what we want for stats/logs.
            await self.process_message_loop(reader, writer, target)

        except Exception as e:
            logger.warning(f"Failed to connect to {host}:{port}: {e}")
            
            # Try ICE P2P if TCP failed (NAT traversal attempt)
            if Connection and self.active_connections:
                logger.info(f"Attempting ICE P2P to {host}:{port} via {len(self.active_connections)} relays")
                for relay_addr in list(self.active_connections.keys()):
                     # Start ICE task
                     asyncio.create_task(self.init_ice_connection(host, port, remote_via_tcp=relay_addr))

            self.log_peer_event(target, "ERR", "EXCEPTION", str(e))
            self.peers.discard((host, port))
            # Record failure
            self.failed_peers[target] = {'timestamp': int(time.time()), 'error': str(e)}
        finally:
            self.pending_peers.discard(target)

    async def init_ice_connection(self, target_ip, target_port, remote_via_tcp=None):
        """Initiates ICE connection to a target."""
        from aioice import Connection, Candidate
        logger.info(f"Initiating ICE to {target_ip}:{target_port}")
        
        # Configurable STUN server (defaults to localhost for local testing)
        stun_ip = getattr(self, 'stun_ip', os.getenv('STUN_IP', '127.0.0.1'))
        stun_port = getattr(self, 'stun_port', int(os.getenv('STUN_PORT', 3478)))
        stun_server = (stun_ip, stun_port) 
        
        logger.info(f"Using STUN Server: {stun_ip}:{stun_port}") 
        
        connection = Connection(ice_controlling=True, components=1, stun_server=stun_server)
        
        # Handle local candidates
        async def on_candidate(c):
            logger.info(f"Gathered local candidate: {c}")
            # Send to peer via Relay (we need a path)
            # We use the 'remote_via_tcp' (the seed node we are connected to) to relay to target
            if remote_via_tcp and remote_via_tcp in self.active_connections:
                writer = self.active_connections[remote_via_tcp]
                # Wrap candidate in SignalMessage
                c_str = c.to_sdp()
                signal = SignalMessage(target_ip=target_ip, target_port=target_port, candidate=c_str)
                # Wrap in RelayMessage
                relay = RelayMessage(target_ip=target_ip, target_port=target_port, inner_payload=signal.serialize())
                writer.write(relay.serialize())
                await writer.drain()
        
        connection.on_candidate = on_candidate
        
        await connection.gather_candidates()
        
        # Send Offer
#         sdp = connection.local_sdp
#         if remote_via_tcp and remote_via_tcp in self.active_connections:
#                 writer = self.active_connections[remote_via_tcp]
#                 signal = SignalMessage(target_ip=target_ip, target_port=target_port, sdp=sdp)
#                 relay = RelayMessage(target_ip=target_ip, target_port=target_port, inner_payload=signal.serialize())
#                 writer.write(relay.serialize())
#                 await writer.drain()
#                 logger.info("Sent ICE w/ Offer via Relay")
        logger.warning("ICE Offer disabled: aioice Connection object missing local_sdp attribute. Update required for full ICE support.")

        # Wait for connection
        # Store this connection somewhere to handle incoming answers?
        key = (target_ip, target_port)
        self.ice_connections[key] = connection 
        self.log_peer_event(key, "ICE", "INIT", "ICE Connection Initiated")

        # Cleanup callback
        async def remove_ice():
             if key in self.ice_connections:
                 del self.ice_connections[key]
                 
        # For this PoC, we rely on the loop handling signals to update this connection
        # But we need a reference.
        return connection

    async def send_test_message(self, target_ip, target_port, content="Ping!"):
        logger.info(f"Sending Test Message to {target_ip}:{target_port}")
        
        # 1. Check active TCP connections (Direct)
        writer = None
        if (target_ip, target_port) in self.active_connections:
            writer = self.active_connections[(target_ip, target_port)]
        elif (target_ip, target_port) in self.ice_connections:
            # Send via ICE
            try:
                msg = TestMessage(content)
                conn = self.ice_connections[(target_ip, target_port)]
                # component 1 is usually RTP/Data
                await conn.send(msg.serialize()) 
                logger.info("Sent Test Message via ICE P2P")
                self.log_peer_event((target_ip, target_port), "SENT", "TEST_MSG (ICE)", content)
                return True
            except Exception as e:
                 logger.error(f"Failed to send via ICE: {e}")
                 return False
            
        if writer:
            msg = TestMessage(content)
            writer.write(msg.serialize())
            await writer.drain()
            logger.info("Sent Test Message via TCP")
            self.log_peer_event((target_ip, target_port), "SENT", "TEST_MSG", content)
            return True
        else:
            logger.warning(f"No active connection to {target_ip}:{target_port} to send test message")
            return False

    async def test_stun_connection(self, stun_ip, stun_port):
        """Tests connectivity to a STUN server by attempting to gather candidates."""
        from aioice import Connection
        logger.info(f"Testing STUN Connection to {stun_ip}:{stun_port}")
        try:
             # Create a temporary connection just for gathering
             stun_server = (stun_ip, int(stun_port))
             c = Connection(ice_controlling=True, components=1, stun_server=stun_server)
             
             # Capture local candidates
             candidates = []
             async def on_candidate(cand):
                 candidates.append(cand)
             
             c.on_candidate = on_candidate # Hook not always reliable in gathering phase of aioice 0.6+, but let's try standard gather
             
             await c.gather_candidates()
             
             # Check results
             found_srflx = False
             public_ip = None
             
             for cand in c.local_candidates:
                 if cand.type == 'srflx':
                     found_srflx = True
                     public_ip = cand.host
                     break
            
             await c.close()
             
             if found_srflx:
                 self.external_ip = public_ip
                 logger.info(f"STUN Test Success. Public IP: {public_ip}")
                 return True, f"Success! Public IP: {public_ip}"
             elif c.local_candidates:
                 # We gathered candidates (host), but no srflx. NAT might be blocking UDP or STUN down.
                 return False, f"Reachable, but no Public IP found. (Candidates: {len(c.local_candidates)} host only)"
             else:
                 return False, "Failed. No candidates gathered."
                 
        except Exception as e:
            logger.error(f"STUN Test Exception: {e}")
            return False, str(e)
