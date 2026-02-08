/* Main.js - iCSI Coin Node UI */

const API = {
    connect: '/api/connect',
    peers: '/api/peers',
    logs: '/api/logs',
    testNat: '/api/stun/test',
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
    statsInterval = setInterval(updateStats, 5000);

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
        document.getElementById('netReward').innerText = data.reward.toFixed(8) + " ICSI";
        document.getElementById('netHalving').innerText = data.halving_countdown + " Blocks";
    } catch (e) {
        console.error("Stats Update Failed", e);
    }
}

async function connectToNetwork() {
    const ip = document.getElementById('seedIp').value;
    if (!ip) return alert("Enter Seed IP");

    const btn = document.getElementById('connectBtn');
    btn.innerText = "CONNECTING...";

    try {
        const res = await fetch(API.connect, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seed_ip: ip })
        });
        const data = await res.json();
        if (res.ok) {
            btn.innerText = `INITIATED (${data.connected_count})`;
            // Status update handled by polling
        }
    } catch (e) {
        alert("Connection Failed");
        btn.innerText = "[ ADD NODE ]";
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
            dot.className = 'inline-block w-2 h-2 rounded-full bg-cyan-400';
            text.className = 'text-cyan-400';
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
            resDiv.className = "mt-2 text-xs font-mono text-cyan-400 break-all";
        } else {
            resDiv.innerText = "FAILED: " + (data.message || "Timeout");
            resDiv.className = "mt-2 text-xs font-mono text-pink-500 break-all";
        }
    } catch (e) {
        resDiv.innerText = "Error: " + e;
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
            statusEl.className = "w-full py-3 rounded-lg text-center font-bold tracking-widest text-sm mb-6 bg-cyan-950/30 border border-cyan-900 text-cyan-500 shadow-[0_0_15px_rgba(6,182,212,0.2)]";
        } else {
            statusEl.innerText = "OFFLINE";
            statusEl.className = "w-full py-3 rounded-lg text-center font-bold tracking-widest text-sm mb-6 bg-black border border-zinc-900 text-pink-500 border-pink-900/30";
        }

        data.peers.forEach(p => {

            if (!p.status.toUpperCase().includes('ACTIVE')) return; // Show ACTIVE and ACTIVE (ICE)

            const key = `${p.ip}:${p.port}`;
            if (filter && !key.toLowerCase().includes(filter)) return;

            const tr = document.createElement('tr');
            tr.className = "hover:bg-zinc-900/50 transition-colors";
            tr.innerHTML = `
                <td class="py-3 pl-2 text-zinc-300 font-mono">${p.ip}</td>
                <td class="py-3 text-zinc-500 font-mono">${p.port}</td>
                <td class="py-3 pr-2 text-right">
                    <button class="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-primary text-[10px] font-bold uppercase rounded-md transition-colors" onclick="showLogs('${p.ip}', ${p.port})">LOG</button>
                    ${p.can_delete ? `<button class="ml-2 text-pink-500 hover:text-pink-400 font-bold" onclick="deletePeer('${p.ip}', ${p.port})">×</button>` : ''}
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) { console.error("Peer Update Failed", e); }
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
        const targetSelect = document.getElementById('miningTargetSelect');

        // Smart Update: Check if we need to full rebuild
        const currentOptions = Array.from(select.options);
        const needsRebuild = currentOptions.length !== data.wallets.length ||
            !data.wallets.every((w, i) => currentOptions[i] && currentOptions[i].value === w.address);

        if (needsRebuild) {
            // Save current selection
            const currentVal = select.value;
            select.innerHTML = '';
            targetSelect.innerHTML = '';

            data.wallets.forEach(w => {
                const opt = document.createElement('option');
                opt.value = w.address;
                opt.innerText = `[${w.balance.toFixed(2)}] ${w.name}`;
                opt.dataset.balance = w.balance;
                opt.dataset.name = w.name;
                select.appendChild(opt);

                const targetOpt = opt.cloneNode(true);
                targetSelect.appendChild(targetOpt);
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
                    opt.innerText = `[${w.balance.toFixed(2)}] ${w.name}`;
                    opt.dataset.balance = w.balance;

                    // Update target select too
                    if (targetSelect.options[i]) {
                        targetSelect.options[i].innerText = `[${w.balance.toFixed(2)}] ${w.name}`;
                    }
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
        displayBal.innerText = parseFloat(opt.dataset.balance).toFixed(2);
        displayAddr.innerText = opt.value;
        selectedWallet = opt.value;
    } else {
        displayBal.innerText = "0.00";
        displayAddr.innerText = "---";
        selectedWallet = null;
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
            resDiv.className = "mt-3 text-center text-xs font-mono text-cyan-400";
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

    document.getElementById('manageWalletModal').style.display = 'block';
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
    const target = document.getElementById('miningTargetSelect').value;
    await fetch(API.minerStart, {
        method: 'POST',
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

function openCreateWalletModal() { document.getElementById('createWalletModal').style.display = 'block'; }
function openImportWalletModal() { document.getElementById('importWalletModal').style.display = 'block'; }

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
