import streamlit as st
import subprocess
import json
import os
from datetime import datetime
import tempfile
import time
import logging
import traceback
import sys
import requests

# ---------------- LOGGING CONFIG ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("YT-TRIMMER")

logger.info("Application booted")

# ---------------- UPGRADE YT-DLP ----------------
try:
    logger.info("Upgrading yt-dlp to latest version...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
        check=True,
        capture_output=True,
        text=True
    )
    logger.info("yt-dlp upgraded successfully")
except Exception as e:
    logger.warning(f"Failed to upgrade yt-dlp: {e}")

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="YouTube Stream Trimmer Pro",
    page_icon="🎬",
    layout="centered"
)

# ---------------- CUSTOM CSS ----------------
st.markdown("""
<style>
body { background-color:#0f1117; }
.block-container { max-width:950px; padding-top:2rem; }
h1,h2,h3,h4,h5,p,label { color:#eaeaea !important; }
input, select { background:#1c1f26 !important; color:white !important; }
.stSlider > div { padding-top:1rem; }
button[kind="primary"] {
    background: linear-gradient(90deg,#ff416c,#ff4b2b);
    color:white;
    font-weight:600;
    border-radius:12px;
    height:3.2rem;
}
footer { visibility:hidden; }
.metric-box {
    background:#1c1f26;
    padding:1rem;
    border-radius:12px;
    text-align:center;
}
</style>
""", unsafe_allow_html=True)

# ---------------- UTILS ----------------
def seconds_to_hms(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02}:{m:02}:{s:02}"

def get_ytdlp_version():
    """Check yt-dlp version"""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except:
        return "Unknown"

def download_video_with_retry(url, output_path, quality_format):
    """Video download karne ka improved function with multiple fallback options"""
    
    # Different strategies to try
    strategies = [
        # Strategy 1: Android client (most reliable for cloud)
        {
            "extractor_args": "youtube:player_client=android",
            "user_agent": "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36",
            "extra_args": []
        },
        # Strategy 2: iOS client
        {
            "extractor_args": "youtube:player_client=ios",
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
            "extra_args": []
        },
        # Strategy 3: Web client with cookies
        {
            "extractor_args": "youtube:player_client=web",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "extra_args": ["--cookies-from-browser", "chrome"]
        }
    ]
    
    for idx, strategy in enumerate(strategies, 1):
        try:
            logger.info(f"Trying download strategy {idx}...")
            
            cmd = [
                "yt-dlp",
                "--no-check-certificate",
                "--no-warnings",
                "--extractor-args", strategy["extractor_args"],
                "--user-agent", strategy["user_agent"],
                "--add-header", "Accept:application/json",
                "--add-header", "Accept-Language:en-US,en;q=0.9",
                "--add-header", "Origin:https://www.youtube.com",
                "-f", quality_format,
                "--merge-output-format", "mp4",
                "-o", output_path,
                "--verbose",  # Debug ke liye
                url
            ]
            
            # Add extra args if any
            cmd.extend(strategy["extra_args"])
            
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            logger.info(f"Strategy {idx} successful!")
            return True, None
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Strategy {idx} timeout")
            continue
        except subprocess.CalledProcessError as e:
            logger.warning(f"Strategy {idx} failed: {e.stderr[:200] if e.stderr else 'No error'}")
            continue
        except Exception as e:
            logger.warning(f"Strategy {idx} exception: {str(e)}")
            continue
    
    return False, "All download strategies failed"

def get_video_info_fallback(url):
    """Alternative method to get video info if yt-dlp fails"""
    try:
        # Try using youtube-dl as fallback
        result = subprocess.run(
            ["youtube-dl", "--dump-json", url],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except:
        pass
    
    # Try using requests directly for basic info
    try:
        import requests
        from bs4 import BeautifulSoup
        
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        if response.status_code == 200:
            # Extract basic info from page
            soup = BeautifulSoup(response.text, 'html.parser')
            title_tag = soup.find('meta', property='og:title')
            title = title_tag['content'] if title_tag else "Unknown"
            return {"title": title, "duration": 0, "thumbnail": None}
    except:
        pass
    
    return None

# ---------------- STATE ----------------
st.session_state.setdefault("video_loaded", False)
st.session_state.setdefault("output_bytes", None)
st.session_state.setdefault("file_name", None)
st.session_state.setdefault("ytdlp_version", get_ytdlp_version())
st.session_state.setdefault("download_strategy", 0)

# ---------------- HEADER ----------------
st.markdown("## 🎬 YouTube Stream Trimmer Pro")
st.markdown("###### Clean • Accurate • Stream-Friendly")

# Show yt-dlp version
st.caption(f"📦 yt-dlp version: {st.session_state.ytdlp_version}")

# ---------------- URL INPUT ----------------
url = st.text_input(
    "YouTube Video / Live Stream URL",
    placeholder="Paste YouTube link here",
    key="url_input"
)

# ---------------- LOAD VIDEO ----------------
if st.button("🚀 LOAD VIDEO", width="stretch", type="primary"):
    logger.info("LOAD VIDEO clicked")
    
    if not url:
        logger.warning("No URL provided")
        st.error("Please paste a YouTube URL.")
    else:
        with st.spinner("Fetching video information... (This may take a few seconds)"):
            try:
                # Try multiple formats for yt-dlp
                formats_to_try = [
                    ["yt-dlp", "--dump-json", "--extractor-args", "youtube:player_client=android", url],
                    ["yt-dlp", "--dump-json", "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", url],
                    ["yt-dlp", "--dump-json", "--no-check-certificate", url],
                    ["youtube-dl", "--dump-json", url]  # Fallback to youtube-dl
                ]
                
                data = None
                for cmd in formats_to_try:
                    try:
                        logger.info(f"Trying: {' '.join(cmd)}")
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=30
                        )
                        if result.returncode == 0 and result.stdout:
                            data = json.loads(result.stdout)
                            logger.info("Successfully fetched video info")
                            break
                    except:
                        continue
                
                if not data:
                    # Try fallback method
                    data = get_video_info_fallback(url)
                
                if data:
                    st.session_state.video_loaded = True
                    st.session_state.duration = int(data.get("duration", 0))
                    st.session_state.title = data.get("title", "Unknown Title")
                    st.session_state.thumbnail = data.get("thumbnail")
                    
                    if st.session_state.duration == 0:
                        st.warning("⚠️ Could not fetch exact duration. You can still try trimming.")
                        st.session_state.duration = 3600  # Default 1 hour
                    
                    logger.info(f"Video loaded | Title='{st.session_state.title}' | Duration={st.session_state.duration}s")
                    st.success("✅ Video loaded successfully!")
                else:
                    st.error("Failed to load video. YouTube might be blocking this server.")
                    st.info("💡 Try these solutions:\n"
                           "1. Wait a few minutes and try again\n"
                           "2. Try a different YouTube video\n"
                           "3. Use a VPN if possible\n"
                           "4. Run this app locally instead of cloud")
                    
            except Exception as e:
                logger.error(traceback.format_exc())
                st.error(f"Failed to load video: {str(e)[:100]}")

# ---------------- MAIN UI ----------------
if st.session_state.video_loaded:
    logger.info("Rendering main UI")
    
    st.markdown("---")
    col1, col2 = st.columns([1, 3])
    
    with col1:
        if st.session_state.thumbnail:
            st.image(st.session_state.thumbnail, width="stretch")
        else:
            st.markdown("🎬")
    
    with col2:
        st.markdown(f"### {st.session_state.title[:50]}...")
        if st.session_state.duration > 0:
            st.markdown(f"**Total Duration:** `{seconds_to_hms(st.session_state.duration)}`")
        else:
            st.markdown("**Duration:** `Unknown`")
    
    st.markdown("### 🎚 Quality")
    quality = st.selectbox(
        "Choose download quality (lower quality = more likely to work)",
        ["Audio Only", "480p", "720p", "1080p", "Best Available"],
        index=1  # Default to 480p for better success rate
    )
    
    quality_map = {
        "Best Available": "bestvideo+bestaudio/best",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "Audio Only": "bestaudio"
    }
    
    st.markdown("## ✂ Trim Timeline")
    
    # Duration slider with fallback
    max_duration = max(1, st.session_state.duration) if st.session_state.duration > 0 else 600
    
    start_sec, end_sec = st.slider(
        "Trim Range",
        0,
        max_duration,
        (0, min(60, max_duration)),
        step=1,
        label_visibility="collapsed"
    )
    
    trim_duration = end_sec - start_sec
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Start", seconds_to_hms(start_sec))
    c2.metric("End", seconds_to_hms(end_sec))
    c3.metric("Duration", seconds_to_hms(trim_duration))
    
    if st.session_state.duration > 0:
        st.markdown("### ▶ Preview (Trim Start)")
        try:
            st.video(url, start_time=start_sec)
        except:
            st.info("Preview not available for this video format")
    
    output_name = st.text_input(
        "Output File Name",
        value=f"youtube_trim_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

# ---------------- TRIM & DOWNLOAD BUTTON ----------------
if st.session_state.get("video_loaded", False):
    if st.button("⬇ TRIM & DOWNLOAD", type="primary", width="stretch"):
        logger.info("TRIM & DOWNLOAD clicked")
        
        if trim_duration <= 0:
            st.error("End time must be greater than start time.")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                t0 = time.time()
                
                with tempfile.TemporaryDirectory() as tmpdir:
                    status_text.text("📥 Downloading video...")
                    progress_bar.progress(20)
                    
                    full_video_path = os.path.join(tmpdir, "full_video.mp4")
                    output_path = os.path.join(tmpdir, f"{output_name}.mp4")
                    
                    logger.info("Downloading full video")
                    
                    # STEP 1: Download with retry logic
                    success, error_msg = download_video_with_retry(
                        url, 
                        full_video_path, 
                        quality_map[quality]
                    )
                    
                    if not success:
                        st.error("❌ Failed to download video. YouTube is blocking this server.")
                        st.info("💡 Solutions:\n"
                               "1. Try 'Audio Only' quality\n"
                               "2. Try a shorter video\n"
                               "3. Try a different YouTube video\n"
                               "4. Run this app locally instead of cloud")
                        logger.error("All download strategies failed")
                        st.stop()
                    
                    if os.path.getsize(full_video_path) == 0:
                        st.error("Downloaded file is empty")
                        st.stop()
                    
                    status_text.text("✂ Trimming video...")
                    progress_bar.progress(60)
                    
                    logger.info("Trimming video using ffmpeg")
                    
                    # STEP 2: Trim using ffmpeg
                    trim_cmd = [
                        "ffmpeg",
                        "-ss", str(start_sec),
                        "-i", full_video_path,
                        "-t", str(trim_duration),
                        "-c", "copy" if quality != "Audio Only" else "copy",
                        "-avoid_negative_ts", "1",
                        "-y",
                        output_path
                    ]
                    
                    try:
                        subprocess.run(
                            trim_cmd,
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=120
                        )
                    except subprocess.TimeoutExpired:
                        st.error("Trimming took too long")
                        st.stop()
                    except subprocess.CalledProcessError as e:
                        logger.error(f"FFmpeg error: {e.stderr}")
                        st.error("Failed to trim video")
                        st.stop()
                    
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        with open(output_path, "rb") as f:
                            st.session_state.output_bytes = f.read()
                            st.session_state.file_name = f"{output_name}.mp4"
                        
                        progress_bar.progress(100)
                        status_text.text("✅ Complete!")
                        
                        logger.info(f"Trim ready | Size={len(st.session_state.output_bytes)} bytes | Time taken={round(time.time()-t0,2)}s")
                    else:
                        st.error("Output file not created")
                
            except Exception as e:
                logger.error(traceback.format_exc())
                st.error(f"Processing failed: {str(e)[:100]}")
                progress_bar.empty()
                status_text.empty()

        if st.session_state.output_bytes:
            st.download_button(
                "⬇ Download Trimmed Video",
                data=st.session_state.output_bytes,
                file_name=st.session_state.file_name,
                mime="video/mp4",
                width="stretch"
            )

# ---------------- FOOTER ----------------
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#777;'>Developed by <b>Darpan</b> 🚀</p>",
    unsafe_allow_html=True
)

# ---------------- TIPS ----------------
with st.expander("💡 Tips for Cloud Deployment"):
    st.markdown("""
    **Why am I getting 403 Forbidden error?**
    - YouTube blocks cloud IP addresses
    - Streamlit Cloud IPs are often blacklisted
    
    **Solutions:**
    1. **Try 'Audio Only' mode** - More likely to work
    2. **Use 480p or lower quality** - Better success rate
    3. **Try different videos** - Some work, some don't
    4. **Short videos** - Under 5 minutes work better
    5. **Local deployment** - Run this app on your computer for guaranteed success
    
    **To run locally:**
    ```
    pip install streamlit yt-dlp
    streamlit run app.py
    ```
    """)

logger.info("App render cycle completed")