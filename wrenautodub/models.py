# -*- coding: utf-8 -*-
"""Quản lý model: tự tải về, kiểm tra dung lượng đĩa, liệt kê, xoá.

Mọi model nằm trong cache HuggingFace (theo biến môi trường HF_HOME nếu có).
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# tên ngắn -> (repo HuggingFace, dung lượng ~MB, mô tả)
WHISPER: Dict[str, Tuple[str, int, str]] = {
    "tiny":            ("Systran/faster-whisper-tiny",                    75, "nhanh nhất, độ chính xác thấp"),
    "base":            ("Systran/faster-whisper-base",                   145, "nhẹ"),
    "small":           ("Systran/faster-whisper-small",                  484, "cân bằng"),
    "medium":          ("Systran/faster-whisper-medium",                1530, "tốt, ~1.2GB VRAM"),
    "large-v2":        ("Systran/faster-whisper-large-v2",              3090, "bản cũ của large"),
    "large-v3":        ("Systran/faster-whisper-large-v3",              3090, "chính xác nhất, ~2.3GB VRAM"),
    "large-v3-turbo":  ("mobiuslabsgmbh/faster-whisper-large-v3-turbo", 1620, "nhanh gần large-v3"),
    "distil-large-v3": ("Systran/faster-distil-whisper-large-v3",       1510, "nhanh, chỉ tốt với tiếng Anh"),
}

# Model TTS tiếng Việt chạy ONNX trên CPU (không tranh VRAM với Whisper)
VIENEU_REPOS: List[Tuple[str, int, str]] = [
    ("pnnbao-ump/VieNeu-TTS-v3-Turbo",              2200, "VieNeu-TTS v3 Turbo"),
    ("OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX",  87, "bộ mã hoá âm thanh đi kèm"),
]


def hub_cache() -> Path:
    from huggingface_hub import constants as C
    return Path(C.HF_HUB_CACHE)


def _repo_dir(repo: str) -> Path:
    return hub_cache() / ("models--" + repo.replace("/", "--"))


def dir_size_mb(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for f in path.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total // (1024 * 1024)


def is_cached(repo: str) -> bool:
    """Có snapshot thật sự chứ không phải thư mục rỗng do lần tải hỏng."""
    snap = _repo_dir(repo) / "snapshots"
    if not snap.is_dir():
        return False
    return any(any(d.iterdir()) for d in snap.iterdir() if d.is_dir())


def free_mb(path: Optional[Path] = None) -> int:
    try:
        return shutil.disk_usage(str(path or hub_cache())).free // (1024 * 1024)
    except OSError:
        return 0


def _check_space(need_mb: int) -> None:
    have = free_mb()
    # cần dư thêm chút: HF tải vào file tạm rồi mới chuyển sang blobs
    if have < need_mb * 1.3:
        raise RuntimeError(
            f"Không đủ dung lượng: cần ~{need_mb} MB (khuyến nghị {int(need_mb * 1.3)} MB "
            f"kể cả file tạm), ổ chứa cache còn {have} MB.\n"
            f"Cache đang ở: {hub_cache()}\n"
            f"Đổi chỗ bằng cách đặt biến môi trường HF_HOME sang ổ khác."
        )


def download_repo(repo: str, need_mb: int, label: str = "", retries: int = 3) -> Path:
    """Tải 1 repo về cache, có kiểm tra đĩa và thử lại khi rớt mạng."""
    from huggingface_hub import snapshot_download

    if is_cached(repo):
        return _repo_dir(repo)

    _check_space(need_mb)
    print(f"  [tải] {label or repo} (~{need_mb} MB) -> {hub_cache()}")

    last = None
    for attempt in range(retries):
        try:
            snapshot_download(repo_id=repo)
            print(f"  [tải] xong {repo}")
            return _repo_dir(repo)
        except Exception as e:
            last = e
            if attempt < retries - 1:
                wait = 3 * (attempt + 1)
                print(f"  [tải] lỗi ({type(e).__name__}), thử lại sau {wait}s "
                      f"(lần {attempt + 2}/{retries}) — phần đã tải được giữ lại")
                time.sleep(wait)
    raise RuntimeError(f"Tải {repo} thất bại sau {retries} lần: {last}")


def ensure_whisper(name: str) -> str:
    """Bảo đảm model Whisper có sẵn; trả về đường dẫn local để khỏi dò mạng lại."""
    from faster_whisper.utils import download_model

    if name not in WHISPER:
        # người dùng tự truyền repo id hoặc thư mục -> để faster-whisper tự lo
        if Path(name).is_dir():
            return name
        print(f"  [model] '{name}' không có trong danh sách, thử tải như repo HuggingFace")
        return download_model(name)

    repo, size, _ = WHISPER[name]
    if is_cached(repo):
        print(f"  [model] '{name}' đã có sẵn ({dir_size_mb(_repo_dir(repo))} MB)")
    else:
        _check_space(size)
        print(f"  [model] '{name}' chưa có, tải về (~{size} MB) -> {hub_cache()}")

    last = None
    for attempt in range(3):
        try:
            return download_model(name)
        except Exception as e:
            last = e
            if attempt < 2:
                print(f"  [model] lỗi tải ({type(e).__name__}), thử lại sau 3s")
                time.sleep(3)
    raise RuntimeError(f"Không tải được model '{name}': {last}")


def ensure_vieneu() -> None:
    """Bảo đảm model VieNeu-TTS + tokenizer đi kèm đã có."""
    for repo, size, label in VIENEU_REPOS:
        download_repo(repo, size, label)


def status() -> List[Tuple[str, str, bool, int, int, str]]:
    """(nhóm, tên, đã tải, MB thực tế, MB ước tính, mô tả)"""
    rows = []
    for name, (repo, size, desc) in WHISPER.items():
        cached = is_cached(repo)
        rows.append(("asr", name, cached, dir_size_mb(_repo_dir(repo)) if cached else 0, size, desc))
    for repo, size, desc in VIENEU_REPOS:
        cached = is_cached(repo)
        rows.append(("tts", repo.split("/")[-1], cached,
                     dir_size_mb(_repo_dir(repo)) if cached else 0, size, desc))
    return rows


def print_status() -> None:
    rows = status()
    print(f"Cache: {hub_cache()}   (còn trống {free_mb()} MB)\n")
    print(f"{'':>3} {'LOẠI':<4} {'TÊN':<34} {'DUNG LƯỢNG':>11}  MÔ TẢ")
    print("-" * 92)
    for group, name, cached, real, est, desc in rows:
        mark = "[x]" if cached else "[ ]"
        size = f"{real} MB" if cached else f"~{est} MB"
        print(f"{mark:>3} {group:<4} {name:<34} {size:>11}  {desc}")
    have = sum(r[3] for r in rows if r[2])
    print("-" * 92)
    print(f"Đã tải {sum(1 for r in rows if r[2])}/{len(rows)} model, chiếm {have} MB")
    print("\nTải thêm:  python wren.py models --get large-v3")
    print("Xoá bớt:   python wren.py models --rm medium")


def remove(name: str) -> None:
    if name in WHISPER:
        repo = WHISPER[name][0]
    else:
        matches = [r for r, _, _ in VIENEU_REPOS if r.split("/")[-1] == name or r == name]
        if not matches:
            print(f"Không biết model '{name}'. Xem danh sách: python wren.py models")
            return
        repo = matches[0]

    d = _repo_dir(repo)
    if not d.exists():
        print(f"'{name}' vốn chưa tải, không có gì để xoá.")
        return
    mb = dir_size_mb(d)
    shutil.rmtree(d, ignore_errors=True)
    print(f"Đã xoá '{name}' ({mb} MB) tại {d}")


def get(name: str) -> None:
    if name in ("vieneu", "tts"):
        ensure_vieneu()
    elif name == "all-asr":
        for n in WHISPER:
            ensure_whisper(n)
    else:
        ensure_whisper(name)
