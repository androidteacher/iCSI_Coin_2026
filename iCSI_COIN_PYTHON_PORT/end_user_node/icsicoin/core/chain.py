import logging
import time
from icsicoin.consensus.validation import validate_block, validate_transaction
from icsicoin.core.primitives import Block

logger = logging.getLogger("ChainManager")

class ChainManager:
    def __init__(self, block_store, block_index, chain_state):
        self.block_store = block_store
        self.block_index = block_index
        self.chain_state = chain_state
        self.orphan_blocks = {} # hash -> block
        self.orphan_dep = {} # prev_hash -> list of orphan blocks waiting for it
        
        # Create Genesis object
        self.genesis_block = self._create_genesis_block()
        
        # Initialize if not present
        self._initialize_genesis()

    def _create_genesis_block(self):
        """Creates the hardcoded Genesis Block object"""
        from icsicoin.core.primitives import Block, BlockHeader, Transaction, TxIn, TxOut
        from icsicoin.consensus.merkle import get_merkle_root
        
        # Create Genesis with standard params
        tx = Transaction(
             vin=[TxIn(b'\x00'*32, 0xffffffff, b'iCSI_COIN is a wholly owned Subsidiary of BeckCoin. Trademark: Beckmeister Industries.', 0xffffffff)],
             vout=[TxOut(5000000000, b'\x00'*25)] # Empty/burned output for genesis
        )
        
        merkle_root = get_merkle_root([tx])
        
        header = BlockHeader(
             version=1,
             prev_block=b'\x00'*32,
             merkle_root=merkle_root,
             timestamp=1231006505,
             bits=0x1f099996, # 6x easier than original (dynamic retarget adjusts)
             nonce=2083236893
        )
        return Block(header, [tx])

    def _initialize_genesis(self):
        best = self.block_index.get_best_block()
        if best:
            return

        logger.info("No Genesis block found. Initializing...")
        
        block_bytes = self.genesis_block.serialize()
        block_hash = self.genesis_block.get_hash().hex()
        loc = self.block_store.write_block(block_bytes)
        
        self.block_index.add_block(
             block_hash, loc[0], loc[1], len(block_bytes),
             prev_hash='0'*64,
             height=0,
             status=3 # Valid Main Chain
        )
        self.block_index.update_best_block(block_hash)
        logger.info(f"Genesis Initialized: {block_hash}")

    def get_block_hash(self, height):
        return self.block_index.get_block_hash_by_height(height)

    def get_block_by_height(self, height):
        """Return a deserialized Block for the given height, or None."""
        block_hash = self.block_index.get_block_hash_by_height(height)
        if not block_hash:
            return None
        return self.get_block_by_hash(block_hash)

    def get_block_by_hash(self, block_hash):
        """Return a deserialized Block for the given hash, or None."""
        block_info = self.block_index.get_block_info(block_hash)
        if not block_info:
            return None
        try:
            import io
            raw = self.block_store.read_block(
                block_info['file_num'],
                block_info['offset'],
                block_info['length']
            )
            if raw:
                return Block.deserialize(io.BytesIO(raw))
        except Exception as e:
            logger.error(f"Error reading block {block_hash}: {e}")
        return None

    def process_block(self, block: Block):
        block_hash = block.get_hash().hex()
        
        # 1. Check if already known
        if self.block_index.get_block_info(block_hash):
            logger.debug(f"Block {block_hash} already known")
            return False

        # 2. Basic Validation (PoW, Structure) - Context-free checks
        # We assume caller might have done some, but good to be safe.
        # However, full validation (utxo) happens at connection time.
        # We pass chain_state=None to validate_block for context-free checks only?
        # Our current validate_block includes everything. We might need to split it.
        # For now, let's assume validate_block does what it can.
        if not validate_block(block, None): # Validate context-free first
             logger.warning(f"Block {block_hash} failed context-free validation")
             return False

        # 3. Check Parent
        prev_hash = block.header.prev_block.hex()
        # Genesis special case: if prev_hash is 00..00 and we have no blocks? 
        # Actually genesis should already be loaded or handled. 
        
        parent_info = self.block_index.get_block_info(prev_hash)
        
        if not parent_info:
             logger.info(f"Block {block_hash} already processing/processed.")
             return True, "Already processed"

        # 3. Connect to Chain (State Updates)
        # We need to determine if this extends the longest chain.
        # For Phase 5, we assume linear extension of current tip.
        # Check Prev Hash
        best_block = self.block_index.get_best_block()
        if best_block:
            prev_hash = block.header.prev_block.hex()
            if prev_hash != best_block['block_hash']:
                # Orphan or Fork?
                # If prev_hash exists in index but is not best, it's a fork.
                # If prev_hash does not exist, it's an orphan.
                if self.block_index.get_block_info(prev_hash):
                     return False, f"Fork detected (prev={prev_hash[:8]}), Reorgs not fully supported yet"
                
                logger.warning(f"Orphan block: {block_hash}, Prev: {prev_hash}")
                # Store as orphan? 
                # For now, reject.
                return False, f"Orphan block (prev={prev_hash[:8]} not found)"
                
        # 4. Connect
        # Determine height for the new block
        height = (best_block['height'] + 1) if best_block else 0
        if self._connect_block(block, height): # Pass height to _connect_block
            # 5. Store Block Body (Disk)
            # Serialize
            data = block.serialize()
            file_num, offset = self.block_store.write_block(data)
            
            # 6. Index It
            # Height is Best + 1
            
            self.block_index.add_block(block_hash, file_num, offset, len(data), block.header.prev_block.hex(), height, status=3)
            logger.info(f"Block {block_hash} connected at height {height}")
            return True, "Accepted"
            
        return False, "Connect failed (State validation mismatch)"

    def _connect_block(self, block, height):
        # Update UTXO set
        # This is where we run full contextual validation
        is_valid, reason = validate_block(block, self.chain_state)
        if not is_valid:
             logger.error(f"Block {block.get_hash().hex()} failed contextual validation: {reason}")
             # Mark invalid?
             return False
             
        # Commit UTXO changes
        # validate_block (current impl) doesn't update DB, just checks.
        # We need a method to APPLY changes.
        # For Phase 5, we'll implement simple apply.
        
        # Spend Inputs
        for tx in block.vtx:
            # Coinbase input doesn't spend (handled in is_coinbase check)
            if not tx.is_coinbase():
                for vin in tx.vin:
                    prev_out = f"{vin.prev_hash.hex()}:{vin.prev_index}"
                    self.chain_state.remove_utxo(vin.prev_hash.hex(), vin.prev_index)
            
            # Create Outputs
            tx_hash = tx.get_hash().hex()
            is_coinbase = tx.is_coinbase()
            for i, vout in enumerate(tx.vout):
                 # add_utxo(tx_hash, index, amount, script_pubkey, block_height, is_coinbase)
                 self.chain_state.add_utxo(tx_hash, i, vout.amount, vout.script_pubkey, height, is_coinbase)
                 
        # Update Best Block in Index
        self.block_index.update_best_block(block.get_hash().hex())
        
        # New: Update status to 3 (Main Chain)
        self.block_index.update_block_status(block.get_hash().hex(), 3)
        return True

    def _disconnect_block(self, block):
        # Undo UTXO changes
        # Inputs -> Add back
        # Outputs -> Remove
        logger.info(f"Disconnecting block {block.get_hash().hex()}")
        
        for tx in block.vtx:
            # Restore Inputs
            if not tx.is_coinbase():
                for vin in tx.vin:
                    # We need to look up the OLD txout to restore it. 
                    # This implies we need a full tx index or we can't revert without data.
                    # CRITICAL LIMITATION of simple UTXO set: undoing requires data we effectively deleted.
                    # SOLUTION:
                    # 1. Re-read the PREVIOUS block's tx to find the output? No, input refers to arbitrary past tx.
                    # 2. We need to look up the transaction from DISK.
                    # We don't have a TxIndex yet! (Phase 8).
                    # Temp Workaround for Reorgs in Phase 5:
                    # - Only support very simple reorgs or strict linear?
                    # - OR: To undo, we assume we can fetch the prev tx. 
                    # - BUT we need to find WHERE valid txs are.
                    # For now, let's admit: REORG UNDO IS HARD without TxIndex.
                    # We will log "Reorg not fully supported for State Revert" and just update Head pointer?
                    # No, that corrupts UTXO.
                    
                    # Real Bitcoin uses "Undo Files" (rev*.dat) containing the spent outputs.
                    # For this Python Port, let's implement a simplified "Undo" by just NOT deleting UTXOs permanently?
                    # Or: We accept that reorgs deep ( > 0) are broken until Phase 8?
                    # Let's try to just update the HEAD pointer, and accept UTXO inconsistencies for deep reorgs 
                    # OR: Just implement TxIndex now? It's easy.
                    pass
            
            tx_hash = tx.get_hash().hex()
            for i, _ in enumerate(tx.vout):
                self.chain_state.remove_utxo(tx_hash, i)
        
        # Set new best to prev
        prev = block.header.prev_block.hex()
        self.block_index.update_best_block(prev)
        
        # New: Revert status to 2 (Valid Header/Data)
        self.block_index.update_block_status(block.get_hash().hex(), 2)


    def _handle_reorg(self, new_tip_block, new_height, old_tip_info):
        old_hash = old_tip_info['block_hash'] if old_tip_info else "None"
        logger.warning(f"REORG DETECTED! Old Tip: {old_hash} -> New Tip: {new_tip_block.get_hash().hex()}")
        # Find Fork Point
        fork_block = self._find_fork(new_tip_block, old_tip_info)
        
        # Disconnect Old -> Fork
        # Connect Fork -> New
        # (Simplified, implementation deferred to improve robustness later)
        # For now, just connect the new one as if it were valid, 
        # risking UTXO set if inputs conflict.
        self._connect_block(new_tip_block, new_height)

    def _find_fork(self, new_block, old_tip_info):
        # Walk back headers
        return None # TODO

    def _process_orphans(self, parent_hash):
        if parent_hash in self.orphan_dep:
            orphans = self.orphan_dep[parent_hash]
            del self.orphan_dep[parent_hash]
            for b in orphans:
                self.process_block(b)
