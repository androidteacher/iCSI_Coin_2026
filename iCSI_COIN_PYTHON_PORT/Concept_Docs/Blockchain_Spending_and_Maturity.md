# Blockchain Spending and Maturity

In traditional banking, when a deposit shows up in your account, it's usually considered "final" immediately or within a few business days. In a decentralized blockchain like iCSI Coin (and Bitcoin/Litecoin), the concept of "finality" is probabilistic. This leads to an important rule known as **Coinbase Maturity**.

## The 100-Block Rule

If you are a miner and you successfully mine a block, you are rewarded with newly created coins (the "Coinbase Transaction"). However, you cannot spend these coins immediately.

**Rule:** Coinbase transaction outputs can only be spent after they have received at least **100 confirmations**.

This means if you mine Block #500, you cannot use the reward from that block until the blockchain reaches Block #600.

## Why is this important?

This delay protects the network and the economy from **Chain Reorganizations (Reorgs)**.

### The Problem: Orphaned Blocks
Imagine two miners find a valid block at the exact same time.
- Miner A finds Block #500 (Hash A).
- Miner B finds Block #500 (Hash B).

Half the network accepts Hash A, and the other half accepts Hash B. The chain splits. Both miners think they have earned the 50 coin reward.

Eventually, Miner A finds Block #501 on top of Hash A. The nodes running Hash B verify this new longer chain, switch over, and **discard Hash B**.

Block #500 (Hash B) is now an **Orphan Block**. It is no valid part of the history.

### The Attack Scenario (What could go wrong?)
If there was **no maturity rule**, here is how an attacker (or an unlucky accident) destroys value:

1. **The Spend:** Malicious Miner finds Block #500. They immediately spend the 50 reward coins to buy a digital gift card from a merchant.
2. **The Exchange:** The merchant sees the transaction in Block #500, verifies it, and sends the gift card code.
3. **The Reorg:** A competing chain (maybe just 1 block longer) emerges that does *not* include the Malicious Miner's block.
4. **The Vanishing Act:** The entire network switches to the new chain. Block #500 is orphaned.
    - The Malicious Miner's 50 coins **never existed**.
    - The transaction paying the merchant **never happened**.
    - The merchant has lost the goods (gift card) and received **zero payment**.

By enforcing a **100-block buffer**, we ensure that by the time the coins are spendable, the block is so deep in the chain history that the probability of it being "reorged" out is effectively zero. A reorg of 100 blocks would require immense computational power, making it economically infeasible for typical attacks.

## Summary for Cyber Students
- **Immutability is built over time.** A block isn't truly set in stone until many other blocks are built on top of it.
- **Maturity prevents "phantom" value.** It stops coins that might disappear from entering the economy.
- **Confirmations matter.** For high-value transactions, always wait for multiple confirmations (usually 6 for regular transactions, 100 for mining rewards).
