from __future__ import annotations

import os
from pathlib import Path
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QScrollArea,
    QGridLayout,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QFileDialog,
)

from constants import IMAGE_EXTENSIONS
from library import Track, get_custom_cover_path


class ImageCard(QFrame):
    clicked = Signal(Path)
    double_clicked = Signal(Path)

    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.selected = False
        self.setObjectName("imageCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)
        
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(120, 120)
        self.thumbnail.setScaledContents(True)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Load pixmap
        pixmap = QPixmap(str(image_path))
        if not pixmap.isNull():
            scaled = pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            if scaled.width() != 120 or scaled.height() != 120:
                x = max(0, (scaled.width() - 120) // 2)
                y = max(0, (scaled.height() - 120) // 2)
                scaled = scaled.copy(x, y, 120, 120)
            self.thumbnail.setPixmap(scaled)
        else:
            self.thumbnail.setText("🖼️")
            self.thumbnail.setStyleSheet("font-size: 24px;")
            
        self.name_label = QLabel(image_path.name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setObjectName("imageCardName")
        self.name_label.setWordWrap(True)
        
        self.layout.addWidget(self.thumbnail, 0, Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.name_label)
        
        self.setStyleSheet("""
            QFrame#imageCard {
                border: 2px solid #1a2333;
                border-radius: 8px;
                background: #0d1320;
            }
            QFrame#imageCard:hover {
                border-color: #3b82f6;
                background: #1e293b;
            }
            QLabel#imageCardName {
                color: #b3b3b3;
                font-size: 11px;
            }
        """)

    def set_selected(self, selected: bool):
        self.selected = selected
        if selected:
            self.setStyleSheet("""
                QFrame#imageCard {
                    border: 2px solid #1d90f4;
                    border-radius: 8px;
                    background: #1e293b;
                }
                QLabel#imageCardName {
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#imageCard {
                    border: 2px solid #1a2333;
                    border-radius: 8px;
                    background: #0d1320;
                }
                QFrame#imageCard:hover {
                    border-color: #3b82f6;
                    background: #1e293b;
                }
                QLabel#imageCardName {
                    color: #b3b3b3;
                    font-size: 11px;
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.image_path)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.image_path)


class CoverArtSelectorDialog(QDialog):
    def __init__(self, track: Track, library_root: Path, parent_window=None):
        super().__init__(parent_window)
        self.track = track
        self.library_root = library_root
        self.parent_window = parent_window
        self.selected_path: Path | None = None
        self.image_cards: list[ImageCard] = []
        
        self.setup_ui()
        self.scan_and_populate_images()

    def tr(self, key: str, **kwargs) -> str:
        if self.parent_window and hasattr(self.parent_window, "tr"):
            return self.parent_window.tr(key, **kwargs)
        return key

    def setup_ui(self):
        self.setWindowTitle(self.tr("dialog_title"))
        self.setMinimumSize(520, 480)
        self.resize(600, 520)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #070b13;
                color: #ffffff;
            }
            QLineEdit {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                color: #ffffff;
                padding: 8px 14px;
                min-height: 18px;
            }
            QLineEdit:focus {
                border: 1px solid #1d90f4;
            }
            QScrollArea {
                border: 1px solid #1a2333;
                background-color: #05080f;
                border-radius: 8px;
            }
            QPushButton {
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton#selectBtn {
                background-color: #1d90f4;
                color: #ffffff;
                border: none;
            }
            QPushButton#selectBtn:hover {
                background-color: #3b82f6;
            }
            QPushButton#selectBtn:disabled {
                background-color: #1a2333;
                color: #627284;
            }
            QPushButton#cancelBtn {
                background-color: transparent;
                color: #a0aab8;
                border: 1px solid #1a2333;
            }
            QPushButton#cancelBtn:hover {
                background-color: rgba(255, 255, 255, 0.05);
                color: #ffffff;
            }
            QPushButton#actionBtn {
                background-color: #161f2e;
                color: #ffffff;
                border: 1px solid #2a3a52;
            }
            QPushButton#actionBtn:hover {
                background-color: #202d42;
                border-color: #3b5170;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header info
        header_layout = QHBoxLayout()
        self.info_label = QLabel(f"<b>{self.track.title}</b><br/><font color='#a0aab8'>{self.track.artist} · {self.track.album}</font>")
        self.info_label.setWordWrap(True)
        header_layout.addWidget(self.info_label)
        
        layout.addLayout(header_layout)

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("dialog_search_placeholder"))
        self.search_input.textChanged.connect(self.filter_images)
        layout.addWidget(self.search_input)

        # Scroll Area for image cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        self.grid_layout.setSpacing(10)
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)

        # No images message
        self.no_images_label = QLabel(self.tr("dialog_no_images"))
        self.no_images_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_images_label.setStyleSheet("color: #627284; font-size: 14px;")
        self.no_images_label.setVisible(False)
        self.grid_layout.addWidget(self.no_images_label, 0, 0)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        
        self.browse_btn = QPushButton(self.tr("dialog_browse_btn"))
        self.browse_btn.setObjectName("actionBtn")
        self.browse_btn.clicked.connect(self.browse_custom_image)
        
        self.remove_btn = QPushButton(self.tr("dialog_remove_btn"))
        self.remove_btn.setObjectName("actionBtn")
        self.remove_btn.clicked.connect(self.remove_custom_image)
        
        custom_cover = get_custom_cover_path(self.track.path)
        self.remove_btn.setEnabled(custom_cover is not None)
        
        self.select_btn = QPushButton(self.tr("dialog_select_btn"))
        self.select_btn.setObjectName("selectBtn")
        self.select_btn.setEnabled(False)
        self.select_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton(self.tr("dialog_cancel_btn"))
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        
        bottom_layout.addWidget(self.browse_btn)
        bottom_layout.addWidget(self.remove_btn)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.cancel_btn)
        bottom_layout.addWidget(self.select_btn)
        
        layout.addLayout(bottom_layout)

    def scan_and_populate_images(self):
        for card in self.image_cards:
            self.grid_layout.removeWidget(card)
            card.deleteLater()
        self.image_cards.clear()
        
        artist_dir = self.library_root / self.track.artist
        image_paths: list[Path] = []
        
        if artist_dir.exists() and artist_dir.is_dir():
            for path in artist_dir.rglob("*"):
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                    image_paths.append(path)
        
        image_paths.sort(key=lambda p: p.name.lower())
        
        if not image_paths:
            self.no_images_label.setVisible(True)
        else:
            self.no_images_label.setVisible(False)
            cols = 3
            for idx, path in enumerate(image_paths):
                card = ImageCard(path, self)
                card.clicked.connect(self.on_card_clicked)
                card.double_clicked.connect(self.on_card_double_clicked)
                self.image_cards.append(card)
                
                row = idx // cols
                col = idx % cols
                self.grid_layout.addWidget(card, row, col)

    def on_card_clicked(self, path: Path):
        self.selected_path = path
        for card in self.image_cards:
            card.set_selected(card.image_path == path)
        self.select_btn.setEnabled(True)

    def on_card_double_clicked(self, path: Path):
        self.selected_path = path
        self.accept()

    def filter_images(self, text: str):
        query = text.lower().strip()
        visible_count = 0
        cols = 3
        
        for card in self.image_cards:
            self.grid_layout.removeWidget(card)
            
        for card in self.image_cards:
            if not query or query in card.image_path.name.lower():
                card.setVisible(True)
                row = visible_count // cols
                col = visible_count % cols
                self.grid_layout.addWidget(card, row, col)
                visible_count += 1
            else:
                card.setVisible(False)
                
        self.no_images_label.setVisible(visible_count == 0)

    def browse_custom_image(self):
        filter_str = "Images (" + " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS) + ")"
        chosen, _ = QFileDialog.getOpenFileName(self, self.tr("dialog_browse_btn"), str(self.library_root), filter_str)
        if chosen:
            self.selected_path = Path(chosen)
            self.accept()

    def remove_custom_image(self):
        self.done(2)
