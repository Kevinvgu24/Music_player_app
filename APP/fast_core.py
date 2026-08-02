from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

HAS_FAST_CORE = False
_fast_dll = None


def _load_fast_core_dll():
    global HAS_FAST_CORE, _fast_dll
    if sys.platform != "win32":
        return

    # Check potential DLL locations
    possible_paths = []
    
    # 1. PyInstaller frozen sys._MEIPASS directory
    if getattr(sys, "frozen", False):
        possible_paths.append(Path(getattr(sys, "_MEIPASS", "")) / "fast_core.dll")
        possible_paths.append(Path(sys.executable).parent / "fast_core.dll")

    # 2. Local APP directory
    possible_paths.append(Path(__file__).parent / "fast_core.dll")
    possible_paths.append(Path.cwd() / "APP" / "fast_core.dll")
    possible_paths.append(Path.cwd() / "fast_core.dll")

    for dll_path in possible_paths:
        if dll_path.exists():
            try:
                _fast_dll = ctypes.CDLL(str(dll_path))
                
                # Configure fast_remove_accents argtypes and restype
                _fast_dll.fast_remove_accents.argtypes = [
                    ctypes.c_char_p,
                    ctypes.c_char_p,
                    ctypes.c_int,
                ]
                _fast_dll.fast_remove_accents.restype = ctypes.c_int

                # Configure fast_scan_audio_files_w argtypes and restype
                _fast_dll.fast_scan_audio_files_w.argtypes = [
                    ctypes.c_wchar_p,
                    ctypes.c_wchar_p,
                    ctypes.c_size_t,
                ]
                _fast_dll.fast_scan_audio_files_w.restype = ctypes.c_int

                # Configure fast_contains_query argtypes and restype
                try:
                    _fast_dll.fast_contains_query.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
                    _fast_dll.fast_contains_query.restype = ctypes.c_int
                except Exception:
                    pass

                HAS_FAST_CORE = True
                print(f"[INFO] Loaded native fast_core.dll from: {dll_path}", flush=True)
                return
            except Exception as e:
                print(f"[WARN] Failed to load fast_core.dll at {dll_path}: {e}", flush=True)

_load_fast_core_dll()


def search_text_fast(value: object) -> str:
    """
    Ultra-fast native C Vietnamese diacritics stripping and normalization.
    Falls back to Python implementation if native DLL is unavailable.
    """
    text_str = str(value)
    if not text_str.strip():
        return ""

    if HAS_FAST_CORE and _fast_dll:
        try:
            input_bytes = text_str.encode("utf-8", errors="ignore")
            max_len = len(input_bytes) * 2 + 32
            out_buf = ctypes.create_string_buffer(max_len)
            
            res_len = _fast_dll.fast_remove_accents(input_bytes, out_buf, max_len)
            if res_len >= 0:
                return out_buf.value.decode("utf-8", errors="ignore")
        except Exception:
            pass

    # Pure Python fallback
    import unicodedata
    text = text_str.casefold().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", text)
    no_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    spaced = "".join(char if char.isalnum() else " " for char in no_marks)
    return " ".join(spaced.split())


def fast_match_query(haystack: str, query: str) -> bool:
    """
    Sub-millisecond native C substring matching with accent normalization.
    """
    if not query or not query.strip():
        return True
    if not haystack:
        return False
    if HAS_FAST_CORE and _fast_dll and hasattr(_fast_dll, "fast_contains_query"):
        try:
            h_bytes = haystack.encode("utf-8", errors="ignore")
            q_bytes = query.strip().encode("utf-8", errors="ignore")
            return bool(_fast_dll.fast_contains_query(h_bytes, q_bytes))
        except Exception:
            pass
    # Pure Python fallback
    q_norm = search_text_fast(query)
    h_norm = search_text_fast(haystack)
    return q_norm in h_norm



def scan_audio_files_fast(root: Path) -> list[Path] | None:
    """
    Ultra-fast native Win32 directory traversal for audio files.
    Returns list of Path objects, or None if fast_core is unavailable.
    """
    if not HAS_FAST_CORE or not _fast_dll or not root.exists():
        return None

    try:
        # 16MB buffer allows scanning tens of thousands of audio paths
        max_chars = 16 * 1024 * 1024
        out_buf = ctypes.create_unicode_buffer(max_chars)
        
        count = _fast_dll.fast_scan_audio_files_w(str(root), out_buf, max_chars)
        if count <= 0:
            return []

        raw_str = out_buf.value
        lines = [line.strip() for line in raw_str.split("\n") if line.strip()]
        return [Path(p) for p in lines]
    except Exception as e:
        print(f"[WARN] Native directory scan failed: {e}, falling back to Python os.walk", flush=True)
        return None
