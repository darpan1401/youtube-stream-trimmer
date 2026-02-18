# Quick Start Guide

Get YouTube Trimmer Pro running in 2 minutes!

## For Beginners (Windows/Mac/Linux)

### Step 1: Prepare Environment
Download and install Python 3.8+ from: https://www.python.org/downloads

### Step 2: Open Terminal/Command Prompt
Navigate to your project folder:
```bash
cd /path/to/codeee
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Run the App
```bash
python app_new.py
```

### Step 5: Open in Browser
Go to: **http://localhost:5000**

Done! Start trimming videos. 🎉

---

## For Developers (Virtual Environment)

### Setup

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app_new.py
```

### Deactivate Environment
```bash
deactivate
```

---

## Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for hosting on free platforms like Render.com

---

## Common Issues

**Issue**: Port 5000 already in use
```bash
PORT=8000 python app_new.py
```

**Issue**: yt-dlp not found
```bash
pip install --upgrade yt-dlp
```

**Issue**: Permission denied (Mac/Linux)
```bash
pip install --user -r requirements.txt
```

---

## What You Can Do

1. **Paste YouTube URL** → App loads video info
2. **Select Quality** → Best, 1080p, 720p, 480p, or Audio
3. **Choose Trim Range** → Use sliders or type seconds
4. **Trim & Download** → Get your edited video

---

## Features Explained

### Dual-Range Slider
- Left slider = Start time
- Right slider = End time
- Or: Type exact seconds in input fields
- Minimum duration: 1 second

### Quality Options
- **Best**: Highest quality + audio
- **1080p, 720p, 480p**: Video quality in pixels
- **Audio Only**: Extract just the audio track

### Live Previews
- Total duration shown
- Trim range displayed
- Download progress tracked

---

## Tips & Tricks

1. **Keyboard Enter**: Load video faster after pasting URL
2. **Live Streams**: Can trim up to current playback time
3. **Long Videos**: Use lower quality for faster processing
4. **Short Clips**: Use 720p or 480p for quick downloads
5. **Only Audio**: Audio-only format is smallest file size

---

## File Locations

- **Main App**: `app_new.py`
- **Web Page**: `templates/index.html`
- **Styling**: `static/style.css`
- **Interactivity**: `static/script.js`
- **Config**: `requirements.txt`, `.env`

---

## Need Help?

1. Check [README.md](README.md) for detailed info
2. Check [DEPLOYMENT.md](DEPLOYMENT.md) for hosting
3. See section "Troubleshooting" in README.md

Ready to go! Happy trimming! 🚀
