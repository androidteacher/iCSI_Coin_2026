import struct
import io

def encode_uint32(n):
    """Encode a 4-byte unsigned integer (little-endian)."""
    return struct.pack('<I', n)

def decode_uint32(f):
    """Decode a 4-byte unsigned integer (little-endian) from a file-like object."""
    data = f.read(4)
    if len(data) < 4:
        raise EOFError("Insufficient data for uint32")
    return struct.unpack('<I', data)[0]

def encode_uint64(n):
    """Encode a 8-byte unsigned integer (little-endian)."""
    return struct.pack('<Q', n)

def decode_uint64(f):
    """Decode a 8-byte unsigned integer (little-endian) from a file-like object."""
    data = f.read(8)
    if len(data) < 8:
        raise EOFError("Insufficient data for uint64")
    return struct.unpack('<Q', data)[0]

def encode_varint(n):
    """
    Encode a variable-length integer (CompactSize).
    https://en.bitcoin.it/wiki/Protocol_documentation#Variable_length_integer
    """
    if n < 0xfd:
        return struct.pack('<B', n)
    elif n <= 0xffff:
        return b'\xfd' + struct.pack('<H', n)
    elif n <= 0xffffffff:
        return b'\xfe' + struct.pack('<I', n)
    else:
        return b'\xff' + struct.pack('<Q', n)

def decode_varint(f):
    """
    Decode a variable-length integer (CompactSize) from a file-like object.
    """
    data = f.read(1)
    if not data:
        raise EOFError("Insufficient data for varint")
    
    prefix = data[0]
    if prefix < 0xfd:
        return prefix
    elif prefix == 0xfd:
        data = f.read(2)
        if len(data) < 2:
            raise EOFError("Insufficient data for varint (uint16)")
        return struct.unpack('<H', data)[0]
    elif prefix == 0xfe:
        data = f.read(4)
        if len(data) < 4:
            raise EOFError("Insufficient data for varint (uint32)")
        return struct.unpack('<I', data)[0]
    else: # 0xff
        data = f.read(8)
        if len(data) < 8:
            raise EOFError("Insufficient data for varint (uint64)")
        return struct.unpack('<Q', data)[0]

def encode_varstr(s):
    """Encode a variable-length string (VarInt length + bytes)."""
    if isinstance(s, str):
        s = s.encode('utf-8')
    return encode_varint(len(s)) + s

def decode_varstr(f):
    """Decode a variable-length string from a file-like object."""
    length = decode_varint(f)
    data = f.read(length)
    if len(data) < length:
        raise EOFError("Insufficient data for varstr")
    return data

def serialize_list(l, serializer):
    """Serialize a list of objects, prefixed by the list length as a VarInt."""
    import io
    buffer = io.BytesIO()
    buffer.write(encode_varint(len(l)))
    for item in l:
        buffer.write(serializer(item))
    return buffer.getvalue()

def deserialize_list(f, deserializer):
    """Deserialize a list of objects, prefixed by the list length as a VarInt."""
    length = decode_varint(f)
    result = []
    for _ in range(length):
        result.append(deserializer(f))
    return result
