
import unittest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock scrypt
sys.modules['scrypt'] = MagicMock()

from icsicoin.network.manager import NetworkManager
from icsicoin.network.messages import VersionMessage, Message

class TestPeerMetadata(unittest.TestCase):
    def setUp(self):
        self.manager = NetworkManager(
            port=9333, bind_address='127.0.0.1', 
            add_nodes=[], connect_nodes=[], rpc_port=9332,
            data_dir='/tmp/test_peer_metadata'
        )
        self.manager.active_connections = {}
        self.manager.peer_stats = {}
        self.manager.log_peer_event = MagicMock()

    def tearDown(self):
        import shutil
        if os.path.exists('/tmp/test_peer_metadata'):
            shutil.rmtree('/tmp/test_peer_metadata')

    async def async_test_outgoing_handshake_metadata(self):
        """Test that outgoing connection captures height from Version message."""
        # Setup mock reader/writer
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        # get_extra_info is synchronous, so we use a standard Mock/MagicMock or set return_value on the AsyncMock 
        # BUT AsyncMock makes it a coroutine. We must replace it.
        mock_writer.get_extra_info = MagicMock(return_value=('1.2.3.4', 9333))
        
        # Mock asyncio.open_connection
        # We need to mock the socket interaction in connect_to_peer
        # connect_to_peer is complex, so we might test the logic block in isolation 
        # OR we can just simulate the reader yielding the right bytes.
        
        # Construct a real Version message to parse
        remote_ver = VersionMessage(start_height=12345, user_agent='/Satoshi:0.1/')
        serialized_ver = remote_ver.serialize()
        
        # We need to simulate the read sequence:
        # 1. Header (24 bytes)
        # 2. Payload (len)
        # 3. Verack Header (24 bytes) -> Validation logic in manager expects this
        
        # Split header and payload
        header = serialized_ver[:24]
        payload = serialized_ver[24:]
        
        # Verack
        from icsicoin.network.messages import VerackMessage
        verack = VerackMessage().serialize()
        verack_header = verack[:24]
        
        # Mock reads
        # calls: read(24) [ver header], read(len) [ver payload], read(24) [verack header]
        mock_reader.read.side_effect = [
            header,
            payload,
            verack_header
        ]
        
        # Mock connect_to_peer internals
        # Since we can't easily mock open_connection inside the method without patching the class or module,
        # we will patch asyncio.open_connection
        
        with unittest.mock.patch('asyncio.open_connection', return_value=(mock_reader, mock_writer)):
            # We also need to mock manager.process_message_loop to return immediately
            self.manager.process_message_loop = AsyncMock()
            self.manager.send_getblocks = AsyncMock()
            
            await self.manager.connect_to_peer("1.2.3.4:9333")
            
            # Verify peer_stats
            target = ('1.2.3.4', 9333)
            self.assertIn(target, self.manager.peer_stats)
            stats = self.manager.peer_stats[target]
            
            self.assertEqual(stats['height'], 12345)
            self.assertEqual(stats['user_agent'], '/Satoshi:0.1/')
            
    def test_metadata_capture(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.async_test_outgoing_handshake_metadata())
        loop.close()

if __name__ == '__main__':
    unittest.main()
