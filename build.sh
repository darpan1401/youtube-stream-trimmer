#!/bin/bash
# Build script for deployment on Render.com and similar platforms

set -e  # Exit on any error

echo "=== Building YouTube Trimmer Pro ==="

# Update pip
echo "- Updating pip..."
pip install --upgrade pip

# Install Python dependencies
echo "- Installing Python packages..."
pip install -r requirements.txt

# Upgrade yt-dlp to LATEST version (critical for YouTube compatibility)
echo "- Installing/upgrading yt-dlp to latest..."
pip install --upgrade yt-dlp

# Verify installations
echo "- Verifying installations..."
python -c "import flask; print(f'Flask {flask.__version__} OK')"
yt_dlp_ver=$(yt-dlp --version 2>/dev/null || echo 'NOT FOUND')
echo "yt-dlp version: $yt_dlp_ver"
ffmpeg_ver=$(ffmpeg -version 2>/dev/null | head -1 || echo 'NOT FOUND')
echo "ffmpeg: $ffmpeg_ver"

# Compile Python files
echo "- Compiling Python files..."
python -m py_compile app_new.py wsgi.py

echo "=== Build complete ==="
echo "yt-dlp: $yt_dlp_ver"
echo "Start command: gunicorn wsgi:app"
