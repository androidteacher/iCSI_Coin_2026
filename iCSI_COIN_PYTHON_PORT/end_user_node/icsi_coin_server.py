import asyncio
import argparse
import logging
import sys
sys.path.insert(0, "/app")

from icsicoin.network.manager import NetworkManager
from icsicoin.wallet.wallet import Wallet
from icsicoin.rpc.rpc_server import RPCServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/app/wallet_data/debug.log")
    ]
)
logger = logging.getLogger("iCSICoinNode")

async def main():
    parser = argparse.ArgumentParser(description="iCSI Coin Node")
    parser.add_argument("--addnode", action="append", help="Add a node to connect to")
    parser.add_argument("--connect", action="append", help="Connect only to the specified node(s)")
    parser.add_argument("--port", type=int, default=9333, help="Listen for connections on <port>")
    parser.add_argument("--listen", action="store_true", default=True, help="Accept connections from outside")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind to given address")
    parser.add_argument("--datadir", default="~/.icsicoin", help="Specify data directory")
    parser.add_argument("--debug", action="store_true", help="Output extra debugging information")
    
    # RPC Options
    parser.add_argument("--rpcuser", help="Username for JSON-RPC connections")
    parser.add_argument("--rpcpassword", help="Password for JSON-RPC connections")
    parser.add_argument("--rpcport", type=int, default=9332, help="Listen for JSON-RPC connections on <port>")
    parser.add_argument("--rpcallowip", default="127.0.0.1", help="Allow JSON-RPC connections from specified IP address")
    parser.add_argument("--rpcthreads", type=int, default=4, help="Set the number of threads to service RPC calls")
    
    # Web Config Options
    parser.add_argument("--web-port", type=int, help="Port to serve the web configuration interface (e.g., 8080)")

    
    args = parser.parse_args()
    
    logger.info(f"Starting iCSI Coin Node on port {args.port}")
    
    # Init Network Manager (which inits Chain & Mempool)
    network_manager = NetworkManager(
        port=args.port,
        bind_address=args.bind,
        add_nodes=args.addnode,
        connect_nodes=args.connect,
        rpc_port=args.rpcport,
        data_dir=args.datadir
    )
    
    # Init Wallet
    wallet = Wallet(args.datadir)
    network_manager.wallet = wallet # Attach wallet to manager for WebServer access

    # Init RPC Server
    rpc_server = RPCServer(
        port=args.rpcport,
        user=args.rpcuser,
        password=args.rpcpassword,
        allow_ip=args.rpcallowip,
        network_manager=network_manager,
        chain_manager=network_manager.chain_manager,
        mempool=network_manager.mempool,
        wallet=wallet
    )
    if args.rpcport:
        await rpc_server.start()
        
    web_server = None
    if args.web_port:
        from icsicoin.web.server import WebServer
        web_server = WebServer(port=args.web_port, network_manager=network_manager, rpc_port=args.rpcport)
        await web_server.start()
    
    # Start the network manager
    await network_manager.start()
    
    # Keep the event loop running
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Node stopping...")
        if rpc_server:
            await rpc_server.stop()
        if web_server:
            await web_server.stop()
        await network_manager.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
