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
import base64
from cryptography import fernet
from aiohttp_session import setup as setup_session, get_session, session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage
import hashlib

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
        
        # Web Auth Config
        self.data_dir = self.network_manager.data_dir
        self.config_file = os.path.join(self.data_dir, 'node_config.json')
        self.web_auth_config = self._load_web_auth_config()
        
        # Setup Session Middleware
        # Use a fixed key if present in config, else generate one (invalidates sessions on restart if not saved)
        # For persistence, we should save the key.
        self.secret_key = self._get_or_create_secret_key()
        
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
        self.app.router.add_get('/management', self.handle_management_page)
        self.app.router.add_get('/db_query', self.handle_db_query_page)
        self.app.router.add_post('/api/db/query', self.handle_api_db_query)
        self.app.router.add_get('/secret', self.handle_secret_page)
        self.app.router.add_static('/static', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'static'))
        
        # API - Network
        self.app.router.add_route('*', '/api/connect', self.handle_connect)
        self.app.router.add_route('*', '/api/peers', self.handle_peers)
        self.app.router.add_route('*', '/api/peers/delete', self.handle_delete_peer)
        self.app.router.add_route('*', '/api/reset', self.handle_reset)
        self.app.router.add_route('*', '/api/logs', self.handle_get_logs)
        self.app.router.add_route('*', '/api/test/send', self.handle_send_test)
        self.app.router.add_route('*', '/api/stats', self.handle_get_stats)
        self.app.router.add_route('*', '/api/stun/test', self.handle_test_stun)
        self.app.router.add_route('*', '/api/discovery/status', self.handle_discovery_status)
        self.app.router.add_post('/api/integrity_check', self.handle_integrity_check)
        
        # API - RPC Config
        # API - RPC Config
        # handle_rpc_config_post will handle both updates and reads (if body has only auth)
        self.app.router.add_get('/api/rpc/config', self.handle_rpc_config_get)
        self.app.router.add_post('/api/rpc/config', self.handle_rpc_config_post)
        
        # Miner Download
        self.app.router.add_route('*', '/api/miner/download', self.handle_miner_download)
        
        # Your Data Download
        self.app.router.add_route('*', '/api/data/download', self.handle_data_download)

        # Web Auth Routes
        self.app.router.add_get('/setup', self.handle_setup_page)
        self.app.router.add_get('/login', self.handle_login_page)
        self.app.router.add_route('*', '/api/auth/setup', self.handle_api_setup)
        self.app.router.add_route('*', '/api/auth/login', self.handle_api_login)
        self.app.router.add_route('*', '/api/auth/logout', self.handle_api_logout)

        # API - Wallet
        self.app.router.add_route('*', '/api/wallet/list', self.handle_wallet_list)
        self.app.router.add_route('*', '/api/wallet/create', self.handle_wallet_create)
        self.app.router.add_route('*', '/api/wallet/delete', self.handle_wallet_delete)
        self.app.router.add_route('*', '/api/wallet/send', self.handle_wallet_send)
        self.app.router.add_route('*', '/api/wallet/export', self.handle_wallet_export)
        self.app.router.add_route('*', '/api/wallet/import', self.handle_wallet_import)
        self.app.router.add_post('/api/stun/test', self.handle_test_stun)
        self.app.router.add_post('/api/stun/set', self.handle_set_stun)
        
        # API - Miner
        self.app.router.add_route('*', '/api/wallet/rename', self.handle_wallet_rename)
        self.app.router.add_route('*', '/api/miner/status', self.handle_miner_status)
        self.app.router.add_route('*', '/api/miner/start', self.handle_miner_start)
        self.app.router.add_route('*', '/api/miner/stop', self.handle_miner_stop)

        # API - Beggar
        self.app.router.add_route('*', '/api/beggar/start', self.handle_beggar_start)
        self.app.router.add_route('*', '/api/beggar/stop', self.handle_beggar_stop)
        self.app.router.add_route('*', '/api/beggar/list', self.handle_beggar_list)
        
        # Explorer Routes
        self.app.router.add_get('/explorer', self.handle_explorer_page)
        self.app.router.add_get('/explorer/block/{block_hash}', self.handle_explorer_detail_page)
        self.app.router.add_route('*', '/api/explorer/blocks', self.handle_api_explorer_blocks)
        self.app.router.add_route('*', '/api/explorer/block/{block_hash}', self.handle_api_explorer_block_detail)
        self.app.router.add_route('*', '/api/explorer/balance/{address}', self.handle_api_explorer_balance)
        self.app.router.add_route('*', '/api/explorer/search', self.handle_api_explorer_search)
        
        self.app.router.add_get('/explorer/address/{address}', self.handle_explorer_address_page)
        self.app.router.add_get('/api-docs', self.handle_api_docs_page)
        self.app.router.add_get('/explainer/forks', self.handle_forks_explainer)

        self.runner = None
        self.site = None

    async def start(self):
        # Setup Session Middleware
        # We pass the Fernet instance directly to avoid aiohttp_session 
        # double-encoding the key if passed as bytes.
        try:
            f = fernet.Fernet(self.secret_key)
            setup_session(self.app, EncryptedCookieStorage(f))
        except Exception as e:
            logger.critical(f"Failed to initialize session storage: {e}")
            raise e
        
        # Add Auth Middleware
        self.app.middlewares.append(self.auth_middleware)
        
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

    # --- MANAGEMENT ---
    async def handle_management_page(self, request):
        return await self.render_template('management.html')

    async def handle_db_query_page(self, request):
        return await self.render_template('db_query.html')

    async def handle_api_db_query(self, request):
        data = await self._get_json(request)
        query_id = data.get('query_id')
        params = data.get('params', {})
        
        # Security: Allow List of Safe Queries
        # We execute raw SQL here but ONLY the strings defined below.
        # User input only goes into parameterized bindings (?)
        
        query_map = {
            'get_max_height': {
                'db': 'block_index',
                'sql': "SELECT MAX(height) as max_height FROM block_index;"
            },
            'get_forks': {
                'db': 'block_index',
                'sql': "SELECT height, COUNT(*) as count FROM block_index GROUP BY height HAVING count > 1 ORDER BY height DESC LIMIT 10;"
            },
            'get_orphans': {
                'db': 'block_index',
                'sql': "SELECT * FROM block_index WHERE prev_hash NOT IN (SELECT block_hash FROM block_index) AND height > 0;"
            },
            'get_block': {
                'db': 'block_index',
                'sql': "SELECT * FROM block_index WHERE height = ?;",
                'args': ['height']
            },
            'get_supply': {
                'db': 'chainstate',
                'sql': "SELECT SUM(amount) / 100000000.0 as supply FROM utxo;"
            },
            'get_rich_list': {
                'db': 'chainstate',
                'sql': "SELECT HEX(script_pubkey) as script, COUNT(*) as utxo_count, SUM(amount)/100000000.0 as balance FROM utxo GROUP BY script_pubkey ORDER BY balance DESC LIMIT 10;"
            },
            'get_tx_count': {
                'db': 'block_index',
                'sql': "SELECT COUNT(*) as count FROM tx_index;"
            },
            'get_chain_size': {
                'db': 'block_index',
                'sql': "SELECT SUM(length) as bytes FROM block_index;"
            },
            'get_avg_block_size': {
                'db': 'block_index',
                'sql': "SELECT AVG(length) as avg_bytes FROM block_index;"
            }
        }
        
        if query_id not in query_map:
            return web.json_response({'error': 'Invalid Query ID'}, status=400)
            
        qi = query_map[query_id]
        sql = qi['sql']
        db_name = qi['db']
        
        # Build Args
        sql_args = []
        if 'args' in qi:
            for arg_name in qi['args']:
                if arg_name not in params:
                    return web.json_response({'error': f'Missing parameter: {arg_name}'}, status=400)
                sql_args.append(params[arg_name])
        
        # Execute
        try:
            # We need to access the DB connections from the manager -> chain_manager -> block_index/chain_state
            # But the 'databases.py' classes usually manage their own connections carefully.
            # It's better to ask the DB object to run a query if exposed, 
            # OR open a read-only cursor here. 
            # Given we have WAL mode, read-only connection is safe.
            
            import sqlite3
            
            db_path = ""
            if db_name == 'block_index':
                db_path = self.network_manager.chain_manager.block_index.db_path
            elif db_name == 'chainstate':
                db_path = self.network_manager.chain_manager.chain_state.db_path
                
            # Connect Read Only
            # uri=True allows 'file:path?mode=ro'
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(sql, tuple(sql_args))
            rows = cursor.fetchall()
            
            # Convert rows to dicts
            result = [dict(row) for row in rows]
            
            conn.close()
            
            return web.json_response({'result': result})
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # --- AUTHENTICATION ---

    def _load_web_auth_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
        return {}

    def _save_web_auth_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.web_auth_config, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def _get_or_create_secret_key(self):
        # Check if we have a stored key
        if 'secret_key' in self.web_auth_config:
            try:
                # Handle legacy double-encoded or simple string
                stored = self.web_auth_config['secret_key']
                
                # Try simple encode first 
                key = stored.encode()
                
                # Validate with Fernet
                fernet.Fernet(key)
                return key
            except Exception:
                # If simple fail, try the legacy decode (double encoded)
                try:
                    key = base64.urlsafe_b64decode(stored)
                    fernet.Fernet(key)
                    return key
                except Exception:
                    logger.warning("Invalid stored secret_key, generating new one.")
                    pass
        
        # Generate new (Simple storage)
        key = fernet.Fernet.generate_key()
        self.web_auth_config['secret_key'] = key.decode()
        self._save_web_auth_config()
        return key

    @web.middleware
    async def auth_middleware(self, request, handler):
        # Public Routes (No Auth Required)
        public_prefixes = [
            '/setup', '/login', '/static', 
            '/api/auth/setup', '/api/auth/login'
        ]
        
        # Check if path starts with any public route
        for r in public_prefixes:
            if request.path.startswith(r):
                return await handler(request)
        
        # Check Config Existence
        if 'username' not in self.web_auth_config or 'password_hash' not in self.web_auth_config:
            return web.HTTPFound('/setup')
            
        # Check Session
        session = await get_session(request)
        authenticated = 'user' in session

        # If not authenticated, check POST params (Dual Auth)
        if not authenticated and request.method == 'POST' and request.path.startswith('/api/'):
            try:
                # Read body and store for handlers
                # We use request.json() here which consumes the stream
                data = await request.json()
                request['json_body'] = data 
                
                u = data.get('username')
                p = data.get('password')
                
                if u and p and u == self.web_auth_config.get('username'):
                     saved_hash = self.web_auth_config.get('password_hash')
                     input_hash = hashlib.sha256(p.encode()).hexdigest()
                     if input_hash == saved_hash:
                         authenticated = True
            except Exception:
                pass

        if not authenticated:
            # If API request (JSON), return 401 instead of redirect
            if request.path.startswith('/api/'):
                return web.json_response({'error': 'Unauthorized'}, status=401)
            return web.HTTPFound('/login')
            
        return await handler(request)

    async def _get_json(self, request):
        """Helper to get JSON from request, checking middleware cache first."""
        if 'json_body' in request:
            return request['json_body']
        return await request.json()

    async def handle_setup_page(self, request):
        if 'username' in self.web_auth_config:
             return web.HTTPFound('/login')
        return await self.render_template('setup.html')

    async def handle_login_page(self, request):
        if 'username' not in self.web_auth_config:
             return web.HTTPFound('/setup')
        return await self.render_template('login.html')

    async def handle_api_setup(self, request):
        if 'username' in self.web_auth_config:
             return web.json_response({'error': 'Already setup'}, status=400)
             
        data = await self._get_json(request)
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return web.json_response({'error': 'Missing fields'}, status=400)
            
        # Hash password
        # Simple SHA256 for this context
        hashed = hashlib.sha256(password.encode()).hexdigest()
        
        self.web_auth_config['username'] = username
        self.web_auth_config['password_hash'] = hashed
        self._save_web_auth_config()
        
        # Auto login
        session = await get_session(request)
        session['user'] = username
        
        return web.json_response({'status': 'ok'})

    async def handle_api_login(self, request):
        data = await self._get_json(request)
        username = data.get('username')
        password = data.get('password')
        
        saved_user = self.web_auth_config.get('username')
        saved_hash = self.web_auth_config.get('password_hash')
        
        if not saved_user or not saved_hash:
             return web.json_response({'error': 'Not setup'}, status=400)
             
        if username != saved_user:
            return web.json_response({'error': 'Invalid credentials'}, status=401)
            
        input_hash = hashlib.sha256(password.encode()).hexdigest()
        if input_hash != saved_hash:
             return web.json_response({'error': 'Invalid credentials'}, status=401)
             
        session = await get_session(request)
        session['user'] = username
        
        return web.json_response({'status': 'ok'})

    async def handle_api_logout(self, request):
        session = await get_session(request)
        session.clear()
        return web.json_response({'status': 'ok'})

    async def handle_explorer_page(self, request):
        return await self.render_template('explorer.html')

    async def handle_explorer_address_page(self, request):
        address = request.match_info['address']
        return await self.render_template('address_detail.html', address=address)

    async def handle_api_docs_page(self, request):
        return await self.render_template('api_docs.html')

    async def handle_forks_explainer(self, request):
        return await self.render_template('forks_explainer.html')

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
        # Transactions
        txs = []
        for tx in block.vtx:
            outputs = []
            for vout in tx.vout:
                addr = self._extract_address(vout.script_pubkey)
                outputs.append({
                    'amount': vout.amount / 100000000.0,
                    'address': addr
                })

            txs.append({
                'txid': tx.get_hash().hex(),
                'version': tx.version,
                'locktime': tx.locktime,
                'vin_count': len(tx.vin),
                'vout_count': len(tx.vout),
                'is_coinbase': tx.is_coinbase(),
                'outputs': outputs
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

    async def handle_api_explorer_balance(self, request):
        address = request.match_info['address']
        try:
            # Reconstruct P2PKH script
            pubkey_hash = binascii.unhexlify(address)
            script = b'\x76\xa9\x14' + pubkey_hash + b'\x88\xac'
            
            chain = self.network_manager.chain_manager
            utxos = chain.chain_state.get_utxos_by_script(script)
            
            balance = sum([u['amount'] for u in utxos]) / 100000000.0
            
            balance = sum([u['amount'] for u in utxos]) / 100000000.0
            
            return web.json_response({
                'address': address,
                'balance': balance,
                'utxo_count': len(utxos),
                'utxos': utxos # Include full List
            })
        except Exception as e:
            return web.json_response({'error': f"Invalid Address or Error: {e}"}, status=400)

    def _extract_address(self, script_pubkey):
        # P2PKH: 76 a9 14 <20-bytes> 88 ac
        if len(script_pubkey) == 25 and script_pubkey.startswith(b'\x76\xa9\x14') and script_pubkey.endswith(b'\x88\xac'):
             pubkey_hash = script_pubkey[3:23]
             return binascii.hexlify(pubkey_hash).decode('utf-8')
        return "Non-Standard / OP_RETURN"

    async def handle_api_explorer_search(self, request):
        query = request.query.get('q', '').strip()
        if not query:
             return web.json_response({'error': 'Empty query'})
             
        chain = self.network_manager.chain_manager
        
        # 1. Address Search (Heuristic: 25-50 chars, Alphanumeric)
        # iCSI addresses are hex (40 chars) or potentially Base58 in future?
        # Let's assume anything looking like an address is one.
        # But wait, a block hash is also hex.
        # Address is usually shorter than 64 chars block hash.
        # 40 chars -> Likely Address (RIPEMD160 hex)
        # > 50 chars -> Likely Block Hash (SHA256 hex is 64)
        if 20 <= len(query) <= 50 and all(c in '0123456789abcdefABCDEF' for c in query):
             return web.json_response({'redirect': f'/explorer/address/{query}'})

        # 2. Block Height Search (Primary Interpretation for Integers)
        if query.isdigit():
            height = int(query)
            # Verify if this height exists
            block_hash = chain.get_block_hash(height)
            if block_hash:
                 return web.json_response({'redirect': f'/explorer/block/{block_hash}'})
            # If not found at height, fallthrough to check if it's a hash starting with numbers
            
        # 3. Block Hash / Partial Hash Search
        # Search DB for hashes starting with query
        matches = chain.block_index.search_block_hashes(query)
        
        if len(matches) == 1:
            # Exact or single partial match
            return web.json_response({'redirect': f'/explorer/block/{matches[0]}'})
        elif len(matches) > 1:
            # Ambiguous
            # Return error with suggestions? Or just first one?
            # For now, let's return error with cached list
            return web.json_response({'error': f'Ambiguous query. Found {len(matches)} blocks starting with {query}. Try more characters.'})
            
        return web.json_response({'error': f'No results found for {query}'})

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

    async def handle_secret_page(self, request):
        template = self.jinja_env.get_template('secret_message.html')
        return web.Response(text=template.render(), content_type='text/html')

    # --- NETWORK HANDLERS ---
    
    async def handle_connect(self, request):
        data = await self._get_json(request)
        seed_ip = data.get('seed_ip', '').strip()
        
        # If no IP given, use discovered seed or own IP
        if not seed_ip:
            seed_ip = (
                getattr(self.network_manager, 'discovered_seed', None)
                or getattr(self.network_manager, 'local_ip', '127.0.0.1')
            )
             
        # 1. Parse Input
        stun_host = seed_ip
        targets = []
        
        if ':' in seed_ip:
            # User provided specific port (e.g. 1.2.3.4:9333)
            parts = seed_ip.split(':')
            stun_host = parts[0]
            targets = [seed_ip]
        else:
            # User provided IP only, try default ports
            stun_host = seed_ip
            targets = [f"{seed_ip}:{p}" for p in [9333, 9334, 9335]]

        # 2. Configure STUN - REMOVED!
        # Original code blindly reconfigured STUN to the new peer, breaking subnet/ICE.
        # self.network_manager.configure_stun(stun_host, 3478)
        # We should NOT change global STUN settings here. 
        # The user just wants to add a peer connection.
        pass
        
        # 3. Connect to Seeds
        connected = 0
        for target in targets:
            asyncio.create_task(self.network_manager.connect_to_peer(target))
            connected += 1
            
        return web.json_response({'status': 'initiated', 'connected_count': connected, 'seed_ip': seed_ip})

    async def handle_set_stun(self, request):
        data = await self._get_json(request)
        stun_ip = data.get('stun_ip', '').strip()
        stun_port = int(data.get('stun_port', 3478))
        
        if not stun_ip:
            return web.json_response({'error': 'STUN IP required'}, status=400)
            
        self.network_manager.configure_stun(stun_ip, stun_port)
        return web.json_response({'status': 'configured', 'stun_ip': stun_ip, 'stun_port': stun_port})

    async def handle_peers(self, request):
        peers_list = []
        import time 
        now = time.time()
        
        def is_visible(peer):
            # Rule 1: Must have logs
            if peer not in self.network_manager.peer_logs or not self.network_manager.peer_logs[peer]:
                return False
            # Rule 2: Active in last 60s
            last_time = self.network_manager.peer_last_log_time.get(peer, 0)
            if now - last_time > 60:
                return False
            return True

        # Peers by IP container: {ip: {'port': p, 'status': s, 'can_delete': b, 'timestamp': t, 'priority': int}}
        # Priority: 
        # 3: Active Listening Port (9333-9335)
        # 2: Active Other Port
        # 1: ICE Active
        # 0: Failed
        peers_by_ip = {}

        def add_candidate(ip, port, status, can_delete, priority):
            # Check visibility first
            if not is_visible((ip, port)):
                 return

            if ip not in peers_by_ip:
                peers_by_ip[ip] = {
                    'ip': ip, 'port': port, 'status': status, 
                    'can_delete': can_delete, 
                    'priority': priority,
                    'height': self.network_manager.peer_stats.get((ip, port), {}).get('height', 0),
                    'user_agent': self.network_manager.peer_stats.get((ip, port), {}).get('user_agent', '')
                }
            else:
                # Existing entry, check priority
                current = peers_by_ip[ip]
                # If new priority is higher, replace
                if priority > current['priority']:
                     peers_by_ip[ip] = {
                        'ip': ip, 'port': port, 'status': status, 
                        'can_delete': can_delete, 
                        'priority': priority,
                        'height': self.network_manager.peer_stats.get((ip, port), {}).get('height', 0),
                        'user_agent': self.network_manager.peer_stats.get((ip, port), {}).get('user_agent', '')
                    }
                # If same priority, maybe prefer standard ports if current isn't?
                # or just stick with first found.
                elif priority == current['priority']:
                     # Tie-breaker: Prefer 9333
                     if port == 9333 and current['port'] != 9333:
                          peers_by_ip[ip]['port'] = port
        
        # 1. Active Peers
        if self.network_manager and hasattr(self.network_manager, 'peers'):
              for (ip, port) in list(self.network_manager.peers):
                  priority = 2
                  if port in [9333, 9334, 9335]:
                      priority = 3
                  add_candidate(ip, port, 'ACTIVE', False, priority)
        
        # 2. ICE Connections
        if hasattr(self.network_manager, 'ice_connections'):
             for (ip, port) in self.network_manager.ice_connections:
                 if (ip, port) not in self.network_manager.peers:
                     add_candidate(ip, port, 'ACTIVE (ICE)', False, 1)

        # 3. Failed Peers
        if hasattr(self.network_manager, 'failed_peers'):
             for (ip, port), data in self.network_manager.failed_peers.items():
                 add_candidate(ip, port, f"FAILED: {data.get('error','')}", True, 0)
        
        # Convert to list
        peers_list = list(peers_by_ip.values())
        
        # Remove internal priority field before sending
        for p in peers_list:
             del p['priority']
        
        # Add basic stats
        best = self.network_manager.chain_manager.block_index.get_best_block()
        height = best['height'] if best else 0
        
        return web.json_response({'peers': peers_list, 'height': height})
        
    async def handle_delete_peer(self, request):
        data = await self._get_json(request)
        self.network_manager.remove_failed_peer(data.get('ip'), data.get('port'))
        return web.json_response({'status': 'deleted'})

    async def handle_integrity_check(self, request):
        try:
            # 1. Run Disk Integrity Check
            result = self.network_manager.chain_manager.check_integrity()
            
            # 2. Run Network Sync Check
            # Get max peer height
            max_peer_height = 0
            peer_count = 0
            
            # self.network_manager.peer_stats is a dict of {addr: {'height': ...}}
            # But keys in peer_stats might be tuple or string depending on implementation.
            # Let's inspect manager.py: peer_stats keys are addr (tuples) usually.
            # However, looking at handle_get_peers, it iterates self.network_manager.peers (list of tuples)
            # peer_stats is auxiliary.
            # Let's use `peers` list and check `peer_stats` for each.
            
            for peer_addr in self.network_manager.peers:
                # peer_addr is (host, port) tuple
                stats = self.network_manager.peer_stats.get(peer_addr, {})
                h = stats.get('height', 0)
                if h > max_peer_height:
                    max_peer_height = h
                peer_count += 1
            
            local_height = self.network_manager.chain_manager.get_best_height()
            
            is_synced = local_height >= max_peer_height
            
            # 3. Combine Results
            result['network'] = {
                'synced': is_synced,
                'local_height': local_height,
                'peer_height': max_peer_height,
                'peer_count': peer_count
            }
            
            return web.json_response(result)
        except Exception as e:
            return web.json_response({'status': 'error', 'message': str(e)}, status=500)

    async def handle_reset(self, request):
        self.network_manager.reset_data()
        return web.json_response({'status': 'ok'})
        
    async def handle_get_logs(self, request):
        ip = request.query.get('ip')
        # port = int(request.query.get('port')) # We ignore specific port now and merge all for this IP
        
        merged_logs = []
        for (peer_ip, peer_port), logs in self.network_manager.peer_logs.items():
            if peer_ip == ip:
                merged_logs.extend(logs)
                
        # Sort logs by timestamp string [HH:MM:SS]
        # This is a simple string sort, which works given 24h format, 
        # but might mix days if logs span midnight. 
        # Given the 50-entry ring buffer and short lifespans, this is acceptable.
        merged_logs.sort()
        
        return web.json_response({'logs': merged_logs})

    async def handle_send_test(self, request):
        data = await self._get_json(request)
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
        
        # Calculate Hashrate
        network_hashrate = self.network_manager.chain_manager.get_network_hashrate()
        
        return web.json_response({
            'height': height,
            'difficulty': bits,
            'reward': reward,
            'halving_countdown': halving_countdown,
            'difficulty_countdown': DIFFICULTY_ADJUSTMENT_INTERVAL - (height % DIFFICULTY_ADJUSTMENT_INTERVAL),
            'test_msg_received': self.network_manager.test_msg_count,
            'network_hashrate': network_hashrate
        })

    async def handle_test_stun(self, request):
        # Accept IP from frontend, fall back to manager's STUN config
        try:
            data = await self._get_json(request)
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
        data = await self._get_json(request)
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
        data = await self._get_json(request)
        addr = data.get('address')
        wallet = self.network_manager.wallet
        wallet.keys = [k for k in wallet.keys if k['addr'] != addr]
        wallet.save()
        return web.json_response({'status': 'deleted'})

    async def handle_wallet_rename(self, request):
        data = await self._get_json(request)
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
        data = await self._get_json(request)
        to_addr = data.get('to')
        amount = float(data.get('amount'))
        
        try:
            # Convert to satoshi
            satoshi = int(amount * 100000000)
            
            # Get current height for maturity check
            best = self.network_manager.chain_manager.block_index.get_best_block()
            current_height = best['height'] if best else 0

            tx = self.network_manager.wallet.create_transaction(
                to_addr, satoshi, self.network_manager.chain_manager.chain_state, current_height,
                mempool=self.network_manager.mempool
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
            data = await self._get_json(request)
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
        data = await self._get_json(request)
        target = data.get('target_address') # Not used yet but passed
        success, msg = self.miner_controller.start_mining(target)
        return web.json_response({'success': success, 'message': msg})

    async def handle_miner_stop(self, request):
        success, msg = self.miner_controller.stop_mining()
        return web.json_response({'success': success, 'message': msg})

    # --- BEGGAR HANDLERS ---

    async def handle_beggar_start(self, request):
        data = await self._get_json(request)
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
            data = await self._get_json(request)
            
            # Check if this is a "Read" request disguised as a POST (only auth params)
            # Keys other than username/password imply an update
            update_keys = [k for k in data.keys() if k not in ['username', 'password']]
            
            if not update_keys:
                # Treat as GET
                 async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            return web.json_response(await resp.json())
                        else:
                            return web.json_response({'error': f'RPC Server returned {resp.status}'}, status=502)

            # Otherwise, proceed with update
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
        return web.Response(
            body=buffer.getvalue(),
            headers={
                'Content-Disposition': 'attachment; filename="icsi_miner.zip"',
                'Content-Type': 'application/zip'
            }
        )
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
