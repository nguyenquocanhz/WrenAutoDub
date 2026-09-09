# -*- coding: utf-8 -*-
"""Ghi lại mọi lần app chết, kèm dấu vết, vào một file đọc được.

Lý do phải có: trong PyQt6, một exception lọt ra khỏi slot Qt làm process
chết NGAY, không in gì cả. Người dùng chỉ thấy cửa sổ biến mất. Không có
file này thì không cách nào biết chuyện gì đã xảy ra, vì chạy từ shortcut
hay từ bản đóng gói thì cũng chẳng có stderr nào để đọc.

`faulthandler` lo phần chết ở tầng C (Qt, ffmpeg, ctranslate2) — kiểu đó
Python không kịp ném exception nào.
"""

from __future__ import annotations

import atexit
import datetime
import faulthandler
import os
import sys
import traceback
from pathlib import Path

_da_cai = False
_f = None


def thu_muc_log() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = Path(base) / "WrenAutoDub"
    d.mkdir(parents=True, exist_ok=True)
    return d


def duong_dan_log() -> Path:
    return thu_muc_log() / "crash.log"


def _ghi(tieu_de: str, than: str) -> None:
    try:
        gio = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(duong_dan_log(), "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 70 + "\n")
            f.write(f"{gio}  {tieu_de}\n")
            f.write(f"lệnh: {' '.join(sys.argv)}\n")
            f.write("=" * 70 + "\n")
            f.write(than)
            if not than.endswith("\n"):
                f.write("\n")
    except OSError:
        pass            # ghi log mà lỗi thì cũng đành chịu, đừng chết thêm lần nữa


def _bao_cho_nguoi_dung(tom_tat: str) -> None:
    """Hiện hộp thoại nếu đang có giao diện, không thì in ra màn hình."""
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None:
            raise RuntimeError
        h = QMessageBox()
        h.setIcon(QMessageBox.Icon.Critical)
        h.setWindowTitle("WrenAutoDub gặp lỗi")
        h.setText("App vừa gặp lỗi không xử lý được.")
        h.setInformativeText(
            f"Dấu vết đã ghi vào:\n{duong_dan_log()}\n\n"
            "Dự án chưa lưu có thể mất. Gửi file này kèm báo lỗi."
        )
        h.setDetailedText(tom_tat)
        h.exec()
    except Exception:
        print(f"\nLỖI: {tom_tat.strip().splitlines()[-1] if tom_tat.strip() else ''}",
              file=sys.stderr)
        print(f"Dấu vết đầy đủ: {duong_dan_log()}", file=sys.stderr)


def install(hien_hop_thoai: bool = True) -> None:
    """Bật ghi log. Gọi càng sớm càng tốt, trước khi dựng QApplication."""
    global _da_cai, _f
    if _da_cai:
        return
    _da_cai = True

    try:
        _f = open(duong_dan_log(), "a", encoding="utf-8", buffering=1)
        # Bắt cả kiểu chết ở tầng C: Qt, ffmpeg, ctranslate2 nổ thì Python
        # không kịp ném exception nào để excepthook thấy.
        faulthandler.enable(file=_f, all_threads=True)
        atexit.register(_dong)
    except OSError:
        _f = None

    goc = sys.excepthook

    def _hook(kieu, gia_tri, tb):
        if issubclass(kieu, KeyboardInterrupt):
            goc(kieu, gia_tri, tb)
            return
        vet = "".join(traceback.format_exception(kieu, gia_tri, tb))
        _ghi("EXCEPTION KHÔNG BẮT ĐƯỢC", vet)
        if hien_hop_thoai:
            _bao_cho_nguoi_dung(vet)
        goc(kieu, gia_tri, tb)

    sys.excepthook = _hook


def _dong() -> None:
    global _f
    try:
        if _f is not None:
            faulthandler.disable()
            _f.close()
    except Exception:
        pass
    _f = None
