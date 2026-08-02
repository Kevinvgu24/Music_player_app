from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
import urllib.request
import urllib.parse
import hashlib

from utils import SUBPROCESS_FLAGS, safe_filename

_CACHED_YT_DLP_CMD: list[str] | None = None
_STREAM_URL_CACHE: dict[str, str] = {}

YT_DLP_FAST_FLAGS = [
    "--no-warnings",
    "--no-call-home",
    "--no-check-certificates",
    "--no-cache-dir",
    "--ignore-config",
]


def get_yt_dlp_cmd() -> list[str]:
    global _CACHED_YT_DLP_CMD
    if _CACHED_YT_DLP_CMD is not None:
        return list(_CACHED_YT_DLP_CMD)

    is_frozen = getattr(sys, "frozen", False)

    # Check local yt-dlp.exe first on Windows
    if sys.platform == "win32":
        local_exe = Path(__file__).parent / "yt-dlp.exe"
        if local_exe.exists():
            _CACHED_YT_DLP_CMD = [str(local_exe)]
            return list(_CACHED_YT_DLP_CMD)

    # Check local yt-dlp (no extension script or binary)
    local_script = Path(__file__).parent / "yt-dlp"
    if local_script.exists():
        try:
            with open(local_script, "rb") as f:
                header = f.read(10)
            if header.startswith(b"#!"):
                if not is_frozen:
                    _CACHED_YT_DLP_CMD = [sys.executable, str(local_script)]
                    return list(_CACHED_YT_DLP_CMD)
        except Exception:
            pass
        if not is_frozen:
            _CACHED_YT_DLP_CMD = [str(local_script)]
            return list(_CACHED_YT_DLP_CMD)

    _CACHED_YT_DLP_CMD = ["yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"]
    return list(_CACHED_YT_DLP_CMD)


def search_soundcloud(query: str, limit: int = 15) -> list[dict]:
    cmd = (
        get_yt_dlp_cmd()
        + YT_DLP_FAST_FLAGS
        + [
            f"scsearch{limit}:{query}",
            "--dump-json",
            "--flat-playlist",
            "--no-playlist",
        ]
    )
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            creationflags=SUBPROCESS_FLAGS,
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
                thumb_url = None
                if "thumbnails" in data and data["thumbnails"]:
                    for t in reversed(data["thumbnails"]):
                        if t.get("id") in ("t300x300", "crop", "large", "original"):
                            thumb_url = t.get("url")
                            break
                    if not thumb_url:
                        thumb_url = data["thumbnails"][-1].get("url")
                if not thumb_url and isinstance(data.get("thumbnail"), str):
                    thumb_url = data.get("thumbnail")

                results.append(
                    {
                        "id": data.get("id"),
                        "title": data.get("title") or data.get("track") or "Unknown Title",
                        "uploader": data.get("uploader") or "Unknown Artist",
                        "duration": data.get("duration") or 0.0,
                        "duration_string": data.get("duration_string") or "00:00",
                        "webpage_url": data.get("webpage_url"),
                        "thumbnail": thumb_url,
                    }
                )
            except Exception as e:
                print(f"Error parsing search result line: {e}")
        return results
    except Exception as e:
        print(f"Error executing soundcloud search: {e}")
        return []


def get_stream_url(webpage_url: str) -> str | None:
    if webpage_url in _STREAM_URL_CACHE:
        return _STREAM_URL_CACHE[webpage_url]

    cmd = (
        get_yt_dlp_cmd()
        + YT_DLP_FAST_FLAGS
        + [
            "-g",
            "-f",
            "http_mp3_0_0/bestaudio",
            webpage_url,
        ]
    )
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=30,
            creationflags=SUBPROCESS_FLAGS,
        )
        if proc.returncode == 0:
            url = proc.stdout.strip()
            if url:
                _STREAM_URL_CACHE[webpage_url] = url
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
    progress_callback=None,
) -> tuple[Path | None, Path | None, str | None]:
    """
    Downloads the SoundCloud track.
    Returns (track_path, cover_path, error_message).
    """
    # 1. Fetch metadata first to know title, artist, thumbnail URL
    cmd_meta = (
        get_yt_dlp_cmd()
        + YT_DLP_FAST_FLAGS
        + [
            "-j",
            webpage_url,
        ]
    )
    try:
        proc_meta = subprocess.run(
            cmd_meta,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            creationflags=SUBPROCESS_FLAGS,
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

    safe_title = safe_filename(title)
    safe_artist = safe_filename(artist)

    # Store in Artist subfolder or root folder
    artist_dir = dest_dir / safe_artist
    try:
        artist_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        artist_dir = dest_dir

    out_template = str(artist_dir / f"{safe_artist} - {safe_title}.%(ext)s")

    cmd_dl = (
        get_yt_dlp_cmd()
        + YT_DLP_FAST_FLAGS
        + [
            "-f",
            "http_mp3_0_0/bestaudio",
            "-o",
            out_template,
            webpage_url,
        ]
    )

    try:
        proc = subprocess.Popen(
            cmd_dl,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=SUBPROCESS_FLAGS,
        )

        percent_re = re.compile(r"(\d+(?:\.\d+)?)%")
        while True:
            line = proc.stdout.readline()
            if not line:
                break

            if progress_callback and "[download]" in line:
                match = percent_re.search(line)
                if match:
                    percent_str = match.group(1)
                    if progress_callback(percent_str) is False:
                        proc.terminate()
                        proc.wait()
                        return None, None, "Cancelled by user"

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

            req = urllib.request.Request(
                thumbnail_url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(
                req, context=context, timeout=10
            ) as response:
                target_cover.write_bytes(response.read())
            if target_cover.exists() and target_cover.stat().st_size > 0:
                cover_path = target_cover
        except Exception as e:
            print(f"Error downloading cover art thumbnail: {e}")

    return downloaded_path, cover_path, None
