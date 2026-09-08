# -*- coding: utf-8 -*-
"""Dựng lệnh ffmpeg xuất bản — dùng chung cho cả cửa sổ Widgets lẫn QML.

Trước đây hàm này nằm trong EditorWindow nên bản QML không gọi được. Tách ra
đây để hai giao diện chạy đúng một đường xuất, khỏi lệch nhau về sau.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from . import hwaccel
from .clips import remap_cues_clips
from .edit import Project, build_full_graph
from .mux import escape_sub_path
from .srtutil import write_srt


def out_path(proj: Project) -> Path:
    v = Path(proj.video)
    tag = f".{proj.out_height()}p" if proj.export.height else ""
    return v.parent / f"{v.stem}.edit{tag}.mp4"


def build_command(proj: Project, cues: Sequence, work: Path,
                  out: Path) -> List[str]:
    vw = proj.width or 1920
    vh = proj.height or 1080
    has_dub = Path(proj.dub).exists()

    sub = ""
    if proj.export.hardsub and cues:
        # Mốc phụ đề phải ánh xạ theo cả nhát cắt lẫn đổi tốc độ. Dùng bản chỉ
        # biết tốc độ thì câu nằm trong đoạn đã cắt vẫn còn và mốc sai hết.
        tmp = Path(work) / "vi_export.srt"
        write_srt(tmp, remap_cues_clips(cues, proj.live_clips(), proj.segments(),
                                        proj.ripple, proj.sync_offset))
        sub = escape_sub_path(tmp)

    graph, extra, vlab, alab = build_full_graph(proj, vw, vh, sub, has_dub=has_dub)

    cmd = ["ffmpeg", "-y", "-v", "error", "-progress", "pipe:1", "-nostats"]
    cmd += hwaccel.decode_args(hwaccel.best_decoder("auto"))
    cmd += ["-i", proj.video]
    if has_dub:
        cmd += ["-i", proj.dub]
    for e in extra:
        cmd += ["-i", e]
    if graph:
        cmd += ["-filter_complex", graph]
    cmd += ["-map", vlab if vlab.startswith("0:") else f"[{vlab}]"]

    # Ép bitrate mục tiêu, nếu không thì con số ước tính chẳng còn nghĩa gì
    kbps = proj.target_kbps()
    enc = hwaccel.encode_args(hwaccel.best_encoder("auto"))
    for flag in ("-cq", "-b:v", "-global_quality", "-crf", "-qp_i"):
        while flag in enc:
            i = enc.index(flag)
            del enc[i:i + 2]
    cmd += enc
    cmd += ["-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.5)}k",
            "-bufsize", f"{kbps * 2}k"]

    if alab:
        cmd += ["-map", f"[{alab}]", "-c:a", "aac", "-b:a", "192k", "-ac", "2"]
    else:
        cmd += ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", str(out)]
    return cmd
