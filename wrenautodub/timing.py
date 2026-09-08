# -*- coding: utf-8 -*-
"""Đổi tốc độ từng đoạn và dời khớp tiếng — phần "thời gian" của editor.

Đổi tốc độ làm mọi thứ phía sau nó dồn lại, nên phụ đề và giọng thuyết minh
phải được ánh xạ qua cùng một bảng thời gian thì mới không lệch. Toàn bộ ánh
xạ đó nằm ở `map_time` và `timeline`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

# atempo của ffmpeg chỉ nhận 0.5–100, chậm hơn thì phải nối nhiều lần
ATEMPO_MIN, ATEMPO_MAX = 0.5, 100.0

Segment = Tuple[float, float, float]        # (đầu, cuối, hệ số) theo thời gian gốc

# Preset "đường cong": chia khoảng đã chọn thành các đoạn nhỏ với hệ số khác
# nhau. Không mượt như đường cong thật của CapCut nhưng không cần nội suy khung
# hình, nên nhanh hơn hàng chục lần.
CURVE_PRESETS: dict[str, List[float]] = {
    "Đều": [1.0],
    "Nhanh dần": [1.0, 1.5, 2.2, 3.0],
    "Chậm dần": [3.0, 2.2, 1.5, 1.0],
    "Vụt rồi chậm": [4.0, 2.5, 1.0, 0.5],
    "Chậm rồi vụt": [0.5, 1.0, 2.5, 4.0],
    "Nhấn giữa": [2.5, 1.0, 0.4, 1.0, 2.5],
}


@dataclass
class Speed:
    start: float = 0.0
    end: float = 0.0
    factor: float = 2.0

    @property
    def label(self) -> str:
        return f"{self.factor:g}×  {self.start:.1f}–{self.end:.1f}s"


def expand_preset(start: float, end: float, preset: str) -> List[Speed]:
    """Biến một khoảng thành chuỗi đoạn nhỏ theo preset."""
    factors = CURVE_PRESETS.get(preset, [1.0])
    if len(factors) == 1:
        return [Speed(start, end, factors[0])]
    step = (end - start) / len(factors)
    return [Speed(start + i * step, start + (i + 1) * step, f)
            for i, f in enumerate(factors)]


def normalize(speeds: Sequence[Speed], duration: float) -> List[Speed]:
    """Bỏ đoạn rỗng, kẹp vào [0, duration], sắp xếp và cắt phần chồng lấn."""
    out: List[Speed] = []
    for s in sorted(speeds, key=lambda x: x.start):
        a = max(0.0, min(s.start, duration))
        b = max(0.0, min(s.end, duration))
        if b - a < 0.05 or s.factor <= 0:
            continue
        if out and a < out[-1].end:
            a = out[-1].end                 # đoạn sau nhường đoạn trước
            if b - a < 0.05:
                continue
        out.append(Speed(a, b, float(s.factor)))
    return out


def timeline(speeds: Sequence[Speed], duration: float) -> List[Segment]:
    """Phủ kín [0, duration]; khoảng nào không đặt tốc độ thì hệ số 1.0."""
    segs: List[Segment] = []
    t = 0.0
    for s in normalize(speeds, duration):
        if s.start - t > 0.01:
            segs.append((t, s.start, 1.0))
        segs.append((s.start, s.end, s.factor))
        t = s.end
    if duration - t > 0.01:
        segs.append((t, duration, 1.0))
    return segs or [(0.0, max(duration, 0.01), 1.0)]


def map_time(t: float, segs: Sequence[Segment]) -> float:
    """Thời điểm t ở bản gốc rơi vào giây thứ mấy của bản đã đổi tốc độ."""
    out = 0.0
    for a, b, f in segs:
        if t <= a:
            break
        out += (min(t, b) - a) / f
    return out


def out_duration(segs: Sequence[Segment]) -> float:
    return sum((b - a) / f for a, b, f in segs)


def has_speed(segs: Sequence[Segment]) -> bool:
    return any(abs(f - 1.0) > 1e-3 for _a, _b, f in segs)


def atempo_chain(factor: float) -> str:
    """Nối nhiều atempo vì mỗi cái chỉ kham được 0.5–100."""
    parts: List[str] = []
    f = float(factor)
    while f < ATEMPO_MIN - 1e-9:
        parts.append(f"atempo={ATEMPO_MIN}")
        f /= ATEMPO_MIN
    while f > ATEMPO_MAX + 1e-9:
        parts.append(f"atempo={ATEMPO_MAX}")
        f /= ATEMPO_MAX
    parts.append(f"atempo={f:.6f}".rstrip("0").rstrip("."))
    return ",".join(parts)


def build_speed_video(segs: Sequence[Segment], src: str, tag: str = "sv"
                      ) -> Tuple[List[str], str]:
    """Cắt luồng video thành đoạn, đổi PTS từng đoạn, nối lại."""
    n = len(segs)
    if n == 1 and not has_speed(segs):
        return [], src
    outs = [f"{tag}{i}" for i in range(n)]
    parts = [f"[{src}]split={n}" + "".join(f"[{tag}s{i}]" for i in range(n))]
    for i, (a, b, f) in enumerate(segs):
        parts.append(f"[{tag}s{i}]trim={a:.4f}:{b:.4f},"
                     f"setpts=(PTS-STARTPTS)/{f:g}[{outs[i]}]")
    parts.append("".join(f"[{o}]" for o in outs) + f"concat=n={n}:v=1:a=0[{tag}out]")
    return parts, f"{tag}out"


def build_speed_audio(segs: Sequence[Segment], src: str, tag: str = "sa"
                      ) -> Tuple[List[str], str]:
    """Như trên nhưng cho tiếng: atempo thay setpts, giữ nguyên cao độ."""
    n = len(segs)
    if n == 1 and not has_speed(segs):
        return [], src
    outs = [f"{tag}{i}" for i in range(n)]
    parts = [f"[{src}]asplit={n}" + "".join(f"[{tag}s{i}]" for i in range(n))]
    for i, (a, b, f) in enumerate(segs):
        parts.append(f"[{tag}s{i}]atrim={a:.4f}:{b:.4f},asetpts=PTS-STARTPTS,"
                     f"{atempo_chain(f)}[{outs[i]}]")
    parts.append("".join(f"[{o}]" for o in outs) + f"concat=n={n}:v=0:a=1[{tag}out]")
    return parts, f"{tag}out"


def sync_filter(offset: float) -> str:
    """Dời track thuyết minh so với hình. Dương = đọc muộn hơn."""
    if abs(offset) < 0.005:
        return ""
    if offset > 0:
        return f"adelay={int(offset * 1000)}:all=1"
    return f"atrim=start={abs(offset):.3f},asetpts=PTS-STARTPTS"


def remap_cues(cues, segs: Sequence[Segment], offset: float = 0.0):
    """Dời và co giãn mốc phụ đề cho khớp bản đã đổi tốc độ."""
    from .srtutil import Cue

    out = []
    for c in cues:
        s = map_time(c.start + offset, segs)
        e = map_time(c.end + offset, segs)
        if e - s < 0.08:
            e = s + 0.08
        out.append(Cue(s, e, c.text))
    return out
