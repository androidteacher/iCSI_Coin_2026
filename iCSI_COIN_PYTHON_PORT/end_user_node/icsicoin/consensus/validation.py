import time
from icsicoin.consensus.merkle import get_merkle_root
# scrypt import will be needed for PoW check, assuming standard library or installed module
import scrypt 

def validate_block_header(header, prev_block_index_entry):
    """
    Validate a block header's PoW and consistency with previous block.
    header: BlockHeader object.
    prev_block_index_entry: Dict from BlockIndexDB for header.prev_block.
    """
    # 1. Check Previous Block
    # In a real node we look up prev_block_index_entry. 
    # If it's None (and not genesis), validation fails.
    
    # 2. Check Proof of Work
    # Scrypt hash must be < Target (derived from header.bits)
    # Using hardcoded parameters for scrypt (N=1024, r=1, p=1) typical for Litecoin/iCSI?
    # Actually need to check legacy code for parameters.
    # Litecoin uses N=1024, r=1, p=1.
    
    header_bytes = header.serialize()
    pow_hash = scrypt.hash(header_bytes, header_bytes, N=1024, r=1, p=1, buflen=32)
    
    # Convert bits to target
    target = bits_to_target(header.bits)
    
    # Compare (little-endian interpretation usually, but python integer comparison works on big-endian bytes if converted)
    pow_int = int.from_bytes(pow_hash, 'little')
    if pow_int > target:
        return False

    return True

def bits_to_target(bits):
    """Convert 'bits' (compact target) to integer target."""
    exponent = bits >> 24
    coefficient = bits & 0xffffff
    return coefficient * (256**(exponent - 3))

def target_to_bits(target):
    """Convert integer target back to compact 'bits' format."""
    # Find the byte length of the target
    target_bytes = target.to_bytes((target.bit_length() + 7) // 8, 'big') if target > 0 else b'\x00'
    length = len(target_bytes)
    
    # Extract 3 most significant bytes as coefficient
    if length >= 3:
        coefficient = int.from_bytes(target_bytes[:3], 'big')
    else:
        coefficient = int.from_bytes(target_bytes.ljust(3, b'\x00'), 'big')
    
    # If the high bit of coefficient is set, we need to shift right 
    # (compact format requires coefficient < 0x800000)
    if coefficient & 0x800000:
        coefficient >>= 8
        length += 1
    
    return (length << 24) | (coefficient & 0xffffff)

# ────── Difficulty Adjustment Constants ──────
DIFFICULTY_ADJUSTMENT_INTERVAL = 2016      # Retarget every 2016 blocks
TARGET_BLOCK_TIME_SECONDS = 30             # Target: 30 seconds per block
EXPECTED_TIMESPAN = DIFFICULTY_ADJUSTMENT_INTERVAL * TARGET_BLOCK_TIME_SECONDS  # 60,480s
GENESIS_BITS = 0x1f099996                  # Starting difficulty (6x easier than original)

def calculate_next_bits(chain_manager, height):
    """
    Calculate the correct 'bits' for the block at `height`.
    
    Returns genesis bits for the first 2016 blocks (height 0-2015).
    At every multiple of 2016, retargets based on actual vs expected time.
    Between retargets, returns the same bits as the last retarget.
    """
    # For heights before the first retarget, use genesis bits
    if height < DIFFICULTY_ADJUSTMENT_INTERVAL:
        return GENESIS_BITS
    
    # Find which retarget period we're in
    last_retarget_height = (height // DIFFICULTY_ADJUSTMENT_INTERVAL) * DIFFICULTY_ADJUSTMENT_INTERVAL
    
    # If we're not exactly at a retarget boundary, use the bits from the last retarget block
    if height != last_retarget_height:
        # Read the block at last_retarget_height to get its bits
        retarget_block = chain_manager.get_block_by_height(last_retarget_height)
        if retarget_block:
            return retarget_block.header.bits
        return GENESIS_BITS
    
    # ── We are at a retarget boundary ──
    # Read the first block of the previous period
    period_start_height = last_retarget_height - DIFFICULTY_ADJUSTMENT_INTERVAL
    period_start_block = chain_manager.get_block_by_height(period_start_height)
    
    # Read the last block of the previous period (block just before this retarget)
    period_end_block = chain_manager.get_block_by_height(last_retarget_height - 1)
    
    if not period_start_block or not period_end_block:
        return GENESIS_BITS
    
    # Calculate actual timespan
    actual_timespan = period_end_block.header.timestamp - period_start_block.header.timestamp
    
    # Clamp: no more than 4× easier, no more than ¼× harder
    if actual_timespan < EXPECTED_TIMESPAN // 4:
        actual_timespan = EXPECTED_TIMESPAN // 4
    if actual_timespan > EXPECTED_TIMESPAN * 4:
        actual_timespan = EXPECTED_TIMESPAN * 4
    
    # Calculate new target
    old_target = bits_to_target(period_end_block.header.bits)
    new_target = (old_target * actual_timespan) // EXPECTED_TIMESPAN
    
    # Don't exceed genesis target (can't get easier than starting difficulty)
    max_target = bits_to_target(GENESIS_BITS)
    if new_target > max_target:
        new_target = max_target
    
    return target_to_bits(new_target)

import logging

logger = logging.getLogger("Validation")

def validate_block(block, utxo_set):
    """
    Validate a full block.
    """
    # 1. Check Merkle Root
    calculated_root = get_merkle_root(block.vtx)
    if calculated_root != block.header.merkle_root:
        logger.error(f"Block validation failed: Merkle Root mismatch. Header: {block.header.merkle_root.hex()}, Calc: {calculated_root.hex()}")
        return False

    # Track spent outputs in this block to prevent double-spending within the block
    spent_in_block = set()

    # 2. Validate Transactions
    for i, tx in enumerate(block.vtx):
        # Coinbase (first tx) is special
        is_coinbase = (i == 0)
        
        if not validate_transaction(tx, utxo_set, is_coinbase):
             logger.error(f"Block validation failed: Invalid transaction {tx.get_hash().hex()} at index {i}")
             return False

        if not is_coinbase:
            for vin in tx.vin:
                prev_out = (vin.prev_hash, vin.prev_index)
                if prev_out in spent_in_block:
                    logger.error(f"Block validation failed: Intra-block double spend. Input {vin.prev_hash.hex()}:{vin.prev_index} used twice.")
                    return False # Double spend within block
                spent_in_block.add(prev_out)
            
    return True

def validate_transaction(tx, utxo_set, is_coinbase=False):
    """
    Validate a single transaction.
    """
    # Basic Checks
    if not tx.vin and not is_coinbase: 
        logger.error("Tx validation failed: No inputs and not coinbase")
        return False
    if not tx.vout: 
        logger.error("Tx validation failed: No outputs")
        return False

    if is_coinbase:
        # Check coinbase maturity, etc (deferred)
        return True

    # Check Inputs
    if utxo_set is None:
        # Context-free check only (structure)
        return True

    total_in = 0
    for i, txin in enumerate(tx.vin):
        # Look up UTXO
        prev_hash_hex = txin.prev_hash.hex()
        utxo = utxo_set.get_utxo(prev_hash_hex, txin.prev_index)
        
        if not utxo:
            # Input does not exist or is already spent
            logger.error(f"Tx validation failed: Input {prev_hash_hex}:{txin.prev_index} not found in UTXO set.")
            return False
            
        total_in += utxo['amount']

    # Check Amounts (Input >= Output)
    total_out = sum(out.amount for out in tx.vout)
    if total_out > total_in:
        logger.error(f"Tx validation failed: Output total {total_out} exceeds input {total_in}")
        return False

    return True
