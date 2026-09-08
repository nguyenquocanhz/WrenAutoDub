# -*- coding: utf-8 -*-
"""Gom kết quả pipeline thành một thư mục kéo thẳng vào CapCut (hoặc NLE khác).

Không đụng tới định dạng project của CapCut — chỉ dùng hai thứ mọi trình dựng
đều nhập được: một file .srt và một file .wav. Nhờ vậy nó không phụ thuộc
phiên bản CapCut và không hỏng khi họ cập nhật.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from .srtutil import read_srt


def _probe(path: Path) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-of", "json", "-show_entries",
             "format=duration,size:stream=codec_type,codec_name,sample_rate,"
             "channels,width,height", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        import json
        return json.loads(out.stdout or "{}")
    except Exception:
        return {}


def _fmt_dur(sec: float) -> str:
    if sec >= 3600:
        return f"{int(sec // 3600)}h{int(sec % 3600 // 60):02d}m{int(sec % 60):02d}s"
    return f"{int(sec // 60)}m{int(sec % 60):02d}s"


README = """WrenAutoDub — bộ file bàn giao
{line}

Phim gốc:
  {video}

Kéo hai file trong thư mục này vào trình dựng, đặt chồng lên phim gốc:

  1. {dub_name}
     Track thuyết minh tiếng Việt, đã ép khớp timing với phim gốc.
     Đặt ở giây 0, KHÔNG dịch chuyển — nó đã canh sẵn theo bản gốc.
     {dub_info}

  2. {srt_name}
     Phụ đề tiếng Việt.
     {srt_info}

Sau khi thả vào:
  - Hạ âm lượng tiếng gốc xuống khoảng 30-35% để nghe rõ giọng đọc.
  - Nếu thấy giọng đọc lệch đều so với hình, dịch cả track thuyết minh
    sang trái hoặc phải vài phần mười giây là khớp.
  - Cắt phim ở đâu thì nhớ cắt track thuyết minh và phụ đề ở đúng chỗ đó.

{extra}Sinh bởi WrenAutoDub. Chạy lại pipeline:
  python wren.py run "{video_name}"
"""


def build(video: str | Path, workdir: Optional[str | Path] = None,
          out_dir: Optional[str | Path] = None,
          copy_video: bool = False) -> Tuple[Path, List[str]]:
    """Tạo thư mục bàn giao. Trả về (thư mục, danh sách cảnh báo)."""
    video = Path(video).expanduser().resolve()
    work = Path(workdir) if workdir else video.parent / f"{video.stem}_work"
    out = Path(out_dir) if out_dir else video.parent / f"{video.stem}_capcut"
    out.mkdir(parents=True, exist_ok=True)

    warn: List[str] = []
    srt_src, dub_src = work / "vi.srt", work / "dub.wav"

    # --- phụ đề
    srt_name = f"{video.stem}.vi.srt"
    srt_info = "(chưa có)"
    if srt_src.exists():
        shutil.copy2(srt_src, out / srt_name)
        cues = read_srt(srt_src)
        last = cues[-1].end if cues else 0.0
        srt_info = f"{len(cues)} câu, câu cuối kết thúc ở {_fmt_dur(last)}."
    else:
        warn.append(f"thiếu {srt_src} — chạy: python wren.py translate \"{video}\"")

    # --- giọng đọc
    dub_name = f"{video.stem}.thuyetminh.wav"
    dub_info = "(chưa có)"
    if dub_src.exists():
        shutil.copy2(dub_src, out / dub_name)
        d = _probe(dub_src)
        st = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
        dur = float(d.get("format", {}).get("duration", 0) or 0)
        mb = int(d.get("format", {}).get("size", 0) or 0) / 2 ** 20
        dub_info = (f"{_fmt_dur(dur)}, {st.get('sample_rate', '?')} Hz, "
                    f"{st.get('channels', '?')} kênh, {mb:.0f} MB.")
    else:
        warn.append(f"thiếu {dub_src} — chạy: python wren.py tts \"{video}\"")

    # --- phim gốc: mặc định chỉ ghi đường dẫn, phim 2 tiếng chép lại rất phí
    extra = ""
    if copy_video and video.exists():
        shutil.copy2(video, out / video.name)
        extra = f"Phim gốc đã được chép vào thư mục này ({video.name}).\n\n"
    elif not video.exists():
        warn.append(f"không thấy phim gốc: {video}")

    (out / "DOC-TRUOC-KHI-DUNG.txt").write_text(
        README.format(line="=" * 34, video=video, video_name=video.name,
                      dub_name=dub_name, dub_info=dub_info,
                      srt_name=srt_name, srt_info=srt_info, extra=extra),
        encoding="utf-8")
    return out, warn


def run(video: str | Path, workdir=None, out_dir=None,
        copy_video: bool = False) -> int:
    out, warn = build(video, workdir, out_dir, copy_video)
    print(f"\n  [bàn giao] thư mục: {out}")
    for f in sorted(out.iterdir()):
        print(f"      {f.name:<44} {f.stat().st_size / 2**20:7.1f} MB")
    for w in warn:
        print(f"  [!] {w}")
    if not warn:
        print("\n  Kéo hai file trên vào CapCut, đặt chồng lên phim gốc.")
    return 1 if warn else 0
