import logging
import asyncio
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
        
        # API - Wallet
        self.app.router.add_get('/api/wallet/list', self.handle_wallet_list)
        self.app.router.add_post('/api/wallet/create', self.handle_wallet_create)
        self.app.router.add_post('/api/wallet/delete', self.handle_wallet_delete) # Not implemented in Wallet yet, stick to purge
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
        from icsicoin.consensus.validation import calculate_next_bits
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
