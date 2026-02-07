import sqlite3
import os
import os

class BlockIndexDB:
    def __init__(self, data_dir):
        self.db_path = os.path.join(data_dir, 'block_index.sqlite')
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_height ON block_index (height)")
            conn.commit()

    def add_block(self, block_hash, file_num, offset, length, prev_hash, height=0, status=1):
        """Add or update a block entry."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO block_index 
                (block_hash, file_num, offset, length, prev_hash, height, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (block_hash, file_num, offset, length, prev_hash, height, status))
            conn.commit()
    def update_block_status(self, block_hash, status):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE block_index SET status = ? WHERE block_hash = ?", (status, block_hash))
            conn.commit()

    def get_block_info(self, block_hash):
        with sqlite3.connect(self.db_path) as conn:
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT value FROM chain_info WHERE key = 'best_block_hash'")
            row = cursor.fetchone()
            if row:
                return self.get_block_info(row[0])
            return None

    def update_best_block(self, block_hash):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO chain_info (key, value) VALUES ('best_block_hash', ?)", (block_hash,))
            conn.commit()

    def get_block_hash_by_height(self, height):
        with sqlite3.connect(self.db_path) as conn:
            # Assumes status=3 means Main Chain
            cursor = conn.execute("SELECT block_hash FROM block_index WHERE height = ? AND status = 3", (height,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None

class ChainStateDB:
    def __init__(self, data_dir):
        self.db_path = os.path.join(data_dir, 'chainstate.sqlite')
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS utxo (
                    txid TEXT,
                    vout_index INTEGER,
                    amount INTEGER,
                    script_pubkey BLOB,
                    PRIMARY KEY (txid, vout_index)
                )
            """)
            conn.commit()

    def add_utxo(self, txid, vout_index, amount, script_pubkey):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO utxo (txid, vout_index, amount, script_pubkey)
                VALUES (?, ?, ?, ?)
            """, (txid, vout_index, amount, script_pubkey))
            conn.commit()

    def remove_utxo(self, txid, vout_index):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM utxo WHERE txid = ? AND vout_index = ?", (txid, vout_index))
            conn.commit()

    def get_utxo(self, txid, vout_index):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT amount, script_pubkey FROM utxo WHERE txid = ? AND vout_index = ?", (txid, vout_index))
            row = cursor.fetchone()
            if row:
                return {'amount': row[0], 'script_pubkey': row[1]}
            return None

    def get_utxos_by_script(self, script_pubkey):
        """Find all UTXOs paying to a specific script (address)."""
        # Note: script_pubkey should be bytes
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT txid, vout_index, amount FROM utxo WHERE script_pubkey = ?", (script_pubkey,))
            rows = cursor.fetchall()
            return [{'txid': r[0], 'vout': r[1], 'amount': r[2]} for r in rows]
