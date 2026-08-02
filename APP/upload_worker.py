from __future__ import annotations

import os
import sys
import time
import uuid
import http.client
import urllib.parse
from pathlib import Path
from PySide6.QtCore import QThread, Signal

CHUNK_SIZE = 512 * 1024  # 512 KB stream chunk size for zero-RAM leak streaming


class UploadWorker(QThread):
    # Signals: (file_index, total_files, file_name, bytes_sent, file_size, speed_mbps)
    progress_signal = Signal(int, int, str, int, int, float)
    file_completed_signal = Signal(int, int, str, bool, str)
    finished_signal = Signal(int, int, list)  # (success_count, total_files, failed_files)

    def __init__(
        self,
        files_to_upload: list[tuple[Path, str, str]],  # List of (file_path, artist, album)
        server_url: str,
        parent=None
    ):
        super().__init__(parent)
        self.files_to_upload = files_to_upload
        self.server_url = server_url
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        if not self.server_url or not self.files_to_upload:
            self.finished_signal.emit(0, 0, [])
            return

        parsed = urllib.parse.urlparse(self.server_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        is_https = parsed.scheme == "https"

        total_files = len(self.files_to_upload)
        success_count = 0
        failed_files = []

        for idx, (file_path, artist, album) in enumerate(self.files_to_upload):
            if self._is_cancelled:
                break

            if not file_path.exists() or not file_path.is_file():
                failed_files.append((file_path.name, "File does not exist"))
                self.file_completed_signal.emit(idx + 1, total_files, file_path.name, False, "File missing")
                continue

            file_size = file_path.stat().st_size
            boundary = uuid.uuid4().hex

            # Build multipart form-data header & footer
            header_parts = []
            fields = {"artist": artist, "album": album}
            for name, val in fields.items():
                header_parts.append(f"--{boundary}\r\n".encode("utf-8"))
                header_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
                header_parts.append(f"{val}\r\n".encode("utf-8"))

            header_parts.append(f"--{boundary}\r\n".encode("utf-8"))
            header_parts.append(
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode("utf-8")
            )
            header_parts.append(b"Content-Type: application/octet-stream\r\n\r\n")

            header_bytes = b"".join(header_parts)
            footer_bytes = f"\r\n--{boundary}--\r\n".encode("utf-8")

            total_content_length = len(header_bytes) + file_size + len(footer_bytes)

            success = False
            error_msg = ""
            start_time = time.time()
            bytes_sent = 0

            try:
                if is_https:
                    conn = http.client.HTTPSConnection(host, port, timeout=120)
                else:
                    conn = http.client.HTTPConnection(host, port, timeout=120)

                conn.putrequest("POST", "/upload")
                conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
                conn.putheader("Content-Length", str(total_content_length))
                conn.putheader("User-Agent", "PlaylistOfflineStreamUploader/2.0")
                conn.endheaders()

                # Send header
                conn.send(header_bytes)

                # Stream file payload in 512KB chunks directly from disk
                with open(file_path, "rb") as f:
                    while not self._is_cancelled:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        conn.send(chunk)
                        bytes_sent += len(chunk)

                        elapsed = max(0.001, time.time() - start_time)
                        speed_mbps = (bytes_sent / (1024 * 1024)) / elapsed
                        self.progress_signal.emit(
                            idx + 1, total_files, file_path.name, bytes_sent, file_size, speed_mbps
                        )

                if self._is_cancelled:
                    conn.close()
                    break

                # Send footer
                conn.send(footer_bytes)

                resp = conn.getresponse()
                resp_body = resp.read().decode("utf-8", errors="ignore")
                conn.close()

                if resp.status == 200 and '"success":true' in resp_body.lower():
                    success = True
                    success_count += 1
                else:
                    error_msg = f"HTTP {resp.status}: {resp_body[:100]}"
            except Exception as exc:
                error_msg = str(exc)

            if not success:
                failed_files.append((file_path.name, error_msg))

            self.file_completed_signal.emit(idx + 1, total_files, file_path.name, success, error_msg)

        self.finished_signal.emit(success_count, total_files, failed_files)
