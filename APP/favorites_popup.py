from __future__ import annotations

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QInputDialog,
    QMessageBox,
    QFrame,
    QScrollArea,
    QWidget,
)


class FavoritesPopup(QDialog):
    """
    Interactive Favorites & Custom Playlists/Albums Popup Dialog.
    Allows toggling default Favorites or adding to up to 12 custom named short albums.
    """

    def __init__(self, track_path: str, track_title: str, main_window, parent=None):
        super().__init__(parent or main_window)
        self.track_path = str(track_path)
        self.track_title = track_title
        self.main_window = main_window

        self.setWindowTitle("Thêm vào Album Yêu Thích")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(280)
        self.setMaximumWidth(340)

        self._build_ui()

    def _build_ui(self) -> None:
        container = QFrame(self)
        container.setObjectName("favoritesPopupFrame")
        container.setStyleSheet("""
            QFrame#favoritesPopupFrame {
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 14px;
            }
            QLabel {
                color: #f8fafc;
            }
            QCheckBox {
                color: #e2e8f0;
                font-size: 13px;
                padding: 4px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #475569;
                background: #1e293b;
            }
            QCheckBox::indicator:checked {
                background: #f5c518;
                border-color: #f5c518;
            }
            QPushButton#newAlbumBtn {
                background: rgba(245, 197, 24, 0.12);
                color: #f5c518;
                border: 1px solid rgba(245, 197, 24, 0.35);
                border-radius: 8px;
                padding: 7px 12px;
                font-weight: 750;
            }
            QPushButton#newAlbumBtn:hover {
                background: rgba(245, 197, 24, 0.22);
                border-color: #f5c518;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header Title
        header = QLabel(f"⭐ {self.track_title}")
        font = header.font()
        font.setBold(True)
        font.setPixelSize(13)
        header.setFont(font)
        header.setWordWrap(True)
        layout.addWidget(header)

        # Divider
        divider1 = QFrame()
        divider1.setFrameShape(QFrame.Shape.HLine)
        divider1.setStyleSheet("background: #1e293b; max-height: 1px;")
        layout.addWidget(divider1)

        # Default Favorites Checkbox
        self.default_fav_cb = QCheckBox("⭐ Yêu thích (Mặc định)")
        is_in_default = self.track_path in self.main_window.liked_tracks
        self.default_fav_cb.setChecked(is_in_default)
        self.default_fav_cb.toggled.connect(self._toggle_default_favorite)
        layout.addWidget(self.default_fav_cb)

        # Custom Playlists / Short Albums Section
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(6)

        custom_playlists = getattr(self.main_window, "custom_playlists", {})
        self.custom_cbs = {}

        for playlist_name, track_set in custom_playlists.items():
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            cb = QCheckBox(f"🎵 {playlist_name} ({len(track_set)})")
            cb.setToolTip("Tích để thêm bài hát, bỏ tích để loại bỏ bài hát khỏi Album")
            cb.setChecked(self.track_path in track_set)
            cb.toggled.connect(lambda checked, name=playlist_name: self._toggle_custom_playlist(name, checked))
            row_layout.addWidget(cb, 1)

            del_btn = QToolButton()
            del_btn.setText("🗑")
            del_btn.setToolTip(f"Xóa Album ngắn '{playlist_name}'")
            del_btn.setStyleSheet("QToolButton { border: none; background: transparent; color: #ef4444; font-size: 13px; padding: 2px; } QToolButton:hover { background: rgba(239, 68, 68, 0.2); border-radius: 4px; }")
            del_btn.clicked.connect(lambda _chk=False, name=playlist_name: self._delete_custom_playlist(name))
            row_layout.addWidget(del_btn, 0)

            scroll_layout.addWidget(row_widget)
            self.custom_cbs[playlist_name] = cb

        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        scroll.setMaximumHeight(160)
        layout.addWidget(scroll)

        # Divider 2
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.Shape.HLine)
        divider2.setStyleSheet("background: #1e293b; max-height: 1px;")
        layout.addWidget(divider2)

        # Button: + Tạo Album Ngắn Mới
        self.add_album_btn = QPushButton("+ Tạo Album Ngắn Mới")
        self.add_album_btn.setObjectName("newAlbumBtn")
        self.add_album_btn.clicked.connect(self._create_new_album)
        layout.addWidget(self.add_album_btn)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)

    def _toggle_default_favorite(self, checked: bool) -> None:
        if checked:
            self.main_window.liked_tracks.add(self.track_path)
        else:
            self.main_window.liked_tracks.discard(self.track_path)
        from favorites import save_local_favorites, sync_favorites_to_server
        save_local_favorites(self.main_window.liked_tracks)
        self.main_window.on_favorites_updated()

    def _toggle_custom_playlist(self, name: str, checked: bool) -> None:
        custom_playlists = getattr(self.main_window, "custom_playlists", {})
        if name not in custom_playlists:
            custom_playlists[name] = set()

        if checked:
            custom_playlists[name].add(self.track_path)
        else:
            custom_playlists[name].discard(self.track_path)

        from favorites import save_custom_playlists
        save_custom_playlists(custom_playlists)
        self.main_window.on_custom_playlists_updated()

    def _delete_custom_playlist(self, name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Xác nhận xóa Album",
            f"Bạn có chắc chắn muốn xóa Album ngắn '{name}' không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            custom_playlists = getattr(self.main_window, "custom_playlists", {})
            if name in custom_playlists:
                del custom_playlists[name]
                from favorites import save_custom_playlists
                save_custom_playlists(custom_playlists)
                self.main_window.on_custom_playlists_updated()
                self.accept()


    def _create_new_album(self) -> None:
        custom_playlists = getattr(self.main_window, "custom_playlists", {})
        if len(custom_playlists) >= 12:
            QMessageBox.warning(
                self,
                "Giới hạn Album",
                "Bạn đã tạo tối đa 12 Album ngắn tùy chỉnh!"
            )
            return

        name, ok = QInputDialog.getText(
            self,
            "Tạo Album Ngắn Mới",
            "Nhập tên Album ngắn yêu thích (VD: Chill Hits, Workout):"
        )
        if ok and name.strip():
            clean_name = name.strip()
            if clean_name in custom_playlists:
                QMessageBox.warning(self, "Tên trùng", "Album này đã tồn tại!")
                return

            custom_playlists[clean_name] = {self.track_path}
            from favorites import save_custom_playlists
            save_custom_playlists(custom_playlists)

            self.main_window.on_custom_playlists_updated()
            self.accept()

    def show_near_widget(self, target_widget: QWidget) -> None:
        global_pos = target_widget.mapToGlobal(QPoint(0, 0))
        x = global_pos.x() - self.width() + target_widget.width()
        y = global_pos.y() + target_widget.height() + 4

        # Keep on screen bounds
        screen = target_widget.screen()
        if screen:
            geo = screen.geometry()
            x = max(geo.left() + 8, min(x, geo.right() - self.width() - 8))
            y = max(geo.top() + 8, min(y, geo.bottom() - self.height() - 8))

        self.move(QPoint(x, y))
        self.exec()
