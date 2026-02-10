
import unittest
from unittest.mock import MagicMock
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.modules['scrypt'] = MagicMock()

from icsicoin.core.chain import ChainManager
from icsicoin.core.primitives import Block, BlockHeader

class TestOrphanLogic(unittest.TestCase):
    def setUp(self):
        self.mock_store = MagicMock()
        self.mock_index = MagicMock()
        self.mock_state = MagicMock()
        
        # Setup Genesis for init
        self.mock_index.get_best_block.return_value = {'block_hash': '00'*32, 'height': 0}
        self.mock_index.get_block_info.return_value = {'status': 3, 'height': 0}
        self.mock_store.write_block.return_value = (1, 100)
        
        self.chain = ChainManager(self.mock_store, self.mock_index, self.mock_state)
        # Mock validation to always pass context-free
        # We need to mock validate_block imported in chain.py
        # But for now we can rely on integration style or just mock _connect_block internally if needed?
        # Actually easier to mock the global validate_block
        
    def test_orphan_resolution(self):
        """Test that adding Parent resolves Orphan Child"""
        
        # Parent Block (A)
        parent_hash = 'a' * 64
        block_a = MagicMock()
        block_a.get_hash.return_value.hex.return_value = parent_hash
        block_a.header.prev_block.hex.return_value = '00'*32 # Point to genesis
        block_a.header.timestamp = 12345
        
        # Child Block (B)
        child_hash = 'b' * 64
        block_b = MagicMock()
        block_b.get_hash.return_value.hex.return_value = child_hash
        block_b.header.prev_block.hex.return_value = parent_hash # Point to A
        block_b.header.timestamp = 12346

        # Mock dependencies for processing
        # 1. Block B comes first. Parent A is unknown.
        self.mock_index.get_block_info.side_effect = lambda h: None if h == parent_hash else {'status': 3} if h=='00'*32 else None
        
        # Mock validate_block to pass
        with unittest.mock.patch('icsicoin.core.chain.validate_block', return_value=(True, "OK")):
            # Process Child B -> Should be orphaned
            self.chain.process_block(block_b)
            
            self.assertIn(child_hash, self.chain.orphan_blocks)
            self.assertIn(parent_hash, self.chain.orphan_dep)
            self.assertIn(block_b, self.chain.orphan_dep[parent_hash])
            
            # Now Process Parent A -> Should trigger B
            # We need to reset get_block_info to acknowledge A exists after it's added? 
            # The ChainManager logic calls _connect_block -> update_best_block.
            # But process_block checks get_block_info(prev) internally.
            
            # When A is processed, it connects. Then _process_orphans(A) is called.
            # It finds B in orphan_dep[A]. Calls process_block(B).
            # Inside process_block(B), it does get_block_info(A). 
            # We need our mock index to respond correctly "Yes A exists now".
            
            # Complex mocking of state change. 
            # Let's mock _connect_block to return True and NOT rely on the index for the recursive call check?
            # Or assume logic works if we see it call _process_orphans?
            
            # Let's spy on process_block to see if it's called recursively?
            # No, let's just inspect orphan_dep. If logic works, B should be processed and removed from orphan_dep.
            
            # We need to ensure the recursive process_block(B) sees 'A' as known.
            # We can use a side_effect on get_block_info that checks a local set?
            
            known_blocks = {'00'*32}
            def mock_get_info(h):
                if h in known_blocks:
                    return {'status': 3, 'height': 0 if h=='00'*32 else 1, 'block_hash': h}
                return None
                
            self.mock_index.get_block_info.side_effect = mock_get_info
            
            # Pre-add genesis
            # known_blocks is set
            
            # Process B (A unknown)
            self.chain.process_block(block_b)
            
            # Check Orphan State
            self.assertIn(parent_hash, self.chain.orphan_dep)
            
            # Process A
            # This should trigger B
            # _connect_block mock needs to add A to known_blocks so B sees it!
            
            original_connect = self.chain._connect_block
            def side_effect_connect(blk, height):
                known_blocks.add(blk.get_hash().hex())
                return True, "Connected"
            
            self.chain._connect_block = side_effect_connect
            self.mock_index.get_best_block.return_value = {'height': 0, 'block_hash': '00'*32}
            
            # Process A
            self.chain.process_block(block_a)
            
            # Assertions
            # Orphan dep for A should be gone
            self.assertNotIn(parent_hash, self.chain.orphan_dep)
            
            # B should have been processed (and thus verify it was "connected")
            # Since we didn't mock "connected" completely, we can verify B is now in "known_blocks" due to our side_effect
            self.assertIn(child_hash, known_blocks, "Block B should have been connected recursively")

if __name__ == '__main__':
    unittest.main()
