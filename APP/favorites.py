from __future__ import annotations

import json
import urllib.request
import urllib.parse
from pathlib import Path

FAVORITES_FILE = Path.home() / ".playlist_offline_favorites.json"


def load_local_favorites() -> set[str]:
    """Load favorited track path strings from local JSON file."""
    if not FAVORITES_FILE.exists():
        return set()
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(data)
    except Exception as e:
        print(f"[WARN] Failed to load local favorites: {e}")
    return set()


def save_local_favorites(favorites: set[str]) -> None:
    """Save favorited track path strings to local JSON file."""
    try:
        FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(list(favorites), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save local favorites: {e}")


CUSTOM_PLAYLISTS_FILE = Path.home() / ".playlist_offline_custom_playlists.json"


def load_custom_playlists() -> dict[str, set[str]]:
    """Load custom playlists mapping name -> set of track path strings."""
    if not CUSTOM_PLAYLISTS_FILE.exists():
        return {}
    try:
        with open(CUSTOM_PLAYLISTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {k: set(v) for k, v in data.items() if isinstance(v, list)}
    except Exception as e:
        print(f"[WARN] Failed to load custom playlists: {e}")
    return {}


def save_custom_playlists(playlists: dict[str, set[str]]) -> None:
    """Save custom playlists mapping to JSON."""
    try:
        CUSTOM_PLAYLISTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {k: list(v) for k, v in playlists.items()}
        with open(CUSTOM_PLAYLISTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save custom playlists: {e}")



def fetch_favorites_from_server(server_url: str) -> set[str]:
    """Fetch favorited track path strings from Server API."""
    if not server_url:
        return set()
    try:
        url = f"{server_url.rstrip('/')}/favorites"
        req = urllib.request.Request(url, headers={"User-Agent": "PlaylistOfflineClient/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    return set(data)
    except Exception as e:
        print(f"[WARN] Failed to fetch server favorites: {e}")
    return set()


def sync_favorites_to_server(server_url: str, favorites: set[str]) -> bool:
    """Push local favorited track path strings to Server API."""
    if not server_url:
        return False
    try:
        url = f"{server_url.rstrip('/')}/favorites"
        payload = json.dumps({"favorites": list(favorites)}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "PlaylistOfflineClient/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[WARN] Failed to sync favorites to server: {e}")
        return False
