import logging
import asyncio
from aiohttp import web
import os
import binascii
import json
import io
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
        
        # API - Wallet
        self.app.router.add_get('/api/wallet/list', self.handle_wallet_list)
        self.app.router.add_post('/api/wallet/create', self.handle_wallet_create)
        self.app.router.add_post('/api/wallet/delete', self.handle_wallet_delete) # Not implemented in Wallet yet, stick to purge
        self.app.router.add_post('/api/wallet/send', self.handle_wallet_send)
        self.app.router.add_get('/api/wallet/export', self.handle_wallet_export)
        self.app.router.add_post('/api/wallet/import', self.handle_wallet_import)
        
        # API - Miner
        self.app.router.add_get('/api/miner/status', self.handle_miner_status)
        self.app.router.add_post('/api/miner/start', self.handle_miner_start)
        self.app.router.add_post('/api/miner/stop', self.handle_miner_stop)

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
        
        ctx = {
            'seed_ip': "", # Persistent? Could store in browser localStorage or cookie.
            'port': self.network_manager.port,
            'stun_ip': stun_ip
        }
        return web.Response(text=template.render(ctx), content_type='text/html')

    # --- NETWORK HANDLERS ---
    
    async def handle_connect(self, request):
        data = await request.json()
        seed_ip = data.get('seed_ip')
        
        if not seed_ip:
             return web.json_response({'error': 'Missing Seed IP'}, status=400)
             
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
            
        return web.json_response({'status': 'initiated', 'connected_count': connected})

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
        
        bits = 0x1f019999 # Default/Genesis bits (Updated to 10x diff)
        if best_block:
             try:
                 # Read raw block to get bits
                 raw = self.network_manager.block_store.read_block(
                     best_block['file_num'], 
                     best_block['offset'], 
                     best_block['length']
                 )
                 if raw:
                     block = Block.deserialize(io.BytesIO(raw))
                     bits = block.header.bits
             except Exception as e:
                 logger.error(f"Error reading best block bits: {e}")

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
        # Trigger explicit STUN test via manager
        # Need to expose a method in manager or use existing
        # Re-using logic from before
        success, msg = await self.network_manager.test_stun_connection(
            self.network_manager.stun_ip, self.network_manager.stun_port
        )
        return web.json_response({'success': success, 'message': msg})

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
                # 2. Broadcast INV
                # network_manager.relay_transaction(tx) -> Helper needed
                # For now, simple loop:
                inv_msg = self.network_manager._create_inv_message([tx.get_hash()]) # access private/internal helper or recreate
                # Actually, inv message creation logic:
                from icsicoin.network.messages import InvMessage
                inv = InvMessage()
                inv.items.append((1, tx.get_hash())) # 1=MSG_TX
                
                await self.network_manager.broadcast_message(inv)
                
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
