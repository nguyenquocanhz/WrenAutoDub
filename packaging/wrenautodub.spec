# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller cho WrenAutoDub.

    pyinstaller packaging/wrenautodub.spec --noconfirm

Chạy từ THƯ MỤC GỐC của repo, không phải từ trong packaging/.

ĐỌC packaging/README.md TRƯỚC. File này chỉ đóng gói phần "gọn": Python +
PyQt6 + tầng logic + ASR. Nó KHÔNG gói:

  - ffmpeg / ffprobe  -> người dùng vẫn phải tự cài, xem README.md
  - vieneu (torch)    -> ~2.5 GB, bị loại thẳng ở EXCLUDES bên dưới
  - DLL CUDA nvidia-* -> tuỳ chọn, bật bằng biến môi trường WREN_PACK_CUDA=1

Nói thẳng: bản đóng gói này giảm rào cản từ "cài Python + 10 package + ffmpeg"
xuống "giải nén + cài ffmpeg", chứ chưa xoá hẳn được rào cản.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

# SPECPATH là biến PyInstaller bơm sẵn, trỏ tới thư mục chứa file .spec.
REPO = Path(SPECPATH).parent  # noqa: F821
sys.path.insert(0, str(REPO))


# --------------------------------------------------------------------------
# Dữ liệu phải gom vào bundle
# --------------------------------------------------------------------------
# qml_app.py tính đường dẫn bằng `Path(__file__).parent / "qml"`. Trong bundle
# onedir, __file__ trỏ vào _internal/wrenautodub/, nên chỉ cần đặt file .qml
# đúng vị trí tương đối là code chạy nguyên không phải sửa.
#
# Đây là chỗ dễ sai nhất: PyInstaller CHỈ theo dõi import Python. File .qml
# không phải import, nên nếu quên dòng này thì build vẫn thành công, exe vẫn
# chạy, và cửa sổ QML im lặng không hiện gì — engine.rootObjects() rỗng.
datas = [
    (str(REPO / "wrenautodub" / "qml"), "wrenautodub/qml"),
]

binaries = []

# Khai báo THẲNG mọi module của app. Không phải thừa: gần như toàn bộ được
# import bên trong hàm chứ không phải ở đầu file (`from . import asr as S1`
# nằm trong hàm chạy pipeline), nên PyInstaller xếp chúng vào loại "delayed".
# Module delayed mà phân tích tĩnh vấp một cái là rụng im lặng — build vẫn
# thành công, tới lúc chạy mới báo "No module named wrenautodub.asr" rồi âm
# thầm lùi về CPU. Đã gặp thật một lần trong lúc dựng file này.
_MODULE_APP = [
    # Pipeline
    "asr", "translate", "tts", "mux", "handoff",
    # Mô hình dựng
    "edit", "clips", "timing", "export",
    # Hạ tầng
    "hwaccel", "models", "cudafix", "srtutil", "media_strip", "doctor",
    # Giao diện Widgets
    "gui", "editor", "editor_main", "timeline", "icons", "player",
    # Giao diện QML — qmlRegisterType đăng ký từ phía QML, PyInstaller không
    # thấy được chỗ dùng.
    "qml_app", "qml_models", "preview_qml", "timeline_qml",
]

hiddenimports = [f"wrenautodub.{_m}" for _m in _MODULE_APP] + [
    # Bắt buộc phải có để QQmlApplicationEngine nạp được QtQuick.Controls.
    "PyQt6.QtQml",
    "PyQt6.QtQuick",
    "PyQt6.QtMultimedia",
]


# --------------------------------------------------------------------------
# DLL CUDA (tuỳ chọn)
# --------------------------------------------------------------------------
# Mặc định KHÔNG gói: cudnn + cublas cộng lại khoảng 1 GB, và người không có
# card NVIDIA tải về cũng vô ích.
#
# Bật bằng:  set WREN_PACK_CUDA=1  rồi build lại.
#
# CẢNH BÁO: gói được DLL vào không có nghĩa là chạy được. cudafix.py dò DLL
# bằng `import nvidia` rồi đọc `nvidia.__path__` — trong bundle, package
# nvidia bị PyInstaller nén vào và __path__ không còn là thư mục thật, nên
# nhánh đó hỏng. Nhánh dự phòng quét sys.path cũng không tìm ra. Xem mục
# "CUDA" trong packaging/README.md — cần một runtime hook để vá.
if os.environ.get("WREN_PACK_CUDA") == "1":
    for _pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime",
                 "nvidia.cuda_nvrtc", "nvidia.cufft", "nvidia.curand"):
        try:
            binaries += collect_dynamic_libs(_pkg)
        except Exception as e:
            print(f"[spec] bỏ qua {_pkg}: {e}")


# --------------------------------------------------------------------------
# Loại bỏ
# --------------------------------------------------------------------------
# tts.py có `from vieneu import Vieneu` bên trong hàm. PyInstaller phân tích
# tĩnh nên vẫn thấy dòng đó và sẽ kéo cả vieneu -> torch -> transformers vào,
# thành bundle vài GB. Loại thẳng ở đây; bản đóng gói chỉ hỗ trợ `--tts edge`.
#
# Hệ quả PHẢI ghi rõ cho người dùng: engine mặc định là vieneu, nên bản .exe
# này bắt buộc chạy với `--tts edge` (cần mạng). Ai muốn vieneu thì cài Python
# theo cách thường.
EXCLUDES = [
    "vieneu",
    "torch",
    "torchaudio",
    "torchvision",
    "transformers",
    # Rác đo được từ lần build đầu — tổng cộng khoảng 130 MB, không dòng code
    # nào của WrenAutoDub chạm tới. Chúng lọt vào theo dependency phụ của
    # huggingface_hub và của các package khác có sẵn trong site-packages.
    "pyarrow",        # 78.9 MB
    "botocore",       # 17.6 MB
    "boto3",
    "s3transfer",
    "PIL",            # 12.7 MB
    "lxml",           # 6.7 MB
    "pydub",
    "wmi",
    "authlib",
    # Không dùng, nhưng hay bị kéo vào theo dependency phụ.
    "tkinter",
    "matplotlib",
    "scipy",
    "pandas",
    "IPython",
    "notebook",
    "pytest",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineQuick",
    "PyQt6.Qt3DCore",
    "PyQt6.Qt3DRender",
    "PyQt6.QtDataVisualization",
    "PyQt6.QtCharts",
    "PyQt6.QtDesigner",
    "PyQt6.QtBluetooth",
    "PyQt6.QtNfc",
    "PyQt6.QtWebSockets",
    "PyQt6.QtPositioning",
    "PyQt6.QtSerialPort",
    "PyQt6.QtSql",
    "PyQt6.QtTest",
    "PyQt6.QtPdf",
    "PyQt6.QtPdfWidgets",
]


a = Analysis(  # noqa: F821
    [str(REPO / "wren.py")],
    pathex=[str(REPO)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    # Chạy trước mọi code của app. Cần để DLL CUDA đã gói kèm được tìm thấy —
    # cudafix.py một mình không lo được trong bundle. Xem rthook_cuda.py.
    runtime_hooks=[str(REPO / "packaging" / "rthook_cuda.py")],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WrenAutoDub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX hay làm hỏng DLL Qt — đừng bật.
    console=True,       # Xem chú thích "console" trong packaging/README.md.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WrenAutoDub",
)
