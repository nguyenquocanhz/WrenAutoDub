# -*- coding: utf-8 -*-
"""WrenAutoDub — giao diện đồ hoạ (PyQt6).

Chạy pipeline bằng QProcess thay vì gọi thẳng trong tiến trình GUI: giao diện
không bị treo, log chảy thẳng ra cửa sổ, và nút Dừng thực sự dừng được.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import (QProcess, QProcessEnvironment, QSettings, Qt,
                          QTimer, pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QFormLayout, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMessageBox, QPlainTextEdit,
                             QProgressBar, QPushButton, QSlider, QSplitter,
                             QStyleFactory, QVBoxLayout, QWidget)

from .icons import icon

ROOT = Path(__file__).resolve().parent.parent
WREN = ROOT / "wren.py"

VIDEO_FILTER = ("Video (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.ts *.webm "
                "*.m4v *.mpg *.mpeg);;Âm thanh (*.wav *.mp3 *.m4a *.aac "
                "*.flac);;Tất cả (*.*)")

MODELS = ["large-v3", "large-v3-turbo", "medium", "small", "base", "tiny", "large-v2"]

# Bước nào chiếm bao nhiêu phần trăm thanh tiến độ (nhận dạng lâu nhất)
STAGE_RANGE = {1: (0, 50), 2: (50, 62), 3: (62, 92), 4: (92, 100)}

RE_STAGE = re.compile(r"===\s*(\d)/4\s+(.+?)\s*===")
RE_ASR = re.compile(r"\[asr\]\s+([\d.]+)%")
RE_TRANS = re.compile(r"\[dịch\]\s+(\d+)/(\d+)\s+câu")
RE_SYNTH = re.compile(r"\[tts\]\s+tổng hợp\s+(\d+)/(\d+)")
RE_FIT = re.compile(r"\[tts\]\s+ép timing\s+(\d+)/(\d+)")
RE_RESULT = re.compile(r"Kết quả:\s*(.+)")


def dark_palette() -> QPalette:
    """Giữ tên cũ cho mọi chỗ đang gọi; thang thật nằm ở theme.py."""
    from .theme import dark_palette as _bang
    return _bang()


def py_env() -> QProcessEnvironment:
    env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONIOENCODING", "utf-8")
    env.insert("PYTHONUTF8", "1")
    return env


class Runner(QProcess):
    """QProcess biết tách dòng và phân biệt dòng tiến độ (ghi đè bằng \\r)."""

    line = pyqtSignal(str)      # dòng hoàn chỉnh -> ghi vào log
    tick = pyqtSignal(str)      # dòng tiến độ đang cập nhật -> chỉ đổi nhãn

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buf = ""
        self.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.setWorkingDirectory(str(ROOT))
        self.setProcessEnvironment(py_env())
        self.readyReadStandardOutput.connect(self._read)

    def launch(self, args: list[str]) -> None:
        self._buf = ""
        self.start(sys.executable, ["-u", str(WREN), *args])

    def _read(self) -> None:
        self._buf += bytes(self.readAllStandardOutput()).decode("utf-8", errors="replace")
        while "\n" in self._buf:
            raw, self._buf = self._buf.split("\n", 1)
            # Bỏ CR của kiểu xuống dòng CRLF trước đã, nếu không thì cái split
            # dưới đây sẽ ăn sạch nội dung dòng và chỉ còn chuỗi rỗng.
            raw = raw.rstrip("\r")
            self.line.emit(raw.split("\r")[-1].rstrip())
        if "\r" in self._buf:
            self._buf = self._buf.split("\r")[-1]
            if self._buf.strip():
                self.tick.emit(self._buf.rstrip())


class ModelsDialog(QDialog):
    """Xem model đã tải, tải thêm, xoá bớt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Model")
        self.setWindowIcon(icon("layers", 64))
        self.resize(720, 460)

        self.info = QLabel("Đang đọc cache ...")
        self.list = QListWidget()
        self.list.setFont(QFont("Consolas", 9))

        self.btn_get = QPushButton(icon("download"), " Tải model đang chọn")
        self.btn_rm = QPushButton(icon("trash"), " Xoá")
        self.btn_refresh = QPushButton(icon("refresh"), " Làm mới")
        self.btn_close = QPushButton(icon("close"), " Đóng")
        self.btn_get.setToolTip("Tải model đang chọn về cache.<br>"
                                "Có kiểm tra dung lượng đĩa trước khi tải.")
        self.btn_rm.setToolTip("Xoá model khỏi đĩa. Cần lại thì tải lại được.")
        self.btn_refresh.setToolTip("Đọc lại cache")
        self.btn_close.setToolTip("Đóng bảng này")
        self.list.setToolTip("Dấu <b>[x]</b> là đã tải, <b>[ ]</b> là chưa.<br>"
                             "Cỡ có dấu ~ là ước tính trước khi tải.")
        for b, f in ((self.btn_get, self.download), (self.btn_rm, self.remove),
                     (self.btn_refresh, self.refresh), (self.btn_close, self.accept)):
            b.clicked.connect(f)

        self.log = QPlainTextEdit(readOnly=True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setMaximumBlockCount(2000)
        self.log.setFixedHeight(120)
        self.log.setToolTip("Tiến trình tải / xoá hiện ở đây")

        row = QHBoxLayout()
        for b in (self.btn_get, self.btn_rm, self.btn_refresh):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.btn_close)

        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(self.list, 1)
        lay.addLayout(row)
        lay.addWidget(self.log)

        self.proc = Runner(self)
        self.proc.line.connect(self._log)
        self.proc.tick.connect(self._log)
        self.proc.finished.connect(self._done)
        self.refresh()

    def _log(self, s: str) -> None:
        if s.strip():
            self.log.appendPlainText(s)

    def _busy(self, on: bool) -> None:
        for b in (self.btn_get, self.btn_rm, self.btn_refresh):
            b.setEnabled(not on)

    def refresh(self) -> None:
        import subprocess
        try:
            out = subprocess.run(
                [sys.executable, str(WREN), "models", "--json"],
                capture_output=True, text=True, encoding="utf-8",
                cwd=str(ROOT), env={**os.environ, "PYTHONUTF8": "1"}, timeout=120)
            data = json.loads(out.stdout.strip().splitlines()[-1])
        except Exception as e:
            self.info.setText(f"Không đọc được danh sách model: {e}")
            return

        self.info.setText(f"Cache: {data['cache']}   —   còn trống {data['free_mb']} MB")
        self.list.clear()
        for m in data["models"]:
            size = f"{m['size_mb']} MB" if m["cached"] else f"~{m['est_mb']} MB"
            mark = "[x]" if m["cached"] else "[ ]"
            it = QListWidgetItem(f"{mark} {m['group']:<4} {m['name']:<34} {size:>9}  {m['desc']}")
            it.setData(Qt.ItemDataRole.UserRole, (m["name"], m["cached"], m["group"]))
            self.list.addItem(it)

    def _selected(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def download(self) -> None:
        sel = self._selected()
        if not sel:
            return
        name, cached, group = sel
        if cached:
            self._log(f"'{name}' đã có sẵn.")
            return
        self._busy(True)
        self.proc.launch(["models", "--get", "vieneu" if group == "tts" else name])

    def remove(self) -> None:
        sel = self._selected()
        if not sel:
            return
        name, cached, _ = sel
        if not cached:
            return
        if QMessageBox.question(self, "Xoá model", f"Xoá '{name}' khỏi cache?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._busy(True)
        self.proc.launch(["models", "--rm", name])

    def _done(self, *_a) -> None:
        self._busy(False)
        self.refresh()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WrenAutoDub")
        self.setWindowIcon(icon("app", 64))
        self.setMinimumSize(1020, 540)
        self.resize(1080, 580)
        self.setAcceptDrops(True)

        self.cfg = QSettings("WrenAutoDub", "gui")
        self.result_path: str | None = None
        self.stage = 0

        self._build()
        self._load_cfg()

        self.proc = Runner(self)
        self.proc.line.connect(self.on_line)
        self.proc.tick.connect(self.on_tick)
        self.proc.finished.connect(self.on_finished)

        self.voices_proc = Runner(self)
        self.voices_proc.line.connect(self._voice_line)
        self.voices_proc.finished.connect(self._voice_done)
        self._voice_buf: list[str] = []

        self.on_engine_changed()
        QTimer.singleShot(60, self._refresh_gpu_info)
        QTimer.singleShot(80, self.probe_video)

    # ------------------------------------------------------------ giao diện

    def _build(self) -> None:
        # --- nguồn
        self.ed_video = QLineEdit(placeholderText="Kéo thả video vào cửa sổ, hoặc bấm Chọn…")
        self.btn_browse = QPushButton(icon("folder"), " Chọn…")
        self.btn_browse.clicked.connect(self.pick_video)
        btn_browse = self.btn_browse
        src = QHBoxLayout()
        src.addWidget(QLabel("Video:"))
        src.addWidget(self.ed_video, 1)
        src.addWidget(btn_browse)

        self.lb_info = QLabel("")
        self.lb_info.setStyleSheet("color:#9aa0a6;")
        self.ed_video.textChanged.connect(self.probe_video)

        # --- nhận dạng
        self.cb_model = QComboBox()
        self.cb_model.addItems(MODELS)
        self.cb_lang = QComboBox()
        self.cb_lang.addItems(["ja", "en", "ko", "zh"])
        self.cb_device = QComboBox()
        self.cb_device.addItems(["auto", "cuda", "cpu"])
        g1 = QGroupBox("Nhận dạng")
        f1 = QFormLayout(g1)
        f1.addRow("Model:", self.cb_model)
        f1.addRow("Tiếng nguồn:", self.cb_lang)
        f1.addRow("Thiết bị:", self.cb_device)

        # --- thuyết minh
        self.cb_engine = QComboBox()
        self.cb_engine.addItems(["vieneu", "edge"])
        self.cb_engine.currentTextChanged.connect(self.on_engine_changed)
        self.cb_voice = QComboBox()
        self.ed_rate = QLineEdit("+8%")
        g2 = QGroupBox("Thuyết minh")
        f2 = QFormLayout(g2)
        f2.addRow("Engine:", self.cb_engine)
        f2.addRow("Giọng:", self.cb_voice)
        f2.addRow("Tốc độ (edge):", self.ed_rate)

        # --- trộn âm
        self.sl_orig = self._slider(35)
        self.sl_dub = self._slider(160, 300)
        self.lb_orig = QLabel("0.35")
        self.lb_dub = QLabel("1.60")
        self.sl_orig.valueChanged.connect(lambda v: self.lb_orig.setText(f"{v/100:.2f}"))
        self.sl_dub.valueChanged.connect(lambda v: self.lb_dub.setText(f"{v/100:.2f}"))
        self.cb_duck = QComboBox()
        self.cb_duck.addItems(["sidechain", "flat"])
        self.ck_orig_track = QCheckBox("Giữ track tiếng gốc")
        self.ck_orig_track.setChecked(True)
        self.ck_softsub = QCheckBox("Nhúng phụ đề Việt")
        self.ck_softsub.setChecked(True)

        g3 = QGroupBox("Trộn âm")
        gl = QGridLayout(g3)
        gl.addWidget(QLabel("Tiếng gốc:"), 0, 0)
        gl.addWidget(self.sl_orig, 0, 1)
        gl.addWidget(self.lb_orig, 0, 2)
        gl.addWidget(QLabel("Thuyết minh:"), 1, 0)
        gl.addWidget(self.sl_dub, 1, 1)
        gl.addWidget(self.lb_dub, 1, 2)
        gl.addWidget(QLabel("Kiểu hạ tiếng gốc:"), 2, 0)
        gl.addWidget(self.cb_duck, 2, 1, 1, 2)
        gl.addWidget(self.ck_orig_track, 3, 0, 1, 3)
        gl.addWidget(self.ck_softsub, 4, 0, 1, 3)

        # --- video / GPU
        self.cb_hwaccel = QComboBox()
        self.cb_hwaccel.addItems(["auto", "cuda", "d3d11va", "dxva2", "qsv", "none"])
        self.cb_venc = QComboBox()
        self.cb_venc.addItems(["copy", "auto", "h264_nvenc", "hevc_nvenc", "libx264"])
        self.ck_hardsub = QCheckBox("Nung phụ đề lên hình")
        self.ck_hardsub.toggled.connect(self.on_hardsub_toggled)
        self.lb_gpu = QLabel("")
        self.lb_gpu.setStyleSheet("color:#9aa0a6;")
        self.lb_gpu.setWordWrap(True)

        g4 = QGroupBox("Video (GPU)")
        f4 = QFormLayout(g4)
        f4.addRow("Giải mã:", self.cb_hwaccel)
        f4.addRow("Mã hoá:", self.cb_venc)
        f4.addRow(self.ck_hardsub)
        f4.addRow(self.lb_gpu)

        opts = QHBoxLayout()
        for g in (g1, g2, g3, g4):
            opts.addWidget(g, 1)

        # --- hàng nút
        self.cb_stage = QComboBox()
        self.cb_stage.addItems(["Cả 4 bước", "1 · Nhận dạng", "2 · Dịch",
                                "3 · Thuyết minh", "4 · Ghép video"])
        self.ck_force = QCheckBox("Làm lại từ đầu")
        self.btn_run = QPushButton(icon("play", 20), " Bắt đầu")
        self.btn_run.setMinimumWidth(120)
        self.btn_run.clicked.connect(self.start)
        self.btn_stop = QPushButton(icon("stop", 20), " Dừng")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_models = QPushButton(icon("layers"), " Model…")
        self.btn_models.clicked.connect(lambda: ModelsDialog(self).exec())
        self.btn_doctor = QPushButton(icon("pulse"), " Doctor")
        self.btn_doctor.clicked.connect(self.run_doctor)
        btn_models, btn_doctor = self.btn_models, self.btn_doctor

        row = QHBoxLayout()
        row.addWidget(QLabel("Chạy:"))
        row.addWidget(self.cb_stage)
        row.addWidget(self.ck_force)
        row.addStretch(1)
        row.addWidget(btn_models)
        row.addWidget(btn_doctor)
        row.addWidget(self.btn_run)
        row.addWidget(self.btn_stop)

        # --- tiến độ + log
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.lb_status = QLabel("Sẵn sàng.")
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setMaximumBlockCount(8000)

        self.lb_result = QLabel("")
        self.lb_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.btn_open = QPushButton(icon("folder_open"), " Mở thư mục")
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self.open_result)
        self.btn_edit = QPushButton(icon("region"), " Sửa video")
        self.btn_edit.clicked.connect(self.open_editor)
        self.btn_srt = QPushButton(icon("subtitle"), " Sửa phụ đề")
        self.btn_srt.setEnabled(False)
        self.btn_srt.clicked.connect(self.open_srt)

        bottom = QHBoxLayout()
        bottom.addWidget(self.lb_result, 1)
        bottom.addWidget(self.btn_edit)
        bottom.addWidget(self.btn_srt)
        bottom.addWidget(self.btn_open)

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addLayout(src)
        tl.addWidget(self.lb_info)
        tl.addLayout(opts)
        tl.addLayout(row)
        tl.addWidget(self.bar)
        tl.addWidget(self.lb_status)

        # Splitter để tự kéo lại tỉ lệ; mặc định log chỉ chiếm phần nhỏ.
        self.split = QSplitter(Qt.Orientation.Vertical)
        self.split.addWidget(top)
        self.split.addWidget(self.log)
        self.split.setCollapsible(0, False)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        # Khối trên lấy đúng chiều cao nó cần, log ăn toàn bộ phần còn lại
        self.split.setSizes([top.sizeHint().height(), 10_000])

        self.log.setMinimumHeight(90)

        lay = QVBoxLayout(self)
        lay.addWidget(self.split, 1)
        lay.addLayout(bottom)

        self._tooltips()

    def _tooltips(self) -> None:
        """Mỗi ô nói rõ nó làm gì và đánh đổi cái gì."""
        t = {
            self.ed_video:
                "Đường dẫn file phim cần thuyết minh.<br>"
                "Kéo thẳng file vào cửa sổ cũng được.",
            self.cb_model:
                "<b>Model nhận dạng tiếng Nhật.</b><br>"
                "<b>large-v3</b> — chính xác nhất, đỉnh 2.3GB VRAM, ~3.7x realtime.<br>"
                "<b>large-v3-turbo</b> — nhanh hơn, nhẹ hơn một chút.<br>"
                "<b>medium</b> — nhanh gấp rưỡi large-v3, kém chính xác hơn rõ.<br>"
                "Model chưa có sẽ <i>tự tải</i> ở lần chạy đầu.",
            self.cb_lang:
                "Ngôn ngữ <b>nói trong phim</b>, không phải ngôn ngữ đích.<br>"
                "Phim Nhật để <b>ja</b>.",
            self.cb_device:
                "<b>auto</b> — thử CUDA trước, hỏng thì tự lùi về CPU.<br>"
                "Ép <b>cpu</b> khi GPU đang bận việc khác (chậm hơn nhiều).",
            self.cb_engine:
                "<b>vieneu</b> — VieNeu-TTS chạy ONNX trên CPU. Không cần mạng, "
                "không tranh VRAM với Whisper, 23 giọng.<br>"
                "<b>edge</b> — Microsoft edge-tts. Cần mạng, chỉ 2 giọng Việt.",
            self.cb_voice:
                "Giọng đọc thuyết minh.<br>"
                "Giọng ghi <i>kể chuyện</i> hợp phim hơn giọng <i>tin tức</i>.",
            self.ed_rate:
                "Tốc độ đọc của edge-tts, ví dụ <b>+0%</b>, <b>+15%</b>.<br>"
                "Không áp dụng cho engine vieneu.",
            self.sl_orig:
                "Âm lượng <b>tiếng Nhật gốc</b> trong bản trộn.<br>"
                "Để 0 là bỏ hẳn tiếng gốc.",
            self.sl_dub:
                "Âm lượng <b>giọng thuyết minh tiếng Việt</b>.",
            self.cb_duck:
                "<b>sidechain</b> — tiếng gốc tự hạ xuống mỗi khi có lời thuyết "
                "minh rồi trả lại như cũ. Nghe tự nhiên hơn.<br>"
                "<b>flat</b> — hạ cố định suốt phim, kiểu thuyết minh truyền hình cũ.",
            self.ck_orig_track:
                "Video ra có thêm một track âm thanh tiếng Nhật nguyên bản,<br>"
                "đổi qua lại được khi xem.",
            self.ck_softsub:
                "Nhúng <b>vi.srt</b> thành track phụ đề bật/tắt được trong video.",
            self.cb_stage:
                "Chạy cả 4 bước, hoặc chỉ một bước.<br>"
                "Hay dùng: sửa tay <b>vi.srt</b> rồi chạy lại riêng bước "
                "<i>Thuyết minh</i> và <i>Ghép video</i>.",
            self.ck_force:
                "Bỏ qua kết quả cũ và làm lại từ đầu.<br>"
                "Không tick thì các bước đã xong sẽ được dùng lại — "
                "đó là cách chạy tiếp sau khi bị ngắt.",
            self.btn_run: "Chạy pipeline",
            self.btn_stop:
                "Dừng tiến trình.<br>"
                "Phần đã xong vẫn được giữ, lần chạy sau đi tiếp chỗ dở dang.",
            self.btn_models:
                "Xem model đã tải và chiếm bao nhiêu đĩa,<br>tải thêm hoặc xoá bớt.",
            self.btn_doctor:
                "Kiểm tra ffmpeg, DLL CUDA, GPU, model, mạng.<br>"
                "Nên chạy trước khi động vào phim dài.",
            self.bar:
                "Tiến độ chung — nhận dạng 0–50%, dịch 50–62%,<br>"
                "thuyết minh 62–92%, ghép video 92–100%.",
            self.log: "Log của pipeline. Lỗi nếu có sẽ hiện ở đây.",
            self.btn_srt:
                "Mở <b>vi.srt</b> bằng trình soạn thảo mặc định.<br>"
                "Sửa xong thì chạy lại bước <i>Thuyết minh</i>.",
            self.btn_open: "Mở thư mục chứa video kết quả",
            self.btn_edit:
                "Mở cửa sổ sửa video: xem trước từng khung, sửa phụ đề,<br>"
                "làm mờ vùng, xoá logo, chèn logo, rồi xuất ra file mới.",
            self.btn_browse: "Mở hộp thoại chọn file phim",
            self.lb_info: "Thông số file đọc bằng ffprobe khi bạn chọn hoặc kéo thả",
            self.cb_hwaccel:
                "Giải mã video bằng GPU thay vì CPU.<br>"
                "<b>Chỉ có tác dụng khi phải mã hoá lại</b> (tức là khi bật "
                "nung phụ đề). Ghép thường chỉ copy stream nên không đụng tới "
                "bộ giải mã.<br><b>none</b> ép dùng CPU.",
            self.cb_venc:
                "<b>copy</b> — không mã hoá lại video, nhanh nhất và không mất "
                "chất lượng. Nên để mặc định.<br>"
                "<b>auto</b> — chọn encoder GPU tốt nhất máy có.<br>"
                "<b>h264_nvenc</b> — GPU, tương thích rộng.<br>"
                "<b>hevc_nvenc</b> — GPU, file nhỏ hơn nhưng kén máy phát.<br>"
                "<b>libx264</b> — CPU, chậm hơn nhiều, chất lượng nhỉnh hơn.",
            self.ck_hardsub:
                "Vẽ phụ đề thẳng lên từng khung hình — máy nào cũng thấy, "
                "nhưng <b>không tắt được</b>.<br>"
                "Buộc phải mã hoá lại toàn bộ video, nên chậm hơn hẳn "
                "và cần encoder.<br>"
                "Không bật thì phụ đề vẫn được nhúng dạng track bật/tắt được.",
            self.lb_gpu: "Năng lực GPU dò được trên máy này",
        }
        for w, tip in t.items():
            w.setToolTip(tip)


    @staticmethod
    def _slider(val: int, top: int = 100) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, top)
        s.setValue(val)
        return s

    # -------------------------------------------------------------- cấu hình

    def _load_cfg(self) -> None:
        c = self.cfg
        self.cb_model.setCurrentText(c.value("model", "large-v3"))
        self.cb_engine.setCurrentText(c.value("engine", "vieneu"))
        self.cb_lang.setCurrentText(c.value("lang", "ja"))
        self.cb_device.setCurrentText(c.value("device", "auto"))
        self.cb_duck.setCurrentText(c.value("duck", "sidechain"))
        self.ed_rate.setText(c.value("rate", "+8%"))
        self.sl_orig.setValue(int(c.value("orig_vol", 35)))
        self.sl_dub.setValue(int(c.value("dub_vol", 160)))
        self.ck_orig_track.setChecked(c.value("orig_track", "true") == "true")
        self.ck_softsub.setChecked(c.value("softsub", "true") == "true")
        self.cb_hwaccel.setCurrentText(c.value("hwaccel", "auto"))
        self.cb_venc.setCurrentText(c.value("venc", "copy"))
        self.ck_hardsub.setChecked(c.value("hardsub", "false") == "true")
        sizes = c.value("split")
        if sizes:
            try:
                self.split.setSizes([int(x) for x in sizes])
            except (TypeError, ValueError):
                pass
        last = c.value("video", "")
        if last and Path(last).exists():
            self.ed_video.setText(last)

    def _save_cfg(self) -> None:
        c = self.cfg
        c.setValue("model", self.cb_model.currentText())
        c.setValue("engine", self.cb_engine.currentText())
        c.setValue("lang", self.cb_lang.currentText())
        c.setValue("device", self.cb_device.currentText())
        c.setValue("duck", self.cb_duck.currentText())
        c.setValue("rate", self.ed_rate.text())
        c.setValue("orig_vol", self.sl_orig.value())
        c.setValue("dub_vol", self.sl_dub.value())
        c.setValue("orig_track", "true" if self.ck_orig_track.isChecked() else "false")
        c.setValue("softsub", "true" if self.ck_softsub.isChecked() else "false")
        c.setValue("hwaccel", self.cb_hwaccel.currentText().split(" ")[0])
        c.setValue("venc", self.cb_venc.currentText().split(" ")[0])
        c.setValue("hardsub", "true" if self.ck_hardsub.isChecked() else "false")
        c.setValue("split", [str(x) for x in self.split.sizes()])
        c.setValue("video", self.ed_video.text())
        c.setValue("voice", self.cb_voice.currentText())

    def closeEvent(self, e) -> None:
        self._save_cfg()
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()
            self.proc.waitForFinished(3000)
        e.accept()

    # ------------------------------------------------------------- kéo thả

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        urls = e.mimeData().urls()
        if urls:
            self.ed_video.setText(urls[0].toLocalFile())

    # ------------------------------------------------------- thông tin video

    def _refresh_gpu_info(self) -> None:
        """Dò năng lực GPU (lần đầu ~3 giây, sau đó đọc cache)."""
        try:
            from . import hwaccel
            caps = hwaccel.probe()
        except Exception as e:
            self.lb_gpu.setText(f"Không dò được: {type(e).__name__}")
            return
        enc = ", ".join(caps["encoders"][:2]) or "không có"
        dec = ", ".join(caps["hwaccels"][:2]) or "không có"
        self.lb_gpu.setText(f"Máy có: {dec} · {enc}")

        for combo, avail in ((self.cb_hwaccel, caps["hwaccels"]),
                             (self.cb_venc, caps["encoders"])):
            for i in range(combo.count()):
                t = combo.itemText(i)
                if t in ("auto", "copy", "none", "libx264"):
                    continue
                if t not in avail:
                    combo.setItemText(i, f"{t} (không có)")

    def probe_video(self) -> None:
        """Đọc nhanh thông số file để biết trước sẽ phải xử lý cái gì."""
        path = self.ed_video.text().strip().strip('"')
        if not path or not Path(path).exists():
            self.lb_info.setText("")
            return
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-of", "json", "-show_entries",
                 "format=duration,size:stream=codec_type,codec_name,width,height,channels",
                 path],
                capture_output=True, text=True, encoding="utf-8", timeout=25)
            d = json.loads(out.stdout or "{}")
        except Exception as e:
            self.lb_info.setText(f"Không đọc được file: {type(e).__name__}")
            return

        fmt = d.get("format", {})
        streams = d.get("streams", [])
        vid = next((x for x in streams if x.get("codec_type") == "video"), {})
        aud = next((x for x in streams if x.get("codec_type") == "audio"), {})

        bits = []
        if vid:
            bits.append(f"{vid.get('codec_name', '?')} "
                        f"{vid.get('width', '?')}×{vid.get('height', '?')}")
        try:
            sec = float(fmt.get("duration", 0))
        except (TypeError, ValueError):
            sec = 0.0
        if sec >= 3600:
            bits.append(f"{int(sec // 3600)}h{int(sec % 3600 // 60):02d}m")
        elif sec >= 60:
            bits.append(f"{int(sec // 60)}m{int(sec % 60):02d}s")
        elif sec > 0:
            bits.append(f"{sec:.0f}s")

        if aud:
            bits.append(f"tiếng {aud.get('codec_name', '?')} {aud.get('channels', '?')}ch")
        n_aud = sum(1 for x in streams if x.get("codec_type") == "audio")
        if n_aud > 1:
            bits.append(f"{n_aud} track tiếng")

        try:
            mb = int(fmt.get("size", 0)) / 2**20
            bits.append(f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB")
        except (TypeError, ValueError):
            pass

        # Ước lượng thô theo tốc độ large-v3 đo được (3.7x realtime)
        if sec >= 120:
            bits.append(f"nhận dạng ~{sec / 60 / 3.7:.0f} phút")
        self.lb_info.setText("   ·   ".join(bits))

    def on_hardsub_toggled(self, on: bool) -> None:
        if on and self.cb_venc.currentText() == "copy":
            self.cb_venc.setCurrentText("auto")
        self.ck_softsub.setEnabled(not on)

    # -------------------------------------------------------------- giọng đọc

    def on_engine_changed(self) -> None:
        engine = self.cb_engine.currentText()
        self.ed_rate.setEnabled(engine == "edge")
        self.cb_voice.clear()

        if engine == "edge":
            self.cb_voice.addItems(["nam", "nu"])
            self.cb_voice.setCurrentText(self.cfg.value("voice_edge", "nam"))
            return

        cached = self.cfg.value("voices_vieneu", "")
        if cached:
            try:
                self.cb_voice.addItems(json.loads(cached))
                self.cb_voice.setCurrentText(self.cfg.value("voice_vieneu", "Thái Sơn"))
                return
            except Exception:
                pass

        self.cb_voice.addItem("(đang nạp danh sách giọng…)")
        self.cb_voice.setEnabled(False)
        self._voice_buf = []
        self.voices_proc.launch(["voices", "--tts", "vieneu", "--json"])

    def _voice_line(self, s: str) -> None:
        if s.strip().startswith("["):
            self._voice_buf.append(s.strip())

    def _voice_done(self, *_a) -> None:
        self.cb_voice.setEnabled(True)
        self.cb_voice.clear()
        try:
            names = [v["name"] for v in json.loads(self._voice_buf[-1])]
        except Exception:
            self.cb_voice.addItem("Thái Sơn")
            self.log.appendPlainText(
                "Không nạp được danh sách giọng VieNeu — dùng tạm giọng mặc định.")
            return
        self.cb_voice.addItems(names)
        self.cb_voice.setCurrentText(self.cfg.value("voice_vieneu", "Thái Sơn"))
        self.cfg.setValue("voices_vieneu", json.dumps(names, ensure_ascii=False))

    # ------------------------------------------------------------------ chạy

    def pick_video(self) -> None:
        start = str(Path(self.ed_video.text()).parent) if self.ed_video.text() else ""
        f, _ = QFileDialog.getOpenFileName(self, "Chọn video", start, VIDEO_FILTER)
        if f:
            self.ed_video.setText(f)

    def _args(self) -> list[str] | None:
        video = self.ed_video.text().strip().strip('"')
        if not video or not Path(video).exists():
            QMessageBox.warning(self, "Thiếu video", "Chọn một file video có thật đã.")
            return None

        voice = self.cb_voice.currentText()
        if voice.startswith("("):     # danh sách giọng chưa nạp xong
            voice = ""

        cmd = ["run", "asr", "translate", "tts", "mux"][self.cb_stage.currentIndex()]
        a = [cmd, video,
             "--model", self.cb_model.currentText(),
             "--lang", self.cb_lang.currentText(),
             "--device", self.cb_device.currentText(),
             "--tts", self.cb_engine.currentText(),
             "--rate", self.ed_rate.text().strip() or "+0%",
             "--duck", self.cb_duck.currentText(),
             "--orig-vol", f"{self.sl_orig.value()/100:.2f}",
             "--dub-vol", f"{self.sl_dub.value()/100:.2f}"]
        if voice:
            a += ["--voice", voice]
        if not self.ck_orig_track.isChecked():
            a.append("--no-orig-track")
        if not self.ck_softsub.isChecked() and not self.ck_hardsub.isChecked():
            a.append("--no-softsub")
        if self.ck_hardsub.isChecked():
            a.append("--hardsub")
        a += ["--hwaccel", self.cb_hwaccel.currentText().split(" ")[0],
              "--venc", self.cb_venc.currentText().split(" ")[0]]
        if self.ck_force.isChecked():
            a.append("-f")
        return a

    def start(self) -> None:
        args = self._args()
        if not args:
            return
        self._save_cfg()
        key = "voice_edge" if self.cb_engine.currentText() == "edge" else "voice_vieneu"
        self.cfg.setValue(key, self.cb_voice.currentText())

        self.log.clear()
        self.bar.setValue(0)
        self.stage = 0
        self.result_path = None
        self.btn_open.setEnabled(False)
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lb_result.setText("")
        self.lb_status.setText("Đang khởi động…")
        self.log.appendPlainText("> wren.py " + " ".join(args) + "\n")
        self.proc.launch(args)

    def stop(self) -> None:
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()
            self.lb_status.setText("Đã dừng theo yêu cầu. Chạy lại sẽ tiếp tục chỗ dở dang.")

    def run_doctor(self) -> None:
        self.log.clear()
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lb_status.setText("Đang kiểm tra môi trường…")
        self.proc.launch(["doctor"])

    # -------------------------------------------------------------- tiến độ

    def _set_progress(self, frac: float) -> None:
        lo, hi = STAGE_RANGE.get(self.stage, (0, 100))
        self.bar.setValue(int(lo + (hi - lo) * max(0.0, min(1.0, frac))))

    def _parse(self, s: str) -> None:
        m = RE_STAGE.search(s)
        if m:
            self.stage = int(m.group(1))
            self.lb_status.setText(f"Bước {self.stage}/4 — {m.group(2).capitalize()}")
            self._set_progress(0)
            return
        m = RE_ASR.search(s)
        if m:
            self._set_progress(float(m.group(1)) / 100)
            return
        m = RE_TRANS.search(s)
        if m:
            self._set_progress(int(m.group(1)) / max(1, int(m.group(2))))
            return
        m = RE_SYNTH.search(s)
        if m:                       # tổng hợp chiếm 70% của bước 3
            self._set_progress(0.7 * int(m.group(1)) / max(1, int(m.group(2))))
            return
        m = RE_FIT.search(s)
        if m:
            self._set_progress(0.7 + 0.3 * int(m.group(1)) / max(1, int(m.group(2))))
            return
        m = RE_RESULT.search(s)
        if m:
            self.result_path = m.group(1).strip()

    def on_line(self, s: str) -> None:
        if s.strip():
            self.log.appendPlainText(s)
        self._parse(s)
        if s.strip() and not s.startswith("==="):
            self.lb_status.setText(s.strip()[:130])

    def on_tick(self, s: str) -> None:
        self._parse(s)
        self.lb_status.setText(s.strip()[:130])

    def on_finished(self, code: int, _status) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)

        srt = self._srt_path()
        self.btn_srt.setEnabled(bool(srt and srt.exists()))

        if code == 0:
            self.bar.setValue(100)
            self.lb_status.setText("Xong.")
            if self.result_path:
                self.lb_result.setText(f"Kết quả: {self.result_path}")
                self.btn_open.setEnabled(Path(self.result_path).exists())
        else:
            self.lb_status.setText(f"Kết thúc với mã lỗi {code} — xem log phía trên.")

    # ------------------------------------------------------------------ tiện

    def _srt_path(self) -> Path | None:
        v = self.ed_video.text().strip().strip('"')
        if not v:
            return None
        p = Path(v)
        return p.parent / f"{p.stem}_work" / "vi.srt"

    def open_editor(self) -> None:
        video = self.ed_video.text().strip().strip('"')
        if not video or not Path(video).exists():
            QMessageBox.warning(self, "Thiếu video", "Chọn một file video có thật đã.")
            return
        from .editor_main import EditorWindow
        self._editor = EditorWindow(video)      # giữ tham chiếu kẻo bị thu gom
        self._editor.show()

    def open_srt(self) -> None:
        srt = self._srt_path()
        if srt and srt.exists():
            os.startfile(str(srt))  # noqa: S606 — mở bằng app mặc định của Windows

    def open_result(self) -> None:
        if not self.result_path:
            return
        p = Path(self.result_path)
        if p.exists():
            os.system(f'explorer /select,"{p}"')
        elif p.parent.exists():
            os.startfile(str(p.parent))


def launch() -> int:
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(dark_palette())
    app.setApplicationName("WrenAutoDub")
    app.setWindowIcon(icon("app", 64))
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(launch())
