from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
import urllib.request
import urllib.parse
import hashlib

YT_DLP_PATH = Path(__file__).parent / ("yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")

# creationflags for subprocess to prevent console window popup on Windows
SUBPROCESS_FLAGS = 0
if sys.platform == "win32":
    SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

def get_yt_dlp_cmd() -> list[str]:
    if YT_DLP_PATH.exists():
        return [str(YT_DLP_PATH)]
    return ["yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"]

def search_soundcloud(query: str, limit: int = 15) -> list[dict]:
    cmd = get_yt_dlp_cmd() + [
        f"scsearch{limit}:{query}",
        "--dump-json",
        "--flat-playlist",
        "--no-playlist"
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            creationflags=SUBPROCESS_FLAGS
        )
        if proc.returncode != 0:
            print(f"yt-dlp search failed with code {proc.returncode}: {proc.stderr}")
            return []
            
        results = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                # Parse thumbnail
                thumb_url = None
                if "thumbnails" in data and data["thumbnails"]:
                    # Find large or t300x300 or crop
                    for t in reversed(data["thumbnails"]):
                        if t.get("id") in ("t300x300", "crop", "large", "original"):
                            thumb_url = t.get("url")
                            break
                    if not thumb_url:
                        thumb_url = data["thumbnails"][-1].get("url")
                if not thumb_url and isinstance(data.get("thumbnail"), str):
                    thumb_url = data.get("thumbnail")
                        
                results.append({
                    "id": data.get("id"),
                    "title": data.get("title") or data.get("track") or "Unknown Title",
                    "uploader": data.get("uploader") or "Unknown Artist",
                    "duration": data.get("duration") or 0.0,
                    "duration_string": data.get("duration_string") or "00:00",
                    "webpage_url": data.get("webpage_url"),
                    "thumbnail": thumb_url
                })
            except Exception as e:
                print(f"Error parsing search result line: {e}")
        return results
    except Exception as e:
        print(f"Error executing soundcloud search: {e}")
        return []

def get_stream_url(webpage_url: str) -> str | None:
    # Get direct MP3 URL first, fall back to bestaudio
    cmd = get_yt_dlp_cmd() + [
        "-g",
        "-f", "http_mp3_0_0/bestaudio",
        webpage_url
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=30,
            creationflags=SUBPROCESS_FLAGS
        )
        if proc.returncode == 0:
            url = proc.stdout.strip()
            if url:
                return url
        print(f"yt-dlp get stream url failed: {proc.stderr}", flush=True)
        return None
    except subprocess.TimeoutExpired:
        print("get_stream_url timed out after 30 seconds", flush=True)
        return None
    except Exception as e:
        print(f"Error getting stream url: {e}", flush=True)
        return None

def download_track(
    webpage_url: str,
    dest_dir: Path,
    cover_cache_dir: Path,
    progress_callback=None
) -> tuple[Path | None, Path | None, str | None]:
    """
    Downloads the SoundCloud track.
    Returns (track_path, cover_path, error_message).
    """
    # 1. Fetch metadata first to know title, artist, thumbnail URL
    cmd_meta = get_yt_dlp_cmd() + ["-j", webpage_url]
    try:
        proc_meta = subprocess.run(
            cmd_meta,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            creationflags=SUBPROCESS_FLAGS
        )
        if proc_meta.returncode != 0:
            return None, None, f"Failed to retrieve metadata: {proc_meta.stderr}"
        
        meta = json.loads(proc_meta.stdout)
        title = meta.get("title") or meta.get("track") or "Unknown Title"
        artist = meta.get("uploader") or "Unknown Artist"
        thumbnail_url = None
        if "thumbnails" in meta and meta["thumbnails"]:
            for t in reversed(meta["thumbnails"]):
                if t.get("id") in ("t300x300", "crop", "large", "original"):
                    thumbnail_url = t.get("url")
                    break
            if not thumbnail_url:
                thumbnail_url = meta["thumbnails"][-1].get("url")
    except Exception as e:
        return None, None, f"Error getting metadata: {str(e)}"

    # Clean file name components
    def safe_filename(name: str) -> str:
        name = re.sub(r'[\\/*?:"<>|]', "", name)
        return name.strip()

    safe_title = safe_filename(title)
    safe_artist = safe_filename(artist)
    
    # Store in Artist subfolder or root folder
    artist_dir = dest_dir / safe_artist
    try:
        artist_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        artist_dir = dest_dir

    # Output file path template
    # Since we download http_mp3_0_0 if available, extension is mp3. Otherwise let yt-dlp choose extension.
    # We download to a temp location first, then find the extension.
    out_template = str(artist_dir / f"{safe_artist} - {safe_title}.%(ext)s")
    
    # Run yt-dlp download command
    cmd_dl = get_yt_dlp_cmd() + [
        "-f", "http_mp3_0_0/bestaudio",
        "-o", out_template,
        webpage_url
    ]
    
    try:
        proc = subprocess.Popen(
            cmd_dl,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=SUBPROCESS_FLAGS
        )
        
        percent_re = re.compile(r'(\d+(?:\.\d+)?)%')
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            
            if progress_callback and "[download]" in line:
                match = percent_re.search(line)
                if match:
                    percent_str = match.group(1)
                    progress_callback(percent_str)
                    
        proc.wait()
        
        if proc.returncode != 0:
            return None, None, f"Download process failed (exit code {proc.returncode})"
            
    except Exception as e:
        return None, None, f"Error running download process: {str(e)}"
        
    # Find the downloaded file
    downloaded_path = None
    for ext in ("mp3", "m4a", "ogg", "opus", "webm"):
        candidate = artist_dir / f"{safe_artist} - {safe_title}.{ext}"
        if candidate.exists():
            downloaded_path = candidate
            break
            
    if not downloaded_path:
        # Fallback search in directory
        for item in artist_dir.glob(f"{safe_artist} - {safe_title}.*"):
            if item.suffix.lower() in (".mp3", ".m4a", ".ogg", ".opus", ".wav"):
                downloaded_path = item
                break
                
    if not downloaded_path:
        return None, None, "Could not locate the downloaded file."

    # Download cover art if thumbnail URL exists
    cover_path = None
    if thumbnail_url:
        try:
            import ssl
            context = ssl._create_unverified_context()
            cover_cache_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha1(str(downloaded_path).encode("utf-8")).hexdigest()
            target_cover = cover_cache_dir / f"{digest}.jpg"
            
            # Fetch the thumbnail image
            req = urllib.request.Request(
                thumbnail_url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, context=context, timeout=10) as response:
                target_cover.write_bytes(response.read())
            if target_cover.exists() and target_cover.stat().st_size > 0:
                cover_path = target_cover
        except Exception as e:
            print(f"Error downloading cover art thumbnail: {e}")
            
    return downloaded_path, cover_path, None
