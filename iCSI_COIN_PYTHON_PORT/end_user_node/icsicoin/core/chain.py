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

    def get_best_height(self):
        """Returns the height of the current best block tip."""
        best = self.block_index.get_best_block()
        return best['height'] if best else 0

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
             
             if prev_hash not in self.orphan_dep:
                 self.orphan_dep[prev_hash] = []
             self.orphan_dep[prev_hash].append(block)
             
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
                        
                        # Process orphans for the NEW tip (which is now best)
                        self._process_orphans(block_hash)
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

                        # Check if any orphans were waiting for this side-chain block
                        self._process_orphans(block_hash)

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
            
            # ATOMIC UPDATE: Index + Head Pointer
            self.block_index.add_block_atomic(block_hash, file_num, offset, len(data), block.header.prev_block.hex(), height, status=3, is_best=True)
            logger.info(f"Block {block_hash} connected at height {height}")
            
            # Check for orphans waiting for this block
            self._process_orphans(block_hash)
            
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
                 
        # Update Best Block in Index - REMOVED (Moved to atomic add_block in process_block)
        # self.block_index.update_best_block(block.get_hash().hex())
        
        # New: Update status to 3 (Main Chain) - REMOVED (Moved to atomic add_block)
        # self.block_index.update_block_status(block.get_hash().hex(), 3)
        
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


    def check_integrity(self):
        """
        Scans the Block Index and validates that every block pointer points to a valid file location
        whose header hash matches the database. This detects manual file overwrites and corruption.
        Returns: {'status': 'ok'|'corrupt', 'message': str, 'bad_block': height|None}
        """
        logger.info("Starting Database Integrity Check...")
        try:
            import hashlib
            
            # Cache file handles to avoid opening/closing constantly
            file_handles = {} 
            
            error_report = None
            
            count = 0
            # Iterate all blocks
            # We use the generator from DB
            for b_hash, file_num, offset, height in self.block_index.get_all_block_locations():
                count += 1
                
                # Open file if not open
                if file_num not in file_handles:
                    file_path = self.block_store.get_file_path(file_num)
                    try:
                        file_handles[file_num] = open(file_path, 'rb')
                    except FileNotFoundError:
                        error_report = {
                            'status': 'corrupt',
                            'message': f"Block file for height {height} (blk{file_num:05d}.dat) is missing!",
                            'bad_block': height
                        }
                        break
                
                f = file_handles[file_num]
                f.seek(offset)
                # Read 80 bytes (Block Header)
                header_bytes = f.read(80)
                
                if len(header_bytes) < 80:
                    error_report = {
                        'status': 'corrupt',
                        'message': f"Block {height}: Incomplete header at offset {offset}",
                        'bad_block': height
                    }
                    break

                # Calculate Hash: SHA256(SHA256(header))
                # Note: b_hash in DB is usually hex string. header hash is bytes.
                # We need to match endianness. 
                # iCSI Coin uses standard double-sha256. 
                # The DB hex string is likely Big-Endian or Little-Endian depending on storage.
                # But 'b_hash' from get_all_block_locations comes from the DB TEXT column.
                # In 'header.py' or 'hashing.py', the hash is reversed for display?
                # Usually: Internal = Bytes, Display = Hex(Reverse(Bytes)).
                # But this Python port might store it as Hex string directly.
                # Let's try both matches.
                
                h1 = hashlib.sha256(header_bytes).digest()
                h2 = hashlib.sha256(h1).digest()
                
                # Standard Bitcoin: Internal is LE, Display is BE. Or vice versa.
                # But let's look at `chain.py`: b_hash is used as a key.
                # If I calculate the hash of the header, it should equal the block hash.
                
                calc_hash_hex = h2[::-1].hex() # Try LE->BE flip first (Standard)
                calc_hash_hex_raw = h2.hex()   # Try Raw
                
                # b_hash is string from DB
                if calc_hash_hex != b_hash and calc_hash_hex_raw != b_hash:
                     # One last check: Maybe b_hash is header + something? No, header hash is block hash.
                     # Wait, Genesis? 
                     # If it mismatches, it's corrupt.
                     
                    logger.critical(f"INTEGRITY FAILURE: Block {height} Hash Mismatch.")
                    logger.critical(f"DB Hash: {b_hash}")
                    logger.critical(f"File Hash (Flip): {calc_hash_hex}")
                    logger.critical(f"File Hash (Raw): {calc_hash_hex_raw}")
                    
                    error_report = {
                        'status': 'corrupt',
                        'message': f"Integrity Failure at Block {height}. Block Hash mismatch (File Content != Database Index).",
                        'bad_block': height
                    }
                    break
            
            # Cleanup
            for fh in file_handles.values():
                fh.close()
                
            if error_report:
                return error_report
                
            logger.info(f"Integrity Check Passed. Scanned {count} blocks.")
            return {'status': 'ok', 'message': f"Integrity Verified. Scanned {count} blocks.", 'bad_block': None}
            
        except Exception as e:
            logger.error(f"Integrity Check Error: {e}")
            return {'status': 'error', 'message': str(e), 'bad_block': None}

    def get_network_hashrate(self, blocks=10):
        """
        Calculates estimated network hashrate based on the last N blocks.
        Formula: (Sum(Difficulty) * 2^32) / (Time_Tip - Time_Tip_Minus_N)
        Returns hashrate in H/s.
        """
        try:
            tip = self.block_index.get_best_block()
            if not tip or tip['height'] < blocks:
                # Not enough blocks for a window, allow smaller window if > 1
                if tip and tip['height'] > 1:
                    blocks = tip['height']
                else:
                    return 0
            
            # Get Tip Info
            tip_height = tip['height']
            start_height = tip_height - blocks
            
            # To be accurate and robust, we MUST fetch the headers.
            # If they are not in the index cache, we read from disk.
            header_tip = self.get_block_header(tip_height)
            if header_tip is None:
                 # Fallback: Try to force read from storage if we have location info
                 tip_idx = self.block_index.get_block(tip['block_hash'])
                 if tip_idx:
                     header_tip = self.block_store.read_block_header(tip_idx['file_num'], tip_idx['offset'])

            header_start = self.get_block_header(start_height)
            if header_start is None:
                # Find the hash for start_height first (expensive sweep?)
                # Actually get_block_header(height) should do this.
                # If it failed, we might need to look up hash by height if supported, 
                # but block_index usually supports get_block_by_height?
                # Looking at source, get_block_header calls self.block_index.get_block_by_height(height)
                # If it returns None, we are stuck.
                pass

            if not header_tip or not header_start:
                return 0
                
            time_delta = header_tip.timestamp - header_start.timestamp
            
            if time_delta <= 0:
                return 0
                
            difficulty = header_tip.difficulty 
            
            # Formula: H/s = (Difficulty * 2^32) / (Average Block Time)
            avg_time = time_delta / blocks
            if avg_time == 0: return 0
            
            hashrate = (difficulty * (2**32)) / avg_time
            return hashrate
            
        except Exception as e:
            logger.error(f"Hashrate Calc Error: {e}")
            return 0

    def get_block_header(self, height):
        # Helper to get header object by height
        b_hash = self.block_index.get_block_hash_by_height(height)
        if not b_hash: return None
        # We need to read from disk.
        # This mirrors check_integrity logic but returns object.
        # Ideally this should be in BlockStore or ChainManager.
        # For now, implemented simply:
        loc = self.block_index.get_block_location(b_hash) # Need this method in DB
        if not loc: return None
        file_num, offset, _ = loc
        try:
            data = self.block_store.read_block(file_num, offset, 80)
            from icsicoin.core.primitives import BlockHeader
            import io
            return BlockHeader.deserialize(io.BytesIO(data))
        except:
            return None

    def get_block_locator(self):
        """
        Creates a block locator (list of hashes) starting from the tip,
        going back densely then exponentially.
        """
        locator = []
        best = self.block_index.get_best_block()
        if not best:
            # Genesis fallback
            return [self.get_block_hash(0)]
            
        current_height = best['height']
        step = 1
        h = current_height
        
        while h > 0:
            b_hash = self.get_block_hash(h)
            if b_hash:
                locator.append(b_hash)
            
            # Dense for first 10, then exponential
            if len(locator) > 10:
                step *= 2
            
            h -= step
            
        # Always include genesis
        genesis = self.get_block_hash(0)
        if genesis:
            if not locator or locator[-1] != genesis:
                locator.append(genesis)

            
        return locator
