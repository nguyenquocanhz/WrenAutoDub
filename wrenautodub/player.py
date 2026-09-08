# -*- coding: utf-8 -*-
"""Phát video mượt bằng QMediaPlayer, khung hình lấy qua QVideoSink.

Cách cũ (QTimer gọi ffmpeg trích từng khung) chỉ được 2 FPS và mỗi khung tốn
~200ms khởi động tiến trình, nên giật. Ở đây khung do backend Windows Media
Foundation đẩy ra đúng nhịp thật của video.

Track thuyết minh phát bằng một player thứ hai chạy song song; nó trôi nhẹ so
với hình nên có kiểm tra và kéo lại khi lệch quá ngưỡng.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink

DRIFT_MS = 300          # lệch quá ngần này thì kéo track thuyết minh về

MIX_ORIG, MIX_DUB, MIX_BOTH = "goc", "thuyetminh", "ca_hai"


class VideoPlayer(QObject):
    """Bọc hai QMediaPlayer: một cho hình + tiếng gốc, một cho giọng thuyết minh."""

    frameReady = pyqtSignal(QPixmap)
    positionChanged = pyqtSignal(float)     # giây
    stateChanged = pyqtSignal(bool)         # True = đang chạy
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sink = QVideoSink(self)
        self.video = QMediaPlayer(self)
        self.a_video = QAudioOutput(self)
        self.video.setAudioOutput(self.a_video)
        self.video.setVideoSink(self.sink)

        self.dub = QMediaPlayer(self)
        self.a_dub = QAudioOutput(self)
        self.dub.setAudioOutput(self.a_dub)

        self.has_dub = False
        self.duration = 0.0
        self._ok = True

        self.sink.videoFrameChanged.connect(self._on_frame)
        self.video.positionChanged.connect(self._on_pos)
        self.video.playbackStateChanged.connect(self._on_state)
        self.video.errorOccurred.connect(self._on_error)
        self.set_mix(MIX_BOTH)

    # ------------------------------------------------------------------ nạp

    def open(self, video: str, dub: str = "") -> None:
        self.video.setSource(QUrl.fromLocalFile(str(Path(video).resolve())))
        self.has_dub = bool(dub) and Path(dub).exists()
        if self.has_dub:
            self.dub.setSource(QUrl.fromLocalFile(str(Path(dub).resolve())))
        self._ok = True

    def usable(self) -> bool:
        return self._ok

    # ------------------------------------------------------------- điều khiển

    def playing(self) -> bool:
        return self.video.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def toggle(self) -> None:
        self.pause() if self.playing() else self.play()

    def play(self) -> None:
        if not self._ok:
            return
        self.video.play()
        if self.has_dub:
            self.dub.setPosition(self.video.position())
            self.dub.play()

    def pause(self) -> None:
        self.video.pause()
        if self.has_dub:
            self.dub.pause()

    def stop(self) -> None:
        self.video.stop()
        if self.has_dub:
            self.dub.stop()

    def seek(self, seconds: float) -> None:
        ms = int(max(0.0, seconds) * 1000)
        self.video.setPosition(ms)
        if self.has_dub:
            self.dub.setPosition(ms)

    def position(self) -> float:
        return self.video.position() / 1000.0

    def set_speed(self, rate: float) -> None:
        self.video.setPlaybackRate(rate)
        if self.has_dub:
            self.dub.setPlaybackRate(rate)

    def set_mix(self, mode: str) -> None:
        """Chọn nghe tiếng gốc, giọng thuyết minh, hay cả hai."""
        self.a_video.setVolume({MIX_ORIG: 1.0, MIX_DUB: 0.0,
                                MIX_BOTH: 0.32}.get(mode, 0.32))
        self.a_dub.setVolume({MIX_ORIG: 0.0, MIX_DUB: 1.0,
                              MIX_BOTH: 1.0}.get(mode, 1.0))

    def set_dub_offset(self, seconds: float) -> None:
        """Dời khớp: đặt lại vị trí track thuyết minh so với hình."""
        if self.has_dub:
            self.dub.setPosition(max(0, self.video.position() - int(seconds * 1000)))

    # ------------------------------------------------------------------ nội bộ

    def _on_frame(self, frame) -> None:
        if not frame.isValid():
            return
        img: QImage = frame.toImage()
        if img.isNull():
            return
        self.frameReady.emit(QPixmap.fromImage(img))

    def _on_pos(self, ms: int) -> None:
        if self.has_dub and self.playing():
            d = abs(self.dub.position() - ms)
            if d > DRIFT_MS:            # hai player trôi khỏi nhau thì kéo lại
                self.dub.setPosition(ms)
        self.positionChanged.emit(ms / 1000.0)

    def _on_state(self, _s) -> None:
        self.stateChanged.emit(self.playing())

    def _on_error(self, _err, msg: str) -> None:
        self._ok = False
        self.failed.emit(msg or "không phát được định dạng này")
