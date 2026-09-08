# -*- coding: utf-8 -*-
"""Kiểm tra môi trường trước khi chạy phim dài.

Mục đích: mọi thứ hay hỏng (DLL CUDA, ffmpeg thiếu rubberband, mất mạng ở bước
dịch) đều lộ ra trong 30 giây, thay vì nổ giữa chừng sau nửa tiếng chạy.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
from typing import List, Tuple

OK, WARN, BAD = "OK ", "!  ", "LỖI"
_rows: List[Tuple[str, str, str]] = []


def _add(state: str, name: str, detail: str = "") -> None:
    _rows.append((state, name, detail))


def _check_python() -> None:
    import sys
    v = sys.version_info
    _add(OK if v >= (3, 9) else BAD, "Python", f"{v.major}.{v.minor}.{v.micro}")


def _check_packages() -> None:
    need = ["faster_whisper", "ctranslate2", "deep_translator", "numpy", "soundfile"]
    opt = ["vieneu", "edge_tts", "huggingface_hub"]
    for mod in need + opt:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "")
            _add(OK, mod, str(ver))
        except Exception as e:
            _add(BAD if mod in need else WARN, mod, f"chưa cài ({type(e).__name__})")


def _check_ffmpeg() -> None:
    for exe in ("ffmpeg", "ffprobe"):
        path = shutil.which(exe)
        _add(OK if path else BAD, exe, path or "không có trong PATH")

    if not shutil.which("ffmpeg"):
        return
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=30).stdout
        for filt, why in (("rubberband", "cần để ép timing giọng đọc"),
                          ("silenceremove", "cần để cắt lặng đầu câu"),
                          ("sidechaincompress", "cần để tự hạ tiếng gốc")):
            has = f" {filt} " in out
            _add(OK if has else WARN, f"ffmpeg:{filt}", "" if has else f"thiếu — {why}")
    except Exception as e:
        _add(WARN, "ffmpeg -filters", str(e)[:60])


def _check_gpu() -> None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=30)
        line = out.stdout.strip().splitlines()[0]
        _add(OK, "GPU", line)
    except Exception:
        _add(WARN, "GPU", "không thấy nvidia-smi — sẽ chạy CPU (rất chậm)")

    try:
        from .cudafix import enable_cuda_dlls
        dirs = enable_cuda_dlls()
        _add(OK if dirs else WARN, "DLL CUDA",
             f"{len(dirs)} thư mục" if dirs else "không tìm thấy package nvidia-*")

        import ctranslate2
        n = ctranslate2.get_cuda_device_count()
        if n:
            types = sorted(ctranslate2.get_supported_compute_types("cuda"))
            _add(OK, "CTranslate2 CUDA", f"{n} thiết bị | {', '.join(types)}")
        else:
            _add(WARN, "CTranslate2 CUDA", "0 thiết bị — sẽ chạy CPU")
    except Exception as e:
        _add(BAD, "CTranslate2 CUDA", f"{type(e).__name__}: {str(e)[:60]}")


def _check_cuda_runtime() -> None:
    """Thử nạp model tiny và chạy 1 giây — bắt lỗi thiếu cuBLAS/cuDNN tại đây."""
    try:
        from .asr import load_model
        load_model("tiny", "cuda", "int8_float16")
        _add(OK, "Chạy thử CUDA", "tiny/int8_float16 nhận dạng được")
    except Exception as e:
        _add(WARN, "Chạy thử CUDA", f"{str(e)[:80]} — sẽ tự lùi về CPU")


def _check_network() -> None:
    try:
        from deep_translator import GoogleTranslator
        r = GoogleTranslator(source="ja", target="vi").translate("テスト")
        _add(OK if r else WARN, "Google Translate", "phản hồi bình thường" if r else "trả về rỗng")
    except Exception as e:
        _add(BAD, "Google Translate", f"{type(e).__name__}: {str(e)[:60]}")

    try:
        import asyncio
        import edge_tts

        async def probe():
            c = edge_tts.Communicate("Thử.", "vi-VN-NamMinhNeural")
            n = 0
            async for ch in c.stream():
                if ch["type"] == "audio":
                    n += len(ch["data"])
            return n

        n = asyncio.run(probe())
        _add(OK if n else WARN, "edge-tts", f"{n} byte" if n else "không trả audio")
    except Exception as e:
        _add(WARN, "edge-tts", f"{type(e).__name__} — dùng engine vieneu thì không cần")


def _check_video_gpu() -> None:
    """Năng lực xử lý video — chỉ có ý nghĩa khi phải mã hoá lại (hardsub)."""
    try:
        from . import hwaccel
        caps = hwaccel.probe()
    except Exception as e:
        _add(WARN, "GPU video", f"{type(e).__name__}: {str(e)[:60]}")
        return

    dec, enc = caps["hwaccels"], caps["encoders"]
    _add(OK if dec else WARN, "Giải mã video GPU",
         ", ".join(dec) if dec else "không có — giải mã bằng CPU")
    _add(OK if enc else WARN, "Mã hoá video GPU",
         ", ".join(enc) if enc else "không có — hardsub sẽ mã hoá bằng CPU (chậm)")

    missing = [n for n, has in (("OpenCL", caps["has_opencl"]),
                                ("Vulkan", caps["has_vulkan"])) if not has]
    if missing:
        _add(WARN, "OpenCL / Vulkan",
             f"bản ffmpeg này không build {', '.join(missing)} — "
             f"dùng CUDA/NVENC thay thế")


def _check_models() -> None:
    from . import models
    rows = models.status()
    have = [r[1] for r in rows if r[2]]
    _add(OK if have else WARN, "Model đã tải",
         f"{len(have)}/{len(rows)}: {', '.join(have)}" if have else "chưa có model nào")
    free = models.free_mb()
    _add(OK if free > 4000 else WARN, "Đĩa chứa cache",
         f"{models.hub_cache()} — còn {free} MB")


def run(quick: bool = False) -> int:
    _rows.clear()
    _check_python()
    _check_packages()
    _check_ffmpeg()
    _check_gpu()
    _check_video_gpu()
    _check_models()
    if not quick:
        _check_cuda_runtime()
        _check_network()

    print(f"\n{'':<4}{'MỤC':<22} CHI TIẾT")
    print("-" * 78)
    for state, name, detail in _rows:
        print(f"{state:<4}{name:<22} {detail}")
    print("-" * 78)

    bad = sum(1 for s, _, _ in _rows if s == BAD)
    warn = sum(1 for s, _, _ in _rows if s == WARN)
    if bad:
        print(f"{bad} lỗi nặng, {warn} cảnh báo — sửa lỗi nặng trước khi chạy phim.")
    elif warn:
        print(f"Không có lỗi nặng, {warn} cảnh báo — chạy được nhưng nên xem qua.")
    else:
        print("Mọi thứ sẵn sàng.")
    if quick:
        print("(bỏ qua kiểm tra mạng và chạy thử CUDA — bỏ --quick để kiểm tra đầy đủ)")
    return 1 if bad else 0
