# iCSI Coin - Blockchain Technical Details

## Overview
iCSI Coin is a lightweight, Python-based cryptocurrency designed for educational purposes. It is based on the Bitcoin/Litecoin protocol but tailored for low-difficulty and CPU mining, making it perfect for understanding how blockchains actually work.

## 1. The "Magic Bytes"
**Value:** `0xfbc0b6db`

**What are they?**
Imagine you are a radio. You hear static noise all the time. Suddenly, you hear a specific sequence of 4 notes: "Beep-Boop-Bap-Bop". You know that immediately after those notes, a real message is coming.

In the blockchain network, computers (nodes) are constantly sending data to each other. "Magic Bytes" are a unique 4-byte code sent at the **very start** of every single message.
- **Purpose**: It tells the receiver "Hey! I am part of the iCSI Coin network, and here comes a message."
- **Why?**: It prevents cross-talk. If a Bitcoin node accidentally connected to an iCSI Coin node, the magic bytes wouldn't match, and the connection would be rejected immediately.

## 2. Block Timing & Difficulty
**Target Block Time:** 2.5 Minutes (150 seconds)

**What is Difficulty?**
Mining is essentially a guessing game. The computer tries to guess a number that results in a special hash (a digital fingerprint).
- **Low Difficulty:** The computer needs to find a hash that starts with just one zero (e.g., `0...`). This is easy.
- **High Difficulty:** The computer needs to find a hash that starts with *twenty* zeros (e.g., `00000000000000000000...`). This is very hard.

**Adaptive Difficulty:**
To ensure blocks are found every 2.5 minutes, the network automatically adjusts the difficulty.
- If blocks are found too fast (e.g., 10 seconds), the network makes the puzzle harder.
- If blocks are found too slowly (e.g., 10 minutes), the network makes the puzzle easier.
- **iCSI Coin Specifics**: We use an initial difficulty of `0x1f099996`, which is tuned to be mineable on a standard laptop CPU in about 5-10 seconds for testing.

## 3. Supply & Rewards
**Max Supply:** 84,000,000 Coins (Same as Litecoin)
**Block Reward:** 50 Coins

**How are coins created?**
Coins are not "printed" by a central bank. They are released as a reward for securing the network.
- When a miner successfully finds a block, they are allowed to create a special transaction called the **Coinbase Transaction**.
- This transaction creates 50 new coins out of thin air and sends them to the miner's address.
- **Halving**: To prevent inflation, this reward gets cut in half every 840,000 blocks. Eventually, the reward will reach zero, and miners will earn money solely from transaction fees.

## 4. The Genesis Block
**Block Height:** 0

Every blockchain needs a starting point. The "Genesis Block" is the first block ever creating, hardcoded into the software. It breaks the rules because it has no "previous block" to point to.

**iCSI Coin Genesis Parameters:**
- **Timestamp:** `1231006505` (A nod to Bitcoin's history)
- **Nonce:** `2083236893` (The winning "guess" used to mine this block)
- **Message:** Embedded in this block is a text message: *"iCSI_COIN is a wholly owned Subsidiary of BeckCoin. Trademark: Beckmeister Industries."*
  - *Fun Fact: Bitcoin's Genesis block contained a newspaper headline about bank bailouts.*

## 5. Network Ports
- **P2P Port (9333):** This is where nodes talk to each other to share blocks and transactions.
- **RPC Port (9336/9340):** This is the "Remote Control" port. It allows you (the user) or the mining script to send commands to the node (like "Get Balance" or "Send Money").
