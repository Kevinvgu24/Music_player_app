import sys
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import ClassInfo, Property, QUrl, Slot
from PySide6.QtMultimedia import QMediaPlayer

try:
    from PySide6.QtDBus import QDBusAbstractAdaptor, QDBusConnection, QDBusInterface, QDBusMessage, QDBusObjectPath
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False
    # Define stubs for Windows/macOS compatibility
    class QDBusAbstractAdaptor:
        def __init__(self, parent: Any) -> None:
            pass
    class QDBusConnection:
        @classmethod
        def sessionBus(cls) -> Any:
            return None
    class QDBusInterface:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
        def call(self, *args: Any, **kwargs: Any) -> Any:
            return None
    class QDBusMessage:
        class MessageType:
            ErrorMessage = 0
            ReplyMessage = 1
        def type(self) -> int:
            return 0
    class QDBusObjectPath:
        def __init__(self, path: str) -> None:
            self.path = path

from constants import APP_NAME


def dbus_interface(name: str) -> Any:
    if not HAS_DBUS:
        return lambda cls: cls
    return cast(Any, ClassInfo)({"D-Bus Interface": name})

@dbus_interface("org.mpris.MediaPlayer2")
class MprisRootAdaptor(QDBusAbstractAdaptor):
    def __init__(self, window: "PlayerWindow") -> None:
        super().__init__(window)
        self.window = window

    @Slot()
    def Raise(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    @Slot()
    def Quit(self) -> None:
        self.window.close()

    @Property(bool)
    def CanQuit(self) -> bool:
        return True

    @Property(bool)
    def CanRaise(self) -> bool:
        return True

    @Property(bool)
    def HasTrackList(self) -> bool:
        return False

    @Property(str)
    def Identity(self) -> str:
        return APP_NAME

    @Property(str)
    def DesktopEntry(self) -> str:
        return "playlist-offline"

    @Property("QStringList")
    def SupportedUriSchemes(self) -> list[str]:
        return ["file"]

    @Property("QStringList")
    def SupportedMimeTypes(self) -> list[str]:
        return ["audio/mpeg", "audio/flac", "audio/x-wav", "audio/mp4", "audio/ogg"]


@dbus_interface("org.mpris.MediaPlayer2.Player")
class MprisPlayerAdaptor(QDBusAbstractAdaptor):
    def __init__(self, window: "PlayerWindow") -> None:
        super().__init__(window)
        self.window = window

    @Slot()
    def Next(self) -> None:
        self.window.next_track()

    @Slot()
    def Previous(self) -> None:
        self.window.previous_track()

    @Slot()
    def Pause(self) -> None:
        self.window.pause_current_track()

    @Slot()
    def PlayPause(self) -> None:
        self.window.toggle_play()

    @Slot()
    def Stop(self) -> None:
        self.window.stop()

    @Slot()
    def Play(self) -> None:
        current = self.window.current_track()
        if current is None and self.window.active_playlist():
            track = self.window.active_playlist()[0]
            self.window.current_index = self.window.tracks.index(track)
            self.window.play_track(track)
            return
        if self.window.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.window.resume_current_track(current)

    @Slot("qlonglong")
    def Seek(self, offset: int) -> None:
        self.window.player.setPosition(max(0, self.window.player.position() + offset // 1000))

    @Slot(QDBusObjectPath, "qlonglong")
    def SetPosition(self, _track_id: QDBusObjectPath, position: int) -> None:
        self.window.player.setPosition(max(0, position // 1000))

    @Slot(str)
    def OpenUri(self, uri: str) -> None:
        path = Path(QUrl(uri).toLocalFile())
        for track in self.window.tracks:
            if track.path == path:
                self.window.current_index = self.window.tracks.index(track)
                self.window.play_track(track)
                break

    @Property(str)
    def PlaybackStatus(self) -> str:
        return self.window.mpris_playback_status()

    @Property("QVariantMap")
    def Metadata(self) -> dict:
        return self.window.mpris_metadata()

    @Property(float)
    def Rate(self) -> float:
        return 1.0

    @Property(float)
    def MinimumRate(self) -> float:
        return 1.0

    @Property(float)
    def MaximumRate(self) -> float:
        return 1.0

    @Property(str)
    def LoopStatus(self) -> str:
        return "None"

    @Property(bool)
    def Shuffle(self) -> bool:
        return self.window.shuffle_enabled

    @Shuffle.setter
    def Shuffle(self, value: bool) -> None:
        self.window.shuffle_enabled = value
        self.window.shuffle_button.setChecked(value)
        self.window.update_shuffle_text()
        self.window.emit_mpris_properties("Shuffle")

    @Property(float)
    def Volume(self) -> float:
        return self.window.audio.volume()

    @Volume.setter
    def Volume(self, value: float) -> None:
        self.window.audio.setVolume(max(0.0, min(1.0, value)))
        self.window.volume.blockSignals(True)
        self.window.volume.setValue(round(self.window.audio.volume() * 100))
        self.window.volume.blockSignals(False)
        self.window.emit_mpris_properties("Volume")

    @Property("qlonglong")
    def Position(self) -> int:
        return self.window.player.position() * 1000

    @Property(bool)
    def CanGoNext(self) -> bool:
        return bool(self.window.active_playlist())

    @Property(bool)
    def CanGoPrevious(self) -> bool:
        return bool(self.window.active_playlist())

    @Property(bool)
    def CanPlay(self) -> bool:
        return bool(self.window.tracks)

    @Property(bool)
    def CanPause(self) -> bool:
        return True

    @Property(bool)
    def CanSeek(self) -> bool:
        return True

    @Property(bool)
    def CanControl(self) -> bool:
        return True


def raise_existing_instance() -> bool:
    if not HAS_DBUS:
        return False
    connection = QDBusConnection.sessionBus()
    bus_interface = connection.interface()
    if bus_interface is None:
        return False

    registered = bus_interface.isServiceRegistered("org.mpris.MediaPlayer2.playlistoffline")
    if not registered.isValid() or not registered.value():
        return False

    interface = QDBusInterface(
        "org.mpris.MediaPlayer2.playlistoffline",
        "/org/mpris/MediaPlayer2",
        "org.mpris.MediaPlayer2",
        connection,
    )
    reply = interface.call("Raise")
    return reply.type() != QDBusMessage.MessageType.ErrorMessage
