import json
from pathlib import Path
import zipfile
import hashlib

def main():
    zip_path = Path.home() / "Downloads" / "youtube_covers.zip"
    if not zip_path.exists():
        print(f"Error: {zip_path} not found! Please run downloader.html in your browser first and make sure the download completes.")
        return

    # Extract destination
    extract_dir = Path(__file__).parent / ".cover_cache"
    extract_dir.mkdir(exist_ok=True)

    print("Extracting covers from ZIP...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)
    print("Covers extracted successfully.")

    # Load track list
    tracks_json_path = Path(__file__).parent / "tracks_list.json"
    if not tracks_json_path.exists():
        print("Error: tracks_list.json not found in the workspace!")
        return

    with open(tracks_json_path, "r", encoding="utf-8") as f:
        tracks = json.load(f)

    # Load or initialize custom_covers.json
    custom_covers_json = extract_dir / "custom_covers.json"
    if custom_covers_json.exists():
        try:
            with open(custom_covers_json, "r", encoding="utf-8") as f:
                mapping = json.load(f)
        except Exception:
            mapping = {}
    else:
        mapping = {}

    registered_count = 0
    for t in tracks:
        track_path = Path(t["path"])
        digest = hashlib.sha1(str(track_path).encode("utf-8")).hexdigest()
        image_file = extract_dir / f"{digest}.jpg"
        if image_file.exists():
            mapping[str(track_path)] = str(image_file)
            registered_count += 1

    with open(custom_covers_json, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(f"Successfully registered {registered_count} covers in custom_covers.json!")
    print("You can now open/restart the Playlist Offline application to see the covers.")

if __name__ == "__main__":
    main()
