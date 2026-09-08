# -*- coding: utf-8 -*-
"""Stage 4: trộn track thuyết minh với tiếng gốc rồi ghép lại vào video."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from . import hwaccel

# Nén sidechain: tiếng gốc tự động hạ xuống mỗi khi giọng thuyết minh cất lên.
# Nhãn trung gian phải khác [v0], [v1]... vì chuỗi filter video dùng dãy đó,
# ghép chung một filter_complex mà trùng nhãn là ffmpeg từ chối chạy.
DUCK_SIDECHAIN = (
    "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[orig];"
    "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
    "volume={dub}[voice];"
    "[voice]asplit=2[vc1][sc];"
    "[orig][sc]sidechaincompress=threshold=0.02:ratio=12:attack=15:release=350[duck];"
    "[duck]volume={orig}[bg];"
    "[bg][vc1]amix=inputs=2:duration=first:normalize=0[mixed];"
    "[mixed]alimiter=limit=0.95[aout]"
)

# Hạ tiếng gốc cố định suốt phim (kiểu thuyết minh truyền hình cũ).
DUCK_FLAT = (
    "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
    "volume={orig}[bg];"
    "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
    "volume={dub}[voice];"
    "[bg][voice]amix=inputs=2:duration=first:normalize=0[mixed];"
    "[mixed]alimiter=limit=0.95[aout]"
)

SUB_STYLE = ("FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H90000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=28")


def escape_sub_path(p: Path) -> str:
    """Đường dẫn Windows nhét vào filter `subtitles` phải escape hai lớp.

    D:\\phim\\a.srt  ->  D\\:/phim/a.srt
    Dấu \\ đổi thành /, dấu : phải escape vì filtergraph dùng nó ngăn tham số.
    """
    s = str(Path(p).resolve()).replace("\\", "/")
    for ch in (":", "'", "[", "]", ","):
        s = s.replace(ch, "\\" + ch)
    return s


def _build_cmd(
    video: Path, dub_wav: Path, out_video: Path, srt: Optional[Path],
    duck: str, orig_vol: float, dub_vol: float, keep_orig_audio: bool,
    softsub: bool, hardsub: bool, hwaccel_name: str, encoder: str,
) -> List[str]:
    audio_graph = (DUCK_SIDECHAIN if duck == "sidechain" else DUCK_FLAT
                   ).format(orig=orig_vol, dub=dub_vol)

    cmd = ["ffmpeg", "-y", "-v", "error", "-stats"]
    cmd += hwaccel.decode_args(hwaccel_name)
    cmd += ["-i", str(video), "-i", str(dub_wav)]
    if softsub and srt:
        cmd += ["-i", str(srt)]

    if hardsub and srt:
        graph = (f"[0:v]subtitles='{escape_sub_path(srt)}'"
                 f":force_style='{SUB_STYLE}'[vout];" + audio_graph)
        cmd += ["-filter_complex", graph, "-map", "[vout]"]
        cmd += hwaccel.encode_args(encoder)
    else:
        cmd += ["-filter_complex", audio_graph, "-map", "0:v:0"]
        cmd += ["-c:v", "copy"] if encoder == "copy" else hwaccel.encode_args(encoder)

    cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ac", "2"]

    if keep_orig_audio:
        cmd += ["-map", "0:a:0", "-c:a:1", "copy",
                "-metadata:s:a:0", "title=Thuyet minh tieng Viet",
                "-metadata:s:a:1", "title=Goc"]

    if softsub and srt:
        idx = 2
        codec = "mov_text" if out_video.suffix.lower() in (".mp4", ".m4v", ".mov") else "srt"
        cmd += ["-map", f"{idx}:0", "-c:s", codec, "-metadata:s:s:0", "language=vie"]

    if out_video.suffix.lower() == ".mp4":
        cmd += ["-movflags", "+faststart"]

    cmd.append(str(out_video))
    return cmd


def mux(
    video: str | Path,
    dub_wav: str | Path,
    out_video: str | Path,
    srt: str | Path | None = None,
    duck: str = "sidechain",
    orig_vol: float = 0.35,
    dub_vol: float = 1.6,
    keep_orig_audio: bool = True,
    hardsub: bool = False,
    hwaccel_name: str = "auto",
    vcodec: str = "copy",
    force: bool = False,
) -> Path:
    out_video = Path(out_video)
    if out_video.exists() and not force:
        print(f"  [skip] đã có {out_video.name}")
        return out_video

    video, dub_wav = Path(video), Path(dub_wav)
    srt_path = Path(srt) if srt and Path(srt).exists() else None
    softsub = srt_path is not None and not hardsub

    hw = hwaccel.best_decoder(hwaccel_name)
    encoder = vcodec

    if hardsub:
        if not srt_path:
            print("  [mux] không có phụ đề để nung, bỏ qua hardsub")
            hardsub = False
        elif vcodec == "copy":
            # Nung phụ đề tức là vẽ lên từng khung -> buộc phải mã hoá lại
            encoder = hwaccel.best_encoder("auto")
            print(f"  [mux] hardsub cần mã hoá lại video -> dùng {encoder}")
    if encoder != "copy":
        encoder = hwaccel.best_encoder(encoder) if encoder == "auto" else encoder

    print(f"  [mux] ducking={duck} | tiếng gốc x{orig_vol} | thuyết minh x{dub_vol}")
    if hw or encoder != "copy":
        bits = []
        if hw:
            bits.append(f"giải mã {hw}")
        bits.append("copy video" if encoder == "copy"
                    else f"mã hoá {encoder}" + (" (GPU)" if hwaccel.is_gpu(encoder) else " (CPU)"))
        print(f"  [mux] {' | '.join(bits)}")

    cmd = _build_cmd(video, dub_wav, out_video, srt_path, duck, orig_vol, dub_vol,
                     keep_orig_audio, softsub, hardsub, hw, encoder)
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")

    if r.returncode != 0 and encoder == "copy":
        # Hay gặp khi codec nguồn không nhét được vào container đích
        print("  [mux] copy video không được, mã hoá lại:")
        for line in (r.stderr or "").strip().splitlines()[-2:]:
            print(f"        {line[:110]}")
        encoder = hwaccel.best_encoder("auto")
        print(f"  [mux] thử lại với {encoder}")
        cmd = _build_cmd(video, dub_wav, out_video, srt_path, duck, orig_vol, dub_vol,
                         keep_orig_audio, softsub, hardsub, hw, encoder)
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")

    if r.returncode != 0:
        for line in (r.stderr or "").strip().splitlines()[-6:]:
            print(f"        {line[:140]}")
        raise RuntimeError(f"ffmpeg thất bại (mã {r.returncode})")

    print(f"  [mux] xong: {out_video}")
    return out_video
