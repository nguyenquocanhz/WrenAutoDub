# -*- coding: utf-8 -*-
"""Ảnh filmstrip và sóng âm cho dòng thời gian.

Cả hai đều chạy nền: filmstrip nhờ ffmpeg qua QProcess, sóng âm nhờ một luồng
riêng đọc file theo khối. Không thứ nào được chặn giao diện, vì phim 2 tiếng
thì cả hai đều mất vài giây.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import List, Optional

import numpy as np
from PyQt6.QtCore import QObject, QProcess, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

CACHE = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "WrenAutoDub" / "strips"
THUMB_H = 44                # chiều cao mỗi ô filmstrip
MAX_TILES = 240             # đủ mịn mà không phình ảnh


def _key(path: str, extra: str = "") -> str:
    st = Path(path).stat()
    raw = f"{path}|{st.st_size}|{int(st.st_mtime)}|{extra}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class FilmStrip(QObject):
    """Một ảnh dài ghép từ nhiều khung hình, cắt ra khi vẽ."""

    ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap: Optional[QPixmap] = None
        self.tiles = 0
        self._proc: Optional[QProcess] = None

    def load(self, video: str, duration: float) -> None:
        if not video or not Path(video).exists() or duration <= 0:
            return
        self.tiles = max(8, min(MAX_TILES, int(duration / 4) or 8))
        CACHE.mkdir(parents=True, exist_ok=True)
        out = CACHE / f"strip_{_key(video, str(self.tiles))}.png"

        if out.exists():
            self.pixmap = QPixmap(str(out))
            self.ready.emit()
            return

        # fps sao cho ra đúng `tiles` khung, rồi ghép thành một hàng ngang
        fps = self.tiles / max(duration, 0.1)
        vf = (f"fps={fps:.6f},scale=-1:{THUMB_H},tile={self.tiles}x1")
        args = ["-v", "error", "-i", video, "-vf", vf, "-frames:v", "1",
                "-y", str(out)]

        p = QProcess(self)
        p.finished.connect(lambda *_a: self._done(out))
        self._proc = p
        p.start("ffmpeg", args)

    def _done(self, out: Path) -> None:
        if out.exists():
            self.pixmap = QPixmap(str(out))
            if not self.pixmap.isNull():
                self.ready.emit()

    def tile_at(self, frac: float) -> Optional[QPixmap]:
        """Ô ảnh ứng với vị trí 0..1 trên dòng thời gian."""
        if not self.pixmap or self.pixmap.isNull() or self.tiles <= 0:
            return None
        w = self.pixmap.width() // self.tiles
        if w <= 0:
            return None
        i = max(0, min(self.tiles - 1, int(frac * self.tiles)))
        return self.pixmap.copy(i * w, 0, w, self.pixmap.height())

    def tile_rect(self, frac: float):
        """O nguon tren dai anh, de drawPixmap ve thang khong phai chep.

        tile_at() chep han mot QPixmap moi cho tung o, tung lan ve - 15 o
        nhan 25 fps la 375 lan chep anh moi giay, khong de lam gi.
        """
        from PyQt6.QtCore import QRect
        if not self.pixmap or self.pixmap.isNull() or self.tiles <= 0:
            return None
        w = self.pixmap.width() // self.tiles
        if w <= 0:
            return None
        i = max(0, min(self.tiles - 1, int(frac * self.tiles)))
        return QRect(i * w, 0, w, self.pixmap.height())


class _WaveWorker(QThread):
    done = pyqtSignal(object)

    def __init__(self, path: str, buckets: int):
        super().__init__()
        self.path, self.buckets = path, buckets

    def run(self) -> None:
        try:
            import soundfile as sf

            info = sf.info(self.path)
            total = info.frames
            if total <= 0:
                self.done.emit(None)
                return
            per = max(1, total // self.buckets)
            peaks = np.zeros(self.buckets, dtype=np.float32)
            i = 0
            # đọc theo khối để phim dài không nuốt hết RAM
            for block in sf.blocks(self.path, blocksize=per, dtype="float32",
                                   always_2d=True):
                if i >= self.buckets:
                    break
                peaks[i] = float(np.abs(block).max()) if block.size else 0.0
                i += 1
            m = float(peaks.max())
            if m > 0:
                peaks /= m
            self.done.emit(peaks)
        except Exception:
            self.done.emit(None)


class Waveform(QObject):
    """Mảng đỉnh biên độ đã chuẩn hoá về 0..1."""

    ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.peaks: Optional[np.ndarray] = None
        self._worker: Optional[_WaveWorker] = None

    def load(self, path: str, buckets: int = 1400) -> None:
        if not path or not Path(path).exists():
            self.peaks = None
            return
        cache = CACHE / f"wave_{_key(path, str(buckets))}.npy"
        CACHE.mkdir(parents=True, exist_ok=True)
        if cache.exists():
            try:
                self.peaks = np.load(cache)
                self.ready.emit()
                return
            except Exception:
                pass

        def finished(peaks):
            self.peaks = peaks
            if peaks is not None:
                try:
                    np.save(cache, peaks)
                except OSError:
                    pass
                self.ready.emit()

        self._worker = _WaveWorker(path, buckets)
        self._worker.done.connect(finished)
        self._worker.start()

    def at(self, frac: float) -> float:
        if self.peaks is None or len(self.peaks) == 0:
            return 0.0
        i = max(0, min(len(self.peaks) - 1, int(frac * len(self.peaks))))
        return float(self.peaks[i])
