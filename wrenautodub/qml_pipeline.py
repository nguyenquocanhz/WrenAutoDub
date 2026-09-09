# -*- coding: utf-8 -*-
"""Cầu nối chuỗi 4 bước cho giao diện QML.

Bản QML trước đây chỉ có màn hình dựng, mà chuỗi 4 bước chạy nhiều phút mới
là phần lõi của sản phẩm — người dùng mở app với một file phim và muốn ra bản
thuyết minh. Bản Widgets có thanh tiến độ 4 bước, bản QML đánh rơi hẳn.

Chạy pipeline bằng QProcess chứ không gọi thẳng trong tiến trình giao diện:
giao diện không bao giờ đứng hình, và dừng giữa chừng chỉ là kill tiến trình
con — mọi thứ đã làm xong vẫn nằm trong `phim_work/`.

Không import Qt Widgets ở đây, để tầng logic vẫn dùng chung được cho cả hai
giao diện.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import (QObject, QProcess, QProcessEnvironment, QTimer,
                          pyqtProperty, pyqtSignal, pyqtSlot)

ROOT = Path(__file__).resolve().parent.parent
WREN = ROOT / "wren.py"

# Tỉ trọng thời gian từng bước, đo trên phim thật. Chia đúng như vậy thì thanh
# tiến độ tổng không bao giờ đứng im ở 50% suốt nửa thời gian.
STAGE_RANGE = {1: (0.0, 0.50), 2: (0.50, 0.62), 3: (0.62, 0.92), 4: (0.92, 1.0)}

TEN_BUOC = ["Lấy lời thoại gốc", "Dịch sang tiếng Việt",
            "Thuyết minh", "Ghép video"]

RE_STAGE = re.compile(r"===\s*(\d)/4\s+(.+?)\s*===")
RE_ASR = re.compile(r"\[asr\]\s+([\d.]+)%")
RE_OCR = re.compile(r"\[ocr\]\s+(\d+)/(\d+)\s+đoạn")
RE_TRANS = re.compile(r"\[dịch\]\s+(\d+)/(\d+)\s+câu")
RE_SYNTH = re.compile(r"\[tts\]\s+tổng hợp\s+(\d+)/(\d+)")
RE_FIT = re.compile(r"\[tts\]\s+ép timing\s+(\d+)/(\d+)")
RE_RESULT = re.compile(r"Kết quả:\s*(.+)")
RE_XONG = re.compile(r"xong:\s*(.+?)\s*\((\d+)\s*câu")
RE_EP = re.compile(r"\[tts\]\s+(\d+)\s+câu dài quá khung")


def py_env() -> QProcessEnvironment:
    env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONIOENCODING", "utf-8")
    env.insert("PYTHONUTF8", "1")
    return env


class Runner(QProcess):
    """QProcess biết tách dòng và phân biệt dòng tiến độ (ghi đè bằng CR)."""

    line = pyqtSignal(str)
    tick = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buf = ""
        self.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.setWorkingDirectory(str(ROOT))
        self.setProcessEnvironment(py_env())
        self.readyReadStandardOutput.connect(self._read)

    def launch(self, args: List[str]) -> None:
        self._buf = ""
        self.start(sys.executable, ["-u", str(WREN), *args])

    def _read(self) -> None:
        self._buf += bytes(self.readAllStandardOutput()).decode(
            "utf-8", errors="replace")
        while "\n" in self._buf:
            raw, self._buf = self._buf.split("\n", 1)
            # Bỏ CR của CRLF TRƯỚC, không thì cái split dưới ăn sạch nội dung
            # dòng và chỉ còn chuỗi rỗng.
            raw = raw.rstrip("\r")
            self.line.emit(raw.split("\r")[-1].rstrip())
        if "\r" in self._buf:
            self._buf = self._buf.split("\r")[-1]
            if self._buf.strip():
                self.tick.emit(self._buf.rstrip())


class PipelineBridge(QObject):
    """Trạng thái chuỗi 4 bước, phơi ra cho QML."""

    changed = pyqtSignal()
    logAdded = pyqtSignal(str)
    finished = pyqtSignal(bool, str)        # (thành công, đường dẫn kết quả)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video = ""
        self._stage = 0                     # 0 = chưa chạy
        self._frac = 0.0                    # tiến độ trong bước hiện tại
        self._chi_tiet = ""                 # dòng tiến độ đang cập nhật
        self._ket_qua = ""
        self._dang_chay = False
        self._loi = ""
        self._log: List[str] = []
        self._so_cau = 0
        self._ep_qua = 0
        self._xong: List[str] = ["", "", "", ""]    # tóm tắt từng bước đã xong

        self.proc = Runner(self)
        self.proc.line.connect(self._dong)
        self.proc.tick.connect(self._nhip)
        self.proc.finished.connect(self._ket_thuc)

        # Nhịp gửi tín hiệu: mỗi dòng tiến độ mà phát changed thì QML vẽ lại
        # hàng trăm lần một giây, tốn vô ích.
        self._hen = QTimer(self)
        self._hen.setInterval(120)
        self._hen.setSingleShot(True)
        self._hen.timeout.connect(self.changed)

    def _bao(self) -> None:
        if not self._hen.isActive():
            self._hen.start()

    # ------------------------------------------------------------ thuộc tính
    @pyqtProperty(str, notify=changed)
    def video(self):
        return self._video

    @pyqtProperty(int, notify=changed)
    def stage(self):
        return self._stage

    @pyqtProperty(str, notify=changed)
    def stageName(self):
        i = self._stage - 1
        return TEN_BUOC[i] if 0 <= i < len(TEN_BUOC) else ""

    @pyqtProperty(float, notify=changed)
    def stageFrac(self):
        return self._frac

    @pyqtProperty(float, notify=changed)
    def overall(self):
        lo, hi = STAGE_RANGE.get(self._stage, (0.0, 0.0))
        return lo + (hi - lo) * max(0.0, min(1.0, self._frac))

    @pyqtProperty(str, notify=changed)
    def detail(self):
        return self._chi_tiet

    @pyqtProperty(bool, notify=changed)
    def running(self):
        return self._dang_chay

    @pyqtProperty(str, notify=changed)
    def result(self):
        return self._ket_qua

    @pyqtProperty(str, notify=changed)
    def error(self):
        return self._loi

    @pyqtProperty(int, notify=changed)
    def cueCount(self):
        return self._so_cau

    @pyqtProperty(int, notify=changed)
    def overFitted(self):
        """Số câu bị ép quá tay — việc người dùng phải sửa sau khi chạy xong."""
        return self._ep_qua

    @pyqtProperty("QStringList", notify=changed)
    def stageDone(self):
        return self._xong

    @pyqtProperty("QStringList", notify=changed)
    def logLines(self):
        return self._log[-200:]

    # --------------------------------------------------------------- điều khiển
    @pyqtSlot(str)
    @pyqtSlot(str, str)
    def start(self, video: str, lang: str = "") -> None:
        if self._dang_chay:
            return
        self._video = video
        self._stage = 0
        self._frac = 0.0
        self._chi_tiet = ""
        self._ket_qua = ""
        self._loi = ""
        self._so_cau = 0
        self._ep_qua = 0
        self._xong = ["", "", "", ""]
        self._log = []
        self._dang_chay = True
        args = ["run", video]
        if lang:
            args += ["--lang", lang]
        self.proc.launch(args)
        self.changed.emit()

    @pyqtSlot()
    def stop(self) -> None:
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()

    # ------------------------------------------------------------------ đọc
    def _dong(self, s: str) -> None:
        if s.strip():
            self._log.append(s)
            self.logAdded.emit(s)
        self._doc(s)
        self._bao()

    def _nhip(self, s: str) -> None:
        self._chi_tiet = s.strip()
        self._doc(s)
        self._bao()

    def _doc(self, s: str) -> None:
        m = RE_STAGE.search(s)
        if m:
            if 1 <= self._stage <= 4:
                self._xong[self._stage - 1] = self._xong[self._stage - 1] or "xong"
            self._stage = int(m.group(1))
            self._frac = 0.0
            return
        for rx, tinh in (
                (RE_ASR, lambda m: float(m.group(1)) / 100),
                (RE_OCR, lambda m: int(m.group(1)) / max(1, int(m.group(2)))),
                (RE_TRANS, lambda m: int(m.group(1)) / max(1, int(m.group(2)))),
                # Tổng hợp giọng chiếm 70% của bước 3, ép timing 30% còn lại.
                (RE_SYNTH, lambda m: 0.7 * int(m.group(1)) / max(1, int(m.group(2)))),
                (RE_FIT, lambda m: 0.7 + 0.3 * int(m.group(1)) / max(1, int(m.group(2)))),
        ):
            m = rx.search(s)
            if m:
                self._frac = max(0.0, min(1.0, tinh(m)))
                return
        m = RE_EP.search(s)
        if m:
            self._ep_qua = int(m.group(1))
            return
        m = RE_XONG.search(s)
        if m:
            self._so_cau = int(m.group(2))
            if 1 <= self._stage <= 4:
                self._xong[self._stage - 1] = f"{m.group(2)} câu"
            return
        m = RE_RESULT.search(s)
        if m:
            self._ket_qua = m.group(1).strip()

    def _ket_thuc(self, ma: int, _tt) -> None:
        self._dang_chay = False
        if ma == 0:
            self._stage = 4
            self._frac = 1.0
            self._xong[3] = self._xong[3] or "xong"
        else:
            self._loi = f"Dừng giữa chừng (mã {ma}). Chạy lại sẽ đi tiếp chỗ dở."
        self.changed.emit()
        self.finished.emit(ma == 0, self._ket_qua)
