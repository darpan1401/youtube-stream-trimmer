import streamlit as st
import subprocess, json, os
from datetime import datetime
import tempfile
import time
import logging
import traceback

# ---------------- LOGGING CONFIG ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("YT-TRIMMER")

logger.info("Application booted")

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

# ---------------- STATE ----------------
st.session_state.setdefault("video_loaded", False)
st.session_state.setdefault("output_bytes", None)
st.session_state.setdefault("file_name", None)

# ---------------- HEADER ----------------
st.markdown("## 🎬 YouTube Stream Trimmer Pro")
st.markdown("###### Clean • Accurate • Stream-Friendly")

# ---------------- URL INPUT ----------------
url = st.text_input(
    "YouTube Video / Live Stream URL",
    placeholder="Paste YouTube link here"
)

# ---------------- LOAD VIDEO ----------------
if st.button("LOAD VIDEO", width="stretch"):
    logger.info("LOAD VIDEO clicked")

    if not url:
        logger.warning("No URL provided")
        st.error("Please paste a YouTube URL.")
    else:
        with st.spinner("Fetching video information..."):
            try:
                data = json.loads(
                    subprocess.check_output(
                        ["yt-dlp", "--dump-json", url],
                        stderr=subprocess.PIPE
                    )
                )
                st.session_state.video_loaded = True
                st.session_state.duration = int(data["duration"])
                st.session_state.title = data.get("title", "Unknown")
                st.session_state.thumbnail = data.get("thumbnail")

                logger.info(
                    f"Video loaded | Title='{st.session_state.title}' "
                    f"| Duration={st.session_state.duration}s"
                )

            except Exception:
                logger.error(traceback.format_exc())
                st.error("Failed to load video.")

# ---------------- MAIN UI ----------------
if st.session_state.video_loaded:
    logger.info("Rendering main UI")

    st.markdown("---")
    col1, col2 = st.columns([1, 3])

    with col1:
        st.image(st.session_state.thumbnail, width="stretch")

    with col2:
        st.markdown(f"### {st.session_state.title}")
        st.markdown(f"**Total Duration:** `{seconds_to_hms(st.session_state.duration)}`")

    st.markdown("### 🎚 Quality")
    quality = st.selectbox(
        "Choose download quality",
        ["Best Available", "1080p", "720p", "480p", "Audio Only"]
    )

    quality_map = {
        "Best Available": "bestvideo+bestaudio/best",
        "1080p": "bestvideo[height<=1080]+bestaudio/best",
        "720p": "bestvideo[height<=720]+bestaudio/best",
        "480p": "bestvideo[height<=480]+bestaudio/best",
        "Audio Only": "bestaudio"
    }

    st.markdown("## ✂ Trim Timeline")
    start_sec, end_sec = st.slider(
        "Trim Range",
        0,
        st.session_state.duration,
        (0, st.session_state.duration),
        step=1,
        label_visibility="collapsed"
    )

    trim_duration = end_sec - start_sec

    c1, c2, c3 = st.columns(3)
    c1.metric("Start", seconds_to_hms(start_sec))
    c2.metric("End", seconds_to_hms(end_sec))
    c3.metric("Duration", seconds_to_hms(trim_duration))

    st.markdown("### ▶ Preview (Trim Start)")
    st.video(url, start_time=start_sec)

    output_name = st.text_input(
        "Output File Name",
        value=f"youtube_trim_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

# ---------------- SINGLE ACTION BUTTON ----------------
if st.button("⬇ TRIM & DOWNLOAD", type="primary", width="stretch"):
    logger.info("TRIM & DOWNLOAD clicked")

    if trim_duration <= 0:
        st.error("End time must be greater than start time.")
    else:
        with st.spinner("Fast trimming in progress..."):
            try:
                t0 = time.time()
                with tempfile.TemporaryDirectory() as tmpdir:

                    full_video_path = os.path.join(tmpdir, "full_video.mp4")
                    output_path = os.path.join(tmpdir, f"{output_name}.mp4")

                    logger.info("Downloading full video")

                    # STEP 1: Download full video
                    subprocess.run(
                        [
                            "yt-dlp",
                            "-f", quality_map[quality],
                            "--merge-output-format", "mp4",
                            "-o", full_video_path,
                            url
                        ],
                        check=True
                    )

                    logger.info("Trimming video using ffmpeg")

                    # STEP 2: Trim using ffmpeg (fast copy mode)
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-ss", str(start_sec),
                            "-to", str(end_sec),
                            "-i", full_video_path,
                            "-c", "copy",
                            "-avoid_negative_ts", "1",
                            output_path
                        ],
                        check=True
                    )

                    with open(output_path, "rb") as f:
                        st.session_state.output_bytes = f.read()
                        st.session_state.file_name = f"{output_name}.mp4"

                logger.info(
                    f"Trim ready | Size={len(st.session_state.output_bytes)} bytes "
                    f"| Time taken={round(time.time()-t0,2)}s"
                )

            except subprocess.CalledProcessError as e:
                logger.error(traceback.format_exc())
                st.error("Processing failed.")
                if e.stderr:
                    st.error(e.stderr)

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

logger.info("App render cycle completed")
