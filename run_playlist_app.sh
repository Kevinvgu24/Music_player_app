#!/bin/sh
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
APP_FILE="$APP_DIR/music_player.py"
LOG_FILE="$APP_DIR/playlist_app.log"
VENDOR_DIR="$APP_DIR/vendor"

cd "$APP_DIR" || exit 1

{
  echo "---- $(date) ----"
  echo "Launching Playlist Offline"
} >> "$LOG_FILE"

if [ -d "$VENDOR_DIR/PySide6" ]; then
  if [ "${container:-}" = "flatpak" ] && command -v flatpak-spawn >/dev/null 2>&1; then
    exec flatpak-spawn --host env PYTHONPATH="$VENDOR_DIR${PYTHONPATH:+:$PYTHONPATH}" sh -c 'cd "$1" || exit 1; shift; exec python3 music_player.py "$@"' sh "$APP_DIR" "$@" >> "$LOG_FILE" 2>&1
  fi
  exec env PYTHONPATH="$VENDOR_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 "$APP_FILE" "$@" >> "$LOG_FILE" 2>&1
fi

if python3 -c 'import PySide6' >/dev/null 2>&1; then
  exec python3 "$APP_FILE" "$@" >> "$LOG_FILE" 2>&1
fi

if command -v flatpak >/dev/null 2>&1; then
  exec flatpak run --command=python3 com.visualstudio.code "$APP_FILE" "$@" >> "$LOG_FILE" 2>&1
fi

echo "PySide6 is not installed and Flatpak is not available." >> "$LOG_FILE"
exit 1
