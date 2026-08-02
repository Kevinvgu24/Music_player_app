from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "Playlist Offline"
DEFAULT_LIBRARY = Path.home() / "Music" / "Nhac_Viet"
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".opus", ".mp4"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
COVER_HINTS = ("cover", "folder", "front", "album", "art", "thumbnail", "thumb")

def _get_cover_cache_path() -> Path:
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "playlist_offline" / ".cover_cache"
        return Path.home() / "AppData" / "Local" / "playlist_offline" / ".cover_cache"
    return Path.home() / ".local" / "share" / "playlist_offline" / ".cover_cache"

COVER_CACHE = _get_cover_cache_path()

# Set to server URL to enable streaming mode, e.g. "http://192.168.1.50:8000"
# Set to None or empty string to use local library offline
SERVER_URL = "http://192.168.1.245:8000"

