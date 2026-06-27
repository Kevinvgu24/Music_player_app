from __future__ import annotations

import json
import subprocess
import threading
from PySide6.QtCore import QObject, Signal


class AudioFocusMonitor(QObject):
    """Monitors whether another application is playing audio using pw-dump."""
    other_audio_detected = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        import shutil
        if shutil.which("pw-dump") is None:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)

    def _run(self):
        import os
        import time
        our_pid = os.getpid()
        while self.running:
            # Check every 800ms for quick response
            time.sleep(0.8)
            if not self.running:
                break
            
            other_playing = False
            try:
                # Run pw-dump with a timeout
                output = subprocess.check_output(["pw-dump"], timeout=1.2)
                dump = json.loads(output)
                
                clients = {}
                for obj in dump:
                    if obj.get("type") == "PipeWire:Interface:Client":
                        c_id = obj.get("id")
                        props = obj.get("info", {}).get("props", {})
                        pid = props.get("application.process.id") or props.get("pipewire.sec.pid")
                        if pid is not None:
                            clients[c_id] = int(pid)
                            
                for obj in dump:
                    props = obj.get("info", {}).get("props", {})
                    if props.get("media.class") == "Stream/Output/Audio":
                        state = obj.get("info", {}).get("state")
                        if state == "running":
                            c_id = props.get("client.id")
                            if c_id is not None:
                                stream_pid = clients.get(c_id)
                                if stream_pid is not None and stream_pid != our_pid:
                                    other_playing = True
                                    break
            except Exception:
                pass
            
            if self.running:
                self.other_audio_detected.emit(other_playing)
