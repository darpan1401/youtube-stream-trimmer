#!/bin/bash
# Entrypoint for Hugging Face Spaces deployment
# Updates yt-dlp at container start, then launches gunicorn on port 7860

echo "=== HF Space starting ==="
echo "Updating yt-dlp and PO token provider to latest..."
pip install --user --upgrade --no-cache-dir yt-dlp bgutil-ytdlp-pot-provider 2>&1 | tail -2

echo "yt-dlp version: $(yt-dlp --version 2>/dev/null || echo 'FAILED')"
echo "Node.js version: $(node --version 2>/dev/null || echo 'NOT FOUND')"
echo "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1 || echo 'NOT FOUND')"

python3 -c "import bgutil_ytdlp_pot_provider; print('PO Token Provider: OK')" 2>/dev/null || echo "WARNING: PO Token Provider not installed"

echo "=== Starting gunicorn on port 7860 ==="

exec gunicorn --bind 0.0.0.0:7860 --workers 2 --threads 4 --timeout 600 --access-logfile - --error-logfile - wsgi:app
