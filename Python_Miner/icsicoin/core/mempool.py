import logging

logger = logging.getLogger("Mempool")

class Mempool:
    def __init__(self):
        self.transactions = {} # tx_hash -> Transaction object

    def add_transaction(self, tx):
        tx_hash = tx.get_hash().hex()
        if tx_hash in self.transactions:
            return False
        
        # In a real node, we would validate mempool acceptance (fees, standardness, etc.)
        self.transactions[tx_hash] = tx
        logger.info(f"Added TX {tx_hash} to mempool. Size: {len(self.transactions)}")
        return True

    def get_transaction(self, tx_hash):
        return self.transactions.get(tx_hash)

    def remove_transaction(self, tx_hash):
        if tx_hash in self.transactions:
            del self.transactions[tx_hash]
            return True
        return False
        
    def get_all_transactions(self):
        return list(self.transactions.values())
