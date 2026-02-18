#!/bin/bash
# Entrypoint script: updates yt-dlp to latest version at container start
# This is CRITICAL because YouTube changes frequently and old yt-dlp versions break

echo "=== Container starting ==="
echo "Updating yt-dlp to latest version..."
pip install --upgrade --no-cache-dir yt-dlp 2>&1 | tail -1

echo "yt-dlp version: $(yt-dlp --version 2>/dev/null || echo 'FAILED')"
echo "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1 || echo 'NOT FOUND')"
echo "=== Starting gunicorn ==="

exec gunicorn --bind 0.0.0.0:2000 --workers 2 --threads 4 --timeout 600 --access-logfile - --error-logfile - wsgi:app
