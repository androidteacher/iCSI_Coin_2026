/* Main.js - iCSI Coin Node UI */

const API = {
    connect: '/api/connect',
    peers: '/api/peers',
    logs: '/api/logs',
    testNat: '/api/stun/test',
    reset: '/api/reset',
    stats: '/api/stats',
    walletList: '/api/wallet/list',
    walletCreate: '/api/wallet/create',
    walletDelete: '/api/wallet/delete',
    walletSend: '/api/wallet/send',
    walletImport: '/api/wallet/import',
    minerStatus: '/api/miner/status',
    minerStart: '/api/miner/start',
    minerStop: '/api/miner/stop'
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

    const btn = document.querySelector('#connectionForm .btn.primary');
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
        btn.innerText = "[ INITIALIZE NETWORK ]";
    }

}

async function testNat() {
    const resDiv = document.getElementById('natResult');
    resDiv.innerText = "Testing...";

    try {
        // We assume STUN IP is same as Seed IP already configured, or grab from input if we want dynamic
        // The endpoint uses whatever is configured in backend or we pass it? 
        // Our backend handle_test_stun uses manager's config. 
        // Let's rely on manager's config which was set by 'connect'.
        const res = await fetch(API.testNat, { method: 'POST', body: JSON.stringify({}) }); // Empty body uses default
        const data = await res.json();

        if (data.success) {
            resDiv.innerText = "SUCCESS: " + data.message;
            resDiv.className = "mt-2 text-xs font-mono text-emerald-400 break-all";
        } else {
            resDiv.innerText = "FAILED: " + (data.message || "Timeout");
            resDiv.className = "mt-2 text-xs font-mono text-red-500 break-all";
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
            statusEl.className = "w-full py-3 rounded-lg text-center font-bold tracking-widest text-sm mb-6 bg-emerald-950/30 border border-emerald-900 text-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.2)]";
        } else {
            statusEl.innerText = "OFFLINE";
            statusEl.className = "w-full py-3 rounded-lg text-center font-bold tracking-widest text-sm mb-6 bg-black border border-zinc-900 text-red-500 border-red-900/30";
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
                    ${p.can_delete ? `<button class="ml-2 text-red-500 hover:text-red-400 font-bold" onclick="deletePeer('${p.ip}', ${p.port})">×</button>` : ''}
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

    modal.style.display = "block";
    title.innerText = `LOGS: ${ip}:${port}`;
    content.innerText = "Loading...";

    try {
        const res = await fetch(`${API.logs}?ip=${ip}&port=${port}`);
        const data = await res.json();
        content.innerText = data.logs.join('\n') || "No logs.";
    } catch (e) { content.innerText = "Error"; }
}

/* --- WALLET --- */

async function loadWallets() {
    try {
        const res = await fetch(API.walletList);
        const data = await res.json();
        const select = document.getElementById('walletSelect');
        const targetSelect = document.getElementById('miningTargetSelect');

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
            resDiv.className = "mt-3 text-center text-xs font-mono text-emerald-400";
            loadWallets(); // Refresh balance
        } else {
            resDiv.innerText = "FAILED: " + data.error;
            resDiv.className = "mt-3 text-center text-xs font-mono text-red-500";
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

function closeModal(id) { document.getElementById(id).style.display = 'none'; }
window.onclick = (e) => {
    if (e.target.classList.contains('modal')) e.target.style.display = 'none';
};
function resetSystem() {
    if (confirm("Reset all logs and peers?")) {
        fetch(API.reset, { method: 'POST' }).then(updatePeers);
    }
}
