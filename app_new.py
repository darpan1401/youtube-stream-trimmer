from flask import Flask, render_template, request, jsonify, send_file, Response
import subprocess
import json
import os
import tempfile
import logging
from datetime import datetime
import traceback
from functools import wraps
import shutil
import re
import uuid
import threading
import time
import sys

app = Flask(__name__)

# In-memory task store for progress tracking
tasks = {}
tasks_lock = threading.Lock()

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 2000 * 1024 * 1024  # 2GB limit
DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 2000))

# Logging setup with better formatting — log to stdout for Render/Docker visibility
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("YT-TRIMMER")

# Startup diagnostics
logger.info("="*60)
logger.info("YouTube Trimmer Pro — Starting up")
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"Temp directory: {tempfile.gettempdir()}")
logger.info(f"DEBUG mode: {DEBUG}")
logger.info(f"HOST: {HOST} | PORT: {PORT}")

# Check yt-dlp availability
try:
    _ytdlp_version = subprocess.run(
        ['yt-dlp', '--version'], capture_output=True, text=True, timeout=10
    )
    logger.info(f"yt-dlp version: {_ytdlp_version.stdout.strip()}")
except Exception as e:
    logger.critical(f"yt-dlp NOT FOUND or broken: {e}")

# Check ffmpeg availability
try:
    _ffmpeg_version = subprocess.run(
        ['ffmpeg', '-version'], capture_output=True, text=True, timeout=10
    )
    _ffmpeg_first_line = _ffmpeg_version.stdout.split('\n')[0] if _ffmpeg_version.stdout else 'unknown'
    logger.info(f"ffmpeg: {_ffmpeg_first_line}")
except Exception as e:
    logger.critical(f"ffmpeg NOT FOUND or broken: {e}")

# Check Node.js availability (needed by PO token provider)
try:
    _node_version = subprocess.run(
        ['node', '--version'], capture_output=True, text=True, timeout=10
    )
    logger.info(f"Node.js version: {_node_version.stdout.strip()}")
except Exception as e:
    logger.warning(f"Node.js not found: {e} (PO token provider won't work)")

# Check PO token provider
POT_PROVIDER_AVAILABLE = False
try:
    import bgutil_ytdlp_pot_provider
    POT_PROVIDER_AVAILABLE = True
    logger.info("PO Token Provider: INSTALLED (auto bot-bypass enabled)")
except ImportError:
    logger.warning("PO Token Provider NOT installed — YouTube may block server requests")
    logger.warning("Install with: pip install bgutil-ytdlp-pot-provider")

logger.info("="*60)

# Temporary directory for downloads
TEMP_DIR = tempfile.gettempdir()

# Check if Node.js is available for yt-dlp JS runtime
NODE_AVAILABLE = False
try:
    _node_check = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=5)
    if _node_check.returncode == 0:
        NODE_AVAILABLE = True
        logger.info(f"Node.js JS runtime available for yt-dlp: {_node_check.stdout.strip()}")
except Exception:
    logger.warning("Node.js not available — yt-dlp may not bypass YouTube bot detection")


def _progress_bar(pct, width=20):
    """Generate a pip-style progress bar: ━━━━━━━━━━░░░░░░░░░░"""
    filled = int(width * min(pct, 100) / 100)
    return '━' * filled + '░' * (width - filled)


# ==================== UTILITY FUNCTIONS ====================
def is_valid_youtube_url(url):
    """Validate if URL is a valid YouTube URL"""
    youtube_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com',
        r'(?:https?://)?(?:www\.)?youtu\.be',
        r'(?:https?://)?(?:www\.)?youtube\.com/live',
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts'
    ]
    return any(re.search(pattern, url) for pattern in youtube_patterns)

def sanitize_filename(filename):
    """Remove special characters from filename"""
    filename = str(filename)[:100]  # Limit to 100 chars
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def get_ytdlp_base_args(player_client=None):
    """Return common yt-dlp arguments with anti-bot measures"""
    args = [
        'yt-dlp',
        '--no-check-certificates',
        '--no-playlist',
        '--socket-timeout', '30',
        '--extractor-retries', '5',
    ]

    # Realistic browser headers to avoid bot fingerprinting
    args.extend([
        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        '--referer', 'https://www.youtube.com/',
        '--add-header', 'Accept-Language:en-US,en;q=0.9',
        '--add-header', 'Accept:text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    ])

    # Use Node.js as JS runtime for yt-dlp (required for YouTube PO token generation)
    if NODE_AVAILABLE:
        args.extend(['--js-runtimes', 'node'])
    # Set player client for YouTube anti-bot bypass
    if player_client:
        args.extend(['--extractor-args', f'youtube:player_client={player_client}'])
    return args

# Player client strategies to try (in order of effectiveness against bot detection)
# Mobile/creator clients do NOT need PO tokens — best for datacenter IPs
PLAYER_CLIENT_STRATEGIES = [
    'web_creator',       # Creator Studio client — bypasses most bot detection (no PO token needed)
    'ios',               # iOS app client — no PO token, very reliable on datacenter IPs
    'android',           # Android app client — no PO token, good fallback
    'mweb',              # Mobile web — often bypasses bot checks
    'tv_embedded',       # TV embedded player — works on many datacenter IPs
    'mediaconnect',      # Media connect client
    None,                # Default (last resort — may trigger bot detection on servers)
]

def run_ytdlp_with_retry(extra_args, url, timeout=60, description="yt-dlp"):
    """
    Run yt-dlp with automatic retry using different player clients.
    First tries without any player_client restriction (most compatible).
    Only falls back to specific clients on bot-detection errors.
    Returns (success, result) tuple.
    """
    last_result = None
    last_stderr = ""
    
    for i, client in enumerate(PLAYER_CLIENT_STRATEGIES):
        cmd = get_ytdlp_base_args(player_client=client) + extra_args + [url]
        
        client_name = client or 'default'
        if i == 0:
            logger.info(f"{description}: Trying player_client={client_name} | URL: {url}")
        else:
            logger.info(f"{description}: Retry #{i} with player_client={client_name} | URL: {url}")
        
        logger.debug(f"Command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            last_result = result
            
            if result.returncode == 0:
                logger.info(f"{description}: SUCCESS with player_client={client_name}")
                return True, result
            
            last_stderr = result.stderr.strip() if result.stderr else ''
            logger.warning(f"{description}: FAILED with player_client={client_name} | Exit: {result.returncode} | Error: {last_stderr[:200]}")
            
            # Only retry with different client on bot-detection / auth errors
            stderr_lower = last_stderr.lower()
            is_bot_error = any(kw in stderr_lower for kw in ['sign in', 'bot', 'confirm', 'cookies', 'authentication'])
            
            if not is_bot_error:
                # Not a bot error — retrying with different client won't help
                logger.info(f"{description}: Error is not bot-related, skipping further retries")
                break
            
            logger.info(f"{description}: Bot detection detected, waiting 2s before trying next client...")
            time.sleep(2)  # Small delay between retries to avoid rate-limiting
        
        except subprocess.TimeoutExpired:
            logger.error(f"{description}: TIMEOUT with player_client={client_name} after {timeout}s")
            last_result = None
            last_stderr = f"Timeout after {timeout}s"
            continue
    
    # All retries failed
    logger.error(f"{description}: ALL strategies failed for URL: {url}")
    logger.error(f"{description}: Last stderr: {last_stderr}")
    return False, last_result

# ==================== ERROR HANDLER ====================
def error_handler(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Unhandled exception in {f.__name__}: {type(e).__name__}: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return jsonify({"error": "An error occurred. Please try again."}), 500
    return decorated

# ==================== CORS HEADERS ====================
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    # Don't cache SSE streams
    if response.content_type and 'text/event-stream' in response.content_type:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    else:
        response.headers['Cache-Control'] = 'public, max-age=3600'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response

@app.route('/')
def index():
    logger.info(f"Homepage requested | IP: {request.remote_addr} | UA: {request.user_agent.string[:80]}")
    return render_template('index.html')

@app.route('/api/get-video-info', methods=['POST'])
@error_handler
def get_video_info():
    """Fetch video info using yt-dlp"""
    req_start = time.time()
    url = request.json.get('url', '').strip()
    
    if not url:
        logger.warning("get_video_info called with empty URL")
        return jsonify({"error": "URL is required"}), 400
    
    if not is_valid_youtube_url(url):
        logger.warning(f"Invalid YouTube URL rejected: {url}")
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    logger.info(f"▶ get_video_info START | URL: {url} | IP: {request.remote_addr}")
    
    try:
        extra_args = ['--dump-json', '--no-warnings']
        
        success, result = run_ytdlp_with_retry(
            extra_args, url, timeout=60, description="get_video_info"
        )
        
        if not success:
            if result is None:
                return jsonify({"error": "Request timeout. The server is slow — please try again."}), 408
            
            stderr_output = result.stderr.strip() if result and result.stderr else 'Unknown error'
            stderr_lower = stderr_output.lower()
            
            if 'sign in' in stderr_lower or 'bot' in stderr_lower:
                error_msg = "YouTube bot detection triggered. Please try again in a moment."
            elif 'age' in stderr_lower:
                error_msg = "This video requires age verification and cannot be processed."
            elif 'private' in stderr_lower:
                error_msg = "This video is private"
            elif 'unavailable' in stderr_lower or 'not available' in stderr_lower:
                error_msg = "Video unavailable or region-restricted"
            elif 'copyright' in stderr_lower:
                error_msg = "Video blocked due to copyright"
            elif 'live' in stderr_lower and 'not started' in stderr_lower:
                error_msg = "Live stream has not started yet"
            elif 'urlopen error' in stderr_lower or 'connection' in stderr_lower:
                error_msg = "Network error — could not reach YouTube. Please try again."
            elif 'http error 429' in stderr_lower or 'too many' in stderr_lower:
                error_msg = "YouTube is rate-limiting requests. Try again in a few minutes."
            else:
                error_msg = "Invalid YouTube URL or video unavailable"
            
            return jsonify({"error": error_msg}), 400
        
        data = json.loads(result.stdout)
        duration = int(data.get("duration", 0))
        title = sanitize_filename(data.get("title", "Video"))
        uploader = data.get("uploader", "Unknown")
        
        if duration <= 0:
            logger.warning(f"Video has zero/negative duration: {url} | duration={duration}")
            return jsonify({"error": "Could not determine video duration (live stream or invalid)"}), 400
        
        elapsed = round(time.time() - req_start, 2)
        logger.info(f"✔ get_video_info SUCCESS in {elapsed}s | Title: '{title}' | Duration: {duration}s | Uploader: {uploader}")
        
        return jsonify({
            "success": True,
            "title": title,
            "duration": duration,
            "thumbnail": data.get("thumbnail", ""),
            "uploader": uploader
        })
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse yt-dlp JSON output | URL: {url} | Error: {e}")
        logger.error(f"Raw stdout (first 500 chars): {result.stdout[:500] if result and result.stdout else 'empty'}")
        return jsonify({"error": "Failed to parse video information"}), 400
    except FileNotFoundError:
        logger.critical("yt-dlp binary NOT FOUND on this system!")
        return jsonify({"error": "Server configuration error — yt-dlp not installed"}), 500
    except Exception as e:
        logger.error(f"Unexpected error fetching video | URL: {url} | Error: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": "Failed to fetch video information"}), 400

@app.route('/api/start-trim', methods=['POST'])
@error_handler
def start_trim():
    """Start trimming video and return a task ID for progress tracking"""
    data = request.json
    url = data.get('url', '').strip()
    start_time = float(data.get('startTime', 0))
    end_time = float(data.get('endTime', 0))
    quality = data.get('quality', 'best')
    filename = sanitize_filename(data.get('filename', 'trimmed_video'))
    
    logger.info(f"▶ start-trim REQUEST | URL: {url} | Range: {start_time}s-{end_time}s | Quality: {quality} | File: {filename} | IP: {request.remote_addr}")
    
    # Validation
    if not url or not is_valid_youtube_url(url):
        logger.warning(f"start-trim rejected: Invalid URL '{url}'")
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    if start_time < 0 or end_time <= start_time:
        logger.warning(f"start-trim rejected: Invalid time params start={start_time} end={end_time}")
        return jsonify({"error": "Invalid time parameters"}), 400
    
    if quality not in ['best', '1080', '720', '480', 'audio']:
        logger.warning(f"start-trim rejected: Invalid quality '{quality}'")
        return jsonify({"error": "Invalid quality"}), 400
    
    is_audio = quality == 'audio'
    task_id = str(uuid.uuid4())
    trim_duration = end_time - start_time
    
    logger.info(f"Task {task_id} CREATED | URL: {url} | Range: {start_time}s-{end_time}s ({trim_duration}s) | Quality: {quality} | Audio: {is_audio}")
    
    quality_map = {
        'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
        '1080': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best',
        '720': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best',
        '480': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best',
        'audio': 'bestaudio[ext=m4a]/bestaudio'
    }
    
    # Create temp directory (will be cleaned up after download)
    tmpdir = tempfile.mkdtemp()
    file_ext = 'mp3' if is_audio else 'mp4'
    output_path = os.path.join(tmpdir, f"{filename}.{file_ext}")
    
    # Initialize task state
    with tasks_lock:
        tasks[task_id] = {
            'status': 'starting',
            'progress': 0,
            'speed': '',
            'eta': '',
            'size': '',
            'downloaded': '',
            'phase': 'Starting download...',
            'error': None,
            'file_path': None,
            'file_name': None,
            'mimetype': None,
            'tmpdir': tmpdir,
            'filename': filename,
            'is_audio': is_audio,
            'created_at': time.time(),
        }
    logger.info(f"Task {task_id}: State initialized | Temp dir: {tmpdir} | Output: {output_path}")
    
    def run_ytdlp():
        try:
            dl_start_time = time.time()
            last_log_pct = -10  # For pip-style log throttling
            tid = task_id[:8]  # Short ID for compact logs
            
            logger.info(f"[{tid}] ▶ TRIM START | {quality} | {start_time}s→{end_time}s ({trim_duration}s) | {url}")
            
            with tasks_lock:
                tasks[task_id]['status'] = 'downloading'
                tasks[task_id]['phase'] = 'Preparing download...'
            
            cmd = get_ytdlp_base_args(player_client='web_creator') + [
                '-f', quality_map.get(quality, quality_map['best']),
                '--download-sections', f'*{start_time}-{end_time}',
                '--fragment-retries', '5',
                '--retries', '5',
                '--buffer-size', '16K',
                '--no-warnings',
                '--newline',
                '--progress-template', '%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s|%(progress._total_bytes_str)s|%(progress._downloaded_bytes_str)s',
            ]
            
            if is_audio:
                cmd.extend([
                    '-x',
                    '--audio-format', 'mp3',
                    '--audio-quality', '0',
                    '--postprocessor-args', 'ffmpeg:-b:a 192k',
                    '-o', output_path,
                ])
            else:
                cmd.extend([
                    '--merge-output-format', 'mp4',
                    '--postprocessor-args', 'ffmpeg:-c copy -movflags +faststart',
                    '-o', output_path,
                ])
            
            cmd.append(url)
            
            logger.info(f"[{tid}] CMD: {' '.join(cmd[:6])} ... {cmd[-1]}")
            
            with tasks_lock:
                tasks[task_id]['status'] = 'downloading'
                tasks[task_id]['phase'] = 'Downloading...'
            
            # Use binary mode + unbuffered to catch \r-separated ffmpeg progress
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0
            )
            
            # Read byte-by-byte to handle both \r and \n separators
            # (ffmpeg uses \r for in-place progress, yt-dlp uses \n)
            buf = b''
            while True:
                byte = process.stdout.read(1)
                if not byte:
                    break
                if byte in (b'\r', b'\n'):
                    if buf:
                        line = buf.decode('utf-8', errors='replace').strip()
                        buf = b''
                        if not line:
                            continue
                        
                        # --- Parse yt-dlp progress-template output ---
                        if '|' in line and '%' in line:
                            parts = line.split('|')
                            if len(parts) >= 5:
                                try:
                                    pct = float(parts[0].strip().replace('%', ''))
                                    speed = parts[1].strip() if parts[1].strip() != 'NA' else ''
                                    eta = parts[2].strip() if parts[2].strip() != 'NA' else ''
                                    total_size = parts[3].strip() if parts[3].strip() != 'NA' else ''
                                    downloaded = parts[4].strip() if parts[4].strip() != 'NA' else ''
                                    with tasks_lock:
                                        tasks[task_id]['progress'] = min(pct, 100)
                                        tasks[task_id]['speed'] = speed
                                        tasks[task_id]['eta'] = eta
                                        tasks[task_id]['size'] = total_size
                                        tasks[task_id]['downloaded'] = downloaded
                                    # Pip-style log every 10%
                                    if pct >= last_log_pct + 10 or pct >= 100:
                                        bar = _progress_bar(pct)
                                        logger.info(f"[{tid}] {bar} {pct:5.1f}% | {speed or '-':>10} | ETA {eta or '-':>6} | {downloaded or '-'}/{total_size or '-'}")
                                        last_log_pct = pct
                                except (ValueError, IndexError):
                                    pass
                        
                        # --- Parse ffmpeg time= output (main progress source for --download-sections) ---
                        elif 'time=' in line and 'speed=' in line:
                            time_match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
                            speed_match = re.search(r'speed=\s*(\S+)', line)
                            size_match = re.search(r'size=\s*(\S+)', line)
                            if time_match and trim_duration > 0:
                                t_h, t_m, t_s = int(time_match.group(1)), int(time_match.group(2)), float(time_match.group(3))
                                current_sec = t_h * 3600 + t_m * 60 + t_s
                                pct = min((current_sec / trim_duration) * 90, 90)  # Cap at 90%, post-processing takes 90-100
                                ffmpeg_speed = speed_match.group(1) if speed_match else ''
                                ffmpeg_size = size_match.group(1) if size_match else ''
                                remaining = trim_duration - current_sec
                                with tasks_lock:
                                    tasks[task_id]['progress'] = pct
                                    tasks[task_id]['speed'] = ffmpeg_speed
                                    tasks[task_id]['eta'] = f'{remaining:.0f}s' if remaining > 0 else '0s'
                                    tasks[task_id]['size'] = ffmpeg_size
                                    tasks[task_id]['phase'] = f'Processing... {pct:.0f}%'
                                # Pip-style log every 10%
                                if pct >= last_log_pct + 10:
                                    bar = _progress_bar(pct)
                                    logger.info(f"[{tid}] {bar} {pct:5.1f}% | {ffmpeg_speed:>10} | ~{remaining:.0f}s left | {ffmpeg_size}")
                                    last_log_pct = pct
                        
                        # --- Parse [download] fallback ---
                        elif '[download]' in line and '%' in line:
                            match = re.search(r'(\d+\.?\d*)%', line)
                            if match:
                                pct = float(match.group(1))
                                with tasks_lock:
                                    tasks[task_id]['progress'] = min(pct, 100)
                        
                        # --- Detect post-processing ---
                        elif '[Merger]' in line or '[ExtractAudio]' in line or '[ffmpeg]' in line:
                            logger.info(f"[{tid}] ⚙ Post-processing...")
                            with tasks_lock:
                                tasks[task_id]['phase'] = 'Merging & processing...'
                                tasks[task_id]['progress'] = 95
                        
                        # --- Log important yt-dlp info lines (not progress noise) ---
                        elif line.startswith('[') and 'download' not in line.lower():
                            logger.info(f"[{tid}] {line}")
                else:
                    buf += byte
            
            process.wait()
            dl_elapsed = round(time.time() - dl_start_time, 2)
            
            if process.returncode != 0:
                logger.error(f"[{tid}] ✘ FAILED | exit={process.returncode} | {dl_elapsed}s")
                with tasks_lock:
                    tasks[task_id]['status'] = 'error'
                    tasks[task_id]['error'] = 'Failed to trim video. Check video availability.'
                return
            
            # Find the actual output file
            actual_file = None
            for f in os.listdir(tmpdir):
                if f.startswith(filename):
                    actual_file = os.path.join(tmpdir, f)
                    break
            
            if not actual_file or not os.path.exists(actual_file):
                dir_contents = os.listdir(tmpdir) if os.path.exists(tmpdir) else []
                logger.error(f"Task {task_id}: Output file not found! Expected prefix: '{filename}' | Dir contents: {dir_contents}")
                with tasks_lock:
                    tasks[task_id]['status'] = 'error'
                    tasks[task_id]['error'] = 'Failed to create output file'
                return
            
            if is_audio:
                mimetype = 'audio/mpeg'
                dl_name = f"{filename}.mp3"
            else:
                mimetype = 'video/mp4'
                dl_name = f"{filename}.mp4"
            
            file_size = os.path.getsize(actual_file)
            total_elapsed = round(time.time() - dl_start_time, 2)
            logger.info(f"[{tid}] ✔ DONE | {dl_name} | {file_size / (1024*1024):.2f} MB | {total_elapsed}s")
            
            with tasks_lock:
                tasks[task_id]['status'] = 'done'
                tasks[task_id]['progress'] = 100
                tasks[task_id]['phase'] = 'Complete!'
                tasks[task_id]['file_path'] = actual_file
                tasks[task_id]['file_name'] = dl_name
                tasks[task_id]['mimetype'] = mimetype
                tasks[task_id]['file_size'] = file_size
        
        except Exception as e:
            logger.error(f"[{tid}] ✘ EXCEPTION: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            with tasks_lock:
                tasks[task_id]['status'] = 'error'
                tasks[task_id]['error'] = str(e)
    
    # Start background thread
    thread = threading.Thread(target=run_ytdlp, daemon=True)
    thread.start()
    logger.info(f"[{task_id[:8]}] Thread started")
    
    return jsonify({"task_id": task_id})


@app.route('/api/progress/<task_id>')
def progress(task_id):
    """SSE endpoint for real-time progress updates"""
    logger.info(f"SSE: Stream opened | {task_id[:8]}")
    sse_start = time.time()
    sse_last_log = -20
    def generate():
        nonlocal sse_last_log
        while True:
            with tasks_lock:
                task = tasks.get(task_id)
            
            if not task:
                yield f"data: {json.dumps({'status': 'error', 'error': 'Task not found'})}\n\n"
                break
            
            event_data = {
                'status': task['status'],
                'progress': task['progress'],
                'speed': task['speed'],
                'eta': task['eta'],
                'size': task['size'],
                'downloaded': task['downloaded'],
                'phase': task['phase'],
            }
            
            if task['status'] == 'done':
                event_data['file_size'] = task.get('file_size', 0)
                event_data['file_name'] = task.get('file_name', '')
                logger.info(f"SSE: ✔ Done | {task_id[:8]} | {round(time.time()-sse_start,1)}s")
                yield f"data: {json.dumps(event_data)}\n\n"
                break
            
            if task['status'] == 'error':
                event_data['error'] = task.get('error', 'Unknown error')
                logger.error(f"SSE: ✘ Error | {task_id[:8]} | {event_data['error']}")
                yield f"data: {json.dumps(event_data)}\n\n"
                break
            
            yield f"data: {json.dumps(event_data)}\n\n"
            time.sleep(0.5)
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@app.route('/api/download/<task_id>')
def download_file(task_id):
    """Download the completed file"""
    logger.info(f"▶ DOWNLOAD REQUEST | {task_id[:8]}")
    
    with tasks_lock:
        task = tasks.get(task_id)
    
    if not task:
        logger.warning(f"Download FAILED: Task {task_id} not found in store")
        return jsonify({"error": "Task not found"}), 404
    
    if task['status'] != 'done':
        logger.warning(f"Download FAILED: Task {task_id} not ready | Current status: {task['status']} | Progress: {task['progress']}%")
        return jsonify({"error": "File not ready"}), 400
    
    file_path = task['file_path']
    if not file_path or not os.path.exists(file_path):
        logger.error(f"Download FAILED: File missing | Path: {file_path} | Task: {task_id}")
        return jsonify({"error": "File not found"}), 404
    
    file_size = os.path.getsize(file_path)
    logger.info(f"Download: Serving {task['file_name']} | {file_size / (1024*1024):.2f} MB")
    
    return send_file(
        file_path,
        mimetype=task['mimetype'],
        as_attachment=True,
        download_name=task['file_name']
    )


@app.route('/api/cleanup/<task_id>', methods=['POST'])
def cleanup_task(task_id):
    """Clean up task files after download"""
    logger.info(f"Cleanup requested for task {task_id}")
    
    with tasks_lock:
        task = tasks.pop(task_id, None)
        active_count = len(tasks)
    
    if task and task.get('tmpdir') and os.path.exists(task['tmpdir']):
        try:
            tmpdir_size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, dn, filenames in os.walk(task['tmpdir'])
                for f in filenames
            )
            shutil.rmtree(task['tmpdir'])
            logger.info(f"Cleaned up task {task_id} | Freed: {tmpdir_size / (1024*1024):.2f} MB | Active tasks remaining: {active_count}")
        except Exception as e:
            logger.error(f"Cleanup failed for task {task_id}: {type(e).__name__}: {e}")
    else:
        logger.info(f"Cleanup: No temp dir to remove for task {task_id} | Active tasks: {active_count}")
    
    return jsonify({"ok": True})


# Keep the old endpoint for backward compatibility
@app.route('/api/trim-video', methods=['POST'])
@error_handler
def trim_video():
    """Trim and download video (legacy endpoint without progress)"""
    data = request.json
    url = data.get('url', '').strip()
    start_time = float(data.get('startTime', 0))
    end_time = float(data.get('endTime', 0))
    quality = data.get('quality', 'best')
    filename = sanitize_filename(data.get('filename', 'trimmed_video'))
    
    # Validation
    if not url or not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    if start_time < 0 or end_time <= start_time:
        return jsonify({"error": "Invalid time parameters"}), 400
    
    if quality not in ['best', '1080', '720', '480', 'audio']:
        return jsonify({"error": "Invalid quality"}), 400
    
    is_audio = quality == 'audio'
    
    logger.info(f"Legacy trim-video | URL: {url} | Range: {start_time}s-{end_time}s | Quality: {quality} | File: {filename} | IP: {request.remote_addr}")
    
    quality_map = {
        'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
        '1080': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best',
        '720': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best',
        '480': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best',
        'audio': 'bestaudio[ext=m4a]/bestaudio'
    }
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_ext = 'mp3' if is_audio else 'mp4'
            output_path = os.path.join(tmpdir, f"{filename}.{file_ext}")
            
            cmd = get_ytdlp_base_args(player_client='web_creator') + [
                '-f', quality_map.get(quality, quality_map['best']),
                '--download-sections', f'*{start_time}-{end_time}',
                '--concurrent-fragments', '16',
                '--fragment-retries', '5',
                '--retries', '5',
                '--buffer-size', '16K',
                '--no-warnings',
            ]
            
            if is_audio:
                cmd.extend([
                    '-x',
                    '--audio-format', 'mp3',
                    '--audio-quality', '0',
                    '--postprocessor-args', 'ffmpeg:-b:a 192k',
                    '-o', output_path,
                ])
            else:
                cmd.extend([
                    '--merge-output-format', 'mp4',
                    '--postprocessor-args', 'ffmpeg:-c copy -movflags +faststart',
                    '-o', output_path,
                ])
            
            cmd.append(url)
            
            logger.info(f"Legacy trim: Executing yt-dlp command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                logger.error(f"Legacy trim yt-dlp FAILED | Exit code: {result.returncode}")
                logger.error(f"Legacy trim yt-dlp stderr: {result.stderr}")
                logger.error(f"Legacy trim yt-dlp stdout: {result.stdout[:500] if result.stdout else 'empty'}")
                error_msg = result.stderr.lower()
                if 'not available' in error_msg or 'unavailable' in error_msg:
                    return jsonify({"error": "Video not available in your region"}), 400
                return jsonify({"error": "Failed to trim video. Check video availability."}), 400
            
            # yt-dlp may change the extension, find the actual output file
            actual_file = None
            for f in os.listdir(tmpdir):
                if f.startswith(filename):
                    actual_file = os.path.join(tmpdir, f)
                    break
            
            if not actual_file or not os.path.exists(actual_file):
                dir_contents = os.listdir(tmpdir) if os.path.exists(tmpdir) else []
                logger.error(f"Legacy trim: Output file not found! Expected prefix: '{filename}' | Dir contents: {dir_contents}")
                return jsonify({"error": "Failed to create output file"}), 500
            
            actual_ext = os.path.splitext(actual_file)[1].lstrip('.')
            
            if is_audio:
                mimetype = 'audio/mpeg'
                dl_name = f"{filename}.mp3"
            else:
                mimetype = 'video/mp4'
                dl_name = f"{filename}.mp4"
            
            file_size = os.path.getsize(actual_file)
            logger.info(f"File ready. Size: {file_size / (1024*1024):.2f} MB | Type: {mimetype}")
            
            return send_file(
                actual_file,
                mimetype=mimetype,
                as_attachment=True,
                download_name=dl_name
            )
    
    except subprocess.TimeoutExpired:
        logger.error(f"Legacy trim TIMEOUT after 600s | URL: {url}")
        return jsonify({"error": "Processing timeout. Try smaller duration or lower quality."}), 408
    except FileNotFoundError:
        logger.critical("yt-dlp binary NOT FOUND on this system!")
        return jsonify({"error": "Server configuration error — yt-dlp not installed"}), 500
    except Exception as e:
        logger.error(f"Legacy trim EXCEPTION: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": "Failed to process video"}), 500

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint with diagnostics"""
    # Check yt-dlp
    ytdlp_ok = False
    ytdlp_version = 'unknown'
    try:
        r = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=10)
        ytdlp_ok = r.returncode == 0
        ytdlp_version = r.stdout.strip() if r.stdout else 'unknown'
    except Exception as e:
        logger.error(f"Health check: yt-dlp failed: {e}")
    
    # Check ffmpeg
    ffmpeg_ok = False
    try:
        r = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        ffmpeg_ok = r.returncode == 0
    except Exception as e:
        logger.error(f"Health check: ffmpeg failed: {e}")
    
    # Check disk space
    try:
        stat = shutil.disk_usage(TEMP_DIR)
        disk_free_mb = stat.free / (1024 * 1024)
    except Exception:
        disk_free_mb = -1
    
    with tasks_lock:
        active_tasks = len(tasks)
    
    status = 'ok' if (ytdlp_ok and ffmpeg_ok) else 'degraded'
    
    health_data = {
        "status": status,
        "yt_dlp": {"installed": ytdlp_ok, "version": ytdlp_version},
        "ffmpeg": {"installed": ffmpeg_ok},
        "pot_provider": {"installed": POT_PROVIDER_AVAILABLE},
        "nodejs_runtime": {"available": NODE_AVAILABLE},
        "disk_free_mb": round(disk_free_mb, 1),
        "active_tasks": active_tasks,
        "temp_dir": TEMP_DIR,
        "timestamp": datetime.now().isoformat()
    }
    
    logger.info(f"Health check | Status: {status} | yt-dlp: {ytdlp_version} | POT: {POT_PROVIDER_AVAILABLE} | Node.js: {NODE_AVAILABLE} | Disk free: {disk_free_mb:.0f} MB | Active tasks: {active_tasks}")
    
    return jsonify(health_data), 200 if status == 'ok' else 503


# ==================== PERIODIC CLEANUP ====================
def periodic_cleanup():
    """Clean up stale tasks older than 30 minutes"""
    while True:
        time.sleep(300)  # Every 5 minutes
        try:
            now = time.time()
            stale_ids = []
            with tasks_lock:
                for tid, task in tasks.items():
                    created = task.get('created_at', now)
                    if now - created > 1800:  # 30 minutes
                        stale_ids.append(tid)
            
            for tid in stale_ids:
                with tasks_lock:
                    task = tasks.pop(tid, None)
                if task and task.get('tmpdir') and os.path.exists(task['tmpdir']):
                    shutil.rmtree(task['tmpdir'], ignore_errors=True)
                    logger.info(f"Auto-cleaned stale task {tid}")
            
            if stale_ids:
                logger.info(f"Periodic cleanup: removed {len(stale_ids)} stale tasks")
        except Exception as e:
            logger.error(f"Periodic cleanup error: {e}")

cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()
logger.info("Periodic cleanup thread started (every 5 min, stale after 30 min)")

if __name__ == '__main__':
    logger.info("Starting YouTube Trimmer App")
    logger.info(f"Configuration — Debug: {DEBUG}, Host: {HOST}, Port: {PORT}")
    app.run(debug=DEBUG, host=HOST, port=PORT)
