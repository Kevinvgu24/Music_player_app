from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QLinearGradient
from PySide6.QtWidgets import QSlider, QWidget
from PySide6.QtMultimedia import QMediaPlayer


class SeekSlider(QSlider):
    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFixedHeight(18)

    def paintEvent(self, _event) -> None:
        if self.orientation() != Qt.Orientation.Horizontal:
            super().paintEvent(_event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        handle_radius = 5
        track_height = 4
        left = handle_radius
        right = self.width() - handle_radius
        center_y = self.height() / 2
        track_width = max(1, right - left)

        minimum = self.minimum()
        maximum = self.maximum()
        ratio = 0.0 if maximum <= minimum else (self.value() - minimum) / (maximum - minimum)
        ratio = max(0.0, min(1.0, ratio))
        handle_x = left + track_width * ratio

        track_rect = QRectF(left, center_y - track_height / 2, track_width, track_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#252f41"))
        painter.drawRoundedRect(track_rect, track_height / 2, track_height / 2)

        if handle_x > left:
            played_rect = QRectF(left, center_y - track_height / 2, handle_x - left, track_height)
            painter.setBrush(QColor("#1d90f4"))
            painter.drawRoundedRect(played_rect, track_height / 2, track_height / 2)

        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(handle_x - handle_radius, center_y - handle_radius, handle_radius * 2, handle_radius * 2))
        painter.end()


class MusicVisualizer(QWidget):
    """A highly dynamic, beat-synced visualizer widget that paints smooth, capsule-shaped bars."""

    def __init__(self, player, parent=None, width: int = 110, height: int = 22) -> None:
        super().__init__(parent)
        self.player = player
        self.accent_color = QColor("#1d90f4")
        self.current_heights = [0.08] * 7
        self.target_heights = [0.08] * 7
        self.bpm = 120
        self.beat_interval = 500.0  # ms
        self.last_track_path = ""
        self.local_time = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFixedSize(width, height)

    def set_accent(self, color: QColor) -> None:
        self.accent_color = color
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._last_time = time.perf_counter() * 1000.0
        self.timer.start(16)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.timer.stop()

    def tick(self) -> None:
        # Calculate time delta
        now = time.perf_counter() * 1000.0
        if not hasattr(self, "_last_time"):
            self._last_time = now
        dt = now - self._last_time
        self._last_time = now

        # Check player state
        playing = False
        if self.player:
            playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

        if playing:
            # Advance local time based on dt
            self.local_time += dt

            # Check if track changed to update BPM
            track_path = ""
            source = self.player.source()
            if not source.isEmpty():
                track_path = source.toString()

            if track_path != self.last_track_path:
                self.last_track_path = track_path
                if track_path:
                    # Simple hash to generate deterministic song BPM
                    h = sum(ord(c) for c in track_path)
                    self.bpm = 90 + (h % 51)  # 90 to 140 BPM
                else:
                    self.bpm = 120
                self.beat_interval = 60000.0 / self.bpm

            # Let's calculate the targets
            t_sec = self.local_time / 1000.0

            # Math formulas for the beats
            beat_main = math.exp(-((self.local_time % self.beat_interval) / self.beat_interval) * 5.0)
            beat_double = math.exp(-((self.local_time % (self.beat_interval / 2.0)) / (self.beat_interval / 2.0)) * 4.0)
            beat_quad = math.exp(-((self.local_time % (self.beat_interval / 4.0)) / (self.beat_interval / 4.0)) * 3.0)

            # Formulate target heights for 7 bars with organic rhythms
            # Bar 0: Sub-bass
            self.target_heights[0] = 0.75 * beat_main + 0.15 * math.sin(t_sec * 8) + 0.1
            # Bar 1: Bass
            self.target_heights[1] = 0.65 * beat_main + 0.25 * beat_double + 0.1 * math.cos(t_sec * 12)
            # Bar 2: Low-mid
            self.target_heights[2] = 0.35 * beat_main + 0.45 * beat_double + 0.2 * math.sin(t_sec * 15)
            # Bar 3: Mid
            self.target_heights[3] = 0.3 * beat_double + 0.45 * beat_quad + 0.25 * math.sin(t_sec * 20)
            # Bar 4: High-mid
            self.target_heights[4] = 0.2 * beat_double + 0.55 * beat_quad + 0.25 * math.cos(t_sec * 28)
            # Bar 5: High
            self.target_heights[5] = 0.65 * beat_quad + 0.25 * (0.5 * math.sin(t_sec * 40) + 0.5) + 0.1
            # Bar 6: Treble
            self.target_heights[6] = 0.35 * beat_quad + 0.55 * random.uniform(0.2, 0.8) + 0.1

            # Clamp all target heights to [0.05, 1.0]
            for i in range(7):
                self.target_heights[i] = max(0.05, min(1.0, self.target_heights[i]))
        else:
            # If not playing, target is a small resting level
            for i in range(7):
                self.target_heights[i] = 0.08

        # Interpolate current heights towards targets
        for i in range(7):
            curr = self.current_heights[i]
            target = self.target_heights[i]
            if target > curr:
                # Snappy rise (fast bounce up)
                self.current_heights[i] = curr + (target - curr) * 0.4
            else:
                # Smooth drop (gentle bounce down)
                self.current_heights[i] = curr + (target - curr) * 0.15

        # Trigger repaint
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        n_bars = 7
        spacing = 3.0
        w = self.width()
        h = self.height()
        bar_width = (w - spacing * (n_bars - 1)) / n_bars

        # Calculate dynamic top color of the gradient
        hue, sat, val, alpha = self.accent_color.getHsv()
        if hue < 0:
            hue = 208  # Default fallback color
        top_color = QColor.fromHsv(hue, max(0, int(sat * 0.85)), min(255, int(val * 1.35)))

        for i in range(n_bars):
            bar_h = self.current_heights[i] * h
            # Ensure a minimum height to be visible (like a small capsule or dot)
            bar_h = max(3.0, bar_h)

            x = i * (bar_width + spacing)
            y = h - bar_h

            # Create a vertical gradient
            grad = QLinearGradient(x, h, x, y)
            grad.setColorAt(0.0, self.accent_color)
            grad.setColorAt(1.0, top_color)

            rect = QRectF(x, y, bar_width, bar_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)

            # Capsule style: rounded corners (radius is half the bar width)
            radius = min(bar_width / 2.0, bar_h / 2.0)
            painter.drawRoundedRect(rect, radius, radius)

        painter.end()
