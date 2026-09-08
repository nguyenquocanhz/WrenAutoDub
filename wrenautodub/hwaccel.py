# -*- coding: utf-8 -*-
"""Dò năng lực xử lý video bằng GPU của ffmpeg trên máy này.

Danh sách `ffmpeg -encoders` chỉ nói ffmpeg *biên dịch kèm* encoder đó, không
nói GPU chạy được. Ví dụ av1_nvenc có trong danh sách nhưng TU117 (GTX 1650 Ti)
báo "No capable devices found". Nên ở đây chạy thử thật rồi mới kết luận, và
nhớ kết quả lại để lần sau khỏi dò.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List

CACHE = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "WrenAutoDub" / "hwcaps.json"
CACHE_DAYS = 30

DECODE_ORDER = ["cuda", "d3d11va", "dxva2", "qsv", "vaapi"]
# h264 trước hevc: file to hơn nhưng máy nào cũng phát được
ENCODE_ORDER = ["h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv",
                "h264_amf", "hevc_amf"]

# Tham số encoder: chất lượng theo CQ, bitrate thả tự do.
ENCODER_ARGS: Dict[str, List[str]] = {
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq",
                   "-rc", "vbr", "-cq", "23", "-b:v", "0", "-profile:v", "high"],
    "hevc_nvenc": ["-c:v", "hevc_nvenc", "-preset", "p5", "-tune", "hq",
                   "-rc", "vbr", "-cq", "26", "-b:v", "0"],
    "h264_qsv": ["-c:v", "h264_qsv", "-global_quality", "23"],
    "hevc_qsv": ["-c:v", "hevc_qsv", "-global_quality", "26"],
    "h264_amf": ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "23"],
    "hevc_amf": ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "26"],
    "libx264": ["-c:v", "libx264", "-preset", "medium", "-crf", "21"],
}

_caps: dict | None = None


def _run(args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _listed(kind: str) -> List[str]:
    try:
        out = _run(["ffmpeg", "-hide_banner", f"-{kind}"]).stdout
    except Exception:
        return []
    names = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and (kind != "hwaccels"):
            names.append(parts[1])
        elif kind == "hwaccels" and len(parts) == 1 and ":" not in line:
            names.append(parts[0])
    return names


def _try_encoder(name: str) -> bool:
    """Mã hoá thử 1 giây màu mè — cách duy nhất biết chắc GPU kham được."""
    try:
        r = _run(["ffmpeg", "-y", "-v", "error",
                  "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=1",
                  *ENCODER_ARGS.get(name, ["-c:v", name]), "-f", "null", "-"], timeout=90)
        return r.returncode == 0
    except Exception:
        return False


def _try_decoder(hw: str) -> bool:
    try:
        r = _run(["ffmpeg", "-y", "-v", "error", "-hwaccel", hw,
                  "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=1",
                  "-f", "null", "-"], timeout=90)
        return r.returncode == 0
    except Exception:
        return False


def probe(force: bool = False, verbose: bool = False) -> dict:
    """Trả về năng lực thật, có nhớ lại giữa các lần chạy."""
    global _caps
    if _caps is not None and not force:
        return _caps

    if CACHE.exists() and not force:
        try:
            data = json.loads(CACHE.read_text(encoding="utf-8"))
            if time.time() - data.get("when", 0) < CACHE_DAYS * 86400:
                _caps = data
                return _caps
        except Exception:
            pass

    if verbose:
        print("  [gpu] dò năng lực video của ffmpeg (chỉ lần đầu, ~10 giây) ...")

    listed_hw = set(_listed("hwaccels"))
    listed_enc = set(_listed("encoders"))

    decoders = [h for h in DECODE_ORDER if h in listed_hw and _try_decoder(h)]
    encoders = [e for e in ENCODE_ORDER if e in listed_enc and _try_encoder(e)]

    _caps = {
        "when": time.time(),
        "hwaccels": decoders,
        "encoders": encoders,
        "has_opencl": "opencl" in listed_hw,
        "has_vulkan": "vulkan" in listed_hw,
        "software_encoder": "libx264" if "libx264" in listed_enc else "",
    }
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(_caps, indent=1), encoding="utf-8")
    except OSError:
        pass
    if verbose:
        print(f"  [gpu] giải mã: {', '.join(decoders) or 'không có'}"
              f" | mã hoá: {', '.join(encoders) or 'không có'}")
    return _caps


def best_decoder(prefer: str = "auto") -> str:
    if prefer in ("none", ""):
        return ""
    caps = probe()
    if prefer != "auto":
        return prefer if prefer in caps["hwaccels"] else ""
    return caps["hwaccels"][0] if caps["hwaccels"] else ""


def best_encoder(prefer: str = "auto") -> str:
    caps = probe()
    if prefer not in ("auto", "", None):
        return prefer
    if caps["encoders"]:
        return caps["encoders"][0]
    return caps["software_encoder"] or "libx264"


def decode_args(hwaccel: str) -> List[str]:
    """Giải mã trên GPU rồi tải khung về RAM cho filter CPU dùng.

    Cố tình KHÔNG đặt -hwaccel_output_format: filter `subtitles` chạy trên CPU,
    để khung nằm lại trên GPU thì ffmpeg sẽ báo lỗi định dạng.
    """
    return ["-hwaccel", hwaccel] if hwaccel else []


def encode_args(encoder: str) -> List[str]:
    return list(ENCODER_ARGS.get(encoder, ["-c:v", encoder]))


def is_gpu(encoder: str) -> bool:
    return any(k in encoder for k in ("nvenc", "qsv", "amf", "vaapi"))
