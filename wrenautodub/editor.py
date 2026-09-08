# -*- coding: utf-8 -*-
"""Cửa sổ sửa video: xem trước, sửa phụ đề, vùng làm mờ / xoá logo / chèn logo.

Khung xem trước là ảnh tĩnh trích bằng ffmpeg chứ không phải trình phát: chạy
được với mọi định dạng ffmpeg đọc nổi, và vẽ vùng hiệu ứng lên đúng từng pixel.
Có nút xem trước kèm hiệu ứng để thấy kết quả thật trước khi xuất.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import (QPoint, QProcess, QProcessEnvironment, QRect, Qt,
                          QTimer, pyqtSignal)
from PyQt6.QtGui import (QBrush, QColor, QFont, QKeySequence, QPainter, QPen,
                         QPixmap, QShortcut)
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QDoubleSpinBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QProgressBar, QPushButton, QSlider, QSpinBox,
                             QSplitter, QTableWidget, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from . import hwaccel
from .edit import (BLUR, DELOGO, KIND_LABEL, LOGO, ExportSettings, History,
                   Project, Region, build_video_chain, human_size)
from .icons import icon
from .mux import DUCK_FLAT, DUCK_SIDECHAIN, escape_sub_path
from .srtutil import Cue, fmt_ts, parse_ts, read_srt, write_srt

HANDLE = 9
COLORS = {BLUR: QColor(90, 170, 250), DELOGO: QColor(240, 140, 70),
          LOGO: QColor(120, 220, 140)}


def ffprobe_info(path: str) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-of", "json", "-show_entries",
             "format=duration:stream=codec_type,width,height", path],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        d = json.loads(out.stdout or "{}")
        vid = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
        return {"width": int(vid.get("width", 0)), "height": int(vid.get("height", 0)),
                "duration": float(d.get("format", {}).get("duration", 0) or 0)}
    except Exception:
        return {"width": 0, "height": 0, "duration": 0.0}


# --------------------------------------------------------------- khung xem trước

class Preview(QLabel):
    """Vẽ khung hình và cho kéo thả vùng hiệu ứng lên trên nó."""

    changed = pyqtSignal()
    committed = pyqtSignal()        # thả chuột xong -> ghi vào lịch sử undo
    selected = pyqtSignal(int)

    def __init__(self, proj: Project, parent=None):
        super().__init__(parent)
        self.proj = proj
        self.frame: Optional[QPixmap] = None
        self.tool = ""              # "" = chỉ chọn; BLUR/DELOGO/LOGO = vẽ mới
        self.sel = -1
        self._drag = ""             # "new" | "move" | góc đang kéo
        self._p0 = QPoint()
        self._r0: Optional[Region] = None
        self.setMinimumSize(480, 270)
        self.setMouseTracking(True)
        self.setStyleSheet("background:#0f1013;")

    # ---- đổi qua lại giữa toạ độ widget và tỉ lệ khung hình

    def draw_rect(self) -> QRect:
        """Vùng ảnh thật nằm trong widget (đã letterbox cho vừa)."""
        if not self.frame or self.frame.isNull():
            return QRect(0, 0, self.width(), self.height())
        fw, fh = self.frame.width(), self.frame.height()
        s = min(self.width() / fw, self.height() / fh)
        w, h = int(fw * s), int(fh * s)
        return QRect((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def to_frac(self, p: QPoint) -> tuple[float, float]:
        r = self.draw_rect()
        return ((p.x() - r.x()) / max(1, r.width()),
                (p.y() - r.y()) / max(1, r.height()))

    def rect_of(self, reg: Region) -> QRect:
        r = self.draw_rect()
        return QRect(int(r.x() + reg.x * r.width()), int(r.y() + reg.y * r.height()),
                     int(reg.w * r.width()), int(reg.h * r.height()))

    # ---- vẽ

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(15, 16, 19))
        if self.frame and not self.frame.isNull():
            p.drawPixmap(self.draw_rect(), self.frame)
        else:
            p.setPen(QColor(140, 143, 148))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Đang lấy khung hình…")

        for i, reg in enumerate(self.proj.regions):
            col = COLORS.get(reg.kind, QColor(200, 200, 200))
            if not reg.enabled:
                col = QColor(120, 122, 126)
            rc = self.rect_of(reg)
            p.setPen(QPen(col, 3 if i == self.sel else 2,
                          Qt.PenStyle.SolidLine if reg.enabled else Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(col.red(), col.green(), col.blue(), 38)))
            p.drawRect(rc)

            p.setPen(col)
            f = QFont()
            f.setPointSize(8)
            p.setFont(f)
            p.drawText(rc.adjusted(4, -16, 0, 0), Qt.AlignmentFlag.AlignLeft,
                       f"{i + 1}. {KIND_LABEL.get(reg.kind, reg.kind)}")

            if i == self.sel:       # tay nắm ở 4 góc
                p.setBrush(QBrush(col))
                for c in (rc.topLeft(), rc.topRight(), rc.bottomLeft(), rc.bottomRight()):
                    p.drawRect(QRect(c.x() - HANDLE // 2, c.y() - HANDLE // 2, HANDLE, HANDLE))
        p.end()

    # ---- chuột

    def _corner_at(self, reg: Region, pos: QPoint) -> str:
        rc = self.rect_of(reg)
        for name, c in (("tl", rc.topLeft()), ("tr", rc.topRight()),
                        ("bl", rc.bottomLeft()), ("br", rc.bottomRight())):
            if abs(pos.x() - c.x()) <= HANDLE and abs(pos.y() - c.y()) <= HANDLE:
                return name
        return ""

    def mousePressEvent(self, e) -> None:
        pos = e.pos()
        if self.sel >= 0:
            corner = self._corner_at(self.proj.regions[self.sel], pos)
            if corner:
                self._drag, self._p0 = corner, pos
                self._r0 = Region(**vars(self.proj.regions[self.sel]))
                return

        for i in range(len(self.proj.regions) - 1, -1, -1):
            if self.rect_of(self.proj.regions[i]).contains(pos):
                self.sel = i
                self.selected.emit(i)
                self._drag, self._p0 = "move", pos
                self._r0 = Region(**vars(self.proj.regions[i]))
                self.update()
                return

        if self.tool:
            fx, fy = self.to_frac(pos)
            reg = Region(kind=self.tool, x=fx, y=fy, w=0.0, h=0.0)
            if self.tool == LOGO:
                reg.path = getattr(self, "logo_path", "")
            self.proj.regions.append(reg)
            self.sel = len(self.proj.regions) - 1
            self.selected.emit(self.sel)
            self._drag, self._p0 = "new", pos
            self._r0 = Region(**vars(reg))
            self.update()
        else:
            self.sel = -1
            self.selected.emit(-1)
            self.update()

    def mouseMoveEvent(self, e) -> None:
        if not self._drag or self.sel < 0 or self._r0 is None:
            return
        reg = self.proj.regions[self.sel]
        r = self.draw_rect()
        dx = (e.pos().x() - self._p0.x()) / max(1, r.width())
        dy = (e.pos().y() - self._p0.y()) / max(1, r.height())

        if self._drag == "move":
            reg.x = min(max(0.0, self._r0.x + dx), 1 - self._r0.w)
            reg.y = min(max(0.0, self._r0.y + dy), 1 - self._r0.h)
        elif self._drag == "new":
            fx, fy = self.to_frac(e.pos())
            reg.x, reg.w = min(self._r0.x, fx), abs(fx - self._r0.x)
            reg.y, reg.h = min(self._r0.y, fy), abs(fy - self._r0.y)
        else:
            if "l" in self._drag:
                reg.x = min(self._r0.x + dx, self._r0.x + self._r0.w - 0.02)
                reg.w = self._r0.w - (reg.x - self._r0.x)
            if "r" in self._drag:
                reg.w = max(0.02, self._r0.w + dx)
            if "t" in self._drag:
                reg.y = min(self._r0.y + dy, self._r0.y + self._r0.h - 0.02)
                reg.h = self._r0.h - (reg.y - self._r0.y)
            if "b" in self._drag:
                reg.h = max(0.02, self._r0.h + dy)

        reg.x, reg.y = max(0.0, reg.x), max(0.0, reg.y)
        reg.w = min(reg.w, 1 - reg.x)
        reg.h = min(reg.h, 1 - reg.y)
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._drag:
            if self.sel >= 0:
                reg = self.proj.regions[self.sel]
                if reg.w < 0.01 or reg.h < 0.01:     # click hụt, không tạo vùng tí hon
                    self.proj.regions.pop(self.sel)
                    self.sel = -1
                    self.selected.emit(-1)
            self._drag, self._r0 = "", None
            self.committed.emit()
            self.update()


# ------------------------------------------------------------ hộp thoại xuất

class ExportDialog(QDialog):
    """Chạy ffmpeg xuất bản, kèm cảnh báo đừng tắt máy."""

    def __init__(self, cmd: List[str], duration: float, out_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Đang xuất video")
        self.setWindowIcon(icon("play", 64))
        self.setMinimumWidth(560)
        self.out_path = out_path
        self.duration = max(1.0, duration)
        self.ok = False

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.lb = QLabel("Đang khởi động ffmpeg…")
        self.lb.setWordWrap(True)

        warn = QLabel(
            "<b>Đang xử lý hiệu ứng — vui lòng không tắt máy.</b><br>"
            "Quá trình này mã hoá lại toàn bộ video, chạy lâu và ăn pin. "
            "Nên cắm sạc trước khi tiếp tục.")
        warn.setWordWrap(True)
        warn.setStyleSheet(
            "background:#3a2f16; color:#f0d79a; border:1px solid #7a6425;"
            "border-radius:6px; padding:10px;")

        self.lb_power = QLabel(self._power_text())
        self.lb_power.setStyleSheet("color:#9aa0a6;")

        self.btn_cancel = QPushButton(icon("stop"), " Huỷ")
        self.btn_cancel.clicked.connect(self.cancel)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_cancel)

        lay = QVBoxLayout(self)
        lay.addWidget(warn)
        lay.addWidget(self.lb_power)
        lay.addWidget(self.bar)
        lay.addWidget(self.lb)
        lay.addLayout(row)

        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self._buf = ""
        self._tail: List[str] = []
        QTimer.singleShot(80, lambda: self.proc.start(cmd[0], cmd[1:]))

        self._power = QTimer(self)
        self._power.timeout.connect(lambda: self.lb_power.setText(self._power_text()))
        self._power.start(15000)

    @staticmethod
    def _power_text() -> str:
        try:
            import psutil
            b = psutil.sensors_battery()
        except Exception:
            return ""
        if b is None:
            return "Nguồn: máy bàn / không có pin — yên tâm."
        if b.power_plugged:
            return f"Nguồn: đang cắm sạc, pin {b.percent:.0f}%."
        mins = b.secsleft // 60 if b.secsleft and b.secsleft > 0 else None
        extra = f", còn khoảng {mins} phút" if mins else ""
        return (f"⚠ Nguồn: ĐANG CHẠY PIN {b.percent:.0f}%{extra} — hãy cắm sạc, "
                f"hết pin giữa chừng là mất công xuất lại từ đầu.")

    def _read(self) -> None:
        self._buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip().rstrip("\r")
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    us = int(line.split("=", 1)[1])
                    # ffmpeg ghi nhầm tên: out_time_ms thật ra cũng là micro giây
                    self.bar.setValue(int(min(100, us / 1e6 / self.duration * 100)))
                except ValueError:
                    pass
            elif line.startswith("speed="):
                sp = line.split("=", 1)[1]
                left = (100 - self.bar.value()) / 100 * self.duration
                try:
                    s = float(sp.rstrip("x") or 1)
                    self.lb.setText(f"Tốc độ {sp} — còn khoảng {left / max(s, 0.01) / 60:.1f} phút")
                except ValueError:
                    self.lb.setText(f"Tốc độ {sp}")
            elif line and not line.startswith(("frame=", "fps=", "bitrate=", "total_size=",
                                               "out_time=", "dup_frames=", "drop_frames=",
                                               "progress=", "stream_")):
                self._tail.append(line)
                self._tail = self._tail[-8:]

    def _done(self, code: int, _s) -> None:
        self._power.stop()
        self.ok = code == 0 and self.out_path.exists()
        if self.ok:
            self.bar.setValue(100)
            size = human_size(self.out_path.stat().st_size)
            self.lb.setText(f"Xong — {self.out_path.name} ({size})")
            QTimer.singleShot(900, self.accept)
        else:
            self.lb.setText("ffmpeg lỗi:\n" + "\n".join(self._tail[-5:]))
            self.btn_cancel.setText(" Đóng")

    def cancel(self) -> None:
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()
            self.proc.waitForFinished(3000)
        self.reject()

    def closeEvent(self, e) -> None:
        self.cancel()
        e.accept()
