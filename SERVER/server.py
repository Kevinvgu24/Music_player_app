import os
import sys
import shutil
import subprocess
import hashlib
import unicodedata
import re
import time
import threading
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort

app = Flask(__name__)

# Config
MUSIC_DIR = Path("/music")
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".opus", ".mp4"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
COVER_HINTS = ("cover", "folder", "front", "album", "art", "thumbnail", "thumb")

# Ensure music directory exists
os.makedirs(MUSIC_DIR, exist_ok=True)

SUBPROCESS_FLAGS = 0
if sys.platform == "win32":
    SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

def readable_title(path: Path) -> str:
    title = path.stem
    for suffix in (" - YouTube", " Official MV", " Official Music Video"):
        title = title.replace(suffix, "")
    return title.strip()

def search_text(value: object) -> str:
    text = str(value).casefold().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", text)
    no_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    spaced = "".join(char if char.isalnum() else " " for char in no_marks)
    return " ".join(spaced.split())

_folder_art_cache = {}

def find_folder_art(path: Path, root: Path) -> Path | None:
    current = path.parent
    if current in _folder_art_cache:
        return _folder_art_cache[current]

    art_path = None
    curr = current
    while curr == root or root in curr.parents:
        if curr in _folder_art_cache:
            art_path = _folder_art_cache[curr]
            break

        try:
            images = [item for item in curr.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS]
        except OSError:
            images = []

        if images:
            preferred = sorted(
                images,
                key=lambda item: (
                    not any(hint in search_text(item.stem) for hint in COVER_HINTS),
                    len(item.name),
                    search_text(item.name),
                ),
            )
            art_path = preferred[0]
            break
        if curr == root:
            break
        curr = curr.parent

    _folder_art_cache[current] = art_path
    return art_path

# Matches word "album" anywhere
_ALBUM_WORD_RE = re.compile(r'\balbum\b', re.IGNORECASE)
_ALBUM_SUFFIX_RE = re.compile(
    r'\s*(?:(?:the|a|an)\s+)?'
    r'(?:first|second|third|fourth|fifth|debut|new|latest|special|deluxe|remastered|'
    r'1st|2nd|3rd|4th|5th|\d+(?:st|nd|rd|th)?)'
    r'\s+album\b.*$'
    r'|\s+album\b.*$',
    re.IGNORECASE,
)

def _folder_is_album(name: str) -> bool:
    return bool(_ALBUM_WORD_RE.search(name))

def _extract_album_name(folder_name: str) -> str:
    segments = re.split(r'\s+-\s+|_', folder_name)
    for segment in segments:
        segment = segment.strip()
        if not _ALBUM_WORD_RE.search(segment):
            continue
        m = re.match(r'^\s*album\s+(.+)', segment, re.IGNORECASE)
        if m:
            name_part = m.group(1).strip()
            if re.search(r'[^\W\d_]', name_part, re.UNICODE):
                return name_part
        candidate = _ALBUM_SUFFIX_RE.sub('', segment).strip()
        if candidate:
            return candidate
    return folder_name

def parse_track_info(path: Path, root: Path) -> tuple[str, str, str]:
    try:
        relative_parent = path.parent.relative_to(root)
    except ValueError:
        relative_parent = Path(".")
        
    folder = str(relative_parent) if str(relative_parent) != "." else "Library"
    parts = relative_parent.parts

    # 1. Folder-based defaults
    artist = parts[0] if parts else "Library"
    album = None
    for part in parts[1:]:
        if _folder_is_album(part):
            album = _extract_album_name(part)
            
    if album is None:
        album = parts[1] if len(parts) > 1 else "Singles"
        
    title = readable_title(path)

    # 2. Refine using stem segments
    stem = path.stem
    for suffix in (" - YouTube", " Official MV", " Official Music Video"):
        stem = stem.replace(suffix, "")
    stem = stem.strip()
    
    import re
    def is_track_info(s: str) -> bool:
        s_low = s.strip().lower()
        if re.match(r'^\d+$', s_low):
            return True
        if re.match(r'^track\s*\d+$', s_low):
            return True
        return False
        
    stem_parts = [s.strip() for s in stem.split(" - ") if s.strip()]
    
    file_album = None
    album_idx = -1
    for idx, seg in enumerate(stem_parts):
        if _folder_is_album(seg):
            album_idx = idx
            file_album = _extract_album_name(seg)
            break
            
    if file_album:
        album = file_album
        
    rem_parts = [seg for idx, seg in enumerate(stem_parts) if idx != album_idx]
    core_parts = [seg for seg in rem_parts if not is_track_info(seg)]
    
    if not core_parts:
        core_parts = rem_parts
        
    if len(core_parts) >= 2:
        seg0, seg1 = core_parts[0], core_parts[1]
        
        seg0_has_track = re.match(r'^\d+\s*[\.\)\-_]', seg0.lower()) is not None
        seg1_has_track = re.match(r'^\d+\s*[\.\)\-_]', seg1.lower()) is not None
        
        if seg0_has_track and not seg1_has_track:
            if artist == "Library":
                artist = seg1
            title = seg0
        elif seg1_has_track and not seg0_has_track:
            if artist == "Library":
                artist = seg0
            title = seg1
        else:
            artist_indicators = ["ft.", "feat.", "prod.", "&", " x ", " x", "x "]
            seg0_has_art = any(ind in seg0.lower() for ind in artist_indicators)
            seg1_has_art = any(ind in seg1.lower() for ind in artist_indicators)
            
            if seg1_has_art and not seg0_has_art:
                if artist == "Library":
                    artist = seg1
                title = seg0
            elif seg0_has_art and not seg1_has_art:
                if artist == "Library":
                    artist = seg0
                title = seg1
            else:
                if artist != "Library":
                    if artist.lower() in seg1.lower():
                        title = seg0
                    elif artist.lower() in seg0.lower():
                        title = seg1
                    else:
                        title = seg1
                        artist = seg0
                else:
                    artist = seg0
                    title = seg1
    elif len(core_parts) == 1:
        title = core_parts[0]

    return artist, album, title


def scan_library(root: Path):
    if not root.exists():
        return []

    _folder_art_cache.clear()
    tracks = []
    audio_files = []
    
    try:
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in AUDIO_EXTENSIONS:
                    audio_files.append(Path(dirpath) / filename)
    except OSError:
        pass

    audio_files.sort(key=lambda item: str(item).casefold())

    for path in audio_files:
        try:
            relative_parent = path.parent.relative_to(root)
        except ValueError:
            continue
        folder = str(relative_parent) if str(relative_parent) != "." else "Library"

        artist, album, title = parse_track_info(path, root)

        # Relpath from root to map for API
        rel_path = path.relative_to(root).as_posix()
        tracks.append({
            "path": f"/server/{rel_path}",
            "title": title,
            "folder": folder,
            "artist": artist,
            "album": album
        })
    return tracks

cached_tracks = []

def background_library_scanner():
    global cached_tracks
    while True:
        try:
            # Periodically scan the library directory for updates
            new_tracks = scan_library(MUSIC_DIR)
            cached_tracks = new_tracks
        except Exception as e:
            print(f"Error in background scanner: {e}", flush=True)
        time.sleep(10)

@app.route('/tracks', methods=['GET'])
def get_tracks():
    global cached_tracks
    if not cached_tracks:
        try:
            cached_tracks = scan_library(MUSIC_DIR)
        except Exception:
            pass
    return jsonify(cached_tracks)

@app.route('/audio/<path:filename>', methods=['GET'])
def get_audio(filename):
    file_path = MUSIC_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        abort(404)
    return send_file(file_path)

@app.route('/cover/<path:filename>', methods=['GET'])
def get_cover(filename):
    file_path = MUSIC_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        abort(404)
        
    # Find art in folder
    art_path = find_folder_art(file_path, MUSIC_DIR)
    if art_path and art_path.exists():
        return send_file(art_path)
        
    # Try extracting embedded art using ffmpeg
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        digest = hashlib.sha1(str(file_path).encode("utf-8")).hexdigest()
        cache_dir = Path("/tmp/cover_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = cache_dir / f"{digest}.jpg"
        
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return send_file(cache_path)
            
        try:
            result = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(file_path),
                    "-an",
                    "-vframes",
                    "1",
                    str(cache_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=SUBPROCESS_FLAGS,
            )
            if result.returncode == 0 and cache_path.exists() and cache_path.stat().st_size > 0:
                return send_file(cache_path)
        except Exception:
            pass
            
    # Serve 404
    abort(404)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    artist = request.form.get('artist', 'Library').strip()
    album = request.form.get('album', 'Singles').strip()
    
    orig_filename = file.filename
    if (artist == 'Library' or album == 'Singles') and orig_filename:
        parsed_artist, parsed_album, _ = parse_track_info(Path(orig_filename), MUSIC_DIR)
        if artist == 'Library':
            artist = parsed_artist
        if album == 'Singles':
            album = parsed_album
            
    # Simple sanitization
    def sanitize(name):
        return "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        
    s_artist = sanitize(artist) or 'Library'
    s_album = sanitize(album) or 'Singles'
    
    # We want to preserve the original filename ext
    name_parts = os.path.splitext(orig_filename)
    clean_name = sanitize(name_parts[0]) + name_parts[1].lower()
    
    dest_dir = MUSIC_DIR / s_artist / s_album
    os.makedirs(dest_dir, exist_ok=True)
    
    dest_path = dest_dir / clean_name
    file.save(dest_path)
    
    global cached_tracks
    try:
        cached_tracks = scan_library(MUSIC_DIR)
    except Exception:
        pass
    
    return jsonify({'success': True, 'path': str(dest_path)})

if __name__ == '__main__':
    # Start background library scanner thread (runs every 10 seconds)
    scanner_thread = threading.Thread(target=background_library_scanner, daemon=True)
    scanner_thread.start()
    
    app.run(host='0.0.0.0', port=8000)
