/* Main.js - iCSI Coin Node UI */

const API = {
    connect: '/api/connect',
    peers: '/api/peers',
    logs: '/api/logs',
    testNat: '/api/stun/test',
    stunSet: '/api/stun/set',
    reset: '/api/reset',
    stats: '/api/stats',
    discovery: '/api/discovery/status',
    walletList: '/api/wallet/list',
    walletCreate: '/api/wallet/create',
    walletDelete: '/api/wallet/delete',
    walletSend: '/api/wallet/send',
    walletImport: '/api/wallet/import',
    walletRename: '/api/wallet/rename',
    minerStatus: '/api/miner/status',
    minerStart: '/api/miner/start',
    minerStop: '/api/miner/stop',
    beggarStart: '/api/beggar/start',
    beggarStop: '/api/beggar/stop',
    beggarList: '/api/beggar/list'
};

let pollInterval = null;
let minerInterval = null;
let statsInterval = null;
let selectedWallet = null;

document.addEventListener('DOMContentLoaded', () => {
    init();
});

function init() {
    startPolling();
    loadWallets();
}

function startPolling() {
    updatePeers();
    pollInterval = setInterval(updatePeers, 2000);

    updateMiner();
    minerInterval = setInterval(updateMiner, 1000);

    updateStats();
    statsInterval = setInterval(updateStats, 2000);

    loadWallets(); // Initial load
    walletInterval = setInterval(loadWallets, 5000); // Poll every 5s

    checkDiscovery(); // Initial check
    setInterval(checkDiscovery, 5000); // Poll every 5s

    checkBeggarStatus(); // Initial beggar check
    setInterval(checkBeggarStatus, 5000); // Poll beggar every 5s
}

/* --- NETWORK --- */

async function updateStats() {
    try {
        const res = await fetch(API.stats);
        const data = await res.json();

        document.getElementById('netDiff').innerText = data.difficulty;
        document.getElementById('netDiffCountdown').innerText = data.difficulty_countdown + " Blocks";
        document.getElementById('netReward').innerText = data.reward.toFixed(8) + " ICSI";
        document.getElementById('netHalving').innerText = data.halving_countdown + " Blocks";

        if (data.network_hashrate !== undefined) {
            const h = parseFloat(data.network_hashrate);
            let hStr = "0 H/s";

            if (!isNaN(h)) {
                if (h > 1000000000) hStr = (h / 1000000000).toFixed(2) + " GH/s";
                else if (h > 1000000) hStr = (h / 1000000).toFixed(2) + " MH/s";
                else if (h > 1000) hStr = (h / 1000).toFixed(2) + " KH/s";
                else hStr = h.toFixed(2) + " H/s";
            }

            const el = document.getElementById('netHashrate');
            if (el) el.innerText = hStr;
        }
    } catch (e) {
        console.error("Stats Update Failed", e);
    }
}

async function connectToNetwork() {
    const ipInput = document.getElementById('seedIp').value.trim();
    const portInput = document.getElementById('seedPort').value.trim() || '9341';

    if (!ipInput) return alert("Enter Seed IP");

    // Construct final address
    const finalAddress = `${ipInput}:${portInput}`;

    const btn = document.getElementById('connectBtn');
    const originalText = btn.innerText;
    btn.innerText = "CONNECTING...";
    btn.disabled = true;

    try {
        const res = await fetch(API.connect, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seed_ip: finalAddress })
        });
        const data = await res.json();

        if (res.ok) {
            btn.innerText = `INITIATED (${data.connected_count})`;
            setTimeout(() => {
                btn.innerText = originalText;
                btn.disabled = false;
            }, 3000);
        } else {
            alert("Connection Failed: " + (data.error || res.statusText));
            btn.innerText = "FAILED";
            setTimeout(() => {
                btn.innerText = originalText;
                btn.disabled = false;
            }, 3000);
        }
    } catch (e) {
        alert("Connection Error: " + e);
        btn.innerText = "ERROR";
        setTimeout(() => {
            btn.innerText = originalText;
            btn.disabled = false;
        }, 3000);
    }
}

async function checkDiscovery() {
    try {
        const res = await fetch(API.discovery);
        const data = await res.json();
        const dot = document.getElementById('discoveryDot');
        const text = document.getElementById('discoveryText');
        const seedInput = document.getElementById('seedIp');

        if (data.discovered_seed) {
            dot.className = 'inline-block w-2 h-2 rounded-full bg-primary';
            text.className = 'text-primary';
            text.innerText = `Seed found: ${data.discovered_seed}`;
            // Auto-fill seed IP if empty or still showing own IP
            if (!seedInput.value || seedInput.value === data.own_ip) {
                seedInput.value = data.discovered_seed;
            }
        } else if (data.known_multicast_peers && data.known_multicast_peers.length > 0) {
            dot.className = 'inline-block w-2 h-2 rounded-full bg-yellow-400';
            text.className = 'text-yellow-400';
            text.innerText = `${data.known_multicast_peers.length} peer(s) found`;
        } else if (data.beacon_active) {
            dot.className = 'inline-block w-2 h-2 rounded-full bg-zinc-500 animate-pulse';
            text.className = 'text-zinc-500';
            text.innerText = 'Scanning for peers...';
        }
    } catch (e) {
        // Silently ignore discovery errors
    }
}

async function testNat() {
    const resDiv = document.getElementById('natResult');
    resDiv.innerText = "Testing...";

    try {
        // Send the current seed IP from the input field for NAT testing
        const seedIp = document.getElementById('seedIp').value;
        const res = await fetch(API.testNat, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stun_ip: seedIp })
        });
        const data = await res.json();

        if (data.success) {
            resDiv.innerText = "SUCCESS: " + data.message;
            resDiv.className = "mt-2 text-xs font-mono text-primary break-all";
        } else {
            resDiv.innerText = "FAILED: " + (data.message || "Timeout");
            resDiv.className = "mt-2 text-xs font-mono text-pink-500 break-all";
        }
    } catch (e) {
        resDiv.innerText = "Error: " + e;
    }
}

async function setStunServer() {
    const ip = document.getElementById('stunIp').value;
    const port = document.getElementById('stunPort').value;
    const statusDiv = document.getElementById('stunStatus');

    statusDiv.innerText = "Saving...";
    statusDiv.className = "mt-2 text-[10px] font-mono text-center text-zinc-500";

    try {
        const res = await fetch(API.stunSet, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stun_ip: ip, stun_port: port })
        });
        const data = await res.json();

        if (res.ok) {
            statusDiv.innerText = "STUN Server Updated!";
            statusDiv.className = "mt-2 text-[10px] font-mono text-center text-primary";
            setTimeout(() => statusDiv.innerText = "", 3000);
        } else {
            statusDiv.innerText = "Error: " + data.error;
            statusDiv.className = "mt-2 text-[10px] font-mono text-center text-pink-500";
        }
    } catch (e) {
        statusDiv.innerText = "Error: " + e;
        statusDiv.className = "mt-2 text-[10px] font-mono text-center text-pink-500";
    }
}

async function updatePeers() {
    try {
        const res = await fetch(API.peers);
        const data = await res.json();

        // Update Stats
        document.getElementById('peerCount').innerText = data.peers.length;
        document.getElementById('blockHeight').innerText = data.height;

        // Update Table
        const tbody = document.getElementById('peerTableBody');
        tbody.innerHTML = '';

        // Simple search filter
        const filter = document.getElementById('peerSearch').value.toLowerCase();

        // Update Uplink Indicator based on TRUTH
        const statusEl = document.getElementById('uplinkStatus');
        const activePeers = data.peers.filter(p => p.status.toUpperCase().includes('ACTIVE'));

        if (activePeers.length > 0) {
            statusEl.innerText = "ONLINE";
            statusEl.className = "w-full py-3 rounded-lg text-center font-bold tracking-widest text-sm mb-6 bg-primary/20 border border-primary/50 text-primary shadow-[0_0_15px_rgba(var(--color-primary),0.2)]";
        } else {
            statusEl.innerText = "OFFLINE";
            statusEl.className = "w-full py-3 rounded-lg text-center font-bold tracking-widest text-sm mb-6 bg-black border border-zinc-900 text-zinc-500 border-zinc-900";
        }

        data.peers.forEach(p => {

            // Show ACTIVE, ACTIVE (ICE), and DISCOVERED
            // Show ALL peers (Active, Discovered, and Failed) for debugging
            // if (!p.status.toUpperCase().includes('ACTIVE') && !p.status.toUpperCase().includes('DISCOVERED')) return;

            const key = `${p.ip}:${p.port}`;
            if (filter && !key.toLowerCase().includes(filter)) return;

            const tr = document.createElement('tr');
            tr.className = "hover:bg-zinc-900/50 transition-colors";

            // Status Indicator Logic
            // Default: Empty Circle (Border only)
            const dotId = `dot-${p.ip.replace(/\./g, '-')}-${p.port}`;
            let statusDot = `<span id="${dotId}" class="inline-block w-3 h-3 rounded-full border-2 border-zinc-600 mr-2 transition-colors"></span>`;

            // ACTION BUTTON LOGIC
            // Standard action is LOG + TEST (Force Reconnect)
            let logBtn = `<button class="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-primary text-[10px] font-bold uppercase rounded-md transition-colors mr-2" onclick="showLogs('${p.ip}', ${p.port})">LOG</button>`;

            // For ACTIVE peers, "TEST" means Force Reconnect
            // let testBtn = `<button class="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white text-[10px] font-bold uppercase rounded-md transition-colors border border-zinc-700" onclick="connectToPeer('${p.ip}', ${p.port}, this, true)">TEST</button>`;
            let actionBtn = logBtn;

            // Status coloring removed for manual test feedback only
            /*
            if (p.status === 'DISCOVERED') {
                statusDot = `<span class="inline-block w-2 h-2 rounded-full bg-yellow-500 mr-2 animate-pulse"></span>`;
            } else if (p.status.startsWith('FAILED')) {
                statusDot = `<span class="inline-block w-2 h-2 rounded-full bg-red-500 mr-2"></span>`;
            }
            */

            tr.innerHTML = `
                <td class="py-3 pl-2 text-zinc-300 font-mono flex items-center">
                    ${statusDot}
                    ${p.ip}
                </td>
                <td class="py-3 text-zinc-500 font-mono">${p.port}</td>
                    ${actionBtn}
                </td>

            `;
            tbody.appendChild(tr);
        });
    } catch (e) { console.error("Peer Update Failed", e); }
}

async function connectToPeer(ip, port, btn, force = false) {
    const originalText = btn.innerText;
    const dotId = `dot-${ip.replace(/\./g, '-')}-${port}`;
    const dot = document.getElementById(dotId);

    // Feedback on button (loading state)
    btn.innerText = "...";
    btn.disabled = true;

    try {
        // Send force=true AND wait=true explicitly
        const res = await fetch(API.connect, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                seed_ip: `${ip}:${port}`,
                force: force,
                wait: true
            })
        });
        const data = await res.json();

        // Check the 'results' array for success status of this specific target
        let success = false;
        if (data.results) {
            // Find result for this target (handling potential "ip:port" vs [ip, port] formats if any)
            const myResult = data.results.find(r => r.target.includes(ip) && r.target.includes(String(port)));
            if (myResult && myResult.success) success = true;
        } else if (data.connected_count > 0) {
            // Fallback for older API or single target implicit success
            success = true;
        }

        if (res.ok && success) {
            btn.innerText = "OK";
            // Button stays standard style, only text changes briefly

            // DOT TURNS GREEN
            if (dot) dot.className = "inline-block w-3 h-3 rounded-full border-2 border-green-500 bg-green-500 mr-2 transition-colors shadow-[0_0_10px_rgba(34,197,94,0.6)]";

            setTimeout(() => {
                btn.innerText = originalText;
                btn.disabled = false;
                // Revert dot to empty
                if (dot) dot.className = "inline-block w-3 h-3 rounded-full border-2 border-zinc-600 mr-2 transition-colors";
            }, 3000);

        } else {
            // Failure
            btn.innerText = "FAIL";
            // DOT TURNS RED
            if (dot) dot.className = "inline-block w-3 h-3 rounded-full border-2 border-red-500 bg-red-500 mr-2 transition-colors shadow-[0_0_10px_rgba(239,68,68,0.6)]";

            setTimeout(() => {
                btn.innerText = originalText;
                btn.disabled = false;
                // Revert dot to empty
                if (dot) dot.className = "inline-block w-3 h-3 rounded-full border-2 border-zinc-600 mr-2 transition-colors";
            }, 3000);
        }
    } catch (e) {
        alert("Connection Error: " + e);
        btn.innerText = "ERR";
        if (dot) dot.className = "inline-block w-3 h-3 rounded-full border-2 border-red-500 bg-red-500 mr-2 transition-colors";
        setTimeout(() => {
            btn.innerText = originalText;
            btn.disabled = false;
            if (dot) dot.className = "inline-block w-3 h-3 rounded-full border-2 border-zinc-600 mr-2 transition-colors";
        }, 3000);
    }
}


async function showLogs(ip, port) {
    const modal = document.getElementById('logModal');
    const content = document.getElementById('logContent');
    const title = document.getElementById('logModalTitle');
    const blockCountEl = document.getElementById('logBlockCount');

    modal.style.display = "flex";
    title.innerText = `LOGS: ${ip}:${port}`;
    content.innerText = "Loading...";
    if (blockCountEl) blockCountEl.innerText = "...";

    try {
        const res = await fetch(`${API.logs}?ip=${ip}&port=${port}`);
        const data = await res.json();
        const logs = data.logs || [];
        content.innerText = logs.join('\n') || "No logs.";

        // Count block-related log entries
        const blockCount = logs.filter(l => /\bblock\b/i.test(l)).length;
        if (blockCountEl) blockCountEl.innerText = blockCount;
    } catch (e) {
        content.innerText = "Error";
        if (blockCountEl) blockCountEl.innerText = "—";
    }
}

/* --- WALLET --- */

async function loadWallets() {
    try {
        const res = await fetch(API.walletList);
        const data = await res.json();
        const select = document.getElementById('walletSelect');

        // Smart Update: Check if we need to full rebuild
        const currentOptions = Array.from(select.options);
        const needsRebuild = currentOptions.length !== data.wallets.length ||
            !data.wallets.every((w, i) => currentOptions[i] && currentOptions[i].value === w.address);

        if (needsRebuild) {
            // Save current selection
            const currentVal = select.value;
            select.innerHTML = '';

            data.wallets.forEach(w => {
                const opt = document.createElement('option');
                opt.value = w.address;
                opt.innerText = `[${w.available.toFixed(2)}] ${w.name}`;
                opt.dataset.available = w.available;
                opt.dataset.confirmed = w.confirmed;
                opt.dataset.pending = w.pending;
                opt.dataset.name = w.name;
                select.appendChild(opt);
            });

            if (currentVal && Array.from(select.options).some(o => o.value === currentVal)) {
                select.value = currentVal;
            } else if (data.wallets.length > 0) {
                select.value = data.wallets[0].address;
            }
        } else {
            // Just update balances in place
            data.wallets.forEach((w, i) => {
                const opt = select.options[i];
                if (opt) {
                    opt.innerText = `[${w.available.toFixed(2)}] ${w.name}`;
                    opt.dataset.available = w.available;
                    opt.dataset.confirmed = w.confirmed;
                    opt.dataset.pending = w.pending;
                }
            });
        }

        updateWalletDisplay();
    } catch (e) { console.error(e); }
}

function updateWalletDisplay() {
    const select = document.getElementById('walletSelect');
    const displayBal = document.getElementById('currentBalance');
    const displayAddr = document.getElementById('currentAddress');

    const opt = select.selectedOptions[0];
    if (opt) {
        displayBal.innerText = parseFloat(opt.dataset.available).toFixed(2);
        displayAddr.value = opt.value; // Use .value for input
        selectedWallet = opt.value;

        // Add Subtext for Confirmed/Pending
        // We need to inject this HTML or update an existing element
        // Since we didn't add a specific element in HTML yet, let's append it purely via JS or modify existing structure
        // Actually, we should check if we can add a sub-div
        let detailsEl = document.getElementById('balanceDetails');
        if (!detailsEl) {
            detailsEl = document.createElement('div');
            detailsEl.id = 'balanceDetails';
            detailsEl.className = "mt-2 text-[10px] font-mono text-zinc-500 flex justify-center gap-4";
            displayBal.parentNode.appendChild(detailsEl);
        }

        const conf = parseFloat(opt.dataset.confirmed).toFixed(2);
        const pend = parseFloat(opt.dataset.pending).toFixed(2);
        const pendClass = parseFloat(pend) < 0 ? "text-pink-500" : (parseFloat(pend) > 0 ? "text-green-500" : "text-zinc-600");

        detailsEl.innerHTML = `
                <span>On-Chain: <span class="text-zinc-300">${conf}</span></span>
                <span>Pending: <span class="${pendClass}">${pend}</span></span>
            `;

    } else {
        displayBal.innerText = "0.00";
        displayAddr.value = "---"; // Use .value for input
        selectedWallet = null;

        let detailsEl = document.getElementById('balanceDetails');
        if (detailsEl) detailsEl.innerHTML = '';
    }
}

async function createWallet() {
    const name = document.getElementById('newWalletName').value;
    if (!name) return alert("Enter Name");

    try {
        await fetch(API.walletCreate, {
            method: 'POST',
            body: JSON.stringify({ name: name })
        });
        closeModal('createWalletModal');
        loadWallets();
    } catch (e) { alert(e); }
}

async function purgeWallet() {
    if (!selectedWallet) return;
    if (!confirm("Delete this wallet? THIS CANNOT BE UNDONE!")) return;

    await fetch(API.walletDelete, {
        method: 'POST',
        body: JSON.stringify({ address: selectedWallet })
    });
    loadWallets();
}

async function sendCoin() {
    if (!selectedWallet) return alert("Select Wallet");
    const to = document.getElementById('sendTo').value;
    const amount = document.getElementById('sendAmount').value;

    if (!to || !amount) return alert("Fill fields");

    const resDiv = document.getElementById('sendResult');
    resDiv.innerText = "Sending...";

    try {
        const res = await fetch(API.walletSend, {
            method: 'POST',
            body: JSON.stringify({
                from: selectedWallet, // Implicitly used by wallet wrapper finding keys, but good to know source
                to: to,
                amount: amount
            })
        });
        const data = await res.json();

        if (res.ok) {
            resDiv.innerText = `SENT! TxID: ${data.txid.substring(0, 16)}...`;
            resDiv.className = "mt-3 text-center text-xs font-mono text-primary";
            loadWallets(); // Refresh balance
        } else {
            resDiv.innerText = "FAILED: " + data.error;
            resDiv.className = "mt-3 text-center text-xs font-mono text-pink-500";
        }
    } catch (e) { resDiv.innerText = "Error: " + e; }
}

async function exportWallets() {
    const res = await fetch('/api/wallet/export');
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'icsi_wallets.json';
    a.click();
}

async function importWallets() {
    const jsonStr = document.getElementById('importData').value;
    try {
        const data = JSON.parse(jsonStr);
        await fetch(API.walletImport, {
            method: 'POST',
            body: JSON.stringify(data)
        });
        closeModal('importWalletModal');
        loadWallets();
        alert("Wallets Imported");
    } catch (e) { alert("Invalid JSON"); }
}

function handleImportFile(input) {
    const file = input.files[0];
    if (!file) return;

    const nameEl = document.getElementById('importFileName');
    nameEl.innerText = file.name;
    nameEl.classList.remove('hidden');

    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('importData').value = e.target.result;
    };
    reader.readAsText(file);
}

function openManageWallet() {
    const select = document.getElementById('walletSelect');
    const opt = select.selectedOptions[0];
    if (!opt || !opt.value) return alert('Select a wallet first');

    document.getElementById('manageWalletName').innerText = opt.dataset.name || 'Unnamed';
    document.getElementById('manageWalletBalance').innerText = parseFloat(opt.dataset.balance).toFixed(8) + ' ICSI';
    document.getElementById('manageWalletAddr').innerText = opt.value;

    // Reset to view mode
    document.getElementById('manageNameView').classList.remove('hidden');
    document.getElementById('manageNameEdit').classList.add('hidden');

    document.getElementById('manageWalletModal').style.display = 'flex';
}

function showRenameField() {
    const currentName = document.getElementById('manageWalletName').innerText;
    document.getElementById('renameInput').value = currentName;
    document.getElementById('manageNameView').classList.add('hidden');
    document.getElementById('manageNameEdit').classList.remove('hidden');
    document.getElementById('renameInput').focus();
}

function cancelRename() {
    document.getElementById('manageNameView').classList.remove('hidden');
    document.getElementById('manageNameEdit').classList.add('hidden');
}

async function saveWalletName() {
    const newName = document.getElementById('renameInput').value.trim();
    const addr = document.getElementById('manageWalletAddr').innerText;
    if (!newName) return alert('Enter a name');

    try {
        const res = await fetch(API.walletRename, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address: addr, name: newName })
        });
        const data = await res.json();
        if (res.ok) {
            document.getElementById('manageWalletName').innerText = newName;
            cancelRename();
            loadWallets(); // Refresh dropdown
        } else {
            alert('Error: ' + (data.error || 'Unknown'));
        }
    } catch (e) { alert('Error: ' + e); }
}

/* --- MINING --- */

async function startMining() {
    // miningTargetSelect removed. Use selectedWallet or let backend default.
    // If user has a wallet selected, use that.
    const target = selectedWallet;

    await fetch(API.minerStart, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_address: target })
    });
}

async function stopMining() {
    await fetch(API.minerStop, { method: 'POST' });
}

async function updateMiner() {
    const res = await fetch(API.minerStatus);
    const data = await res.json();

    // Update Buttons
    document.getElementById('startMineBtn').disabled = data.is_mining;
    document.getElementById('stopMineBtn').disabled = !data.is_mining;

    // Update Terminal
    const terminal = document.getElementById('miningTerminal');
    // We only append new logs or replace?
    // Let's replace content with last 10 logs for simplicity, or append diff.
    // Simpler: Just render last 20 logs joined
    terminal.innerHTML = data.logs.join('<div class="mb-1 border-l-2 border-zinc-700 pl-2"></div>');
    terminal.scrollTop = terminal.scrollHeight;
}

/* --- UTILS --- */

function openCreateWalletModal() { document.getElementById('createWalletModal').style.display = 'flex'; }
function openImportWalletModal() { document.getElementById('importWalletModal').style.display = 'flex'; }

function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'flex';
}

function closeModal(id) {
    document.getElementById(id).style.display = 'none';
    if (id === 'beggarListModal' && beggarListInterval) {
        clearInterval(beggarListInterval);
        beggarListInterval = null;
    }
}
window.onclick = (e) => {
    if (e.target.classList.contains('modal')) e.target.style.display = 'none';
};

/* --- BEGGAR SYSTEM --- */

async function populateBegWalletSelect() {
    try {
        const res = await fetch(API.walletList);
        const data = await res.json();
        const select = document.getElementById('begWalletSelect');
        if (!select) return;
        const currentVal = select.value;
        select.innerHTML = '<option value="">Select Wallet...</option>';
        (data.wallets || []).forEach(w => {
            const opt = document.createElement('option');
            opt.value = w.address;
            opt.textContent = `${w.label || w.address.slice(0, 12) + '...'}  (${(w.balance || 0).toFixed(4)} iCSI)`;
            select.appendChild(opt);
        });
        if (currentVal) select.value = currentVal;
    } catch (e) { }
}

async function startBegging() {
    const select = document.getElementById('begWalletSelect');
    const address = select ? select.value : '';
    if (!address) { alert('Please select a wallet to advertise.'); return; }
    try {
        await fetch(API.beggarStart, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address })
        });
        checkBeggarStatus();
    } catch (e) { alert('Failed to start begging'); }
}

async function stopBegging() {
    try {
        await fetch(API.beggarStop, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        checkBeggarStatus();
    } catch (e) { alert('Failed to stop begging'); }
}

async function checkBeggarStatus() {
    try {
        const res = await fetch(API.beggarList);
        const data = await res.json();
        const statusDiv = document.getElementById('begStatus');
        const timerSpan = document.getElementById('begTimer');
        const addrDiv = document.getElementById('begAddress');
        const startSection = document.getElementById('begStartSection');
        const stopBtn = document.getElementById('stopBegBtn');
        const menuDot = document.getElementById('begMenuDot');

        if (data.active_beg) {
            statusDiv.classList.remove('hidden');
            if (stopBtn) stopBtn.classList.remove('hidden');
            startSection.classList.add('hidden');
            addrDiv.innerText = data.active_beg.address;
            const mins = Math.floor(data.active_beg.remaining_seconds / 60);
            const secs = data.active_beg.remaining_seconds % 60;
            timerSpan.innerText = `${mins}:${String(secs).padStart(2, '0')}`;
            if (menuDot) menuDot.classList.remove('hidden');
        } else {
            statusDiv.classList.add('hidden');
            if (stopBtn) stopBtn.classList.add('hidden');
            startSection.classList.remove('hidden');
            populateBegWalletSelect();
            if (menuDot) menuDot.classList.add('hidden');
        }
    } catch (e) { }
}

let beggarListInterval = null;

function openBeggarModal() {
    const modal = document.getElementById('beggarListModal');
    modal.style.display = 'flex';
    checkBeggarStatus();
    renderBeggarList();
    if (beggarListInterval) clearInterval(beggarListInterval);
    beggarListInterval = setInterval(() => { renderBeggarList(); checkBeggarStatus(); }, 5000);
}

// Keep showBeggarList as alias
function showBeggarList() { openBeggarModal(); }

async function renderBeggarList() {
    const content = document.getElementById('beggarListContent');
    try {
        const res = await fetch(API.beggarList);
        const data = await res.json();
        const beggars = data.beggars || [];

        if (beggars.length === 0) {
            content.innerHTML = '<div class="text-zinc-500 text-sm font-mono text-center py-8">No beggars on the network yet.</div>';
            return;
        }

        content.innerHTML = beggars.map(b => {
            const shortAddr = b.address.length > 20 ? b.address.slice(0, 10) + '...' + b.address.slice(-10) : b.address;
            const ago = Math.floor((Date.now() / 1000 - b.last_seen) / 60);
            return `
            <div class="bg-black border border-zinc-800 rounded-lg p-4 flex items-center justify-between gap-4 hover:border-yellow-800/50 transition-colors">
                <div class="flex-1 min-w-0">
                    <div class="font-mono text-xs text-yellow-400 truncate cursor-pointer hover:text-yellow-300" title="${b.address}" onclick="copyBeggarAddress('${b.address}')">
                        💰 ${shortAddr}
                    </div>
                    <div class="flex gap-4 mt-1">
                        <span class="text-[10px] text-zinc-500">Balance: <span class="text-cyan-400">${(b.balance || 0).toFixed(4)} iCSI</span></span>
                        <span class="text-[10px] text-zinc-600">Seen ${ago}m ago</span>
                    </div>
                </div>
                <button onclick="copyBeggarAddress('${b.address}')" class="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-yellow-400 text-[10px] font-bold uppercase rounded-md transition-colors whitespace-nowrap">
                    📋 Copy
                </button>
            </div>`;
        }).join('');
    } catch (e) {
        content.innerHTML = '<div class="text-red-400 text-sm font-mono text-center py-8">Error loading beggars list.</div>';
    }
}

function copyBeggarAddress(address) {
    navigator.clipboard.writeText(address).then(() => {
        // Brief visual feedback
        const btn = event.target;
        const original = btn.innerText;
        btn.innerText = '✓ Copied!';
        btn.classList.add('text-green-400');
        setTimeout(() => { btn.innerText = original; btn.classList.remove('text-green-400'); }, 1500);
    }).catch(() => {
        // Fallback for non-https
        const ta = document.createElement('textarea');
        ta.value = address;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        alert('Address copied!');
    });
}

// --- Data Export Logic ---
function openDataModal() {
    openModal('dataModal');
}

// --- Download Miner Logic ---


function openDownloadMinerModal() {
    openModal('downloadMinerModal');

    // Auto-populate command with current host and credentials
    const host = window.location.hostname;
    const rpcPort = 9342; // External RPC port

    // Fetch current auth to populate command
    fetch('/api/rpc/config')
        .then(res => res.json())
        .then(data => {
            const user = data.user || 'user';
            const pass = data.password || 'pass';

            const cmd = `python3 miner.py --url http://${host}:${rpcPort} --user ${user} --pass ${pass}`;
            document.getElementById('minerCommand').innerText = cmd;
        })
        .catch(() => {
            // Fallback
            const cmd = `python3 miner.py --url http://${host}:${rpcPort} --user user --pass pass`;
            document.getElementById('minerCommand').innerText = cmd;
        });
}

function openGpuMinerModal() {
    openModal('gpuMinerModal');
}

// --- RPC Auth Logic ---

function openRpcConfigModal() {
    openModal('rpcConfigModal');
    loadRpcConfig();
}

function checkMinerAuth() {
    alert("To verify if your miner supports Auth:\n\n1. Check if 'Enforce Username/Password' is ENABLED in RPC Auth.\n2. If enabled, your miner MUST be started with:\n   --user <username> --pass <password>\n\nIf you see '401 Unauthorized' in your miner logs, either correct the password or DISABLE enforcement here.");
}

async function loadRpcConfig() {
    try {
        const response = await fetch('/api/rpc/config');
        const data = await response.json();

        document.getElementById('rpcUser').value = data.user;
        document.getElementById('rpcPass').value = data.password;
        document.getElementById('rpcEnforce').checked = data.enforce_auth;
    } catch (error) {
        console.error("Failed to load RPC config:", error);
        alert("Failed to load RPC config");
    }
}

async function saveRpcConfig() {
    const user = document.getElementById('rpcUser').value;
    const password = document.getElementById('rpcPass').value;
    const enforce = document.getElementById('rpcEnforce').checked;

    try {
        const response = await fetch('/api/rpc/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user: user,
                password: password,
                enforce_auth: enforce
            })
        });

        const result = await response.json();
        if (response.ok) {
            alert("RPC Configuration Saved");
            closeModal('rpcConfigModal');
        } else {
            alert("Error: " + result.error);
        }
    } catch (error) {
        console.error("Failed to save RPC config:", error);
        alert("Failed to save RPC config");
    }
}

// --- Web Auth ---

async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
        window.location.reload();
    } catch (e) {
        console.error("Logout failed", e);
    }
}

// --- Theme Functions ---
function openThemeModal() {
    const modal = document.getElementById('themeModal');
    const content = document.getElementById('themeModalContent');
    modal.classList.remove('hidden');
    // Small timeout to allow display:block to apply before opacity transition
    setTimeout(() => {
        modal.classList.remove('opacity-0');
        content.classList.remove('scale-95');
        content.classList.add('scale-100');
    }, 10);
}

function closeThemeModal() {
    const modal = document.getElementById('themeModal');
    const content = document.getElementById('themeModalContent');
    modal.classList.add('opacity-0');
    content.classList.remove('scale-100');
    content.classList.add('scale-95');
    setTimeout(() => {
        modal.classList.add('hidden');
    }, 300);
}

function setTheme(colorValue) {
    // Update CSS Variable
    document.documentElement.style.setProperty('--color-primary', colorValue);
    // Save to LocalStorage
    localStorage.setItem('theme-color', colorValue);
}

// Close modal on outside click
const themeModal = document.getElementById('themeModal');
if (themeModal) {
    themeModal.addEventListener('click', (e) => {
        if (e.target === themeModal) {
            closeThemeModal();
        }
    });
}

function openNetworkUplinkModal() {
    const modal = document.getElementById('networkUplinkModal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }
}


function closeNetworkUplinkModal() {
    const modal = document.getElementById('networkUplinkModal');
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }
}

async function checkIntegrity() {
    const btn = document.getElementById('btnIntegrity');
    const originalText = btn.innerHTML;

    // Set Loading State
    btn.disabled = true;
    btn.innerHTML = `<span class="animate-spin">↻</span> Checking DB...`;
    btn.classList.remove('bg-zinc-800', 'hover:bg-zinc-700');
    btn.classList.add('bg-yellow-900/20', 'text-yellow-500');

    try {
        const res = await fetch('/api/integrity_check', {
            method: 'POST'
        });
        const data = await res.json();

        if (data.status === 'ok') {
            let msg = `<span>✅ Integrity OK</span>`;

            if (data.network) {
                if (data.network.peer_count === 0) {
                    msg = `<span>⚠️ Valid but Offline (0 Peers)</span>`;
                    btn.classList.remove('bg-green-900/20', 'text-green-500');
                    btn.classList.add('bg-orange-900/20', 'text-orange-500');
                } else if (data.network.synced) {
                    msg = `<span>✅ Everything is Cool! (Synced)</span>`;
                    btn.classList.add('bg-green-900/20', 'text-green-500');
                } else {
                    const diff = data.network.peer_height - data.network.local_height;
                    // If diff is huge, say "Syncing". If small, say "Lagging".
                    // Let's just say "Syncing" to be safe/encouraging.
                    msg = `<span>⏳ Syncing... (${diff} blocks behind)</span>`;
                    // Use Blue for syncing? Or Orange? Orange is fine.
                    btn.classList.remove('bg-green-900/20', 'text-green-500');
                    btn.classList.add('bg-blue-900/20', 'text-blue-500');
                }
            } else {
                btn.classList.add('bg-green-900/20', 'text-green-500');
            }

            btn.innerHTML = msg;
            btn.classList.remove('bg-yellow-900/20', 'text-yellow-500');


            // Revert after 5s
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.className = "w-full py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-400 hover:text-white transition-colors flex items-center justify-center gap-2";
                btn.classList.remove('bg-green-900/20', 'text-green-500', 'bg-orange-900/20', 'text-orange-500', 'bg-blue-900/20', 'text-blue-500');
                btn.disabled = false;
            }, 5000);
        } else {
            // Corruption Found!
            alert(`DATA CORRUPTION DETECTED!\n\n${data.message}\n\nBlock Height: ${data.bad_block}\n\nRecommendation: Go to NODE MANAGEMENT -> Terminal Scripts and use the Update/Reset script to fix this.`);
            btn.innerHTML = `<span>❌ Corruption Found</span>`;
            btn.classList.remove('bg-yellow-900/20', 'text-yellow-500');
            btn.classList.add('bg-red-900/20', 'text-red-500');
            btn.disabled = false;
        }
    } catch (e) {
        alert("Check Failed: " + e);
        btn.innerHTML = originalText;
        btn.disabled = false;
        btn.className = "w-full py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-400 hover:text-white transition-colors flex items-center justify-center gap-2";
    }
}
