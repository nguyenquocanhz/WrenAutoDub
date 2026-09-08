# -*- coding: utf-8 -*-
"""Nạp DLL CUDA từ các package pip nvidia-* (Windows không tự tìm thấy chúng).

Triệu chứng nếu thiếu: model load OK nhưng chạy thì báo
"Library cublas64_12.dll is not found" hoặc "cudnn_ops64_9.dll".
Phải gọi TRƯỚC khi import ctranslate2 / faster_whisper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

SUBDIRS = ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc", "cufft", "curand")
_done = False


def enable_cuda_dlls(verbose: bool = False) -> List[str]:
    global _done
    if _done or not sys.platform.startswith("win"):
        return []

    roots: List[Path] = []
    try:
        import nvidia
        roots = [Path(p) for p in nvidia.__path__]
    except Exception:
        for sp in sys.path:
            cand = Path(sp) / "nvidia"
            if cand.is_dir():
                roots.append(cand)

    added: List[str] = []
    for root in roots:
        for sub in SUBDIRS:
            bin_dir = root / sub / "bin"
            if not bin_dir.is_dir():
                continue
            try:
                os.add_dll_directory(str(bin_dir))
            except OSError:
                continue
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            added.append(str(bin_dir))

    _done = True
    if verbose and added:
        print(f"  [cuda] nạp {len(added)} thư mục DLL: "
              + ", ".join(Path(a).parent.name for a in added))
    return added
