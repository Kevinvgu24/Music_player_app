FROM python:3.11-slim

# Install ffmpeg for embedded artwork extraction
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask

# Copy server code
COPY server.py .

# Expose server port
EXPOSE 8000

# Mount point for music files
VOLUME ["/music"]

# Run flask server
CMD ["python", "server.py"]
