import asyncio
import logging
from aiohttp import web
import json
import binascii
import time
from icsicoin.core.primitives import Block, BlockHeader, Transaction, TxIn, TxOut
from icsicoin.core.hashing import double_sha256

logger = logging.getLogger("RPCServer")

class RPCServer:
    def __init__(self, port, user, password, allow_ip, network_manager, chain_manager, mempool, wallet):
        self.port = port
        self.user = user
        self.password = password
        self.enforce_auth = False # Default: permissive
        self.allow_ip = allow_ip
        self.network_manager = network_manager
        self.chain_manager = chain_manager
        self.mempool = mempool
        self.wallet = wallet
        self.app = web.Application()
        self.app.router.add_post('/', self.handle_request)
        self.app.router.add_get('/api/rpc/config', self.handle_rpc_config_get)
        self.app.router.add_post('/api/rpc/config', self.handle_rpc_config_post)
        self.runner = None
        self.site = None

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        logger.info(f"RPC Server started on port {self.port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
        logger.info("RPC Server stopped")

    async def handle_request(self, request):
        # Basic Auth Check
        if self.enforce_auth:
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                return web.Response(text="Unauthorized", status=401, headers={'WWW-Authenticate': 'Basic realm="RPC"'})
            
            try:
                auth_type, encoded = auth_header.split(None, 1)
                if auth_type.lower() != 'basic':
                     return web.Response(text="Unauthorized (Use Basic Auth)", status=401)
                
                import base64
                decoded = base64.b64decode(encoded).decode('utf-8')
                username, password = decoded.split(':', 1)
                
                if username != self.user or password != self.password:
                     return web.Response(text="Unauthorized (Invalid Credentials)", status=401)
            except Exception:
                 return web.Response(text="Unauthorized (Bad Request)", status=401)

        # Parsing JSON
        try:
            data = await request.json()
        except:
            return web.Response(text="Invalid JSON", status=400)

        method = data.get('method')
        params = data.get('params', [])
        req_id = data.get('id')

        result = None
        error = None

        logger.info(f"RPC Request: {method}")

        if method == 'getinfo':
            result = {
                "version": "0.1-beta-python",
                "protocolversion": 70015,
                "blocks": 0,
                "connections": len(self.network_manager.peers),
                "proxy": "",
                "difficulty": 1.0,
                "testnet": False,
                "errors": ""
            }
        elif method == 'stop':
            result = "iCSI Coin server stopping"
            # Schedule shutdown
            asyncio.create_task(self._shutdown_server())
        elif method == 'getblockcount':
            best = self.chain_manager.block_index.get_best_block()
            result = best['height'] if best else 0

        elif method == 'getbestblockhash':
            best = self.chain_manager.block_index.get_best_block()
            result = best['block_hash'] if best else self.chain_manager.genesis_block.get_hash().hex()

        elif method == 'getblocktemplate':
            # 1. Get Tip
            best = self.chain_manager.block_index.get_best_block()
            prev_hash_hex = best['block_hash'] if best else '0'*64
            height = (best['height'] + 1) if best else 1
            
            # 2. Coinbase
            miner_addr = None
            if params and isinstance(params[0], dict):
                 miner_addr = params[0].get("mining_address")
            
            if not miner_addr:
                # Pay to our wallet
                addrs = self.wallet.get_addresses()
                if not addrs:
                    self.wallet.get_new_address()
                    addrs = self.wallet.get_addresses()
                miner_addr = addrs[0]
            
            # ScriptPubkey for P2PKH: OP_DUP OP_HASH160 <pubKeyHash> OP_EQUALVERIFY OP_CHECKSIG
            # address is hex of pubKeyHash as per our Wallet impl
            # binascii is imported globally
            pubkey_hash = binascii.unhexlify(miner_addr)
            # 0x76=OP_DUP, 0xa9=OP_HASH160, 0x14=Push20, <hash>, 0x88=OP_EQUALVERIFY, 0xac=OP_CHECKSIG
            script_pubkey = b'\x76\xa9\x14' + pubkey_hash + b'\x88\xac'
            
            coinbase_tx = Transaction(
                vin=[TxIn(prev_hash=b'\x00'*32, prev_index=0xffffffff, script_sig=str(height).encode(), sequence=0xffffffff)],
                vout=[TxOut(amount=50*100000000, script_pubkey=script_pubkey)]
            )
            
            # 3. Select Mempool Txs (Greedy non-conflicting selection)
            # txs = [coinbase_tx] + self.mempool.get_all_transactions()
            selected_txs = [coinbase_tx]
            spent_in_block = set()
            
            # Mempool txs
            candidate_txs = self.mempool.get_all_transactions()
            # Sort by fee/priority? For now just FCFS/Arbitrary
            
            for tx in candidate_txs:
                is_conflict = False
                # Check inputs
                current_tx_inputs = []
                for vin in tx.vin:
                    prev_out = (vin.prev_hash, vin.prev_index)
                    if prev_out in spent_in_block:
                        is_conflict = True
                        break
                    current_tx_inputs.append(prev_out)
                
                if not is_conflict:
                    selected_txs.append(tx)
                    for inp in current_tx_inputs:
                        spent_in_block.add(inp)
            
            txs = selected_txs
            
            # 4. Build Block Object to calculate Merkle Root
            # Merkle Root calculation is implicit in Block logic usually, or we do it here.
            # We need a helper. primitive.Block doesn't have build_merkle_tree method publicly exposed easily?
            # actually we used a helper in tests.
            # Let's create a temp block just to get the merkle root if the class supports it, 
            # or implemented simplistic merkle root here.
            # Wait, `validate_block` calculates it. Block header has it.
            # We need to constructing the merkle root from txs.
            from icsicoin.consensus.merkle import get_merkle_root
            merkle_root = get_merkle_root(txs)
            
            # 5. Calculate dynamic difficulty
            from icsicoin.consensus.validation import calculate_next_bits, bits_to_target
            next_bits = calculate_next_bits(self.chain_manager, height)
            next_target = bits_to_target(next_bits)
            target_hex = format(next_target, '064x')
            
            # 6. Return dict
            # We return enough info for miner to build header
            result = {
                "version": 1,
                "previousblockhash": prev_hash_hex,
                "curtime": int(time.time()),
                "bits": next_bits,
                "height": height,
                "coinbase_value": 5000000000,
                "transactions": [binascii.hexlify(tx.serialize()).decode('utf-8') for tx in txs],
                "merkle_root": binascii.hexlify(merkle_root).decode('utf-8'),
                "target": target_hex
            }

        elif method == 'submitblock':
            params = data.get('params', [])
            if not params:
                return web.json_response({"result": None, "error": "Missing block hex", "id": req_id})
            
            block_hex = params[0]
            try:
                # binascii is already imported at top module level
                block_bytes = binascii.unhexlify(block_hex)
                import io
                f = io.BytesIO(block_bytes)
                block = Block.deserialize(f)
                
                success, reason = self.chain_manager.process_block(block)
                if success:
                    # Remove mined transactions from mempool
                    for tx in block.vtx:
                        self.mempool.remove_transaction(tx.get_hash().hex())

                    result = "accepted"
                    # Broadcast to network
                    asyncio.create_task(self.network_manager.announce_new_block(block))
                else:
                    result = f"rejected: {reason}"
            except Exception as e:
                 error = {"code": -1, "message": f"Block decode failed: {e}"}

        elif method == 'getnewaddress':
            result = self.wallet.get_new_address()
            
        elif method == 'getbalance':
            # Very simple balance check: scan UTXO set (ChainState)
            # This is slow, but functional for Phase 6.
            # Real wallet maintains its own index/UTXO subset.
            addrs = self.wallet.get_addresses()
            total = 0
            # We can't easily query ChainStateDB for "all UTXOs matching these addresses" 
            # without iterating EVERYTHING or adding an index.
            # ChainStateDB (LevelDB/SQLite) usually keys by TxID.
            # Our SQLite schemas: PRIMARY KEY (txid, vout_index).
            # We need to SELECT * FROM utxo.
            # Or add a method to ChainManager/Wallet to scan.
            # Let's add 'get_balance' to ChainStateDB/Manager later.
            # For now, return "Not Implemented" or 0.
            result = 0 
            
        elif method == 'addnode':
             params = data.get('params', [])
             if not params:
                 return web.json_response({"result": None, "error": "Missing node address (usage: addnode <ip>:<port>)", "id": req_id})
             
             target = params[0]
             try:
                 if ':' in target:
                     ip, port_str = target.split(':')
                     port = int(port_str)
                 else:
                      return web.json_response({"result": None, "error": "Invalid format. Use <ip>:<port>", "id": req_id})
                 
                 # Attempt connection (fire and forget task)
                 asyncio.create_task(self.network_manager.connect_to_peer(ip, port))
                 result = f"Attempting connection to {ip}:{port}"
             except Exception as e:
                 error = {"code": -1, "message": f"Failed to add node: {e}"}

        elif method == 'getpeerinfo':
            peers = []
            try:
                for peer_addr, writer in self.network_manager.active_connections.items():
                    # active_connections keys are tuples (ip, port)
                    ip, port = peer_addr
                    
                    stats = self.network_manager.peer_stats.get(peer_addr, {})
                    
                    peer_info = {
                        "id": f"{ip}:{port}",
                        "addr": f"{ip}:{port}",
                        "addrlocal": f"{self.network_manager.external_ip}:{self.network_manager.port}" if self.network_manager.external_ip else "127.0.0.1:9341",
                        "services": "00000001",
                        "relaytxes": True,
                        "lastsend": 0,
                        "lastrecv": stats.get('last_seen', int(time.time())),
                        "bytesbound": 0,
                        "bytesrecv": 0,
                        "conntime": 0,
                        "timeoffset": 0,
                        "pingtime": 0,
                        "minping": 0,
                        "version": 70015,
                        "subver": "/iCSI:0.1/",
                        "inbound": False,
                        "startingheight": stats.get('height', 0),
                        "banscore": 0,
                        "synced_headers": stats.get('height', 0),
                        "synced_blocks": stats.get('height', 0),
                        "inflight": [],
                        "whitelisted": False
                    }
                    peers.append(peer_info)
                result = peers
            except Exception as e:
                error = {"code": -1, "message": f"GetPeerInfo Failed: {e}"}


        response = {
            "result": result,
            "error": error,
            "id": req_id
        }
        return web.json_response(response)

    async def _shutdown_server(self):
        logger.info("Shutdown requested via RPC")
        await asyncio.sleep(1) # Give time to return response
        # In a real app we'd signal the main loop
        # For now, we can raise a SystemExit or similar, but asyncio.CancelledError is better handled in main
        # We can simulate SIGINT?
        import signal
        import os
        os.kill(os.getpid(), signal.SIGINT)

    async def handle_rpc_config_get(self, request):
        return web.json_response({
            'user': self.user,
            'password': self.password,
            'enforce_auth': self.enforce_auth
        })

    async def handle_rpc_config_post(self, request):
        try:
            data = await request.json()
            if 'user' in data: self.user = data['user']
            if 'password' in data: self.password = data['password']
            if 'enforce_auth' in data: self.enforce_auth = bool(data['enforce_auth'])
            
            return web.json_response({'status': 'updated'})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)
