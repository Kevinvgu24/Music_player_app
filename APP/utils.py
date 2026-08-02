import re
import subprocess
import sys

# creationflags for subprocess to prevent console window popup on Windows
SUBPROCESS_FLAGS = 0
if sys.platform == "win32":
    SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def safe_filename(name: str) -> str:
    """Sanitize string for safe use in Windows/Unix filenames."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()


def format_ms(value: int) -> str:
    seconds = max(0, value // 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    return f"{minutes:02}:{seconds:02}"

