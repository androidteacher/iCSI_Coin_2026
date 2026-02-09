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

    def get_block_locator(self):
        """
        Construct a block locator (list of hashes) to help a peer find the most recent common ancestor.
        Strategy: Dense at first, then exponential back-off (1, 2, 4, 8...).
        """
        locator = []
        best_block = self.block_index.get_best_block()
        if not best_block:
            return [self.genesis_block.get_hash().hex()]
            
        current_height = best_info = best_block['height']
        step = 1
        
        while current_height > 0:
            block_hash = self.get_block_hash(current_height)
            if block_hash:
                locator.append(block_hash)
            
            # Stop if we have enough or hit genesis (approx 32 items covers full history usually)
            if len(locator) > 32:
                break
                
            # Apply step (Exponential backoff)
            # First 10 blocks are dense (step=1)
            # Then double the step
            if len(locator) > 10:
                step *= 2
                
            current_height -= step
            
        # Always include Genesis as the final fallback
        genesis_hash = self.genesis_block.get_hash().hex()
        if not locator or locator[-1] != genesis_hash:
            locator.append(genesis_hash)
            
        return locator

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
            return False, "Already known"

        # 2. Basic Validation (PoW, Structure) - Context-free checks
        # We assume caller might have done some, but good to be safe.
        # However, full validation (utxo) happens at connection time.
        # We pass chain_state=None to validate_block for context-free checks only?
        # Our current validate_block includes everything. We might need to split it.
        # For now, let's assume validate_block does what it can.
        is_valid, reason = validate_block(block, None) # Validate context-free first
        if not is_valid:
             logger.warning(f"Block {block_hash} failed context-free validation: {reason}")
             return False, reason

        # 3. Check Parent
        prev_hash = block.header.prev_block.hex()
        # Genesis special case: if prev_hash is 00..00 and we have no blocks? 
        # Actually genesis should already be loaded or handled. 
        
        parent_info = self.block_index.get_block_info(prev_hash)
        
        if not parent_info:
             logger.warning(f"Orphan block detected: {block_hash} (Parent {prev_hash} unknown)")
             self.orphan_blocks[block_hash] = block
             return False, "Orphan block"

        # 3. Connect to Chain (State Updates)
        # We need to determine if this extends the longest chain.
        # For Phase 5, we assume linear extension of current tip.
        # Check Prev Hash
        best_block = self.block_index.get_best_block()
        if best_block:
            prev_hash = block.header.prev_block.hex()
            if prev_hash != best_block['block_hash']:
                # Fork detected
                # Check if this fork is longer/has more work
                # For Phase 5, just height.
                
                # We need the height of this new block.
                # Since we don't have it yet, we check the parent's height.
                parent_info = self.block_index.get_block_info(prev_hash)
                if parent_info:
                    new_height = parent_info['height'] + 1
                    current_height = best_block['height']
                    
                    if new_height > current_height:
                        logger.info(f"Longer chain found! Current: {current_height}, New: {new_height}. Triggering Reorg.")
                        self._handle_reorg(block, new_height, best_block)
                        return True, "Reorg Success"
                    else:
                        logger.info(f"Fork detected but shorter/equal ({new_height} vs {current_height}). Ignoring for now.")
                        # Special Path: Store Side Chain Block
                        data = block.serialize()
                        file_num, offset = self.block_store.write_block(data)
                        self.block_index.add_block(block_hash, file_num, offset, len(data), block.header.prev_block.hex(), new_height, status=2) # Status 2 = Valid Data
                        
                        # Also index transactions!
                        for tx in block.vtx:
                            self.block_index.add_transaction(tx.get_hash().hex(), block_hash)

                        return True, "Fork Stored"
                else:
                     # This should be caught by "Check Parent" above, but just in case
                     return False, f"Orphan block (prev={prev_hash[:8]} not found)"
                
        # 4. Connect
        # Determine height for the new block
        height = (best_block['height'] + 1) if best_block else 0
        
        success, reason = self._connect_block(block, height)
        if success:
            # 5. Store Block Body (Disk)
            # Serialize
            data = block.serialize()
            file_num, offset = self.block_store.write_block(data)
            
            # 6. Index It
            # Height is Best + 1
            
            self.block_index.add_block(block_hash, file_num, offset, len(data), block.header.prev_block.hex(), height, status=3)
            logger.info(f"Block {block_hash} connected at height {height}")
            return True, "Accepted"
            
        return False, f"Connect failed: {reason}"

    def _connect_block(self, block, height):
        # Update UTXO set
        # This is where we run full contextual validation
        is_valid, reason = validate_block(block, self.chain_state)
        if not is_valid:
             logger.error(f"Block {block.get_hash().hex()} failed contextual validation: {reason}")
             # Mark invalid?
             return False, reason
             
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
        
        # Populate Tx Index
        block_hash = block.get_hash().hex()
        for tx in block.vtx:
            self.block_index.add_transaction(tx.get_hash().hex(), block_hash)
            
        return True, "Connected"

    def _disconnect_block(self, block):
        logger.info(f"Disconnecting block {block.get_hash().hex()}")
        
        # 1. Reverse Transactions (Right to Left)
        for tx in reversed(block.vtx):
            tx_hash = tx.get_hash().hex()
            
            # A. Remove Outputs created by this block
            for i, _ in enumerate(tx.vout):
                self.chain_state.remove_utxo(tx_hash, i)
                
            # B. Restore Inputs spent by this block
            if not tx.is_coinbase():
                for vin in tx.vin:
                     prev_txid = vin.prev_hash.hex()
                     prev_out_idx = vin.prev_index
                     
                     # Find which block contains this previous transaction
                     source_block_hash = self.block_index.get_transaction_block_hash(prev_txid)
                     
                     if source_block_hash:
                         source_block = self.get_block_by_hash(source_block_hash)
                         if source_block:
                             # Find the tx in that block
                             original_tx = next((t for t in source_block.vtx if t.get_hash().hex() == prev_txid), None)
                             if original_tx and prev_out_idx < len(original_tx.vout):
                                 out = original_tx.vout[prev_out_idx]
                                 # Restore UTXO
                                 # We need the block height of the source block
                                 source_info = self.block_index.get_block_info(source_block_hash)
                                 height = source_info['height'] if source_info else 0
                                 
                                 self.chain_state.add_utxo(
                                     prev_txid, 
                                     prev_out_idx, 
                                     out.amount, 
                                     out.script_pubkey, 
                                     height, 
                                     original_tx.is_coinbase()
                                 )
                             else:
                                 logger.error(f"Could not find tx {prev_txid} in block {source_block_hash} during rollback")
                         else:
                             logger.error(f"Could not load source block {source_block_hash} during rollback")
                     else:
                         # Fallback: Maybe it's in the mempool? No, blocks only spend confirmed (usually).
                         # Or we just don't have the index for it yet (old block).
                         logger.critical(f"CRITICAL: Could not find block for input {prev_txid} during rollback. UTXO Set may be corrupt.")
                         
        # Update Best Block to Parent
        prev = block.header.prev_block.hex()
        self.block_index.update_best_block(prev)
        
        # Revert status to 2 (Valid Header/Data, but not active chain)
        self.block_index.update_block_status(block.get_hash().hex(), 2)


    def _handle_reorg(self, new_tip_block, new_height, old_tip_info):
        old_hash = old_tip_info['block_hash'] if old_tip_info else "None"
        new_hash = new_tip_block.get_hash().hex()
        logger.warning(f"REORG START: {old_hash} -> {new_hash}")
        
        # 1. Find Common Ancestor
        fork_hash, path_to_new = self._find_fork(new_tip_block, old_tip_info)
        
        if not fork_hash:
            logger.error("Reorg failed: Could not find common ancestor (Genesis mismatch?)")
            return
            
        logger.info(f"Reorg Common Ancestor: {fork_hash}")
        
        # 2. Disconnect Old Chain (Old Tip -> Fork exclusive)
        curr = old_hash
        while curr != fork_hash:
             block_to_disconnect = self.get_block_by_hash(curr)
             if not block_to_disconnect:
                 logger.critical(f"Could not load block {curr} during reorg disconnect!")
                 break
             
             self._disconnect_block(block_to_disconnect)
             # Move to parent
             curr = block_to_disconnect.header.prev_block.hex()

        # 3. Connect New Chain (Fork -> New Tip)
        # path_to_new is [Fork+1, ..., NewTip]
        for b in path_to_new:
             b_hash = b.get_hash().hex()
             parent_hash = b.header.prev_block.hex()
             
             # Get parent height to determine this block's height
             parent_info = self.block_index.get_block_info(parent_hash)
             h = (parent_info['height'] + 1) if parent_info else 0
             
             self._connect_block(b, h)
             
             if b == new_tip_block:
                 # This is the new tip we haven't stored yet.
                 data = b.serialize()
                 file_num, offset = self.block_store.write_block(data)
                 self.block_index.add_block(b_hash, file_num, offset, len(data), parent_hash, h, status=3)
             else:
                 # Intermediate block, should be on disk/index already?
                 pass

        logger.info("REORG COMPLETE")


    def _find_fork(self, new_tip_block, old_tip_info):
        """
        Returns (fork_hash, [block_objects_from_fork_to_new])
        """
        # Load new chain path backwards
        new_chain = []
        curr_block = new_tip_block
        
        while True:
             block_hash = curr_block.get_hash().hex()
             
             # Check if this block exists and is active?
             info = self.block_index.get_block_info(block_hash)
             if info and info['status'] == 3:
                 return block_hash, list(reversed(new_chain))
             
             new_chain.append(curr_block)
             
             prev_hash = curr_block.header.prev_block.hex()
             parent = self.get_block_by_hash(prev_hash)
             
             if not parent:
                 # Check genesis in index
                 p_info = self.block_index.get_block_info(prev_hash)
                 if p_info and p_info['status'] == 3:
                      return prev_hash, list(reversed(new_chain))
                 
                 # If we hit Genesis hash hardcoded
                 if prev_hash == '00'*32: 
                      # This shouldn't happen if genesis is indexed
                      return None, None
                 
                 return None, None
                 
             curr_block = parent

    def _process_orphans(self, parent_hash):
        if parent_hash in self.orphan_dep:
            orphans = self.orphan_dep[parent_hash]
            del self.orphan_dep[parent_hash]
            for b in orphans:
                self.process_block(b)
