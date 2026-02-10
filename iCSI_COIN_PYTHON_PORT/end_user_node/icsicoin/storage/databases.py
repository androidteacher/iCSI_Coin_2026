import sqlite3
import os
import os

class BlockIndexDB:
    def __init__(self, data_dir):
        self.db_path = os.path.join(data_dir, 'block_index.sqlite')
        self._init_db()
        self.repair_chain_pointer()

    def _init_db(self):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS block_index (
                    block_hash TEXT PRIMARY KEY,
                    file_num INTEGER,
                    offset INTEGER,
                    length INTEGER,
                    height INTEGER,
                    prev_hash TEXT,
                    status INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chain_info (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tx_index (
                    tx_hash TEXT PRIMARY KEY,
                    block_hash TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_height ON block_index (height)")
            conn.commit()

    def repair_chain_pointer(self):
        """
        SELF-HEAL: Check if chain_info pointer matches the actual max height in block_index.
        If we have blocks but the pointer is lost/old (e.g. crash), fast-forward it.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                # 1. Get Actual Max Height
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(height) FROM block_index")
                row = cursor.fetchone()
                max_height = row[0] if row and row[0] is not None else -1
                
                if max_height == -1:
                    return # Empty DB, nothing to repair
                    
                # 2. Get Current Head Pointer
                cursor.execute("SELECT value FROM chain_info WHERE key='best_block_hash'")
                row = cursor.fetchone()
                current_head_hash = row[0] if row else None
                
                # Check if we use 'value' or column name?
                # Previous CREATE TABLE said: key TEXT PRIMARY KEY, value TEXT
                # So we select value where key='best_block_hash'
                
                current_head_height = -1
                if current_head_hash:
                    cursor.execute("SELECT height FROM block_index WHERE block_hash=?", (current_head_hash,))
                    row = cursor.fetchone()
                    if row:
                        current_head_height = row[0]
                
                # 3. Compare and Repair
                if max_height > current_head_height:
                    print(f"[DB REPAIR] Detected Chain Pointer Corruption! Head: {current_head_height}, Actual Max: {max_height}")
                    # Find hash for max height
                    cursor.execute("SELECT block_hash FROM block_index WHERE height=?", (max_height,))
                    row = cursor.fetchone()
                    if row:
                        real_best_hash = row[0]
                        print(f"[DB REPAIR] Self-Healing: Updating Head Pointer to {real_best_hash} (Height {max_height})...")
                        
                        conn.execute("INSERT OR REPLACE INTO chain_info (key, value) VALUES ('best_block_hash', ?)", (real_best_hash,))
                        conn.commit()
                        print("[DB REPAIR] Database Integrity Restored.")
        except Exception as e:
            print(f"[DB REPAIR] Error verifying DB integrity: {e}")

    def add_block(self, block_hash, file_num, offset, length, prev_hash, height=0, status=1):
        """Add or update a block entry."""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO block_index 
                (block_hash, file_num, offset, length, prev_hash, height, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (block_hash, file_num, offset, length, prev_hash, height, status))
            conn.commit()
    def update_block_status(self, block_hash, status):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("UPDATE block_index SET status = ? WHERE block_hash = ?", (status, block_hash))
            conn.commit()

    def get_block_info(self, block_hash):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.execute("SELECT * FROM block_index WHERE block_hash = ?", (block_hash,))
            row = cursor.fetchone()
            if row:
                return {
                    'block_hash': row[0],
                    'file_num': row[1],
                    'offset': row[2],
                    'length': row[3],
                    'height': row[4],
                    'prev_hash': row[5],
                    'status': row[6]
                }
            return None
            
    def get_best_block(self):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.execute("SELECT value FROM chain_info WHERE key = 'best_block_hash'")
            row = cursor.fetchone()
            if row:
                return self.get_block_info(row[0])
            return None

    def update_best_block(self, block_hash):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("INSERT OR REPLACE INTO chain_info (key, value) VALUES ('best_block_hash', ?)", (block_hash,))
            conn.commit()

    def get_block_hash_by_height(self, height):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            # Assumes status=3 means Main Chain
            cursor = conn.execute("SELECT block_hash FROM block_index WHERE height = ? AND status = 3", (height,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None

    def search_block_hashes(self, query_fragment):
        """Find block hashes starting with the query fragment."""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            # Limit to 5 results for now
            cursor = conn.execute("SELECT block_hash FROM block_index WHERE block_hash LIKE ? LIMIT 5", (query_fragment + '%',))
            rows = cursor.fetchall()
            return [r[0] for r in rows]

    def add_transaction(self, tx_hash, block_hash):
        """Map a transaction hash to the block hash that contains it."""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("INSERT OR REPLACE INTO tx_index (tx_hash, block_hash) VALUES (?, ?)", (tx_hash, block_hash))
            conn.commit()

    def get_transaction_block_hash(self, tx_hash):
        """Get the block hash containing the given transaction."""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.execute("SELECT block_hash FROM tx_index WHERE tx_hash = ?", (tx_hash,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None

class ChainStateDB:
    def __init__(self, data_dir):
        self.db_path = os.path.join(data_dir, 'chainstate.sqlite')
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS utxo (
                    txid TEXT,
                    vout_index INTEGER,
                    amount INTEGER,
                    script_pubkey BLOB,
                    block_height INTEGER DEFAULT 0,
                    is_coinbase BOOLEAN DEFAULT 0,
                    PRIMARY KEY (txid, vout_index)
                )
            """)
            # Migration check: Check if columns exist, if not add them
            cursor = conn.execute("PRAGMA table_info(utxo)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'block_height' not in columns:
                conn.execute("ALTER TABLE utxo ADD COLUMN block_height INTEGER DEFAULT 0")
            if 'is_coinbase' not in columns:
                conn.execute("ALTER TABLE utxo ADD COLUMN is_coinbase BOOLEAN DEFAULT 0")
                
            conn.commit()

    def add_utxo(self, txid, vout_index, amount, script_pubkey, block_height, is_coinbase):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO utxo (txid, vout_index, amount, script_pubkey, block_height, is_coinbase)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (txid, vout_index, amount, script_pubkey, block_height, is_coinbase))
            conn.commit()

    def remove_utxo(self, txid, vout_index):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("DELETE FROM utxo WHERE txid = ? AND vout_index = ?", (txid, vout_index))
            conn.commit()

    def get_utxo(self, txid, vout_index):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.execute("SELECT amount, script_pubkey, block_height, is_coinbase FROM utxo WHERE txid = ? AND vout_index = ?", (txid, vout_index))
            row = cursor.fetchone()
            if row:
                return {'amount': row[0], 'script_pubkey': row[1], 'block_height': row[2], 'is_coinbase': bool(row[3])}
            return None

    def get_utxos_by_script(self, script_pubkey):
        """Find all UTXOs paying to a specific script (address)."""
        # Note: script_pubkey should be bytes
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.execute("SELECT txid, vout_index, amount, block_height, is_coinbase FROM utxo WHERE script_pubkey = ?", (script_pubkey,))
            rows = cursor.fetchall()
            return [{'txid': r[0], 'vout': r[1], 'amount': r[2], 'block_height': r[3], 'is_coinbase': bool(r[4])} for r in rows]
