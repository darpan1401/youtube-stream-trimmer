// ==================== ALERT NOTIFICATION SYSTEM ====================
function showAlert(message, type = 'info', duration = 4000) {
    // Remove existing alert if any (except loading ones when showing non-loading)
    const existing = document.querySelectorAll('.custom-alert-overlay');
    existing.forEach(el => {
        if (!el.classList.contains('alert-loading') || type !== 'loading') {
            el.classList.add('alert-exit');
            setTimeout(() => el.remove(), 300);
        }
    });

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-times-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle',
        loading: 'fa-spinner fa-spin'
    };

    const titles = {
        success: 'Success!',
        error: 'Error!',
        warning: 'Warning!',
        info: 'Info',
        loading: 'Processing...'
    };

    const overlay = document.createElement('div');
    overlay.className = `custom-alert-overlay alert-${type} ${type === 'loading' ? 'alert-loading' : ''}`;

    overlay.innerHTML = `
        <div class="custom-alert">
            <div class="alert-icon alert-icon-${type}"><i class="fas ${icons[type] || icons.info}"></i></div>
            <h3 class="alert-title">${titles[type] || titles.info}</h3>
            <p class="alert-message">${message}</p>
            <div class="alert-details" id="alertDetails"></div>
            ${type === 'loading' ? `
                <div class="alert-progress-wrapper">
                    <div class="alert-progress-bar">
                        <div class="alert-progress-fill"></div>
                    </div>
                    <span class="alert-progress-percent">0%</span>
                </div>
            ` : ''}
            ${type !== 'loading' ? '<button class="alert-ok-btn" onclick="this.closest(\'.custom-alert-overlay\').classList.add(\'alert-exit\');setTimeout(()=>this.closest(\'.custom-alert-overlay\').remove(),300)">OK</button>' : ''}
        </div>
    `;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('alert-enter'));

    // Auto-remove for non-loading alerts
    if (type !== 'loading' && duration > 0) {
        setTimeout(() => {
            overlay.classList.add('alert-exit');
            setTimeout(() => overlay.remove(), 300);
        }, duration);
    }

    return overlay;
}

function removeAlert(overlay) {
    if (overlay && overlay.parentElement) {
        overlay.classList.add('alert-exit');
        setTimeout(() => overlay.remove(), 300);
    }
}

function updateAlertMessage(overlay, message) {
    if (overlay) {
        const msgEl = overlay.querySelector('.alert-message');
        if (msgEl) msgEl.innerHTML = message;
    }
}

function updateAlertDetails(overlay, html) {
    if (overlay) {
        const detailsEl = overlay.querySelector('.alert-details');
        if (detailsEl) detailsEl.innerHTML = html;
    }
}

function updateAlertProgress(overlay, percent) {
    if (overlay) {
        const fill = overlay.querySelector('.alert-progress-fill');
        if (fill) fill.style.width = percent + '%';
    }
}

function updateAlertPercentText(overlay, percent) {
    if (overlay) {
        const pctEl = overlay.querySelector('.alert-progress-percent');
        if (pctEl) pctEl.textContent = percent + '%';
    }
}

// ==================== STATE MANAGEMENT ====================
let videoState = {
    url: '',
    duration: 0,
    title: '',
    uploader: '',
    thumbnail: '',
    startTime: 0,
    endTime: 0,
    quality: 'best'
};

// ==================== DOM ELEMENTS ====================
const videoUrlInput = document.getElementById('videoUrl');
const loadBtn = document.getElementById('loadBtn');
const loadingSpinner = document.getElementById('loadingSpinner');
const videoSection = document.getElementById('videoSection');

const videoThumbnail = document.getElementById('videoThumbnail');
const videoTitle = document.getElementById('videoTitle');
const videoUploader = document.getElementById('videoUploader');
const totalDurationEl = document.getElementById('totalDuration');
const durationBadge = document.getElementById('durationBadge');

const startTimeDisplay = document.getElementById('startTimeDisplay');
const endTimeDisplay = document.getElementById('endTimeDisplay');
const trimDurationDisplay = document.getElementById('trimDurationDisplay');
const startSecInput = document.getElementById('startSecInput');
const endSecInput = document.getElementById('endSecInput');

// Custom slider elements
const rangeSlider = document.getElementById('rangeSlider');
const handleStart = document.getElementById('handleStart');
const handleEnd = document.getElementById('handleEnd');
const sliderHighlight = document.getElementById('sliderHighlight');
const tooltipStart = document.getElementById('tooltipStart');
const tooltipEnd = document.getElementById('tooltipEnd');

const qualityBtns = document.querySelectorAll('.quality-btn');
const selectedQualityInput = document.getElementById('selectedQuality');
const outputName = document.getElementById('outputName');
const downloadBtn = document.getElementById('downloadBtn');

// ==================== UTILITY FUNCTIONS ====================
function secondsToHMS(seconds) {
    seconds = Math.floor(seconds);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function showError(message) {
    showAlert(message, 'error', 5000);
}

function showSuccess(message) {
    showAlert(message, 'success', 4000);
}

function disableLoadBtn(disable) {
    loadBtn.disabled = disable;
    loadBtn.style.opacity = disable ? '0.6' : '1';
}

// ==================== LOAD VIDEO ====================
loadBtn.addEventListener('click', async () => {
    const url = videoUrlInput.value.trim();
    
    if (!url) {
        showError('Please paste a YouTube URL');
        return;
    }

    disableLoadBtn(true);
    loadingSpinner.classList.remove('hidden');

    try {
        const response = await fetch('/api/get-video-info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to load video');
        }

        const data = await response.json();
        
        // Update state
        videoState.url = url;
        videoState.duration = data.duration;
        videoState.title = data.title;
        videoState.uploader = data.uploader;
        videoState.thumbnail = data.thumbnail;
        videoState.startTime = 0;
        videoState.endTime = data.duration;

        // Update UI
        videoThumbnail.src = data.thumbnail;
        videoTitle.textContent = data.title;
        videoUploader.textContent = `By ${data.uploader}`;
        totalDurationEl.textContent = secondsToHMS(data.duration);
        durationBadge.textContent = secondsToHMS(data.duration);

        // Reset slider
        startSecInput.max = data.duration;
        endSecInput.max = data.duration;
        startSecInput.value = 0;
        endSecInput.value = data.duration;

        updateSliderUI();
        updateTimeDisplayFromState();
        
        videoSection.classList.remove('hidden');
        loadingSpinner.classList.add('hidden');
        showAlert('Video loaded successfully!', 'success', 3000);

    } catch (error) {
        showError(error.message || 'Error loading video');
        loadingSpinner.classList.add('hidden');
    } finally {
        disableLoadBtn(false);
    }
});

// ==================== CUSTOM SLIDER HANDLING ====================

// Update handle positions and highlight bar from state
function updateSliderUI() {
    const duration = videoState.duration;
    if (duration <= 0) return;
    
    const startPct = (videoState.startTime / duration) * 100;
    const endPct = (videoState.endTime / duration) * 100;
    
    // Position handles using percentage of the track area
    handleStart.style.left = startPct + '%';
    handleEnd.style.left = endPct + '%';
    
    // Highlight bar between the two handles
    sliderHighlight.style.left = startPct + '%';
    sliderHighlight.style.width = (endPct - startPct) + '%';
    
    // Update tooltips
    tooltipStart.textContent = secondsToHMS(videoState.startTime);
    tooltipEnd.textContent = secondsToHMS(videoState.endTime);
}

// Update all time displays from videoState
function updateTimeDisplayFromState() {
    startTimeDisplay.textContent = secondsToHMS(videoState.startTime);
    endTimeDisplay.textContent = secondsToHMS(videoState.endTime);
    trimDurationDisplay.textContent = secondsToHMS(videoState.endTime - videoState.startTime);
    startSecInput.value = videoState.startTime;
    endSecInput.value = videoState.endTime;
}

// Convert mouse/touch X position to seconds
function xToSeconds(clientX) {
    const rect = rangeSlider.getBoundingClientRect();
    let pct = (clientX - rect.left) / rect.width;
    pct = Math.max(0, Math.min(1, pct));
    return Math.round(pct * videoState.duration);
}

// Drag state
let activeHandle = null;

function onDragStart(e, handle) {
    e.preventDefault();
    activeHandle = handle;
    handle.classList.add('dragging');
    document.body.style.cursor = 'grabbing';
    document.body.style.userSelect = 'none';
}

function onDragMove(e) {
    if (!activeHandle) return;
    
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    let sec = xToSeconds(clientX);
    
    if (activeHandle === handleStart) {
        sec = Math.max(0, Math.min(sec, videoState.endTime - 1));
        videoState.startTime = sec;
    } else {
        sec = Math.max(videoState.startTime + 1, Math.min(sec, videoState.duration));
        videoState.endTime = sec;
    }
    
    updateSliderUI();
    updateTimeDisplayFromState();
}

function onDragEnd() {
    if (!activeHandle) return;
    activeHandle.classList.remove('dragging');
    activeHandle = null;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
}

// Mouse events on handles
handleStart.addEventListener('mousedown', (e) => onDragStart(e, handleStart));
handleEnd.addEventListener('mousedown', (e) => onDragStart(e, handleEnd));
document.addEventListener('mousemove', onDragMove);
document.addEventListener('mouseup', onDragEnd);

// Touch events on handles
handleStart.addEventListener('touchstart', (e) => onDragStart(e, handleStart), { passive: false });
handleEnd.addEventListener('touchstart', (e) => onDragStart(e, handleEnd), { passive: false });
document.addEventListener('touchmove', onDragMove, { passive: false });
document.addEventListener('touchend', onDragEnd);

// Click on track to move nearest handle
rangeSlider.addEventListener('click', (e) => {
    if (e.target.closest('.slider-handle')) return; // ignore handle clicks
    
    const sec = xToSeconds(e.clientX);
    const distToStart = Math.abs(sec - videoState.startTime);
    const distToEnd = Math.abs(sec - videoState.endTime);
    
    if (distToStart <= distToEnd) {
        videoState.startTime = Math.max(0, Math.min(sec, videoState.endTime - 1));
    } else {
        videoState.endTime = Math.max(videoState.startTime + 1, Math.min(sec, videoState.duration));
    }
    
    updateSliderUI();
    updateTimeDisplayFromState();
});

// Keyboard support on handles (arrow keys)
handleStart.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
        videoState.startTime = Math.min(videoState.startTime + 1, videoState.endTime - 1);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
        videoState.startTime = Math.max(0, videoState.startTime - 1);
    } else return;
    e.preventDefault();
    updateSliderUI();
    updateTimeDisplayFromState();
});

handleEnd.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
        videoState.endTime = Math.min(videoState.endTime + 1, videoState.duration);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
        videoState.endTime = Math.max(videoState.startTime + 1, videoState.endTime - 1);
    } else return;
    e.preventDefault();
    updateSliderUI();
    updateTimeDisplayFromState();
});

// Precise input handling
startSecInput.addEventListener('input', function() {
    handleStartInput();
});

startSecInput.addEventListener('change', function() {
    handleStartInput();
});

endSecInput.addEventListener('input', function() {
    handleEndInput();
});

endSecInput.addEventListener('change', function() {
    handleEndInput();
});

function handleStartInput() {
    let value = parseInt(startSecInput.value);
    if (isNaN(value) || startSecInput.value === '') {
        return;
    }
    
    value = Math.max(0, Math.min(value, videoState.duration - 1));
    
    if (value >= videoState.endTime) {
        value = Math.max(0, videoState.endTime - 1);
    }
    
    videoState.startTime = value;
    startSecInput.value = value;
    
    startTimeDisplay.textContent = secondsToHMS(value);
    trimDurationDisplay.textContent = secondsToHMS(videoState.endTime - value);
    updateSliderUI();
}

function handleEndInput() {
    let value = parseInt(endSecInput.value);
    if (isNaN(value) || endSecInput.value === '') {
        return;
    }
    
    value = Math.max(1, Math.min(value, videoState.duration));
    
    if (value <= videoState.startTime) {
        value = Math.min(videoState.duration, videoState.startTime + 1);
    }
    
    videoState.endTime = value;
    endSecInput.value = value;
    
    endTimeDisplay.textContent = secondsToHMS(value);
    trimDurationDisplay.textContent = secondsToHMS(value - videoState.startTime);
    updateSliderUI();
}

// Re-position handles on window resize
window.addEventListener('resize', () => {
    if (videoState.duration > 0) updateSliderUI();
});

// ==================== QUALITY SELECTION ====================
qualityBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        qualityBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        videoState.quality = btn.dataset.quality;
        selectedQualityInput.value = videoState.quality;
    });
});

// ==================== DOWNLOAD VIDEO ====================
let isDownloading = false;

downloadBtn.addEventListener('click', async () => {
    if (isDownloading) return;
    
    const trimDuration = videoState.endTime - videoState.startTime;
    
    if (trimDuration <= 0) {
        showAlert('End time must be greater than start time', 'warning', 4000);
        return;
    }

    const filename = outputName.value.trim() || 'youtube_trim';
    
    const isAudio = videoState.quality === 'audio';
    const fileExt = isAudio ? '.mp3' : '.mp4';
    
    isDownloading = true;
    downloadBtn.disabled = true;
    downloadBtn.style.opacity = '0.5';
    downloadBtn.style.pointerEvents = 'none';
    downloadBtn.querySelector('span:last-child').textContent = 'Processing...';
    
    const qualityLabel = isAudio ? 'Audio Only' : (videoState.quality === 'best' ? 'Best Quality' : videoState.quality + 'p');
    const loadingAlert = showAlert(`Processing ${qualityLabel}...<br><span style="font-size:0.85rem;color:var(--text-secondary)">Trim: ${secondsToHMS(videoState.startTime)} → ${secondsToHMS(videoState.endTime)}</span>`, 'loading', 0);

    let taskId = null;

    try {
        // Step 1: Start the trim task
        const startResponse = await fetch('/api/start-trim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: videoState.url,
                startTime: videoState.startTime,
                endTime: videoState.endTime,
                quality: videoState.quality,
                filename: filename
            })
        });

        if (!startResponse.ok) {
            const data = await startResponse.json();
            throw new Error(data.error || 'Failed to start processing');
        }

        const startData = await startResponse.json();
        taskId = startData.task_id;

        // Step 2: Listen to SSE progress
        await new Promise((resolve, reject) => {
            const evtSource = new EventSource(`/api/progress/${taskId}`);
            
            evtSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.status === 'error') {
                    evtSource.close();
                    reject(new Error(data.error || 'Processing failed'));
                    return;
                }
                
                // Update progress bar
                const percent = Math.round(data.progress || 0);
                updateAlertProgress(loadingAlert, percent);
                
                // Build phase/status message
                let statusMsg = data.phase || 'Processing...';
                if (percent > 0 && percent < 100) {
                    statusMsg = `Downloading... ${percent}%`;
                }
                updateAlertMessage(loadingAlert, statusMsg + `<br><span style="font-size:0.85rem;color:var(--text-secondary)">Trim: ${secondsToHMS(videoState.startTime)} → ${secondsToHMS(videoState.endTime)}</span>`);
                
                // Build details
                let detailsHtml = '';
                if (percent > 0) {
                    detailsHtml += `<span>Progress: <strong>${percent}%</strong></span>`;
                }
                if (data.speed) {
                    detailsHtml += `<span>Speed: <strong>${data.speed}</strong></span>`;
                }
                if (data.eta && data.eta !== 'Unknown') {
                    detailsHtml += `<span>ETA: <strong>${data.eta}</strong></span>`;
                }
                if (data.size) {
                    detailsHtml += `<span>Size: <strong>${data.size}</strong></span>`;
                }
                if (data.downloaded) {
                    detailsHtml += `<span>Downloaded: <strong>${data.downloaded}</strong></span>`;
                }
                if (detailsHtml) {
                    updateAlertDetails(loadingAlert, detailsHtml);
                }
                
                // Update progress bar percentage text
                updateAlertPercentText(loadingAlert, percent);
                
                if (data.status === 'done') {
                    evtSource.close();
                    resolve(data);
                }
            };
            
            evtSource.onerror = () => {
                evtSource.close();
                reject(new Error('Connection to server lost'));
            };
        });

        // Step 3: Download the file
        removeAlert(loadingAlert);

        // Use window.location to trigger native browser download
        // Server sends Content-Disposition: attachment so page won't navigate away
        window.location.href = `/api/download/${taskId}`;

        showAlert(`Download Started!<br><span style="font-size:0.85rem;color:var(--text-secondary)">File: ${filename}${fileExt} — check your browser downloads</span>`, 'success', 6000);

        // Cleanup server-side temp files (delay to let download complete)
        setTimeout(() => {
            fetch(`/api/cleanup/${taskId}`, { method: 'POST' }).catch(() => {});
        }, 120000);

    } catch (error) {
        removeAlert(loadingAlert);
        showAlert(error.message || 'Error processing video', 'error', 6000);
        
        // Cleanup on error too
        if (taskId) {
            fetch(`/api/cleanup/${taskId}`, { method: 'POST' }).catch(() => {});
        }
    } finally {
        isDownloading = false;
        downloadBtn.disabled = false;
        downloadBtn.style.opacity = '1';
        downloadBtn.style.pointerEvents = '';
        downloadBtn.querySelector('span:last-child').textContent = 'Trim & Download';
    }
});

// Utility function to format bytes
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Utility function to format speed
function formatSpeed(bytesPerSec) {
    return formatBytes(bytesPerSec) + '/s';
}

// ==================== KEYBOARD SHORTCUTS ====================
document.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && videoUrlInput === document.activeElement) {
        loadBtn.click();
    }
});

// ==================== PAGE LOAD ====================
window.addEventListener('load', () => {
    console.log('YouTube Trimmer Pro loaded');
    // Prefill if there's a URL in the input
    if (videoUrlInput.value) {
        loadBtn.click();
    }
    // Check cookies status on load
    checkCookiesStatus();
});

// ==================== COOKIES SETTINGS ====================
const settingsBtn = document.getElementById('settingsBtn');
const cookiesModal = document.getElementById('cookiesModal');
const closeModal = document.getElementById('closeModal');
const uploadCookiesBtn = document.getElementById('uploadCookiesBtn');
const cookiesFileInput = document.getElementById('cookiesFile');
const uploadStatusEl = document.getElementById('uploadStatus');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

// Open/close modal
settingsBtn.addEventListener('click', () => {
    cookiesModal.classList.remove('hidden');
    checkCookiesStatus();
});

closeModal.addEventListener('click', () => {
    cookiesModal.classList.add('hidden');
});

cookiesModal.addEventListener('click', (e) => {
    if (e.target === cookiesModal) cookiesModal.classList.add('hidden');
});

// Check cookies status
async function checkCookiesStatus() {
    try {
        const resp = await fetch('/api/cookies-status');
        const data = await resp.json();
        
        if (data.has_cookies && data.youtube_cookies > 0) {
            statusDot.classList.add('active');
            statusText.textContent = `Active — ${data.youtube_cookies} YouTube cookies loaded`;
        } else if (data.has_cookies) {
            statusDot.classList.remove('active');
            statusText.textContent = `File exists but no YouTube cookies found`;
        } else {
            statusDot.classList.remove('active');
            statusText.textContent = 'Not configured — YouTube may block requests';
        }
    } catch (e) {
        statusText.textContent = 'Could not check status';
    }
}

// Upload cookies
uploadCookiesBtn.addEventListener('click', () => {
    cookiesFileInput.click();
});

cookiesFileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    uploadStatusEl.textContent = 'Uploading...';
    uploadStatusEl.className = 'upload-status';
    
    const formData = new FormData();
    formData.append('cookies', file);
    
    try {
        const resp = await fetch('/api/upload-cookies', {
            method: 'POST',
            body: formData
        });
        
        const data = await resp.json();
        
        if (data.success) {
            uploadStatusEl.textContent = data.message;
            uploadStatusEl.className = 'upload-status ' + (data.warning ? 'error' : 'success');
            checkCookiesStatus();
        } else {
            uploadStatusEl.textContent = data.error || 'Upload failed';
            uploadStatusEl.className = 'upload-status error';
        }
    } catch (err) {
        uploadStatusEl.textContent = 'Upload failed — server error';
        uploadStatusEl.className = 'upload-status error';
    }
    
    // Reset file input
    cookiesFileInput.value = '';
});
