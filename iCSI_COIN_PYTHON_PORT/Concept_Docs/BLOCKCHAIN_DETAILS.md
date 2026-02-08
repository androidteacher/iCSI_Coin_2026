# iCSI Coin - Blockchain Details

## Overview
iCSI Coin is a lightweight, Python-based cryptocurrency designed for educational purposes and CPU mining. It is based on the Litecoin protocol but tailored for low-difficulty, high-supply experimentation.

## Technical Parameters

### 1. Supply & Rewards
-   **Maximum Supply**: 84,000,000 COINS (Same as Litecoin)
-   **Initial Block Reward**: 50 COINS
-   **Halving Interval**: Every 840,000 Blocks (Approx. 4 years at target speed)
    -   Compare to Bitcoin/Litecoin: 840,000 blocks ensures a smoother curve or specific total?
    -   *Correction*: Litecoin is 84M coins, 50 start, 840k halving. Bitcoin is 21M, 50 start, 210k halving. We will stick to Litecoin parameters for familiar economics.

### 2. Block Timing & Difficulty
-   **Target Block Time**: 2.5 Minutes (150 seconds)
-   **Difficulty Adjustment Algorithm**: Simple Moving Average per block (or standard Retarget every 2016 blocks).
    -   *For MVP*: Standard retargeting every 2016 blocks (approx 3.5 days).
-   **Initial Difficulty (Genesis)**: `0x1f0fffff` (Bits)
    -   Target: `000fffff...`
    -   **Adjustment for CPU Mining**: We tuned this (Exp 31) to require ~4000 hashes per block, targeting ~5-10 seconds on a standard CPU.

### 3. Mining
-   **Algorithm**: Scrypt
    -   N=1024, r=1, p=1 (Standard Litecoin)
-   **Hardware**: optimized for CPU.

## Protocol Rules
-   **Magic Bytes**: `0xf9beb4d9` (Mainnet)
-   **Port**: 9333 (P2P), 9332 (RPC)

## Reset Policy
-   The blockchain is **ephemeral** during development.
-   Running `burn.sh` triggers a **Hard Reset**:
    -   All containers stopped & removed.
    -   All images deleted.
    -   **All blockchain data (databases, wallets) is wiped from the host.**
    -   The chain restarts at Block 0 (Genesis).
