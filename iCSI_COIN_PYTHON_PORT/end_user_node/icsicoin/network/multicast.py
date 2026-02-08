"""
UDP Multicast Peer Discovery for iCSI Coin Network.

Enables automatic LAN peer discovery so nodes on the same subnet can find
each other without manually entering seed IPs.

Multicast Group: 239.69.42.1
Port:            19333
Beacon Interval: 10 seconds

Each beacon contains:
  - magic:   "iCSI_COIN" (filter non-iCSI traffic)
  - comment: "iCSI Coin is a Subsidiary of Beck Coin! (2013!)"
  - ip:      The sender's IP address
  - ports:   The P2P ports the sender has available (e.g. [9333,9334,9335] for seeds)
  - p2p_port: The sender's own P2P listen port
  - ts:      Unix timestamp
"""

import asyncio
import json
import socket
import struct
import time
import logging

logger = logging.getLogger("Multicast")

MULTICAST_GROUP = "239.69.42.1"
MULTICAST_PORT = 19333
BEACON_MAGIC = "iCSI_COIN"
BEACON_COMMENT = "iCSI Coin is a Subsidiary of Beck Coin! (2013!)"
BEACON_INTERVAL = 10  # seconds


def get_local_ip():
    """Get the machine's LAN IP address."""
    try:
        # Connect to a public address to determine the local IP
        # (doesn't actually send any data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class MulticastBeacon:
    """
    Sends and receives UDP multicast beacons for peer discovery.
    
    Usage:
        beacon = MulticastBeacon(p2p_port=9341, seed_ports=[])
        # For a seed node, pass seed_ports=[9333, 9334, 9335]
        
        asyncio.create_task(beacon.start_sender())
        asyncio.create_task(beacon.start_listener(on_discover))
    """

    def __init__(self, p2p_port=9341, seed_ports=None, on_discover=None):
        self.p2p_port = p2p_port
        self.seed_ports = seed_ports or []
        self.on_discover = on_discover
        self.local_ip = get_local_ip()
        self.running = False
        self.known_peers = set()  # IPs we've already seen

    def _build_beacon(self):
        """Build the beacon JSON payload."""
        return json.dumps({
            "magic": BEACON_MAGIC,
            "comment": BEACON_COMMENT,
            "ip": self.local_ip,
            "ports": self.seed_ports,
            "p2p_port": self.p2p_port,
            "ts": int(time.time())
        }).encode("utf-8")

    async def start_sender(self):
        """Broadcast beacon every BEACON_INTERVAL seconds."""
        self.running = True
        logger.info(f"Multicast sender started on {MULTICAST_GROUP}:{MULTICAST_PORT} (local IP: {self.local_ip})")

        # Create UDP socket for sending
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.setblocking(False)

        loop = asyncio.get_event_loop()

        while self.running:
            try:
                beacon = self._build_beacon()
                await loop.sock_sendto(sock, beacon, (MULTICAST_GROUP, MULTICAST_PORT))
                logger.debug(f"Beacon sent: {self.local_ip}:{self.p2p_port}")
            except Exception as e:
                logger.warning(f"Multicast send error: {e}")

            await asyncio.sleep(BEACON_INTERVAL)

        sock.close()

    async def start_listener(self):
        """Listen for multicast beacons from other nodes."""
        self.running = True
        logger.info(f"Multicast listener started on {MULTICAST_GROUP}:{MULTICAST_PORT}")

        # Create UDP socket for receiving
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Bind to the multicast port
        sock.bind(("", MULTICAST_PORT))

        # Join the multicast group
        mreq = struct.pack(
            "4sl",
            socket.inet_aton(MULTICAST_GROUP),
            socket.INADDR_ANY
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)

        loop = asyncio.get_event_loop()

        while self.running:
            try:
                data, addr = await loop.sock_recvfrom(sock, 4096)
                sender_ip = addr[0]

                # Ignore our own beacons
                if sender_ip == self.local_ip:
                    continue

                # Parse beacon
                try:
                    beacon = json.loads(data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                # Validate magic
                if beacon.get("magic") != BEACON_MAGIC:
                    continue

                advertised_ip = beacon.get("ip", sender_ip)
                advertised_ports = beacon.get("ports", [])
                p2p_port = beacon.get("p2p_port", 9341)

                # Check if this is a new peer
                peer_key = advertised_ip
                if peer_key not in self.known_peers:
                    self.known_peers.add(peer_key)
                    logger.info(
                        f"🔍 Discovered peer via multicast: {advertised_ip} "
                        f"(ports: {advertised_ports}, p2p: {p2p_port})"
                    )

                    # Fire callback
                    if self.on_discover:
                        try:
                            await self.on_discover(advertised_ip, advertised_ports, p2p_port)
                        except Exception as e:
                            logger.error(f"Discovery callback error: {e}")
                else:
                    # Already known, just update timestamp silently
                    pass

            except Exception as e:
                if self.running:
                    logger.warning(f"Multicast listen error: {e}")
                    await asyncio.sleep(1)

        sock.close()

    def stop(self):
        """Stop sender and listener."""
        self.running = False
        logger.info("Multicast beacon stopped")
