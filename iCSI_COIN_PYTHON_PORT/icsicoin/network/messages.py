import struct
import time
import random

# Magic value for iCSI Coin (Litecoin mainnet magic)
MAGIC_VALUE = 0xfbc0b6db

class Message:
    def __init__(self, command, payload):
        self.command = command
        self.payload = payload

    def serialize(self):
        # Header: magic (4), command (12), length (4), checksum (4)
        magic = struct.pack('<I', MAGIC_VALUE)
        command_padded = self.command.encode('ascii') + b'\x00' * (12 - len(self.command))
        payload_len = struct.pack('<I', len(self.payload))
        
        # Checksum is first 4 bytes of double-sha256 of payload?
        # For simplicity in this beta, we might skip full checksum validation or use a placeholder
        # But let's check standard bitcoin protocol.
        # Actually, let's use a simple placeholder checksum for this phase to avoid imports if we can,
        # but hashlib is standard.
        import hashlib
        checksum = hashlib.sha256(hashlib.sha256(self.payload).digest()).digest()[:4]
        
        return magic + command_padded + payload_len + checksum + self.payload

    @classmethod
    def parse_header(cls, data):
        if len(data) < 24:
            return None
        magic, command, length, checksum = struct.unpack('<I12sI4s', data[:24])
        command = command.rstrip(b'\x00').decode('ascii')
        return magic, command, length, checksum

    @staticmethod
    def serialize_var_int(i):
        if i < 0xfd:
            return struct.pack('B', i)
        elif i <= 0xffff:
            return b'\xfd' + struct.pack('<H', i)
        elif i <= 0xffffffff:
            return b'\xfe' + struct.pack('<I', i)
        else:
            return b'\xff' + struct.pack('<Q', i)

    @staticmethod
    def parse_var_int(data, offset=0):
        if offset >= len(data):
            return 0, offset
        b = data[offset]
        offset += 1
        if b < 0xfd:
            return b, offset
        elif b == 0xfd:
            return struct.unpack('<H', data[offset:offset+2])[0], offset + 2
        elif b == 0xfe:
            return struct.unpack('<I', data[offset:offset+4])[0], offset + 4
        elif b == 0xff:
            return struct.unpack('<Q', data[offset:offset+8])[0], offset + 8
        return 0, offset

    @staticmethod
    def serialize_net_addr(services, ip, port, timestamp=None):
        res = b''
        if timestamp is not None:
             res += struct.pack('<I', timestamp)
        
        res += struct.pack('<Q', services)
        
        # IP (IPv4 mapped to IPv6) (Simple fix)
        prefix = b'\x00' * 10 + b'\xff' * 2
        parts = ip.split('.')
        if len(parts) == 4:
            ip_bytes = bytes([int(x) for x in parts])
        else:
            ip_bytes = b'\x00' * 4 # Placeholder
            
        res += prefix + ip_bytes
        res += struct.pack('>H', port)
        return res

    @staticmethod
    def parse_net_addr(data, offset=0, has_timestamp=True):
        timestamp = None
        if has_timestamp:
            timestamp = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            
        services = struct.unpack('<Q', data[offset:offset+8])[0]
        offset += 8
        
        # IP
        ip_bytes = data[offset+12:offset+16] # Last 4 bytes of IPv6 mapped
        ip = ".".join([str(b) for b in ip_bytes])
        offset += 16
        
        port = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        
        return {
            'timestamp': timestamp,
            'services': services,
            'ip': ip,
            'port': port
        }, offset

class VersionMessage(Message):
    def __init__(self, version=70015, services=1, timestamp=None, 
                 addr_recv_services=1, addr_recv_ip='127.0.0.1', addr_recv_port=9333,
                 addr_from_services=1, addr_from_ip='127.0.0.1', addr_from_port=9333,
                 nonce=None, user_agent='/iCSICoin:0.1/', start_height=0):
        
        if timestamp is None:
            timestamp = int(time.time())
        if nonce is None:
            nonce = random.getrandbits(64)
            
        self.version = version
        self.services = services
        self.timestamp = timestamp
        self.addr_recv = (addr_recv_services, addr_recv_ip, addr_recv_port)
        self.addr_from = (addr_from_services, addr_from_ip, addr_from_port)
        self.nonce = nonce
        self.user_agent = user_agent
        self.start_height = start_height
        
        payload = self._serialize_payload()
        super().__init__('version', payload)

    def _serialize_payload(self):
        # Version (4), Services (8), Timestamp (8)
        payload = struct.pack('<IQQ', self.version, self.services, self.timestamp)
        
        # Addr Recv (26 bytes: services(8) + ip(16) + port(2))
        payload += self._serialize_net_addr(self.addr_recv[0], self.addr_recv[1], self.addr_recv[2])
        
        # Addr From (26 bytes)
        payload += self._serialize_net_addr(self.addr_from[0], self.addr_from[1], self.addr_from[2])
        
        # Nonce (8), User Agent (VarInt + Str), Start Height (4)
        payload += struct.pack('<Q', self.nonce)
        payload += self._serialize_var_str(self.user_agent)
        payload += struct.pack('<I', self.start_height)
        
        # Relay (1) - optional in some versions, including for now
        payload += b'\x01'
        
        return payload

    def _serialize_net_addr(self, services, ip, port):
        # Simplified: IPv4 mapped to IPv6 [::ffff:127.0.0.1]
        # For this prototype we'll just pack it simply or use a fixed buffer for localhost
        # Services (8)
        res = struct.pack('<Q', services)
        
        # IP (16 bytes). Needs to be big-endian for network? Bitcoin uses network byte order (BE) for IP/Port
        # But struct pack is usually LE for bitcoin fields? Wait, IP/Port in net_addr are BE.
        # Let's simple-hack IPv4->IPv6 mapping
        # 12 zero bytes, then 4 ip bytes? No, ::ffff:1.2.3.4
        prefix = b'\x00' * 10 + b'\xff' * 2
        
        parts = ip.split('.')
        if len(parts) == 4:
            ip_bytes = bytes([int(x) for x in parts])
        else:
            ip_bytes = b'\x00' * 4 # Placeholder for actual IPv6 or non-parsing
            
        res += prefix + ip_bytes
        res += struct.pack('>H', port) # Port is BE
        return res

    def _serialize_var_str(self, s):
        b = s.encode('ascii')
        l = len(b)
        if l < 0xfd:
            return struct.pack('B', l) + b
        elif l <= 0xffff:
            return b'\xfd' + struct.pack('<H', l) + b
        # ... skip larger for now
        return b'\x00'


class VersionMessage(Message):
    def __init__(self, version=70015, services=1, timestamp=None, 
                 addr_recv_services=1, addr_recv_ip='127.0.0.1', addr_recv_port=9333,
                 addr_from_services=1, addr_from_ip='127.0.0.1', addr_from_port=9333,
                 nonce=None, user_agent='/iCSICoin:0.1/', start_height=0):
        
        if timestamp is None:
            timestamp = int(time.time())
        if nonce is None:
            nonce = random.getrandbits(64)
            
        self.version = version
        self.services = services
        self.timestamp = timestamp
        self.addr_recv = (addr_recv_services, addr_recv_ip, addr_recv_port)
        self.addr_from = (addr_from_services, addr_from_ip, addr_from_port)
        self.nonce = nonce
        self.user_agent = user_agent
        self.start_height = start_height
        
        payload = self._serialize_payload()
        super().__init__('version', payload)

    def _serialize_payload(self):
        # Version (4), Services (8), Timestamp (8)
        payload = struct.pack('<IQQ', self.version, self.services, self.timestamp)
        
        # Addr Recv (No timestamp in Version msg)
        payload += Message.serialize_net_addr(self.addr_recv[0], self.addr_recv[1], self.addr_recv[2], timestamp=None)
        
        # Addr From (No timestamp in Version msg)
        payload += Message.serialize_net_addr(self.addr_from[0], self.addr_from[1], self.addr_from[2], timestamp=None)
        
        # Nonce (8)
        payload += struct.pack('<Q', self.nonce)
        
        # User Agent
        payload += Message.serialize_var_int(len(self.user_agent)) + self.user_agent.encode('ascii')
        
        # Start Height (4)
        payload += struct.pack('<I', self.start_height)
        
        # Relay (1)
        payload += b'\x01'
        
        return payload

class VerackMessage(Message):
    def __init__(self):
        super().__init__('verack', b'')

class GetAddrMessage(Message):
    def __init__(self):
        super().__init__('getaddr', b'')

class AddrMessage(Message):
    def __init__(self, addresses=None):
        # addresses is list of dicts or tuples: (timestamp, services, ip, port)
        if addresses is None:
            addresses = []
        
        payload = b''
        payload += Message.serialize_var_int(len(addresses))
        
        for addr in addresses:
            # Assuming addr is dict for flexibility or tuple
            if isinstance(addr, dict):
                ts = addr.get('timestamp', int(time.time()))
                srv = addr.get('services', 1)
                ip = addr.get('ip', '0.0.0.0')
                port = addr.get('port', 9333)
            else:
                ts, srv, ip, port = addr
            
            payload += Message.serialize_net_addr(srv, ip, port, timestamp=ts)
            
        super().__init__('addr', payload)
    
    @classmethod
    def parse(cls, payload):
        count, offset = Message.parse_var_int(payload, 0)
        # arbitrary limit to prevent DoS
        if count > 1000: 
            count = 1000
            
        addresses = []
        for _ in range(count):
            if offset >= len(payload):
                break
            addr, offset = Message.parse_net_addr(payload, offset, has_timestamp=True)
            addresses.append(addr)
            
        return addresses
