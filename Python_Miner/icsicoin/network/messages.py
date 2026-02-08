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
        
        # Addr Recv (No timestamp in Version msg)
        payload += Message.serialize_net_addr(self.addr_recv[0], self.addr_recv[1], self.addr_recv[2], timestamp=None)
        
        # Addr From (No timestamp in Version msg)
        payload += Message.serialize_net_addr(self.addr_from[0], self.addr_from[1], self.addr_from[2], timestamp=None)
        
        # Nonce (8)
        payload += struct.pack('<Q', self.nonce)
        
        # User Agent (Var Int Str)
        ua_bytes = self.user_agent.encode('ascii')
        payload += Message.serialize_var_int(len(ua_bytes)) + ua_bytes
        
        # Start Height (4)
        payload += struct.pack('<I', self.start_height)
        
        # Relay (1)
        payload += b'\x01'
        
        return payload

    @classmethod
    def parse(cls, payload):
        offset = 0
        version, services, timestamp = struct.unpack('<IQQ', payload[offset:offset+20])
        offset += 20
        
        # Addr Recv
        addr_recv, offset = Message.parse_net_addr(payload, offset, has_timestamp=False)
        
        # Addr From
        addr_from, offset = Message.parse_net_addr(payload, offset, has_timestamp=False)
        
        nonce = struct.unpack('<Q', payload[offset:offset+8])[0]
        offset += 8
        
        len_ua, offset = Message.parse_var_int(payload, offset)
        user_agent_bytes = payload[offset:offset+len_ua]
        user_agent = user_agent_bytes.decode('ascii', errors='ignore')
        offset += len_ua
        
        start_height = struct.unpack('<I', payload[offset:offset+4])[0]
        offset += 4
        
        # Ignoring relay
        
        return cls(version, services, timestamp, 
                   addr_recv['services'], addr_recv['ip'], addr_recv['port'],
                   addr_from['services'], addr_from['ip'], addr_from['port'],
                   nonce, user_agent, start_height)

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

class SignalMessage(Message):
    def __init__(self, target_ip=None, target_port=None, source_ip=None, source_port=None, sdp=None, candidate=None):
        # Payload: target (net_addr), source (net_addr), type (1), len, data
        
        if target_ip is None and sdp is None and candidate is None:
             super().__init__('signal', b'')
             return

        self.target_ip = target_ip
        self.target_port = target_port
        self.source_ip = source_ip
        self.source_port = source_port
        self.sdp = sdp
        self.candidate = candidate
        
        payload = b''
        payload += Message.serialize_net_addr(0, target_ip, target_port, timestamp=None)
        # Source. If None (e.g. unknown), use 0.0.0.0
        s_ip = source_ip if source_ip else '0.0.0.0'
        s_port = source_port if source_port else 0
        payload += Message.serialize_net_addr(0, s_ip, s_port, timestamp=None)
        
        if sdp:
            payload += b'\x00' # Type SDP
            data_bytes = sdp.encode('utf-8')
        elif candidate:
            payload += b'\x01' # Type Candidate
            data_bytes = candidate.encode('utf-8')
        else:
            data_bytes = b''
            
        payload += Message.serialize_var_int(len(data_bytes))
        payload += data_bytes
        
        super().__init__('signal', payload)

    @classmethod
    def parse(cls, payload):
        offset = 0
        addr_info, offset = Message.parse_net_addr(payload, offset, has_timestamp=False)
        target_ip = addr_info['ip']
        target_port = addr_info['port']
        
        source_info, offset = Message.parse_net_addr(payload, offset, has_timestamp=False)
        source_ip = source_info['ip']
        source_port = source_info['port']
        
        type_byte = payload[offset]
        offset += 1
        
        len_data, offset = Message.parse_var_int(payload, offset)
        data_bytes = payload[offset:offset+len_data]
        data = data_bytes.decode('utf-8')
        
        sdp = None
        candidate = None
        
        if type_byte == 0:
            sdp = data
        elif type_byte == 1:
            candidate = data
            
        return cls(target_ip, target_port, source_ip, source_port, sdp, candidate)

class RelayMessage(Message):
    def __init__(self, target_ip=None, target_port=None, inner_payload=None):
        # Reusing the structure of SignalMessage for simplicity? 
        # Actually Relay is just "Please send this payload to Target".
        # The payload is usually a SignalMessage.
        
        if target_ip is None:
             super().__init__('relay', b'')
             return

        self.target_ip = target_ip
        self.target_port = target_port
        self.inner_payload = inner_payload
        
        payload = b''
        payload += Message.serialize_net_addr(0, target_ip, target_port, timestamp=None)
        
        payload += Message.serialize_var_int(len(inner_payload))
        payload += inner_payload
        
        super().__init__('relay', payload)

    @classmethod
    def parse(cls, payload):
        offset = 0
        addr_info, offset = Message.parse_net_addr(payload, offset, has_timestamp=False)
        target_ip = addr_info['ip']
        target_port = addr_info['port']
        
        len_data, offset = Message.parse_var_int(payload, offset)
        inner_payload = payload[offset:offset+len_data]
        
        return cls(target_ip, target_port, inner_payload)

class TestMessage(Message):
    def __init__(self, content=None):
        if content is None:
            super().__init__('test', b'')
            return
            
        self.content = content
        # Serialize content (var int string)
        data = content.encode('utf-8')
        payload = Message.serialize_var_int(len(data)) + data
        super().__init__('test', payload)
        
    @classmethod
    def parse(cls, payload):
        length, offset = Message.parse_var_int(payload, 0)
        content = payload[offset:offset+length].decode('utf-8')
        return cls(content)
