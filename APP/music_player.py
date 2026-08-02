#!/usr/bin/env python3
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from constants import APP_NAME
from mpris import raise_existing_instance
from player_window import PlayerWindow


def main() -> int:
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass
    if sys.stderr is not None and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(line_buffering=True)
        except Exception:
            pass
    app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    if raise_existing_instance():
        return 0
    window = PlayerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
