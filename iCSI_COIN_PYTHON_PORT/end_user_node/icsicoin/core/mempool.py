import logging
import os
import json
import binascii
import io
from icsicoin.core.primitives import Transaction

logger = logging.getLogger("Mempool")

class Mempool:
    def __init__(self, data_dir=None):
        self.transactions = {} # tx_hash -> Transaction object
        self.data_dir = data_dir
        self.filename = os.path.join(data_dir, "mempool.dat") if data_dir else None
        if self.filename:
            self.load()

    def load(self):
        if not self.filename or not os.path.exists(self.filename):
            return
        
        try:
            with open(self.filename, 'r') as f:
                data = json.load(f)
                
            count = 0
            for tx_hex in data:
                try:
                    tx_bytes = binascii.unhexlify(tx_hex)
                    tx = Transaction.deserialize(io.BytesIO(tx_bytes))
                    # Validate? We assume persisted mempool was valid.
                    # Re-verify logic could be added here but for now just load.
                    self.transactions[tx.get_hash().hex()] = tx
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to deserialize mempool tx: {e}")
            
            logger.info(f"Loaded {count} transactions from mempool.dat")
        except Exception as e:
            logger.error(f"Failed to load mempool: {e}")

    def save(self):
        if not self.filename:
            return
            
        try:
            # Serialize all transactions to hex
            data = []
            for tx in self.transactions.values():
                data.append(binascii.hexlify(tx.serialize()).decode('utf-8'))
                
            with open(self.filename, 'w') as f:
                json.dump(data, f)
            logger.info(f"Saved {len(data)} transactions to mempool.dat")
        except Exception as e:
            logger.error(f"Failed to save mempool: {e}")

    def add_transaction(self, tx):
        tx_hash = tx.get_hash().hex()
        if tx_hash in self.transactions:
            return False
        
        # Check if any input is already spent by a tx in the mempool
        for vin in tx.vin:
            for existing_tx in self.transactions.values():
                for existing_vin in existing_tx.vin:
                    if vin.prev_hash == existing_vin.prev_hash and vin.prev_index == existing_vin.prev_index:
                        logger.warning(f"Rejected TX {tx_hash}: Input {vin.prev_hash.hex()}:{vin.prev_index} already spent in mempool by {existing_tx.get_hash().hex()}")
                        return False

        # In a real node, we would validate mempool acceptance (fees, standardness, etc.)
        self.transactions[tx_hash] = tx
        logger.info(f"Added TX {tx_hash} to mempool. Size: {len(self.transactions)}")
        self.save() # Auto-save on addition? Yes, for safety. Or periodic. Auto-save is safer for crashes.
        return True

    def get_transaction(self, tx_hash):
        return self.transactions.get(tx_hash)

    def remove_transaction(self, tx_hash):
        if tx_hash in self.transactions:
            del self.transactions[tx_hash]
            self.save() # Update persistence
            return True
        return False
        
    def get_all_transactions(self):
        return list(self.transactions.values())
