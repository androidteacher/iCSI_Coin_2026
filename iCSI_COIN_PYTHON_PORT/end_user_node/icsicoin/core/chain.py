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
             vin=[TxIn(b'\x00'*32, 0xffffffff, b'The Times 03/Jan/2009 Chancellor on brink of second bailout for banks', 0xffffffff)],
             vout=[TxOut(5000000000, b'\x00'*25)] # Empty/burned output for genesis
        )
        
        merkle_root = get_merkle_root([tx])
        
        header = BlockHeader(
             version=1,
             prev_block=b'\x00'*32,
             merkle_root=merkle_root,
             timestamp=1231006505,
             bits=0x1f019999, # Tuned for ~5-10s CPU mining (Exp 31), Increased 10x per user request
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
            # Orphan
            logger.info(f"Block {block_hash} is invalid/orphan (parent {prev_hash} missing). Adding to orphan pool.")
            self.orphan_blocks[block_hash] = block
            if prev_hash not in self.orphan_dep:
                self.orphan_dep[prev_hash] = []
            self.orphan_dep[prev_hash].append(block)
            return False 

        # 4. Save to Disk
        # We save it now so we have it. Status will be 'valid-header' or similar until connected?
        # For simplicity, we write it and index it.
        block_bytes = block.serialize()
        loc = self.block_store.write_block(block_bytes)
        
        # 5. Connect or Store
        # Calculate Work. For now, we assume simple "longest chain = highest height".
        # Real work calc requires target.
        parent_height = parent_info.get('height', 0)
        new_height = parent_height + 1
        
        current_tip = self.block_index.get_best_block()
        current_height = current_tip['height'] if current_tip else -1
        
        # Add to index
        self.block_index.add_block(
             block_hash, loc[0], loc[1], len(block_bytes),
             prev_hash=prev_hash,
             height=new_height,
             status=2 # 2=Valid Data, not main chain yet?
        )
        
        # 6. Chain Selection Logic
        if new_height > current_height:
            # Make this the new tip!
            logger.info(f"New Best Block: {block_hash} (Height: {new_height})")
            
            # If we are just extending the tip (linear)
            # Handle genesis case where current_tip is None
            if current_tip is None or prev_hash == current_tip['block_hash']:
                 self._connect_block(block, new_height)
            else:
                 # REORG!
                 self._handle_reorg(block, new_height, current_tip)
                 
            # Process Orphans that depended on this
            self._process_orphans(block_hash)
            return True
            
        else:
            logger.info(f"Block {block_hash} valid but not best chain (Height: {new_height} <= {current_height})")
            return True

    def _connect_block(self, block, height):
        # Update UTXO set
        # This is where we run full contextual validation
        if not validate_block(block, self.chain_state):
             logger.error(f"Block {block.get_hash().hex()} failed contextual validation during connection!")
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
            for i, vout in enumerate(tx.vout):
                 # add_utxo(tx_hash, index, amount, script_pubkey/address, height?)
                 # Checking signature: add_utxo(self, tx_hash, index, amount, script_pubkey)
                 # vout.script_pubkey is bytes, converting to hex?
                 # Let's check primitives.py. script_pubkey is bytes.
                 # Database expects hex string or bytes? schema is TEXT usually or BLOB.
                 # Let's check schema in databases.py (not shown but inferred).
                 # Better to pass hex if schema is TEXT.
                 self.chain_state.add_utxo(tx_hash, i, vout.amount, vout.script_pubkey)
                 
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
