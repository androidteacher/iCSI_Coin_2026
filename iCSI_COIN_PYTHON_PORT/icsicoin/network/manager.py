import asyncio
import logging
import random
import time
from icsicoin.network.messages import VersionMessage, VerackMessage, Message, MAGIC_VALUE, GetAddrMessage, AddrMessage

logger = logging.getLogger("NetworkManager")

class NetworkManager:
    def __init__(self, port, bind_address, add_nodes, connect_nodes):
        self.port = port
        self.bind_address = bind_address
        self.add_nodes = add_nodes
        self.connect_nodes = connect_nodes
        self.peers = set()
        self.known_peers = set() # Set of (ip, port)
        self.pending_peers = set() # Set of (host, port) tuples
        self.failed_peers = {} # (ip, port) -> {'timestamp': ts, 'error': str}
        self.peer_stats = {} # (ip, port) -> {'connected_at': ts, 'last_seen': ts}
        self.peer_logs = {} # (ip, port) -> list of strings
        self.tasks = set() # Keep strong references to background tasks
        self.server = None
        self.running = False

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

    async def stop(self):
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("Network manager stopped.")

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
            if remote_listening_port > 0:
                self.peers.add((addr[0], remote_listening_port))
            else:
                 self.peers.add(addr) # Fallback
            
            while self.running:
                # Read Header
                header_data = await reader.read(24)
                if not header_data:
                    break
                if len(header_data) < 24:
                    break # Incomplete header
                    
                magic, command, length, checksum = Message.parse_header(header_data)
                
                # Read Payload
                if length > 0:
                     payload = await reader.read(length)
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
                        # Relaxed check for Docker networking
                        # if ip.startswith('172.16.') or ip.startswith('172.17.') or ip.startswith('172.18.') or ip.startswith('172.19.') or ip.startswith('172.20.') or ip.startswith('172.21.'): return False 
                        if ip == '0.0.0.0': return False
                        return True

                    # Add current connected peers
                    for ip, port in self.peers:
                        if is_advertisable(ip):
                             peers_list.append({'ip': ip, 'port': port, 'services': 1, 'timestamp': int(time.time())})
                             
                    # Add discovered known peers (limit to 100)
                    for ip, port in list(self.known_peers)[:100]:
                         if (ip, port) not in self.peers and is_advertisable(ip):
                             peers_list.append({'ip': ip, 'port': port, 'services': 1, 'timestamp': int(time.time())})
                    
                    if peers_list:
                        addr_msg = AddrMessage(peers_list)
                        writer.write(addr_msg.serialize())
                        await writer.drain()
                        logger.info(f"Sent ADDR with {len(peers_list)} peers to {addr}")
                        self.log_peer_event(addr, "SENT", "ADDR", f"Sent {len(peers_list)} nodes")

                elif command == 'addr':
                    addresses = AddrMessage.parse(payload)
                    logger.info(f"Received ADDR from {addr} with {len(addresses)} nodes")
                    self.log_peer_event(addr, "RECV", "ADDR", f"Received {len(addresses)} nodes")
                    for a in addresses:
                        peer = (a['ip'], a['port'])
                        # Basic validity check (not self, not 0.0.0.0)
                        if peer[0] != '0.0.0.0' and peer != (self.bind_address, self.port):
                            self.known_peers.add(peer)
                
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

    async def connect_to_peer(self, node_address):
        host = node_address
        port = 9333 # Default port
        
        if ":" in node_address:
            host, port = node_address.split(":")
            port = int(port)
        
        target = (host, port)
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
            version_msg = VersionMessage()
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
            
            # Outbound connections: we know the target port because we dialed it.
            # So register 'target' as the peer, not the random internal source port.
            self.peers.add(target)
            
            # Remove from pending once connected
            self.pending_peers.discard(target)
            
            # Keep connection alive & listen for messages
            while self.running:
                header_data = await reader.read(24)
                if not header_data: break
                
                magic, command, length, checksum = Message.parse_header(header_data)
                
                # Read Payload
                if length > 0:
                     payload = await reader.read(length)
                else:
                     payload = b''
                
                if addr in self.peer_stats:
                    self.peer_stats[addr]['last_seen'] = int(time.time())
                
                # Update stats for target too if differ
                if target in self.peer_stats:
                     self.peer_stats[target]['last_seen'] = int(time.time())


                if command == 'getaddr':
                    self.log_peer_event(addr, "RECV", "GETADDR", "Peer requested node list")
                    # Reply with peers
                    peers_list = []
                    
                    def is_advertisable(ip):
                        if ip.startswith('127.'): return False
                        # Relaxed check for Docker networking
                        # if ip.startswith('172.16.') or ip.startswith('172.17.') or ip.startswith('172.18.') or ip.startswith('172.19.') or ip.startswith('172.20.') or ip.startswith('172.21.'): return False 
                        if ip == '0.0.0.0': return False
                        return True

                    for p_ip, p_port in self.peers:
                         if is_advertisable(p_ip):
                            peers_list.append({'ip': p_ip, 'port': p_port, 'services': 1, 'timestamp': int(time.time())})
                    
                    if peers_list:
                        writer.write(AddrMessage(peers_list).serialize())
                        await writer.drain()
                        self.log_peer_event(addr, "SENT", "ADDR", f"Sent {len(peers_list)} nodes")
                        
                elif command == 'addr':
                    addresses = AddrMessage.parse(payload)
                    logger.info(f"Received ADDR from {addr} with {len(addresses)} nodes")
                    self.log_peer_event(addr, "RECV", "ADDR", f"Received {len(addresses)} nodes")
                    for a in addresses:
                        p = (a['ip'], a['port'])
                        if p != (self.bind_address, self.port):
                             self.known_peers.add(p)
                             
                elif command == 'ping':
                    # TODO: Pong
                    pass

        except Exception as e:
            logger.warning(f"Failed to connect to {host}:{port}: {e}")
            self.log_peer_event(target, "ERR", "EXCEPTION", str(e))
            self.peers.discard((host, port))
            # Record failure
            self.failed_peers[target] = {'timestamp': int(time.time()), 'error': str(e)}
        finally:
             self.pending_peers.discard(target)
