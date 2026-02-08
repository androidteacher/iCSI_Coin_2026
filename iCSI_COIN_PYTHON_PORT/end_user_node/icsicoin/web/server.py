import logging
import asyncio
import aiohttp
from aiohttp import web
import os
import binascii
import json
import io
import socket as socket_mod
from icsicoin.core.primitives import Block
from icsicoin.mining.controller import MinerController
import jinja2

logger = logging.getLogger("WebServer")

class WebServer:
    def __init__(self, port, network_manager, rpc_port=9332):
        self.port = port
        self.network_manager = network_manager
        self.app = web.Application()
        self.rpc_port = rpc_port
        self.user = 'user'
        self.password = 'pass'
        self.enforce_auth = False # Default: permissive
        
        # Setup Jinja2
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'templates')
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        
        # Miner Controller (Connects to Local RPC)
        # We need to grab RPC credentials. 
        self.miner_controller = MinerController(
            rpc_url=f"http://127.0.0.1:{self.rpc_port}",
            rpc_user=os.environ.get('RPC_USER', 'user'),
            rpc_password=os.environ.get('RPC_PASSWORD', 'pass')
        )

        # Routes
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_static('/static', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'static'))
        
        # API - Network
        self.app.router.add_post('/api/connect', self.handle_connect)
        self.app.router.add_get('/api/peers', self.handle_peers)
        self.app.router.add_post('/api/peers/delete', self.handle_delete_peer)
        self.app.router.add_post('/api/reset', self.handle_reset)
        self.app.router.add_get('/api/logs', self.handle_get_logs)
        self.app.router.add_post('/api/test/send', self.handle_send_test)
        self.app.router.add_get('/api/stats', self.handle_get_stats)
        self.app.router.add_post('/api/stun/test', self.handle_test_stun)
        self.app.router.add_get('/api/discovery/status', self.handle_discovery_status)
        
        # API - RPC Config
        self.app.router.add_get('/api/rpc/config', self.handle_rpc_config_get)
        self.app.router.add_post('/api/rpc/config', self.handle_rpc_config_post)
        
        # Miner Download
        self.app.router.add_get('/api/miner/download', self.handle_miner_download)
        
        # Your Data Download
        self.app.router.add_get('/api/data/download', self.handle_data_download)

        # API - Wallet
        self.app.router.add_get('/api/wallet/list', self.handle_wallet_list)
        self.app.router.add_post('/api/wallet/create', self.handle_wallet_create)
        self.app.router.add_post('/api/wallet/delete', self.handle_wallet_delete)
        self.app.router.add_post('/api/wallet/send', self.handle_wallet_send)
        self.app.router.add_get('/api/wallet/export', self.handle_wallet_export)
        self.app.router.add_post('/api/wallet/import', self.handle_wallet_import)
        self.app.router.add_post('/api/wallet/rename', self.handle_wallet_rename)
        
        # API - Miner
        self.app.router.add_get('/api/miner/status', self.handle_miner_status)
        self.app.router.add_post('/api/miner/start', self.handle_miner_start)
        self.app.router.add_post('/api/miner/stop', self.handle_miner_stop)

        # API - Beggar
        self.app.router.add_post('/api/beggar/start', self.handle_beggar_start)
        self.app.router.add_post('/api/beggar/stop', self.handle_beggar_stop)
        self.app.router.add_get('/api/beggar/list', self.handle_beggar_list)
        # Explorer Routes
        self.app.router.add_get('/explorer', self.handle_explorer_page)
        self.app.router.add_get('/explorer/block/{block_hash}', self.handle_explorer_detail_page)
        self.app.router.add_get('/api/explorer/blocks', self.handle_api_explorer_blocks)
        self.app.router.add_get('/api/explorer/block/{block_hash}', self.handle_api_explorer_block_detail)

        self.runner = None
        self.site = None

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        logger.info(f"Web server started on port {self.port}")

    async def stop(self):
        self.miner_controller.stop_mining()
        if self.runner:
            await self.runner.cleanup()

    async def render_template(self, template_name, **context):
        template = self.jinja_env.get_template(template_name)
        content = template.render(context)
        return web.Response(text=content, content_type='text/html')

    async def handle_explorer_page(self, request):
        return await self.render_template('explorer.html')

    async def handle_explorer_detail_page(self, request):
        block_hash = request.match_info['block_hash']
        return await self.render_template('block_detail.html', block_hash=block_hash)

    async def handle_api_explorer_blocks(self, request):
        # Pagination
        try:
            page = int(request.query.get('page', 1))
            limit = int(request.query.get('limit', 20))
        except ValueError:
            page = 1
            limit = 20

        chain = self.network_manager.chain_manager
        best_block = chain.block_index.get_best_block()
        
        if not best_block:
            return web.json_response({'blocks': [], 'total_pages': 0, 'current_page': page})

        best_height = best_block['height']
        total_blocks = best_height + 1
        total_pages = (total_blocks + limit - 1) // limit

        start_height = best_height - ((page - 1) * limit)
        end_height = start_height - limit + 1
        
        if start_height < 0:
             return web.json_response({'blocks': [], 'total_pages': total_pages, 'current_page': page})

        end_height = max(0, end_height)
        
        blocks_data = []
        for h in range(start_height, end_height - 1, -1):
            # We need timestamp, so we must load the block header
            # Optimization: chain.get_block_by_height loads full block (txs included). 
            # For just header info, we might want a lighter method, but for now this is fine.
            block = chain.get_block_by_height(h)
            if block:
                blocks_data.append({
                    'height': h,
                    'hash': block.get_hash().hex(),
                    'timestamp': block.header.timestamp,
                    'tx_count': len(block.vtx),
                    'size': len(block.serialize())
                })
        
        return web.json_response({
            'blocks': blocks_data,
            'total_pages': total_pages,
            'current_page': page
        })

    async def handle_api_explorer_block_detail(self, request):
        block_hash = request.match_info['block_hash']
        chain = self.network_manager.chain_manager
        
        # Try to find by hash
        # We need validation logic to distinguish standard hash or maybe height?
        # User requirement says "click on block number (row)". 
        # So we might want to support height lookup here too?
        # For now, let's stick to hash as the primary ID, and the frontend links to /block/<hash>
        
        block = chain.get_block_by_hash(block_hash)
        if not block:
            return web.json_response({'error': 'Block not found'}, status=404)
            
        # Get Next Hash (if exists) -> Requires looking up by height + 1
        # Get Height first
        # We don't have height in the Block object instantly, we have to look it up in index?
        # chain.get_block_by_hash returns deserialized block, but we lose the 'height' context unless we look it up again.
        # Actually BlockIndex has it.
        
        block_info = chain.block_index.get_block_info(block_hash)
        height = block_info['height'] if block_info else -1
        
        next_hash = None
        if height != -1:
            next_hash = chain.get_block_hash(height + 1)

        # Transactions
        txs = []
        for tx in block.vtx:
            txs.append({
                'txid': tx.get_hash().hex(),
                'version': tx.version,
                'locktime': tx.locktime,
                'vin_count': len(tx.vin),
                'vout_count': len(tx.vout),
                'is_coinbase': tx.is_coinbase()
            })

        return web.json_response({
            'header': {
                'hash': block_hash,
                'version': block.header.version,
                'prev_block': block.header.prev_block.hex(),
                'merkle_root': block.header.merkle_root.hex(),
                'timestamp': block.header.timestamp,
                'bits': block.header.bits,
                'nonce': block.header.nonce,
                'height': height,
                'next_block': next_hash
            },
            'transactions': txs,
            'size': len(block.serialize())
        })

    async def handle_index(self, request):
        template = self.jinja_env.get_template('dashboard.html')
        
        # Context
        stun_ip = getattr(self.network_manager, 'stun_ip', '127.0.0.1')
        
        # Pre-fill seed IP with discovered seed or node's own LAN IP
        default_seed_ip = (
            getattr(self.network_manager, 'discovered_seed', None)
            or getattr(self.network_manager, 'local_ip', '')
        )
        
        ctx = {
            'seed_ip': default_seed_ip,
            'port': self.network_manager.port,
            'stun_ip': stun_ip
        }
        return web.Response(text=template.render(ctx), content_type='text/html')

    # --- NETWORK HANDLERS ---
    
    async def handle_connect(self, request):
        data = await request.json()
        seed_ip = data.get('seed_ip', '').strip()
        
        # If no IP given, use discovered seed or own IP
        if not seed_ip:
            seed_ip = (
                getattr(self.network_manager, 'discovered_seed', None)
                or getattr(self.network_manager, 'local_ip', '127.0.0.1')
            )
             
        # 1. Configure STUN
        # Enforce 3478 as per requirement
        self.network_manager.configure_stun(seed_ip, 3478)
        
        # 2. Connect to Seeds
        ports = [9333, 9334, 9335]
        connected = 0
        for p in ports:
            target = f"{seed_ip}:{p}"
            asyncio.create_task(self.network_manager.connect_to_peer(target))
            connected += 1
            
        return web.json_response({'status': 'initiated', 'connected_count': connected, 'seed_ip': seed_ip})

    async def handle_peers(self, request):
        peers_list = []
        # Active
        if self.network_manager and hasattr(self.network_manager, 'peers'):
              for (ip, port) in list(self.network_manager.peers):
                  peers_list.append({'ip': ip, 'port': port, 'status': 'ACTIVE', 'can_delete': False})
        
        # ICE
        if hasattr(self.network_manager, 'ice_connections'):
             for (ip, port) in self.network_manager.ice_connections:
                 if (ip, port) not in self.network_manager.peers:
                     peers_list.append({'ip': ip, 'port': port, 'status': 'ACTIVE (ICE)', 'can_delete': False})

        # Failed
        if hasattr(self.network_manager, 'failed_peers'):
             for (ip, port), data in self.network_manager.failed_peers.items():
                 peers_list.append({'ip': ip, 'port': port, 'status': f"FAILED: {data.get('error','')}", 'can_delete': True})
        
        # Add basic stats
        best = self.network_manager.chain_manager.block_index.get_best_block()
        height = best['height'] if best else 0
        
        return web.json_response({'peers': peers_list, 'height': height})
        
    async def handle_delete_peer(self, request):
        data = await request.json()
        self.network_manager.remove_failed_peer(data.get('ip'), data.get('port'))
        return web.json_response({'status': 'deleted'})

    async def handle_reset(self, request):
        self.network_manager.reset_data()
        return web.json_response({'status': 'ok'})
        
    async def handle_get_logs(self, request):
        ip = request.query.get('ip')
        port = int(request.query.get('port'))
        logs = self.network_manager.peer_logs.get((ip, port), [])
        return web.json_response({'logs': logs})

    async def handle_send_test(self, request):
        data = await request.json()
        await self.network_manager.send_test_message(data.get('ip'), data.get('port'), "TEST_PACKET")
        return web.json_response({'status': 'sent'})
        
    async def handle_get_stats(self, request):
        best_block = self.network_manager.chain_manager.block_index.get_best_block()
        height = best_block['height'] if best_block else 0
        
        # Dynamic difficulty
        from icsicoin.consensus.validation import calculate_next_bits, DIFFICULTY_ADJUSTMENT_INTERVAL
        bits = calculate_next_bits(self.network_manager.chain_manager, height + 1)

        # Calculate Reward
        # 50 coins initial, halve every 210000 blocks
        halvings = height // 210000
        if halvings >= 64:
            reward = 0
        else:
            reward = 50 * (0.5 ** halvings)
            
        halving_countdown = 210000 - (height % 210000)
        
        return web.json_response({
            'height': height,
            'difficulty': bits,
            'reward': reward,
            'halving_countdown': halving_countdown,
            'difficulty_countdown': DIFFICULTY_ADJUSTMENT_INTERVAL - (height % DIFFICULTY_ADJUSTMENT_INTERVAL),
            'test_msg_received': self.network_manager.test_msg_count
        })

    async def handle_test_stun(self, request):
        # Accept IP from frontend, fall back to manager's STUN config
        try:
            data = await request.json()
            stun_ip = data.get('stun_ip', '').strip() or self.network_manager.stun_ip
        except Exception:
            stun_ip = self.network_manager.stun_ip
        
        # Update manager's STUN config to match
        self.network_manager.configure_stun(stun_ip, self.network_manager.stun_port)
        
        success, msg = await self.network_manager.test_stun_connection(
            stun_ip, self.network_manager.stun_port
        )
        return web.json_response({'success': success, 'message': msg})

    async def handle_discovery_status(self, request):
        """Returns multicast discovery status."""
        return web.json_response({
            'discovered_seed': self.network_manager.discovered_seed,
            'own_ip': getattr(self.network_manager, 'local_ip', ''),
            'beacon_active': getattr(self.network_manager.multicast_beacon, 'running', False),
            'known_multicast_peers': list(getattr(self.network_manager.multicast_beacon, 'known_peers', []))
        })

    # --- WALLET HANDLERS ---

    async def handle_wallet_list(self, request):
        # We need balances for each wallet
        # Scanning chain state for each might be slow if many keys
        wallets = []
        wallet_keys = getattr(self.network_manager, 'wallet', None)
        if wallet_keys:
             # Need to implement Wallet.get_keys_with_names
             # Assuming keys list: {priv, pub, addr, name}
             # Wait, existing wallet keys only had {priv, pub, addr}. User asked for names.
             # I need to update Wallet data structure if I haven't yet.
             # Or just allow adding name in frontend/local storage?
             # No, user said "Let the user name their wallet and attach that to the metadata."
             # So I should update Wallet.get_new_address(label)
             # But for now, let's just return what we have, adding placeholder name or stored.
             
             for k in wallet_keys.keys:
                 name = k.get('name', 'Unnamed Wallet')
                 addr = k['addr']
                 # Balance check
                 # We need to access chain_state. 
                 # We can use wallet.get_balance() but that sums ALL.
                 # We need per-address balance.
                 # Let's add a helper here or in wallet.
                 
                 # Manual balance calc for this addr
                 pubkey_hash = binascii.unhexlify(addr)
                 script = b'\x76\xa9\x14' + pubkey_hash + b'\x88\xac'
                 utxos = self.network_manager.chain_manager.chain_state.get_utxos_by_script(script)
                 balance = sum([u['amount'] for u in utxos]) / 100000000.0 # Convert satoshi to coin
                 
                 wallets.append({'address': addr, 'name': name, 'balance': balance})
                 
        return web.json_response({'wallets': wallets})

    async def handle_wallet_create(self, request):
        data = await request.json()
        name = data.get('name', 'My Wallet')
        wallet = self.network_manager.wallet
        addr = wallet.get_new_address()
        # Add name metadata
        wallet.keys[-1]['name'] = name
        wallet.save()
        return web.json_response({'address': addr, 'name': name})

    async def handle_wallet_delete(self, request):
        # "Purge"
        # We need a delete method on wallet
        # wallet.keys.remove(...)
        # For now, just remove from memory and save
        data = await request.json()
        addr = data.get('address')
        wallet = self.network_manager.wallet
        wallet.keys = [k for k in wallet.keys if k['addr'] != addr]
        wallet.save()
        return web.json_response({'status': 'deleted'})

    async def handle_wallet_rename(self, request):
        data = await request.json()
        addr = data.get('address')
        new_name = data.get('name', '').strip()
        if not addr or not new_name:
            return web.json_response({'error': 'Address and name required'}, status=400)
        wallet = self.network_manager.wallet
        for k in wallet.keys:
            if k['addr'] == addr:
                k['name'] = new_name
                wallet.save()
                return web.json_response({'status': 'renamed', 'name': new_name})
        return web.json_response({'error': 'Wallet not found'}, status=404)

    async def handle_wallet_send(self, request):
        data = await request.json()
        to_addr = data.get('to')
        amount = float(data.get('amount'))
        
        try:
            # Convert to satoshi
            satoshi = int(amount * 100000000)
            tx = self.network_manager.wallet.create_transaction(
                to_addr, satoshi, self.network_manager.chain_manager.chain_state
            )
            
            # Broadcast
            # Validation first?
            # NetworkManager.broadcast_transaction
            # We don't have that method explicitly?
            # We have protocol message handling.
            # We should add tx to mempool AND broadcast "inv".
            
            # 1. Add to Mempool (Validation happens here)
            # validation.validate_transaction needs UTXO set?
            # mempool.add_transaction(tx, chain_state)
            if self.network_manager.mempool.add_transaction(tx):
                # Broadcast INV to peers
                import json as json_mod
                from icsicoin.network.messages import Message
                tx_hash_hex = tx.get_hash().hex()
                inv_msg = {
                    "type": "inv",
                    "inventory": [{"type": "tx", "hash": tx_hash_hex}]
                }
                json_payload = json_mod.dumps(inv_msg).encode('utf-8')
                out_m = Message('inv', json_payload)
                
                for peer_addr, peer_writer in self.network_manager.active_connections.items():
                    try:
                        peer_writer.write(out_m.serialize())
                        await peer_writer.drain()
                    except: pass
                
                return web.json_response({'status': 'sent', 'txid': tx.get_hash().hex()})
            else:
                 return web.json_response({'error': 'Transaction rejected by mempool (Invalid or double spend)'}, status=400)
                 
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def handle_wallet_export(self, request):
        # Return JSON of keys
        # Security warning: plaintext private keys
        return web.json_response(self.network_manager.wallet.keys)

    async def handle_wallet_import(self, request):
        try:
            data = await request.json()
            if isinstance(data, list):
                self.network_manager.wallet.keys.extend(data)
                self.network_manager.wallet.save()
                return web.json_response({'status': 'imported', 'count': len(data)})
            return web.json_response({'error': 'Invalid format (expected list)'}, status=400)
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)

    # --- MINER HANDLERS ---
    
    async def handle_miner_status(self, request):
        return web.json_response(self.miner_controller.get_status())

    async def handle_miner_start(self, request):
        data = await request.json()
        target = data.get('target_address') # Not used yet but passed
        success, msg = self.miner_controller.start_mining(target)
        return web.json_response({'success': success, 'message': msg})

    async def handle_miner_stop(self, request):
        success, msg = self.miner_controller.stop_mining()
        return web.json_response({'success': success, 'message': msg})

    # --- BEGGAR HANDLERS ---

    async def handle_beggar_start(self, request):
        data = await request.json()
        address = data.get('address', '').strip()
        if not address:
            return web.json_response({'error': 'No wallet address provided'}, status=400)
        await self.network_manager.start_begging(address)
        return web.json_response({'status': 'begging', 'address': address})

    async def handle_beggar_stop(self, request):
        await self.network_manager.stop_begging()
        return web.json_response({'status': 'stopped'})

    async def handle_beggar_list(self, request):
        beggars = self.network_manager.get_beggar_list()
        active = None
        if self.network_manager.active_beg:
            import time as time_mod
            ab = self.network_manager.active_beg
            remaining = max(0, int(20 * 60 - (time_mod.time() - ab['started_at'])))
            active = {'address': ab['address'], 'remaining_seconds': remaining}
        return web.json_response({'beggars': beggars, 'active_beg': active})

    async def handle_rpc_config_get(self, request):
        url = f"http://127.0.0.1:{self.rpc_port}/api/rpc/config"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return web.json_response(await resp.json())
                    else:
                        return web.json_response({'error': f'RPC Server returned {resp.status}'}, status=502)
        except Exception as e:
            return web.json_response({'error': f"Failed to reach RPC server: {e}"}, status=502)

    async def handle_rpc_config_post(self, request):
        url = f"http://127.0.0.1:{self.rpc_port}/api/rpc/config"
        try:
            data = await request.json()
            
            # Update miner controller if Present
            if self.miner_controller:
                u = data.get('user', self.user)
                p = data.get('password', self.password)
                self.miner_controller.set_credentials(u, p)

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as resp:
                    if resp.status == 200:
                        return web.json_response(await resp.json())
                    else:
                        try:
                            err = await resp.json()
                            return web.json_response(err, status=resp.status)
                        except:
                            return web.json_response({'error': f'RPC Server returned {resp.status}'}, status=502)
        except Exception as e:
            return web.json_response({'error': f"Failed to reach RPC server: {e}"}, status=502)

    async def handle_miner_download(self, request):
        import zipfile
        import io
        
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Add miner.py (assuming it is in the parent directory of icsicoin/web/server.py... wait, no)
            # server.py is in end_user_node/icsicoin/web/server.py
            # miner.py is in end_user_node/miner.py
            # So root is three levels up? 
            # __file__ = .../icsicoin/web/server.py
            # root = .../
            
            # Let's verify paths.
            # WORKDIR is /app in Docker.
            # server.py is imported.
            # We can use reference from where we run.
            
            # Docker WORKDIR is /app
            # /app/miner.py exists.
            # /app/icsicoin/ exists.
            
            base_dir = os.getcwd() # Should be /app
            
            # Add miner.py
            miner_path = os.path.join(base_dir, 'miner.py')
            if os.path.exists(miner_path):
                zip_file.write(miner_path, arcname='miner.py')
            
            # Add requirements.txt (Create on fly)
            zip_file.writestr('requirements.txt', 'requests\nscrypt\n')

            # Add icsicoin package
            icsicoin_dir = os.path.join(base_dir, 'icsicoin')
            for root, dirs, files in os.walk(icsicoin_dir):
                if '__pycache__' in dirs:
                    dirs.remove('__pycache__') # Don't traverse
                
                for file in files:
                    if file == '.DS_Store' or file.endswith('.pyc'):
                        continue
                    
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, base_dir)
                    zip_file.write(file_path, arcname=arcname)
        
        buffer.seek(0)
    async def handle_data_download(self, request):
        import zipfile
        import io
        import json
        
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Add wallet_export.json (User requested valid json export)
            # This matches the format used by handle_wallet_export defaults
            keys_json = json.dumps(self.network_manager.wallet.keys, indent=4)
            zip_file.writestr('wallet_export.json', keys_json)
            
            # 2. Add all files from data directory (chain state, wallet.dat, etc)
            data_dir = self.network_manager.data_dir
            
            # We want them inside a folder in the zip for cleanliness
            zip_root = "node_data"
            
            for root, dirs, files in os.walk(data_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Create relative path for zip
                    rel_path = os.path.relpath(file_path, data_dir)
                    arcname = os.path.join(zip_root, rel_path)
                    
                    try:
                        zip_file.write(file_path, arcname=arcname)
                    except Exception as e:
                        logger.warning(f"Failed to zip {file_path}: {e}")
        
        buffer.seek(0)
        return web.Response(
            body=buffer.getvalue(),
            headers={
                'Content-Disposition': 'attachment; filename="icsi_your_data.zip"',
                'Content-Type': 'application/zip'
            }
        )
