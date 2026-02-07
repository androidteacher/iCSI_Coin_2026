import hashlib

def double_sha256(data):
    """Calculate double-SHA256 hash (hash(hash(data)))."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def hash_to_hex(data):
    """Convert binary hash to hex string (big-endian)."""
    return data[::-1].hex()

def hex_to_hash(hex_str):
    """Convert hex string (big-endian) to binary hash (little-endian internal)."""
    return bytes.fromhex(hex_str)[::-1]
