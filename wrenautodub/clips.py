# -*- coding: utf-8 -*-
"""Cắt / ghép / sắp xếp clip trên dòng thời gian.

Trước đây phim được coi là một khối liền. Ở đây nó thành danh sách clip, mỗi
clip là một lát của file gốc. Cắt là tách một clip thành hai, ghép là nối hai
clip liền kề nếu chúng vốn liền nhau trong file gốc.

Hai chế độ sắp xếp:
  hít lại  — clip xếp sát nhau, xoá một clip thì các clip sau dồn lên
  rời rạc  — clip giữ nguyên chỗ, khoảng trống thành màn đen + im lặng
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .timing import Segment

MIN_CLIP = 0.10


@dataclass
class Clip:
    src_start: float = 0.0
    src_end: float = 0.0
    at: float = 0.0             # vị trí trên dòng thời gian đích
    enabled: bool = True

    @property
    def dur(self) -> float:
        return max(0.0, self.src_end - self.src_start)

    @property
    def label(self) -> str:
        return f"{self.src_start:.1f}–{self.src_end:.1f}s  ({self.dur:.1f}s)"


def default_clips(duration: float) -> List[Clip]:
    return [Clip(0.0, max(duration, MIN_CLIP), 0.0)]


def ensure(clips: Optional[Sequence[Clip]], duration: float) -> List[Clip]:
    live = [c for c in (clips or []) if c.enabled and c.dur >= MIN_CLIP]
    return live or default_clips(duration)


def ripple_close(clips: Sequence[Clip]) -> List[Clip]:
    """Xếp lại cho các clip sát nhau, không còn khoảng hở."""
    out, t = [], 0.0
    for c in sorted(clips, key=lambda x: x.at):
        out.append(Clip(c.src_start, c.src_end, t, c.enabled))
        t += c.dur
    return out


def layout(clips: Sequence[Clip], ripple: bool) -> List[Tuple[float, float, int]]:
    """(đầu, cuối, chỉ số clip) trên dòng thời gian đích; -1 nghĩa là khoảng trống."""
    seq = ripple_close(clips) if ripple else sorted(clips, key=lambda x: x.at)
    out: List[Tuple[float, float, int]] = []
    t = 0.0
    for i, c in enumerate(seq):
        if not ripple and c.at - t > 0.02:
            out.append((t, c.at, -1))
            t = c.at
        out.append((t, t + c.dur, i))
        t += c.dur
    return out


def out_duration(clips: Sequence[Clip], ripple: bool) -> float:
    lay = layout(clips, ripple)
    return lay[-1][1] if lay else 0.0


def dest_to_src(t: float, clips: Sequence[Clip], ripple: bool) -> Optional[float]:
    """Giây thứ t của bản dựng ứng với giây nào của file gốc."""
    seq = ripple_close(clips) if ripple else sorted(clips, key=lambda x: x.at)
    for a, b, i in layout(clips, ripple):
        if a <= t < b and i >= 0:
            return seq[i].src_start + (t - a)
    return None


def split_at(clips: Sequence[Clip], t: float, ripple: bool) -> List[Clip]:
    """Cắt tại giây t của bản dựng. Trả về danh sách mới."""
    seq = ripple_close(clips) if ripple else sorted(clips, key=lambda x: x.at)
    out: List[Clip] = []
    for (a, b, i) in layout(clips, ripple):
        if i < 0:
            continue
        c = seq[i]
        if a + MIN_CLIP < t < b - MIN_CLIP:
            cut = c.src_start + (t - a)
            out.append(Clip(c.src_start, cut, c.at, c.enabled))
            out.append(Clip(cut, c.src_end, c.at + (cut - c.src_start), c.enabled))
        else:
            out.append(Clip(c.src_start, c.src_end, c.at, c.enabled))
    return ripple_close(out) if ripple else out


def can_merge(clips: Sequence[Clip], i: int, ripple: bool) -> bool:
    seq = ripple_close(clips) if ripple else sorted(clips, key=lambda x: x.at)
    if not (0 <= i < len(seq) - 1):
        return False
    return abs(seq[i].src_end - seq[i + 1].src_start) < 0.02


def merge_at(clips: Sequence[Clip], i: int, ripple: bool) -> List[Clip]:
    """Nối clip i với clip kế nếu chúng vốn liền nhau trong file gốc."""
    seq = ripple_close(clips) if ripple else sorted(clips, key=lambda x: x.at)
    if not can_merge(clips, i, ripple):
        return list(seq)
    a, b = seq[i], seq[i + 1]
    merged = Clip(a.src_start, b.src_end, a.at, a.enabled)
    out = seq[:i] + [merged] + seq[i + 2:]
    return ripple_close(out) if ripple else out


def merge_all(clips: Sequence[Clip], ripple: bool) -> List[Clip]:
    """Gộp mọi cặp liền nhau — đưa về ít clip nhất có thể."""
    out = list(ripple_close(clips) if ripple else sorted(clips, key=lambda x: x.at))
    i = 0
    while i < len(out) - 1:
        if abs(out[i].src_end - out[i + 1].src_start) < 0.02:
            out = merge_at(out, i, ripple)
        else:
            i += 1
    return out


# ----------------------------------------------------- ghép clip với tốc độ

def compose(clips: Sequence[Clip], speed_segs: Sequence[Segment],
            ripple: bool) -> List[tuple]:
    """Danh sách việc cần làm theo đúng thứ tự xuất ra.

    Mỗi phần tử là ("src", đầu_gốc, cuối_gốc, hệ_số) hoặc ("gap", số_giây).
    Cắt clip theo các mốc đổi tốc độ, nên hai tính năng chồng lên nhau vẫn đúng.
    """
    seq = ripple_close(clips) if ripple else sorted(clips, key=lambda x: x.at)
    items: List[tuple] = []
    for a, b, i in layout(clips, ripple):
        if i < 0:
            items.append(("gap", b - a))
            continue
        c = seq[i]
        cur = c.src_start
        for sa, sb, f in speed_segs:
            lo, hi = max(cur, sa), min(c.src_end, sb)
            if hi - lo > 0.01:
                items.append(("src", lo, hi, f))
        if not speed_segs:
            items.append(("src", c.src_start, c.src_end, 1.0))
    return items


def items_duration(items: Sequence[tuple]) -> float:
    total = 0.0
    for it in items:
        total += it[1] if it[0] == "gap" else (it[2] - it[1]) / it[3]
    return total


def build_items_video(items: Sequence[tuple], src: str, w: int, h: int,
                      fps: float = 25.0, tag: str = "cv") -> Tuple[List[str], str]:
    """Trim + setpts từng mảnh, khoảng trống chèn màn đen, rồi concat."""
    n = len(items)
    if n == 0:
        return [], src
    srcs = [i for i, it in enumerate(items) if it[0] == "src"]
    parts: List[str] = []
    if srcs:
        parts.append(f"[{src}]split={len(srcs)}"
                     + "".join(f"[{tag}s{i}]" for i in srcs))
    labels: List[str] = []
    for i, it in enumerate(items):
        lab = f"{tag}{i}"
        if it[0] == "gap":
            parts.append(f"color=c=black:s={w}x{h}:r={fps:g}:d={it[1]:.4f},"
                         f"format=yuv420p[{lab}]")
        else:
            _k, a, b, f = it
            parts.append(f"[{tag}s{i}]trim={a:.4f}:{b:.4f},"
                         f"setpts=(PTS-STARTPTS)/{f:g}[{lab}]")
        labels.append(lab)
    parts.append("".join(f"[{x}]" for x in labels)
                 + f"concat=n={n}:v=1:a=0[{tag}out]")
    return parts, f"{tag}out"


def build_items_audio(items: Sequence[tuple], src: str, tag: str = "ca"
                      ) -> Tuple[List[str], str]:
    from .timing import atempo_chain

    n = len(items)
    if n == 0:
        return [], src
    srcs = [i for i, it in enumerate(items) if it[0] == "src"]
    parts: List[str] = []
    if srcs:
        parts.append(f"[{src}]asplit={len(srcs)}"
                     + "".join(f"[{tag}s{i}]" for i in srcs))
    labels: List[str] = []
    for i, it in enumerate(items):
        lab = f"{tag}{i}"
        if it[0] == "gap":
            parts.append(f"anullsrc=r=48000:cl=stereo:d={it[1]:.4f}[{lab}]")
        else:
            _k, a, b, f = it
            parts.append(f"[{tag}s{i}]atrim={a:.4f}:{b:.4f},asetpts=PTS-STARTPTS,"
                         f"{atempo_chain(f)}[{lab}]")
        labels.append(lab)
    parts.append("".join(f"[{x}]" for x in labels)
                 + f"concat=n={n}:v=0:a=1[{tag}out]")
    return parts, f"{tag}out"


def remap_cues_clips(cues, clips: Sequence[Clip], speed_segs: Sequence[Segment],
                     ripple: bool, offset: float = 0.0):
    """Dời mốc phụ đề theo bản dựng; câu rơi vào phần bị cắt bỏ thì bỏ luôn."""
    from .srtutil import Cue

    items = compose(clips, speed_segs, ripple)
    out = []
    for c in cues:
        a, b = c.start + offset, c.end + offset
        s, e = _map(a, items), _map(b, items)
        if s is None and e is None:
            continue                    # cả câu nằm gọn trong đoạn đã cắt
        if e is None:
            # Câu bắt đầu ở phần giữ lại nhưng kéo sang phần đã cắt: cắt cụt
            # nó ở mối nối thay vì bỏ, không thì mất phụ đề cho đoạn còn giữ.
            e = _edge_after(s, items)
        elif s is None:
            s = _edge_before(e, items)
        if s is None or e is None or e - s < 0.05:
            continue
        out.append(Cue(s, e, c.text))
    return out


def _edge_after(dest: float, items: Sequence[tuple]) -> Optional[float]:
    """Mốc kết thúc của mảnh đang chứa `dest` trên bản dựng."""
    t = 0.0
    for it in items:
        d = it[1] if it[0] == "gap" else (it[2] - it[1]) / it[3]
        if t <= dest < t + d:
            return t + d
        t += d
    return None


def _edge_before(dest: float, items: Sequence[tuple]) -> Optional[float]:
    t = 0.0
    for it in items:
        d = it[1] if it[0] == "gap" else (it[2] - it[1]) / it[3]
        if t <= dest < t + d:
            return t
        t += d
    return None


def _map(t: float, items: Sequence[tuple]) -> Optional[float]:
    """Giây t của file gốc rơi vào giây nào của bản dựng (None nếu đã bị cắt)."""
    dest = 0.0
    for it in items:
        if it[0] == "gap":
            dest += it[1]
            continue
        _k, a, b, f = it
        if a <= t < b:
            return dest + (t - a) / f
        dest += (b - a) / f
    return None
