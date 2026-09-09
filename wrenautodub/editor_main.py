# -*- coding: utf-8 -*-
"""Cửa sổ sửa video: rail công cụ, khung xem trước, bảng bên phải, dòng thời gian."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QProcess, QRect, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                             QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QSlider, QSpinBox, QSplitter, QStackedWidget,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from . import hwaccel
from .edit import (BLUR, DELOGO, KIND_LABEL, LOGO, History, Project,
                   build_full_graph, build_video_chain, human_size)
from .clips import (can_merge, merge_all, merge_at, remap_cues_clips,
                    ripple_close, split_at)
from .editor import ExportDialog, Preview, ffprobe_info
from .icons import icon
from .mux import escape_sub_path
from .player import MIX_BOTH, MIX_DUB, MIX_ORIG, VideoPlayer
from .srtutil import Cue, fmt_ts, parse_ts, read_srt, write_srt
from .theme import LAM_2, pha
from .timeline import L_SUB, Timeline

# Nền dòng đang phát. Dùng pha() thay vì khai màu mới — cùng nguồn với màu
# chip phụ đề nên hai chỗ luôn ăn khớp.
C_DANG_DOC = QBrush(pha(LAM_2, 0.22))
from .timing import CURVE_PRESETS, expand_preset

RES_CHOICES = [("Giữ nguyên", 0), ("1080p", 1080), ("720p", 720), ("480p", 480)]
PANELS = [("Phụ đề", "subtitle"), ("Hiệu ứng", "region"),
          ("Tốc độ", "refresh"), ("Xuất bản", "download")]

GREEN_BTN = (
    "QPushButton{background:#1f8b4c;color:#fff;font-weight:600;"
    "border:1px solid #2aa35c;border-radius:6px;padding:6px 14px;}"
    "QPushButton:hover{background:#25a259;}"
    "QPushButton:pressed{background:#187a41;}"
    "QPushButton:disabled{background:#3a3d41;color:#8a8d92;border-color:#4a4d51;}")

RAIL_BTN = (
    "QPushButton{border:none;border-radius:6px;padding:8px 2px;color:#a8adb4;}"
    "QPushButton:hover{background:#2b2e33;}"
    "QPushButton:checked{background:#333941;color:#e6eaf0;}")


class EditorWindow(QWidget):
    """Sửa phụ đề, hiệu ứng và tốc độ trên dòng thời gian, rồi xuất ra file mới."""

    def __init__(self, video: str, workdir: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("WrenAutoDub — Sửa video")
        self.setWindowIcon(icon("app", 64))
        self.setMinimumSize(1240, 760)

        v = Path(video)
        self.work = Path(workdir) if workdir else v.parent / f"{v.stem}_work"
        self.proj_path = self.work / "edit.json"

        info = ffprobe_info(video)
        self.proj = Project.load(self.proj_path) or Project()
        self.proj.video = video
        self.proj.srt = str(self.work / "vi.srt")
        self.proj.dub = str(self.work / "dub.wav")
        self.proj.width = info["width"] or self.proj.width
        self.proj.height = info["height"] or self.proj.height
        self.proj.duration = info["duration"] or self.proj.duration
        # Bản xuất chỉ ghi một track tiếng; để True thì ước tính cộng dư audio.
        self.proj.export.keep_orig_audio = False

        self.hist = History(self.proj)
        self.cues: List[Cue] = read_srt(self.proj.srt) if Path(self.proj.srt).exists() else []
        # Phụ đề GỐC do ASR nhận ra, để đối chiếu. Sản phẩm này là bản DỊCH mà
        # người dùng không có gì soi lại thì không biết câu nào dịch sai.
        _goc = self.work / "ja.srt"
        self.cues_goc: List[Cue] = read_srt(_goc) if _goc.exists() else []
        self._frame_proc: Optional[QProcess] = None
        self._frame_buf = bytearray()
        self._pending = 0.0
        self._play_timer: Optional[QTimer] = None

        self.player = VideoPlayer(self)
        self.player.frameReady.connect(self._player_frame)
        self.player.positionChanged.connect(self._player_pos)
        self.player.stateChanged.connect(self._player_state)
        self.player.failed.connect(self._player_failed)

        self._build()
        self.player.open(self.proj.video, self.proj.dub)
        self.tl.set_media(self.proj.video, self.proj.dub, self.proj.duration)
        self._sync_all()
        self._restore_layout()
        QTimer.singleShot(120, lambda: self.seek(min(3.0, self.proj.duration / 3)))

    # =============================================================== giao diện

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._top_bar())

        # Chia bằng splitter chứ không phải tỉ lệ cố định — mọi mảng đều kéo
        # giãn được bằng tay, và vị trí kéo được nhớ lại cho lần mở sau.
        self.hsplit = QSplitter(Qt.Orientation.Horizontal)
        self.hsplit.addWidget(self._center())
        self.hsplit.addWidget(self._side())
        self.hsplit.setStretchFactor(0, 3)
        self.hsplit.setStretchFactor(1, 2)
        self.hsplit.setSizes([760, 460])
        self.hsplit.setChildrenCollapsible(False)

        mid = QWidget()
        ml = QHBoxLayout(mid)
        ml.setContentsMargins(8, 6, 8, 4)
        ml.setSpacing(8)
        ml.addWidget(self._rail())
        ml.addWidget(self.hsplit, 1)

        self.tl = Timeline()
        self.tl.duration = max(0.01, self.proj.duration)
        self.tl.fps = self.proj.fps or 25.0
        self.tl.speeds = self.proj.speeds
        self.tl.regions = self.proj.regions
        self.tl.cues = self.cues
        self.tl.dub_offset = self.proj.sync_offset
        self.tl.clips = self.proj.live_clips()
        self.tl.dub_clips = self.proj.dub_clips
        self.tl.ripple = self.proj.ripple
        self.tl.seeked.connect(self._tl_seeked)
        self.tl.seekDone.connect(self._tl_seek_done)
        self.tl.speedsChanged.connect(self._speeds_live)
        self.tl.committed.connect(self._commit)
        self.tl.speedSelected.connect(self._speed_selected)
        self.tl.cueClicked.connect(self._select_cue_row)
        self.tl.cuesChanged.connect(self._cues_dragged)
        self.tl.regionsChanged.connect(self._regions_dragged)
        self.tl.selectionChanged.connect(self._tl_selection)
        self.tl.clipsChanged.connect(self._clips_dragged)
        self.tl.dubClipsChanged.connect(self._dub_clips_dragged)
        self.tl.setToolTip(
            "<b>Kéo được cả ba lớp</b>: chip phụ đề, đoạn tốc độ, thanh hiệu ứng.<br>"
            "Kéo giữa để dời, kéo hai mép để co giãn — có bắt dính vào đầu đọc "
            "và mốc của phần tử khác.<br>"
            "Bấm (không kéo) một chip phụ đề để nhảy tới câu đó.<br>"
            "Kéo chỗ trống để tua. Ctrl + lăn chuột để phóng to.<br>"
            "Kéo đường viền phía trên để dòng thời gian cao lên — ảnh khung "
            "hình và sóng âm dày theo.")

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(8, 0, 8, 6)
        bl.setSpacing(4)
        bl.addWidget(self._tool_bar())
        bl.addWidget(self.tl, 1)

        self.vsplit = QSplitter(Qt.Orientation.Vertical)
        self.vsplit.addWidget(mid)
        self.vsplit.addWidget(bottom)
        self.vsplit.setStretchFactor(0, 1)
        self.vsplit.setStretchFactor(1, 0)
        self.vsplit.setSizes([500, 290])
        self.vsplit.setChildrenCollapsible(False)
        handle = ("QSplitter::handle{background:#2c3036;}"
                  "QSplitter::handle:hover{background:#4884d6;}")
        self.vsplit.setStyleSheet(handle)
        self.hsplit.setStyleSheet(handle)
        root.addWidget(self.vsplit, 1)

        for key, fn in (("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo),
                        ("Ctrl+Shift+Z", self.redo), ("Delete", self.delete_selected),
                        ("Ctrl+S", self.save_project), ("Space", self.toggle_play),
                        ("Ctrl++", lambda: self._zoom_by(1.6)),
                        ("Ctrl+=", lambda: self._zoom_by(1.6)),
                        ("Ctrl+-", lambda: self._zoom_by(1 / 1.6)),
                        ("Ctrl+0", lambda: self._set_zoom(1.0)),
                        ("Ctrl+K", self.split_video),
                        ("Ctrl+Shift+K", self.split_sound),
                        ("Ctrl+J", self.merge_video)):
            QShortcut(QKeySequence(key), self, fn)
        self._update_buttons()

    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet("QFrame{background:#191b1f;border-bottom:1px solid #2c3036;}")
        bar.setFixedHeight(52)

        name = QLabel(f"  {Path(self.proj.video).name}")
        name.setStyleSheet("color:#e2e5ea;font-weight:600;")
        self.lb_meta = QLabel("")
        self.lb_meta.setStyleSheet("color:#8d939b;")

        self.btn_export = QPushButton(icon("download", 18), " Xuất video")
        self.btn_export.setMinimumHeight(34)
        self.btn_export.setStyleSheet(GREEN_BTN)
        self.btn_export.setToolTip(
            "Dựng file mới với toàn bộ hiệu ứng và tốc độ đã đặt.<br>"
            "Bước này mã hoá lại video nên chạy lâu — nhớ cắm sạc.")
        self.btn_export.clicked.connect(self.export)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.addWidget(name)
        lay.addWidget(self.lb_meta)
        lay.addStretch(1)
        lay.addWidget(self.btn_export)
        return bar

    def _rail(self) -> QWidget:
        w = QFrame()
        w.setFixedWidth(80)
        w.setStyleSheet("QFrame{background:#191b1f;border-radius:8px;}")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(4)

        self.rail_btns: List[QPushButton] = []
        tips = ["Sửa lời thoại và mốc thời gian",
                "Làm mờ, xoá logo, chèn logo",
                "Đổi tốc độ từng đoạn và dời khớp tiếng",
                "Độ phân giải, chất lượng, dung lượng"]
        for i, ((label, ic), tip) in enumerate(zip(PANELS, tips)):
            b = QPushButton(icon(ic, 20), " " + label)
            b.setCheckable(True)
            b.setStyleSheet(RAIL_BTN)
            b.setToolTip(tip)
            b.setMinimumHeight(46)
            b.clicked.connect(lambda _c, k=i: self.show_panel(k))
            self.rail_btns.append(b)
            lay.addWidget(b)
        lay.addStretch(1)
        self.rail_btns[0].setChecked(True)
        return w

    def _center(self) -> QWidget:
        self.preview = Preview(self.proj)
        self.preview.changed.connect(self.preview.update)
        self.preview.committed.connect(self._commit)
        self.preview.selected.connect(self._on_region_selected)

        self.tools: dict[str, QPushButton] = {}
        tips = {
            BLUR: "Kéo một khung trên hình để <b>làm mờ</b> vùng đó.<br>"
                  "Che mặt, biển số, chữ chạy.",
            DELOGO: "Kéo khung lên chỗ có logo để <b>xoá</b> — ffmpeg nội suy từ "
                    "viền.<br>Ăn nhất với logo nhỏ trên nền phẳng.",
            LOGO: "Chọn ảnh rồi kéo khung để <b>chèn logo</b>.<br>"
                  "PNG nền trong suốt cho kết quả đẹp nhất.",
        }
        left = QHBoxLayout()
        for kind in (BLUR, DELOGO, LOGO):
            b = QPushButton(icon("region"), "")
            b.setCheckable(True)
            b.setFixedWidth(36)
            b.setToolTip(f"<b>{KIND_LABEL[kind]}</b><br>{tips[kind]}")
            b.clicked.connect(lambda _c, k=kind: self.set_tool(k))
            self.tools[kind] = b
            left.addWidget(b)
        self.btn_del = QPushButton(icon("trash"), "")
        self.btn_del.setFixedWidth(36)
        self.btn_del.setToolTip("Xoá vùng, đoạn tốc độ hoặc clip đang chọn — <b>Delete</b>")
        self.btn_del.clicked.connect(self.delete_selected)
        left.addWidget(self.btn_del)

        left.addSpacing(10)
        self.btn_split = QPushButton(icon("scissors"), "")
        self.btn_split.setToolTip(
            "<b>Cắt hình</b> tại đầu đọc — <b>Ctrl+K</b><br>"
            "Tách clip đang nằm dưới đầu đọc thành hai. Cắt xong chọn một nửa "
            "rồi Delete là bỏ được đoạn đó.")
        self.btn_split.clicked.connect(self.split_video)

        self.btn_split_snd = QPushButton(icon("split_snd"), "")
        self.btn_split_snd.setToolTip(
            "<b>Cắt tiếng</b> tại đầu đọc — <b>Ctrl+Shift+K</b><br>"
            "Chỉ cắt track thuyết minh, không đụng tới hình. Dùng khi muốn bỏ "
            "một đoạn lời đọc mà vẫn giữ nguyên hình ảnh.")
        self.btn_split_snd.clicked.connect(self.split_sound)

        self.btn_merge = QPushButton(icon("merge"), "")
        self.btn_merge.setToolTip(
            "<b>Ghép clip</b> đang chọn với clip kế — <b>Ctrl+J</b><br>"
            "Chỉ ghép được khi hai clip vốn liền nhau trong file gốc.<br>"
            "Giữ Shift khi bấm để gộp hết mọi cặp liền nhau.")
        self.btn_merge.clicked.connect(self.merge_video)

        self.btn_magnet = QPushButton(icon("magnet"), "")
        self.btn_magnet.setCheckable(True)
        self.btn_magnet.setChecked(True)
        self.btn_magnet.setToolTip(
            "<b>Hít clip lại</b> (đang bật)<br>"
            "Bật: clip luôn xếp sát nhau, xoá một clip thì các clip sau dồn lên, "
            "phim không có chỗ hở.<br>"
            "Tắt: clip nằm rời rạc đúng chỗ bạn đặt, khoảng hở thành màn đen "
            "và im lặng.")
        self.btn_magnet.toggled.connect(self.toggle_ripple)

        for b in (self.btn_split, self.btn_split_snd, self.btn_merge, self.btn_magnet):
            b.setFixedWidth(36)
            left.addWidget(b)

        self.btn_back = QPushButton(icon("undo"), "")
        self.btn_play = QPushButton(icon("play", 20), "")
        self.btn_fwd = QPushButton(icon("redo"), "")
        for b, tip, w in ((self.btn_back, "Lùi 5 giây", 36),
                          (self.btn_play, "Chạy / dừng xem trước — <b>Space</b>", 46),
                          (self.btn_fwd, "Tiến 5 giây", 36)):
            b.setToolTip(tip)
            b.setFixedWidth(w)
        self.btn_back.clicked.connect(lambda: self.seek(self.tl.playhead - 5))
        self.btn_fwd.clicked.connect(lambda: self.seek(self.tl.playhead + 5))
        self.btn_play.clicked.connect(self.toggle_play)

        self.lb_time = QLabel("0:00.0")
        self.lb_time.setFont(QFont("Consolas", 10))
        self.lb_time.setStyleSheet("color:#e2e5ea;")
        self.lb_time.setToolTip("Vị trí đầu đọc hiện tại")
        self.lb_dur = QLabel("")
        self.lb_dur.setStyleSheet("color:#8d939b;")
        self.lb_dur.setToolTip("Tổng thời lượng bản gốc")

        self.btn_undo = QPushButton(icon("undo"), "")
        self.btn_undo.setToolTip("Hoàn tác — <b>Ctrl+Z</b>")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = QPushButton(icon("redo"), "")
        self.btn_redo.setToolTip("Làm lại — <b>Ctrl+Y</b>")
        self.btn_redo.clicked.connect(self.redo)
        for b in (self.btn_undo, self.btn_redo):
            b.setFixedWidth(36)

        self.btn_zin = QPushButton(icon("zoom_in"), "")
        self.btn_zout = QPushButton(icon("zoom_out"), "")
        self.btn_zfit = QPushButton(icon("fit"), "")
        for b, tip in ((self.btn_zout, "Thu nhỏ dòng thời gian — <b>Ctrl+-</b>"),
                       (self.btn_zin, "Phóng to dòng thời gian — <b>Ctrl++</b><br>"
                                      "Phóng to thì kéo mốc chính xác hơn nhiều."),
                       (self.btn_zfit, "Xem vừa khít cả phim — <b>Ctrl+0</b>")):
            b.setFixedWidth(32)
            b.setToolTip(tip)
        self.btn_zin.clicked.connect(lambda: self._zoom_by(1.6))
        self.btn_zout.clicked.connect(lambda: self._zoom_by(1 / 1.6))
        self.btn_zfit.clicked.connect(lambda: self._set_zoom(1.0))

        self.sl_zoom = QSlider(Qt.Orientation.Horizontal)
        self.sl_zoom.setRange(10, 2000)
        self.sl_zoom.setValue(10)
        self.sl_zoom.setFixedWidth(120)
        self.sl_zoom.setToolTip("Phóng to dòng thời gian.<br>"
                                "Hoặc giữ Ctrl và lăn chuột ngay trên dòng thời gian.")
        self.sl_zoom.valueChanged.connect(self._zoom_slider)

        self.cb_mix = QComboBox()
        self.cb_mix.addItems(["Nghe cả hai", "Chỉ tiếng gốc", "Chỉ thuyết minh"])
        self.cb_mix.setFixedWidth(132)
        self.cb_mix.setToolTip(
            "Chọn nghe gì khi phát.<br>"
            "<b>Cả hai</b> hạ tiếng gốc xuống để nghe rõ giọng đọc — giống bản "
            "sẽ xuất ra.<br><b>Chỉ thuyết minh</b> để soát lời đọc có khớp miệng.")
        self.cb_mix.currentIndexChanged.connect(
            lambda i: self.player.set_mix([MIX_BOTH, MIX_ORIG, MIX_DUB][i]))

        self.ck_fx = QCheckBox("Xem kèm hiệu ứng")
        self.ck_fx.setToolTip(
            "Trích khung đã chạy qua toàn bộ filter — chậm hơn chút nhưng "
            "thấy đúng kết quả sẽ xuất ra.<br>"
            "Chỉ áp dụng khi <b>đang dừng</b> — lúc phát thì hiện khung gốc, "
            "vì lọc từng khung theo thời gian thực thì không kịp.")
        self.ck_fx.toggled.connect(lambda: self.seek(self.tl.playhead))

        # Nhóm nút sửa (left) chuyển xuống sát dòng thời gian — xem _tool_bar().
        # Để lại đây thì bề rộng tối thiểu của khung xem lên tới 1166px và
        # splitter bị ghim cứng, kéo không nhúc nhích.
        self._edit_tools = left

        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(self.btn_back)
        bar.addWidget(self.btn_play)
        bar.addWidget(self.btn_fwd)
        bar.addSpacing(8)
        bar.addWidget(self.lb_time)
        bar.addWidget(self.lb_dur)
        bar.addStretch(1)
        bar.addWidget(self.cb_mix)
        bar.addWidget(self.ck_fx)

        w = QWidget()
        w.setMinimumWidth(360)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.preview, 1)
        lay.addLayout(bar)
        return w

    def _tool_bar(self) -> QWidget:
        """Nút sửa nằm ngay trên dòng thời gian, cạnh thứ nó thao tác lên."""
        w = QFrame()
        w.setStyleSheet("QFrame{background:#191b1f;border-radius:6px;}")
        w.setFixedHeight(42)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(4)
        lay.addLayout(self._edit_tools)
        lay.addStretch(1)
        lay.addWidget(self.btn_undo)
        lay.addWidget(self.btn_redo)
        lay.addSpacing(8)
        lay.addWidget(self.btn_zout)
        lay.addWidget(self.sl_zoom)
        lay.addWidget(self.btn_zin)
        lay.addWidget(self.btn_zfit)
        return w

    # ------------------------------------------------------------ bảng phải

    def _side(self) -> QWidget:
        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(240)
        self.stack.addWidget(self._panel_subs())
        self.stack.addWidget(self._panel_fx())
        self.stack.addWidget(self._panel_speed())
        self.stack.addWidget(self._panel_export())
        return self.stack

    def _panel_subs(self) -> QWidget:
        co_goc = bool(self.cues_goc)
        self.tbl = QTableWidget(0, 4 if co_goc else 3)
        self.tbl.setHorizontalHeaderLabels(
            ["Bắt đầu", "Kết thúc", "Lời gốc", "Lời thoại"] if co_goc
            else ["Bắt đầu", "Kết thúc", "Lời thoại"])
        hh = self.tbl.horizontalHeader()
        if co_goc:
            hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        else:
            hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl.setColumnWidth(0, 94)
        self.tbl.setColumnWidth(1, 94)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                 | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.tbl.itemChanged.connect(self._cue_edited)
        self.tbl.itemSelectionChanged.connect(self._cue_selected)
        self.tbl.setToolTip("Sửa thẳng lời thoại hoặc mốc thời gian.<br>"
                            "Chọn dòng nào thì khung xem và dòng thời gian nhảy tới đó.<br>"
                            "Khi tua, câu đang phát tự sáng lên ở đây.")

        btn = QPushButton(icon("subtitle"), " Lưu phụ đề")
        btn.setToolTip("Ghi đè <b>vi.srt</b>.<br>Sửa lời thoại xong thì chạy lại "
                       "bước Thuyết minh cho giọng đọc khớp.")
        btn.clicked.connect(self.save_srt)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self.tbl, 1)
        lay.addWidget(btn)
        return w

    def _panel_fx(self) -> QWidget:
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._list_selected)
        self.lst.setToolTip("Các vùng đã đặt. Vùng tắt hiện chữ xám.")

        self.sp_start = QDoubleSpinBox()
        self.sp_end = QDoubleSpinBox()
        for sp in (self.sp_start, self.sp_end):
            sp.setRange(0, max(1.0, self.proj.duration))
            sp.setSuffix(" s")
            sp.setDecimals(1)
            sp.valueChanged.connect(self._prop_changed)
        self.sp_start.setToolTip("Hiệu ứng bắt đầu có tác dụng từ giây này")
        self.sp_end.setToolTip("Kết thúc ở giây này.<br>Cả hai bằng 0 = suốt phim.")

        self.sp_strength = QSpinBox()
        self.sp_strength.setRange(1, 60)
        self.sp_strength.setToolTip("Độ mờ (sigma Gaussian). Càng lớn càng nhoè.")
        self.sp_strength.valueChanged.connect(self._prop_changed)

        self.sp_opacity = QDoubleSpinBox()
        self.sp_opacity.setRange(0.05, 1.0)
        self.sp_opacity.setSingleStep(0.05)
        self.sp_opacity.setToolTip("Độ đục logo — 1.0 là đục hoàn toàn")
        self.sp_opacity.valueChanged.connect(self._prop_changed)

        self.btn_logo = QPushButton(icon("folder"), " Chọn ảnh logo…")
        self.btn_logo.setToolTip("Ảnh dùng cho vùng logo đang chọn.<br>"
                                 "File JPG không có nền trong, sẽ đè thành khối đặc.")
        self.btn_logo.clicked.connect(self.pick_logo)

        self.ck_on = QCheckBox("Bật vùng này")
        self.ck_on.setChecked(True)
        self.ck_on.setToolTip("Tắt tạm để so sánh, khỏi phải xoá")
        self.ck_on.toggled.connect(self._prop_changed)

        box = QGroupBox("Thuộc tính vùng")
        f = QFormLayout(box)
        f.addRow("Từ giây:", self.sp_start)
        f.addRow("Đến giây:", self.sp_end)
        f.addRow("Độ mờ:", self.sp_strength)
        f.addRow("Độ đục logo:", self.sp_opacity)
        f.addRow(self.btn_logo)
        f.addRow(self.ck_on)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self.lst, 1)
        lay.addWidget(box)
        return w

    def _panel_speed(self) -> QWidget:
        self.ck_speed_tool = QCheckBox("Bật vẽ đoạn tốc độ")
        self.ck_speed_tool.setToolTip(
            "Bật rồi kéo trên lớp <b>Tốc độ</b> của dòng thời gian để tạo đoạn.<br>"
            "Kéo mép để co giãn, kéo giữa để dời, Delete để xoá.")
        self.ck_speed_tool.toggled.connect(
            lambda on: setattr(self.tl, "tool_speed", on))

        self.sp_factor = QDoubleSpinBox()
        self.sp_factor.setRange(0.1, 8.0)
        self.sp_factor.setSingleStep(0.25)
        self.sp_factor.setValue(2.0)
        self.sp_factor.setSuffix(" ×")
        self.sp_factor.setToolTip(
            "Trên 1 là tua nhanh, dưới 1 là quay chậm.<br>"
            "Giọng thuyết minh và phụ đề dồn theo nên vẫn khớp hình.<br>"
            "Chọn sẵn hệ số này rồi mới vẽ đoạn mới.")
        self.sp_factor.valueChanged.connect(self._factor_changed)

        self.cb_preset = QComboBox()
        self.cb_preset.addItems(list(CURVE_PRESETS))
        self.cb_preset.setToolTip(
            "Chia đoạn đang chọn thành nhiều đoạn nhỏ tốc độ khác nhau.<br>"
            "Là xấp xỉ bậc thang chứ không phải đường cong mượt — đổi lại "
            "không cần nội suy khung hình nên nhanh hơn hàng chục lần.")
        btn_preset = QPushButton("Áp dụng lên đoạn đang chọn")
        btn_preset.setToolTip("Chọn một đoạn trên dòng thời gian trước đã")
        btn_preset.clicked.connect(self.apply_preset)

        self.lst_speed = QListWidget()
        self.lst_speed.currentRowChanged.connect(self._speed_row)
        self.lst_speed.setToolTip("Các đoạn đã đặt tốc độ")

        self.sp_sync = QDoubleSpinBox()
        self.sp_sync.setRange(-30.0, 30.0)
        self.sp_sync.setSingleStep(0.1)
        self.sp_sync.setDecimals(2)
        self.sp_sync.setSuffix(" s")
        self.sp_sync.setToolTip(
            "Dời cả phụ đề lẫn giọng thuyết minh so với hình.<br>"
            "Dương = đọc muộn hơn, âm = đọc sớm hơn.<br>"
            "Dùng khi tiếng lệch đều so với miệng nhân vật.")
        self.sp_sync.valueChanged.connect(self._sync_changed)

        self.lb_newdur = QLabel("")
        self.lb_newdur.setWordWrap(True)
        self.lb_newdur.setStyleSheet("color:#8d939b;")
        self.lb_newdur.setToolTip("Thời lượng sau khi áp dụng toàn bộ đoạn tốc độ")

        box = QGroupBox("Dời khớp tiếng")
        f = QFormLayout(box)
        f.addRow("Lệch:", self.sp_sync)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self.ck_speed_tool)
        lay.addWidget(QLabel("Hệ số cho đoạn mới:"))
        lay.addWidget(self.sp_factor)
        lay.addWidget(QLabel("Preset đường cong:"))
        lay.addWidget(self.cb_preset)
        lay.addWidget(btn_preset)
        lay.addWidget(self.lst_speed, 1)
        lay.addWidget(self.lb_newdur)
        lay.addWidget(box)
        return w

    def _panel_export(self) -> QWidget:
        self.cb_res = QComboBox()
        self.cb_res.addItems([lbl for lbl, _ in RES_CHOICES])
        self.cb_res.setToolTip("Độ phân giải file ra.<br>Hạ xuống thì nhẹ và nhanh "
                               "hơn nhiều, đổi lại mất chi tiết.<br>"
                               "Đừng nâng cao hơn bản gốc, chỉ tốn dung lượng.")
        self.cb_res.currentIndexChanged.connect(self._export_changed)

        self.cb_q = QComboBox()
        self.cb_q.addItems(["cao", "vừa", "nhẹ"])
        self.cb_q.setCurrentText("vừa")
        self.cb_q.setToolTip("Quyết định bitrate mục tiêu, và do đó dung lượng")
        self.cb_q.currentTextChanged.connect(self._export_changed)

        self.ck_hardsub = QCheckBox("Nung phụ đề lên hình")
        self.ck_hardsub.setToolTip("Máy nào cũng thấy, nhưng không tắt được.<br>"
                                   "Mốc phụ đề tự ánh xạ theo các đoạn đổi tốc độ.")
        self.ck_hardsub.toggled.connect(self._export_changed)

        self.lb_est = QLabel("")
        self.lb_est.setWordWrap(True)
        self.lb_est.setStyleSheet(
            "background:#20242a;border:1px solid #333941;border-radius:6px;"
            "padding:10px;color:#cdd3da;")
        self.lb_est.setToolTip(
            "Ước tính = bitrate mục tiêu × thời lượng sau khi đổi tốc độ.<br>"
            "Lúc xuất có ép bitrate nên với phim thật số này khá sát.<br>"
            "Cảnh tĩnh thì VBR dùng ít hơn mức đặt, file ra "
            "<b>nhẹ hơn ước tính</b> — bình thường.")

        box = QGroupBox("Thiết lập xuất")
        f = QFormLayout(box)
        f.addRow("Độ phân giải:", self.cb_res)
        f.addRow("Chất lượng:", self.cb_q)
        f.addRow(self.ck_hardsub)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(box)
        lay.addWidget(self.lb_est)
        lay.addStretch(1)
        return w

    def show_panel(self, i: int) -> None:
        for j, b in enumerate(self.rail_btns):
            b.setChecked(j == i)
        self.stack.setCurrentIndex(i)

    # ============================================================ xem trước

    # ------------------------------------------------------------------ zoom

    def _zoom_slider(self, v: int) -> None:
        self.tl.set_zoom(v / 10)

    def _set_zoom(self, z: float) -> None:
        z = max(1.0, min(200.0, z))
        self.sl_zoom.blockSignals(True)
        self.sl_zoom.setValue(int(z * 10))
        self.sl_zoom.blockSignals(False)
        self.tl.set_zoom(z)

    def _zoom_by(self, k: float) -> None:
        self._set_zoom(self.tl.zoom * k)

    # ============================================================== cắt / ghép

    def _commit_clips(self) -> None:
        self.tl.clips = self.proj.live_clips()
        self.tl.dub_clips = self.proj.dub_clips
        self.tl.ripple = self.proj.ripple
        self._commit()

    def split_video(self) -> None:
        t = self.tl.playhead
        before = len(self.proj.live_clips())
        self.proj.clips = split_at(self.proj.live_clips(), t, self.proj.ripple)
        if self.proj.dub_clips:     # tiếng đã tách riêng thì cắt luôn cho khớp
            self.proj.dub_clips = split_at(self.proj.dub_clips, t, self.proj.ripple)
        if len(self.proj.clips) == before:
            self.lb_meta.setText("   đầu đọc đang ở ngay mối nối, không cắt được")
            return
        self.tl.sel_clip = self.tl.clip_at(t)
        self._commit_clips()

    def split_sound(self) -> None:
        base = self.proj.dub_clips or self.proj.live_clips()
        after = split_at(base, self.tl.playhead, self.proj.ripple)
        if len(after) == len(base):
            self.lb_meta.setText("   đầu đọc đang ở ngay mối nối tiếng")
            return
        self.proj.dub_clips = after
        self._commit_clips()

    def merge_video(self) -> None:
        from PyQt6.QtWidgets import QApplication
        cl = self.proj.live_clips()
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.proj.clips = merge_all(cl, self.proj.ripple)
            self.tl.sel_clip = -1
            self._commit_clips()
            return
        i = self.tl.sel_clip if self.tl.sel_clip >= 0 else self.tl.clip_at(self.tl.playhead)
        if i < 0 or not can_merge(cl, i, self.proj.ripple):
            self.lb_meta.setText("   hai clip này không liền nhau trong file gốc")
            return
        self.proj.clips = merge_at(cl, i, self.proj.ripple)
        self._commit_clips()

    def toggle_ripple(self, on: bool) -> None:
        self.proj.ripple = on
        if on:
            self.proj.clips = ripple_close(self.proj.live_clips())
        self.btn_magnet.setToolTip(
            self.btn_magnet.toolTip().replace(
                "(đang bật)" if not on else "(đang tắt)",
                "(đang tắt)" if not on else "(đang bật)"))
        self._commit_clips()

    def delete_clip(self) -> bool:
        i = self.tl.sel_clip
        cl = self.proj.live_clips()
        if not (0 <= i < len(cl)) or len(cl) < 2:
            return False
        rest = [c for j, c in enumerate(cl) if j != i]
        self.proj.clips = ripple_close(rest) if self.proj.ripple else rest
        self.tl.sel_clip = -1
        self._commit_clips()
        return True

    def toggle_play(self) -> None:
        if self.player.usable():
            self.player.toggle()
            return
        self._toggle_fallback()

    def _toggle_fallback(self) -> None:
        """Chế độ dự phòng khi trình phát không đọc nổi định dạng: nhảy khung.

        Giật, nhưng còn hơn không xem được gì. Chỉ dùng khi QMediaPlayer báo lỗi.
        """
        if self._play_timer and self._play_timer.isActive():
            self._play_timer.stop()
            self.btn_play.setIcon(icon("play", 20))
            return
        if self._play_timer is None:
            self._play_timer = QTimer(self)
            self._play_timer.timeout.connect(self._advance)
        self._play_timer.start(500)
        self.btn_play.setIcon(icon("stop", 20))

    def _advance(self) -> None:
        t = self.tl.playhead + 0.5
        if t >= self.proj.duration:
            self._toggle_fallback()
            return
        self.seek(t)

    # ---- tín hiệu từ trình phát

    def _player_frame(self, pm: QImage) -> None:
        self.preview.frame = pm
        self.preview.update()

    def _player_pos(self, t: float) -> None:
        self.tl.update_playhead(t)
        self.lb_time.setText(f"{int(t // 60)}:{t % 60:04.1f}")
        self._highlight_cue(t)

    def _player_state(self, playing: bool) -> None:
        self.btn_play.setIcon(icon("stop" if playing else "play", 20))
        if not playing and self.ck_fx.isChecked():
            self._grab_frame(self.tl.playhead)

    def _player_failed(self, msg: str) -> None:
        self.lb_meta.setText(
            f"   ⚠ không phát trực tiếp được — dùng chế độ tua khung")
        self.lb_meta.setToolTip(
            f"QMediaPlayer từ chối file này: {msg}<br>"
            "Thường do container hoặc codec Windows không có sẵn bộ giải mã.<br>"
            "Vẫn tua và sửa bình thường được, chỉ là không phát liền mạch.")
        self.cb_mix.setEnabled(False)

    # ---- tua

    def _tl_seeked(self, t: float) -> None:
        self.seek(t, from_timeline=True)

    def _tl_seek_done(self, t: float) -> None:
        """Thả tay sau khi kéo đầu đọc: tua ngay, không qua bộ gộp lệnh."""
        if self.player.usable():
            self.player.seek(max(0.0, min(t, self.proj.duration)), ngay=True)

    def seek(self, t: float, from_timeline: bool = False) -> None:
        t = max(0.0, min(t, self.proj.duration))
        self.tl.playhead = t
        if not from_timeline:
            self.tl.ensure_visible(t)
            self.tl.update()
        self.lb_time.setText(f"{int(t // 60)}:{t % 60:04.1f}")
        self._highlight_cue(t)

        if self.player.usable():
            self.player.seek(t)
            # Khung hình do trình phát đẩy ra; chỉ gọi ffmpeg khi đang dừng và
            # cần xem kèm hiệu ứng, vì lọc theo thời gian thực thì không kịp.
            if self.player.playing() or not self.ck_fx.isChecked():
                return
        self._pending = t
        QTimer.singleShot(160, self._seek_pending)

    def _seek_pending(self) -> None:
        if abs(self._pending - self.tl.playhead) < 0.001:
            self._grab_frame(self._pending)

    def _grab_frame(self, t: float) -> None:
        if self._frame_proc and self._frame_proc.state() != QProcess.ProcessState.NotRunning:
            self._frame_proc.kill()
        args = ["-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", self.proj.video]
        if self.ck_fx.isChecked() and self.proj.regions:
            chain, extra, out = build_video_chain(
                self.proj, self.proj.width or 1920, self.proj.height or 1080,
                logo_base=1, do_scale=False)
            for e in extra:
                args += ["-i", e]
            if chain:
                args += ["-filter_complex", chain, "-map", f"[{out}]"]
        args += ["-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"]

        self._frame_buf = bytearray()
        p = QProcess(self)
        p.readyReadStandardOutput.connect(
            lambda: self._frame_buf.extend(bytes(p.readAllStandardOutput())))
        p.finished.connect(self._frame_done)
        self._frame_proc = p
        p.start("ffmpeg", args)

    def _frame_done(self, *_a) -> None:
        pm = QImage()
        if self._frame_buf and pm.loadFromData(bytes(self._frame_buf), "PNG"):
            self.preview.frame = pm
            self.preview.update()

    def _highlight_cue(self, t: float) -> None:
        """Làm nổi câu đang phát — KHÔNG đụng vào lựa chọn, KHÔNG cuộn ép.

        Bản cũ gọi selectRow() mỗi lần đổi câu. selectRow vừa đổi lựa chọn vừa
        TỰ CUỘN bảng, nên đang xem là bảng nhảy liên tục; mà ở đoạn phim không
        có phụ đề thì nó bỏ mặc dòng cũ đang sáng, vào câu mới là giật một cái.
        Giờ tô nền dòng thay vì đổi lựa chọn — lựa chọn để dành cho thao tác
        của người dùng — và chỉ cuộn khi dòng đã trôi khỏi tầm nhìn.
        """
        cur = -1
        for i, c in enumerate(self.cues):
            if c.start <= t <= c.end:
                cur = i
                break
        if cur == self.tl.cur_cue:
            return
        truoc, self.tl.cur_cue = self.tl.cur_cue, cur

        # Chỉ vẽ lại lớp phụ đề, không phải cả thanh thời gian
        self.tl.update(QRect(0, self.tl.lane_y(L_SUB),
                             self.tl.width(), self.tl.lane_h(L_SUB)))

        self.tbl.blockSignals(True)
        for hang, on in ((truoc, False), (cur, True)):
            if not (0 <= hang < self.tbl.rowCount()):
                continue
            for col in range(self.tbl.columnCount()):
                it = self.tbl.item(hang, col)
                if it is not None:
                    it.setBackground(C_DANG_DOC if on else QBrush())
        self.tbl.blockSignals(False)

        if cur >= 0:
            o = self.tbl.visualItemRect(self.tbl.item(cur, 0))
            if not self.tbl.viewport().rect().contains(o.center()):
                self.tbl.scrollToItem(self.tbl.item(cur, 0),
                                      QAbstractItemView.ScrollHint.EnsureVisible)

    # ============================================================ vùng hiệu ứng

    def set_tool(self, kind: str) -> None:
        on = self.tools[kind].isChecked()
        for k, b in self.tools.items():
            b.setChecked(k == kind and on)
        self.preview.tool = kind if on else ""
        if on and kind == LOGO and not getattr(self.preview, "logo_path", ""):
            self.pick_logo()

    def pick_logo(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh logo", "",
                                           "Ảnh (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not f:
            return
        self.preview.logo_path = f
        i = self.preview.sel
        if 0 <= i < len(self.proj.regions) and self.proj.regions[i].kind == LOGO:
            self.proj.regions[i].path = f
            self._commit()

    def delete_selected(self) -> None:
        if self.delete_clip():
            return
        if self.tl.delete_selected():
            self._sync_regions()
            self._sync_speed_list()
            self._update_estimate()
            self._update_buttons()
            return
        i = self.preview.sel
        if 0 <= i < len(self.proj.regions):
            self.proj.regions.pop(i)
            self.preview.sel = -1
            self._commit()

    def _on_region_selected(self, i: int) -> None:
        self.lst.blockSignals(True)
        self.lst.setCurrentRow(i)
        self.lst.blockSignals(False)
        self._load_props(i)
        self._update_buttons()

    def _list_selected(self, i: int) -> None:
        self.preview.sel = i
        self.preview.update()
        self._load_props(i)
        self._update_buttons()

    def _load_props(self, i: int) -> None:
        ok = 0 <= i < len(self.proj.regions)
        widgets = (self.sp_start, self.sp_end, self.sp_strength,
                   self.sp_opacity, self.ck_on, self.btn_logo)
        for w in widgets:
            w.setEnabled(ok)
        if not ok:
            return
        r = self.proj.regions[i]
        for w in widgets[:5]:
            w.blockSignals(True)
        self.sp_start.setValue(r.start)
        self.sp_end.setValue(r.end)
        self.sp_strength.setValue(r.strength)
        self.sp_opacity.setValue(r.opacity)
        self.ck_on.setChecked(r.enabled)
        for w in widgets[:5]:
            w.blockSignals(False)
        self.sp_strength.setEnabled(r.kind == BLUR)
        self.sp_opacity.setEnabled(r.kind == LOGO)
        self.btn_logo.setEnabled(r.kind == LOGO)

    def _prop_changed(self) -> None:
        i = self.preview.sel
        if not (0 <= i < len(self.proj.regions)):
            return
        r = self.proj.regions[i]
        r.start, r.end = self.sp_start.value(), self.sp_end.value()
        r.strength = self.sp_strength.value()
        r.opacity = self.sp_opacity.value()
        r.enabled = self.ck_on.isChecked()
        self._commit()

    # ================================================================= tốc độ

    def _speeds_live(self) -> None:
        self.proj.speeds = self.tl.speeds
        self._sync_speed_list()
        self._update_estimate()

    def _speed_selected(self, i: int) -> None:
        self.lst_speed.blockSignals(True)
        self.lst_speed.setCurrentRow(i)
        self.lst_speed.blockSignals(False)
        if 0 <= i < len(self.proj.speeds):
            self.sp_factor.blockSignals(True)
            self.sp_factor.setValue(self.proj.speeds[i].factor)
            self.sp_factor.blockSignals(False)
        self._update_buttons()

    def _speed_row(self, i: int) -> None:
        self.tl.sel = i
        self.tl.update()
        if 0 <= i < len(self.proj.speeds):
            self.sp_factor.blockSignals(True)
            self.sp_factor.setValue(self.proj.speeds[i].factor)
            self.sp_factor.blockSignals(False)
        self._update_buttons()

    def _factor_changed(self, v: float) -> None:
        self.tl.new_factor = v
        i = self.tl.sel
        if 0 <= i < len(self.proj.speeds):
            self.proj.speeds[i].factor = v
            self._commit()

    def apply_preset(self) -> None:
        i = self.tl.sel
        if not (0 <= i < len(self.proj.speeds)):
            QMessageBox.information(self, "Chưa chọn đoạn",
                                    "Chọn một đoạn tốc độ trên dòng thời gian đã.")
            return
        s = self.proj.speeds.pop(i)
        self.proj.speeds.extend(expand_preset(s.start, s.end,
                                              self.cb_preset.currentText()))
        self.tl.speeds = self.proj.speeds
        self.tl.sel = -1
        self._commit()

    def _sync_changed(self, v: float) -> None:
        self.proj.sync_offset = v
        self.tl.dub_offset = v
        self.player.set_dub_offset(v)
        self.tl.update()
        self._commit()

    def _sync_speed_list(self) -> None:
        self.lst_speed.blockSignals(True)
        self.lst_speed.clear()
        for i, s in enumerate(self.proj.speeds):
            self.lst_speed.addItem(QListWidgetItem(f"{i + 1}. {s.label}"))
        self.lst_speed.setCurrentRow(self.tl.sel)
        self.lst_speed.blockSignals(False)
        d = self.proj.final_duration()
        g = self.proj.duration
        self.lb_newdur.setText(
            f"Thời lượng sau khi đổi tốc độ: {int(d // 60)}:{d % 60:04.1f}"
            f"  (gốc {int(g // 60)}:{g % 60:04.1f})")

    # ================================================================ phụ đề

    def _goc_cua(self, c: Cue) -> str:
        """Câu gốc trùng khung thời gian với câu đã dịch.

        Khớp theo ĐỘ CHỒNG thời gian chứ không theo chỉ số: người dùng có thể
        đã tách hay gộp câu tiếng Việt, lúc đó chỉ số lệch hết.
        """
        tot, txt = 0.0, ""
        for g in self.cues_goc:
            ov = min(c.end, g.end) - max(c.start, g.start)
            if ov > tot:
                tot, txt = ov, g.text
        return txt

    def _sync_cues(self) -> None:
        self.tbl.blockSignals(True)
        self.tbl.setRowCount(len(self.cues))
        co_goc = bool(self.cues_goc)
        for i, c in enumerate(self.cues):
            o = [(0, fmt_ts(c.start)), (1, fmt_ts(c.end))]
            if co_goc:
                o += [(2, self._goc_cua(c)), (3, c.text)]
            else:
                o += [(2, c.text)]
            for col, val in o:
                it = QTableWidgetItem(val)
                if co_goc and col == 2:     # cột gốc chỉ để đối chiếu
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    it.setForeground(QColor(150, 154, 160))
                self.tbl.setItem(i, col, it)
        self.tbl.blockSignals(False)
        self.tl.cues = self.cues

    def _cues_dragged(self) -> None:
        """Chip phụ đề vừa bị kéo — cập nhật bảng, đừng đụng vào lời thoại."""
        self.tbl.blockSignals(True)
        for i, c in enumerate(self.cues):
            if i < self.tbl.rowCount():
                self.tbl.item(i, 0).setText(fmt_ts(c.start))
                self.tbl.item(i, 1).setText(fmt_ts(c.end))
        self.tbl.blockSignals(False)

    def _regions_dragged(self) -> None:
        i = self.preview.sel
        self._sync_regions()
        self.preview.sel = i
        self._load_props(i)

    def _clips_dragged(self) -> None:
        """Kéo hoặc trim clip trên dòng thời gian."""
        self.proj.clips = list(self.tl.clips)
        self._update_estimate()

    def _dub_clips_dragged(self) -> None:
        """Kéo hoặc trim clip trên lớp thuyết minh — nhát cắt riêng của tiếng."""
        self.proj.dub_clips = list(self.tl.dub_clips)
        self._update_estimate()

    def _tl_selection(self, lane: int, idx: int) -> None:
        """Chọn trên dòng thời gian thì mở đúng bảng bên phải."""
        from .timeline import L_FX, L_SPEED, L_SUB, L_VIDEO
        if lane != L_VIDEO:
            self.tl.sel_clip = -1
        if lane == L_VIDEO:
            self.lb_meta.setText(
                f"   clip {idx + 1}/{len(self.proj.live_clips())} đang chọn")
        elif lane == L_SUB:
            self.show_panel(0)
            self.tbl.blockSignals(True)
            self.tbl.selectRow(idx)
            self.tbl.blockSignals(False)
        elif lane == L_FX:
            self.show_panel(1)
            self.preview.sel = idx
            self.preview.update()
            self.lst.blockSignals(True)
            self.lst.setCurrentRow(idx)
            self.lst.blockSignals(False)
            self._load_props(idx)
        elif lane == L_SPEED:
            self.show_panel(2)
            self._speed_selected(idx)
        self._update_buttons()

    def _select_cue_row(self, i: int) -> None:
        self.show_panel(0)
        self.tbl.selectRow(i)

    def _cue_selected(self) -> None:
        rows = self.tbl.selectionModel().selectedRows()
        if rows:
            self.seek(self.cues[rows[0].row()].start)

    def _cue_edited(self, item: QTableWidgetItem) -> None:
        r, c = item.row(), item.column()
        if not (0 <= r < len(self.cues)):
            return
        cue = self.cues[r]
        try:
            cot_text = 3 if self.cues_goc else 2
            if c == 0:
                cue.start = parse_ts(item.text())
            elif c == 1:
                cue.end = parse_ts(item.text())
            elif c == cot_text:
                cue.text = item.text()
            else:
                return                      # cột gốc, không sửa được
        except Exception:
            # gõ sai định dạng thì trả về giá trị cũ, đừng làm hỏng cue
            self.tbl.blockSignals(True)
            item.setText(fmt_ts(cue.start if c == 0 else cue.end))
            self.tbl.blockSignals(False)
        self.tl.update()

    def save_srt(self) -> None:
        if not self.cues:
            QMessageBox.warning(self, "Chưa có phụ đề",
                                f"Không tìm thấy câu nào trong:\n{self.proj.srt}")
            return
        write_srt(self.proj.srt, self.cues)
        QMessageBox.information(
            self, "Đã lưu",
            f"Ghi {len(self.cues)} câu vào:\n{self.proj.srt}\n\n"
            "Sửa lời thoại xong thì chạy lại bước Thuyết minh cho giọng đọc khớp.")

    # ============================================================ undo / redo

    def _sync_all(self) -> None:
        self._sync_regions()
        self._sync_cues()
        self._sync_speed_list()
        self.sp_sync.blockSignals(True)
        self.sp_sync.setValue(self.proj.sync_offset)
        self.sp_sync.blockSignals(False)
        self._export_changed()
        d = self.proj.duration
        self.lb_dur.setText(f"/ {int(d // 60)}:{int(d % 60):02d}")
        self.lb_meta.setText(f"   {self.proj.width}×{self.proj.height}")

    def _sync_regions(self) -> None:
        self.lst.blockSignals(True)
        self.lst.clear()
        for i, r in enumerate(self.proj.regions):
            it = QListWidgetItem(f"{i + 1}. {r.label}")
            if not r.enabled:
                it.setForeground(QColor(120, 122, 126))
            self.lst.addItem(it)
        self.lst.setCurrentRow(self.preview.sel)
        self.lst.blockSignals(False)
        self._load_props(self.preview.sel)
        self.tl.regions = self.proj.regions

    def _commit(self) -> None:
        self.hist.push(self.proj)
        self._sync_regions()
        self._sync_speed_list()
        self._update_estimate()
        self._update_buttons()
        self.preview.update()
        self.tl.update()
        if self.ck_fx.isChecked():
            self._grab_frame(self.tl.playhead)

    def _restore(self, proj: Optional[Project]) -> None:
        if proj is None:
            return
        self.proj.regions = proj.regions
        self.proj.speeds = proj.speeds
        # Thieu ba dong duoi thi undo sau khi cat clip tra ve trang thai lai:
        # vung va toc do lui lai, clip thi khong - roi save_project ghi nguyen
        # cai lai do xuong dia.
        self.proj.clips = proj.clips
        self.proj.dub_clips = proj.dub_clips
        self.proj.ripple = proj.ripple
        self.proj.sync_offset = proj.sync_offset
        self.proj.export = proj.export
        self.preview.proj = self.proj
        self.preview.sel = min(self.preview.sel, len(self.proj.regions) - 1)
        self.tl.speeds = self.proj.speeds
        self.tl.regions = self.proj.regions
        self.tl.clips = self.proj.live_clips()
        self.tl.dub_clips = self.proj.dub_clips
        self.tl.ripple = self.proj.ripple
        self.tl.dub_offset = self.proj.sync_offset
        self.tl.sel = -1
        self.sp_sync.blockSignals(True)
        self.sp_sync.setValue(self.proj.sync_offset)
        self.sp_sync.blockSignals(False)
        self._sync_regions()
        self._sync_speed_list()
        self._update_estimate()
        self._update_buttons()
        self.preview.update()
        self.tl.update()
        if self.ck_fx.isChecked():
            self._grab_frame(self.tl.playhead)

    def undo(self) -> None:
        self._restore(self.hist.undo())

    def redo(self) -> None:
        self._restore(self.hist.redo())

    def _update_buttons(self) -> None:
        self.btn_undo.setEnabled(self.hist.can_undo())
        self.btn_redo.setEnabled(self.hist.can_redo())
        n = {0: len(self.cues), 3: len(self.proj.speeds),
             4: len(self.proj.regions)}.get(self.tl.sel_lane, 0)
        clip_ok = (0 <= self.tl.sel_clip < len(self.proj.live_clips())
                   and len(self.proj.live_clips()) > 1)
        self.btn_del.setEnabled(clip_ok
                                or 0 <= self.preview.sel < len(self.proj.regions)
                                or (self.tl.sel_lane != 0 and 0 <= self.tl.sel_idx < n))
        cl = self.proj.live_clips()
        i = self.tl.sel_clip
        self.btn_merge.setEnabled(0 <= i < len(cl) - 1
                                  and can_merge(cl, i, self.proj.ripple))

    # ============================================================== xuất bản

    def _export_changed(self) -> None:
        self.proj.export.height = RES_CHOICES[self.cb_res.currentIndex()][1]
        self.proj.export.quality = self.cb_q.currentText()
        self.proj.export.hardsub = self.ck_hardsub.isChecked()
        self._update_estimate()

    def _update_estimate(self) -> None:
        d = self.proj.final_duration()
        dur = f"{d / 60:.0f} phút" if d >= 90 else f"{d:.0f} giây"
        self.lb_est.setText(
            f"<b>Ước tính  ~{human_size(self.proj.est_bytes())}</b><br>"
            f"{self.proj.out_height()}p · {self.proj.target_kbps()} kbps · {dur}")

    def save_project(self) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        self.proj.save(self.proj_path)
        from PyQt6.QtCore import QSettings
        c = QSettings("WrenAutoDub", "editor")
        c.setValue("hsplit", [str(x) for x in self.hsplit.sizes()])
        c.setValue("vsplit", [str(x) for x in self.vsplit.sizes()])
        c.setValue("geom", self.saveGeometry())

    def _restore_layout(self) -> None:
        """Trả lại đúng cách người dùng đã kéo lần trước."""
        from PyQt6.QtCore import QSettings
        c = QSettings("WrenAutoDub", "editor")
        for key, sp in (("hsplit", self.hsplit), ("vsplit", self.vsplit)):
            v = c.value(key)
            if v:
                try:
                    sp.setSizes([int(x) for x in v])
                except (TypeError, ValueError):
                    pass
        g = c.value("geom")
        if g is not None:
            try:
                self.restoreGeometry(g)
            except Exception:
                pass

    def _out_path(self) -> Path:
        v = Path(self.proj.video)
        tag = f".{self.proj.out_height()}p" if self.proj.export.height else ""
        return v.parent / f"{v.stem}.edit{tag}.mp4"

    def build_export_cmd(self, out: Path) -> List[str]:
        from .export import build_command
        return build_command(self.proj, self.cues, self.work, out)

    def export(self) -> None:
        if not Path(self.proj.video).exists():
            QMessageBox.warning(self, "Thiếu video", "Không tìm thấy file gốc.")
            return
        self.save_project()
        out = self._out_path()
        dlg = ExportDialog(self.build_export_cmd(out),
                           self.proj.final_duration(), out, self)
        dlg.exec()
        if dlg.ok:
            QMessageBox.information(
                self, "Xong",
                f"Đã xuất:\n{out}\n\n"
                f"Dung lượng thật: {human_size(out.stat().st_size)}\n"
                f"Ước tính trước đó: {human_size(self.proj.est_bytes())}")

    def closeEvent(self, e) -> None:
        self.save_project()
        self.player.stop()
        if self._frame_proc and self._frame_proc.state() != QProcess.ProcessState.NotRunning:
            self._frame_proc.kill()
        e.accept()
