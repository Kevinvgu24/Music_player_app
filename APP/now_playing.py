from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QConicalGradient, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen, QPixmap, QLinearGradient
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from constants import APP_NAME
from library import Track, embedded_art_cache_path, embedded_no_art_path
from utils import format_ms
from widgets import SeekSlider, MusicVisualizer


class DiscWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("discWidget")
        self.setFixedSize(280, 280)
        self.pixmap = QPixmap()
        self.old_pixmap = QPixmap()
        self.accent = QColor("#1d90f4")
        self.old_accent = QColor("#1d90f4")
        self.angle = 0.0
        
        self.current_speed = 0.0
        self.target_speed = 0.0
        self.fade_progress = 1.0
        self.fade_animation = None
        
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.rotate_disc)
        self.timer.start()

    def set_disc(self, pixmap: QPixmap, accent: QColor) -> None:
        self.old_pixmap = self.pixmap
        self.old_accent = self.accent
        
        self.pixmap = pixmap
        self.accent = accent if accent.isValid() else QColor("#1d90f4")
        
        if self.fade_animation is not None:
            self.fade_animation.stop()
            
        self.fade_progress = 0.0
        self.fade_animation = QVariantAnimation(self)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.setDuration(400)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        def update_fade(val):
            self.fade_progress = val
            self.update()
            
        self.fade_animation.valueChanged.connect(update_fade)
        self.fade_animation.start()

    def set_spinning(self, spinning: bool) -> None:
        self.target_speed = 0.36 if spinning else 0.0

    def rotate_disc(self) -> None:
        if abs(self.current_speed - self.target_speed) > 0.001:
            self.current_speed += 0.05 * (self.target_speed - self.current_speed)
        else:
            self.current_speed = self.target_speed

        if self.current_speed > 0.0:
            self.angle = (self.angle + self.current_speed) % 360
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        side = min(self.width(), self.height()) - 12
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        center = rect.center()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawEllipse(rect.translated(0, 7))

        clip_path = QPainterPath()
        clip_path.addEllipse(rect)
        painter.save()
        painter.setClipPath(clip_path)
        painter.translate(center)
        painter.rotate(self.angle)
        target = QRectF(-side / 2, -side / 2, side, side)

        def draw_disc_face(pix: QPixmap, acc: QColor, opacity: float):
            painter.setOpacity(opacity)
            if not pix.isNull():
                painter.drawPixmap(target, pix, QRectF(pix.rect()))
            else:
                gradient = QConicalGradient(QPointF(0, 0), 35)
                gradient.setColorAt(0.0, acc.lighter(126))
                gradient.setColorAt(0.45, acc)
                gradient.setColorAt(0.72, acc.darker(150))
                gradient.setColorAt(1.0, acc.lighter(118))
                painter.fillRect(target, gradient)
                painter.setPen(QColor(255, 255, 255, 235))
                font = QFont()
                font.setPixelSize(112)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(target, Qt.AlignmentFlag.AlignCenter, "♪")

        if self.fade_progress < 1.0 and (not self.old_pixmap.isNull() or not self.old_accent == self.accent):
            draw_disc_face(self.old_pixmap, self.old_accent, 1.0 - self.fade_progress)
            draw_disc_face(self.pixmap, self.accent, self.fade_progress)
        else:
            draw_disc_face(self.pixmap, self.accent, 1.0)

        painter.setOpacity(1.0)
        shine = QConicalGradient(QPointF(0, 0), -25)
        shine.setColorAt(0.0, QColor(255, 255, 255, 0))
        shine.setColorAt(0.22, QColor(255, 255, 255, 36))
        shine.setColorAt(0.34, QColor(255, 255, 255, 0))
        shine.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shine)
        painter.drawEllipse(target)
        painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1.2))
        painter.drawEllipse(rect.adjusted(1.5, 1.5, -1.5, -1.5))



class MiniControlButton(QToolButton):
    ICONS = {
        "repeat": """
            <path d="M17 2l4 4-4 4"/>
            <path d="M3 11v-1a4 4 0 0 1 4-4h14"/>
            <path d="M7 22l-4-4 4-4"/>
            <path d="M21 13v1a4 4 0 0 1-4 4H3"/>
        """,
        "shuffle": """
            <path d="M16 3h5v5"/>
            <path d="M4 20 21 3"/>
            <path d="M21 16v5h-5"/>
            <path d="M15 15l6 6"/>
            <path d="M4 4l5 5"/>
        """,
        "prev": """
            <path fill="currentColor" stroke="none" d="M6 5h2.4v14H6z"/>
            <path fill="currentColor" stroke="none" d="M9.2 12 18 5.5v13z"/>
        """,
        "play": """
            <path fill="currentColor" stroke="none" d="M8 5v14l11-7z"/>
        """,
        "pause": """
            <path fill="currentColor" stroke="none" d="M7 5h4.2v14H7z"/>
            <path fill="currentColor" stroke="none" d="M12.8 5H17v14h-4.2z"/>
        """,
        "next": """
            <path fill="currentColor" stroke="none" d="M15.6 5H18v14h-2.4z"/>
            <path fill="currentColor" stroke="none" d="M6 5.5 14.8 12 6 18.5z"/>
        """,
        "volume": """
            <path fill="currentColor" stroke="none" d="M4 9.2h4.2L14 4.8v14.4l-5.8-4.4H4z"/>
            <path d="M17 8.2a5.2 5.2 0 0 1 0 7.6"/>
            <path d="M19.4 5.8a8.6 8.6 0 0 1 0 12.4"/>
        """,
    }

    def __init__(self, kind: str, callback, primary: bool = False) -> None:
        super().__init__()
        self.kind = kind
        self.primary = primary
        self.icon_color = QColor("#ffffff")
        self.setObjectName("miniPlayButton" if primary else "miniControlButton")
        self.clicked.connect(callback)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(54 if primary else 42, 54 if primary else 42)

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Draw circular background
        if self.isChecked():
            bg = QColor(255, 255, 255, 66)
        elif self.underMouse():
            bg = QColor(255, 255, 255, 82 if self.primary else 60)
        else:
            bg = QColor(255, 255, 255, 48 if self.primary else 36)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawEllipse(self.rect())

        self.draw_svg_icon(painter)

    def draw_svg_icon(self, painter: QPainter) -> None:
        color = self.icon_color.name()
        paths = self.ICONS.get(self.kind, self.ICONS["play"])
        if self.kind == "volume" and self.isChecked():
            paths += '<path d="M19 9l-6 6"/><path d="M13 9l6 6"/>'
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
             width="24" height="24" fill="none" stroke="{color}"
             stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"
             color="{color}">
            {paths.replace("currentColor", color)}
        </svg>
        """
        renderer = QSvgRenderer(svg.encode("utf-8"))
        size = 26 if self.primary else 22
        if self.kind in {"prev", "next"}:
            size = 20
        if self.kind == "repeat":
            size = 20
        if self.kind == "shuffle":
            size = 20
        rect = QRectF(int((self.width() - size) / 2), int((self.height() - size) / 2), size, size)
        renderer.render(painter, rect)


class NowPlayingWindow(QWidget):
    def __init__(self, window: "PlayerWindow") -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.window = window
        self.current_accent = QColor("#1d90f4")
        self.current_bg = QColor("#0a0e17")
        self.bg_animation = None
        self.setObjectName("nowPlayingWindow")
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(300)

        # QVideoSink for manual rendering of video frames as blurred background
        self.video_sink = QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self.on_video_frame_changed)
        self.window.player.setVideoOutput(self.video_sink)
        self.raw_video_frame = None
        self.scaled_video_frame = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 18, 15, 24)
        layout.setSpacing(12)

        top = QHBoxLayout()
        self.close_button = QToolButton()
        self.close_button.setObjectName("playerButton")
        self.close_button.setText("‹")
        self.close_button.clicked.connect(self.window.hide_now_playing)
        self.title_label = QLabel()
        self.title_label.setObjectName("miniTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self.close_button)
        top.addWidget(self.title_label, 1)
        top.addSpacing(42)
        layout.addLayout(top)

        self.disc = DiscWidget()
        layout.addWidget(self.disc, 0, Qt.AlignmentFlag.AlignHCenter)

        self.mini_wave = MusicVisualizer(self.window.player, height=40)
        layout.addWidget(self.mini_wave, 0, Qt.AlignmentFlag.AlignHCenter)

        self.song_label = QLabel()
        self.song_label.setObjectName("miniSong")
        self.song_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.song_label.setWordWrap(True)
        self.song_label.setFixedHeight(64)
        self.artist_label = QLabel()
        self.artist_label.setObjectName("miniArtist")
        self.artist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_label.setWordWrap(True)
        self.artist_label.setFixedHeight(24)
        layout.addWidget(self.song_label)
        layout.addWidget(self.artist_label)

        timeline = QHBoxLayout()
        timeline.setContentsMargins(0, 2, 0, 0)
        timeline.setSpacing(10)
        self.elapsed = QLabel("00:00")
        self.elapsed.setObjectName("miniTimeLabel")
        self.duration = QLabel("00:00")
        self.duration.setObjectName("miniTimeLabel")
        self.slider = SeekSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("miniPositionSlider")
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.sliderPressed.connect(self.window._start_seek)
        self.slider.sliderReleased.connect(self.seek_from_slider)
        timeline.addWidget(self.elapsed)
        timeline.addWidget(self.slider, 1)
        timeline.addWidget(self.duration)
        layout.addLayout(timeline)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 2, 0, 0)
        controls.setSpacing(16)
        controls.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.repeat_button = self.control_button("repeat", self.toggle_repeat_from_mini)
        self.prev_button = self.control_button("prev", self.window.previous_track)
        self.play_button = self.control_button("play", self.window.toggle_play, primary=True)
        self.next_button = self.control_button("next", self.window.next_track)
        self.volume_button = self.control_button("volume", self.toggle_mute_from_mini)
        self.repeat_button.setCheckable(True)
        self.volume_button.setCheckable(True)
        controls.addWidget(self.repeat_button)
        controls.addWidget(self.prev_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.volume_button)
        layout.addLayout(controls)

        layout.addStretch(1)

    def on_video_frame_changed(self) -> None:
        frame = self.video_sink.videoFrame()
        if not frame or not frame.isValid():
            return
        image = frame.toImage()
        if not image.isNull():
            self.raw_video_frame = image
            # Apply a light blur by downsampling to 160x160 and then upsampling
            blurred = self.raw_video_frame.scaled(
                160, 160,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            self.scaled_video_frame = blurred.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            self.update()
            
            # Dynamically grab the first valid non-black frame as the disc's thumbnail
            if getattr(self, "has_video_thumbnail", False) is False:
                # Check if it's not a black frame (using lightness threshold of 40)
                is_black = True
                w, h = image.width(), image.height()
                if w > 0 and h > 0:
                    samples = [
                        image.pixelColor(w // 4, h // 4),
                        image.pixelColor(w // 2, h // 4),
                        image.pixelColor(w // 2, h // 2),
                        image.pixelColor(w // 4, h // 2),
                        image.pixelColor(3 * w // 4, 3 * h // 4)
                    ]
                    for c in samples:
                        if c.lightness() > 40:
                            is_black = False
                            break
                
                if not is_black:
                    self.has_video_thumbnail = True
                    track = self.window.current_track()
                    if track:
                        # Save image to cache so all views use the same image!
                        cache_path = embedded_art_cache_path(track.path)
                        try:
                            cache_path.parent.mkdir(exist_ok=True)
                            image.save(str(cache_path), "JPG")
                            no_art_path = embedded_no_art_path(track.path)
                            if no_art_path.exists():
                                try:
                                    no_art_path.unlink()
                                except OSError:
                                    pass
                            # Register cover to update UI and other caches
                            self.window.register_extracted_cover(track)
                        except Exception as e:
                            print(f"Failed to cache captured video thumbnail: {e}")
                    
                    pixmap = QPixmap.fromImage(image)
                    size = self.disc.width()
                    if size <= 0:
                        size = 280
                    scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    if scaled.width() != size or scaled.height() != size:
                        x = max(0, (scaled.width() - size) // 2)
                        y = max(0, (scaled.height() - size) // 2)
                        scaled = scaled.copy(x, y, size, size)
                    self.disc.set_disc(scaled, self.current_accent)

    def paintEvent(self, event) -> None:
        # First, draw standard background (stylesheet)
        super().paintEvent(event)
        
        # Draw video frame if playing a video
        track = self.window.current_track()
        is_video = track is not None and str(track.path).lower().endswith(".mp4")
        
        if is_video and getattr(self, "scaled_video_frame", None) is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            
            # Draw center crop of the expanded frame to cover the entire panel
            target_rect = self.rect()
            s_width = target_rect.width()
            s_height = target_rect.height()
            
            # scaled_video_frame is pre-scaled to fully cover the target size,
            # so we crop the excess from the center.
            x = max(0, (self.scaled_video_frame.width() - s_width) // 2)
            y = max(0, (self.scaled_video_frame.height() - s_height) // 2)
            source_rect = QRectF(x, y, s_width, s_height)
            
            painter.drawImage(QRectF(target_rect), self.scaled_video_frame, source_rect)
            
            # Draw a subtle dark gradient at the bottom (bottom 35% of the height) to ensure text/controls are readable
            gradient = QLinearGradient(0, self.height() * 0.65, 0, self.height())
            gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
            gradient.setColorAt(1.0, QColor(0, 0, 0, 180))
            painter.fillRect(QRectF(0, self.height() * 0.65, self.width(), self.height() * 0.35), gradient)
            
            painter.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        
        # Re-scale video frame on resize if present
        if getattr(self, "raw_video_frame", None) is not None:
            blurred = self.raw_video_frame.scaled(
                160, 160,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            self.scaled_video_frame = blurred.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
        
        # Calculate dynamic disc size based on current width (min 200px, max 450px)
        disc_size = min(max(200, self.width() - 40), 450)
        self.disc.setFixedSize(disc_size, disc_size)
        
        # Scale the mini wave visualizer proportionally
        visualizer_width = min(260, self.width() - 80)
        self.mini_wave.setFixedSize(visualizer_width, 40)
        
        # Re-fit labels for the new width
        self.refit_labels()
        
        # Remember preferred size when resized by user (splitter dragging)
        anim = getattr(self.window, "splitter_animation", None)
        is_animating = anim is not None and anim.state() == QVariantAnimation.State.Running
        if self.isVisible() and not is_animating and self.width() > 50:
            self.window.preferred_now_playing_width = self.width()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        track = self.window.current_track()
        if track and str(track.path).lower().endswith(".mp4"):
            self.window.player.setVideoOutput(self.video_sink)

    def refit_labels(self) -> None:
        track = self.window.current_track()
        if track is None:
            self.set_fitted_label(self.song_label, self.window.tr("not_playing"), 22, 14, 2)
            self.artist_label.setText("")
        else:
            self.set_fitted_label(self.song_label, track.title, 20, 7, 5)
            self.set_fitted_label(self.artist_label, f"{track.artist} · {self.window.display_album(track.album)}", 13, 10, 1)

    def control_button(self, kind: str, callback, primary: bool = False) -> MiniControlButton:
        return MiniControlButton(kind, callback, primary)

    def toggle_repeat_from_mini(self) -> None:
        self.window.toggle_repeat()
        self.update_extra_buttons()

    def toggle_mute_from_mini(self) -> None:
        current = int(round(self.window.audio.volume() * 100))
        previous = getattr(self, "previous_volume", 80)
        if current > 0:
            self.previous_volume = current
            self.window.volume.setValue(0)
        else:
            self.window.volume.setValue(max(25, previous))
        self.update_extra_buttons()

    def update_extra_buttons(self) -> None:
        if hasattr(self, "repeat_button"):
            self.repeat_button.setChecked(self.window.repeat_enabled)
        if hasattr(self, "volume_button"):
            self.volume_button.setChecked(self.window.audio.volume() <= 0.001)

    def seek_from_slider(self) -> None:
        self.window.is_user_seeking = False
        self.window.player.setPosition(self.slider.value())

    def update_language(self) -> None:
        self.title_label.setText(self.window.tr("now_playing_title"))

    def update_track(self, track: Track | None) -> None:
        self.update_language()
        if track is None:
            self.apply_dynamic_background(QColor("#1d90f4"))
            self.disc.set_disc(QPixmap(), QColor("#1d90f4"))
            self.disc.set_spinning(False)
            self.mini_wave.set_accent(QColor("#1d90f4"))
            self.set_fitted_label(self.song_label, self.window.tr("not_playing"), 22, 14, 2)
            self.artist_label.setText("")
            self.update_extra_buttons()
            self.disc.setVisible(True)
            self.mini_wave.setVisible(True)
            self.raw_video_frame = None
            self.scaled_video_frame = None
            self.update()
            return
        cover = self.window.safe_track_pixmap(track, 360, allow_extract=True)
        accent = self.extract_accent_color(cover)
        self.apply_dynamic_background(accent)
        self.disc.set_disc(cover, accent)
        self.mini_wave.set_accent(accent)
        self.disc.set_spinning(self.window.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self.set_fitted_label(self.song_label, track.title, 20, 7, 5)
        self.set_fitted_label(self.artist_label, f"{track.artist} · {self.window.display_album(track.album)}", 13, 10, 1)
        self.update_extra_buttons()

        is_video = track is not None and str(track.path).lower().endswith(".mp4")
        self.disc.setVisible(True)
        self.mini_wave.setVisible(True)
        if is_video:
            cover_path = self.window.track_art_path(track, allow_extract=True)
            has_real_cover = cover_path is not None and cover_path.exists()
            self.has_video_thumbnail = has_real_cover
            self.window.player.setVideoOutput(self.video_sink)
        else:
            self.raw_video_frame = None
            self.scaled_video_frame = None
            self.update()

    def extract_accent_color(self, pixmap: QPixmap) -> QColor:
        if pixmap.isNull():
            return QColor("#1d90f4")

        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32).scaled(
            28,
            28,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        red = green = blue = count = 0
        for y in range(image.height()):
            for x in range(image.width()):
                color = QColor(image.pixel(x, y))
                if color.lightness() < 28 or color.lightness() > 235:
                    continue
                saturation_weight = max(1, color.saturation())
                red += color.red() * saturation_weight
                green += color.green() * saturation_weight
                blue += color.blue() * saturation_weight
                count += saturation_weight

        if count <= 0:
            return QColor("#1d90f4")

        accent = QColor(red // count, green // count, blue // count)
        if accent.saturation() < 55:
            accent = QColor("#1d90f4")
        if accent.lightness() < 74:
            accent = accent.lighter(140)
        if accent.lightness() > 190:
            accent = accent.darker(135)
        return accent

    def apply_dynamic_background(self, accent: QColor) -> None:
        target_accent = accent if accent.isValid() else QColor("#1d90f4")
        target_bg = self.solid_background_color(target_accent)
        
        if getattr(self, "bg_animation", None) is not None:
            self.bg_animation.stop()
            
        start_accent = self.current_accent
        start_bg = self.current_bg
        
        self.bg_animation = QVariantAnimation(self)
        self.bg_animation.setStartValue(0.0)
        self.bg_animation.setEndValue(1.0)
        self.bg_animation.setDuration(450)
        self.bg_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        def interp(c1: QColor, c2: QColor, t: float) -> QColor:
            r = int(c1.red() + t * (c2.red() - c1.red()))
            g = int(c1.green() + t * (c2.green() - c1.green()))
            b = int(c1.blue() + t * (c2.blue() - c1.blue()))
            return QColor(r, g, b)
            
        track = self.window.current_track()
        is_video = track is not None and str(track.path).lower().endswith(".mp4")

        def update_style(t):
            curr_accent = interp(start_accent, target_accent, t)
            curr_bg = interp(start_bg, target_bg, t)
            
            self.current_accent = curr_accent
            self.current_bg = curr_bg
            
            bg_val = "transparent" if is_video else curr_bg.name()
            
            self.setStyleSheet(
                self.window.styleSheet()
                + f"""
                QWidget#nowPlayingWindow {{
                    background: {bg_val};
                }}
                QWidget#nowPlayingWindow::disabled {{
                    background: {bg_val};
                }}
                QWidget#discWidget {{
                    background: transparent;
                }}
                QLabel#miniTitle {{
                    color: {curr_accent.lighter(150).name()};
                }}
                QToolButton#miniControlButton {{
                    background: rgba(255, 255, 255, 34);
                }}
                QToolButton#miniControlButton:hover {{
                    background: rgba(255, 255, 255, 58);
                }}
                QToolButton#miniControlButton:checked {{
                    background: rgba(29, 144, 244, 82);
                    color: {curr_accent.lighter(175).name()};
                }}
                QToolButton#miniPlayButton {{
                    background: rgba(255, 255, 255, 42);
                }}
                QToolButton#miniPlayButton:hover {{
                    background: rgba(255, 255, 255, 70);
                }}
                """
            )
            
        self.bg_animation.valueChanged.connect(update_style)
        self.bg_animation.start()


    def solid_background_color(self, accent: QColor) -> QColor:
        hue, saturation, value, _alpha = accent.getHsv()
        if hue < 0:
            hue = 208
        saturation = min(200, max(70, int(saturation * 0.85)))
        value = min(28, max(14, int(value * 0.20)))
        return QColor.fromHsv(hue, saturation, value)

    def set_fitted_label(self, label: QLabel, text: str, max_size: int, min_size: int, max_lines: int) -> None:
        available_width = self.label_text_width(label)
        available_height = max(12, label.height() - 6)
        for size in range(max_size, min_size - 1, -1):
            font = label.font()
            font.setPixelSize(size)
            font.setBold(label.objectName() == "miniSong")
            metrics = QFontMetrics(font)
            wrapped = self.wrap_text(text, metrics, available_width, max_lines)
            if wrapped and self.text_fits(wrapped, metrics, available_width, available_height):
                label.setFont(font)
                label.setText(wrapped)
                label.setToolTip(text)
                return

        for size in range(min_size - 1, 5, -1):
            font = label.font()
            font.setPixelSize(size)
            font.setBold(label.objectName() == "miniSong")
            metrics = QFontMetrics(font)
            line_budget = max(1, min(max_lines + 2, available_height // max(1, metrics.lineSpacing())))
            wrapped = self.wrap_text(text, metrics, available_width, line_budget)
            if wrapped and self.text_fits(wrapped, metrics, available_width, available_height):
                label.setFont(font)
                label.setText(wrapped)
                label.setToolTip(text)
                return

        font = label.font()
        font.setPixelSize(6)
        font.setBold(label.objectName() == "miniSong")
        metrics = QFontMetrics(font)
        line_budget = max(1, available_height // max(1, metrics.lineSpacing()))
        label.setFont(font)
        label.setText(self.wrap_text(text, metrics, available_width, line_budget) or text)
        label.setToolTip(text)

    def label_text_width(self, label: QLabel) -> int:
        window_width = self.width() if self.width() > 80 else 360
        fallback_width = max(80, window_width - 52)
        label_width = label.width() if label.width() > 80 else fallback_width
        return max(80, min(label_width - 8, fallback_width))

    def text_fits(self, text: str, metrics: QFontMetrics, width: int, height: int) -> bool:
        lines = text.splitlines() or [text]
        if any(metrics.horizontalAdvance(line) > width for line in lines):
            return False
        return len(lines) * metrics.lineSpacing() <= height

    def wrap_text(self, text: str, metrics: QFontMetrics, width: int, max_lines: int) -> str:
        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            chunks = self.split_long_word(word, metrics, width)
            for chunk in chunks:
                current = self.add_wrap_chunk(lines, current, chunk, metrics, width, max_lines)
                if len(lines) > max_lines:
                    return ""

        if current:
            lines.append(current)

        if len(lines) > max_lines:
            return ""
        return "\n".join(lines)

    def add_wrap_chunk(
        self,
        lines: list[str],
        current: str,
        chunk: str,
        metrics: QFontMetrics,
        width: int,
        max_lines: int,
    ) -> str:
        candidate = f"{current} {chunk}".strip()
        if metrics.horizontalAdvance(candidate) <= width or not current:
            return candidate
        lines.append(current)
        if len(lines) > max_lines:
            return ""
        return chunk

    def split_long_word(self, word: str, metrics: QFontMetrics, width: int) -> list[str]:
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

    def update_position(self, position: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(position)
        self.elapsed.setText(format_ms(position))

    def update_duration(self, duration: int) -> None:
        self.slider.setRange(0, max(0, duration))
        self.duration.setText(format_ms(duration))

    def update_play_button(self) -> None:
        playing = self.window.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.set_kind("pause" if playing else "play")
        self.disc.set_spinning(playing and self.window.current_track() is not None)
        self.update_extra_buttons()


