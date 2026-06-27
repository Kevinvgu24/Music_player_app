from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from constants import AUDIO_EXTENSIONS, COVER_CACHE, COVER_HINTS, IMAGE_EXTENSIONS

# creationflags for subprocess to prevent console window popup on Windows
SUBPROCESS_FLAGS = 0
if sys.platform == "win32":
    SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)



@dataclass(frozen=True)
class Track:
    path: Path
    title: str
    folder: str
    artist: str
    album: str
    art_path: Path | None = None


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


def find_folder_art(path: Path, root: Path) -> Path | None:
    current = path.parent
    while current == root or root in current.parents:
        images = [item for item in current.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS]
        if images:
            preferred = sorted(
                images,
                key=lambda item: (
                    not any(hint in search_text(item.stem) for hint in COVER_HINTS),
                    len(item.name),
                    search_text(item.name),
                ),
            )
            return preferred[0]
        if current == root:
            break
        current = current.parent
    return None


def embedded_art_cache_path(path: Path) -> Path:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return COVER_CACHE / f"{digest}.jpg"


def embedded_no_art_path(path: Path) -> Path:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return COVER_CACHE / f"{digest}.noart"


def extract_embedded_art(path: Path) -> Path | None:
    cache_path = embedded_art_cache_path(path)
    no_art_path = embedded_no_art_path(path)
    if cache_path.exists():
        return cache_path
    if no_art_path.exists():
        return None

    COVER_CACHE.mkdir(exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        no_art_path.touch()
        return None

    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(path),
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
    except OSError:
        cache_path.unlink(missing_ok=True)
        no_art_path.touch()
        return None

    if result.returncode == 0 and cache_path.exists() and cache_path.stat().st_size > 0:
        no_art_path.unlink(missing_ok=True)
        return cache_path
    cache_path.unlink(missing_ok=True)
    no_art_path.touch()
    return None


import re as _re

# Matches: optional ordinal/article/descriptor + word "album" at end of segment
_ALBUM_SUFFIX_RE = _re.compile(
    r'\s*(?:(?:the|a|an)\s+)?'
    r'(?:first|second|third|fourth|fifth|debut|new|latest|special|deluxe|remastered|'
    r'1st|2nd|3rd|4th|5th|\d+(?:st|nd|rd|th)?)'
    r'\s+album\b.*$'
    r'|\s+album\b.*$',
    _re.IGNORECASE,
)

# Matches word "album" anywhere (used for detection)
_ALBUM_WORD_RE = _re.compile(r'\balbum\b', _re.IGNORECASE)


def _folder_is_album(name: str) -> bool:
    """Return True if a folder name contains the word 'album'."""
    return bool(_ALBUM_WORD_RE.search(name))


def _extract_album_name(folder_name: str) -> str:
    """Extract the album name from a folder name that contains the word 'album'.

    The album name is the text immediately preceding the word 'album'
    (and any descriptors like 'the first', 'second', 'new', etc.).

    Folder name segments are delimited by ' - ' (space-dash-space) or '_'.

    Examples:
        'LOI CHOI the first album'                       → 'LOI CHOI'
        'SỐ KHÔNG album'                                 → 'SỐ KHÔNG'
        'Wren Evans - Call Me - LOI CHOI the first album'→ 'LOI CHOI'
        'Album SỐ KHÔNG'                                 → 'SỐ KHÔNG'
    """
    # Split into segments by ' - ' or '_'
    segments = _re.split(r'\s+-\s+|_', folder_name)

    for segment in segments:
        segment = segment.strip()
        if not _ALBUM_WORD_RE.search(segment):
            continue

        # Pattern B first: "album [album name]" at start (e.g. "Album SỐ KHÔNG")
        # Guard: only apply if the captured name contains actual letters (not just a number like "Album 1")
        m = _re.match(r'^\s*album\s+(.+)', segment, _re.IGNORECASE)
        if m:
            name_part = m.group(1).strip()
            if _re.search(r'[^\W\d_]', name_part, _re.UNICODE):  # has at least one letter
                return name_part

        # Pattern A: "album name [descriptors] album" at end (e.g. "LOI CHOI the first album")
        candidate = _ALBUM_SUFFIX_RE.sub('', segment).strip()
        if candidate:
            return candidate

    # Fallback: return original folder name unchanged
    return folder_name


def scan_library(root: Path) -> list[Track]:
    if not root.exists():
        return []

    tracks: list[Track] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        relative_parent = path.parent.relative_to(root)
        folder = str(relative_parent) if str(relative_parent) != "." else "Library"
        parts = relative_parent.parts

        # Artist: always the first directory under root
        first_part = parts[0] if parts else "Library"

        # ── Album detection (step 1): check folder names ──────────────────────
        # Walk parts[1:] and find the deepest folder containing "album".
        album: str | None = None
        for part in parts[1:]:
            if _folder_is_album(part):
                album = _extract_album_name(part)

        # ── Album detection (step 2): check the file stem ──────────────────────
        # If no album found from folders, inspect the file name itself.
        # e.g. "(141) WREN EVANS - CALL ME - LOI CHOI The First Album.mp3"
        if album is None and _folder_is_album(path.stem):
            extracted = _extract_album_name(path.stem)
            # Only accept if extraction actually changed the string
            # (i.e. we found a meaningful album name, not just the whole stem)
            if extracted != path.stem:
                album = extracted

        # ── Fallback ────────────────────────────────────────────────────────────
        if album is None:
            album = parts[1] if len(parts) > 1 else "Singles"

        art_path = find_folder_art(path, root)
        tracks.append(
            Track(
                path=path,
                title=readable_title(path),
                folder=folder,
                artist=first_part,
                album=album,
                art_path=art_path,
            )
        )
    return tracks


def get_custom_covers_map() -> dict[str, str]:
    import json
    json_path = COVER_CACHE / "custom_covers.json"
    if not json_path.exists():
        return {}
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_custom_covers_map(mapping: dict[str, str]) -> None:
    import json
    COVER_CACHE.mkdir(exist_ok=True)
    json_path = COVER_CACHE / "custom_covers.json"
    try:
        json_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Error saving custom covers map: {e}")


def get_custom_cover_path(track_path: Path) -> Path | None:
    mapping = get_custom_covers_map()
    path_str = mapping.get(str(track_path))
    if path_str:
        p = Path(path_str)
        if p.exists():
            return p
    return None


def set_custom_cover_path(track_path: Path, image_path: Path | None) -> None:
    mapping = get_custom_covers_map()
    if image_path is None:
        if str(track_path) in mapping:
            del mapping[str(track_path)]
    else:
        mapping[str(track_path)] = str(image_path)
    save_custom_covers_map(mapping)

