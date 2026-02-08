import os
import struct

class BlockStore:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.blocks_dir = os.path.join(data_dir, 'blocks')
        os.makedirs(self.blocks_dir, exist_ok=True)
        self.current_file_num = 0
        self.current_offset = 0
        self._init_state()

    def _init_state(self):
        """Determine the current file number and offset by scanning existing files."""
        existing_files = [f for f in os.listdir(self.blocks_dir) if f.startswith('blk') and f.endswith('.dat')]
        if not existing_files:
            self.current_file_num = 0
            self.current_offset = 0
            return

        existing_files.sort()
        last_file = existing_files[-1]
        try:
            self.current_file_num = int(last_file[3:8])
            self.current_offset = os.path.getsize(os.path.join(self.blocks_dir, last_file))
        except ValueError:
            self.current_file_num = 0
            self.current_offset = 0

    def get_file_path(self, file_num):
        return os.path.join(self.blocks_dir, f"blk{file_num:05d}.dat")

    def write_block(self, block_bytes):
        """
        Write serialized block bytes to disk.
        Returns: (file_num, offset)
        """
        # Rollover if > 128MB
        if self.current_offset > 128 * 1024 * 1024:
            self.current_file_num += 1
            self.current_offset = 0

        file_path = self.get_file_path(self.current_file_num)
        mode = 'ab' if os.path.exists(file_path) else 'wb'

        with open(file_path, mode) as f:
            start_offset = f.tell()
            if start_offset != self.current_offset:
                self.current_offset = start_offset
            
            f.write(block_bytes)
            f.flush()
            bytes_written = len(block_bytes)
            
            location = (self.current_file_num, self.current_offset)
            self.current_offset += bytes_written
            
            return location

    def read_block(self, file_num, offset, length):
        """Read a raw block from disk given its location."""
        file_path = self.get_file_path(file_num)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Block file {file_path} not found")
            
        with open(file_path, 'rb') as f:
            f.seek(offset)
            data = f.read(length)
            if len(data) < length:
                raise EOFError("Unexpected end of block file")
            return data
