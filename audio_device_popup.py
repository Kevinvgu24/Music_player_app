from __future__ import annotations

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout


class AudioDevicePopup(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        # Use Tool window so it sits on top but does NOT use compositing transparency
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
        )
        # Do NOT set WA_TranslucentBackground – we want a fully opaque solid fill
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("audioDevicePopup")

        self._popup_layout = QVBoxLayout(self)
        self._popup_layout.setContentsMargins(8, 8, 8, 8)
        self._popup_layout.setSpacing(4)
        self.player_window = parent
        self.setMinimumWidth(260)

    # Override paintEvent to draw a solid black rounded rectangle
    # This guarantees the popup fully occludes whatever is behind it.
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Fill solid black background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#000000"))
        painter.drawRoundedRect(self.rect(), 12, 12)
        # Draw border
        border_pen = QPen(QColor("#2b3952"), 2)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 11, 11)
        super().paintEvent(event)

    def populate(self, bg_color: QColor, border_color: QColor, accent_color: QColor) -> None:
        while self._popup_layout.count() > 0:
            item = self._popup_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        accent_name = accent_color.name()

        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #e8e8e8;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                text-align: left;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {accent_name};
                color: #ffffff;
            }}
        """)

        current_volume = self.player_window.volume.value()
        if current_volume > 0:
            mute_btn = QPushButton("🔇 Tắt âm thanh", self)
        else:
            mute_btn = QPushButton("🔊 Bật âm thanh", self)
        mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mute_btn.clicked.connect(self.handle_mute_clicked)
        self._popup_layout.addWidget(mute_btn)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #2b3952; margin: 2px 4px;")
        self._popup_layout.addWidget(sep)

        devices = QMediaDevices.audioOutputs()
        current_device = self.player_window.audio.device()

        if not devices:
            no_device_btn = QPushButton("Không tìm thấy thiết bị", self)
            no_device_btn.setEnabled(False)
            self._popup_layout.addWidget(no_device_btn)
            return

        for device in devices:
            desc = device.description()
            is_current = (desc == current_device.description())
            prefix = "✓ " if is_current else "  "

            btn = QPushButton(prefix + desc, self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, d=device: self.handle_device_clicked(d))
            self._popup_layout.addWidget(btn)

    def handle_mute_clicked(self) -> None:
        self.player_window.toggle_mute()
        self.close()
        
    def handle_device_clicked(self, device) -> None:
        self.player_window.select_audio_device(device)
        self.close()
