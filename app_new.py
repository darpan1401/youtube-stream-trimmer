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

logger.info("="*60)

# Temporary directory for downloads
TEMP_DIR = tempfile.gettempdir()

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
    url = request.json.get('url', '').strip()
    
    if not url:
        logger.warning("get_video_info called with empty URL")
        return jsonify({"error": "URL is required"}), 400
    
    if not is_valid_youtube_url(url):
        logger.warning(f"Invalid YouTube URL rejected: {url}")
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    logger.info(f"Fetching video info | URL: {url} | IP: {request.remote_addr}")
    
    try:
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--no-warnings',
            '--no-check-certificates',
            '--no-playlist',
            '--extractor-retries', '3',
            '--socket-timeout', '30',
            url
        ]
        logger.debug(f"Running command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60  # Increased timeout for slow Render instances
        )
        
        if result.returncode != 0:
            stderr_output = result.stderr.strip() if result.stderr else 'No stderr output'
            stdout_output = result.stdout.strip()[:500] if result.stdout else 'No stdout output'
            logger.error(f"yt-dlp FAILED for URL: {url}")
            logger.error(f"yt-dlp exit code: {result.returncode}")
            logger.error(f"yt-dlp stderr: {stderr_output}")
            logger.error(f"yt-dlp stdout (first 500 chars): {stdout_output}")
            
            # Try to give a more specific error message
            stderr_lower = stderr_output.lower()
            if 'sign in' in stderr_lower or 'age' in stderr_lower:
                error_msg = "This video requires sign-in or age verification"
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
        
        logger.info(f"Video info SUCCESS | Title: '{title}' | Duration: {duration}s | Uploader: {uploader}")
        
        return jsonify({
            "success": True,
            "title": title,
            "duration": duration,
            "thumbnail": data.get("thumbnail", ""),
            "uploader": uploader
        })
    
    except subprocess.TimeoutExpired:
        logger.error(f"TIMEOUT fetching video info after 60s | URL: {url}")
        return jsonify({"error": "Request timeout. The server is slow — please try again."}), 408
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse yt-dlp JSON output | URL: {url} | Error: {e}")
        logger.error(f"Raw stdout (first 500 chars): {result.stdout[:500] if result.stdout else 'empty'}")
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
    
    logger.info(f"start-trim request | URL: {url} | Range: {start_time}s-{end_time}s | Quality: {quality} | File: {filename} | IP: {request.remote_addr}")
    
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
            logger.info(f"Task {task_id}: Background thread started")
            cmd = [
                'yt-dlp',
                '-f', quality_map.get(quality, quality_map['best']),
                '--download-sections', f'*{start_time}-{end_time}',
                '--concurrent-fragments', '16',
                '--fragment-retries', '5',
                '--retries', '5',
                '--socket-timeout', '30',
                '--buffer-size', '16K',
                '--no-warnings',
                '--no-playlist',
                '--no-check-certificates',
                '--newline',  # Progress on separate lines for real-time parsing
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
            
            logger.info(f"Task {task_id}: Executing yt-dlp command: {' '.join(cmd)}")
            
            with tasks_lock:
                tasks[task_id]['status'] = 'downloading'
                tasks[task_id]['phase'] = 'Downloading...'
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if not line:
                    continue
                
                # Parse yt-dlp progress output
                # Pattern for --progress-template output
                if '|' in line and '%' in line:
                    parts = line.split('|')
                    if len(parts) >= 5:
                        try:
                            pct_str = parts[0].strip().replace('%', '')
                            pct = float(pct_str)
                            with tasks_lock:
                                tasks[task_id]['progress'] = min(pct, 100)
                                tasks[task_id]['speed'] = parts[1].strip() if parts[1].strip() != 'NA' else ''
                                tasks[task_id]['eta'] = parts[2].strip() if parts[2].strip() != 'NA' else ''
                                tasks[task_id]['size'] = parts[3].strip() if parts[3].strip() != 'NA' else ''
                                tasks[task_id]['downloaded'] = parts[4].strip() if parts[4].strip() != 'NA' else ''
                        except (ValueError, IndexError):
                            pass
                
                # Fallback: parse standard yt-dlp progress lines
                elif '[download]' in line and '%' in line:
                    match = re.search(r'(\d+\.?\d*)%', line)
                    if match:
                        pct = float(match.group(1))
                        with tasks_lock:
                            tasks[task_id]['progress'] = min(pct, 100)
                    
                    speed_match = re.search(r'at\s+(\S+/s)', line)
                    if speed_match:
                        with tasks_lock:
                            tasks[task_id]['speed'] = speed_match.group(1)
                    
                    eta_match = re.search(r'ETA\s+(\S+)', line)
                    if eta_match:
                        with tasks_lock:
                            tasks[task_id]['eta'] = eta_match.group(1)
                    
                    size_match = re.search(r'of\s+~?\s*(\S+)', line)
                    if size_match:
                        with tasks_lock:
                            tasks[task_id]['size'] = size_match.group(1)
                
                # Detect merging/postprocessing phase
                elif '[Merger]' in line or '[ExtractAudio]' in line or '[ffmpeg]' in line:
                    with tasks_lock:
                        tasks[task_id]['phase'] = 'Merging & processing...'
                        tasks[task_id]['progress'] = 95
                
                logger.debug(f"Task {task_id} yt-dlp: {line}")
            
            process.wait()
            
            logger.info(f"Task {task_id}: yt-dlp process exited with code {process.returncode}")
            
            if process.returncode != 0:
                logger.error(f"Task {task_id}: yt-dlp FAILED with exit code {process.returncode}")
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
            logger.info(f"Task {task_id}: File ready. Size: {file_size / (1024*1024):.2f} MB")
            
            with tasks_lock:
                tasks[task_id]['status'] = 'done'
                tasks[task_id]['progress'] = 100
                tasks[task_id]['phase'] = 'Complete!'
                tasks[task_id]['file_path'] = actual_file
                tasks[task_id]['file_name'] = dl_name
                tasks[task_id]['mimetype'] = mimetype
                tasks[task_id]['file_size'] = file_size
        
        except Exception as e:
            logger.error(f"Task {task_id} EXCEPTION: {type(e).__name__}: {e}")
            logger.error(f"Task {task_id} traceback:\n{traceback.format_exc()}")
            with tasks_lock:
                tasks[task_id]['status'] = 'error'
                tasks[task_id]['error'] = str(e)
    
    # Start background thread
    thread = threading.Thread(target=run_ytdlp, daemon=True)
    thread.start()
    logger.info(f"Task {task_id}: Background download thread started")
    
    return jsonify({"task_id": task_id})


@app.route('/api/progress/<task_id>')
def progress(task_id):
    """SSE endpoint for real-time progress updates"""
    logger.info(f"SSE progress stream opened for task {task_id}")
    def generate():
        while True:
            with tasks_lock:
                task = tasks.get(task_id)
            
            if not task:
                logger.warning(f"SSE: Task {task_id} not found in task store")
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
                logger.info(f"SSE: Task {task_id} completed | File: {event_data['file_name']} | Size: {event_data['file_size']} bytes")
                yield f"data: {json.dumps(event_data)}\n\n"
                break
            
            if task['status'] == 'error':
                event_data['error'] = task.get('error', 'Unknown error')
                logger.error(f"SSE: Task {task_id} failed | Error: {event_data['error']}")
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
    logger.info(f"Download requested for task {task_id} | IP: {request.remote_addr}")
    
    with tasks_lock:
        task = tasks.get(task_id)
    
    if not task:
        logger.warning(f"Download failed: Task {task_id} not found")
        return jsonify({"error": "Task not found"}), 404
    
    if task['status'] != 'done':
        logger.warning(f"Download failed: Task {task_id} not ready (status: {task['status']})")
        return jsonify({"error": "File not ready"}), 400
    
    file_path = task['file_path']
    if not file_path or not os.path.exists(file_path):
        logger.error(f"Download failed: File not found at {file_path} for task {task_id}")
        return jsonify({"error": "File not found"}), 404
    
    file_size = os.path.getsize(file_path)
    logger.info(f"Serving download | Task: {task_id} | File: {task['file_name']} | Size: {file_size / (1024*1024):.2f} MB | Mime: {task['mimetype']}")
    
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
            
            cmd = [
                'yt-dlp',
                '-f', quality_map.get(quality, quality_map['best']),
                '--download-sections', f'*{start_time}-{end_time}',
                '--concurrent-fragments', '16',
                '--fragment-retries', '5',
                '--retries', '5',
                '--socket-timeout', '30',
                '--buffer-size', '16K',
                '--no-warnings',
                '--no-playlist',
                '--no-check-certificates',
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
        "disk_free_mb": round(disk_free_mb, 1),
        "active_tasks": active_tasks,
        "temp_dir": TEMP_DIR,
        "timestamp": datetime.now().isoformat()
    }
    
    logger.info(f"Health check | Status: {status} | yt-dlp: {ytdlp_version} | Disk free: {disk_free_mb:.0f} MB | Active tasks: {active_tasks}")
    
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
