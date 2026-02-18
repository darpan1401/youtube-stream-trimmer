/* ClipForge — Production Frontend JS */
'use strict';

// ===== UTILITIES =====
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

function hms(sec) {
    sec = Math.max(0, Math.floor(sec));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

function shortTime(sec) {
    sec = Math.max(0, Math.floor(sec));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    if (sec >= 3600) {
        const h = Math.floor(sec / 3600);
        return `${h}:${String(m % 60).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    }
    return `${m}:${String(s).padStart(2,'0')}`;
}

function parseHMS(str) {
    const parts = str.replace(/[^0-9:]/g, '').split(':').map(Number);
    if (parts.length === 3) return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
    if (parts.length === 2) return (parts[0] * 60) + parts[1];
    return parts[0] || 0;
}

function fmtBytes(b) {
    if (b === 0) return '0 B';
    const k = 1024, u = ['B','KB','MB','GB'];
    const i = Math.floor(Math.log(b) / Math.log(k));
    return (b / Math.pow(k, i)).toFixed(1) + ' ' + u[i];
}

// ===== TOAST SYSTEM =====
function toast(title, msg, type = 'success', dur = 4500) {
    const wrap = $('#toasts');
    const icons = { success: '✓', error: '✕', warning: '!' };
    const cls = { success: 's', error: 'e', warning: 'w' };
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = `
        <div class="toast-icon ${cls[type] || 's'}">${icons[type] || '✓'}</div>
        <div class="toast-body">
            <div class="toast-title">${title}</div>
            ${msg ? `<div class="toast-msg">${msg}</div>` : ''}
        </div>
        <button class="toast-close" aria-label="Close">×</button>
    `;
    el.querySelector('.toast-close').onclick = () => dismiss(el);
    wrap.appendChild(el);

    const timer = setTimeout(() => dismiss(el), dur);
    function dismiss(t) {
        clearTimeout(timer);
        t.classList.add('exit');
        setTimeout(() => t.remove(), 260);
    }
}

// ===== STATE =====
const state = {
    url: '',
    duration: 0,
    title: '',
    channel: '',
    thumb: '',
    start: 0,
    end: 0,
    quality: 'best',
    busy: false
};

// ===== DOM =====
const urlInput = $('#urlInput');
const loadBtn = $('#loadBtn');
const urlError = $('#urlError');
const skeleton = $('#skeleton');
const editor = $('#editor');
const trimBtn = $('#trimBtn');

// Video info
const vThumb = $('#vThumb');
const vBadge = $('#vBadge');
const vTitle = $('#vTitle');
const vChannel = $('#vChannel');

// Slider
const sliderTrack = $('#sliderTrack');
const sliderFill = $('#sliderFill');
const hStart = $('#hStart');
const hEnd = $('#hEnd');
const tipStart = $('#tipStart');
const tipEnd = $('#tipEnd');
const sliderMax = $('#sliderMax');
const trimDur = $('#trimDur');

// Time inputs
const tStart = $('#tStart');
const tEnd = $('#tEnd');

// Quality
const qualityRow = $('#qualityRow');
const fnameInput = $('#fnameInput');

// Progress overlay
const overlay = $('#overlay');
const ringFg = $('#ringFg');
const ringPct = $('#ringPct');
const oPhase = $('#oPhase');
const oSpeed = $('#oSpeed');
const oEta = $('#oEta');
const oSize = $('#oSize');
const oBar = $('#oBar');

// Ring circumference (r=52)
const CIRC = 2 * Math.PI * 52; // ~326.73

// ===== LOAD VIDEO =====
loadBtn.addEventListener('click', loadVideo);
urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') loadVideo(); });

async function loadVideo() {
    const url = urlInput.value.trim();
    console.log('[ClipForge] loadVideo called | URL:', url);
    if (!url) { showUrlError('Please paste a YouTube URL'); return; }
    if (state.busy) { console.log('[ClipForge] loadVideo blocked — busy'); return; }

    state.busy = true;
    setLoading(true);
    hideUrlError();
    editor.classList.add('hidden');
    skeleton.classList.remove('hidden');

    try {
        console.log('[ClipForge] Fetching video info...');
        const t0 = performance.now();
        const res = await fetch('/api/get-video-info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        console.log('[ClipForge] Video info response:', res.status, data, `(${Math.round(performance.now()-t0)}ms)`);

        if (!res.ok || !data.success) {
            throw new Error(data.error || 'Failed to load video');
        }

        state.url = url;
        state.duration = data.duration;
        state.title = data.title || 'Untitled';
        state.channel = data.uploader || 'Unknown';
        state.thumb = data.thumbnail || '';
        state.start = 0;
        state.end = data.duration;

        // Populate UI
        vThumb.src = state.thumb;
        vBadge.textContent = shortTime(state.duration);
        vTitle.textContent = state.title;
        vChannel.textContent = state.channel;
        sliderMax.textContent = shortTime(state.duration);
        fnameInput.value = state.title.substring(0, 60).replace(/[^a-zA-Z0-9_ -]/g, '_') || 'youtube_trim';

        updateSlider();
        updateTimeDisplays();

        skeleton.classList.add('hidden');
        editor.classList.remove('hidden');
        console.log('[ClipForge] Video loaded successfully:', state.title, '| Duration:', state.duration + 's');
        toast('Video loaded', state.title, 'success', 3000);

    } catch (err) {
        console.error('[ClipForge] loadVideo ERROR:', err.message);
        skeleton.classList.add('hidden');
        showUrlError(err.message);
        toast('Error', err.message, 'error', 5000);
    } finally {
        state.busy = false;
        setLoading(false);
    }
}

function setLoading(on) {
    loadBtn.disabled = on;
    loadBtn.querySelector('.btn-load-text').classList.toggle('hidden', on);
    loadBtn.querySelector('.btn-load-spinner').classList.toggle('hidden', !on);
}

function showUrlError(msg) {
    urlError.textContent = msg;
    urlError.classList.remove('hidden');
}
function hideUrlError() {
    urlError.classList.add('hidden');
}

// ===== SLIDER =====
let dragging = null;

function updateSlider() {
    if (state.duration <= 0) return;
    const sp = (state.start / state.duration) * 100;
    const ep = (state.end / state.duration) * 100;
    hStart.style.left = sp + '%';
    hEnd.style.left = ep + '%';
    sliderFill.style.left = sp + '%';
    sliderFill.style.width = (ep - sp) + '%';
    tipStart.textContent = hms(state.start);
    tipEnd.textContent = hms(state.end);
}

function updateTimeDisplays() {
    tStart.value = hms(state.start);
    tEnd.value = hms(state.end);
    const dur = state.end - state.start;
    if (dur >= 3600) trimDur.textContent = hms(dur);
    else if (dur >= 60) trimDur.textContent = Math.floor(dur / 60) + 'm ' + (dur % 60) + 's';
    else trimDur.textContent = dur + 's';
}

function posToSec(clientX) {
    const rect = sliderTrack.getBoundingClientRect();
    let pct = (clientX - rect.left) / rect.width;
    pct = Math.max(0, Math.min(1, pct));
    return Math.round(pct * state.duration);
}

// Mouse
hStart.addEventListener('mousedown', e => startDrag(e, 'start'));
hEnd.addEventListener('mousedown', e => startDrag(e, 'end'));
document.addEventListener('mousemove', onDrag);
document.addEventListener('mouseup', stopDrag);

// Touch
hStart.addEventListener('touchstart', e => startDrag(e, 'start'), { passive: false });
hEnd.addEventListener('touchstart', e => startDrag(e, 'end'), { passive: false });
document.addEventListener('touchmove', onDrag, { passive: false });
document.addEventListener('touchend', stopDrag);

function startDrag(e, which) {
    e.preventDefault();
    dragging = which;
    const handle = which === 'start' ? hStart : hEnd;
    handle.classList.add('dragging');
}

function onDrag(e) {
    if (!dragging) return;
    e.preventDefault();
    const x = e.touches ? e.touches[0].clientX : e.clientX;
    let sec = posToSec(x);

    if (dragging === 'start') {
        sec = Math.max(0, Math.min(sec, state.end - 1));
        state.start = sec;
    } else {
        sec = Math.max(state.start + 1, Math.min(sec, state.duration));
        state.end = sec;
    }
    updateSlider();
    updateTimeDisplays();
}

function stopDrag() {
    if (!dragging) return;
    const handle = dragging === 'start' ? hStart : hEnd;
    handle.classList.remove('dragging');
    dragging = null;
}

// Keyboard
hStart.addEventListener('keydown', e => handleKey(e, 'start'));
hEnd.addEventListener('keydown', e => handleKey(e, 'end'));

function handleKey(e, which) {
    const step = e.shiftKey ? 10 : 1;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
        e.preventDefault();
        if (which === 'start') state.start = Math.max(0, state.start - step);
        else state.end = Math.max(state.start + 1, state.end - step);
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (which === 'start') state.start = Math.min(state.end - 1, state.start + step);
        else state.end = Math.min(state.duration, state.end + step);
    } else return;
    updateSlider();
    updateTimeDisplays();
}

// Time Inputs
tStart.addEventListener('change', () => {
    let s = parseHMS(tStart.value);
    s = Math.max(0, Math.min(s, state.end - 1));
    state.start = s;
    updateSlider();
    updateTimeDisplays();
});
tEnd.addEventListener('change', () => {
    let s = parseHMS(tEnd.value);
    s = Math.max(state.start + 1, Math.min(s, state.duration));
    state.end = s;
    updateSlider();
    updateTimeDisplays();
});

// ===== QUALITY =====
qualityRow.addEventListener('click', e => {
    const btn = e.target.closest('.q-chip');
    if (!btn) return;
    qualityRow.querySelectorAll('.q-chip').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.quality = btn.dataset.q;
});

// ===== TRIM & DOWNLOAD =====
trimBtn.addEventListener('click', startTrim);

async function startTrim() {
    console.log('[ClipForge] startTrim called | URL:', state.url, '| Range:', state.start + 's -', state.end + 's | Quality:', state.quality);
    if (state.busy || !state.url) { console.log('[ClipForge] startTrim blocked — busy:', state.busy, '| url:', !!state.url); return; }
    const dur = state.end - state.start;
    if (dur <= 0) { toast('Invalid range', 'End time must be after start time', 'warning'); return; }

    state.busy = true;
    trimBtn.disabled = true;
    showOverlay(true);

    const fname = fnameInput.value.trim() || 'youtube_trim';
    const isAudio = state.quality === 'audio';
    const ext = isAudio ? '.mp3' : '.mp4';
    let taskId = null;
    const trimStartTime = performance.now();

    try {
        // 1. Start trim
        console.log('[ClipForge] Sending start-trim request...');
        const res = await fetch('/api/start-trim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: state.url,
                startTime: state.start,
                endTime: state.end,
                quality: state.quality,
                filename: fname
            })
        });
        const d = await res.json();
        console.log('[ClipForge] start-trim response:', res.status, d);
        if (!res.ok) throw new Error(d.error || 'Failed to start');
        taskId = d.task_id;
        console.log('[ClipForge] Task created:', taskId);

        // 2. SSE progress
        console.log('[ClipForge] Opening SSE stream for task:', taskId);
        let sseEventCount = 0;
        let lastLoggedPct = -1;
        await new Promise((resolve, reject) => {
            const es = new EventSource(`/api/progress/${taskId}`);
            es.onmessage = ev => {
                const p = JSON.parse(ev.data);
                sseEventCount++;
                
                if (p.status === 'error') {
                    console.error('[ClipForge] SSE ERROR:', p.error, '| Events received:', sseEventCount);
                    es.close(); reject(new Error(p.error || 'Processing failed')); return;
                }

                const pct = Math.round(p.progress || 0);
                
                // Log every 10% change or status change
                if (pct >= lastLoggedPct + 10 || p.status === 'done') {
                    const elapsed = Math.round((performance.now() - trimStartTime) / 1000);
                    console.log(`[ClipForge] SSE #${sseEventCount} | Status: ${p.status} | Progress: ${pct}% | Speed: ${p.speed} | ETA: ${p.eta} | Size: ${p.size} | Elapsed: ${elapsed}s`);
                    lastLoggedPct = pct;
                }
                
                setProgress(pct);

                // Phase text
                let phase = p.phase || 'Processing…';
                if (pct > 0 && pct < 100 && p.status === 'downloading') phase = `Downloading… ${pct}%`;
                oPhase.textContent = phase;

                // Stats
                oSpeed.textContent = p.speed || '—';
                oEta.textContent = (p.eta && p.eta !== 'Unknown') ? p.eta : '—';
                oSize.textContent = p.size || '—';

                if (p.status === 'done') {
                    const totalTime = Math.round((performance.now() - trimStartTime) / 1000);
                    console.log(`[ClipForge] ✔ DOWNLOAD COMPLETE | Total time: ${totalTime}s | Events: ${sseEventCount} | File: ${p.file_name} | Size: ${p.file_size} bytes`);
                    es.close(); resolve(p);
                }
            };
            es.onerror = (e) => {
                console.error('[ClipForge] SSE connection error:', e, '| Events received:', sseEventCount);
                es.close(); reject(new Error('Connection lost — please retry'));
            };
        });

        // 3. Download
        console.log('[ClipForge] Triggering file download for task:', taskId);
        oPhase.textContent = 'Preparing download…';
        setProgress(100);

        // Trigger native download
        window.location.href = `/api/download/${taskId}`;

        // Hide overlay after short delay
        setTimeout(() => {
            showOverlay(false);
            toast('Download started', `${fname}${ext} — check your browser downloads`, 'success', 5000);
        }, 800);

        // Cleanup later
        setTimeout(() => { fetch(`/api/cleanup/${taskId}`, { method: 'POST' }).catch(() => {}); }, 120000);

    } catch (err) {
        console.error('[ClipForge] startTrim ERROR:', err.message, err);
        showOverlay(false);
        toast('Error', err.message, 'error', 6000);
        if (taskId) fetch(`/api/cleanup/${taskId}`, { method: 'POST' }).catch(() => {});
    } finally {
        state.busy = false;
        trimBtn.disabled = false;
    }
}

// ===== OVERLAY HELPERS =====
function showOverlay(show) {
    overlay.classList.toggle('hidden', !show);
    if (show) {
        setProgress(0);
        oPhase.textContent = 'Starting…';
        oSpeed.textContent = '—';
        oEta.textContent = '—';
        oSize.textContent = '—';
    }
}

function setProgress(pct) {
    pct = Math.max(0, Math.min(100, pct));
    ringPct.textContent = pct + '%';
    const offset = CIRC - (pct / 100) * CIRC;
    ringFg.style.strokeDashoffset = offset;
    oBar.style.width = pct + '%';
}

// Add SVG gradient for ring (inject once)
(function injectRingGradient() {
    const svg = document.querySelector('.ring-svg');
    if (!svg) return;
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `<linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#7c3aed"/>
        <stop offset="100%" stop-color="#c084fc"/>
    </linearGradient>`;
    svg.insertBefore(defs, svg.firstChild);
})();

// ===== ENTER KEY ON URL =====
urlInput.addEventListener('focus', () => hideUrlError());
