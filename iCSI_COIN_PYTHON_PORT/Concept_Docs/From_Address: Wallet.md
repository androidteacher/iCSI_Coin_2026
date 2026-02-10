# Sending Money: The "Shared Pool" Concept

When you use the iCSI Coin Web Interface to send money, you might notice a dropdown menu asking you to select a "From" wallet address. While this seems to imply that you are sending money *only* from that specific address, the system actually works a bit differently under the hood.

## The Reality: All Addresses are One Wallet

In this implementation of iCSI Coin, even though you can generate multiple "Receive Addresses" (Wallet A, Wallet B, Wallet C), they all belong to a single **Wallet File** (`wallet.dat`).

When you create a transaction, the system treats all your addresses as a **single pool of funds**.

### How It Works

1.  **You Request to Send:** You ask to send 50 coins to a friend.
2.  **System Scans Funds:** The wallet software looks at *all* the unspent coins (UTXOs) belonging to *any* of your addresses.
    *   It does not matter if the coins are in Wallet A, Wallet B, or Wallet C.
3.  **Aggregating Inputs:** The system grabs coins from whichever address has them until it has enough to cover the 50 coins + transaction fee.
    *   *Example:* It might take 10 coins from Wallet A and 40 coins from Wallet B to make the payment.
4.  **Change Address:** If you have 60 coins total and send 50, the remaining ~10 coins (minus fee) are sent back to one of your addresses as "change."

### Why the "From" Dropdown?

The "From" dropdown in the UI is primarily for:
1.  **Dashboard Display:** It updates the "Current Balance" shown on the screen so you can see how many coins are associated with that specific address.
2.  **Estimation:** It helps you estimate if you *collectively* have enough funds.

**Key Takeaway:** You cannot strictly isolate funds between addresses in this specific wallet implementation. Your spending power is the sum of all your addresses combined.
