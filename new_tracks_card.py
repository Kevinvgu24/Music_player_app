from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget


class NewTracksCard(QWidget):
    """Glassmorphism-style card showing newly detected tracks, with dynamic album color support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accent = QColor("#1d90f4")
        self._lines: list[str] = []
        self.setMinimumWidth(210)
        self.setMaximumWidth(240)
        self.hide()

    def set_accent(self, accent: QColor) -> None:
        self._accent = accent
        self.update()

    def set_lines(self, lines: list[str]) -> None:
        self._lines = lines
        self._update_height()
        self.update()

    def clear(self) -> None:
        self._lines = []
        self.hide()

    def _update_height(self) -> None:
        n = len(self._lines)
        self.setFixedHeight(20 + n * 28 + 16)

    def paintEvent(self, _event) -> None:
        if not self._lines:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        a = self._accent
        h, s, v, _ = a.getHsv()
        if h < 0:
            h = 208

        # Card background — dark tinted glass
        bg = QColor.fromHsv(h, min(180, int(s * 0.7)), min(30, int(v * 0.22)))
        bg.setAlpha(230)

        # Gradient fill top→bottom
        grad_top = QColor.fromHsv(h, min(200, int(s * 0.9)), min(42, int(v * 0.30)))
        grad_top.setAlpha(245)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, grad_top)
        grad.setColorAt(1.0, bg)

        rect = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(rect, 14, 14)

        # Subtle top-edge highlight (glass shimmer)
        shimmer = QLinearGradient(0, 0, 0, 18)
        shimmer.setColorAt(0, QColor(255, 255, 255, 28))
        shimmer.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(shimmer)
        painter.drawRoundedRect(rect, 14, 14)

        # Border
        border_color = QColor.fromHsv(h, min(200, int(s * 0.9)), min(80, int(v * 0.55)))
        border_color.setAlpha(140)
        painter.setPen(QPen(border_color, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), 13.5, 13.5)

        # Text rows
        accent_text = QColor.fromHsv(h, min(140, int(s * 0.55)), 255)
        muted = QColor(255, 255, 255, 160)

        font = painter.font()
        font.setPointSizeF(10.5)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)

        y = 18
        for i, line in enumerate(self._lines):
            if i == len(self._lines) - 1 and line.startswith("…"):
                painter.setPen(QPen(muted))
            else:
                painter.setPen(QPen(accent_text))
            painter.drawText(14, y + 14, line)
            y += 28

        painter.end()
