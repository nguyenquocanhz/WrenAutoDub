# -*- coding: utf-8 -*-
"""Vỏ giao diện viết bằng QML — bản song song với cửa sổ Widgets.

Toàn bộ phần logic (edit.py, clips.py, timing.py, mux.py, pipeline...) dùng
chung, không đụng tới. Ở đây chỉ có lớp trình bày và cầu nối dữ liệu.

Giao diện nằm trong wrenautodub/qml/editor.qml — sửa file đó là đổi được bố
cục, màu, khoảng cách mà không phải động vào Python.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PyQt6.QtWidgets import QApplication

from .edit import Project, human_size
from .editor import ffprobe_info
from .srtutil import read_srt
from .player import MIX_BOTH, MIX_DUB, MIX_ORIG, VideoPlayer
from .preview_qml import PreviewItem
from .qml_models import CueModel
from .timeline_qml import TimelineItem

QML_DIR = Path(__file__).parent / "qml"


class EditorBridge(QObject):
    """Cầu nối: đọc/ghi Project từ QML."""

    changed = pyqtSignal()
    statusChanged = pyqtSignal()
    playingChanged = pyqtSignal()
    positionChanged = pyqtSignal()

    def __init__(self, video: str, workdir: Optional[str] = None):
        super().__init__()
        v = Path(video)
        self.work = Path(workdir) if workdir else v.parent / f"{v.stem}_work"
        info = ffprobe_info(video)

        self.proj = Project.load(self.work / "edit.json") or Project()
        self.proj.video = video
        self.proj.srt = str(self.work / "vi.srt")
        self.proj.dub = str(self.work / "dub.wav")
        self.proj.width = info["width"] or self.proj.width
        self.proj.height = info["height"] or self.proj.height
        self.proj.duration = info["duration"] or self.proj.duration
        self.proj.export.keep_orig_audio = False

        self.cues = read_srt(self.proj.srt) if Path(self.proj.srt).exists() else []
        self.cueModel = CueModel(self.cues)
        self.cues = self.cueModel.cues()        # dùng chung một list
        self.cueModel.edited.connect(self._on_cue_edited)
        self._status = "Sẵn sàng."
        self.timeline: Optional[TimelineItem] = None
        self.preview: Optional[PreviewItem] = None
        self._playing = False
        self._pos = 0.0

        self.player = VideoPlayer(self)
        self.player.frameReady.connect(self._on_frame)
        self.player.positionChanged.connect(self._on_pos)
        self.player.stateChanged.connect(self._on_play_state)
        self.player.failed.connect(
            lambda m: self.set_status(f"Không phát trực tiếp được: {m[:60]}"))
        self.player.open(self.proj.video, self.proj.dub)

    # ---- thuộc tính đọc từ QML

    @pyqtProperty(str, notify=changed)
    def fileName(self) -> str:
        return Path(self.proj.video).name

    @pyqtProperty(str, notify=changed)
    def meta(self) -> str:
        d = self.proj.duration
        return (f"{self.proj.width}×{self.proj.height}   ·   "
                f"{int(d // 60)}m{int(d % 60):02d}s")

    @pyqtProperty(int, notify=changed)
    def clipCount(self) -> int:
        return len(self.proj.live_clips())

    @pyqtProperty(int, notify=changed)
    def cueCount(self) -> int:
        return len(self.cues)

    @pyqtProperty(int, notify=changed)
    def regionCount(self) -> int:
        return len(self.proj.regions)

    @pyqtProperty(str, notify=changed)
    def estimate(self) -> str:
        d = self.proj.final_duration()
        dur = f"{d / 60:.0f} phút" if d >= 90 else f"{d:.0f} giây"
        return (f"~{human_size(self.proj.est_bytes())}   "
                f"{self.proj.out_height()}p · {self.proj.target_kbps()} kbps · {dur}")

    @pyqtProperty(QObject, constant=True)
    def cueList(self):
        return self.cueModel

    @pyqtProperty(int, notify=positionChanged)
    def activeCue(self) -> int:
        return self.cueModel.rowAt(self._pos)

    @pyqtProperty(bool, notify=playingChanged)
    def playing(self) -> bool:
        return self._playing

    @pyqtProperty(str, notify=positionChanged)
    def timecode(self) -> str:
        t, d = self._pos, self.proj.duration
        return (f"{int(t // 60)}:{t % 60:04.1f}  /  "
                f"{int(d // 60)}:{int(d % 60):02d}")

    @pyqtProperty(float, notify=positionChanged)
    def position(self) -> float:
        return self._pos

    @pyqtProperty(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    def set_status(self, s: str) -> None:
        self._status = s
        self.statusChanged.emit()

    # ---- lệnh gọi từ QML

    @pyqtSlot(QObject)
    def attachTimeline(self, item) -> None:
        """QML báo lên item timeline nào để nạp dữ liệu vào."""
        self.timeline = item
        tl = item.tl
        tl.clips = self.proj.live_clips()
        tl.ripple = self.proj.ripple
        tl.speeds = self.proj.speeds
        tl.regions = self.proj.regions
        tl.cues = self.cues
        tl.dub_offset = self.proj.sync_offset
        tl.set_media(self.proj.video, self.proj.dub, self.proj.duration)

        # Noi nguoc lai. Thieu doan nay thi keo clip hay sua toc do trong ban
        # QML chi doi hinh ve tren widget, con proj khong he hay biet - luc
        # luu hay xuat la mat sach, khong bao loi gi.
        tl.clipsChanged.connect(self._pull_clips)
        tl.speedsChanged.connect(self._pull_speeds)
        tl.cuesChanged.connect(self._pull_cues)
        tl.regionsChanged.connect(self._pull_regions)
        tl.committed.connect(self._pull_all)

        item.update()
        self.changed.emit()

    # ------------------------------------------------- dong bo timeline -> proj
    def _pull_clips(self) -> None:
        self.proj.clips = list(self.timeline.tl.clips)
        self.proj.ripple = self.timeline.tl.ripple
        self.changed.emit()

    def _pull_speeds(self) -> None:
        tl = self.timeline.tl
        self.proj.speeds = list(tl.speeds)
        tl.speeds = self.proj.speeds        # giu lai tham chieu dung chung
        self.changed.emit()

    def _pull_cues(self) -> None:
        self.cues = list(self.timeline.tl.cues)
        self.changed.emit()

    def _pull_regions(self) -> None:
        tl = self.timeline.tl
        self.proj.regions = list(tl.regions)
        tl.regions = self.proj.regions
        self.changed.emit()

    def _pull_all(self) -> None:
        """Chot lai moi thu sau mot thao tac hoan tat."""
        self._pull_clips()
        self._pull_speeds()
        self._pull_cues()
        self._pull_regions()
        self.proj.sync_offset = self.timeline.tl.dub_offset

    @pyqtSlot(str)
    def action(self, what: str) -> None:
        from .clips import merge_all, ripple_close, split_at
        if self.timeline is None:
            return
        tl = self.timeline.tl
        if what == "split":
            before = len(self.proj.live_clips())
            self.proj.clips = split_at(self.proj.live_clips(), tl.playhead,
                                       self.proj.ripple)
            tl.clips = self.proj.live_clips()
            self.set_status("Đã cắt." if len(self.proj.clips) > before
                            else "Đầu đọc đang ở ngay mối nối.")
        elif what == "merge":
            self.proj.clips = merge_all(self.proj.live_clips(), self.proj.ripple)
            tl.clips = self.proj.live_clips()
            self.set_status(f"Còn {len(self.proj.clips)} clip.")
        elif what == "delete":
            i = tl.sel_clip
            cl = self.proj.live_clips()
            if 0 <= i < len(cl) and len(cl) > 1:
                rest = [c for j, c in enumerate(cl) if j != i]
                self.proj.clips = (ripple_close(rest) if self.proj.ripple else rest)
                tl.clips = self.proj.live_clips()
                tl.sel_clip = -1
                self.set_status("Đã xoá clip.")
            else:
                self.set_status("Chọn một clip trên dòng thời gian đã.")
        self.timeline.update()
        self.changed.emit()

    # ---- trình phát

    def _on_frame(self, pm) -> None:
        if self.preview is not None:
            self.preview.set_frame(pm)

    def _on_pos(self, t: float) -> None:
        self._pos = t
        self.positionChanged.emit()
        if self.timeline is not None:
            self.timeline.tl.playhead = t
            self.timeline.tl.ensure_visible(t)
            self.timeline.update()

    def _on_play_state(self, playing: bool) -> None:
        self._playing = playing
        self.playingChanged.emit()

    @pyqtSlot(QObject)
    def attachPreview(self, item) -> None:
        self.preview = item
        item.pv.proj = self.proj
        item.pv.sel = -1
        item.update()
        self.player.seek(min(3.0, self.proj.duration / 3))

    @pyqtSlot()
    def togglePlay(self) -> None:
        self.player.toggle()

    @pyqtSlot(float)
    def seekBy(self, d: float) -> None:
        self.player.seek(max(0.0, min(self._pos + d, self.proj.duration)))

    @pyqtSlot(float)
    def seekTo(self, t: float) -> None:
        self.player.seek(t)

    @pyqtSlot(int)
    def setMix(self, i: int) -> None:
        self.player.set_mix([MIX_BOTH, MIX_ORIG, MIX_DUB][max(0, min(2, i))])

    @pyqtSlot(str)
    def setTool(self, kind: str) -> None:
        if self.preview is not None:
            self.preview.setTool(kind)
            self.set_status(f"Kéo một khung trên hình để đặt vùng."
                            if kind else "Chế độ chọn.")

    @pyqtSlot()
    def onRegionCommitted(self) -> None:
        if self.timeline is not None:
            self.timeline.tl.regions = self.proj.regions
            self.timeline.update()
        self.set_status(f"{len(self.proj.regions)} vùng hiệu ứng.")
        self.changed.emit()

    def _on_cue_edited(self) -> None:
        if self.timeline is not None:
            self.timeline.tl.cues = self.cues
            self.timeline.update()
        self.set_status("Đã sửa phụ đề — nhớ bấm Lưu phụ đề.")

    @pyqtSlot(int)
    def gotoCue(self, row: int) -> None:
        self.player.seek(self.cueModel.startOf(row))

    @pyqtSlot()
    def saveSubs(self) -> None:
        from .srtutil import write_srt
        if not self.cues:
            self.set_status("Chưa có phụ đề nào.")
            return
        write_srt(self.proj.srt, self.cues)
        self.set_status(f"Đã ghi {len(self.cues)} câu vào vi.srt")

    @pyqtSlot()
    def exportVideo(self) -> None:
        """Mở hộp thoại xuất — dùng lại đúng hộp thoại đã kiểm của bản Widgets,
        gồm cả thanh tiến độ và cảnh báo pin."""
        from .editor import ExportDialog
        from .export import build_command, out_path

        if self.player.playing():
            self.player.pause()
        self.save()
        out = out_path(self.proj)
        try:
            cmd = build_command(self.proj, self.cues, self.work, out)
        except Exception as e:
            self.set_status(f"Không dựng được lệnh xuất: {type(e).__name__}: {e}")
            return

        self.set_status(f"Đang xuất ra {out.name} …")
        dlg = ExportDialog(cmd, self.proj.final_duration(), out)
        dlg.exec()
        if dlg.ok:
            self.set_status(f"Đã xuất {out.name} — {human_size(out.stat().st_size)}")
        else:
            self.set_status("Đã huỷ hoặc xuất lỗi — xem chi tiết trong hộp thoại.")
        self.changed.emit()

    @pyqtSlot()
    def save(self) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        self.proj.save(self.work / "edit.json")
        self.set_status("Đã lưu dự án.")


def launch(video: str, workdir: Optional[str] = None) -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QApplication(sys.argv)
    qmlRegisterType(TimelineItem, "Wren", 1, 0, "TimelineView")
    qmlRegisterType(PreviewItem, "Wren", 1, 0, "PreviewView")

    bridge = EditorBridge(video, workdir)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("app", bridge)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "editor.qml")))
    if not engine.rootObjects():
        print("Không nạp được giao diện QML.")
        return 1
    rc = app.exec()
    bridge.player.stop()
    return rc
