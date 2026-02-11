import asyncio
import socket
import logging
import ipaddress
import time
from icsicoin.network.multicast import get_local_ip

logger = logging.getLogger("LANScanner")

class LANScanner:
    def __init__(self, port=9333):
        self.port = port
        self.local_ip = get_local_ip()

    async def check_host(self, ip, port, timeout=0.2):
        """
        Checks if a specific IP:Port is open using a fast async connect.
        Returns IP if successful, None otherwise.
        """
        writer = None
        try:
            # We use open_connection with a very short timeout
            conn = asyncio.open_connection(ip, port)
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return ip
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, socket.gaierror):
            return None
        except Exception as e:
            # logger.debug(f"Scan error {ip}: {e}")
            return None
        finally:
             if writer:
                 try:
                     writer.close()
                 except: pass

    def get_subnet_hosts(self):
        """
        Generates a list of IPs in the local /24 subnet.
        Excludes the local IP and gateway (.1 usually).
        """
        try:
            # Simple heuristic: Assume /24 based on local IP structure
            # e.g. 192.168.1.15 -> 192.168.1.0/24
            if self.local_ip == '127.0.0.1':
                 return []
                 
            ip_obj = ipaddress.IPv4Interface(f"{self.local_ip}/24")
            network = ip_obj.network
            
            # Generate all hosts
            hosts = [str(ip) for ip in network.hosts()]
            
            # Filter out self
            if self.local_ip in hosts:
                hosts.remove(self.local_ip)
                
            return hosts
        except Exception as e:
            logger.error(f"Failed to calculate subnet: {e}")
            return []

    async def scan(self, timeout=0.2):
        """
        Scans the local subnet for the target port.
        Returns a list of active IPs.
        """
        hosts = self.get_subnet_hosts()
        if not hosts:
            return []
            
        logger.info(f"Starting LAN Scan on {len(hosts)} hosts (Port {self.port})...")
        start_time = time.time()
        
        # Limit concurrency to avoid file descriptor exhaustion (e.g. 50 at a time)
        found_peers = []
        batch_size = 50
        
        for i in range(0, len(hosts), batch_size):
            batch = hosts[i:i + batch_size]
            tasks = [self.check_host(ip, self.port, timeout) for ip in batch]
            results = await asyncio.gather(*tasks)
            
            for res in results:
                if res:
                    found_peers.append(res)
                    logger.info(f"LAN Scanner Found Peer: {res}:{self.port}")
        
        duration = time.time() - start_time
        logger.info(f"LAN Scan completed in {duration:.2f}s. Found {len(found_peers)} peers.")
        return found_peers
