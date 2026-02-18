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

app = Flask(__name__)

# In-memory task store for progress tracking
tasks = {}
tasks_lock = threading.Lock()

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 2000 * 1024 * 1024  # 2GB limit
DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 2000))

# Logging setup with better formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("YT-TRIMMER")

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
            logger.error(f"Error in {f.__name__}: {traceback.format_exc()}")
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
    return render_template('index.html')

@app.route('/api/get-video-info', methods=['POST'])
@error_handler
def get_video_info():
    """Fetch video info using yt-dlp"""
    url = request.json.get('url', '').strip()
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    logger.info(f"Fetching info for: {url}")
    
    try:
        result = subprocess.run(
            ['yt-dlp', '--dump-json', '--no-warnings', url],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return jsonify({"error": "Invalid YouTube URL or video unavailable"}), 400
        
        data = json.loads(result.stdout)
        duration = int(data.get("duration", 0))
        
        if duration <= 0:
            return jsonify({"error": "Could not determine video duration"}), 400
        
        return jsonify({
            "success": True,
            "title": sanitize_filename(data.get("title", "Video")),
            "duration": duration,
            "thumbnail": data.get("thumbnail", ""),
            "uploader": data.get("uploader", "Unknown")
        })
    
    except subprocess.TimeoutExpired:
        logger.error("Timeout fetching video info")
        return jsonify({"error": "Request timeout. Try again."}), 408
    except json.JSONDecodeError:
        logger.error("Failed to parse yt-dlp output")
        return jsonify({"error": "Failed to fetch video information"}), 400
    except Exception as e:
        logger.error(f"Error fetching video: {str(e)}")
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
    
    # Validation
    if not url or not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    if start_time < 0 or end_time <= start_time:
        return jsonify({"error": "Invalid time parameters"}), 400
    
    if quality not in ['best', '1080', '720', '480', 'audio']:
        return jsonify({"error": "Invalid quality"}), 400
    
    is_audio = quality == 'audio'
    task_id = str(uuid.uuid4())
    
    logger.info(f"Task {task_id}: Trimming {url} [{start_time}s - {end_time}s] Quality: {quality}")
    
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
        }
    
    def run_ytdlp():
        try:
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
            
            if process.returncode != 0:
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
            logger.error(f"Task {task_id} error: {traceback.format_exc()}")
            with tasks_lock:
                tasks[task_id]['status'] = 'error'
                tasks[task_id]['error'] = str(e)
    
    # Start background thread
    thread = threading.Thread(target=run_ytdlp, daemon=True)
    thread.start()
    
    return jsonify({"task_id": task_id})


@app.route('/api/progress/<task_id>')
def progress(task_id):
    """SSE endpoint for real-time progress updates"""
    def generate():
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
                yield f"data: {json.dumps(event_data)}\n\n"
                break
            
            if task['status'] == 'error':
                event_data['error'] = task.get('error', 'Unknown error')
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
    with tasks_lock:
        task = tasks.get(task_id)
    
    if not task:
        return jsonify({"error": "Task not found"}), 404
    
    if task['status'] != 'done':
        return jsonify({"error": "File not ready"}), 400
    
    file_path = task['file_path']
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    
    return send_file(
        file_path,
        mimetype=task['mimetype'],
        as_attachment=True,
        download_name=task['file_name']
    )


@app.route('/api/cleanup/<task_id>', methods=['POST'])
def cleanup_task(task_id):
    """Clean up task files after download"""
    with tasks_lock:
        task = tasks.pop(task_id, None)
    
    if task and task.get('tmpdir') and os.path.exists(task['tmpdir']):
        try:
            shutil.rmtree(task['tmpdir'])
            logger.info(f"Cleaned up task {task_id}")
        except Exception:
            pass
    
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
    
    logger.info(f"Trimming video: {url} [{start_time}s - {end_time}s] Quality: {quality}")
    
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
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                error_msg = result.stderr.lower()
                if 'not available' in error_msg or 'unavailable' in error_msg:
                    return jsonify({"error": "Video not available in your region"}), 400
                logger.error(f"yt-dlp error: {result.stderr}")
                return jsonify({"error": "Failed to trim video. Check video availability."}), 400
            
            # yt-dlp may change the extension, find the actual output file
            actual_file = None
            for f in os.listdir(tmpdir):
                if f.startswith(filename):
                    actual_file = os.path.join(tmpdir, f)
                    break
            
            if not actual_file or not os.path.exists(actual_file):
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
        logger.error("Processing timeout")
        return jsonify({"error": "Processing timeout. Try smaller duration or lower quality."}), 408
    except Exception as e:
        logger.error(f"Trim video error: {str(e)}")
        return jsonify({"error": "Failed to process video"}), 500

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    logger.info("Starting YouTube Trimmer App")
    logger.info(f"Configuration - Debug: {DEBUG}, Host: {HOST}, Port: {PORT}")
    app.run(debug=DEBUG, host=HOST, port=PORT)
