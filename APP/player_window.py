from __future__ import annotations

import hashlib
import random
import sys
from pathlib import Path
import urllib.parse


import json
import subprocess
import threading

from PySide6.QtCore import QEasingCurve, QPoint, QRectF, QSize, Qt, QTimer, QUrl, QVariantAnimation, Signal, QObject, QEvent, QThread
try:
    from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusObjectPath
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False
    class QDBusConnection:
        class RegisterOption:
            ExportAdaptors = 0
        @classmethod
        def sessionBus(cls):
            return None
    class QDBusMessage:
        @classmethod
        def createSignal(cls, *args, **kwargs):
            return None
    class QDBusObjectPath:
        def __init__(self, path: str):
            self.path = path
from PySide6.QtGui import QAction, QBrush, QColor, QCloseEvent, QFont, QFontMetrics, QIcon, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap, QKeyEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStyle,
    QTableWidget,
    QStackedWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from constants import APP_NAME, DEFAULT_LIBRARY
from i18n import TRANSLATIONS
from library import (
    Track,
    embedded_art_cache_path,
    extract_embedded_art,
    scan_library,
    search_text,
    get_custom_cover_path,
    set_custom_cover_path,
    _folder_is_album,
    _extract_album_name,
    readable_title,
)
from mpris import MprisPlayerAdaptor, MprisRootAdaptor
from now_playing import MiniControlButton, NowPlayingWindow
from utils import format_ms
from widgets import SeekSlider, MusicVisualizer

from audio_monitor import AudioFocusMonitor
from new_tracks_card import NewTracksCard
from audio_device_popup import AudioDevicePopup


class SoundCloudWorker(QObject):
    search_done = Signal(list)
    search_failed = Signal(str)
    download_progress = Signal(int, str)
    download_done = Signal(int, bool, str)
    stream_done = Signal(str, str, str, str)   # title, artist, virtual_path, stream_url
    stream_failed = Signal(str)


class UploadWorker(QObject):
    progress_changed = Signal(int, str)
    upload_finished = Signal(int)
    
    def __init__(self, chosen_files, artist_name, album_name, url, language):
        super().__init__()
        self.chosen_files = chosen_files
        self.artist_name = artist_name
        self.album_name = album_name
        self.url = url
        self.language = language
        self.is_cancelled = False
        
    def run(self):
        import uuid
        import urllib.request
        from pathlib import Path
        
        total_files = len(self.chosen_files)
        success_count = 0
        
        for i, file_path_str in enumerate(self.chosen_files):
            if self.is_cancelled:
                break
                
            file_path = Path(file_path_str)
            msg = f"Tải lên {i+1}/{total_files}: {file_path.name}..." if self.language == "vi" else f"Uploading {i+1}/{total_files}: {file_path.name}..."
            self.progress_changed.emit(i, msg)
            
            try:
                upload_url = f"{self.url}/upload"
                boundary = uuid.uuid4().hex
                parts = []
                
                fields = {
                    "artist": self.artist_name,
                    "album": self.album_name
                }
                for name, val in fields.items():
                    parts.append(f"--{boundary}".encode('utf-8'))
                    parts.append(f'Content-Disposition: form-data; name="{name}"'.encode('utf-8'))
                    parts.append(b'')
                    parts.append(str(val).encode('utf-8'))
                    
                parts.append(f"--{boundary}".encode('utf-8'))
                parts.append(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"'.encode('utf-8'))
                parts.append(b'Content-Type: application/octet-stream')
                parts.append(b'')
                with open(file_path, 'rb') as f:
                    parts.append(f.read())
                    
                parts.append(f"--{boundary}--".encode('utf-8'))
                parts.append(b'')
                
                body = b'\r\n'.join(parts)
                req = urllib.request.Request(upload_url, data=body)
                req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                req.add_header('Content-Length', str(len(body)))
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    response.read()
                success_count += 1
            except Exception as e:
                print(f"Error uploading {file_path.name}: {e}", flush=True)
                
        if not self.is_cancelled:
            self.progress_changed.emit(total_files, "Tải lên hoàn tất!" if self.language == "vi" else "Upload complete!")
        self.upload_finished.emit(success_count)


class PlayerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.library_root = DEFAULT_LIBRARY
        self.tracks: list[Track] = []
        self.visible_tracks: list[Track] = []
        self.art_cache: dict[tuple[str, int], QIcon] = {}
        self.pixmap_cache: dict[tuple[str, int], QPixmap] = {}
        self.language = "vi"
        self.mpris_available = False
        self.current_index = -1
        self.last_track: Track | None = None
        self.current_online_track: Track | None = None   # Active SoundCloud streaming track
        self.paused_position = 0
        self.resume_token = 0
        self.is_user_seeking = False
        self.shuffle_enabled = False
        self.repeat_enabled = False
        self.liked_tracks: set[Path] = set()
        self.online_stream_urls = {}
        self.online_results = []
        
        self.soundcloud_worker = SoundCloudWorker(self)
        self.soundcloud_worker.search_done.connect(self.handle_search_results)
        self.soundcloud_worker.search_failed.connect(self.handle_search_failed)
        self.soundcloud_worker.download_progress.connect(self.handle_download_progress)
        self.soundcloud_worker.download_done.connect(self.handle_download_done)
        self.soundcloud_worker.stream_done.connect(self._on_stream_done)
        self.soundcloud_worker.stream_failed.connect(self._on_stream_failed)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.8)

        self.current_bg_sidebar = QColor("#0a0e17")
        self.current_bg_border = QColor("#1a2333")
        self.current_accent = QColor("#1d90f4")
        
        self.current_colors = {
            "bg_window": QColor("#070b13"),
            "bg_sidebar": QColor("#0a0e17"),
            "bg_border": QColor("#1a2333"),
            "gradient_start": QColor("#0e1320"),
            "bg_dark": QColor("#0e1320"),
            "accent": QColor("#1d90f4"),
        }
        self.bg_animation = None
        self.splitter_animation = None
        self.mini_player = None
        self._really_closing = False


        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1020, 620)
        self.resize(1200, 720)
        icon_path = Path(__file__).parent / "app_icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

        self._build_actions()
        self._build_ui()
        self.now_playing_window = NowPlayingWindow(self)
        self.main_splitter.addWidget(self.now_playing_window)
        self.main_splitter.setCollapsible(2, False)
        self.main_splitter.setStretchFactor(2, 0)
        self.now_playing_window.hide()
        self.main_splitter.setSizes([190, 1010, 0])
        self._apply_theme()
        self._apply_effects()
        self.now_playing_window.setStyleSheet(self.styleSheet())

        self.update_static_texts()
        self._connect_player()
        self.setup_mpris()
        self.reload_library()
        self.auto_paused_by_other_media = False
        self.audio_monitor = AudioFocusMonitor(self)
        self.audio_monitor.other_audio_detected.connect(self.handle_other_audio_state)
        self.audio_monitor.start()
        QTimer.singleShot(700, self.refresh_mpris_metadata)
        QTimer.singleShot(1800, self.refresh_mpris_metadata)

        # Double-press and shortcut timers/state
        self.left_click_timer = QTimer(self)
        self.left_click_timer.setSingleShot(True)
        self.left_click_timer.timeout.connect(self._do_seek_backward)

        self.right_click_timer = QTimer(self)
        self.right_click_timer.setSingleShot(True)
        self.right_click_timer.timeout.connect(self._do_seek_forward)

        # Install global event filter for keyboard shortcuts
        QApplication.instance().installEventFilter(self)

    def tr(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS[self.language].get(key, TRANSLATIONS["vi"].get(key, key))
        return text.format(**kwargs) if kwargs else text

    def toggle_language(self) -> None:
        if self.language == "vi":
            self.language = "en"
        elif self.language == "en":
            self.language = "de"
        else:
            self.language = "vi"
        self.update_static_texts()
        self.populate_folders()
        self.populate_albums()
        self.apply_filter()

    def _do_seek_backward(self) -> None:
        new_pos = max(0, self.player.position() - 5000)
        self.player.setPosition(new_pos)
        self.emit_mpris_properties("Position")

    def _do_seek_forward(self) -> None:
        duration = self.player.duration()
        new_pos = min(duration, self.player.position() + 5000)
        self.player.setPosition(new_pos)
        self.emit_mpris_properties("Position")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key_event = event
            focused = QApplication.focusWidget()
            if focused is not None and isinstance(focused, QLineEdit):
                return super().eventFilter(watched, event)

            if key_event.key() == Qt.Key.Key_Space:
                self.toggle_play()
                return True
            elif key_event.key() == Qt.Key.Key_Left:
                if key_event.isAutoRepeat():
                    self.left_click_timer.stop()
                    self._do_seek_backward()
                else:
                    if self.left_click_timer.isActive():
                        self.left_click_timer.stop()
                        self.previous_track()
                    else:
                        self.left_click_timer.start(QApplication.doubleClickInterval())
                return True
            elif key_event.key() == Qt.Key.Key_Right:
                if key_event.isAutoRepeat():
                    self.right_click_timer.stop()
                    self._do_seek_forward()
                else:
                    if self.right_click_timer.isActive():
                        self.right_click_timer.stop()
                        self.next_track()
                    else:
                        self.right_click_timer.start(QApplication.doubleClickInterval())
                return True

        return super().eventFilter(watched, event)

    def update_static_texts(self) -> None:
        self.library_menu.setTitle(self.tr("library_menu"))
        self.open_action.setText(self.tr("choose_library"))
        self.rescan_action.setText(self.tr("rescan"))
        self.quit_action.setText(self.tr("quit"))

        self.search.setPlaceholderText(self.tr("search_placeholder"))
        self.artist_search.setPlaceholderText(self.tr("artist_search_placeholder"))
        self.home_button.setText(self.tr("home_nav"))
        self.search_nav_button.setText(self.tr("search_nav"))
        self.soundcloud_nav_button.setText(self.tr("online_nav"))
        self.library_button.setText(self.tr("library_nav"))
        self.upload_nav_button.setText(self.tr("upload_nav_btn"))
        self.sidebar_caption.setText(self.tr("artists_caption"))
        self.album_caption.setText(self.tr("album_caption"))
        self.hero_caption.setText(self.tr("hero_caption"))
        self.hero_subtitle.setText(self.tr("hero_subtitle_empty"))
        self.hero_play_button.setText(self.tr("play_list"))
        self.hero_rescan_button.setText(self.tr("rescan"))
        self.hero_folder_button.setText(self.tr("choose_folder"))
        if hasattr(self, "hero_sync_button"):
            self.hero_sync_button.setText(self.tr("sync_server_btn"))
        self.language_button.setText(self.tr("language_button"))
        self.track_table.setHorizontalHeaderLabels(
            [
                self.tr("table_title"),
                self.tr("table_artist"),
                self.tr("table_album"),
                self.tr("table_folder"),
                self.tr("table_path"),
            ]
        )
        if hasattr(self, "online_search"):
            self.online_search.setPlaceholderText(self.tr("search_online_placeholder"))
            self.online_search_btn.setText(self.tr("search_nav"))
            self.soundcloud_header.setText(self.tr("online_header"))
            self.soundcloud_table.setHorizontalHeaderLabels(
                [
                    self.tr("table_title"),
                    self.tr("table_artist"),
                    self.tr("table_duration"),
                    self.tr("btn_stream"),
                    self.tr("btn_download"),
                ]
            )
            if hasattr(self, "online_results") and self.online_results:
                self.online_status_label.setText(self.tr("online_status", count=len(self.online_results)))
                for row in range(len(self.online_results)):
                    stream_btn = self.soundcloud_table.cellWidget(row, 3)
                    if isinstance(stream_btn, QPushButton):
                        stream_btn.setText(self.tr("btn_stream_action"))
                    
                    download_btn = self.soundcloud_table.cellWidget(row, 4)
                    if isinstance(download_btn, QPushButton):
                        curr_text = download_btn.text()
                        if curr_text in ("Tải", "Get", "Laden"):
                            download_btn.setText(self.tr("btn_download_action"))
                        elif curr_text in ("Đã tải", "Downloaded", "Heruntergeladen"):
                            download_btn.setText(self.tr("downloaded_status"))
                        elif curr_text in ("Lỗi", "Error", "Fehler"):
                            download_btn.setText(self.tr("error_status"))
        self.prev_button.setToolTip(self.tr("prev"))
        self.play_button.setToolTip(self.tr("play_pause"))
        self.next_button.setToolTip(self.tr("next"))
        # Initial volume icon is set dynamically via set_volume
        self.update_shuffle_text()
        self.now_playing_window.update_language()
        if self.current_track() is None:
            self.now_playing.setText(self.tr("not_playing"))
            self.set_bottom_text(self.tr("not_playing"))
        else:
            self.update_now_playing()
        self.update_path_label()

    def _build_actions(self) -> None:
        self.open_action = QAction(self.tr("choose_library"), self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.choose_library)

        self.rescan_action = QAction(self.tr("rescan"), self)
        self.rescan_action.setShortcut(QKeySequence("Ctrl+R"))
        self.rescan_action.triggered.connect(self.reload_library)

        self.quit_action = QAction(self.tr("quit"), self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)

        self.library_menu = self.menuBar().addMenu(self.tr("library_menu"))
        self.library_menu.addAction(self.open_action)
        self.library_menu.addAction(self.rescan_action)
        self.library_menu.addSeparator()
        self.library_menu.addAction(self.quit_action)
        self.menuBar().hide()

    def _build_ui(self) -> None:
        self.root_widget = QWidget()
        self.root_widget.setObjectName("appRoot")
        main = QVBoxLayout(self.root_widget)
        main.setContentsMargins(12, 12, 12, 0)
        main.setSpacing(12)

        self.path_label = QLabel()
        self.path_label.setObjectName("libraryPath")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.search = QLineEdit()
        self.search.setObjectName("songSearch")
        self.search.textChanged.connect(self.apply_filter)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")
        self.sidebar_widget = QWidget()
        self.sidebar_widget.setObjectName("sidebar")
        self.sidebar_widget.setFixedWidth(190)
        folder_layout = QVBoxLayout(self.sidebar_widget)
        folder_layout.setContentsMargins(8, 16, 8, 16)
        folder_layout.setSpacing(12)
        self.home_button = QPushButton()
        self.home_button.setObjectName("navButton")
        self.home_button.clicked.connect(self.go_home)
        self.search_nav_button = QPushButton()
        self.search_nav_button.setObjectName("navButton")
        self.search_nav_button.clicked.connect(self.focus_search)
        self.soundcloud_nav_button = QPushButton()
        self.soundcloud_nav_button.setObjectName("navButton")
        self.soundcloud_nav_button.clicked.connect(self.show_soundcloud_view)
        self.library_button = QPushButton()
        self.library_button.setObjectName("navButton")
        self.library_button.clicked.connect(self.choose_library)
        self.upload_nav_button = QPushButton()
        self.upload_nav_button.setObjectName("navButton")
        self.upload_nav_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.upload_nav_button.clicked.connect(self.choose_and_upload_file)
        nav_group = QVBoxLayout()
        nav_group.setSpacing(6)
        nav_group.addWidget(self.home_button)
        nav_group.addWidget(self.search_nav_button)
        nav_group.addWidget(self.soundcloud_nav_button)
        nav_group.addWidget(self.library_button)
        nav_group.addWidget(self.upload_nav_button)
        self.sidebar_caption = QLabel()
        self.sidebar_caption.setObjectName("sidebarCaption")
        self.artist_search = QLineEdit()
        self.artist_search.setObjectName("artistSearch")
        self.artist_search.textChanged.connect(self.refresh_artist_filter)
        self.folder_list = QListWidget()
        self.folder_list.currentItemChanged.connect(self.artist_changed)
        self.album_caption = QLabel()
        self.album_caption.setObjectName("sidebarCaption")
        self.album_list = QListWidget()
        self.album_list.setMinimumHeight(150)
        self.album_list.currentItemChanged.connect(self.apply_filter)
        self.language_button = QPushButton()
        self.language_button.setObjectName("languageButton")
        self.language_button.clicked.connect(self.toggle_language)
        sidebar_header = QHBoxLayout()
        sidebar_header.setSpacing(8)
        sidebar_header.addWidget(self.sidebar_caption, 1)
        sidebar_header.addWidget(self.language_button, 0)
        folder_layout.addLayout(sidebar_header)
        folder_layout.addWidget(self.artist_search)
        folder_layout.addWidget(self.search)
        folder_layout.addLayout(nav_group)
        folder_layout.addWidget(self.folder_list, 2)
        folder_layout.addWidget(self.album_caption)
        folder_layout.addWidget(self.album_list, 1)

        self.content_panel = QWidget()
        self.content_panel.setObjectName("contentPanel")
        self.content_panel.setMinimumWidth(510)
        content_layout = QVBoxLayout(self.content_panel)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.content_stack = QStackedWidget()

        self.local_library_page = QWidget()
        local_layout = QVBoxLayout(self.local_library_page)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.setSpacing(12)

        self.hero_panel = QFrame()
        self.hero_panel.setObjectName("heroPanel")
        hero_layout = QHBoxLayout(self.hero_panel)
        hero_layout.setContentsMargins(18, 18, 18, 18)
        hero_layout.setSpacing(18)

        self.cover_frame = QFrame()
        self.cover_frame.setObjectName("coverArt")
        self.cover_frame.setFixedSize(148, 148)
        cover_layout = QVBoxLayout(self.cover_frame)
        cover_layout.setContentsMargins(12, 12, 12, 12)
        cover_layout.addStretch(1)
        self.cover_image = QLabel("♪")
        self.cover_image.setObjectName("coverIcon")
        self.cover_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_image.setScaledContents(True)
        self.cover_image.setFixedSize(100, 100)
        cover_layout.addWidget(self.cover_image)
        self.cover_wave = MusicVisualizer(self.player)
        self.cover_wave.setObjectName("coverWave")
        cover_layout.addWidget(self.cover_wave, 0, Qt.AlignmentFlag.AlignCenter)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(8)
        self.hero_caption = QLabel()
        self.hero_caption.setObjectName("heroCaption")
        self.hero_title = QLabel()
        self.hero_title.setObjectName("heroTitle")
        self.hero_title.setWordWrap(True)
        self.hero_subtitle = QLabel()
        self.hero_subtitle.setObjectName("heroSubtitle")
        self.hero_subtitle.setWordWrap(True)

        hero_actions = QHBoxLayout()
        hero_actions.setSpacing(10)
        self.hero_play_button = QPushButton()
        self.hero_play_button.setObjectName("primaryButton")
        self.hero_play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.hero_play_button.clicked.connect(self.play_visible_first)
        self.hero_rescan_button = QPushButton()
        self.hero_rescan_button.setObjectName("secondaryButton")
        self.hero_rescan_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.hero_rescan_button.clicked.connect(self.reload_library)
        self.hero_folder_button = QPushButton()
        self.hero_folder_button.setObjectName("secondaryButton")
        self.hero_folder_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.hero_folder_button.clicked.connect(self.choose_library)
        
        self.hero_sync_button = QPushButton()
        self.hero_sync_button.setObjectName("secondaryButton")
        self.hero_sync_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon))
        self.hero_sync_button.clicked.connect(self.sync_library_to_server)
        
        from constants import SERVER_URL
        if not SERVER_URL:
            self.hero_sync_button.hide()
            
        hero_actions.addWidget(self.hero_play_button)
        hero_actions.addWidget(self.hero_rescan_button)
        hero_actions.addWidget(self.hero_folder_button)
        hero_actions.addWidget(self.hero_sync_button)
        hero_actions.addStretch(1)

        hero_text.addWidget(self.hero_caption)
        hero_text.addWidget(self.hero_title)
        hero_text.addWidget(self.hero_subtitle)
        hero_text.addLayout(hero_actions)
        hero_text.addStretch(1)

        # New-tracks notification card (daily reset, glassmorphism)
        self.new_tracks_card = NewTracksCard()

        hero_layout.addWidget(self.cover_frame)
        hero_layout.addLayout(hero_text, 1)
        hero_layout.addWidget(self.new_tracks_card, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        self.track_table = QTableWidget(0, 5)
        self.track_table.setObjectName("playlistTable")
        self.track_table.setHorizontalHeaderLabels(["", "", "", "", ""])
        self.track_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.track_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.track_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.track_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.track_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.track_table.setColumnWidth(1, 130)
        self.track_table.setColumnWidth(2, 120)
        self.track_table.setColumnWidth(3, 130)
        self.track_table.verticalHeader().setVisible(False)
        self.track_table.verticalHeader().setDefaultSectionSize(76)
        self.track_table.setIconSize(QSize(46, 46))
        self.track_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.track_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.track_table.setAlternatingRowColors(True)
        self.track_table.setShowGrid(False)
        self.track_table.setMouseTracking(True)
        self.track_table.setColumnHidden(4, True)
        self.track_table.doubleClicked.connect(self.play_selected_row)
        self.track_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_table.customContextMenuRequested.connect(self.show_track_context_menu)

        local_layout.addWidget(self.hero_panel)
        local_layout.addWidget(self.track_table, 1)
        self.content_stack.addWidget(self.local_library_page)

        # SoundCloud Online page
        self.soundcloud_page = QWidget()
        self.soundcloud_page.setObjectName("soundcloudPage")
        soundcloud_layout = QVBoxLayout(self.soundcloud_page)
        soundcloud_layout.setContentsMargins(18, 18, 18, 18)
        soundcloud_layout.setSpacing(12)
        
        self._build_soundcloud_ui(soundcloud_layout)
        self.content_stack.addWidget(self.soundcloud_page)

        content_layout.addWidget(self.content_stack, 1)

        self.main_splitter.addWidget(self.sidebar_widget)
        self.main_splitter.addWidget(self.content_panel)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        main.addWidget(self.main_splitter, 1)

        self.player_bar = QFrame()
        self.player_bar.setObjectName("playerBar")
        self.player_bar.setFrameShape(QFrame.Shape.StyledPanel)
        self.player_bar.setMaximumHeight(86)
        player_layout = QHBoxLayout(self.player_bar)
        player_layout.setContentsMargins(14, 8, 14, 8)
        player_layout.setSpacing(18)

        self.playbar_info_container = QWidget()
        self.playbar_info_container.setObjectName("playbarInfoContainer")
        info_layout = QHBoxLayout(self.playbar_info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(12)

        self.bottom_cover = QLabel("♪")
        self.bottom_cover.setObjectName("bottomCover")
        self.bottom_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bottom_cover.setScaledContents(True)
        self.bottom_cover.setFixedSize(46, 46)

        bottom_text = QVBoxLayout()
        bottom_text.setSpacing(1)
        bottom_text.setContentsMargins(0, 0, 0, 0)
        self.bottom_title = QLabel()
        self.bottom_title.setObjectName("bottomTitle")
        self.bottom_title.setWordWrap(True)
        self.bottom_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.bottom_title.setFixedHeight(36)
        self.bottom_title.setMinimumWidth(170)
        self.bottom_artist = QLabel()
        self.bottom_artist.setObjectName("bottomArtist")
        self.bottom_artist.setWordWrap(True)
        self.bottom_artist.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.bottom_artist.setFixedHeight(16)
        self.bottom_artist.setMinimumWidth(170)
        self.now_playing = QLabel()
        self.now_playing.setObjectName("nowPlaying")
        self.now_playing.setVisible(False)
        bottom_text.addWidget(self.bottom_title)
        bottom_text.addWidget(self.bottom_artist)

        info_layout.addWidget(self.bottom_cover)
        info_layout.addLayout(bottom_text, 1)

        track_info = QHBoxLayout()
        track_info.setSpacing(12)
        track_info.addWidget(self.playbar_info_container, 1)

        self.like_button = self._text_tool_button("+", self.toggle_like_current)
        self.like_button.setCheckable(True)
        self.like_button.setToolTip("Luu / bo luu bai dang phat")
        track_info.addWidget(self.like_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.playbar_center_container = QWidget()
        self.playbar_center_container.setObjectName("playbarCenterContainer")
        center_layout = QVBoxLayout(self.playbar_center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.prev_button = self._player_icon_button("prev", self.previous_track)
        self.play_button = self._player_icon_button("play", self.toggle_play, primary=True)
        self.next_button = self._player_icon_button("next", self.next_track)
        self.repeat_button = self._player_icon_button("repeat", self.toggle_repeat)
        self.repeat_button.setCheckable(True)
        self.repeat_button.setToolTip("Lap lai bai hien tai")
        self.shuffle_button = self._player_icon_button("shuffle")
        self.shuffle_button.setCheckable(True)
        self.shuffle_button.clicked.connect(self.toggle_shuffle)
        buttons.addStretch(1)
        buttons.addWidget(self.shuffle_button, 0, Qt.AlignmentFlag.AlignVCenter)
        buttons.addWidget(self.prev_button, 0, Qt.AlignmentFlag.AlignVCenter)
        buttons.addWidget(self.play_button, 0, Qt.AlignmentFlag.AlignVCenter)
        buttons.addWidget(self.next_button, 0, Qt.AlignmentFlag.AlignVCenter)
        buttons.addWidget(self.repeat_button, 0, Qt.AlignmentFlag.AlignVCenter)
        buttons.addStretch(1)

        timeline = QHBoxLayout()
        timeline.setSpacing(8)
        self.elapsed_label = QLabel("00:00")
        self.elapsed_label.setObjectName("timeLabel")
        self.duration_label = QLabel("00:00")
        self.duration_label.setObjectName("timeLabel")
        self.position_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.position_slider.setObjectName("positionSlider")
        self.position_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.position_slider.sliderPressed.connect(self._start_seek)
        self.position_slider.sliderReleased.connect(self._finish_seek)
        timeline.addWidget(self.elapsed_label)
        timeline.addWidget(self.position_slider, 1)
        timeline.addWidget(self.duration_label)

        center_layout.addLayout(buttons)
        center_layout.addLayout(timeline)

        center_controls = QVBoxLayout()
        center_controls.setSpacing(0)
        center_controls.setContentsMargins(0, 0, 0, 0)
        center_controls.addWidget(self.playbar_center_container)

        volume_controls = QHBoxLayout()
        volume_controls.setSpacing(7)
        volume_controls.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.queue_button = self._text_tool_button("☰", self.focus_track_table)
        self.queue_button.setToolTip("Di toi danh sach bai hat")
        self.queue_button.setStyleSheet("QToolButton#playerButton { font-size: 22px; }")
        self.device_button = self._text_tool_button("⌂", self.choose_library)
        self.device_button.setToolTip("Chon thu muc nhac")
        self.device_button.setStyleSheet("QToolButton#playerButton { font-size: 22px; }")
        self.compact_button = self._text_tool_button("▣", self.toggle_now_playing)
        self.compact_button.setToolTip("Mo cua so dang phat")
        self.fullscreen_button = self._text_tool_button("⛶", self.toggle_fullscreen_view)
        self.fullscreen_button.setToolTip("Bat / tat toan man hinh")
        self.volume_label = self._text_tool_button("\U0001f50a\ufe0e", self.show_audio_menu)
        self.volume_label.setObjectName("playerButton")
        self.volume_label.setToolTip("Am luong va thiet bi dau ra")

        self.audio_popup = AudioDevicePopup(self)

        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("volumeSlider")
        self.volume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(120)
        self.volume.valueChanged.connect(self.set_volume)

        volume_controls.addStretch(1)
        volume_controls.addWidget(self.queue_button)
        volume_controls.addWidget(self.device_button)
        volume_controls.addWidget(self.volume_label)
        volume_controls.addWidget(self.volume)
        volume_controls.addWidget(self.compact_button)
        volume_controls.addWidget(self.fullscreen_button)

        player_layout.addLayout(track_info, 4)
        player_layout.addLayout(center_controls, 4)
        player_layout.addLayout(volume_controls, 3)
        content_layout.addWidget(self.player_bar)

        self.status = QLabel()
        self.status.setObjectName("statusLabel")
        main.addWidget(self.status)
        self.setCentralWidget(self.root_widget)

    def _tool_button(self, icon: QStyle.StandardPixmap, tooltip: str, callback) -> QToolButton:
        button = QToolButton()
        button.setObjectName("playerButton")
        button.setIcon(self.style().standardIcon(icon))
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        button.setIconSize(button.iconSize() * 1.3)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return button

    def _text_tool_button(self, text: str, callback=None) -> QToolButton:
        button = QToolButton()
        button.setObjectName("playerButton")
        button.setText(text)
        button.clicked.connect(lambda _checked=False, cb=callback: cb() if cb else None)
        button.setFixedSize(34, 34)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        return button

    def _player_text_button(self, text: str, callback=None) -> QToolButton:
        button = self._text_tool_button(text, callback)
        button.setObjectName("playerControlButton")
        button.setFixedSize(36, 36)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setAutoRaise(False)
        return button

    def _player_icon_button(self, kind: str, callback=None, primary: bool = False) -> MiniControlButton:
        button = MiniControlButton(kind, callback or (lambda: None), primary)
        button.setObjectName("playerPlayIconButton" if primary else "playerIconButton")
        button.setFixedSize(52 if primary else 36, 52 if primary else 36)
        return button

    def go_home(self) -> None:
        self.search.clear()
        self.artist_search.clear()
        self.select_list_value(self.folder_list, "")
        self.select_list_value(self.album_list, "")
        if hasattr(self, "content_stack"):
            self.content_stack.setCurrentWidget(self.local_library_page)
        self.apply_filter()

    def focus_search(self) -> None:
        if hasattr(self, "content_stack"):
            self.content_stack.setCurrentWidget(self.local_library_page)
        self.search.setFocus()
        self.search.selectAll()

    def focus_track_table(self) -> None:
        self.track_table.setFocus()
        track = self.current_track() or self.last_track
        if track is not None:
            self.highlight_track(track)
        elif self.track_table.rowCount() > 0:
            self.track_table.selectRow(0)

    def toggle_fullscreen_view(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def toggle_like_current(self) -> None:
        track = self.current_track() or self.last_track
        if track is None:
            self.like_button.setChecked(False)
            return
        if track.path in self.liked_tracks:
            self.liked_tracks.remove(track.path)
        else:
            self.liked_tracks.add(track.path)
        self.update_like_button(track)

    def update_like_button(self, track: Track | None = None) -> None:
        track = track or self.current_track() or self.last_track
        liked = bool(track and track.path in self.liked_tracks)
        self.like_button.setChecked(liked)
        self.like_button.setText("✓" if liked else "+")

    def toggle_repeat(self) -> None:
        self.repeat_enabled = not self.repeat_enabled
        self.repeat_button.setChecked(self.repeat_enabled)
        if hasattr(self, "now_playing_window"):
            self.now_playing_window.update_extra_buttons()

    def _apply_effects(self) -> None:
        self.cover_frame.setGraphicsEffect(self._shadow(34, QColor(0, 0, 0, 170), 0, 12))
        self.hero_panel.setGraphicsEffect(self._shadow(42, QColor(0, 0, 0, 120), 0, 18))
        self.player_bar.setGraphicsEffect(self._shadow(28, QColor(0, 0, 0, 150), 0, -2))

    def _shadow(self, blur: int, color: QColor, x_offset: int, y_offset: int) -> QGraphicsDropShadowEffect:
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(blur)
        effect.setColor(color)
        effect.setOffset(x_offset, y_offset)
        return effect


    def _apply_theme(self) -> None:
        style_path = Path(__file__).parent / "style.qss"
        if style_path.exists():
            try:
                with open(style_path, "r", encoding="utf-8") as f:
                    qss = f.read()
                self.setStyleSheet(qss)
                self.menuBar().setStyleSheet(qss)
            except Exception as e:
                print(f"Error loading stylesheet: {e}", file=sys.stderr)

    def _connect_player(self) -> None:
        self.player.positionChanged.connect(self.update_position)
        self.player.positionChanged.connect(self.now_playing_window.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.durationChanged.connect(self.now_playing_window.update_duration)
        self.player.durationChanged.connect(lambda _duration: self.emit_mpris_properties("Metadata"))
        self.player.playbackStateChanged.connect(self.update_play_button)
        self.player.playbackStateChanged.connect(self.now_playing_window.update_play_button)
        self.player.playbackStateChanged.connect(lambda _state: self.emit_mpris_properties("PlaybackStatus"))
        self.player.mediaStatusChanged.connect(self.handle_media_status)
        self.player.errorOccurred.connect(self.show_player_error)

    def setup_mpris(self) -> None:
        if not HAS_DBUS:
            self.mpris_available = False
            return
        self.mpris_root_adaptor = MprisRootAdaptor(self)
        self.mpris_player_adaptor = MprisPlayerAdaptor(self)
        connection = QDBusConnection.sessionBus()
        service_ok = connection.registerService("org.mpris.MediaPlayer2.playlistoffline")
        object_ok = connection.registerObject(
            "/org/mpris/MediaPlayer2",
            self,
            QDBusConnection.RegisterOption.ExportAdaptors,
        )
        self.mpris_available = service_ok and object_ok
        if not self.mpris_available:
            print("MPRIS registration failed. Close other Playlist Offline windows and reopen the app.", file=sys.stderr)

    def emit_mpris_properties(self, *names: str) -> None:
        if not self.mpris_available:
            return

        all_props = {
            "PlaybackStatus": self.mpris_playback_status(),
            "Metadata": self.mpris_metadata(),
            "CanGoNext": bool(self.active_playlist()),
            "CanGoPrevious": bool(self.active_playlist()),
            "CanPlay": bool(self.tracks),
            "CanPause": True,
            "CanSeek": True,
            "CanControl": True,
            "Volume": self.audio.volume(),
            "Shuffle": self.shuffle_enabled,
            "Position": self.player.position() * 1000,
        }
        changed = {name: all_props[name] for name in names if name in all_props}
        if not changed:
            return
        invalidated = ["Position"] if "Position" not in changed else ["Rate"]
        message = QDBusMessage.createSignal(
            "/org/mpris/MediaPlayer2",
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
        )
        message.setArguments(["org.mpris.MediaPlayer2.Player", changed, invalidated])
        QDBusConnection.sessionBus().send(message)

    def shutdown_mpris(self) -> None:
        if not self.mpris_available:
            return
        connection = QDBusConnection.sessionBus()
        connection.unregisterObject("/org/mpris/MediaPlayer2")
        connection.unregisterService("org.mpris.MediaPlayer2.playlistoffline")
        self.mpris_available = False

    def refresh_mpris_metadata(self) -> None:
        self.emit_mpris_properties(
            "Metadata",
            "PlaybackStatus",
            "CanPlay",
            "CanGoNext",
            "CanGoPrevious",
            "CanPause",
            "CanSeek",
            "CanControl",
            "Volume",
            "Shuffle",
        )

    def mpris_playback_status(self) -> str:
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            return "Playing"
        if state == QMediaPlayer.PlaybackState.PausedState:
            return "Paused"
        return "Stopped"

    def mpris_metadata(self) -> dict:
        track = self.mpris_track()
        if track is None:
            return {}

        metadata = {
            "mpris:trackid": self.mpris_track_id(track),
            "xesam:title": track.title,
            "xesam:artist": [track.artist],
            "xesam:album": self.display_album(track.album),
            "xesam:url": (
                self.online_stream_urls.get(track.path.as_posix(), "")
                if track.path.as_posix().startswith("/online/")
                else (
                    f"{SERVER_URL}/audio/{urllib.parse.quote(track.path.as_posix()[8:])}"
                    if SERVER_URL and track.path.as_posix().startswith("/server/")
                    else QUrl.fromLocalFile(str(track.path)).toString()
                )
            ),

        }
        duration = self.player.duration()
        if duration > 0:
            metadata["mpris:length"] = duration * 1000
        art_path = self.track_art_path(track, allow_extract=True)
        if art_path:
            metadata["mpris:artUrl"] = QUrl.fromLocalFile(str(art_path)).toString()
        return metadata

    def mpris_track(self) -> Track | None:
        return (
            self.current_track()
            or self.last_track
            or self.selected_visible_track()
            or (self.visible_tracks[0] if self.visible_tracks else None)
            or (self.tracks[0] if self.tracks else None)
        )

    def mpris_track_id(self, track: Track) -> QDBusObjectPath:
        digest = hashlib.sha1(str(track.path).encode("utf-8")).hexdigest()
        return QDBusObjectPath(f"/org/mpris/MediaPlayer2/Track/{digest}")

    def choose_library(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, self.tr("choose_library"), str(self.library_root))
        if chosen:
            self.library_root = Path(chosen)
            self.reload_library()

    def reload_library(self) -> None:
        from constants import SERVER_URL
        if SERVER_URL:
            import urllib.request
            import json
            try:
                self.status.setText("Đang tải danh sách nhạc từ Server..." if self.language == "vi" else "Loading track list from Server...")
                with urllib.request.urlopen(f"{SERVER_URL}/tracks", timeout=5) as response:
                    raw_tracks = json.loads(response.read().decode("utf-8"))
                
                self.tracks = []
                for t in raw_tracks:
                    self.tracks.append(
                        Track(
                            path=Path(t["path"]),
                            title=t["title"],
                            folder=t["folder"],
                            artist=t["artist"],
                            album=t["album"],
                            art_path=None
                        )
                    )
                self.set_status_notification("Tải danh sách nhạc thành công!" if self.language == "vi" else "Track list loaded successfully!", "success")
            except Exception as e:
                print(f"Server connection failed: {e}. Falling back to local offline library.", flush=True)
                self.set_status_notification("Lỗi kết nối Server. Đang quét nhạc trong máy..." if self.language == "vi" else "Server connection failed. Scanning local music...", "error")
                self.tracks = scan_library(self.library_root)
                QMessageBox.warning(
                    self, 
                    "Lỗi kết nối Server" if self.language == "vi" else "Server Connection Error", 
                    f"Không kết nối được tới Server nhạc: {e}\nĐã tự động chuyển sang thư viện ngoại tuyến." if self.language == "vi" else f"Could not connect to the music server: {e}\nAutomatically switched to offline local library."
                )
        else:
            self.tracks = scan_library(self.library_root)
            
        self.current_index = -1
        self.update_path_label()
        self._detect_new_tracks()
        self.populate_folders()
        self.populate_albums()
        self.apply_filter(switch_page=False)
        self.emit_mpris_properties("Metadata", "CanPlay", "CanGoNext", "CanGoPrevious")


    def _detect_new_tracks(self) -> None:
        """Compare current tracks to daily-reset cache; show notification if new artists/tracks found."""
        import json
        from datetime import date

        if sys.platform == "win32":
            import os
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                cache_dir = Path(local_appdata) / "playlist_offline"
            else:
                cache_dir = Path.home() / "AppData" / "Local" / "playlist_offline"
        else:
            cache_dir = Path.home() / ".local" / "share" / "playlist_offline"

        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            import tempfile
            cache_dir = Path(tempfile.gettempdir()) / "playlist_offline"
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                cache_dir = Path(__file__).parent / ".cover_cache"

        cache_file = cache_dir / "seen_tracks.json"

        today = str(date.today())
        current_paths = {str(t.path): t.artist for t in self.tracks}

        # Load existing cache
        cache = {}
        if cache_file.exists():
            try:
                cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                cache = {}

        # Reset daily
        if cache.get("date") != today:
            cache = {"date": today, "seen": {}}

        seen: dict = cache.get("seen", {})

        # Find tracks not in seen set
        new_by_artist: dict[str, int] = {}
        for path, artist in current_paths.items():
            if path not in seen:
                new_by_artist[artist] = new_by_artist.get(artist, 0) + 1

        # Save updated seen set
        cache["seen"] = current_paths
        try:
            cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        # Update notification card
        if new_by_artist and hasattr(self, "new_tracks_card"):
            lines = []
            for artist, count in sorted(new_by_artist.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"🎵 {artist}: +{count} bài mới")
            if len(new_by_artist) > 5:
                lines.append(f"… và {len(new_by_artist) - 5} nghệ sĩ khác")
            self.new_tracks_card.set_lines(lines)
            self.new_tracks_card.show()
        elif hasattr(self, "new_tracks_card"):
            self.new_tracks_card.clear()

    def update_path_label(self) -> None:
        from constants import SERVER_URL
        if SERVER_URL:
            self.path_label.setText(self.tr("library_path", path=f"Server: {SERVER_URL}"))
        else:
            self.path_label.setText(self.tr("library_path", path=self.library_root))


    def populate_folders(self) -> None:
        artist_query = search_text(self.artist_search.text().strip())
        current_item = self.folder_list.currentItem()
        current_artist = current_item.data(Qt.ItemDataRole.UserRole) if current_item else ""

        self.folder_list.blockSignals(True)
        self.folder_list.clear()
        local_tracks = [t for t in self.tracks if not t.path.as_posix().startswith("/online/")]
        all_item = QListWidgetItem(self.tr("all_artists", count=len(local_tracks)))
        all_item.setData(Qt.ItemDataRole.UserRole, "")
        self.folder_list.addItem(all_item)

        folders: dict[str, int] = {}
        for track in self.tracks:
            if track.path.as_posix().startswith("/online/"):
                continue
            folders[track.artist] = folders.get(track.artist, 0) + 1


        next_row = 0
        for folder, count in sorted(folders.items(), key=lambda item: search_text(item[0])):
            if artist_query and artist_query not in search_text(folder):
                continue
            item = QListWidgetItem(f"{folder} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, folder)
            self.folder_list.addItem(item)
            if folder == current_artist:
                next_row = self.folder_list.count() - 1

        self.folder_list.setCurrentRow(next_row)
        self.folder_list.blockSignals(False)

    def refresh_artist_filter(self) -> None:
        self.populate_folders()
        self.populate_albums()
        self.apply_filter()

    def artist_changed(self) -> None:
        self.populate_albums()
        self.apply_filter()

    def populate_albums(self) -> None:
        folder_item = self.folder_list.currentItem()
        selected_artist = folder_item.data(Qt.ItemDataRole.UserRole) if folder_item else ""
        current_item = self.album_list.currentItem()
        current_album = current_item.data(Qt.ItemDataRole.UserRole) if current_item else ""

        album_counts: dict[str, int] = {}
        for track in self.tracks:
            if track.path.as_posix().startswith("/online/"):
                continue
            if selected_artist and track.artist != selected_artist:
                continue
            album_counts[track.album] = album_counts.get(track.album, 0) + 1

        self.album_list.blockSignals(True)
        self.album_list.clear()
        all_item = QListWidgetItem(self.tr("all_albums", count=sum(album_counts.values())))
        all_item.setData(Qt.ItemDataRole.UserRole, "")
        self.album_list.addItem(all_item)

        next_row = 0
        for album, count in sorted(album_counts.items(), key=lambda item: search_text(item[0])):
            item = QListWidgetItem(f"{self.display_album(album)} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, album)
            self.album_list.addItem(item)
            if album == current_album:
                next_row = self.album_list.count() - 1

        self.album_list.setCurrentRow(next_row)
        self.album_list.blockSignals(False)

    def apply_filter(self, switch_page: bool = True) -> None:
        if switch_page and hasattr(self, "content_stack") and self.content_stack.currentWidget() != self.local_library_page:
            self.content_stack.setCurrentWidget(self.local_library_page)
        query = search_text(self.search.text().strip())
        artist_query = search_text(self.artist_search.text().strip())
        folder_item = self.folder_list.currentItem()
        selected_artist = folder_item.data(Qt.ItemDataRole.UserRole) if folder_item else ""
        album_item = self.album_list.currentItem()
        selected_album = album_item.data(Qt.ItemDataRole.UserRole) if album_item else ""

        def matches(track: Track) -> bool:
            if track.path.as_posix().startswith("/online/"):
                return False
            if selected_artist and track.artist != selected_artist:
                return False
            if selected_album and track.album != selected_album:
                return False
            if artist_query and artist_query not in search_text(track.artist):
                return False
            if query and query not in search_text(track.title):
                return False
            return True

        self.visible_tracks = [track for track in self.tracks if matches(track)]
        self.track_table.setUpdatesEnabled(False)
        self.track_table.setRowCount(len(self.visible_tracks))
        for row, track in enumerate(self.visible_tracks):
            self._set_track_title_cell(row, track)
            self._set_cell(row, 1, track.artist)
            self._set_cell(row, 2, self.display_album(track.album))
            self._set_cell(row, 3, self.display_folder(track.folder))
            self._set_cell(row, 4, str(track.path))
            self.update_track_row_height(row, track)
        self.track_table.setUpdatesEnabled(True)
        self.status.setText(self.tr("status", visible=len(self.visible_tracks), total=len(self.tracks)))
        self.update_hero()

    def update_hero(self) -> None:
        artists = {track.artist for track in self.tracks}
        folder_item = self.folder_list.currentItem()
        selected_artist = folder_item.data(Qt.ItemDataRole.UserRole) if folder_item else ""
        album_item = self.album_list.currentItem()
        selected_album = album_item.data(Qt.ItemDataRole.UserRole) if album_item else ""
        if selected_artist:
            albums = {track.album for track in self.tracks if track.artist == selected_artist}
        else:
            albums = {(track.artist, track.album) for track in self.tracks}
        title_parts = [selected_artist] if selected_artist else []
        if selected_album:
            title_parts.append(self.display_album(selected_album))
        self.hero_title.setText(" - ".join(title_parts) if title_parts else self.tr("hero_title_default"))
        self.hero_subtitle.setText(self.tr("hero_subtitle", path=self.library_root))
        display_track = self.current_track()
        if display_track is None and self.visible_tracks:
            display_track = self.visible_tracks[0]
        self.set_cover_image(display_track)

    def _set_cell(self, row: int, column: int, text: str, icon: QIcon | None = None) -> None:
        item = QTableWidgetItem(text)
        if icon is not None:
            item.setIcon(icon)
        if column == 0:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setForeground(QBrush(QColor("#ffffff")))
        else:
            item.setForeground(QBrush(QColor("#b3b3b3")))
        item.setToolTip(text)
        self.track_table.setItem(row, column, item)

    def _set_track_title_cell(self, row: int, track: Track) -> None:
        cell = QWidget()
        cell.setObjectName("trackTitleCell")
        cell.setToolTip(track.title)
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        cover = QLabel()
        cover.setObjectName("trackTitleCover")
        cover.setFixedSize(46, 46)
        cover.setScaledContents(True)
        cover.setPixmap(self.safe_track_pixmap(track, 46, allow_extract=True))
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title = QLabel()
        title.setObjectName("trackTitleText")
        title.setWordWrap(False)
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title.setText(self.table_title_text(track, row))
        title.setToolTip(track.title)

        artist = QLabel()
        artist.setObjectName("trackSubtitleText")
        artist.setWordWrap(False)
        artist.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        width = self.table_title_text_width()
        sub_font = QFont()
        sub_font.setPixelSize(11)
        sub_metrics = QFontMetrics(sub_font)
        full_text = f"{track.artist} · {self.display_album(track.album)}"
        artist.setText(sub_metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, width))
        artist.setToolTip(full_text)

        text_layout.addStretch(1)
        text_layout.addWidget(title)
        text_layout.addWidget(artist)
        text_layout.addStretch(1)
        layout.addWidget(cover)
        layout.addLayout(text_layout, 1)
        self.track_table.setCellWidget(row, 0, cell)

        item = QTableWidgetItem("")
        item.setData(Qt.ItemDataRole.UserRole, str(track.path))
        item.setToolTip(track.title)
        self.track_table.setItem(row, 0, item)

    def table_title_text(self, track: Track, row: int) -> str:
        width = self.table_title_text_width()
        font = QFont()
        font.setPixelSize(12)
        font.setBold(True)
        metrics = QFontMetrics(font)
        return metrics.elidedText(track.title, Qt.TextElideMode.ElideRight, width)

    def table_title_text_width(self) -> int:
        column_width = self.track_table.columnWidth(0)
        if column_width <= 0:
            column_width = max(320, self.track_table.viewport().width() // 2)
        return max(120, column_width - 92)

    def update_track_row_height(self, row: int, track: Track) -> None:
        self.track_table.setRowHeight(row, 76)

    def refresh_track_title_cells(self) -> None:
        width = self.table_title_text_width()
        sub_font = QFont()
        sub_font.setPixelSize(11)
        sub_metrics = QFontMetrics(sub_font)
        for row, track in enumerate(self.visible_tracks):
            widget = self.track_table.cellWidget(row, 0)
            if widget is None:
                continue
            title = widget.findChild(QLabel, "trackTitleText")
            if title is not None:
                title.setText(self.table_title_text(track, row))
            artist = widget.findChild(QLabel, "trackSubtitleText")
            if artist is not None:
                full_text = f"{track.artist} · {self.display_album(track.album)}"
                artist.setText(sub_metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, width))
            self.update_track_row_height(row, track)

    def display_album(self, album: str) -> str:
        return self.tr("singles") if album == "Singles" else album

    def display_folder(self, folder: str) -> str:
        return self.tr("root_folder") if folder == "Library" else folder

    def current_track(self) -> Track | None:
        # If an online track is actively playing, return it as the current track
        if self.current_online_track is not None and self.last_track is self.current_online_track:
            return self.current_online_track
        if 0 <= self.current_index < len(self.tracks):
            return self.tracks[self.current_index]
        return None

    def track_icon(self, track: Track, size: int, allow_extract: bool = False) -> QIcon:
        key = (self.art_key(track, allow_extract), size)
        cached = self.art_cache.get(key)
        if cached is not None:
            return cached
        icon = QIcon(self.safe_track_pixmap(track, size, allow_extract))
        self.art_cache[key] = icon
        return icon

    def safe_track_pixmap(self, track: Track, size: int, allow_extract: bool = False) -> QPixmap:
        try:
            return self.track_pixmap(track, size, allow_extract)
        except Exception as exc:
            print(f"Artwork load failed for {track.path}: {exc}", file=sys.stderr)
            return self.default_art_pixmap(track, size)

    def track_pixmap(self, track: Track, size: int, allow_extract: bool = False) -> QPixmap:
        key = (self.art_key(track, allow_extract), size)
        cached = self.pixmap_cache.get(key)
        if cached is not None:
            return cached

        art_path = self.track_art_path(track, allow_extract)
        if art_path:
            source = QPixmap(str(art_path))
            if not source.isNull():
                pixmap = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                if pixmap.width() != size or pixmap.height() != size:
                    x = max(0, (pixmap.width() - size) // 2)
                    y = max(0, (pixmap.height() - size) // 2)
                    pixmap = pixmap.copy(x, y, size, size)
                self.pixmap_cache[key] = pixmap
                return pixmap

        pixmap = self.default_art_pixmap(track, size)
        self.pixmap_cache[key] = pixmap
        return pixmap

    def track_art_path(self, track: Track, allow_extract: bool = False) -> Path | None:
        custom_path = get_custom_cover_path(track.path)
        if custom_path:
            return custom_path
        
        path_str = str(track.path)
        is_server = path_str.startswith("/server/")
        
        if not is_server and track.art_path and track.art_path.exists():
            return track.art_path
            
        cached = embedded_art_cache_path(track.path)
        if cached.exists():
            return cached
            
        if is_server:
            from constants import SERVER_URL
            if SERVER_URL:
                if not hasattr(self, "_in_progress_covers"):
                    self._in_progress_covers = set()
                if path_str not in self._in_progress_covers:
                    self._in_progress_covers.add(path_str)
                    from urllib.parse import quote
                    relative_part = path_str[len("/server/"):]
                    cover_url = f"{SERVER_URL}/cover/{quote(relative_part)}"
                    QTimer.singleShot(0, lambda: self.async_cache_online_art(cover_url, cached))
                    
        if allow_extract and not is_server:
            return extract_embedded_art(track.path)
        return None



    def art_key(self, track: Track, allow_extract: bool = False) -> str:
        art_path = self.track_art_path(track, allow_extract)
        if art_path:
            try:
                return f"file:{art_path}:{art_path.stat().st_mtime_ns}"
            except OSError:
                return f"file:{art_path}"
        return f"default:{track.artist}:{track.album}:{track.title}"

    def default_art_pixmap(self, track: Track, size: int) -> QPixmap:
        digest = hashlib.sha1(f"{track.artist}|{track.album}|{track.title}".encode("utf-8")).digest()
        color_a = QColor(70 + digest[0] % 120, 40 + digest[1] % 120, 90 + digest[2] % 120)
        color_b = QColor(20 + digest[3] % 80, 110 + digest[4] % 120, 80 + digest[5] % 100)

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, size, size)
        gradient.setColorAt(0, color_a)
        gradient.setColorAt(1, color_b)
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, size, size, max(6, size // 10), max(6, size // 10))

        label = search_text(track.artist or track.album or track.title)[:1].upper() or "♪"
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(max(18, size // 3))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
        return pixmap

    def set_cover_image(self, track: Track | None) -> None:
        if track is None:
            self.cover_image.setText("♪")
            self.cover_image.setPixmap(QPixmap())
            return
        self.cover_image.setText("")
        pixmap = self.safe_track_pixmap(track, 100, allow_extract=True)
        self.cover_image.setPixmap(pixmap)
        
        # Synchronize track list cover icon immediately
        if hasattr(self, "visible_tracks") and track in self.visible_tracks:
            try:
                row = self.visible_tracks.index(track)
                widget = self.track_table.cellWidget(row, 0)
                if widget:
                    cover_label = widget.findChild(QLabel, "trackTitleCover")
                    if cover_label:
                        cover_label.setPixmap(self.safe_track_pixmap(track, 46, allow_extract=True))
            except Exception:
                pass

    def register_extracted_cover(self, track: Track) -> None:
        # Clear the old default/fallback pixmap caches for this track
        keys_to_remove = [k for k in self.pixmap_cache.keys() if k[0].startswith("default:") and track.title in k[0]]
        for k in keys_to_remove:
            self.pixmap_cache.pop(k, None)
            
        keys_to_remove_art = [k for k in self.art_cache.keys() if k[0].startswith("default:") and track.title in k[0]]
        for k in keys_to_remove_art:
            self.art_cache.pop(k, None)
            
        # Update the cover image in the player bar (bottom bar)
        self.set_bottom_cover(track)
        
        # Update the cover image in the side player info
        self.set_cover_image(track)
        
        # Update the theme/background colors of the app
        self.update_dynamic_background(track)
        
        # Update the Now Playing window components
        if getattr(self, "now_playing_window", None) is not None:
            try:
                self.now_playing_window.update_track(track)
            except Exception:
                pass
        
        # Update the cover image in the track table row
        if hasattr(self, "visible_tracks") and track in self.visible_tracks:
            try:
                row = self.visible_tracks.index(track)
                widget = self.track_table.cellWidget(row, 0)
                if widget:
                    cover_label = widget.findChild(QLabel, "trackTitleCover")
                    if cover_label:
                        cover_label.setPixmap(self.safe_track_pixmap(track, 46, allow_extract=True))
            except Exception:
                pass

    def set_bottom_cover(self, track: Track | None) -> None:
        if track is None:
            self.bottom_cover.setText("♪")
            self.bottom_cover.setPixmap(QPixmap())
            return
        pixmap = self.bottom_track_pixmap(track, 46)
        self.bottom_cover.setText("")
        self.bottom_cover.setPixmap(pixmap)

    def bottom_track_pixmap(self, track: Track, size: int) -> QPixmap:
        art_path = self.track_art_path(track, allow_extract=True)
        if art_path:
            source = QPixmap(str(art_path))
            if not source.isNull():
                pixmap = source.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if pixmap.width() != size or pixmap.height() != size:
                    x = max(0, (pixmap.width() - size) // 2)
                    y = max(0, (pixmap.height() - size) // 2)
                    pixmap = pixmap.copy(x, y, size, size)
                return pixmap
        return self.neutral_bottom_pixmap(track, size)

    def neutral_bottom_pixmap(self, track: Track, size: int) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, size, size)
        gradient.setColorAt(0, QColor("#3a3a3a"))
        gradient.setColorAt(1, QColor("#181818"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, size, size, max(6, size // 8), max(6, size // 8))

        label = search_text(track.artist or track.album or track.title)[:1].upper() or "♪"
        painter.setPen(QColor("#f0f0f0"))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(max(16, size // 3))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
        return pixmap

    def set_bottom_text(self, title: str, artist: str = "") -> None:
        self.set_fitted_bottom_label(self.bottom_title, title, 10, 8, 2, bold=True)
        self.set_fitted_bottom_label(self.bottom_artist, artist, 9, 8, 1, bold=False)

    def set_fitted_bottom_label(
        self,
        label: QLabel,
        text: str,
        max_size: int,
        min_size: int,
        max_lines: int,
        bold: bool,
    ) -> None:
        width = max(120, label.width() - 4)
        for size in range(max_size, min_size - 1, -1):
            font = label.font()
            font.setPixelSize(size)
            font.setBold(bold)
            metrics = QFontMetrics(font)
            wrapped = self.wrap_text_for_width(text, metrics, width, max_lines)
            if wrapped and metrics.boundingRect(0, 0, width, 1000, Qt.TextFlag.TextWordWrap, wrapped).height() <= label.height() - 6:
                label.setFont(font)
                label.setText(wrapped)
                label.setToolTip(text)
                return

        font = label.font()
        font.setPixelSize(min_size)
        font.setBold(bold)
        label.setFont(font)
        label.setText(self.wrap_text_for_width(text, QFontMetrics(font), width, max_lines) or text)
        label.setToolTip(text)

    def wrap_text_for_width(self, text: str, metrics: QFontMetrics, width: int, max_lines: int) -> str:
        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            chunks = self.split_word_for_width(word, metrics, width)
            for chunk in chunks:
                candidate = f"{current} {chunk}".strip()
                if metrics.horizontalAdvance(candidate) <= width or not current:
                    current = candidate
                    continue
                lines.append(current)
                if len(lines) >= max_lines:
                    return "\n".join(lines)
                current = chunk

        if current and len(lines) < max_lines:
            lines.append(current)
        return "\n".join(lines)

    def split_word_for_width(self, word: str, metrics: QFontMetrics, width: int) -> list[str]:
        if metrics.horizontalAdvance(word) <= width:
            return [word]
        chunks: list[str] = []
        current = ""
        for char in word:
            candidate = current + char
            if metrics.horizontalAdvance(candidate) <= width or not current:
                current = candidate
                continue
            chunks.append(current)
            current = char
        if current:
            chunks.append(current)
        return chunks

    def play_visible_first(self) -> None:
        if not self.visible_tracks:
            return
        selected = self.selected_visible_track()
        track = selected or self.visible_tracks[0]
        self.current_index = self.tracks.index(track)
        self.play_track(track)

    def play_selected_row(self) -> None:
        row = self.track_table.currentRow()
        if row < 0 or row >= len(self.visible_tracks):
            return
        track = self.visible_tracks[row]
        self.current_index = self.tracks.index(track)
        self.play_track(track)

    def play_track(self, track: Track, manual: bool = True) -> None:
        if manual:
            self.auto_paused_by_other_media = False
        # Update or clear current_online_track
        if track.path.as_posix().startswith("/online/"):
            self.current_online_track = track
        else:
            self.current_online_track = None
        if track in self.tracks:
            self.current_index = self.tracks.index(track)
        self.last_track = track
        self.paused_position = 0
        self.resume_token += 1
        path_str = track.path.as_posix()
        if path_str.startswith("/online/"):
            stream_url = self.online_stream_urls.get(path_str)
            if stream_url:
                self.player.setSource(QUrl(stream_url))
                self.player.play()
            else:
                self.resolve_and_play_online(track)
                return
        elif path_str.startswith("/server/"):
            from constants import SERVER_URL
            from urllib.parse import quote
            relative_part = path_str[len("/server/"):]
            stream_url = f"{SERVER_URL}/audio/{quote(relative_part)}"
            self.player.setSource(QUrl(stream_url))
            self.player.play()
        else:
            self.player.setSource(QUrl.fromLocalFile(path_str))
            self.player.play()

        self.update_now_playing(track)
        self.set_cover_image(track)
        self.show_now_playing(track)
        if getattr(self, "mini_player", None) is not None:
            self.mini_player.update_track_info()
        self.emit_mpris_properties("Metadata", "PlaybackStatus", "CanGoNext", "CanGoPrevious", "CanPlay")
        self.highlight_track(track)

    def show_now_playing(self, track: Track | None = None) -> None:
        track = track or self.current_track()
        if track is None:
            return
            
        self.now_playing_window.update_track(track)
        self.now_playing_window.update_duration(self.player.duration())
        self.now_playing_window.update_position(self.player.position())
        self.now_playing_window.update_play_button()
        
        if hasattr(self, "playbar_center_container"):
            self.playbar_center_container.setVisible(False)
        if hasattr(self, "playbar_info_container"):
            self.playbar_info_container.setVisible(False)
            
        self.now_playing_window.show()
        
        if getattr(self, "splitter_animation", None) is not None:
            self.splitter_animation.stop()
            
        start_sizes = self.main_splitter.sizes()
        current_np_width = start_sizes[2] if len(start_sizes) > 2 else 0
        
        self.splitter_animation = QVariantAnimation(self)
        self.splitter_animation.setStartValue(current_np_width)
        target_width = getattr(self, "preferred_now_playing_width", 320)
        self.splitter_animation.setEndValue(target_width)
        self.splitter_animation.setDuration(350)
        self.splitter_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        def update_sizes(val):
            w = self.width()
            sidebar_w = start_sizes[0] if start_sizes else 190
            middle_w = max(0, w - sidebar_w - val)
            self.main_splitter.setSizes([sidebar_w, middle_w, val])
            
        self.splitter_animation.valueChanged.connect(update_sizes)
        self.splitter_animation.start()

    def hide_now_playing(self) -> None:
        if getattr(self, "splitter_animation", None) is not None:
            self.splitter_animation.stop()
            
        start_sizes = self.main_splitter.sizes()
        current_np_width = start_sizes[2] if len(start_sizes) > 2 else 0
        
        self.splitter_animation = QVariantAnimation(self)
        self.splitter_animation.setStartValue(current_np_width)
        self.splitter_animation.setEndValue(0)
        self.splitter_animation.setDuration(350)
        self.splitter_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        def update_sizes(val):
            w = self.width()
            sidebar_w = start_sizes[0] if start_sizes else 190
            middle_w = max(0, w - sidebar_w - val)
            self.main_splitter.setSizes([sidebar_w, middle_w, val])
            
        def on_finished():
            self.now_playing_window.hide()
            if hasattr(self, "playbar_center_container"):
                self.playbar_center_container.setVisible(True)
            if hasattr(self, "playbar_info_container"):
                self.playbar_info_container.setVisible(True)
                
        self.splitter_animation.valueChanged.connect(update_sizes)
        self.splitter_animation.finished.connect(on_finished)
        self.splitter_animation.start()

    def toggle_now_playing(self) -> None:
        is_animating_to_hide = False
        if getattr(self, "splitter_animation", None) is not None and self.splitter_animation.state() == QVariantAnimation.State.Running:
            if self.splitter_animation.endValue() == 0:
                is_animating_to_hide = True
                
        if self.now_playing_window.isVisible() and not is_animating_to_hide:
            self.hide_now_playing()
        else:
            self.show_now_playing()


    def update_now_playing(self, track: Track | None = None) -> None:
        track = track or self.current_track()
        self.update_dynamic_background(track)
        if track is None:
            self.now_playing.setText(self.tr("not_playing"))
            self.set_bottom_text(self.tr("not_playing"))
            self.set_bottom_cover(None)
            return
        self.now_playing.setText(
            self.tr("now_playing", title=track.title, artist=track.artist, album=self.display_album(track.album))
        )
        self.set_bottom_text(track.title, f"{track.artist} · {self.display_album(track.album)}")
        self.set_bottom_cover(track)
        self.update_like_button(track)

    def update_dynamic_background(self, track: Track | None) -> None:
        if not hasattr(self, "content_panel") or not hasattr(self, "now_playing_window") or not hasattr(self, "sidebar_widget") or not hasattr(self, "root_widget"):
            return

        if track is None:
            target_colors = {
                "bg_window": QColor("#070b13"),
                "bg_sidebar": QColor("#0a0e17"),
                "bg_border": QColor("#1a2333"),
                "gradient_start": QColor("#0e1320"),
                "bg_dark": QColor("#0e1320"),
                "accent": QColor("#1d90f4"),
            }
        else:
            cover = self.safe_track_pixmap(track, 360, allow_extract=True)
            accent = self.now_playing_window.extract_accent_color(cover)
            
            hue, saturation, value, _alpha = accent.getHsv()
            if hue < 0:
                hue = 208
            
            # Generate the dynamic palette based on the accent color
            # 1. content_panel top gradient color (vibrant accent color)
            sat_gradient = min(220, max(100, int(saturation * 1.05)))
            val_gradient = min(85, max(38, int(value * 0.45)))
            gradient_start = QColor.fromHsv(hue, sat_gradient, val_gradient)
            
            # 2. content_panel base color (vibrant dark/deep accent version)
            sat_dark = min(200, max(70, int(saturation * 0.85)))
            val_dark = min(32, max(16, int(value * 0.24)))
            bg_dark = QColor.fromHsv(hue, sat_dark, val_dark)
            
            # 3. main window background (slightly darker than content panel)
            sat_window = min(200, max(70, int(saturation * 0.85)))
            val_window = min(24, max(12, int(value * 0.18)))
            bg_window = QColor.fromHsv(hue, sat_window, val_window)
            
            # 4. sidebar and playerBar background (slightly lighter than window, darker than content panel)
            sat_sidebar = min(200, max(70, int(saturation * 0.85)))
            val_sidebar = min(28, max(14, int(value * 0.20)))
            bg_sidebar = QColor.fromHsv(hue, sat_sidebar, val_sidebar)
            
            # 5. borders (subtle tint of the color)
            sat_border = min(200, max(70, int(saturation * 0.85)))
            val_border = min(50, max(26, int(value * 0.35)))
            bg_border = QColor.fromHsv(hue, sat_border, val_border)

            target_colors = {
                "bg_window": bg_window,
                "bg_sidebar": bg_sidebar,
                "bg_border": bg_border,
                "gradient_start": gradient_start,
                "bg_dark": bg_dark,
                "accent": accent,
            }

        if not self.isVisible():
            self.animate_colors(1.0, self.current_colors, target_colors)
            return

        if getattr(self, "bg_animation", None) is not None:
            self.bg_animation.stop()

        start_colors = self.current_colors.copy()

        self.bg_animation = QVariantAnimation(self)
        self.bg_animation.setStartValue(0.0)
        self.bg_animation.setEndValue(1.0)
        self.bg_animation.setDuration(450)
        self.bg_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.bg_animation.valueChanged.connect(
            lambda t: self.animate_colors(t, start_colors, target_colors)
        )
        self.bg_animation.start()

    def animate_colors(self, t: float, start_colors: dict, target_colors: dict) -> None:
        def interp(c1: QColor, c2: QColor) -> QColor:
            r = int(c1.red() + t * (c2.red() - c1.red()))
            g = int(c1.green() + t * (c2.green() - c1.green()))
            b = int(c1.blue() + t * (c2.blue() - c1.blue()))
            return QColor(r, g, b)

        current_bg_window = interp(start_colors["bg_window"], target_colors["bg_window"])
        current_bg_sidebar = interp(start_colors["bg_sidebar"], target_colors["bg_sidebar"])
        current_bg_border = interp(start_colors["bg_border"], target_colors["bg_border"])
        current_gradient_start = interp(start_colors["gradient_start"], target_colors["gradient_start"])
        current_bg_dark = interp(start_colors["bg_dark"], target_colors["bg_dark"])
        current_accent = interp(start_colors["accent"], target_colors["accent"])

        self.current_colors = {
            "bg_window": current_bg_window,
            "bg_sidebar": current_bg_sidebar,
            "bg_border": current_bg_border,
            "gradient_start": current_gradient_start,
            "bg_dark": current_bg_dark,
            "accent": current_accent,
        }

        self.current_bg_sidebar = current_bg_sidebar
        self.current_bg_border = current_bg_border
        self.current_accent = current_accent

        self.root_widget.setStyleSheet(f"QWidget#appRoot {{ background: {current_bg_window.name()}; }}")
        self.sidebar_widget.setStyleSheet(f"QWidget#sidebar {{ background: {current_bg_sidebar.name()}; }}")
        self.player_bar.setStyleSheet(f"QFrame#playerBar {{ background: {current_bg_sidebar.name()}; border: 1px solid {current_bg_border.name()}; }}")
        self.content_panel.setStyleSheet(
            f"QWidget#contentPanel {{"
            f"    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {current_gradient_start.name()}, stop:0.45 {current_bg_dark.name()}, stop:1 {current_bg_dark.name()});"
            f"    border-radius: 14px;"
            f"}}"
        )
        self.cover_frame.setStyleSheet(
            f"QFrame#coverArt {{"
            f"    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {current_accent.name()}, stop:1 #000000);"
            f"    border-radius: 14px;"
            f"    border: 1px solid {current_bg_border.name()};"
            f"}}"
        )
        
        # Dynamically theme hero buttons in sidebar/playlist
        accent_hex = current_accent.name()
        h, s, v, a = current_accent.getHsv()
        v_hover = min(255, int(v * 1.15)) if v < 220 else max(0, int(v * 0.85))
        accent_hover = QColor.fromHsv(h, s, v_hover, a).name()
        v_pressed = max(0, int(v * 0.80))
        accent_pressed = QColor.fromHsv(h, s, v_pressed, a).name()
        
        self.hero_play_button.setStyleSheet(f"""
            QPushButton#primaryButton {{
                background: {accent_hex};
                color: #ffffff;
                border: 1px solid {accent_hex};
                border-radius: 20px;
                padding: 10px 18px;
                min-height: 20px;
                font-weight: 850;
            }}
            QPushButton#primaryButton:hover {{
                background: {accent_hover};
                border-color: {accent_hover};
            }}
            QPushButton#primaryButton:pressed {{
                background: {accent_pressed};
                border-color: {accent_pressed};
            }}
        """)
        
        secondary_hover_style = f"""
            QPushButton#secondaryButton {{
                background: rgba(255, 255, 255, 0.06);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 20px;
                padding: 10px 18px;
                min-height: 20px;
                font-weight: 650;
            }}
            QPushButton#secondaryButton:hover {{
                background: rgba(255, 255, 255, 0.10);
                border-color: {accent_hex};
                color: {accent_hex};
            }}
        """
        self.hero_rescan_button.setStyleSheet(secondary_hover_style)
        self.hero_folder_button.setStyleSheet(secondary_hover_style)

        if hasattr(self, "new_tracks_card"):
            self.new_tracks_card.set_accent(current_accent)
        if hasattr(self, "cover_wave"):
            self.cover_wave.set_accent(current_accent)
        if getattr(self, "mini_player", None) is not None:
            try:
                self.mini_player.update_theme(current_accent, current_gradient_start, current_bg_dark, current_bg_border)
            except Exception:
                pass


    def highlight_track(self, track: Track) -> None:
        # Online/SoundCloud tracks are not in the local library table — skip entirely
        if track.path.as_posix().startswith("/online/"):
            return
        
        row = self.visible_row_for_track(track)
        if row is None:
            self.show_track_in_library(track)
            row = self.visible_row_for_track(track)

        if row is None:
            return

        item = self.track_table.item(row, 0)
        if item is None:
            return

        self.track_table.selectRow(row)
        self.track_table.scrollToItem(item)

    def visible_row_for_track(self, track: Track) -> int | None:
        for row, visible in enumerate(self.visible_tracks):
            if visible.path == track.path:
                return row
        return None

    def show_track_in_library(self, track: Track) -> None:
        query = self.search.text().strip()
        haystack = search_text(f"{track.title} {track.artist} {track.album} {track.folder} {track.path}")
        if query and search_text(query) not in haystack:
            self.search.clear()

        if self.artist_search.text().strip() and search_text(self.artist_search.text()) not in search_text(track.artist):
            self.artist_search.clear()

        self.select_list_value(self.folder_list, track.artist)
        self.populate_albums()
        self.select_list_value(self.album_list, track.album)
        self.apply_filter()

    def select_list_value(self, list_widget: QListWidget, value: str) -> bool:
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == value:
                list_widget.setCurrentRow(row)
                return True
        return False

    def selected_visible_track(self) -> Track | None:
        row = self.track_table.currentRow()
        if 0 <= row < len(self.visible_tracks):
            return self.visible_tracks[row]
        return None

    def toggle_play(self) -> None:
        state = self.player.playbackState()
        selected = self.selected_visible_track()
        current = self.current_track()
        if selected is not None and (current is None or selected.path != current.path):
            self.current_index = self.tracks.index(selected)
            self.play_track(selected)
            return

        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.pause_current_track()
            return

        if self.current_index == -1:
            track = selected or (self.visible_tracks[0] if self.visible_tracks else None)
            if track is not None:
                self.current_index = self.tracks.index(track)
                self.play_track(track)
            return

        if current is None:
            return

        self.resume_current_track(current)

    def pause_current_track(self, manual: bool = True) -> None:
        if manual:
            self.auto_paused_by_other_media = False
        current = self.current_track()
        if current is not None:
            self.last_track = current
        self.paused_position = max(0, self.player.position())
        self.player.pause()
        self.emit_mpris_properties("PlaybackStatus", "Position")

    def resume_current_track(self, track: Track | None = None, manual: bool = True) -> None:
        if manual:
            self.auto_paused_by_other_media = False
        track = track or self.current_track() or self.last_track
        if track is None:
            return

        if track in self.tracks:
            self.current_index = self.tracks.index(track)
        self.last_track = track

        target_position = max(self.paused_position, self.player.position(), 0)
        path_str = track.path.as_posix()
        if path_str.startswith("/online/"):
            track_url = self.online_stream_urls.get(path_str, "")
            current_source = self.player.source().toString()
            if current_source != track_url:
                self.player.setSource(QUrl(track_url))
        elif path_str.startswith("/server/"):
            from constants import SERVER_URL
            from urllib.parse import quote
            relative_part = path_str[len("/server/"):]
            track_url = f"{SERVER_URL}/audio/{quote(relative_part)}"
            current_source = self.player.source().toString()
            if current_source != track_url:
                self.player.setSource(QUrl(track_url))
        else:
            source_path = Path(self.player.source().toLocalFile()) if not self.player.source().isEmpty() else None
            if source_path != track.path:
                self.player.setSource(QUrl.fromLocalFile(path_str))


        self.update_now_playing(track)
        self.set_cover_image(track)
        self.show_now_playing(track)
        self.player.play()
        if target_position > 0:
            QTimer.singleShot(80, lambda pos=target_position: self.player.setPosition(pos))

        self.resume_token += 1
        token = self.resume_token
        QTimer.singleShot(650, lambda token=token, track=track, pos=target_position: self.verify_resume(token, track, pos))
        self.emit_mpris_properties("PlaybackStatus", "Metadata", "Position")

    def verify_resume(self, token: int, track: Track, position: int) -> None:
        if token != self.resume_token:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return

        path_str = track.path.as_posix()
        if path_str.startswith("/online/"):
            track_url = self.online_stream_urls.get(path_str, "")
            self.player.setSource(QUrl(track_url))
        elif path_str.startswith("/server/"):
            from constants import SERVER_URL
            from urllib.parse import quote
            relative_part = path_str[len("/server/"):]
            track_url = f"{SERVER_URL}/audio/{quote(relative_part)}"
            self.player.setSource(QUrl(track_url))
        else:
            self.player.setSource(QUrl.fromLocalFile(path_str))

        self.player.play()
        if position > 0:
            QTimer.singleShot(120, lambda pos=position: self.player.setPosition(pos))
        self.emit_mpris_properties("PlaybackStatus", "Metadata", "Position")

    def handle_other_audio_state(self, other_playing: bool) -> None:
        state = self.player.playbackState()
        if other_playing:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                self.auto_paused_by_other_media = True
                self.pause_current_track(manual=False)
                if hasattr(self, "status"):
                    self.status.setText("Tạm dừng do phương tiện khác đang phát..." if self.language == "vi" else "Paused due to other active media...")
        else:
            if self.auto_paused_by_other_media:
                self.auto_paused_by_other_media = False
                if state == QMediaPlayer.PlaybackState.PausedState:
                    current = self.current_track()
                    if current:
                        self.resume_current_track(current, manual=False)
                        if hasattr(self, "status"):
                            self.status.setText("Đã tiếp tục phát nhạc" if self.language == "vi" else "Resumed playback")

    def stop(self) -> None:
        self.paused_position = 0
        self.player.stop()
        self.emit_mpris_properties("PlaybackStatus")

    def set_volume(self, value: int) -> None:
        self.audio.setVolume(value / 100)
        if hasattr(self, "volume_label"):
            if value <= 0:
                self.volume_label.setText("\U0001f507\ufe0e")
            elif value < 30:
                self.volume_label.setText("\U0001f508\ufe0e")
            elif value < 70:
                self.volume_label.setText("\U0001f509\ufe0e")
            else:
                self.volume_label.setText("\U0001f50a\ufe0e")
        if hasattr(self, "now_playing_window"):
            self.now_playing_window.update_extra_buttons()
        self.emit_mpris_properties("Volume")

    def toggle_mute(self) -> None:
        current_volume = self.volume.value()
        if current_volume > 0:
            self.previous_volume = current_volume
            self.volume.setValue(0)
        else:
            prev = getattr(self, "previous_volume", 80)
            self.volume.setValue(max(20, prev))

    def select_audio_device(self, device) -> None:
        self.audio.setDevice(device)
        if hasattr(self, "status"):
            self.status.setText(f"Output changed to: {device.description()}")

    def show_audio_menu(self) -> None:
        # Determine the colors to pass
        if hasattr(self, "current_bg_sidebar") and hasattr(self, "current_bg_border") and hasattr(self, "current_accent"):
            bg = self.current_bg_sidebar
            border = self.current_bg_border
            accent = self.current_accent
        else:
            bg = QColor("#0a0e17")
            border = QColor("#1a2333")
            accent = QColor("#1d90f4")

        self.audio_popup.populate(bg, border, accent)
        self.audio_popup.adjustSize()

        # Position popup above and right-aligned to the volume button
        button_pos = self.volume_label.mapToGlobal(QPoint(0, 0))
        menu_width = max(self.audio_popup.sizeHint().width(), 260)
        menu_height = self.audio_popup.sizeHint().height()

        # Right-align popup edge with right edge of the volume button
        x = button_pos.x() + self.volume_label.width() - menu_width
        y = button_pos.y() - menu_height - 6

        self.audio_popup.setFixedWidth(menu_width)
        self.audio_popup.move(QPoint(x, y))
        self.audio_popup.show()

    def previous_track(self) -> None:
        playlist = self.active_playlist()
        if not playlist:
            return
        current_track = self.current_track()
        try:
            playlist_index = playlist.index(current_track) if current_track else -1
        except ValueError:
            playlist_index = -1
            
        if playlist_index == -1:
            track = playlist[-1]
        else:
            track = playlist[(playlist_index - 1) % len(playlist)]
            
        if track in self.tracks:
            self.current_index = self.tracks.index(track)
        else:
            self.current_index = -1
        self.play_track(track)

    def next_track(self) -> None:
        playlist = self.active_playlist()
        if not playlist:
            return
        if self.shuffle_enabled:
            track = random.choice(playlist)
        else:
            current_track = self.current_track()
            try:
                playlist_index = playlist.index(current_track) if current_track else -1
            except ValueError:
                playlist_index = -1
                
            if playlist_index == -1:
                track = playlist[0]
            else:
                track = playlist[(playlist_index + 1) % len(playlist)]
                
        if track in self.tracks:
            self.current_index = self.tracks.index(track)
        else:
            self.current_index = -1
        self.play_track(track)

    def active_playlist(self) -> list[Track]:
        if hasattr(self, "content_stack") and self.content_stack.currentWidget() == self.soundcloud_page:
            playlist = []
            for res in getattr(self, "online_results", []):
                url_hash = hashlib.sha1(res["webpage_url"].encode()).hexdigest()
                virtual_path = Path(f"/online/soundcloud/{url_hash}.mp3")
                t = Track(
                    path=virtual_path,
                    title=res["title"],
                    folder="SoundCloud",
                    artist=res["uploader"],
                    album="SoundCloud",
                    art_path=None
                )
                playlist.append(t)
            return playlist
        return self.visible_tracks or self.tracks

    def toggle_shuffle(self, checked: bool) -> None:
        self.shuffle_enabled = checked
        self.update_shuffle_text()
        self.emit_mpris_properties("Shuffle")

    def update_shuffle_text(self) -> None:
        if hasattr(self.shuffle_button, "set_kind"):
            self.shuffle_button.set_kind("shuffle")
        else:
            self.shuffle_button.setText("⤨")
        self.shuffle_button.setToolTip(self.tr("shuffle_on" if self.shuffle_enabled else "shuffle_off"))

    def update_position(self, position: int) -> None:
        if not self.is_user_seeking:
            self.position_slider.setValue(position)
        self.elapsed_label.setText(format_ms(position))

    def update_duration(self, duration: int) -> None:
        self.position_slider.setRange(0, max(0, duration))
        self.duration_label.setText(format_ms(duration))

    def _start_seek(self) -> None:
        self.is_user_seeking = True

    def _finish_seek(self) -> None:
        self.is_user_seeking = False
        self.player.setPosition(self.position_slider.value())
        self.emit_mpris_properties("Position")

    def update_play_button(self) -> None:
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if hasattr(self.play_button, "set_kind"):
            self.play_button.set_kind("pause" if playing else "play")
            return
        icon = QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))

    def handle_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            current = self.current_track()
            if self.repeat_enabled and current is not None:
                QTimer.singleShot(80, lambda track=current: self.play_track(track))
                return
            QTimer.singleShot(150, self.next_track)

    def show_player_error(self, error, message: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        detail = message or self.tr("player_error_body")
        QMessageBox.warning(self, self.tr("player_error_title"), detail)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._really_closing:
            event.accept()
            return
        event.ignore()
        self.show_mini_player()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "now_playing_window") and self.now_playing_window is not None:
            max_width = max(300, self.width() // 2)
            self.now_playing_window.setMaximumWidth(max_width)

    def ensure_mini_player(self):
        if self.mini_player is None:
            from mini_player import MiniPlayerWidget
            self.mini_player = MiniPlayerWidget(self)
        return self.mini_player

    def show_mini_player(self) -> None:
        if self._really_closing:
            return
        mini_player = self.ensure_mini_player()
        self.hide()
        mini_player.show_widget()

    def restore_from_mini_player(self) -> None:
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if self.mini_player is not None:
            self.mini_player.hide()

    def real_close(self) -> None:
        from PySide6.QtWidgets import QApplication
        self._really_closing = True
        self.player.stop()
        self.emit_mpris_properties("PlaybackStatus", "Metadata", "Position")
        self.shutdown_mpris()
        if hasattr(self, "audio_monitor"):
            self.audio_monitor.stop()
        if self.mini_player is not None:
            self.mini_player.hide()
            self.mini_player.deleteLater()
            self.mini_player = None
        QApplication.quit()

    def changeEvent(self, event) -> None:
        from PySide6.QtCore import QEvent
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                QTimer.singleShot(0, self.show_mini_player)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "bottom_title"):
            return
        if hasattr(self, "track_table"):
            self.refresh_track_title_cells()
        track = self.current_track()
        if track is None:
            self.set_bottom_text(self.tr("not_playing"))
            return
        self.set_bottom_text(track.title, f"{track.artist} · {self.display_album(track.album)}")

    def show_track_context_menu(self, pos: QPoint) -> None:
        row = self.track_table.rowAt(pos.y())
        if row < 0 or row >= len(self.visible_tracks):
            return
        
        track = self.visible_tracks[row]
        menu = QMenu(self)
        
        menu.setStyleSheet(self.menuBar().styleSheet())
        
        play_action = menu.addAction(self.tr("context_menu_play"))
        play_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        
        set_bg_action = menu.addAction(self.tr("context_menu_set_bg"))
        set_bg_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        
        path_str = track.path.as_posix()
        is_server = path_str.startswith("/server/")
        from constants import SERVER_URL
        
        download_action = None
        upload_action = None
        
        if is_server:
            if SERVER_URL:
                download_action = menu.addAction(self.tr("context_menu_download_server"))
                download_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        else:
            if SERVER_URL:
                upload_action = menu.addAction(self.tr("context_menu_upload_server"))
                upload_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
                
        action = menu.exec(self.track_table.viewport().mapToGlobal(pos))
        if action == play_action:
            self.current_index = self.tracks.index(track)
            self.play_track(track)
        elif action == set_bg_action:
            self.show_cover_art_selector(track)
        elif download_action and action == download_action:
            self.download_server_track(track)
        elif upload_action and action == upload_action:
            self.upload_server_track(track)

    def show_cover_art_selector(self, track: Track) -> None:
        from art_selector import CoverArtSelectorDialog
        
        dialog = CoverArtSelectorDialog(track, self.library_root, self)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted and dialog.selected_path:
            try:
                set_custom_cover_path(track.path, dialog.selected_path)
                
                self.pixmap_cache.clear()
                self.art_cache.clear()
                
                current = self.current_track()
                if current and current.path == track.path:
                    self.set_cover_image(track)
                    self.set_bottom_cover(track)
                    self.update_dynamic_background(track)
                    self.show_now_playing(track)
                    if getattr(self, "mini_player", None) is not None:
                        self.mini_player.update_track_info()
                
                self.update_hero()
                self.refresh_track_title_cells()
                row_idx = self.visible_row_for_track(track)
                if row_idx is not None:
                    self._set_track_title_cell(row_idx, track)
                    
            except Exception as e:
                print(f"Error setting custom cover art mapping: {e}", file=sys.stderr)
                
        elif result == 2:
            try:
                set_custom_cover_path(track.path, None)
                
                self.pixmap_cache.clear()
                self.art_cache.clear()
                
                current = self.current_track()
                if current and current.path == track.path:
                    self.set_cover_image(track)
                    self.set_bottom_cover(track)
                    self.update_dynamic_background(track)
                    self.show_now_playing(track)
                    if getattr(self, "mini_player", None) is not None:
                        self.mini_player.update_track_info()
                
                self.update_hero()
                self.refresh_track_title_cells()
                row_idx = self.visible_row_for_track(track)
                if row_idx is not None:
                    self._set_track_title_cell(row_idx, track)
            except Exception as e:
                print(f"Error removing custom cover art mapping: {e}", file=sys.stderr)

    def show_soundcloud_view(self) -> None:
        self.folder_list.blockSignals(True)
        self.folder_list.clearSelection()
        self.folder_list.setCurrentItem(None)
        self.folder_list.blockSignals(False)

        self.album_list.blockSignals(True)
        self.album_list.clearSelection()
        self.album_list.setCurrentItem(None)
        self.album_list.blockSignals(False)
        
        self.content_stack.setCurrentWidget(self.soundcloud_page)
        self.update_static_texts()

    def _build_soundcloud_ui(self, layout: QVBoxLayout) -> None:
        self.soundcloud_header = QLabel()
        self.soundcloud_header.setObjectName("heroTitle")
        self.soundcloud_header.setStyleSheet("color: #ff5500; font-weight: 900; font-size: 26px;")
        layout.addWidget(self.soundcloud_header)

        self.soundcloud_sub = QLabel("Tìm kiếm và phát nhạc trực tuyến / Tải về thư viện offline")
        self.soundcloud_sub.setObjectName("heroSubtitle")
        layout.addWidget(self.soundcloud_sub)

        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)
        
        self.online_search = QLineEdit()
        self.online_search.setObjectName("songSearch")
        self.online_search.returnPressed.connect(self.start_soundcloud_search)
        
        self.online_search_btn = QPushButton()
        self.online_search_btn.setObjectName("primaryButton")
        self.online_search_btn.setStyleSheet("""
            QPushButton {
                background: #ff5500;
                border-color: #ff5500;
                padding: 8px 16px;
                border-radius: 16px;
            }
            QPushButton:hover {
                background: #ff7733;
                border-color: #ff7733;
            }
        """)
        self.online_search_btn.clicked.connect(self.start_soundcloud_search)
        
        search_layout.addWidget(self.online_search, 1)
        search_layout.addWidget(self.online_search_btn, 0)
        layout.addLayout(search_layout)

        self.online_status_label = QLabel("")
        self.online_status_label.setStyleSheet("color: #b3b3b3; font-style: italic; font-size: 13px; margin-left: 4px;")
        layout.addWidget(self.online_status_label)

        self.soundcloud_table = QTableWidget(0, 5)
        self.soundcloud_table.setObjectName("playlistTable")
        self.soundcloud_table.setHorizontalHeaderLabels(["", "", "", "", ""])
        self.soundcloud_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.soundcloud_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.soundcloud_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.soundcloud_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.soundcloud_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.soundcloud_table.setColumnWidth(1, 150)
        self.soundcloud_table.setColumnWidth(2, 90)
        self.soundcloud_table.setColumnWidth(3, 90)
        self.soundcloud_table.setColumnWidth(4, 100)
        
        self.soundcloud_table.verticalHeader().setVisible(False)
        self.soundcloud_table.verticalHeader().setDefaultSectionSize(76)
        self.soundcloud_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.soundcloud_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.soundcloud_table.setAlternatingRowColors(True)
        self.soundcloud_table.setShowGrid(False)
        self.soundcloud_table.setMouseTracking(True)
        
        self.soundcloud_table.doubleClicked.connect(self.play_soundcloud_row)
        
        layout.addWidget(self.soundcloud_table, 1)

    def start_soundcloud_search(self) -> None:
        query = self.online_search.text().strip()
        if not query:
            return
            
        self.online_status_label.setText(self.tr("searching_online"))
        self.online_search_btn.setEnabled(False)
        self.soundcloud_table.setRowCount(0)
        
        def run():
            try:
                from soundcloud_handler import search_soundcloud
                results = search_soundcloud(query, limit=50)
                self.soundcloud_worker.search_done.emit(results)
            except Exception as e:
                self.soundcloud_worker.search_failed.emit(str(e))
                
        threading.Thread(target=run, daemon=True).start()

    def handle_search_results(self, results: list) -> None:
        self.online_search_btn.setEnabled(True)
        self.online_results = results
        self.soundcloud_table.setRowCount(len(results))
        self.online_status_label.setText(self.tr("online_status", count=len(results)))
        
        for row, res in enumerate(results):
            self.populate_soundcloud_row(row, res)

    def handle_search_failed(self, err_msg: str) -> None:
        self.online_search_btn.setEnabled(True)
        self.online_status_label.setText(f"Lỗi: {err_msg}")
        QMessageBox.warning(self, "Lỗi tìm kiếm", f"Không tìm kiếm được trên SoundCloud: {err_msg}")

    def populate_soundcloud_row(self, row: int, res: dict) -> None:
        title_widget = QWidget()
        title_widget.setObjectName("trackTitleCell")
        title_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        cell_layout = QHBoxLayout(title_widget)
        cell_layout.setContentsMargins(12, 12, 12, 12)
        cell_layout.setSpacing(12)
        
        cover_label = QLabel("♪")
        cover_label.setObjectName("trackTitleCover")
        cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_label.setFixedSize(46, 46)
        cover_label.setStyleSheet("""
            QLabel#trackTitleCover {
                border-radius: 8px;
                background: #ff5500;
                color: #ffffff;
                font-weight: bold;
                font-size: 20px;
            }
        """)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 0, 0, 0)
        
        title_lbl = QLabel(res["title"])
        title_lbl.setObjectName("trackTitleText")
        title_lbl.setWordWrap(True)
        
        sub_lbl = QLabel(res["uploader"])
        sub_lbl.setObjectName("trackSubtitleText")
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(sub_lbl)
        
        cell_layout.addWidget(cover_label)
        cell_layout.addLayout(text_layout, 1)
        
        # Set empty QTableWidgetItem in model to ensure row/cell is active and selectable
        item0 = QTableWidgetItem("")
        self.soundcloud_table.setItem(row, 0, item0)
        self.soundcloud_table.setCellWidget(row, 0, title_widget)
        self.soundcloud_table.setRowHeight(row, 76)
        
        self._set_soundcloud_cell(row, 1, res["uploader"])
        self._set_soundcloud_cell(row, 2, res["duration_string"])
        
        # Stream Button set directly as cell widget for 100% reliable interaction
        stream_btn = QPushButton(self.tr("btn_stream_action"))
        stream_btn.setStyleSheet("""
            QPushButton {
                background: #1a2740;
                color: #e0e0e0;
                border: 1px solid #2a3a52;
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #1d90f4;
                border-color: #1d90f4;
                color: #ffffff;
            }
        """)
        from functools import partial
        stream_btn.clicked.connect(partial(self.start_soundcloud_stream, row, res))
        
        item3 = QTableWidgetItem("")
        self.soundcloud_table.setItem(row, 3, item3)
        self.soundcloud_table.setCellWidget(row, 3, stream_btn)
        
        # Download Button set directly as cell widget for 100% reliable interaction
        download_btn = QPushButton(self.tr("btn_download_action"))
        download_btn.setStyleSheet("""
            QPushButton {
                background: #1a2740;
                color: #e0e0e0;
                border: 1px solid #2a3a52;
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #ff5500;
                border-color: #ff5500;
                color: #ffffff;
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.04);
                color: #627284;
                border-color: transparent;
            }
        """)
        download_btn.clicked.connect(partial(self.start_soundcloud_download, row, res))
        
        item4 = QTableWidgetItem("")
        self.soundcloud_table.setItem(row, 4, item4)
        self.soundcloud_table.setCellWidget(row, 4, download_btn)
        
        if res.get("thumbnail"):
            self.load_online_thumbnail(res["thumbnail"], cover_label)
 
    def _set_soundcloud_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setForeground(QColor("#e8e8e8"))
        item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.soundcloud_table.setItem(row, col, item)
 
    def get_rounded_pixmap(self, src: QPixmap, radius: int = 8) -> QPixmap:
        from PySide6.QtGui import QPainterPath
        target = QPixmap(src.size())
        target.fill(Qt.GlobalColor.transparent)
        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, src.width(), src.height()), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, src)
        painter.end()
        return target
 
    def load_online_thumbnail(self, url: str, label: QLabel) -> None:
        from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
        from PySide6.QtCore import QUrl
        
        if not hasattr(self, "nam"):
            self.nam = QNetworkAccessManager(self)
            
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Mozilla/5.0")
        
        reply = self.nam.get(request)
        reply.sslErrors.connect(lambda errors: reply.ignoreSslErrors())
        
        from functools import partial
        reply.finished.connect(partial(self.on_thumbnail_download_finished, reply, label))
 
    def on_thumbnail_download_finished(self, reply, label: QLabel) -> None:
        from PySide6.QtNetwork import QNetworkReply
        reply.deleteLater()
        
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll().data()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                scaled = pixmap.scaled(46, 46, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                rounded = self.get_rounded_pixmap(scaled, 8)
                label.setPixmap(rounded)
        else:
            print(f"Network error downloading thumbnail: {reply.errorString()}", flush=True)

    def play_soundcloud_row(self) -> None:
        row = self.soundcloud_table.currentRow()
        if row < 0 or row >= len(self.online_results):
            return
        res = self.online_results[row]
        self.start_soundcloud_stream(row, res)

    def start_soundcloud_stream(self, row: int, res: dict) -> None:
        webpage_url = res["webpage_url"]
        title = res["title"]
        artist = res["uploader"]
        thumbnail = res.get("thumbnail") or ""
        
        self.status.setText(self.tr("stream_loading", title=title))
        self.soundcloud_table.setEnabled(False)
        
        # Store thumbnail so _on_stream_done can start async art caching
        self._pending_stream_thumbnail = thumbnail
        
        def run():
            try:
                from soundcloud_handler import get_stream_url
                stream_url = get_stream_url(webpage_url)
                if stream_url:
                    url_hash = hashlib.sha1(webpage_url.encode()).hexdigest()
                    virtual_path_str = f"/online/soundcloud/{url_hash}.mp3"
                    # Emit signal — this is thread-safe and guaranteed to reach main thread
                    self.soundcloud_worker.stream_done.emit(title, artist, virtual_path_str, stream_url)
                else:
                    self.soundcloud_worker.stream_failed.emit("Could not retrieve stream URL")
            except Exception as e:
                self.soundcloud_worker.stream_failed.emit(str(e))
                
        threading.Thread(target=run, daemon=True).start()

    def _on_stream_done(self, title: str, artist: str, virtual_path_str: str, stream_url: str) -> None:
        """Called on the main thread via Qt Signal when the stream URL is ready."""
        virtual_path = Path(virtual_path_str)
        thumbnail = getattr(self, "_pending_stream_thumbnail", "")
        
        if thumbnail:
            from library import COVER_CACHE, embedded_art_cache_path
            cache_art = embedded_art_cache_path(virtual_path)
            if not cache_art.exists():
                self.async_cache_online_art(thumbnail, cache_art)
        
        self.play_online_track(title, artist, virtual_path, stream_url)

    def _on_stream_failed(self, err_msg: str) -> None:
        """Called on the main thread via Qt Signal when streaming fails."""
        self.handle_stream_failed(err_msg)

    def async_cache_online_art(self, url: str, target_path: Path) -> None:
        from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
        from PySide6.QtCore import QUrl
        
        if not hasattr(self, "nam"):
            self.nam = QNetworkAccessManager(self)
            
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Mozilla/5.0")
        
        reply = self.nam.get(request)
        reply.sslErrors.connect(lambda errors: reply.ignoreSslErrors())
        
        from functools import partial
        reply.finished.connect(partial(self.on_cache_art_download_finished, reply, target_path))

    def on_cache_art_download_finished(self, reply, target_path: Path) -> None:
        from PySide6.QtNetwork import QNetworkReply
        reply.deleteLater()
        
        # Discard from in-progress covers
        if hasattr(self, "_in_progress_covers"):
            for path_str in list(self._in_progress_covers):
                try:
                    if embedded_art_cache_path(Path(path_str)).resolve().as_posix() == target_path.resolve().as_posix():
                        self._in_progress_covers.discard(path_str)
                        break
                except Exception:
                    pass
        
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll().data()
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(data)
                curr = self.current_track()
                if curr and embedded_art_cache_path(curr.path).resolve().as_posix() == target_path.resolve().as_posix():
                    # Clear entire in-memory caches to guarantee reload of new image
                    self.pixmap_cache.clear()
                    self.art_cache.clear()
                    
                    self.register_extracted_cover(curr)
                    self.now_playing_window.update_track(curr)
                    if getattr(self, "mini_player", None) is not None:
                        self.mini_player.update_track_info()
            except Exception as e:
                print(f"Error saving cached online art: {e}", flush=True)
        else:
            print(f"Network error caching art: {reply.errorString()}", flush=True)


    def play_online_track(self, title: str, artist: str, virtual_path: Path, stream_url: str) -> None:
        self.soundcloud_table.setEnabled(True)
        self.status.setText("SoundCloud: " + title)
        
        self.online_stream_urls[str(virtual_path)] = stream_url
        
        track = Track(
            path=virtual_path,
            title=title,
            folder="SoundCloud",
            artist=artist,
            album="SoundCloud",
            art_path=None
        )
        
        # Keep online track separate — do NOT add to self.tracks (local library list)
        self.current_online_track = track
        
        # Play directly without going through the normal play_track flow
        # (which would try to highlight in the local library table)
        self.player.setSource(QUrl(stream_url))
        self.player.play()
        self.last_track = track
        self.resume_token += 1
        self.paused_position = 0
        
        # Update now playing panel and cover art
        self.update_now_playing(track)
        self.set_cover_image(track)
        self.show_now_playing(track)
        if getattr(self, "mini_player", None) is not None:
            self.mini_player.update_track_info()
        self.emit_mpris_properties("Metadata", "PlaybackStatus", "CanGoNext", "CanGoPrevious", "CanPlay")

    def handle_stream_failed(self, err_msg: str) -> None:
        self.soundcloud_table.setEnabled(True)
        self.status.setText(f"Lỗi stream: {err_msg}")
        QMessageBox.warning(self, "Lỗi phát trực tuyến", f"Không lấy được luồng phát từ SoundCloud: {err_msg}")

    def resolve_and_play_online(self, track: Track) -> None:
        url_hash = track.path.stem
        webpage_url = None
        thumbnail = None
        for res in getattr(self, "online_results", []):
            res_hash = hashlib.sha1(res["webpage_url"].encode()).hexdigest()
            if res_hash == url_hash:
                webpage_url = res["webpage_url"]
                thumbnail = res["thumbnail"]
                break
                
        if not webpage_url:
            self.status.setText("Lỗi: Không tìm thấy liên kết bài hát online")
            return
            
        self.status.setText(self.tr("stream_loading", title=track.title))
        
        def run():
            try:
                from soundcloud_handler import get_stream_url
                stream_url = get_stream_url(webpage_url)
                if stream_url:
                    self.online_stream_urls[str(track.path)] = stream_url
                    
                    from library import COVER_CACHE, embedded_art_cache_path
                    cache_art = embedded_art_cache_path(track.path)
                    if thumbnail and not cache_art.exists():
                        QTimer.singleShot(0, lambda: self.async_cache_online_art(thumbnail, cache_art))
                            
                    QTimer.singleShot(0, lambda: self.play_track(track))
                else:
                    QTimer.singleShot(0, lambda: self.status.setText("Lỗi kết nối stream SoundCloud"))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.status.setText(f"Lỗi: {e}"))
                
        threading.Thread(target=run, daemon=True).start()

    def start_soundcloud_download(self, row: int, res: dict) -> None:
        webpage_url = res["webpage_url"]
        title = res["title"]
        artist = res["uploader"]
        
        # Check if already exists in library (self.tracks or filesystem)
        already_exists = False
        for track in self.tracks:
            if search_text(track.title) == search_text(title) and search_text(track.artist) == search_text(artist):
                already_exists = True
                break
                
        if not already_exists:
            # Check filesystem too
            import re
            def safe_filename(name: str) -> str:
                return re.sub(r'[\\/*?:"<>|]', "", name).strip()
            safe_title = safe_filename(title)
            safe_artist = safe_filename(artist)
            artist_dir = self.library_root / safe_artist
            if artist_dir.exists():
                for ext in ("mp3", "m4a", "ogg", "opus", "webm", "wav", "flac"):
                    if (artist_dir / f"{safe_artist} - {safe_title}.{ext}").exists():
                        already_exists = True
                        break
                        
        if already_exists:
            reply = QMessageBox.question(
                self,
                self.tr("download_exists_title"),
                self.tr("download_exists_msg").format(title=title, artist=artist),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
                
        btn = self.soundcloud_table.cellWidget(row, 4)
        if btn:
            btn.setEnabled(False)
            btn.setText("0%")
            
        self.status.setText(self.tr("download_start", title=title))
            
        def progress_cb(percent_str):
            self.soundcloud_worker.download_progress.emit(row, f"{percent_str}%")
            
        def run():
            try:
                from soundcloud_handler import download_track
                from library import COVER_CACHE
                
                dest_path, cover_path, err = download_track(
                    webpage_url,
                    self.library_root,
                    COVER_CACHE,
                    progress_callback=progress_cb
                )
                if dest_path:
                    self.soundcloud_worker.download_done.emit(row, True, "")
                else:
                    self.soundcloud_worker.download_done.emit(row, False, err or "Unknown error")
            except Exception as e:
                self.soundcloud_worker.download_done.emit(row, False, str(e))
                
        threading.Thread(target=run, daemon=True).start()

    def handle_download_progress(self, row: int, progress_str: str) -> None:
        btn = self.soundcloud_table.cellWidget(row, 4)
        if btn:
            btn.setText(progress_str)

    def handle_download_done(self, row: int, success: bool, error_msg: str) -> None:
        btn = self.soundcloud_table.cellWidget(row, 4)
        if btn:
            if success:
                btn.setText(self.tr("downloaded_status"))
                btn.setStyleSheet("color: #10b981; font-weight: bold; background: transparent; border: none; margin: 20px 8px;")
                self.reload_library()
            else:
                btn.setText(self.tr("error_status"))
                btn.setStyleSheet("color: #ef4444; font-weight: bold; margin: 20px 8px;")
                btn.setEnabled(True)
                QMessageBox.warning(self, self.tr("download_failed").split(":")[0], f"{self.tr('download_failed').format(title=error_msg)}")

    def download_server_track(self, track: Track) -> None:
        from constants import SERVER_URL
        if not SERVER_URL:
            return
            
        path_str = track.path.as_posix()
        if not path_str.startswith("/server/"):
            return
            
        relative_part = path_str[len("/server/"):]
        
        filename = Path(relative_part).name
        def sanitize_dir(name):
            return "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
            
        artist_dir = sanitize_dir(track.artist) or "Library"
        album_dir = sanitize_dir(track.album) or "Singles"
        dest_dir = self.library_root / artist_dir / album_dir
        dest_path = dest_dir / filename
        
        if dest_path.exists():
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                self.tr("download_exists_title"),
                self.tr("download_exists_msg").format(title=track.title, artist=track.artist),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
                
        self.status.setText(self.tr("download_start", title=track.title))
        
        def run():
            import urllib.request
            import urllib.parse
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                audio_url = f"{SERVER_URL}/audio/{urllib.parse.quote(relative_part)}"
                
                with urllib.request.urlopen(audio_url, timeout=15) as response:
                    with open(dest_path, "wb") as f:
                        f.write(response.read())
                        
                try:
                    cover_url = f"{SERVER_URL}/cover/{urllib.parse.quote(relative_part)}"
                    cover_dest = dest_dir / "cover.jpg"
                    if not cover_dest.exists():
                        with urllib.request.urlopen(cover_url, timeout=3) as cover_resp:
                            with open(cover_dest, "wb") as cf:
                                cf.write(cover_resp.read())
                except Exception:
                    pass
                    
                QTimer.singleShot(0, lambda: self.on_server_download_success(track))
            except Exception as e:
                QTimer.singleShot(0, lambda err=str(e): self.on_server_download_failed(track, err))
                
        import threading
        threading.Thread(target=run, daemon=True).start()

    def on_server_download_success(self, track: Track) -> None:
        self.status.setText(self.tr("download_success", title=track.title))
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            self.tr("download_success", title="").replace(":", "").strip(),
            self.tr("download_success_toast", title=track.title)
        )
        self.reload_library()

    def on_server_download_failed(self, track: Track, error_msg: str) -> None:
        self.status.setText(self.tr("download_failed", title=track.title))
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            self,
            self.tr("download_failed", title="").split(":")[0],
            self.tr("download_failed", title=f"{track.title} ({error_msg})")
        )

    def upload_server_track(self, track: Track) -> None:
        from constants import SERVER_URL
        if not SERVER_URL:
            return
            
        path_str = track.path.as_posix()
        if path_str.startswith("/server/") or path_str.startswith("/online/"):
            return
            
        if not track.path.exists():
            return
            
        self.status.setText(self.tr("upload_start", title=track.title))
        
        def run():
            import uuid
            import urllib.request
            try:
                url = f"{SERVER_URL}/upload"
                boundary = uuid.uuid4().hex
                parts = []
                
                fields = {
                    "artist": track.artist,
                    "album": track.album
                }
                for name, value in fields.items():
                    parts.append(f"--{boundary}".encode('utf-8'))
                    parts.append(f'Content-Disposition: form-data; name="{name}"'.encode('utf-8'))
                    parts.append(b'')
                    parts.append(str(value).encode('utf-8'))
                    
                parts.append(f"--{boundary}".encode('utf-8'))
                filename = track.path.name
                parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode('utf-8'))
                parts.append(b'Content-Type: application/octet-stream')
                parts.append(b'')
                with open(track.path, 'rb') as f:
                    parts.append(f.read())
                    
                parts.append(f"--{boundary}--".encode('utf-8'))
                parts.append(b'')
                
                body = b'\r\n'.join(parts)
                req = urllib.request.Request(url, data=body)
                req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                req.add_header('Content-Length', str(len(body)))
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    response.read()
                    
                QTimer.singleShot(0, lambda: self.on_server_upload_success(track))
            except Exception as e:
                QTimer.singleShot(0, lambda err=str(e): self.on_server_upload_failed(track, err))
                
        import threading
        threading.Thread(target=run, daemon=True).start()

    def on_server_upload_success(self, track: Track) -> None:
        self.status.setText(self.tr("upload_success", title=track.title))
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            self.tr("upload_success", title="").replace(":", "").strip(),
            self.tr("upload_success", title=track.title)
        )
        self.reload_library()

    def on_server_upload_failed(self, track: Track, error_msg: str) -> None:
        self.status.setText(self.tr("upload_failed", title=track.title, error=error_msg))
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            self,
            self.tr("upload_failed", title="", error="").replace("():", "").strip(),
            self.tr("upload_failed", title=track.title, error=error_msg)
        )

    def sync_library_to_server(self) -> None:
        from constants import SERVER_URL
        if not SERVER_URL:
            return
            
        if not self.library_root.exists():
            return
            
        self.hero_sync_button.setEnabled(False)
        self.status.setText(self.tr("sync_start"))
        
        def run():
            import uuid
            import urllib.request
            from library import scan_library
            try:
                # 1. Gather all relative paths of tracks currently on the server
                server_rel_paths = set()
                for track in self.tracks:
                    path_str = track.path.as_posix()
                    if path_str.startswith("/server/"):
                        server_rel_paths.add(path_str[len("/server/"):].lower())
                        
                # 2. Scan local tracks
                local_tracks = scan_library(self.library_root)
                
                # 3. Identify new tracks that aren't on the server
                tracks_to_upload = []
                for local_track in local_tracks:
                    try:
                        rel_path = local_track.path.relative_to(self.library_root).as_posix()
                        if rel_path.lower() not in server_rel_paths:
                            tracks_to_upload.append(local_track)
                    except ValueError:
                        pass
                        
                if not tracks_to_upload:
                    QTimer.singleShot(0, lambda: self.on_sync_success(0))
                    return
                    
                # 4. Upload each new track sequentially
                uploaded_count = 0
                for i, local_track in enumerate(tracks_to_upload):
                    msg = f"Đồng bộ: Tải lên {i+1}/{len(tracks_to_upload)} - {local_track.title}..." if self.language == "vi" else f"Sync: Uploading {i+1}/{len(tracks_to_upload)} - {local_track.title}..."
                    QTimer.singleShot(0, lambda m=msg: self.status.setText(m))
                    
                    url = f"{SERVER_URL}/upload"
                    boundary = uuid.uuid4().hex
                    parts = []
                    
                    fields = {
                        "artist": local_track.artist,
                        "album": local_track.album
                    }
                    for name, value in fields.items():
                        parts.append(f"--{boundary}".encode('utf-8'))
                        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode('utf-8'))
                        parts.append(b'')
                        parts.append(str(value).encode('utf-8'))
                        
                    parts.append(f"--{boundary}".encode('utf-8'))
                    filename = local_track.path.name
                    parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode('utf-8'))
                    parts.append(b'Content-Type: application/octet-stream')
                    parts.append(b'')
                    with open(local_track.path, 'rb') as f:
                        parts.append(f.read())
                        
                    parts.append(f"--{boundary}--".encode('utf-8'))
                    parts.append(b'')
                    
                    body = b'\r\n'.join(parts)
                    req = urllib.request.Request(url, data=body)
                    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                    req.add_header('Content-Length', str(len(body)))
                    
                    with urllib.request.urlopen(req, timeout=30) as response:
                        response.read()
                        
                    uploaded_count += 1
                    
                QTimer.singleShot(0, lambda cnt=uploaded_count: self.on_sync_success(cnt))
            except Exception as e:
                QTimer.singleShot(0, lambda err=str(e): self.on_sync_failed(err))
                
        import threading
        threading.Thread(target=run, daemon=True).start()

    def on_sync_success(self, count: int) -> None:
        self.hero_sync_button.setEnabled(True)
        from PySide6.QtWidgets import QMessageBox
        if count > 0:
            self.status.setText(self.tr("sync_complete", count=count))
            QMessageBox.information(
                self,
                self.tr("sync_server_btn"),
                self.tr("sync_complete", count=count)
            )
            self.reload_library()
        else:
            self.status.setText(self.tr("sync_no_new"))
            QMessageBox.information(
                self,
                self.tr("sync_server_btn"),
                self.tr("sync_no_new")
            )

    def on_sync_failed(self, error_msg: str) -> None:
        self.hero_sync_button.setEnabled(True)
        self.status.setText(self.tr("sync_failed", error=error_msg))
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            self,
            self.tr("sync_failed", error="").replace(":", "").strip(),
            self.tr("sync_failed", error=error_msg)
        )

    def save_server_url(self, url: str) -> None:
        import re
        from pathlib import Path
        constants_path = Path(__file__).parent / "constants.py"
        if not constants_path.exists():
            return
        try:
            content = constants_path.read_text(encoding="utf-8")
            new_content = re.sub(
                r'SERVER_URL\s*=\s*(?:["\'][^"\']*["\']|None|""|\'\')',
                f'SERVER_URL = "{url}"',
                content
            )
            constants_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            print(f"Error saving SERVER_URL to constants.py: {e}", flush=True)

    def parse_track_info_heuristics(self, path: Path) -> tuple[str, str, str]:
        # Try to parse from parent folders
        parent = path.parent
        try:
            rel = parent.relative_to(self.library_root)
            parts = rel.parts
        except ValueError:
            parts = parent.parts[-2:] if len(parent.parts) >= 2 else (parent.parts[-1:] if parent.parts else ())
            
        artist = parts[0] if parts else "Library"
        album = None
        for part in parts[1:]:
            if _folder_is_album(part):
                album = _extract_album_name(part)
        if album is None:
            album = parts[1] if len(parts) > 1 else "Singles"
            
        title = readable_title(path)
        
        # Now apply filename heuristics if artist/album are defaults
        stem = path.stem
        for suffix in (" - YouTube", " Official MV", " Official Music Video"):
            stem = stem.replace(suffix, "")
        stem = stem.strip()
        
        stem_parts = [s.strip() for s in stem.split(" - ") if s.strip()]
        
        artist_indicators = ["ft.", "feat.", "prod.", "&", " x ", " x", "x "]
        
        if len(stem_parts) >= 3:
            album_idx = -1
            for idx, seg in enumerate(stem_parts):
                if _folder_is_album(seg):
                    album_idx = idx
                    break
            if album_idx != -1:
                album = _extract_album_name(stem_parts[album_idx])
                if album_idx > 0:
                    if artist == "Library":
                        artist = stem_parts[album_idx - 1]
                    title = " - ".join(stem_parts[:album_idx - 1]) or stem_parts[0]
                else:
                    title = " - ".join(stem_parts[1:])
            else:
                if artist == "Library":
                    artist = stem_parts[0]
                    title = " - ".join(stem_parts[1:])
                else:
                    title = " - ".join(stem_parts[1:])
        elif len(stem_parts) == 2:
            seg0, seg1 = stem_parts[0], stem_parts[1]
            seg0_has_art = any(ind in seg0.lower() for ind in artist_indicators)
            seg1_has_art = any(ind in seg1.lower() for ind in artist_indicators)
            
            if seg1_has_art and not seg0_has_art:
                if artist == "Library":
                    artist = seg1
                title = seg0
            elif seg0_has_art and not seg1_has_art:
                if artist == "Library":
                    artist = seg0
                title = seg1
            else:
                if artist == "Library":
                    artist = seg0
                    title = seg1
                else:
                    if artist.lower() in seg1.lower():
                        title = seg0
                    elif artist.lower() in seg0.lower():
                        title = seg1
                    else:
                        title = stem
                        
        return artist, album, title

    def choose_and_upload_file(self) -> None:
        from constants import SERVER_URL
        url = SERVER_URL
        if not url:
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(
                self,
                "Cấu hình Server URL" if self.language == "vi" else "Configure Server URL",
                "Nhập địa chỉ URL của Server nhạc (ví dụ http://192.168.1.245:8000):" if self.language == "vi" else "Enter the music Server URL (e.g. http://192.168.1.245:8000):",
                text="http://localhost:8000"
            )
            if not ok or not text.strip():
                return
            url = text.strip()
            self.save_server_url(url)
            import constants
            constants.SERVER_URL = url
            self.update_path_label()
            if hasattr(self, "hero_sync_button"):
                self.hero_sync_button.show()
                self.hero_sync_button.setText(self.tr("sync_server_btn"))

        from PySide6.QtWidgets import QMessageBox, QFileDialog
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Phương thức tải lên" if self.language == "vi" else "Upload Method")
        msg_box.setText("Bạn muốn tải lên các tệp tin riêng lẻ hay quét cả thư mục?" if self.language == "vi" else "Do you want to upload individual files or scan a folder?")
        
        files_btn = msg_box.addButton("Chọn file" if self.language == "vi" else "Select Files", QMessageBox.ButtonRole.YesRole)
        folder_btn = msg_box.addButton("Quét thư mục" if self.language == "vi" else "Scan Folder", QMessageBox.ButtonRole.NoRole)
        cancel_btn = msg_box.addButton("Hủy" if self.language == "vi" else "Cancel", QMessageBox.ButtonRole.RejectRole)
        
        msg_box.exec()
        clicked = msg_box.clickedButton()
        
        chosen_files = []
        if clicked == files_btn:
            chosen_files, _ = QFileDialog.getOpenFileNames(
                self,
                "Chọn file nhạc để tải lên" if self.language == "vi" else "Select Music Files to Upload",
                "",
                "Audio Files (*.mp3 *.flac *.wav *.m4a *.ogg *.aac *.opus *.mp4)"
            )
        elif clicked == folder_btn:
            selected_dir = QFileDialog.getExistingDirectory(
                self,
                "Chọn thư mục nhạc để quét và tải lên" if self.language == "vi" else "Select Music Folder to Scan and Upload",
                ""
            )
            if selected_dir:
                import os
                from library import AUDIO_EXTENSIONS
                for dirpath, _, filenames in os.walk(selected_dir):
                    for filename in filenames:
                        ext = os.path.splitext(filename)[1].lower()
                        if ext in AUDIO_EXTENSIONS:
                            chosen_files.append(os.path.join(dirpath, filename))
                            
        if not chosen_files:
            return

        # Prompt user to confirm/edit classification info
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QLineEdit
        dialog = QDialog(self)
        dialog.setWindowTitle("Thông tin phân loại" if self.language == "vi" else "Classification Info")
        dialog.setMinimumWidth(320)
        form = QFormLayout(dialog)
        
        # Heuristically parse from the first chosen file
        first_path = Path(chosen_files[0])
        parsed_artist, parsed_album, _ = self.parse_track_info_heuristics(first_path)
        
        artist_input = QLineEdit(parsed_artist)
        album_input = QLineEdit(parsed_album)
        
        form.addRow("Nghệ sĩ (Artist):" if self.language == "vi" else "Artist:", artist_input)
        form.addRow("Album:" if self.language == "vi" else "Album:", album_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
            
        artist_name = artist_input.text().strip() or "Library"
        album_name = album_input.text().strip() or "Singles"
        
        # Upload chosen files sequentially using QThread and UploadWorker with QProgressDialog
        total_files = len(chosen_files)
        
        from PySide6.QtWidgets import QProgressDialog
        from PySide6.QtCore import Qt
        
        progress_dialog = QProgressDialog(
            "Đang chuẩn bị tải lên..." if self.language == "vi" else "Preparing upload...",
            "Hủy" if self.language == "vi" else "Cancel",
            0,
            total_files,
            self
        )
        progress_dialog.setWindowTitle("Tải nhạc lên Server" if self.language == "vi" else "Uploading to Server")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        
        worker = UploadWorker(chosen_files, artist_name, album_name, url, self.language)
        thread = QThread(self)
        worker.moveToThread(thread)
        
        def update_progress(val, msg):
            progress_dialog.setValue(val)
            progress_dialog.setLabelText(msg)
            self.status.setText(msg)
            
        worker.progress_changed.connect(update_progress)
        
        def on_cancel():
            worker.is_cancelled = True
            self.status.setText("Đã hủy tải lên" if self.language == "vi" else "Upload cancelled")
            
        progress_dialog.canceled.connect(on_cancel)
        
        thread.started.connect(worker.run)
        
        def on_finished(success_count):
            thread.quit()
            thread.wait()
            progress_dialog.close()
            
            msg_done = f"Đã tải lên thành công {success_count}/{total_files} file!" if self.language == "vi" else f"Successfully uploaded {success_count}/{total_files} files!"
            self.set_status_notification(msg_done, "success" if success_count == total_files else "error")
            
            QMessageBox.information(
                self,
                "Tải lên hoàn tất" if self.language == "vi" else "Upload Completed",
                msg_done
            )
            
            import constants
            if constants.SERVER_URL:
                self.reload_library()
                
        worker.upload_finished.connect(on_finished)
        thread.start()
        
        # Keep reference to avoid garbage collection
        self._upload_thread = thread
        self._upload_worker = worker

    def set_status_notification(self, text: str, color_type: str) -> None:
        self.status.setText(text)
        if color_type == "success":
            self.status.setStyleSheet("color: #2ecc71; font-weight: bold; background-color: rgba(46, 204, 113, 0.12); border: 1px solid rgba(46, 204, 113, 0.25); border-radius: 6px; padding: 4px 8px;")
        elif color_type == "error":
            self.status.setStyleSheet("color: #e74c3c; font-weight: bold; background-color: rgba(231, 76, 60, 0.12); border: 1px solid rgba(231, 76, 60, 0.25); border-radius: 6px; padding: 4px 8px;")
        else:
            self.status.setStyleSheet("")
            return

        if hasattr(self, "_status_timer") and self._status_timer:
            try:
                self._status_timer.stop()
            except Exception:
                pass
            
        from PySide6.QtCore import QTimer
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self.status.setStyleSheet(""))
        self._status_timer.start(5000)
