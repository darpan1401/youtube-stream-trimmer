FROM python:3.11-slim

# Install system dependencies (ffmpeg for video processing, Node.js for PO token generation)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --root-user-action=ignore --no-cache-dir --upgrade pip && \
    pip install --root-user-action=ignore --no-cache-dir -r requirements.txt && \
    pip install --root-user-action=ignore --no-cache-dir --upgrade yt-dlp && \
    pip install --root-user-action=ignore --no-cache-dir bgutil-ytdlp-pot-provider

# Copy app code
COPY . .

# Copy and set up entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose port
EXPOSE 2000

# Use entrypoint to update yt-dlp at container start, then launch gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]
