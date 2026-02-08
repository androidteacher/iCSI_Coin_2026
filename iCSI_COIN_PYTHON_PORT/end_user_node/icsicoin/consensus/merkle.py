from icsicoin.core.hashing import double_sha256

def get_merkle_root(transactions):
    """
    Calculate the Merkle Root for a list of transactions.
    transactions: List of Transaction objects.
    Returns: 32-byte hash.
    """
    if not transactions:
        raise ValueError("Transaction list cannot be empty")

    # Start with the hashes of all transactions
    hashes = [tx.get_hash() for tx in transactions]

    while len(hashes) > 1:
        # If odd number of hashes, duplicate the last one
        if len(hashes) % 2 != 0:
            hashes.append(hashes[-1])
        
        new_hashes = []
        for i in range(0, len(hashes), 2):
            # Concatenate pair and hash
            # Note: Bitcoin implementations often double-hash the concatenation
            combined = hashes[i] + hashes[i+1]
            new_hashes.append(double_sha256(combined))
        
        hashes = new_hashes

    return hashes[0]
