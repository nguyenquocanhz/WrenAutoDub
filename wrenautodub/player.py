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

import time

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink

# Toi da mot lenh tua moi chung nay mili giay khi dang keo dau doc.
# 90ms la nguong do duoc: thap hon thi bo giai ma nghen, cao hon thi
# hinh chay theo tay tre thay ro.
SEEK_GOP_MS = 90.0

DRIFT_MS = 300          # lệch quá ngần này thì kéo track thuyết minh về

MIX_ORIG, MIX_DUB, MIX_BOTH = "goc", "thuyetminh", "ca_hai"


class VideoPlayer(QObject):
    """Bọc hai QMediaPlayer: một cho hình + tiếng gốc, một cho giọng thuyết minh."""

    frameReady = pyqtSignal(QImage)
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
        self._moi_nap = False       # dang cho khung hinh dau tien sau khi mo
        self._seek_dich = 0.0       # vi tri tua dang cho, xem seek()
        self._seek_luc = 0.0
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.timeout.connect(self._tua_that)

        self.sink.videoFrameChanged.connect(self._on_frame)
        self.video.mediaStatusChanged.connect(self._on_status)
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
        self._moi_nap = True

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

    def seek(self, seconds: float, ngay: bool = False) -> None:
        """Tua. Kéo đầu đọc thì GỘP lệnh lại thay vì tua theo từng pixel.

        Mỗi setPosition bắt bộ giải mã xả sạch rồi nạp lại từ khung khoá.
        Kéo chuột sinh ~60 sự kiện mỗi giây; tua đủ 60 lần thì bộ giải mã
        không kịp thở — đo được 2.3 FPS và có lần đứng hình 5.2 giây. Gộp
        lại còn tối đa ~1 lần mỗi SEEK_GOP_MS, và luôn tua đúng vị trí cuối
        cùng khi thả tay (ngay=True).
        """
        self._seek_dich = max(0.0, seconds)
        if ngay:
            self._seek_timer.stop()
            self._tua_that()
            return
        tu_lan_truoc = (time.monotonic() - self._seek_luc) * 1000
        if tu_lan_truoc >= SEEK_GOP_MS:
            self._tua_that()
        elif not self._seek_timer.isActive():
            self._seek_timer.start(int(SEEK_GOP_MS - tu_lan_truoc))

    def _tua_that(self) -> None:
        self._seek_luc = time.monotonic()
        ms = int(self._seek_dich * 1000)
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
        # Phat thang QImage. Doi qua QPixmap tuong nhu re nhung do la mot lan
        # chuyen dinh dang cong mot lan tai len GPU cho MOI khung: da do,
        # bo no giam CPU tu 48.5% xuong 26.2% mot loi ma van du 25 fps.
        self.frameReady.emit(img)

    def _on_status(self, st) -> None:
        """Nhá phát rồi dừng ngay, chỉ để lấy khung hình đầu tiên.

        QMediaPlayer khong giai ma khung nao cho toi khi that su phat. Chi
        setSource roi doi thi khung xem truoc dung o "Dang lay khung hinh..."
        vinh vien - da do: qua 15 giay van trong, ke ca sau khi goi seek(0).
        Nha mot cai thi khung dau tien ve sau 0.15 giay.
        """
        if not self._moi_nap:
            return
        ok = (QMediaPlayer.MediaStatus.LoadedMedia,
              QMediaPlayer.MediaStatus.BufferedMedia)
        if st not in ok:
            return
        self._moi_nap = False
        self.a_video.setMuted(True)          # dung de bat ra tieng khi vua mo
        self.video.play()
        QTimer.singleShot(0, self._dung_nha)

    def _dung_nha(self) -> None:
        """Dừng cú nhá lấy khung hình đầu tiên.

        KHÔNG kéo về 0: cửa sổ editor hẹn seek(3.0) sau 120ms, mà cú nhá này
        chạy ở ~200ms nên sẽ đè lên, hình đứng ở 0.00 thay vì 3s. Chỉ trả về
        0 khi chưa ai tua đi đâu.
        """
        self.video.pause()
        if self._seek_luc == 0.0 and self._seek_dich == 0.0:
            self.video.setPosition(0)
        self.a_video.setMuted(False)

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
