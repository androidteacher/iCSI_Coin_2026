import os
import time
from icsicoin.consensus.merkle import get_merkle_root
# scrypt is the Proof-of-Work hash (Litecoin-style, N=1024/r=1/p=1). It is a hard
# dependency now that PoW is actually enforced; every validating node needs it.
import scrypt

# scrypt PoW parameters -- MUST match the miner (mining/controller.py, miner.py).
SCRYPT_N = 1024
SCRYPT_R = 1
SCRYPT_P = 1


def check_pow(header):
    """Return True iff the header's scrypt hash meets the target encoded in header.bits.

    Uses the same scrypt parameters and little-endian comparison as the miner, so any
    block the miner produces for a given `bits` will validate here.
    """
    header_bytes = header.serialize()
    pow_hash = scrypt.hash(header_bytes, header_bytes,
                           N=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, buflen=32)
    target = bits_to_target(header.bits)
    return int.from_bytes(pow_hash, 'little') <= target


def validate_block_header(header, prev_block_index_entry=None):
    """Validate a block header's PoW. Kept for API compatibility; delegates to check_pow."""
    return check_pow(header)

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

# ────── Economic / coinbase parameters ──────
# All configurable via environment so a classroom can make halving + maturity happen
# fast enough to observe in a single lesson (the Bitcoin-scale defaults of 210,000-block
# halving and 100-block maturity are ~73 days / ~50 min at a 30s block target).
COIN = 100_000_000                                                   # base units per 1 iCSI
INITIAL_BLOCK_SUBSIDY = 50 * COIN                                    # 50 iCSI at height 0
HALVING_INTERVAL = int(os.getenv("ICSI_HALVING_INTERVAL", "1000"))  # blocks between halvings
COINBASE_MATURITY = int(os.getenv("ICSI_COINBASE_MATURITY", "20"))  # blocks before mined coins are spendable


def get_block_subsidy(height):
    """Block reward (in base units) at `height`, halving every HALVING_INTERVAL blocks.

    Uses integer bit-shift math -- never float -- so the total supply is exact and
    every node computes the identical value (float 0.5**n drifts and breaks consensus).
    """
    halvings = height // HALVING_INTERVAL
    if halvings >= 64:
        return 0
    return INITIAL_BLOCK_SUBSIDY >> halvings

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

def validate_block(block, utxo_set, height=None, chain_manager=None, check_proof_of_work=True):
    """
    Validate a full block.

    utxo_set        : ChainStateDB for contextual checks, or None for a context-free
                      (PoW + merkle + structure) check.
    height          : height this block would occupy. Enables difficulty (bits), coinbase
                      subsidy, and coinbase-maturity checks.
    chain_manager   : needed to compute the expected difficulty for `height`.
    check_proof_of_work : set False to skip the (expensive) scrypt PoW when the caller
                      already verified it (avoids re-hashing the same block twice).
    """
    # 1. Proof of Work -- the header's scrypt hash must meet its claimed difficulty.
    if check_proof_of_work and not check_pow(block.header):
        reason = "Invalid Proof of Work (scrypt hash above target)"
        logger.error(f"Block validation failed: {reason}")
        return False, reason

    # 2. Check Merkle Root
    calculated_root = get_merkle_root(block.vtx)
    if calculated_root != block.header.merkle_root:
        reason = f"Merkle Root mismatch. Header: {block.header.merkle_root.hex()}, Calc: {calculated_root.hex()}"
        logger.error(f"Block validation failed: {reason}")
        return False, reason

    # 3. Difficulty: the block must carry exactly the bits the retarget rule demands,
    #    so a miner can't just lower its own difficulty.
    if height is not None and chain_manager is not None:
        expected_bits = calculate_next_bits(chain_manager, height)
        if block.header.bits != expected_bits:
            reason = f"Incorrect difficulty bits {hex(block.header.bits)} (expected {hex(expected_bits)}) at height {height}"
            logger.error(f"Block validation failed: {reason}")
            return False, reason

    # Track spent outputs in this block to prevent double-spending within the block
    spent_in_block = set()

    # Track new outputs created in this block (for chaining)
    # Key: (tx_hash_hex, vout_index) -> UTXO dict
    chained_utxos = {}

    total_fees = 0

    # 4. Validate Transactions
    for i, tx in enumerate(block.vtx):
        # Coinbase (first tx) is special
        is_coinbase = (i == 0)

        is_valid, reason, fee = validate_transaction(tx, utxo_set, is_coinbase, chained_utxos, height=height)
        if not is_valid:
             logger.error(f"Block validation failed: Invalid transaction {tx.get_hash().hex()} at index {i}: {reason}")
             return False, f"Invalid Tx {i}: {reason}"

        if not is_coinbase:
            total_fees += fee
            for vin in tx.vin:
                prev_out = (vin.prev_hash, vin.prev_index)
                if prev_out in spent_in_block:
                    reason = f"Intra-block double spend. Input {vin.prev_hash.hex()}:{vin.prev_index} used twice."
                    logger.error(f"Block validation failed: {reason}")
                    return False, reason # Double spend within block
                spent_in_block.add(prev_out)

        # Add outputs to chained_utxos
        tx_hash = tx.get_hash().hex()
        for idx, out in enumerate(tx.vout):
            chained_utxos[(tx_hash, idx)] = {
                'amount': out.amount,
                'script_pubkey': out.script_pubkey,
                'block_height': height if height is not None else 0,
                'is_coinbase': is_coinbase
            }

    # 5. Coinbase subsidy: the miner may claim at most the block subsidy for this height
    #    plus the total fees of the block. This enforces the halving schedule and caps
    #    the money supply (without it a miner could mint unlimited coin).
    if height is not None and utxo_set is not None and block.vtx:
        coinbase_out = sum(out.amount for out in block.vtx[0].vout)
        max_allowed = get_block_subsidy(height) + total_fees
        if coinbase_out > max_allowed:
            reason = f"Coinbase pays {coinbase_out} > allowed {max_allowed} (subsidy {get_block_subsidy(height)} + fees {total_fees}) at height {height}"
            logger.error(f"Block validation failed: {reason}")
            return False, reason

    return True, "Valid"

def validate_transaction(tx, utxo_set, is_coinbase=False, chained_utxos=None, height=None):
    """
    Validate a single transaction.

    Returns (is_valid, reason, fee) where `fee` = total_in - total_out (0 for coinbase
    and for context-free checks). `height`, when given, enables the coinbase-maturity
    rule (a coinbase output cannot be spent until COINBASE_MATURITY blocks later).
    """
    # Basic Checks
    if not tx.vin and not is_coinbase:
        reason = "Tx validation failed: No inputs and not coinbase"
        logger.error(reason)
        return False, reason, 0
    if not tx.vout:
        reason = "Tx validation failed: No outputs"
        logger.error(reason)
        return False, reason, 0

    if is_coinbase:
        # The coinbase has no real inputs; its payout cap is checked by validate_block
        # (subsidy + fees), so there is no fee to report here.
        return True, "Valid Coinbase", 0

    # Check Inputs
    if utxo_set is None:
        # Context-free check only (structure)
        return True, "Valid Structure", 0

    total_in = 0
    for i, txin in enumerate(tx.vin):
        # Look up UTXO
        prev_hash_hex = txin.prev_hash.hex()

        # 1. Check Chained UTXOs (Intra-block)
        utxo = None
        if chained_utxos and (prev_hash_hex, txin.prev_index) in chained_utxos:
             utxo = chained_utxos[(prev_hash_hex, txin.prev_index)]

        # 2. Check Database
        if not utxo:
             utxo = utxo_set.get_utxo(prev_hash_hex, txin.prev_index)

        if not utxo:
            # Input does not exist or is already spent
            reason = f"Input {prev_hash_hex}:{txin.prev_index} not found/spent"
            logger.error(f"Tx validation failed: {reason}")
            return False, reason, 0

        # Coinbase maturity: freshly-mined coins are locked for COINBASE_MATURITY blocks.
        if height is not None and utxo.get('is_coinbase'):
            confirmations = height - utxo.get('block_height', 0)
            if confirmations < COINBASE_MATURITY:
                reason = (f"Coinbase input {prev_hash_hex}:{txin.prev_index} is immature "
                          f"({confirmations}/{COINBASE_MATURITY} confirmations)")
                logger.error(f"Tx validation failed: {reason}")
                return False, reason, 0

        total_in += utxo['amount']

    # Check Amounts (Input >= Output)
    total_out = sum(out.amount for out in tx.vout)
    if total_out > total_in:
        reason = f"Output total {total_out} exceeds input {total_in}"
        logger.error(f"Tx validation failed: {reason}")
        return False, reason, 0

    return True, "Valid", total_in - total_out
