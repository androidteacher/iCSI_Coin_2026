import asyncio
import logging
from aiohttp import web
import json

logger = logging.getLogger("RPCServer")

class RPCServer:
    def __init__(self, port, user, password, allow_ip, network_manager):
        self.port = port
        self.user = user
        self.password = password
        self.allow_ip = allow_ip
        self.network_manager = network_manager
        self.app = web.Application()
        self.app.router.add_post('/', self.handle_request)
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
        # Basic Auth Check (if configured)
        # For MVP we might skip strict auth or implement basic header check later
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
            result = 0 # Placeholder
        else:
            error = {"code": -32601, "message": "Method not found"}

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
