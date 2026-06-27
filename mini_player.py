from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsDropShadowEffect,
    QApplication,
)
from library import Track

class MiniPlayerWidget(QWidget):
    EDGE_MARGIN = 10
    DESKTOP_SHORTCUT_MARGIN = 144

    def __init__(self, main_window: "PlayerWindow") -> None:
        super().__init__(None)  # No parent, makes it a standalone window
        self.main_window = main_window
        
        # Keep this as an independent window. Qt.Tool can be hidden together
        # with the main window on some Linux desktop sessions when minimized.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("miniPlayerWidget")
        self.setFixedSize(300, 110)
        
        self.drag_position = QPoint()
        self.is_dragging = False
        self.system_dragging = False
        self.user_positioned = False
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(90)
        self.snap_timer.timeout.connect(self.snap_after_system_drag)
        
        self.setup_ui()
        self.position_in_corner()
        
        # Connect to player state changes
        self.main_window.player.playbackStateChanged.connect(self.update_play_state)
        self.main_window.player.mediaStatusChanged.connect(self.update_track_info)
        self.main_window.player.sourceChanged.connect(self.update_track_info)
        
        # Initial update
        self.update_track_info()
        self.update_play_state()

    def setup_ui(self):
        # Main container with glassmorphism style
        self.container = QWidget(self)
        self.container.setObjectName("container")
        self.container.setFixedSize(300, 110)
        
        # Glassmorphic stylesheet
        accent_color = self.main_window.now_playing_window.current_accent.name() if hasattr(self.main_window, "now_playing_window") else "#1d90f4"
        
        self.container.setStyleSheet(f"""
            QWidget#container {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(18, 28, 45, 0.85), 
                    stop:1 rgba(10, 16, 26, 0.90));
                border: 1.2px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
            }}
            QLabel#titleLabel {{
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
            }}
            QLabel#artistLabel {{
                color: #b3c0d1;
                font-size: 11px;
            }}
            QPushButton#controlBtn {{
                background: transparent;
                border: none;
                color: #ffffff;
                font-size: 20px;
            }}
            QPushButton#controlBtn:hover {{
                color: {accent_color};
            }}
            QPushButton#controlBtn:pressed {{
                color: #ffffff;
            }}
            QLabel#musicNote {{
                color: rgba(255, 255, 255, 0.5);
                font-size: 14px;
            }}
        """)
        
        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)
        
        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Left: Cover image
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(86, 86)
        self.cover_label.setScaledContents(True)
        self.cover_label.setStyleSheet("border-radius: 10px; background-color: #0c1220;")
        layout.addWidget(self.cover_label)
        
        # Right: Info & Controls
        right_layout = QVBoxLayout()
        right_layout.setSpacing(6)
        right_layout.setContentsMargins(0, 2, 0, 2)
        
        # Title, artist and visualizer top row
        top_row = QHBoxLayout()
        info_col = QVBoxLayout()
        info_col.setSpacing(1)
        self.title_label = QLabel("Not Playing")
        self.title_label.setObjectName("titleLabel")
        self.artist_label = QLabel("")
        self.artist_label.setObjectName("artistLabel")
        
        # Limit text width/wrap to make room for visualizer
        self.title_label.setFixedWidth(120)
        self.artist_label.setFixedWidth(120)
        
        info_col.addWidget(self.title_label)
        info_col.addWidget(self.artist_label)
        
        from widgets import MusicVisualizer
        self.visualizer = MusicVisualizer(self.main_window.player, self, width=45, height=18)
        
        top_row.addLayout(info_col, 1)
        top_row.addWidget(self.visualizer, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(22)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.prev_btn = QPushButton("⏮")
        self.prev_btn.setObjectName("controlBtn")
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.clicked.connect(self.main_window.previous_track)
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("controlBtn")
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self.main_window.toggle_play)
        
        self.next_btn = QPushButton("⏭")
        self.next_btn.setObjectName("controlBtn")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.clicked.connect(self.main_window.next_track)
        
        btn_row.addWidget(self.prev_btn)
        btn_row.addWidget(self.play_btn)
        btn_row.addWidget(self.next_btn)
        
        right_layout.addLayout(top_row)
        right_layout.addStretch(1)
        right_layout.addLayout(btn_row)
        
        layout.addLayout(right_layout, 1)
        
        # Main widget layout containing container
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)
        self.install_drag_filters()

    def install_drag_filters(self) -> None:
        for widget in (
            self,
            self.container,
            self.cover_label,
            self.title_label,
            self.artist_label,
            self.visualizer,
        ):
            widget.installEventFilter(self)
            widget.setCursor(Qt.CursorShape.OpenHandCursor)

    def position_in_corner(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - self.EDGE_MARGIN
        y = screen.bottom() - self.height() - self.EDGE_MARGIN
        self.move(x, y)

    def active_screen_geometry(self):
        screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        return screen.availableGeometry()

    def safe_x_range(self, geometry) -> tuple[int, int]:
        left = geometry.left() + self.DESKTOP_SHORTCUT_MARGIN
        right = geometry.right() - self.width() - self.EDGE_MARGIN
        if left > right:
            left = geometry.left() + self.EDGE_MARGIN
        return left, max(left, right)

    def safe_y_range(self, geometry) -> tuple[int, int]:
        top = geometry.top() + self.EDGE_MARGIN
        bottom = geometry.bottom() - self.height() - self.EDGE_MARGIN
        return top, max(top, bottom)

    def ensure_visible_position(self) -> None:
        geometry = self.active_screen_geometry()
        min_x, max_x = self.safe_x_range(geometry)
        min_y, max_y = self.safe_y_range(geometry)
        x = min(max(self.x(), min_x), max_x)
        y = min(max(self.y(), min_y), max_y)
        self.move(x, y)

    def snap_to_nearest_edge(self) -> None:
        geometry = self.active_screen_geometry()
        min_x, max_x = self.safe_x_range(geometry)
        min_y, max_y = self.safe_y_range(geometry)
        current_x = min(max(self.x(), min_x), max_x)
        current_y = min(max(self.y(), min_y), max_y)

        distances = {
            "left": abs(current_x - min_x),
            "right": abs(max_x - current_x),
            "top": abs(current_y - min_y),
            "bottom": abs(max_y - current_y),
        }
        edge = min(distances, key=distances.get)

        if edge == "left":
            current_x = min_x
        elif edge == "right":
            current_x = max_x
        elif edge == "top":
            current_y = min_y
        else:
            current_y = max_y

        self.move(current_x, current_y)

    def constrained_position_for_point(self, point: QPoint) -> QPoint:
        screen = QApplication.screenAt(point)
        if screen is None:
            screen = QApplication.primaryScreen()
        geometry = screen.availableGeometry()
        min_x, max_x = self.safe_x_range(geometry)
        min_y, max_y = self.safe_y_range(geometry)
        wanted = point - self.drag_position
        x = min(max(wanted.x(), min_x), max_x)
        y = min(max(wanted.y(), min_y), max_y)
        return QPoint(x, y)

    def dock_position_for_point(self, point: QPoint) -> QPoint:
        screen = QApplication.screenAt(point)
        if screen is None:
            screen = QApplication.primaryScreen()
        geometry = screen.availableGeometry()
        min_x, max_x = self.safe_x_range(geometry)
        min_y, max_y = self.safe_y_range(geometry)

        cursor_x = min(max(point.x() - self.width() // 2, min_x), max_x)
        cursor_y = min(max(point.y() - self.height() // 2, min_y), max_y)
        distances = {
            "left": abs(point.x() - min_x),
            "right": abs(point.x() - (max_x + self.width())),
            "top": abs(point.y() - min_y),
            "bottom": abs(point.y() - (max_y + self.height())),
        }
        edge = min(distances, key=distances.get)

        if edge == "left":
            return QPoint(min_x, cursor_y)
        if edge == "right":
            return QPoint(max_x, cursor_y)
        if edge == "top":
            return QPoint(cursor_x, min_y)
        return QPoint(cursor_x, max_y)

    def show_widget(self) -> None:
        self.update_track_info()
        self.update_play_state()
        if self.user_positioned:
            self.ensure_visible_position()
        else:
            self.position_in_corner()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()

    def update_track_info(self):
        track = self.main_window.current_track()
        if not track:
            self.title_label.setText("Not Playing")
            self.artist_label.setText("")
            self.cover_label.setPixmap(QPixmap())
            return
            
        self.title_label.setText(track.title)
        self.artist_label.setText(track.artist)
        
        # Load cover
        pixmap = self.main_window.safe_track_pixmap(track, 120, allow_extract=True)
        if not pixmap.isNull():
            # Apply rounded corners to cover using QPainter
            rounded = QPixmap(pixmap.size())
            rounded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            path = QPainterPath()
            path.addRoundedRect(QRectF(pixmap.rect()), 10, 10)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, pixmap)
            painter.end()
            self.cover_label.setPixmap(rounded)
        else:
            self.cover_label.setPixmap(QPixmap())
            
        # Update styling based on accent color
        if hasattr(self.main_window, "current_colors"):
            colors = self.main_window.current_colors
            accent = colors.get("accent", QColor("#1d90f4"))
            bg_start = colors.get("gradient_start", QColor("#121c2d"))
            bg_dark = colors.get("bg_dark", QColor("#0a101a"))
            border = colors.get("bg_border", QColor("#1a2333"))
        else:
            accent = self.main_window.now_playing_window.current_accent if hasattr(self.main_window, "now_playing_window") else QColor("#1d90f4")
            bg_start = QColor("#121c2d")
            bg_dark = QColor("#0a101a")
            border = QColor("#1a2333")
            
        self.update_theme(accent, bg_start, bg_dark, border)

    def update_theme(self, accent: QColor, bg_start: QColor, bg_dark: QColor, border_color: QColor) -> None:
        if not hasattr(self, "visualizer"):
            return
        self.visualizer.set_accent(accent)
        
        r1, g1, b1 = bg_start.red(), bg_start.green(), bg_start.blue()
        r2, g2, b2 = bg_dark.red(), bg_dark.green(), bg_dark.blue()
        br, bg, bb = border_color.red(), border_color.green(), border_color.blue()
        
        self.container.setStyleSheet(f"""
            QWidget#container {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba({r1}, {g1}, {b1}, 0.85), 
                    stop:1 rgba({r2}, {g2}, {b2}, 0.92));
                border: 1.2px solid rgba({br}, {bg}, {bb}, 0.35);
                border-radius: 16px;
            }}
            QLabel#titleLabel {{
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
            }}
            QLabel#artistLabel {{
                color: rgba(255, 255, 255, 0.75);
                font-size: 11px;
            }}
            QPushButton#controlBtn {{
                background: transparent;
                border: none;
                color: #ffffff;
                font-size: 20px;
            }}
            QPushButton#controlBtn:hover {{
                color: {accent.name()};
            }}
            QPushButton#controlBtn:pressed {{
                color: #ffffff;
            }}
        """)

    def update_play_state(self):
        from PySide6.QtMultimedia import QMediaPlayer
        playing = self.main_window.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setText("⏸" if playing else "▶")

    def start_drag(self, event: QMouseEvent) -> None:
        self.user_positioned = True
        self.snap_timer.stop()
        self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        for widget in (self.container, self.cover_label, self.title_label, self.artist_label, self.visualizer):
            widget.setCursor(Qt.CursorShape.ClosedHandCursor)
        if self.should_use_system_drag() and self.start_system_drag():
            event.accept()
            return
        self.is_dragging = True
        event.accept()

    def should_use_system_drag(self) -> bool:
        platform = QApplication.platformName().lower()
        return "wayland" in platform

    def start_system_drag(self) -> bool:
        window = self.windowHandle()
        if window is None:
            window = self.window().windowHandle()
        if window is None or not self.isVisible():
            return False
        try:
            started = bool(window.startSystemMove())
        except RuntimeError:
            return False
        self.system_dragging = started
        return started

    def update_drag(self, event: QMouseEvent) -> None:
        if not self.is_dragging:
            return
        self.move(self.constrained_position_for_point(event.globalPosition().toPoint()))
        self.user_positioned = True
        event.accept()

    def update_docked_drag(self, point: QPoint) -> None:
        self.move(self.dock_position_for_point(point))

    def finish_drag(self, event: QMouseEvent) -> None:
        self.snap_timer.stop()
        self.is_dragging = False
        self.system_dragging = False
        self.snap_to_nearest_edge()
        for widget in (self.container, self.cover_label, self.title_label, self.artist_label, self.visualizer):
            widget.setCursor(Qt.CursorShape.OpenHandCursor)
        event.accept()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            self.main_window.restore_from_mini_player()
            event.accept()
            return True
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.start_drag(event)
            return True
        if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
            self.update_drag(event)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and self.is_dragging:
            self.finish_drag(event)
            return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_drag(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.update_drag(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.finish_drag(event)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.system_dragging:
            self.user_positioned = True
            self.snap_timer.start()

    def snap_after_system_drag(self) -> None:
        if not self.isVisible() or self.is_dragging:
            return
        self.system_dragging = False
        self.snap_to_nearest_edge()
        for widget in (self.container, self.cover_label, self.title_label, self.artist_label, self.visualizer):
            widget.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.main_window.restore_from_mini_player()
            event.accept()

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0c1220;
                color: #ffffff;
                border: 1.2px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1d90f4;
            }
        """)
        if self.main_window.language == "vi":
            restore_text = "Hiện trình phát"
            exit_text = "Thoát hoàn toàn"
        elif self.main_window.language == "de":
            restore_text = "Player anzeigen"
            exit_text = "Anwendung beenden"
        else:
            restore_text = "Restore Player"
            exit_text = "Exit Application"
            
        restore_action = menu.addAction(restore_text)
        exit_action = menu.addAction(exit_text)
        
        action = menu.exec(event.globalPos())
        if action == restore_action:
            self.main_window.restore_from_mini_player()
        elif action == exit_action:
            self.main_window.real_close()

    def closeEvent(self, event) -> None:
        if getattr(self.main_window, "_really_closing", False):
            event.accept()
            return
        event.accept()
        self.main_window.real_close()
