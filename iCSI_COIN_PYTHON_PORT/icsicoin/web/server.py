import logging
import asyncio
from aiohttp import web
import os

logger = logging.getLogger("WebServer")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iCSI Coin Node Config</title>
    <style>
        :root {{
            --bg-color: #0d0d0d;
            --term-green: #00ff41;
            --term-cyan: #0ff;
            --alert-red: #ff0055;
            --panel-bg: #1a1a1a;
            --input-bg: #000;
        }}
        
        body {{
            background-color: var(--bg-color);
            color: var(--term-green);
            font-family: 'Courier New', Courier, monospace;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            overflow-x: hidden;
            padding: 2rem;
            box-sizing: border-box;
        }}

        .container {{
            background-color: var(--panel-bg);
            padding: 2rem;
            border: 1px solid var(--term-green);
            box-shadow: 0 0 15px rgba(0, 255, 65, 0.2);
            width: 500px;
            position: relative;
            margin-bottom: 2rem;
        }}

        .container::before {{
            content: "SYSTEM_CONFIG // NODE_UPLINK";
            position: absolute;
            top: -10px;
            left: 20px;
            background-color: var(--bg-color);
            padding: 0 10px;
            color: var(--term-cyan);
            font-weight: bold;
            font-size: 0.9em;
        }}

        h1 {{
            text-align: center;
            color: var(--term-cyan);
            text-shadow: 0 0 5px var(--term-cyan);
            margin-bottom: 2rem;
            font-size: 1.5rem;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}

        .input-group {{
            margin-bottom: 1.5rem;
        }}

        label {{
            display: block;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
            color: var(--term-green);
        }}

        input[type="text"] {{
            width: 100%;
            background-color: var(--input-bg);
            border: 1px solid var(--term-green);
            color: var(--term-green);
            padding: 10px;
            font-family: inherit;
            box-sizing: border-box;
            outline: none;
            transition: box-shadow 0.3s ease;
        }}

        input[type="text"]:focus {{
            box-shadow: 0 0 10px rgba(0, 255, 65, 0.5);
            border-color: var(--term-cyan);
        }}

        button.primary-btn {{
            width: 100%;
            padding: 12px;
            background-color: transparent;
            border: 1px solid var(--term-cyan);
            color: var(--term-cyan);
            font-family: inherit;
            font-weight: bold;
            cursor: pointer;
            text-transform: uppercase;
            transition: all 0.3s ease;
            margin-top: 1rem;
        }}

        button.primary-btn:hover {{
            background-color: var(--term-cyan);
            color: var(--bg-color);
            box-shadow: 0 0 15px var(--term-cyan);
        }}

        button.danger-btn {{
            width: 100%;
            padding: 10px;
            background-color: transparent;
            border: 1px solid var(--alert-red);
            color: var(--alert-red);
            font-family: inherit;
            font-weight: bold;
            cursor: pointer;
            text-transform: uppercase;
            transition: all 0.3s ease;
            margin-top: 2rem;
        }}

        button.danger-btn:hover {{
            background-color: var(--alert-red);
            color: white;
            box-shadow: 0 0 15px var(--alert-red);
        }}

        .delete-btn {{
            background: none;
            border: none;
            color: var(--alert-red);
            cursor: pointer;
            font-weight: bold;
            padding: 0 5px;
        }}
        
        .delete-btn:hover {{
            color: white;
            text-shadow: 0 0 5px var(--alert-red);
        }}

        .status {{
            margin-top: 1rem;
            text-align: center;
            font-size: 0.8rem;
            min-height: 1.2em;
        }}
        
        .nodes-container {{
            width: 700px;
            background-color: var(--panel-bg);
            border: 1px solid var(--term-green);
            padding: 1rem;
            display: none; /* Hidden by default until toggled or loaded */
        }}

        .nodes-container.visible {{
            display: block;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}

        th, td {{
            text-align: left;
            padding: 8px;
            border-bottom: 1px solid #333;
        }}

        th {{
            color: var(--term-cyan);
            text-transform: uppercase;
        }}
        
        tr:last-child td {{
            border-bottom: none;
        }}

        .scanlines {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: linear-gradient(
                to bottom,
                rgba(255,255,255,0),
                rgba(255,255,255,0) 50%,
                rgba(0,0,0,0.1) 50%,
                rgba(0,0,0,0.1)
            );
            background-size: 100% 4px;
            pointer-events: none;
            z-index: 10;
        }}
        
        .nav-link {{
            color: var(--term-cyan);
            text-decoration: none;
            cursor: pointer;
            border-bottom: 1px dashed var(--term-cyan);
            margin-bottom: 1rem;
            display: inline-block;
        }}
        .modal {{
            display: none; 
            position: fixed; 
            z-index: 100; 
            left: 0;
            top: 0;
            width: 100%; 
            height: 100%; 
            overflow: auto; 
            background-color: rgba(0,0,0,0.8); 
        }}

        .modal-content {{
            background-color: var(--panel-bg);
            margin: 10% auto; 
            padding: 20px;
            border: 1px solid var(--term-green);
            width: 80%;
            box-shadow: 0 0 20px rgba(0, 255, 65, 0.3);
            font-family: 'Courier New', Courier, monospace;
            color: var(--term-green);
            max-height: 70vh;
            display: flex;
            flex-direction: column;
        }}

        .modal-header {{
            display: flex;
            justify-content: space-between;
            border-bottom: 1px solid var(--term-green);
            padding-bottom: 10px;
            margin-bottom: 10px;
        }}

        .modal-body {{
            flex-grow: 1;
            overflow-y: auto;
            background-color: black;
            padding: 10px;
            border: 1px solid #333;
            white-space: pre-wrap;
            font-size: 0.8rem;
        }}

        .close {{
            color: var(--alert-red);
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }}

        .close:hover,
        .close:focus {{
            color: white;
            text-decoration: none;
            cursor: pointer;
        }}
        
        .log-btn {{
            background: none;
            border: 1px solid var(--term-cyan);
            color: var(--term-cyan);
            cursor: pointer;
            font-size: 0.8rem;
            padding: 2px 5px;
            margin-right: 5px;
        }}
        
        .log-btn:hover {{
            background-color: var(--term-cyan);
            color: black;
        }}
    </style>
</head>
<body>
    <div class="scanlines"></div>
    
    <div class="container">
        <h1>iCSI Coin Node</h1>
        
        <div class="status">
            {status_message}
        </div>

        <form action="/connect" method="post">
            <div class="input-group">
                <label>SEED NODE 1</label>
                <input type="text" name="seed_nodes" placeholder="192.168.X.X:9333" value="{seed1}">
            </div>
            <div class="input-group">
                <label>SEED NODE 2</label>
                <input type="text" name="seed_nodes" placeholder="192.168.X.X:9333" value="{seed2}">
            </div>
            <div class="input-group">
                <label>SEED NODE 3</label>
                <input type="text" name="seed_nodes" placeholder="192.168.X.X:9333" value="{seed3}">
            </div>
            <button type="submit" class="primary-btn">INITIALIZE UPLINK</button>
        </form>
        
        <div style="text-align: center; margin-top: 1.5rem;">
            <a onclick="toggleNodes()" class="nav-link">[ DISCOVERED NODES ]</a>
        </div>
        
        <button class="danger-btn" onclick="resetData()">[ RESET ALL SYSTEM LOGS ]</button>
    </div>

    <div id="nodeListPanel" class="nodes-container">
        <h3 style="color: var(--term-green); margin-top: 0;">network_topology</h3>
        <table>
            <thead>
                <tr>
                    <th>IP ADDRESS</th>
                    <th>PORT</th>
                    <th>STATUS</th>
                    <th>ACTION</th>
                </tr>
            </thead>
            <tbody id="nodeTableBody">
                <!-- Populated by JS -->
            </tbody>
        </table>
    </div>

    <!-- Log Viewer Modal -->
    <div id="logModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <span id="modalTitle">CONNECTION LOGS</span>
                <span class="close" onclick="closeModal()">&times;</span>
            </div>
            <div id="modalBody" class="modal-body">
                Loading...
            </div>
        </div>
    </div>

    <script>
        let pollingInterval = null;

        function toggleNodes() {{
            const panel = document.getElementById('nodeListPanel');
            panel.classList.toggle('visible');
            
            if(panel.classList.contains('visible')) {{
                fetchNodes();
                if (!pollingInterval) {{
                    pollingInterval = setInterval(fetchNodes, 2000);
                }}
            }} else {{
                if (pollingInterval) {{
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                }}
            }}
        }}

        async function fetchNodes() {{
            try {{
                const response = await fetch('/api/peers');
                const peers = await response.json();
                const tbody = document.getElementById('nodeTableBody');
                tbody.innerHTML = '';
                
                peers.forEach(peer => {{
                    const row = document.createElement('tr');
                    
                    let statusColor = 'var(--term-green)';
                    if(peer.status.includes('FAILED') || peer.status.includes('Disconnected')) {{
                        statusColor = 'var(--alert-red)';
                    }}
                    
                    let actionHtml = `<button class="log-btn" onclick="showLogs('${{peer.ip}}', ${{peer.port}})">LOGS</button>`;
                    
                    if(peer.can_delete) {{
                         actionHtml += `<button class="delete-btn" onclick="deletePeer('${{peer.ip}}', ${{peer.port}})">[ X ]</button>`;
                    }}

                    row.innerHTML = `
                        <td>${{peer.ip}}</td>
                        <td>${{peer.port}}</td>
                        <td style="color: ${{statusColor}};">[ ${{peer.status}} ]</td>
                        <td>${{actionHtml}}</td>
                    `;
                    tbody.appendChild(row);
                }});
                
                if (peers.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: #555;">NO DATA LOGGED</td></tr>';
                }}
            }} catch (e) {{
                console.error("Failed to fetch nodes", e);
            }}
        }}

        async function showLogs(ip, port) {{
            const modal = document.getElementById('logModal');
            const modalBody = document.getElementById('modalBody');
            const modalTitle = document.getElementById('modalTitle');
            
            modal.style.display = "block";
            modalTitle.innerText = `LOGS: ${{ip}}:${{port}}`;
            modalBody.innerText = "Loading logs...";
            
            try {{
                const response = await fetch(`/api/logs?ip=${{ip}}&port=${{port}}`);
                const data = await response.json();
                
                if (data.logs && data.logs.length > 0) {{
                    modalBody.innerText = data.logs.join('\\n');
                }} else {{
                    modalBody.innerText = "No logs recorded for this peer.";
                }}
            }} catch(e) {{
                modalBody.innerText = "Error fetching logs.";
                console.error(e);
            }}
        }}

        function closeModal() {{
            document.getElementById('logModal').style.display = "none";
        }}
        
        // Close modal if clicked outside
        window.onclick = function(event) {{
            const modal = document.getElementById('logModal');
            if (event.target == modal) {{
                modal.style.display = "none";
            }}
        }}
        
        async function deletePeer(ip, port) {{
             try {{
                const response = await fetch('/api/peers/delete', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ ip: ip, port: port }})
                }});
                fetchNodes(); // Refresh immediately
             }} catch(e) {{
                 console.error("Delete failed", e);
             }}
        }}
        
        async function resetData() {{
             if(!confirm("WARNING: This will clear all connection logs and reset the network manager tracking. Continue?")) return;
             
             try {{
                const response = await fetch('/api/reset', {{ method: 'POST' }});
                fetchNodes(); // Refresh
                alert("System logs purged.");
             }} catch(e) {{
                 console.error("Reset failed", e);
             }}
        }}
    </script>
</body>
</html>
"""

class WebServer:
    def __init__(self, port, network_manager):
        self.port = port
        self.network_manager = network_manager
        self.app = web.Application()
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_post('/connect', self.handle_connect)
        self.app.router.add_get('/api/peers', self.handle_peers)
        self.app.router.add_post('/api/peers/delete', self.handle_delete_peer)
        self.app.router.add_post('/api/reset', self.handle_reset)
        self.app.router.add_get('/api/logs', self.handle_get_logs)
        self.runner = None
        self.site = None

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        logger.info(f"Web server started on port {self.port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    async def handle_index(self, request):
        return web.Response(text=HTML_TEMPLATE.format(status_message="AWAITING INPUT...", seed1="", seed2="", seed3=""), content_type='text/html')
    
    async def handle_peers(self, request):
        peers_list = []
        # network_manager.peers is a set of (ip, port) tuples
        if self.network_manager and hasattr(self.network_manager, 'peers'):
              # Active peers
              for (ip, port) in list(self.network_manager.peers):
                  # Filter localhost to avoid UI clutter
                  if ip.startswith("127."):
                      continue
                  peers_list.append({'ip': ip, 'port': port, 'status': 'ACTIVE', 'can_delete': False})
              
              # Failed peers
              if hasattr(self.network_manager, 'failed_peers'):
                   for (ip, port), data in self.network_manager.failed_peers.items():
                       peers_list.append({
                           'ip': ip, 
                           'port': port, 
                           'status': f"FAILED: {data['error']}",
                           'can_delete': True
                       })
        
        return web.json_response(peers_list)

    async def handle_get_logs(self, request):
        ip = request.query.get('ip')
        port = request.query.get('port')
        
        if not ip or not port:
            return web.json_response({'error': 'Missing ip or port'}, status=400)
            
        try:
            port = int(port)
            key = (ip, port)
            logs = []
            
            if hasattr(self.network_manager, 'peer_logs') and key in self.network_manager.peer_logs:
                logs = self.network_manager.peer_logs[key]
                
            return web.json_response({'logs': logs})
        except ValueError:
             return web.json_response({'error': 'Invalid port'}, status=400)
    
    async def handle_delete_peer(self, request):
        try:
            data = await request.json()
            ip = data.get('ip')
            port = data.get('port')
            if ip and port:
                self.network_manager.remove_failed_peer(ip, port)
                return web.json_response({'status': 'deleted'})
            return web.json_response({'error': 'Invalid parameters'}, status=400)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def handle_reset(self, request):
        if self.network_manager:
            self.network_manager.reset_data()
            return web.json_response({'status': 'reset_complete'})
        return web.json_response({'error': 'Network manager not available'}, status=500)

    async def handle_connect(self, request):
        data = await request.post()
        seed_nodes = data.getall('seed_nodes')
        
        connected_count = 0
        for node in seed_nodes:
            node = node.strip()
            if node:
                if ":" not in node:
                     node = f"{node}:9333" 
                
                logger.info(f"Web User requested connection to: {node}")
                t = asyncio.create_task(self.network_manager.connect_to_peer(node))
                if hasattr(self.network_manager, 'tasks'):
                    self.network_manager.tasks.add(t)
                    t.add_done_callback(self.network_manager.tasks.discard)
                connected_count += 1
        
        # Ensure we have 3 for the template, pad with empty if needed
        seeds_for_template = [s.strip() for s in seed_nodes]
        while len(seeds_for_template) < 3:
            seeds_for_template.append("")

        return web.Response(text=HTML_TEMPLATE.format(
            status_message=f"Initiated connection to {connected_count} nodes.",
            seed1=seeds_for_template[0],
            seed2=seeds_for_template[1],
            seed3=seeds_for_template[2]
        ), content_type='text/html')
