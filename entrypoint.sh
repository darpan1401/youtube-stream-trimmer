#!/bin/bash
# Entrypoint script: updates yt-dlp + PO token provider to latest version at container start
# This is CRITICAL because YouTube changes frequently and old yt-dlp versions break

echo "=== Container starting ==="
echo "Updating yt-dlp and PO token provider to latest..."
pip install --root-user-action=ignore --upgrade --no-cache-dir yt-dlp bgutil-ytdlp-pot-provider 2>&1 | tail -2

echo "yt-dlp version: $(yt-dlp --version 2>/dev/null || echo 'FAILED')"
echo "Node.js version: $(node --version 2>/dev/null || echo 'NOT FOUND')"
echo "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1 || echo 'NOT FOUND')"

# Verify PO token provider is installed
python -c "import bgutil_ytdlp_pot_provider; print('PO Token Provider: OK')" 2>/dev/null || echo "WARNING: PO Token Provider not installed"

echo "=== Starting gunicorn ==="

exec gunicorn --bind 0.0.0.0:2000 --workers 2 --threads 4 --timeout 600 --access-logfile - --error-logfile - wsgi:app
