from __future__ import annotations

from pathlib import Path


APP_NAME = "Playlist Offline"
DEFAULT_LIBRARY = Path.home() / "Music" / "Nhac_Viet"
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".opus", ".mp4"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
COVER_HINTS = ("cover", "folder", "front", "album", "art", "thumbnail", "thumb")
COVER_CACHE = Path(__file__).with_name(".cover_cache")

# Set to server URL to enable streaming mode, e.g. "http://192.168.1.50:8000"
# Set to None or empty string to use local library offline
SERVER_URL = "http://192.168.1.245:8000"

