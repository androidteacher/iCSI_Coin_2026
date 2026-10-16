// ============================================================================
//  theme.js — Shared theme picker (accent color) for all iCSI Coin pages
// ----------------------------------------------------------------------------
//  Drives the single CSS variable --color-primary (stored as an "R G B" triple)
//  and persists the choice in localStorage('theme-color'). Each page keeps its
//  own small inline <head> script that applies the saved color early (to avoid
//  a flash); this file provides the modal, presets, custom picker and random.
// ============================================================================

// Curated accent-color presets (name + "R G B" triple for --color-primary)
const THEME_PRESETS = [
    { name: 'Amethyst', rgb: '168 85 247' },
    { name: 'Violet', rgb: '139 92 246' },
    { name: 'Indigo', rgb: '99 102 241' },
    { name: 'Royal', rgb: '59 130 246' },
    { name: 'Sky', rgb: '14 165 233' },
    { name: 'Cyan', rgb: '6 182 212' },
    { name: 'Teal', rgb: '20 184 166' },
    { name: 'Emerald', rgb: '16 185 129' },
    { name: 'Matrix', rgb: '0 230 118' },
    { name: 'Green', rgb: '34 197 94' },
    { name: 'Lime', rgb: '132 204 22' },
    { name: 'Gold', rgb: '234 179 8' },
    { name: 'Amber', rgb: '245 158 11' },
    { name: 'Orange', rgb: '249 115 22' },
    { name: 'Ember', rgb: '234 88 12' },
    { name: 'Red', rgb: '239 68 68' },
    { name: 'Crimson', rgb: '220 38 38' },
    { name: 'Rose', rgb: '244 63 94' },
    { name: 'Pink', rgb: '236 72 153' },
    { name: 'Fuchsia', rgb: '217 70 239' },
    { name: 'Magenta', rgb: '233 30 170' },
    { name: 'Steel', rgb: '100 116 139' },
    { name: 'Silver', rgb: '148 163 184' },
    { name: 'Snow', rgb: '226 232 240' },
];

function getCurrentThemeRgb() {
    const saved = localStorage.getItem('theme-color');
    if (saved) return saved.trim();
    const v = getComputedStyle(document.documentElement).getPropertyValue('--color-primary').trim();
    return v || '168 85 247';
}

function rgbTripleToHex(triple) {
    const parts = triple.trim().split(/\s+/).map(Number);
    const h = (n) => Math.max(0, Math.min(255, n || 0)).toString(16).padStart(2, '0');
    return `#${h(parts[0])}${h(parts[1])}${h(parts[2])}`;
}

function hexToRgbTriple(hex) {
    hex = hex.replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);
    return `${r} ${g} ${b}`;
}

// Random hue with pleasant saturation/lightness so "Surprise Me" always looks good
function hslToRgbTriple(h, s, l) {
    let r, g, b;
    if (s === 0) {
        r = g = b = l;
    } else {
        const hue2rgb = (p, q, t) => {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1 / 6) return p + (q - p) * 6 * t;
            if (t < 1 / 2) return q;
            if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
            return p;
        };
        const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        const p = 2 * l - q;
        r = hue2rgb(p, q, h + 1 / 3);
        g = hue2rgb(p, q, h);
        b = hue2rgb(p, q, h - 1 / 3);
    }
    return `${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)}`;
}

function renderThemePresets() {
    const grid = document.getElementById('themePresetGrid');
    if (!grid) return;
    const current = getCurrentThemeRgb();
    grid.innerHTML = THEME_PRESETS.map((p) => {
        const active = p.rgb === current;
        const css = p.rgb.split(' ').join(',');
        return `
            <button type="button" onclick="setTheme('${p.rgb}')" title="${p.name}"
                class="group relative flex flex-col items-center gap-1.5 p-2 rounded-xl border transition-all focus:outline-none ${active ? 'border-white bg-zinc-800/60' : 'border-transparent hover:border-zinc-600 hover:bg-zinc-800/40'}">
                <span class="relative w-full aspect-square rounded-lg shadow-inner ring-offset-2 ring-offset-surface ${active ? 'ring-2 ring-white' : ''}" style="background-color: rgb(${css})">
                    <span class="absolute inset-0 flex items-center justify-center ${active ? '' : 'hidden'}">
                        <svg class="w-6 h-6 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                    </span>
                </span>
                <span class="text-[11px] truncate w-full text-center ${active ? 'text-white font-semibold' : 'text-zinc-400 group-hover:text-white'}">${p.name}</span>
            </button>`;
    }).join('');
}

function syncThemeControls() {
    const hex = rgbTripleToHex(getCurrentThemeRgb());
    const picker = document.getElementById('customColorPicker');
    if (picker) picker.value = hex;
    const hexLabel = document.getElementById('customColorHex');
    if (hexLabel) hexLabel.textContent = hex.toUpperCase();
    renderThemePresets();
}

function openThemeModal() {
    const modal = document.getElementById('themeModal');
    const content = document.getElementById('themeModalContent');
    if (!modal) return;
    syncThemeControls();
    modal.classList.remove('hidden');
    // Small timeout to allow display:block to apply before opacity transition
    setTimeout(() => {
        modal.classList.remove('opacity-0');
        if (content) {
            content.classList.remove('scale-95');
            content.classList.add('scale-100');
        }
    }, 10);
}

function closeThemeModal() {
    const modal = document.getElementById('themeModal');
    const content = document.getElementById('themeModalContent');
    if (!modal) return;
    modal.classList.add('opacity-0');
    if (content) {
        content.classList.remove('scale-100');
        content.classList.add('scale-95');
    }
    setTimeout(() => {
        modal.classList.add('hidden');
    }, 300);
}

function setTheme(colorValue) {
    colorValue = colorValue.trim();
    // Update CSS Variable
    document.documentElement.style.setProperty('--color-primary', colorValue);
    // Save to LocalStorage
    localStorage.setItem('theme-color', colorValue);
    // Keep the picker, hex label, and preset highlight in sync
    syncThemeControls();
}

function setThemeFromPicker(hex) {
    setTheme(hexToRgbTriple(hex));
}

function setRandomTheme() {
    setTheme(hslToRgbTriple(Math.random(), 0.72, 0.6));
}

// Close the modal when clicking the dimmed backdrop
(function attachThemeBackdropClose() {
    const modal = document.getElementById('themeModal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeThemeModal();
        });
    }
})();
