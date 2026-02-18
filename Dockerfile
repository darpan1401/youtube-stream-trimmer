FROM python:3.11-slim

# Install system dependencies (ffmpeg for video processing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp

# Copy app code
COPY . .

# Expose port
EXPOSE 2000

# Use gunicorn with threading support for SSE
CMD ["gunicorn", "--bind", "0.0.0.0:2000", "--workers", "2", "--threads", "4", "--timeout", "600", "wsgi:app"]
