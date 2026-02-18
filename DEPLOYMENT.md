# Free Hosting Deployment Guide

This guide will help you deploy the YouTube Trimmer Pro application for FREE to various hosting platforms.

## Prerequisites

- GitHub account (for code hosting)
- Note: yt-dlp requires a system binary, not just Python package. Some free platforms may have limitations.

## Option 1: Render.com (Recommended - Completely FREE)

### Setup Steps:

1. **Create Render account**
   - Go to https://render.com
   - Sign up with GitHub

2. **Create Web Service**
   - Click "New +" → "Web Service"
   - Connect your GitHub repo
   - Fill in settings:
     - Name: `youtube-trimmer`
     - Region: Closest to you
     - Branch: `main`
     - Build command: `pip install -r requirements.txt && pip install yt-dlp --upgrade`
     - Start command: `gunicorn wsgi:app`
     - Instance type: Free (0.5 CPU, 512MB RAM)

3. **Set Environment Variables**
   - In Render dashboard → Environment
   - Add: `FLASK_ENV=production`

4. **Deploy**
   - Render will auto-deploy when you push to GitHub

### Cost: **$0/month** (free tier has limits)

---

## Option 2: Railway.app (FREE with $5 credit)

### Setup Steps:

1. **Create account**: https://railway.app
2. **Connect GitHub** to Railway
3. **Create new project** → Import from GitHub
4. **Add `railway.json` to your repo**:
```json
{
  "build": {
    "builder": "heroku.buildpacks"
  }
}
```

5. **Deploy** - Railway auto-deploys on push

### Cost: **$0/month** with free $5 monthly credit

---

## Option 3: Heroku (Free tier discontinued, but alternatives exist)

Use Railway or Render instead.

---

## Option 4: Replit (Very Easy)

### Setup Steps:

1. **Go to**: https://replit.com
2. **Create new project** → Import from GitHub or upload files
3. **Create `.replit` file**:
```
run = "python3 app_new.py"
```

4. **Install dependencies**: Click Shell → `pip install -r requirements.txt`
5. **Run** - Click Run button
6. **Share** - Get public URL

### Cost: **$0/month** (free tier, slower)

### Pros:
- Easiest setup
- No deployment needed
- Great for testing

### Cons:
- Slow performance
- Goes to sleep after inactivity
- 500MB storage limit

---

## Option 5: PythonAnywhere (Free tier available)

### Setup Steps:

1. **Create account**: https://pythonanywhere.com
2. **Upload files** using web interface
3. **Create Web app**:
   - Framework: Flask
   - Python: 3.9+
4. **Configure WSGI file** to use `wsgi.py`
5. **Install packages** in consoles

### Cost: **$0/month** (free tier with limitations)

### Limitations:
- Free tier slow
- Limited CPU time
- Whitelist needed for external URLs

---

## Option 6: DigitalOcean App Platform ($0-5/month)

### Setup Steps:

1. **Create DigitalOcean account**: Pay-as-you-go (very cheap)
2. **Create new App**
3. **Connect GitHub repo**
4. **Build/Run commands**:
   - Build: `pip install -r requirements.txt && pip install yt-dlp`
   - Run: `gunicorn wsgi:app`
5. **Deploy**

### Cost: **~$5/month** (or less if you use credits)

### Benefits:
- Very reliable
- Fast performance
- Good for production

---

## Option 7: Local Machine as Server (Advanced)

### For continuous running on your local machine:

```bash
# Install required packages
pip install -r requirements.txt

# Run with Gunicorn (production-ready)
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app

# Or use this for public access:
# Use ngrok for tunneling: ngrok http 5000
```

---

## Comparison Table

| Platform | Cost | Difficulty | Speed | Auto-Deploy | yt-dlp Support |
|----------|------|-----------|-------|------------|-----------------|
| Render | Free | Easy | Fast ✓ | Yes | Yes ✓ |
| Railway | Free ($5) | Easy | Fast ✓ | Yes | Yes ✓ |
| Replit | Free | Very Easy | Slow | No | Yes ✓ |
| PythonAnywhere | Free | Easy | Slow | No | Limited |
| DigitalOcean | $5+ | Easy | Fast ✓ | Yes | Yes ✓ |

---

## Recommended: Render.com Setup (Step-by-Step)

### 1. Prepare GitHub Repository

```bash
# Initialize git if not done
git init
git add .
git commit -m "Initial commit"
git push -u origin main
```

### 2. Create `build.sh` in root directory

```bash
#!/bin/bash
echo "Installing dependencies..."
pip install -r requirements.txt
echo "Upgrading yt-dlp..."
pip install --upgrade yt-dlp
echo "Build complete!"
```

### 3. Update `requirements.txt` with:

```
flask>=3.0.0
yt-dlp>=2025.12.8
gunicorn>=21.2.0
python-dotenv>=1.0.0
```

### 4. In Render Dashboard:

- **Build Command**: `bash build.sh`
- **Start Command**: `gunicorn -w 4 wsgi:app`
- **Environment**:
  - `FLASK_ENV=production`
  - `FLASK_DEBUG=False`

### 5. Deploy & Access

Your app will be live at: `https://youtube-trimmer-xxxx.onrender.com`

---

## Troubleshooting

### Error: "yt-dlp command not found"
- Make sure your `build.sh` or build command includes `pip install yt-dlp`
- Check platform documentation for system package support

### Error: "Module not found"
- Run `pip install -r requirements.txt` again
- Ensure all dependencies are listed in requirements.txt

### Slow Performance
- Use Render or DigitalOcean for better performance
- Reduce quality settings for faster processing
- Try shorter video durations

### Port Issues
- Most platforms use PORT environment variable
- Our app reads from `os.getenv('PORT', 5000)`
- Set PORT in platform's environment settings

---

## Security Tips for Production

1. Set `FLASK_DEBUG=False` always
2. Use strong SECRET_KEY if you add user auth
3. Rate limit API endpoints
4. Monitor logs for suspicious activity
5. Keep yt-dlp updated
6. Run security tests before deployment

---

## Monitoring & Logs

### Check logs:

**Render**: Dashboard → Logs
**Railway**: Dashboard → Logs
**Replit**: Console tab
**PythonAnywhere**: Web → Error log

---

## Scaling to Production (If Needed)

1. Add database (PostgreSQL, MongoDB)
2. Implement caching (Redis)
3. Add authentication if needed
4. Use CDN for static files
5. Monitor performance metrics

---

For detailed platform-specific help, visit their documentation:
- Render: https://render.com/docs
- Railway: https://docs.railway.app
- Replit: https://docs.replit.com
- PythonAnywhere: https://help.pythonanywhere.com
- DigitalOcean: https://www.digitalocean.com/docs
