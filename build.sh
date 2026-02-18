#!/bin/bash
# Build script for deployment on Render.com and similar platforms

set -e  # Exit on any error

echo "🔨 Building YouTube Trimmer Pro..."

# Update pip
echo "- Updating pip..."
pip install --upgrade pip

# Install Python dependencies
echo "- Installing Python packages..."
pip install -r requirements.txt

# Upgrade yt-dlp to latest version
echo "- Installing/upgrading yt-dlp..."
pip install --upgrade yt-dlp

# Verify installations
echo "- Verifying installations..."
python -c "import flask; print(f'Flask {flask.__version__} ✓')"
python -c "import yt_dlp; print(f'yt-dlp found ✓')"

# Compile Python files
echo "- Compiling Python files..."
python -m py_compile app_new.py wsgi.py

echo "✅ Build complete!"
echo ""
echo "Your app is ready for production."
echo "Start command: gunicorn wsgi:app"
