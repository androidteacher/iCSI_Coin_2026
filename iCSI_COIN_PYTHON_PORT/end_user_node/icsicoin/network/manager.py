import asyncio
import logging
import json
import time
import os
import io
import random
from icsicoin.network.messages import (
    VersionMessage, VerackMessage, Message, MAGIC_VALUE, GetAddrMessage, AddrMessage,
    SignalMessage, RelayMessage, TestMessage, PingMessage, PongMessage
)
from icsicoin.storage.blockstore import BlockStore
from icsicoin.storage.databases import BlockIndexDB, ChainStateDB
from icsicoin.core.primitives import Transaction, Block
from icsicoin.consensus.validation import validate_block, validate_transaction
from icsicoin.core.chain import ChainManager
from icsicoin.core.mempool import Mempool
from icsicoin.network.multicast import MulticastBeacon, get_local_ip
from icsicoin.network.scanner import LANScanner
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
        self.mempool = Mempool(self.data_dir)
        self.chain_manager = ChainManager(self.block_store, self.block_index, self.chain_state)

        
        self.add_nodes = add_nodes if add_nodes else []
        self.connect_nodes = connect_nodes
        self.peers = set() # (ip, port)
        self.known_peers = set() # Set of (ip, port)
        self.pending_peers = set() # Set of (host, port) tuples
        self.failed_peers = {} # (ip, port) -> {'timestamp': ts, 'error': str}
        self.peer_stats = {} # (ip, port) -> {'connected_at': ts, 'last_seen': ts}
        self.peer_logs = {} # (ip, port) -> list of strings
        self.peer_logs = {} # (ip, port) -> list of strings
        self.peer_last_log_time = {} # (ip, port) -> timestamp (float)
        self.peer_last_heard = {} # (ip, port) -> timestamp (float) - Tracks INCOMING data only
        self.tasks = set() # Keep strong references to background tasks
        self.server = None
        self.active_connections = {} # (ip, port) -> writer
        self.ice_connections = {} # (ip, port) -> aioice.Connection
        self.test_msg_count = 0
        self.running = False
        self.stun_ip = os.getenv('STUN_IP', '127.0.0.1')
        self.stun_port = int(os.getenv('STUN_PORT', 3478))
        self.external_ip = None
        self.local_ip = get_local_ip()
        self.discovered_seed = None  # IP of seed discovered via multicast
        self.sync_lock = asyncio.Lock()

        # Multicast discovery beacon
        # Seed nodes advertise ports 9333-9335; end user nodes advertise nothing
        seed_ports = []
        if self.port in (9333, 9334, 9335):
            seed_ports = [9333, 9334, 9335]
        self.multicast_beacon = MulticastBeacon(
            p2p_port=self.port,
            seed_ports=seed_ports,
            on_discover=self._on_multicast_discover
        )
        
        self.lan_scanner = LANScanner(port=9333) # Default scanning port
        self.last_lan_scan = 0

        # Debugging / Logging state
        self.peer_logs = {} # Ring buffer of logs per peer
        self.peer_last_log_time = {} # For sorting
        
        # Debounce state
        self.requested_orphans = {} # {parent_hash: timestamp} - Debounce for orphan requests
        
        # Sync Optimization: Single Download Peer
        self.sync_peer = None # (ip, port) of the current primary sync partner
        self.last_sync_peer_switch = 0
        self.last_block_received_time = 0 # Initialize to 0
        
        # Beggar System
        self.beggar_list = {} # {address: {'first_seen': ts, 'last_seen': ts, 'source_ip': ip}}
        self.active_beg = None

        # BULLDOG SPRINT 1: Tracking Collections
        self.wanted_blocks = set()        # Hashes of blocks we know exist but failed to download
        self.banned_peers = {}            # {ip: expiry_timestamp}
        self.peer_disconnect_counts = {}  # {ip: {count: N, last_fail: time}}

    def ban_peer(self, ip, duration=60):
        """Bans a peer IP for a specified duration (default 60s)."""
        logger.warning(f"BULLDOG: Banning peer {ip} for {duration} seconds due to instability.")
        self.banned_peers[ip] = int(time.time()) + duration
        # Disconnect if active
        for p in list(self.active_connections):
            if p[0] == ip:
                self.forget_peer(p)

    def is_banned(self, ip):
        """Checks if an IP is currently banned."""
        if ip in self.banned_peers:
            if time.time() > self.banned_peers[ip]:
                del self.banned_peers[ip] # Expired
                return False
            return True
        return False

    def track_disconnect(self, ip):
        """Tracks frequent disconnects to trigger bans."""
        now = time.time()
        stats = self.peer_disconnect_counts.get(ip, {'count': 0, 'last_fail': 0})
        
        # If last fail was recent (< 10s), increment count
        if now - stats['last_fail'] < 10:
            stats['count'] += 1
        else:
            stats['count'] = 1 # Reset if it's been a while
            
        stats['last_fail'] = now
        self.peer_disconnect_counts[ip] = stats
        
        if stats['count'] >= 3:
            logger.error(f"Peer {ip} failed 3 times in rapid succession. Incurring 1m BAN.")
            self.ban_peer(ip, duration=60)

    async def retry_wanted_blocks(self):
        """Immediately asks ANY other connected peer for blocks we missed."""
        if not self.wanted_blocks:
            return

        # Sanity check limit
        if len(self.wanted_blocks) > 500:
             # Prevent memory leak if we get desynced
             self.wanted_blocks.clear()
             return

        logger.info(f"BULLDOG: Retrying download of {len(self.wanted_blocks)} wanted blocks from available peers...")
        
        # Create inventory request
        inv = [{"type": "block", "hash": h} for h in list(self.wanted_blocks)]
        
        # Create GETDATA message
        entry = {
            "type": "getdata",
            "inventory": inv
        }
        payload = json.dumps(entry).encode('utf-8')
        msg = Message('getdata', payload)
        serialized = msg.serialize()
        
        sent_count = 0
        for peer, writer in self.active_connections.items():
            try:
                writer.write(serialized)
                await writer.drain()
                sent_count += 1
            except: pass
        
        if sent_count > 0:
            logger.info(f"BULLDOG: Sent GETDATA for wanted blocks to {sent_count} peers.")
        else:
            logger.warning("BULLDOG: No peers available to retry wanted blocks! Waiting for new connection...")

    def configure_stun(self, ip, port):
        self.stun_ip = ip
        self.stun_port = int(port)
        logger.info(f"STUN Configuration Updated: {self.stun_ip}:{self.stun_port}")

    def log_peer_event(self, peer, direction, message_type, details=""):
        if peer not in self.peer_logs:
            self.peer_logs[peer] = []
        
        # NOTE: We DO NOT update peer_last_heard here. 
        # log_peer_event captures outgoing attempts too.
        
        timestamp = time.strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] [{direction}] {message_type}: {details}"
        self.peer_logs[peer].append(log_entry)
        self.peer_last_log_time[peer] = time.time()
        
        # Keep ring buffer of last 50 entries
        if len(self.peer_logs[peer]) > 50:
             self.peer_logs[peer].pop(0)

    async def get_all_peer_logs(self):
        """Aggregate all peer logs into a single string."""
        buffer = io.StringIO()
        header = f"--- iCSI Coin Node Debug Logs ---\nGenerated: {time.ctime()}\n\n"
        buffer.write(header)
        
        # Sort peers by last log time (most recent first)
        sorted_peers = sorted(self.peer_logs.keys(), key=lambda p: self.peer_last_log_time.get(p, 0), reverse=True)
        
        for peer in sorted_peers:
            logs = self.peer_logs.get(peer, [])
            if not logs: continue
            
            p_str = f"{peer[0]}:{peer[1]}" if isinstance(peer, tuple) else str(peer)
            buffer.write(f"\n{'='*60}\nPEER: {p_str}\n{'='*60}\n")
            
            for entry in logs:
                buffer.write(f"[{p_str}] {entry}\n")
        
        return buffer.getvalue()

    def is_initial_block_download(self):
        """
        Returns true if we are currently in Initial Block Download mode.
        Heuristic: 
        1. If we have no peers, we are not downloading (technically).
        2. If the best peer's height is significantly > our height (e.g. 100 blocks), we are in IBD.
        3. If our best block is very old (24h+), we are in IBD (unless we are at genesis).
        """
        if not self.peers:
            return False
            
        best_peer_height = 0
        for stats in self.peer_stats.values():
            h = stats.get('height', 0)
            if h > best_peer_height:
                best_peer_height = h
                
        my_height = 0
        best_block = self.block_index.get_best_block()
        if best_block:
            my_height = best_block['height']
            
        # If we are effectively at 0 (genesis), assume IBD if anyone has blocks
        if my_height <= 1 and best_peer_height > 10:
            return True
            
        # Standard check: 100 blocks behind
        if best_peer_height - my_height > 100:
            return True
            
        return False

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
        
        # Rebroadcast Loop
        t3 = asyncio.create_task(self.rebroadcast_loop())
        self.tasks.add(t3)
        t3.add_done_callback(self.tasks.discard)
        
        # If -connect is specified, we ONLY connect to those nodes
        if self.connect_nodes:
            logger.info(f"Connect-only mode active. Connecting to: {self.connect_nodes}")
            for node in self.connect_nodes:
                     t = asyncio.create_task(self.connect_to_peer(node))
                     self.tasks.add(t)
                     t.add_done_callback(self.tasks.discard)
                     # Grace period for added nodes
                     host = node.split(':')[0] if ':' in node else node
                     port = int(node.split(':')[1]) if ':' in node else 9333
                     self.peer_last_heard[(host, port)] = time.time()
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

        # Multicast Discovery (LAN auto-discovery)
        t5 = asyncio.create_task(self.multicast_beacon.start_sender())
        self.tasks.add(t5)
        t5.add_done_callback(self.tasks.discard)

        t6 = asyncio.create_task(self.multicast_beacon.start_listener())
        self.tasks.add(t6)
        t6.add_done_callback(self.tasks.discard)

        # Periodic Peer Pruning based on port check (60s)
        t7 = asyncio.create_task(self.periodically_prune_peers())
        self.tasks.add(t7)
        t7.add_done_callback(self.tasks.discard)

        # Sync Watchdog
        t7 = asyncio.create_task(self.sync_worker())
        self.tasks.add(t7)
        t7.add_done_callback(self.tasks.discard)

        # Keepalive Worker (Ping/Pong)
        t8 = asyncio.create_task(self.keepalive_worker())
        self.tasks.add(t8)
        t8.add_done_callback(self.tasks.discard)


    async def _on_multicast_discover(self, ip, ports, p2p_port):
        """Called when a new peer is discovered via multicast."""
        # If this peer advertises seed ports (9333-9335), treat it as a seed
        seed_ports = {9333, 9334, 9335}
        if seed_ports.issubset(set(ports)):
            if self.discovered_seed is None:
                self.discovered_seed = ip
                self.configure_stun(ip, 3478)
                logger.info(f"🌐 Auto-discovered SEED node: {ip} (ports: {ports})")

                # Auto-connect to all seed ports
                for sp in ports:
                    target = f"{ip}:{sp}"
                    t = asyncio.create_task(self.connect_to_peer(target))
                    self.tasks.add(t)
                    t.add_done_callback(self.tasks.discard)
        else:
            # Regular peer — connect to its P2P port
            target = f"{ip}:{p2p_port}"
            if (ip, p2p_port) not in self.peers:
                logger.info(f"🌐 Auto-discovered peer: {target}")
                t = asyncio.create_task(self.connect_to_peer(target))
                self.tasks.add(t)
                t.add_done_callback(self.tasks.discard)

    async def stop(self):
        self.running = False
        self.multicast_beacon.stop()
        if self.active_beg and self.active_beg.get('task'):
            self.active_beg['task'].cancel()
            self.active_beg = None
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("Network manager stopped.")

    # --- BEGGAR SYSTEM ---

    async def start_begging(self, address):
        """Start broadcasting a beggar advertisement every 60s for 20 minutes."""
        # Stop any existing beg
        if self.active_beg and self.active_beg.get('task'):
            self.active_beg['task'].cancel()

        async def _beg_loop():
            started = time.time()
            duration = 20 * 60  # 20 minutes
            interval = 60  # 60 seconds
            while time.time() - started < duration:
                payload = json.dumps({
                    'address': address,
                    'comment': f'Wallet Beggar: {address}'
                }).encode('utf-8')
                msg = Message('beggar', payload)
                for peer_addr, peer_writer in self.active_connections.items():
                    try:
                        peer_writer.write(msg.serialize())
                        await peer_writer.drain()
                    except: pass
                logger.info(f"💰 Beggar broadcast sent: {address}")
                await asyncio.sleep(interval)
            # Auto-expire
            logger.info(f"💰 Beggar expired after 20 minutes: {address}")
            self.active_beg = None

        task = asyncio.create_task(_beg_loop())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        self.active_beg = {'address': address, 'started_at': time.time(), 'task': task}
        logger.info(f"💰 Started begging with address: {address}")

    async def stop_begging(self):
        """Stop begging and broadcast removal to peers."""
        if not self.active_beg:
            return
        address = self.active_beg['address']
        if self.active_beg.get('task'):
            self.active_beg['task'].cancel()

        # Broadcast removal
        payload = json.dumps({'address': address}).encode('utf-8')
        msg = Message('beggar_rm', payload)
        for peer_addr, peer_writer in self.active_connections.items():
            try:
                peer_writer.write(msg.serialize())
                await peer_writer.drain()
            except: pass

        self.active_beg = None
        logger.info(f"💰 Stopped begging: {address}")

    def get_beggar_list(self):
        """Return list of beggars with balances from chain state."""
        result = []
        for address, info in self.beggar_list.items():
            # Look up balance from chain state
            balance = 0
            try:
                utxos = self.chain_state.get_utxos_by_script(address)
                balance = sum(u.get('amount', 0) for u in utxos)
            except: pass
            result.append({
                'address': address,
                'balance': balance,
                'first_seen': info.get('first_seen', 0),
                'last_seen': info.get('last_seen', 0),
                'source': info.get('source_ip', '')
            })
        return result

    async def process_message_loop(self, reader, writer, addr):
        """Unified message processing loop for both inbound and outbound connections."""
        peer_ip = addr[0]

        # Check ban before starting
        if self.is_banned(peer_ip):
            logger.info(f"Dropping connection to banned peer {addr}")
            writer.close()
            return

        try:
            while self.running:
                # Read Header
                header_data = await reader.readexactly(24)
                if not header_data: break
                # UNCOMMENTED FOR DEBUGGING SYNC ISSUES
                logger.debug(f"Raw Header from {addr}: {binascii.hexlify(header_data)}")
                
                magic, command, length, checksum = Message.parse_header(header_data)
                
                # LOG EVERY RECEIVED COMMAND (As requested)
                logger.debug(f"[RECV] CMD: {command} (Size: {length}) from {addr}")
                
                # Read Payload
                if length > 0:
                     logger.debug(f"Reading payload of size {length} from {addr}")
                     try:
                         payload = await reader.readexactly(length)
                     except asyncio.IncompleteReadError as e:
                         logger.error(f"Incomplete Read from {addr}: Expected {length}, got {len(e.partial)}")
                         break
                else:
                     payload = b''
                
                if addr in self.peer_stats:
                    self.peer_stats[addr]['last_seen'] = int(time.time())
                
                # Update HEARD FROM timer - This is the heartbeat!
                self.peer_last_heard[addr] = time.time()

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
                    msg = PingMessage.parse(payload)
                    # logger.debug(f"Received PING from {addr} (nonce={msg.nonce})")
                    # Reply with Pong
                    response = PongMessage(msg.nonce)
                    writer.write(response.serialize())
                    await writer.drain()
                    self.log_peer_event(addr, "SENT", "PONG", f"Nonce: {msg.nonce}")

                elif command == 'pong':
                    msg = PongMessage.parse(payload)
                    # Calculate latency if we tracked it
                    latency = 0
                    if hasattr(self, 'last_ping_time') and addr in self.last_ping_time:
                        latency = time.time() - self.last_ping_time[addr]
                    
                    # logger.debug(f"Received PONG from {addr} (latency={latency:.3f}s)")
                    self.log_peer_event(addr, "RECV", "PONG", f"Latency: {latency:.3f}s")
                
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

                    # 2. Add connected peers (High Priority)
                    for ip, port in list(self.peers)[:10]: # Limit connected peers to 10
                        if is_advertisable(ip):
                             peers_list.append({'ip': ip, 'port': port, 'services': 1, 'timestamp': int(time.time())})
                             debug_advertised.append(f"{ip}:{port}")
                             
                    # 3. Add discovered known peers (Lower Priority, Limit Total to 10)
                    # Filter for recently seen peers (last 3 hours)
                    now = time.time()
                    candidates = []
                    for p in list(self.known_peers):
                        p_stats = self.peer_stats.get(p, {})
                        if now - p_stats.get('last_seen', 0) < 10800: # 3 hours
                            candidates.append(p)
                            
                    # Shuffle to rotate through healthy peers
                    random.shuffle(candidates)
                    
                    for ip, port in candidates:
                         if len(peers_list) >= 10: break
                         if (ip, port) not in self.peers and is_advertisable(ip):
                             peers_list.append({'ip': ip, 'port': port, 'services': 1, 'timestamp': int(time.time())})
                             debug_advertised.append(f"{ip}:{port}")
                    
                    if peers_list:
                        addr_msg = AddrMessage(peers_list)
                        writer.write(addr_msg.serialize())
                        await writer.drain()
                        logger.debug(f"Sent ADDR with {len(peers_list)} peers to {addr}: {debug_advertised}")
                        self.log_peer_event(addr, "SENT", "ADDR", f"Sent nodes: {debug_advertised}")

                elif command == 'addr':
                    addresses = AddrMessage.parse(payload)
                     # Create a human-readable list of received nodes
                    received_nodes_str = ", ".join([f"{a['ip']}:{a['port']}" for a in addresses])
                    logger.debug(f"Received ADDR from {addr} with {len(addresses)} nodes: [{received_nodes_str}]")
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
                        # Decode payload
                        inv_data = json.loads(payload.decode('utf-8'))
                        items = inv_data.get('inventory', [])
                        
                        # LOGGING: Record incoming INV
                        first_item = items[0]['hash'][:8] if items and 'hash' in items[0] else "EMPTY"
                        self.log_peer_event(addr, "RECV", "INV", f"Size: {len(items)}, First: {first_item}...")
                        logger.info(f"Received INV from {addr} with {len(items)} items")

                        # BULLDOG: Track wanted blocks
                        for item in items:
                            if item['type'] == 'block':
                                self.wanted_blocks.add(item['hash'])

                        # Check what we need
                        # Check what we need
                        to_get = []
                        
                        # IBD OPTIMIZATION:
                        # If we are syncing (far behind), ONLY process INVs from our chosen Sync Peer.
                        # This prevents CPU spikes from processing 10x duplicate INVs from all 10 peers.
                        # FIX: Only enforce this if we actually HAVE a sync peer selected.
                        if self.is_initial_block_download() and self.sync_peer and addr != self.sync_peer:
                            # logger.debug(f"Ignoring INV from {addr} (Not our Sync Peer {self.sync_peer})")
                            return

                        for item in items:
                            if item['type'] == 'block':
                                # ... (rest of logic) ...
                                # Core Logic: If we don't have it in the main index, get it.
                                if not self.block_index.get_block_info(item['hash']):
                                     # Check if already requested/in-flight? associated with sync_peer?
                                     to_get.append(item)
                                else:
                                    pass
                            elif item['type'] == 'tx':
                                 # ... (tx logic)
                                if not self.mempool.get_transaction(item['hash']):
                                    to_get.append(item)
                        
                        if to_get:
                            # Reverting to standard batch size (driven by peer INV size, typ. 500)
                            msg = {
                                "type": "getdata",
                                "inventory": to_get
                            }
                            json_payload = json.dumps(msg).encode('utf-8')
                            out_msg = Message('getdata', json_payload)
                            writer.write(out_msg.serialize())
                            await writer.drain()
                            logger.info(f"Sent GETDATA for {len(to_get)} items to {addr}")
                            self.log_peer_event(addr, "SENT", "GETDATA", f"Requested {len(to_get)} blocks/txs")
                        else:
                            # CONTINUE SYNC LOGIC
                            # If to_get is empty, we already have everything in this INV.
                            # But if the INV was full (suggesting more blocks exist), we should ask for what comes NEXT.
                            # Otherwise we stall here.
                            
                            # We check the last item in the inventory.
                            last_item = inventory[-1]
                            # CONTINUE SYNC LOGIC
                            # If to_get is empty, we already have everything in this INV.
                            # But if the INV was full (suggesting more blocks exist), we should ask for what comes NEXT.
                            # Otherwise we stall here.
                            
                            # We check the last item in the inventory.
                            last_item = inventory[-1]
                            if last_item['type'] == 'block':
                                last_hash = last_item['hash']
                                
                                # Store the expected "End of Batch" hash
                                # This allows handle_block to trigger getblocks when this specific block arrives.
                                self.sync_batch_end = last_hash
                                
                                # Check peer height to decide if we should ask for more
                                peer_height = self.peer_stats.get(addr, {}).get('height', 0)
                                my_height = self.block_index.get_best_block()['height'] if self.block_index.get_best_block() else 0
                                
                                # If peer is ahead, ask for more even if this batch was known
                                # or if the batch was substantial.
                                if peer_height > my_height or len(inventory) > 0:
                                     # Logic update: Always request more if we are not at tip.
                                     logger.debug(f"INV processing complete. Checking if we need more blocks (Peer H:{peer_height} vs My H:{my_height})...")
                                     if peer_height > my_height:
                                          # Trigger getblocks to continue sync
                                          # BUT: We set sync_batch_end? 
                                          # If we DON'T download anything (because we have it all?), we must trigger NOW.
                                          if not to_get:
                                              logger.info("INV contained only known blocks/orphans. Forcing next batch request immediately.")
                                              await self.send_getblocks(writer)

                    except Exception as e:
                        logger.error(f"INV error: {e}")

                elif command == 'getdata':
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        inventory = data.get('inventory', [])
                        logger.info(f"Received GETDATA from {addr}")
                        self.log_peer_event(addr, "RECV", "GETDATA", f"Peer requested {len(inventory)} items")
                        
                        for item in inventory:
                            try:
                                if item['type'] == 'block':
                                    # Retrieve block (logic deferred to finding it in blockstore)
                                    # For Phase 4, we assume we rely on BlockIndex to find it
                                    info = self.block_index.get_block_info(item['hash'])
                                    if info:
                                        try:
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
                                            self.log_peer_event(addr, "SENT", "BLOCK", f"Hash {item['hash'][:16]}...")
                                        except Exception as e:
                                            logger.error(f"Failed to read/send block {item['hash']}: {e}")
                                    else:
                                        logger.warning(f"Requested block {item['hash']} not found in index")
                                
                                elif item['type'] == 'tx':
                                    # Retrieve tx from mempool
                                    tx = self.mempool.get_transaction(item['hash'])
                                    if tx:
                                        try:
                                            # Send TX message
                                            # We need to wrap it in a 'tx' command like existing codebase expects?
                                            # Let's check 'tx' handler below.
                                            # It expects { "payload": hex_tx } ?? No wait.
                                            # Let's see how 'tx' message is typically formed.
                                            # The existing codebase doesn't seem to have a standard TX message serializer yet?
                                            # Wait, existing grep showed 'elif command == 'tx''. Let's check its parsing.
                                            # Assuming it follows 'block' pattern: JSON with payload hex.
                                            
                                            tx_hex = binascii.hexlify(tx.serialize()).decode('ascii')
                                            msg = {
                                                "type": "tx",
                                                "payload": tx_hex
                                            }
                                            json_payload = json.dumps(msg).encode('utf-8')
                                            out_msg = Message('tx', json_payload)
                                            writer.write(out_msg.serialize())
                                            await writer.drain()
                                            logger.info(f"Sent TX {item['hash']} to {addr}")
                                            self.log_peer_event(addr, "SENT", "TX", f"Hash {item['hash'][:16]}...")
                                        except Exception as e:
                                            logger.error(f"Failed to send tx {item['hash']}: {e}")
                                    else:
                                        # Could be in block?
                                        # For now, only serve from mempool.
                                        logger.debug(f"Requested TX {item['hash']} not found in mempool")

                            except Exception as item_e:
                                logger.error(f"Error processing inventory item {item}: {item_e}")

                    except Exception as e:
                        logger.error(f"GETDATA error: {e}")

                elif command == 'block':
                    try:
                        try:
                            # Try decoding JSON
                            data = json.loads(payload.decode('utf-8'))
                        except json.JSONDecodeError as decode_err:
                            logger.error(f"[ERR] DECODE: Failed to parse JSON for block. Raw first 50 chars: {payload[:50]}")
                            # Try binary fallback or just fail
                            raise decode_err
                        block_hex = data.get('payload')
                        if block_hex:
                            block_bytes = binascii.unhexlify(block_hex)
                            # Deserialize
                            import io
                            f = io.BytesIO(block_bytes)
                            block = Block.deserialize(f)
                            
                            b_hash = block.get_hash().hex()
                            self.log_peer_event(addr, "RECV", "BLOCK", f"Hash {b_hash[:16]}...")

                            # BULLDOG: Remove from wanted list
                            if b_hash in self.wanted_blocks:
                                self.wanted_blocks.discard(b_hash)

                            # Update watchdog timer ONLY on valid block connect or processing start.
                            # We don't want to reset it for orphans if we are stuck in an orphan loop.
                            # Actually, we can update it here, but we need the Watchdog to be smarter.
                            # BETTER FIX: Only update it if the block is NOT an orphan or if it triggers a successful backfill step.
                            # For now, let's move this update ensuring we don't count endless orphans as "progress".
                            # logic moved to later in handle_block
                            pass

                            # Process via ChainManager
                            # DEADLOCK FIX: Run in main thread to avoid SQLite threading issues
                            # (SQLite objects created in main thread cannot be shared with executor)
                            success, reason = self.chain_manager.process_block(block)
                            
                            if success:
                                # Remove received transactions from mempool
                                try:
                                    for tx in block.vtx:
                                        self.mempool.remove_transaction(tx.get_hash().hex())
                                except Exception as e:
                                    logger.warning(f"Failed to remove tx from mempool: {e}")

                                self.log_peer_event(addr, "CONSENSUS", "ACCEPTED", f"Block {b_hash[:16]}... added to chain")

                                # PEER HEIGHT UPDATE FIX:
                                # Update the peer's height so the Watchdog knows it's a good peer.
                                try:
                                    best_info = self.block_index.get_best_block()
                                    if best_info:
                                        new_height = best_info['height']
                                        current_peer_height = self.peer_stats.get(addr, {}).get('height', 0)
                                        if new_height > current_peer_height:
                                            self.peer_stats.setdefault(addr, {})['height'] = new_height
                                except Exception as e:
                                    logger.warning(f"Failed to update peer height stats: {e}")

                                # LOW_DELAY SYNC FIX:
                                # We request more blocks if the peer has more blocks than we do.
                                
                                # Batch Monitor Logic:
                                self.blocks_since_req += 1
                                
                                peer_height = self.peer_stats.get(addr, {}).get('height', 0)
                                if best_info and peer_height > new_height:
                                     # SYNC TRIGGER OPTIMIZATION:
                                     # We want to ask for the next batch when:
                                     # 1. We are approaching the end of a large batch (Streaming at 70%).
                                     # 2. We hit the EXACT end of the current batch (Batch-Stop-and-Wait).
                                     
                                     is_streaming_trigger = self.blocks_since_req >= 350
                                     
                                     # Check if this block is the last one we expected from the INV
                                     # (Requires saving sync_batch_end in handle_inv)
                                     last_expected = getattr(self, 'sync_batch_end', None)
                                     is_batch_end = (b_hash == last_expected)
                                     
                                     # Safety Net: If we haven't asked in > 2.0s, ask again.
                                     # This covers cases where we missed the batch end or INV order was weird.
                                     is_stall_trigger = (time.time() - self.last_getblocks_time > 2.0)
                                     
                                     if is_streaming_trigger or is_batch_end or is_stall_trigger:
                                         reason_str = "Streaming"
                                         if is_batch_end: reason_str = "Batch-End"
                                         if is_stall_trigger: reason_str = "Stall-Timeout"
                                         
                                         # Only log streaming/batch-end as INFO. Stall as DEBUG/INFO if actually needed.
                                         if is_stall_trigger:
                                              logger.info(f"Sync: Stall Trigger (>2.0s). Requesting next batch...")
                                         else:
                                              logger.info(f"Sync: Triggering next batch ({reason_str})...")
                                              
                                         await self.send_getblocks(writer)
                                         
                                         # Reset triggers
                                         self.blocks_since_req = 0
                                         self.sync_batch_end = None

                                # Relay logic (simple flood)
                                inv_msg = {
                                    "type": "inv", 
                                    "inventory": [{"type": "block", "hash": b_hash}]
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
                                
                                # Valid block progress -> Reset Watchdog
                                self.last_block_received_time = time.time()
                            else:
                                self.log_peer_event(addr, "CONSENSUS", "IGNORED", f"Block {b_hash[:16]}... {reason}")
                                
                                # ORPHAN HANDLING
                                if "Orphan" in reason:
                                    self.log_peer_event(addr, "CONSENSUS", "ORPHAN", f"Detected {b_hash[:16]}. Triggering recovery.")
                                    # REMOVED DEBOUNCE: Always try to fetch if we are confused.
                                    # REMOVED DEBOUNCE: Always try to fetch if we are confused.
                                    try:
                                        # OLD LOGIC: Trigger full sync.
                                        # New Logic: Wait! Sending getblocks here causes the Peer to dump 500 blocks we likely already have or can't connect.
                                        # Instead, rely on the BACKFILL STRATEGY below to fetch the specific missing parent.
                                        # self.log_peer_event(addr, "OUT", "GETBLOCKS", "Triggering ancestry fetch for Orphan recovery")
                                        # await self.send_getblocks(writer)
                                        # self.log_peer_event(addr, "OUT", "GETBLOCKS", "Triggering ancestry fetch for Orphan recovery")
                                        # await self.send_getblocks(writer)
                                        pass
                                        
                                        # BACKFILL STRATEGY: Iterative Ancestry Lookup
                                        logger.debug("Orphan Backfill: Starting ancestry lookup...")
                                        # If we have a chain of orphans (A->B->C), receiving C should trigger request for B's parent (if B is known orphan).
                                        # We trace back up to 100 steps to find the "Root Orphan" that needs a parent.
                                        
                                        curr_hash = b_hash
                                        steps = 0
                                        target_parent = None
                                        
                                        while steps < 100:
                                            orphan_block = self.chain_manager.orphan_blocks.get(curr_hash)
                                            if not orphan_block:
                                                # Should not happen for the first iteration (b_hash), but safe to break
                                                break
                                                
                                            prev_hash = orphan_block.header.prev_block.hex()
                                            
                                            # Do we have this parent in the MAIN chain?
                                            if self.block_index.get_block_info(prev_hash):
                                                # Parent is known and processed. 
                                                # If we are here, it means we FAILED to connect the child despite having parent?
                                                # That suggests validation failure or race condition. 
                                                # We stop here.
                                                target_parent = None
                                                break
                                                
                                            # Do we have this parent in the ORPHAN pool?
                                            if prev_hash in self.chain_manager.orphan_blocks:
                                                # Yes, so we need TO CHECK *ITS* PARENT. 
                                                # Move one step back.
                                                curr_hash = prev_hash
                                                steps += 1
                                                continue
                                            
                                            # If neither, THIS is the missing link we need.
                                            target_parent = prev_hash
                                            break
                                            
                                        if target_parent:
                                            # Check Debounce
                                            now = time.time()
                                            last_req = self.requested_orphans.get(target_parent, 0)
                                            if now - last_req < 5.0:
                                                # Debounce: Skip request
                                                pass
                                            else:
                                                self.requested_orphans[target_parent] = now
                                                
                                                logger.info(f"Orphan Backfill: Found gap at {target_parent[:16]} (Child: {curr_hash[:16]}). Requesting...")
                                                self.log_peer_event(addr, "OUT", "GETDATA", f"Requesting missing root parent {target_parent[:16]}...")
                                                
                                                inv_item = {"type": "block", "hash": target_parent}
                                                msg = {"type": "getdata", "inventory": [inv_item]}
                                                payload = json.dumps(msg).encode('utf-8')
                                                out_m = Message('getdata', payload)
                                                writer.write(out_m.serialize())
                                                await writer.drain()
                                        else:
                                             # No actionable parent found (or loop/limit hit)
                                             pass

                                        # Update stats for tracking
                                        if addr in self.peer_stats:
                                            self.peer_stats[addr]['last_ancestry_req'] = time.time()
                                    except Exception as e:
                                        logger.error(f"Failed to send recovery requests: {e}")
                                else:
                                    pass # Invalid or known
                                
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
                            # FIX: validate_transaction requires utxo_set and returns (bool, reason)
                            is_valid, reason = validate_transaction(tx, self.chain_manager.chain_state)
                            if is_valid:
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
                                logger.warning(f"Received INVALID TX from {addr}: {reason}")
                    except Exception as e:
                        logger.error(f"TX error: {e}")

                elif command == 'getblocks':
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        locator = data.get('locator', [])
                        
                        # LOGGING: Record incoming getblocks request
                        tip_str = locator[0][:8] if locator else "EMPTY"
                        self.log_peer_event(addr, "RECV", "GETBLOCKS", f"Locator Size: {len(locator)}, Tip: {tip_str}...")
                        
                        # Find common ancestor
                        start_hash = None
                        start_info = None
                        
                        for h in locator:
                            info = self.block_index.get_block_info(h)
                            # RELAXED CHECK: Accept Status 2 (Valid Fork) or 3 (Main Chain)
                            if info and info['status'] >= 2:
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
                            # Limit to 500 blocks per batch (Standard) to prevent huge getdata bursts
                            # Changed back from 2000 to 500
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

                elif command == 'beggar':
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        address = data.get('address', '')
                        comment = data.get('comment', '')
                        if address:
                            now = int(time.time())
                            is_new = address not in self.beggar_list
                            self.beggar_list[address] = {
                                'first_seen': self.beggar_list.get(address, {}).get('first_seen', now),
                                'last_seen': now,
                                'source_ip': str(addr)
                            }
                            if is_new:
                                logger.info(f"💰 Beggar discovered: {address} from {addr}")
                                # Relay to other peers
                                relay_msg = Message('beggar', payload)
                                for peer_addr, peer_writer in self.active_connections.items():
                                    if peer_addr != addr:
                                        try:
                                            peer_writer.write(relay_msg.serialize())
                                            await peer_writer.drain()
                                        except: pass
                    except Exception as e:
                        logger.error(f"Beggar message error: {e}")

                elif command == 'beggar_rm':
                    try:
                        data = json.loads(payload.decode('utf-8'))
                        address = data.get('address', '')
                        if address and address in self.beggar_list:
                            del self.beggar_list[address]
                            logger.info(f"💰 Beggar removed: {address}")
                            # Relay removal
                            relay_msg = Message('beggar_rm', payload)
                            for peer_addr, peer_writer in self.active_connections.items():
                                if peer_addr != addr:
                                    try:
                                        peer_writer.write(relay_msg.serialize())
                                        await peer_writer.drain()
                                    except: pass
                    except Exception as e:
                        logger.error(f"Beggar_rm error: {e}")
                
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}")
            self.log_peer_event(addr, "ERR", "EXCEPTION", str(e))
        finally:
            # BULLDOG: Logic for disconnect tracking
            # peer_ip is defined at start of function
            self.track_disconnect(peer_ip)
            
            # BULLDOG: Trigger immediate retry for any pending blocks
            # (Wanted blocks persist until explicitly cleared or received)
            asyncio.create_task(self.retry_wanted_blocks())

            logger.info(f"[CONN] CLOSED: Connection to {addr} ended.")
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
            
            pass

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        logger.info(f"New incoming connection from {addr}")
        self.peer_stats[addr] = {'connected_at': int(time.time()), 'last_seen': int(time.time())}
        self.log_peer_event(addr, "IN", "CONNECTION", "Established incoming connection")
        
        # Temp var to store the actual listening port if provided
        remote_listening_port = addr[1]
        
        # Initialize variables to prevent UnboundLocalError if parsing fails
        remote_height = 0
        remote_agent = "Unknown"

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
                    remote_height = version_msg.start_height
                    remote_agent = version_msg.user_agent
                    
                    if remote_height == 0:
                        logger.warning(f"Peer {addr[0]} has Height 0.")
                    
                    logger.info(f"Peer {addr[0]} reports listening on port {remote_listening_port}, Height: {remote_height}")
                except Exception as e:
                    logger.error(f"Failed to parse Version message: {e}")
                
                self.log_peer_event(addr, "RECV", "VERSION", f"Handshake initiated (Port {remote_listening_port}, Height {remote_height})")
                
                # BUG FIX: Initialize stats if missing so we don't lose the height
                if addr not in self.peer_stats:
                    self.peer_stats[addr] = {'connected_at': int(time.time()), 'last_seen': int(time.time())}
                
                self.peer_stats[addr]['height'] = remote_height
                self.peer_stats[addr]['user_agent'] = remote_agent
                
                # 2. Send Version
                best = self.chain_manager.block_index.get_best_block()
                my_height = best['height'] if best else 0
                my_version = VersionMessage(addr_from_port=self.port, start_height=my_height)
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
            
            # Delegate to unified loop using canonical address (listening port) if available
            canonical_addr = (addr[0], remote_listening_port) if remote_listening_port > 0 else addr
            
            # If changed, ensure stats/logs container exists for canonical key
            if canonical_addr != addr:
                 if canonical_addr not in self.peer_stats:
                      # Copy stats from original addr if available
                      raw_stats = self.peer_stats.get(addr, {})
                      self.peer_stats[canonical_addr] = {
                          'connected_at': raw_stats.get('connected_at', int(time.time())), 
                          'last_seen': int(time.time()),
                          'height': raw_stats.get('height', 0),
                          'user_agent': raw_stats.get('user_agent', '')
                      }

            await self.process_message_loop(reader, writer, canonical_addr)
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

        if key in self.peer_last_heard:
            del self.peer_last_heard[key]

    def forget_peer(self, peer):
        """Completely removes a peer from all tracking lists."""
        ip, port = peer
        
        # 1. Close Connection
        if peer in self.active_connections:
            writer = self.active_connections[peer]
            try:
                writer.close()
            except: pass
            del self.active_connections[peer]

        # 2. Remove from collections
        self.peers.discard(peer)
        self.known_peers.discard(peer)
        self.pending_peers.discard(peer)
        
        if peer in self.failed_peers:
            del self.failed_peers[peer]
        
        if peer in self.peer_stats:
            del self.peer_stats[peer]
            
        if peer in self.peer_logs:
            del self.peer_logs[peer]
        
        if peer in self.peer_last_log_time:
            del self.peer_last_log_time[peer]

    def reset_data(self):
        self.peers.clear()
        self.known_peers.clear()
        self.pending_peers.clear()
        self.failed_peers.clear()
        self.peer_stats.clear()
        self.peer_logs.clear()
        self.peer_logs.clear()
        self.peer_last_log_time.clear()
        self.peer_last_heard.clear()
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
            if len(self.peers) < 8:
                if self.known_peers:
                     # Try to connect to a random known peer
                     peer = random.choice(list(self.known_peers))
                     
                     # Check if already connected
                     if peer not in self.peers:
                          logger.info(f"Discovery: Attempting to connect to {peer}")
                          t = asyncio.create_task(self.connect_to_peer(f"{peer[0]}:{peer[1]}"))
                          self.tasks.add(t)
                          t.add_done_callback(self.tasks.discard)
                else:
                     # NO KNOWN PEERS AND FEW PEERS CONNECTED
                     # Trigger LAN Scanner if enough time passed
                     if time.time() - self.last_lan_scan > 60:
                         logger.info("Discovery: No peers found. Triggering LAN Subnet Scan...")
                         self.last_lan_scan = time.time()
                         
                         # Scan self.port (likely 9341) + defaults
                         scan_ports = list(set([self.port, 9333, 9334, 9335, 9341]))
                         found_hosts = await self.lan_scanner.scan(ports=scan_ports)
                         
                         for host, port in found_hosts:
                             target = f"{host}:{port}"
                             logger.info(f"Discovery: Auto-Connecting to scanned peer {target}")
                             t = asyncio.create_task(self.connect_to_peer(target))
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
            
            # Aggressive Cleanup: Remove peers inactive for > 120s based on HEARD FROM
            # Note: We now use 120s and rely on peer_last_heard to avoid killing nodes we are trying to dial
            now = time.time()
            cleanup_candidates = []
            
            # Check active peers
            for peer in list(self.peers):
                # Init last_heard if missing (grace period for new peers or existing ones)
                if peer not in self.peer_last_heard:
                    self.peer_last_heard[peer] = now
                    
                last_heard = self.peer_last_heard.get(peer, 0)
                if now - last_heard > 120:
                     cleanup_candidates.append(peer)
            
            # Check failed peers (cleanup logs/stats)
            # Failed peers might not be in peer_last_heard if they never sent data
            for peer in list(self.failed_peers.keys()):
                 last_heard = self.peer_last_heard.get(peer, 0)
                 # If never heard from (0), use timestamp of failure? No, just kill them if old.
                 if last_heard == 0:
                     # If they have a failure timestamp, use that age
                     fail_time = self.failed_peers[peer].get('timestamp', 0)
                     if now - fail_time > 120:
                         cleanup_candidates.append(peer)
                 elif now - last_heard > 120:
                      cleanup_candidates.append(peer)

            # Execution
            if cleanup_candidates:
                logger.info(f"🧹 Maintenance: Checking {len(cleanup_candidates)} candidates for cleanup...")
                
            for peer in cleanup_candidates:
                ip, port = peer
                logger.info(f"🧹 Pruning DEAD peer: {ip}:{port} (Not HEARD from in >120s)")
                self.forget_peer(peer)

            await asyncio.sleep(5) # Poll faster for UI responsiveness

    async def keepalive_worker(self):
        """Sends periodic PINGs to all peers to prevent timeouts."""
        logger.info("Starting Keepalive Worker...")
        self.last_ping_time = {} # Init latency tracker
        
        while self.running:
            await asyncio.sleep(30) # Ping every 30s
            
            # Copy keys to avoid modification during iteration
            for peer in list(self.active_connections.keys()):
                try:
                    if peer in self.active_connections:
                        writer = self.active_connections[peer]
                        nonce = random.getrandbits(64)
                        ping = PingMessage(nonce)
                        writer.write(ping.serialize())
                        await writer.drain()
                        
                        self.last_ping_time[peer] = time.time()
                        # self.log_peer_event(peer, "SENT", "PING", "Keepalive")
                except Exception as e:
                    logger.debug(f"Failed to ping {peer}: {e}")

    async def sync_worker(self):
        """
        Background task to monitor synchronization progress.
        If we are behind (based on time) and haven't received a block recently,
        trigger a getblocks request to a random peer to restart the flow.
        """
        logger.info("Starting Sync Watchdog...")
        while self.running:
            await asyncio.sleep(10) # Check every 10 seconds

            try:
                # 0. SMART RECONNECT: If we have no peers, try to reconnect to known good ones
                if not self.active_connections and self.peer_stats:
                    logger.warning("Sync Watchdog: No active connections! Attempting Smart Reconnect...")
                    
                    # Sort peers by last_seen (most recent first)
                    # peer_stats = {addr: {'last_seen': ts, ...}}
                    # Filter out purely local IPs if we know better? No, trust peer_stats for now.
                    candidates = sorted(
                        self.peer_stats.keys(), 
                        key=lambda p: self.peer_stats[p].get('last_seen', 0), 
                        reverse=True
                    )
                    
                    reconnected_count = 0
                    for peer in candidates[:5]: # Try top 5 recent peers
                        host = peer[0]
                        port = peer[1]
                        
                        # Quick check
                        # Use a shorter timeout for reconnection checks
                        if await self.quick_connect_check(host, port, timeout=1.0):
                            logger.info(f"Smart Reconnect: {host}:{port} is ALIVE. Reconnecting...")
                            target_str = f"{host}:{port}"
                            # Spawn connection task
                            t = asyncio.create_task(self.connect_to_peer(target_str))
                            self.tasks.add(t)
                            t.add_done_callback(self.tasks.discard)
                            
                            reconnected_count += 1
                            if reconnected_count >= 1: 
                                break # Found a lifeline, let discovery handle the rest
                    
                    if reconnected_count > 0:
                        # Give it a moment to connect before checking sync status
                        await asyncio.sleep(2)
                        continue

                # 1. Determine if we need to sync
                # Check current tip timestamp
                best_block = self.block_index.get_best_block()
                if not best_block:
                    continue
                
                # Get block timestamp (approximate from header if we had it, but we can infer from other sources?)
                # We don't have timestamp in block_index directly unless we load the block or it's in metadata?
                # Actually, wait. block_index info doesn't have timestamp. 
                # We'll use system time vs. expected block time? 
                # Better: load the block header.
                
                tip_hash = best_block['block_hash']
                tip_block = self.chain_manager.get_block_by_hash(tip_hash)
                if not tip_block:
                    continue
                    
                tip_time = tip_block.header.timestamp
                now = int(time.time())
                
                tip_time = tip_block.header.timestamp
                now = int(time.time())
                
                # FIX: Remove 1-hour delay check. 
                # If we are silent for > 60s, we should ask for blocks regardless of tip age.
                # This ensures we catch up even if only a few minutes behind.
                
                # OPTIMIZATION: If we recently asked for blocks (via Continue Sync or previous loop), 
                # don't interrupt it.
                if time.time() - getattr(self, 'last_getblocks_time', 0) < 10:
                     # logger.debug("Sync in progress (recent getblocks), skipping watchdog check.")
                     continue

                # Check if we are stalling
                # Stalled = No block received in last 60 seconds
                time_since_last_block = time.time() - self.last_block_received_time
                
                if time_since_last_block > 20: 
                    logger.warning(f"Sync Watchdog: Silence detected! (Last Recv: {time_since_last_block:.1f}s ago). Requesting blocks...")
                    
                    # STALL RECOVERY: Force Reconnect if stuck > 45s
                    # This replicates the "Restart" wakeup effect.
                    if time_since_last_block > 45 and self.active_connections:
                        if time.time() - getattr(self, 'last_stall_recovery', 0) > 60:
                            logger.error("🚨 Sync Watchdog: STALL DETECTED (>45s). Force-reconnecting best peer to trigger wakeup!")
                            self.last_stall_recovery = time.time()
                            
                            # Find the most likely culprit (Best Peer)
                            victim = None
                            max_h = -1
                            for p, stats in self.peer_stats.items():
                                if p in self.active_connections and stats.get('height', 0) > max_h:
                                    max_h = stats.get('height', 0)
                                    victim = p
                            
                            # If no clear best, kill random
                            if not victim:
                                victim = random.choice(list(self.active_connections.keys()))
                                
                            logger.info(f"Refeshing connection to {victim}...")
                            self.forget_peer(victim)
                            # Discovery/Maintain Nodes will pick it up again
                            continue 

                    
                    # Trigger getblocks to a random peer
                    if self.active_connections:
                        # 3. SELECT SYNC PEER (Targeted Sync)
                        # Pick the best peer and stick to it.
                        best_peer = None
                        max_h = -1
                        
                        # Election: Find best candidate
                        for p, stats in self.peer_stats.items():
                             if p in self.active_connections:
                                 h = stats.get('height', 0)
                                 if h > max_h:
                                     max_h = h
                                     best_peer = p
                        
                        # Switch validity check
                        if best_peer:
                            # If we don't have a sync peer, or current one is dead/stalled/worse, switch.
                            need_switch = False
                            if not self.sync_peer or self.sync_peer not in self.active_connections:
                                need_switch = True
                            elif best_peer != self.sync_peer:
                                # Only switch if significantly better or current is causing gaps
                                # Use a small hysteresis or stickiness to avoid flapping
                                current_h = self.peer_stats.get(self.sync_peer, {}).get('height', 0)
                                if max_h > current_h + 10: # Only if much better
                                     need_switch = True
                            
                            if need_switch:
                                logger.info(f"Sync Watchdog: Switching Sync Peer to {best_peer} (Height {max_h})")
                                self.sync_peer = best_peer
                                self.last_sync_peer_switch = time.time()
                            
                            # Execute Sync Request
                            if self.sync_peer:
                                 logger.info(f"Sync Watchdog: Requesting blocks from Sync Peer {self.sync_peer}")
                                 writer = self.active_connections[self.sync_peer]
                                 await self.send_getblocks(writer)
                        else:
                             # Fallback if no valid stats
                             import random
                             target_peer = random.choice(list(self.active_connections.keys()))
                             logger.info(f"Sync Watchdog: No clear best peer, trying random {target_peer}")
                             writer = self.active_connections[target_peer]
                             await self.send_getblocks(writer)
                             self.last_block_received_time = time.time()
                            
            except Exception as e:
                logger.error(f"Sync Watchdog error: {e}")

    async def rebroadcast_loop(self):
        """Periodically rebroadcast mempool transactions to ensure propagation."""
        while self.running:
            await asyncio.sleep(60) # Every 60 seconds
            
            txs = self.mempool.get_all_transactions()
            if not txs:
                continue
                
            logger.info(f"Rebroadcasting {len(txs)} transactions from mempool...")
            
            # Announce all TXs
            for tx in txs:
                inv_msg = {
                    "type": "inv", 
                    "inventory": [{"type": "tx", "hash": tx.get_hash().hex()}]
                }
                json_payload = json.dumps(inv_msg).encode('utf-8')
                out_m = Message('inv', json_payload)
                
                # Send to all connected peers
                count = 0
                for peer_addr, peer_writer in list(self.active_connections.items()):
                    try:
                        peer_writer.write(out_m.serialize())
                        await peer_writer.drain()
                        count += 1
                    except: pass
            
            logger.info(f"Rebroadcast completed to {count} peers")

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
            # Create locator using dense-then-sparse strategy
            locator = self.chain_manager.get_block_locator()
            
            if not locator:
                logger.error("get_block_locator returned empty list! Cannot sync.")
                return

            msg = {
                "type": "getblocks",
                "locator": locator
            }
            json_payload = json.dumps(msg).encode('utf-8')
            out_msg = Message('getblocks', json_payload)
            
            peer_writer.write(out_msg.serialize())
            await peer_writer.drain()
            self.last_getblocks_time = time.time()
            self.blocks_since_req = 0 # Reset batch monitor
            
            # Use log_peer_event for consistency with user's view
            try:
                addr_info = peer_writer.get_extra_info('peername')
                self.log_peer_event(addr_info, "OUT", "GETBLOCKS", f"Sent locator with {len(locator)} hashes (Tip: {locator[0][:8]}...)")
            except:
                logger.info(f"SENT GETBLOCKS (Locator size: {len(locator)}) to peer")
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

    async def periodically_prune_peers(self):
        """
        Periodically checks known peers for connectivity and removes dead ones.
        Run interval: 60 seconds.
        """
        while self.running:
            await asyncio.sleep(60)
            
            if not self.known_peers:
                continue
                
            logger.info("Starting periodic peer pruning scan...")
            to_remove = set()
            
            # Create a copy to iterate safely
            current_peers = list(self.known_peers)
            
            for peer in current_peers:
                if not self.running: break
                host, port = peer
                
                # Skip if currently connected (don't prune active connections here)
                if peer in self.active_connections:
                    continue
                    
                is_reachable = await self.quick_connect_check(host, port, timeout=2.0)
                if not is_reachable:
                    logger.info(f"Pruning unreachable peer: {host}:{port}")
                    to_remove.add(peer)
            
            # Remove dead peers
            if to_remove:
                self.known_peers -= to_remove
                logger.info(f"Pruned {len(to_remove)} unreachable peers.")
            else:
                logger.info("Peer pruning scan complete. No peers removed.")

    async def quick_connect_check(self, host, port, timeout=2.0):
        """
        Attempts a raw TCP connection with a short timeout to fail fast on dead peers.
        Returns True if reachable, False otherwise.
        """
        try:
            # We use open_connection with a short timeout just to check reachability
            # This avoids the overhead of the full handshake logic if the host is down
            conn = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as e:
            # logger.debug(f"Fast-Fail: {host}:{port} unreachable ({e})")
            return False
        except Exception as e:
            logger.debug(f"Fast-Fail: {host}:{port} error ({e})")
            return False

    async def connect_to_peer(self, node_address, force=False):
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

        # Force Reconnect Logic
        if force:
            logger.info(f"Force-Reconnecting to {host}:{port}...")
            self.log_peer_event(target, "USER", "TEST", "Manual Test Initiated")
            if target in self.peers:
                # Close existing connection but don't forget peer data (we want logs)
                if target in self.active_connections:
                    writer = self.active_connections[target]
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except: pass
                    # Use pop to avoid KeyError if the background task already cleaned it up
                    self.active_connections.pop(target, None)
                self.peers.discard(target)
                # We don't discard pending_peers because we are about to add it back
        
        # Avoid duplicate connection attempts
        if not force and (target in self.peers or target in self.pending_peers):
            return 
        
        # Also check if we are connected to this host on any port? 
        # No, because host might have multiple nodes? Unlikely for P2P but ok.

        # --- FAST FAIL CHECK ---
        # Before we commit to the pending set and full log noise, check if it's even there.
        # This prevents the "Stall" where we wait 10s for 20 dead nodes.
        if not await self.quick_connect_check(host, port, timeout=1.5):
             # logger.info(f"Fast-Fail: Skipping dead peer {host}:{port}")
             # Mark as failed so we don't retry immediately
             self.failed_peers[target] = {'timestamp': int(time.time()), 'error': 'Fast-Fail Timeout'}
             return False

        self.pending_peers.add(target)
        # Clear previous failure if any
        if target in self.failed_peers:
            del self.failed_peers[target]
            
        logger.info(f"Attempting to connect to peer: {host}:{port}")
        self.log_peer_event(target, "OUT", "CONNECT", "Attempting connection...")
        
        reader = None
        writer = None
        try:
            # Add timeout to initial connection
            # We already did a quick check, but a race condition or firewall could still block it,
            # so we keep the timeout but maybe shorten it or keep it 10s for safety.
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=10)
            
            addr = writer.get_extra_info('peername')
            logger.info(f"TCP Connected to {addr}")
            self.log_peer_event(addr, "OUT", "CONNECT", "TCP Connection Established")
            
            # Update stats
            self.peer_stats[addr] = {'connected_at': int(time.time()), 'last_seen': int(time.time())}

            # 1. Send Version
            # We must advertise our own listening port so the remote node knows how to dial us back.
            # Using external_ip if available, otherwise 127.0.0.1 placeholder
            my_ip = self.external_ip if self.external_ip else '127.0.0.1'
            
            # Get current height for accurate handshake
            best = self.chain_manager.block_index.get_best_block()
            my_height = best['height'] if best else 0
            
            version_msg = VersionMessage(addr_from_port=self.port, addr_from_ip=my_ip, start_height=my_height)
            writer.write(version_msg.serialize())
            await writer.drain()
            logger.info(f"Sent VERSION to {addr}")
            self.log_peer_event(addr, "SENT", "VERSION", "Handshake initiated")
            
            # Recv Version with Timeout
            header_data = await asyncio.wait_for(reader.read(24), timeout=10)
            if len(header_data) < 24: return 
            
            magic, command, length, checksum = Message.parse_header(header_data)
            if command == 'version':
                payload = await asyncio.wait_for(reader.read(length), timeout=10)
                logger.info(f"Received VERSION from {addr}")
                
                 # Parse Version
                try:
                    version_msg = VersionMessage.parse(payload)
                    remote_height = version_msg.start_height
                    remote_agent = version_msg.user_agent
                    
                    if remote_height == 0:
                        logger.warning(f"Connected to Peer {addr} (Height: 0). WARNING: Peer has no blocks.")
                    else:
                        logger.info(f"Connected to Peer {addr} (Height: {remote_height}, Agent: {remote_agent})")
                        
                    # Update stats
                    self.peer_stats[addr] = {
                        'connected_at': int(time.time()), 
                        'last_seen': int(time.time()),
                        'height': remote_height,
                        'user_agent': remote_agent
                    }

                except Exception as e:
                    logger.error(f"Failed to parse Version from {addr}: {e}")

                self.log_peer_event(addr, "RECV", "VERSION", f"Handshake initiated (Port {remote_listening_port if 'remote_listening_port' in locals() else '?'}, Height {remote_height if 'remote_height' in locals() else '?'})")
                
                # Send Verack
                writer.write(VerackMessage().serialize())
                await writer.drain()
                logger.info(f"Sent VERACK to {addr}")
                self.log_peer_event(addr, "SENT", "VERACK", "")
            
            # Recv Verack with Timeout
            header_data = await asyncio.wait_for(reader.read(24), timeout=10)
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
            
            # Delegate to unified loop in background task
            # Here 'target' is (ip, port) of the listener, which is what we want for stats/logs.
            asyncio.create_task(self.process_message_loop(reader, writer, target))
            return True

        except Exception as e:
            # Immediate failure (timeout, connection refused, etc)
            logger.error(f"Failed to connect to peer {target}: {e}")
            self.log_peer_event(target, "ERR", "CONNECT_FAIL", str(e))
            
            if writer:
                 try:
                     writer.close()
                     await writer.wait_closed()
                 except: pass

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
            return False
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
        
        connection = None
        try:
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

        except Exception as e:
            logger.error(f"Failed to initiate ICE connection check to {target_ip}:{target_port}: {e}")
            if connection:
                await connection.close()
            raise e

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
        c = None
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
        finally:
            if c:
                await c.close()
