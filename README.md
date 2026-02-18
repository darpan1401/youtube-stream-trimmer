# YouTube Video Trimmer Pro

A powerful, fast, and beautiful web application to trim and download YouTube videos.

## Features

- **One-Click Trimming**: Easily specify start and end times
- **Multiple Quality Options**: Choose from Best, 1080p, 720p, 480p, or Audio Only
- **Live Preview**: See your trim range before downloading
- **Fast Processing**: Optimized backend with concurrent fragment downloads
- **Beautiful UI**: Modern, responsive design with smooth animations
- **No Watermarks**: Clean video downloads
- **Production Ready**: Secure, scalable, and well-tested

## Prerequisites

- Python 3.8 or higher
- yt-dlp (will be installed via pip)

## Installation & Setup

## Installation & Setup

### Step 1: Clone/Download the Project
```bash
git clone <repository-url>
cd codeee
```

### Step 2: Create Virtual Environment (Recommended)
```bash
# On Linux/Mac
python3 -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Run Locally
```bash
python app_new.py
```
Visit: **http://localhost:5000**

## Production Deployment

### Option 1: Deploy to Render (Free)

1. **Push code to GitHub**
2. **Connect to Render**: https://render.com
   - Create New Web Service
   - Connect your GitHub repo
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn wsgi:app`
   - Set environment: `FLASK_ENV=production, PORT=5000`
3. **Add yt-dlp to PATH**:
   - In Render dashboard, add build script to install yt-dlp system-wide
   - Create `build.sh`:
   ```bash
   #!/bin/bash
   pip install -r requirements.txt
   pip install yt-dlp --upgrade
   ```

### Option 2: Deploy to Replit (Free)

1. **Create Replit account**: https://replit.com
2. **Import from GitHub** or create new Python project
3. **Install dependencies**: `pip install -r requirements.txt`
4. **Run**: `python app_new.py`
5. **Share**: Replit provides a public URL

### Option 3: Deploy to PythonAnywhere (Free tier available)

1. **Sign up**: https://www.pythonanywhere.com
2. **Upload files** to your account
3. **Create new web app** → Flask
4. **Configure WSGI file** to point to `wsgi.py`
5. **Install packages** in web app settings

### Option 4: Local Server with Gunicorn

```bash
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
```

## Usage

## Usage

1. **Open the app** in your browser
2. **Paste a YouTube URL** - works with videos and live streams
3. **Click Load Video** - the app fetches video info
4. **Select video quality** - Best, 1080p, 720p, 480p, or Audio Only
5. **Choose trim range** - use sliders or enter precise seconds
   - **Start time**: Set where the trim begins (in seconds)
   - **End time**: Set where the trim ends (in seconds)
   - **Duration**: Minimum 1 second
6. **Click Trim & Download** - process and download

### Tips for Using Sliders
- **Drag sliders** on the timeline to select range
- **Or type numbers** in the "Start (sec)" and "End (sec)" fields
- **Minimum duration**: 1 second between start and end
- **End time**: Cannot exceed video duration
- **Live streams**: Can be trimmed up to current playback position

## Keyboard Shortcuts

- **Enter key**: Load video after pasting URL
- **Tab key**: Navigate between input fields

## File Structure

```
codeee/
├── app_new.py           # Main Flask application
├── wsgi.py              # WSGI entry point for production
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variables template
├── README.md            # This file
├── templates/
│   └── index.html      # Main HTML page
└── static/
    ├── style.css       # CSS styling
    └── script.js       # JavaScript logic
```

## How It Works

### Backend (Python/Flask)
- REST API endpoints for video fetching and trimming
- Uses yt-dlp for downloading and metadata extraction
- Efficient binary section downloads for trimming
- Proper error handling and request validation
- Production-ready logging

### Frontend (HTML/CSS/JavaScript)
- Modern, responsive user interface
- Real-time slider controls for time selection
- Dual-range slider for start/end time
- Quality selection with visual indicators
- Download progress tracking
- Font Awesome icons for professional appearance

## Supported Platforms

- YouTube Videos
- YouTube Live Streams
- YouTube Shorts
- All qualities available on YouTube (subject to regional restrictions)

## Quality Options

| Option | Description |
|--------|-------------|
| Best | Highest available quality (video + audio combined) |
| 1080p | Full HD (1920 × 1080) |
| 720p | HD (1280 × 720) |
| 480p | Standard Definition (854 × 480) |
| Audio Only | Extract audio track as MP4 |

## Troubleshooting 🔧

### "Invalid YouTube URL" error
- Make sure the URL is a valid YouTube link
- Check if the video is publicly available
- Try a different video

### Download takes too long
- Choose lower quality
- Reduce trim duration
- Check your internet connection

### 500 Error on download
- Ensure video is still available
- Try with different quality
- Check available disk space

## Performance Tips ⚡

1. Use lower quality for large trimmed sections
2. Trim to exact duration you need
3. Use keyboard shortcuts for faster workflow

## API Reference

### GET /
Returns the main web interface

### POST /api/get-video-info
Fetches video information.

**Request body:**
```json
{
  "url": "https://youtube.com/watch?v=..."
}
```

**Response:**
```json
{
  "success": true,
  "title": "Video Title",
  "duration": 3600,
  "thumbnail": "https://...",
  "uploader": "Channel Name"
}
```

### POST /api/trim-video
Trims and downloads video.

**Request body:**
```json
{
  "url": "https://youtube.com/watch?v=...",
  "startTime": 30.5,
  "endTime": 60.0,
  "quality": "best",
  "filename": "my_video"
}
```

**Response:** Video file (MP4)

### GET /api/health
Health check endpoint.

## Troubleshooting

### Error: "yt-dlp not found"
Install yt-dlp:
```bash
pip install -U yt-dlp
```

### Error: "Invalid YouTube URL"
- Make sure the URL is correct
- Check if the video is publicly available
- Try a different video to test

### Slider not working properly
- Try refreshing the page
- Clear browser cache
- Use exact numbers in the input fields instead of slider

### Video fails to trim
- Check if video is available in your region
- Try lower quality setting
- Ensure start time is less than end time

### Application won't start on port 5000
- Change PORT: `PORT=8000 python app_new.py`
- Or use different port in .env file

## Security & Privacy

- All processing happens on your server
- No video data sent to external services (except YouTube API)
- No user data storage or tracking
- Open source - inspect the code anytime

## Environment Variables

Create `.env` file based on `.env.example`:

```
FLASK_DEBUG=False
FLASK_ENV=production
HOST=0.0.0.0
PORT=5000
```

## Development

To contribute or modify:

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run in debug mode
FLASK_DEBUG=True python app_new.py

# Check code quality
pip install pylint flake8
pylint app_new.py
```

## Performance Tips

1. **Use appropriate quality** - Lower quality files download faster
2. **Trim shorter videos** - Less processing time
3. **Use latest yt-dlp** - Bug fixes and improvements
4. **Check internet speed** - Affects download performance

## Built With

- **Flask** - Python web framework
- **yt-dlp** - YouTube video downloader
- **Font Awesome** - Icon library
- **Modern CSS/JavaScript** - Responsive frontend

## License

Open source and free to use. Attribution appreciated.

---

**YouTube Trimmer Pro** | Created with attention to detail and care for user experience
