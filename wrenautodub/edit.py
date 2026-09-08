# -*- coding: utf-8 -*-
"""Mô hình dự án sửa video: vùng hiệu ứng, undo/redo, dựng filter, ước tính dung lượng.

Toạ độ vùng lưu theo tỉ lệ 0..1 của khung hình, nên đổi độ phân giải khi xuất
hay phóng to thu nhỏ khung xem trước đều không lệch.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .clips import (Clip, build_items_audio, build_items_video, compose,
                    ensure, items_duration)
from .timing import Speed, has_speed, sync_filter, timeline

BLUR, DELOGO, LOGO = "blur", "delogo", "logo"

KIND_LABEL = {
    BLUR: "Làm mờ",
    DELOGO: "Xoá logo",
    LOGO: "Chèn logo",
}

# Bitrate video (kbps) ở mức chất lượng "vừa", dùng để ước tính dung lượng
BITRATE = {480: 1200, 720: 2500, 1080: 4500, 1440: 8000, 2160: 14000}
QUALITY = {"cao": 1.6, "vừa": 1.0, "nhẹ": 0.62}
AUDIO_KBPS = 192


@dataclass
class Region:
    kind: str = BLUR
    x: float = 0.1          # tỉ lệ so với chiều rộng
    y: float = 0.1
    w: float = 0.2
    h: float = 0.12
    start: float = 0.0      # giây; end<=start nghĩa là suốt phim
    end: float = 0.0
    strength: int = 14      # sigma của gblur
    path: str = ""          # ảnh logo (kind=logo)
    opacity: float = 1.0
    enabled: bool = True

    @property
    def label(self) -> str:
        t = KIND_LABEL.get(self.kind, self.kind)
        if self.end > self.start:
            t += f"  {self.start:.0f}–{self.end:.0f}s"
        if self.kind == LOGO and self.path:
            t += f"  {Path(self.path).name}"
        return t

    def px(self, vw: int, vh: int) -> Tuple[int, int, int, int]:
        """Đổi sang pixel, ép chẵn vì nhiều filter không nhận số lẻ."""
        def even(v: int) -> int:
            return max(2, v - (v % 2))
        x = even(int(self.x * vw))
        y = even(int(self.y * vh))
        w = even(int(self.w * vw))
        h = even(int(self.h * vh))
        w = min(w, even(vw - x))
        h = min(h, even(vh - y))
        return x, y, max(2, w), max(2, h)


@dataclass
class ExportSettings:
    height: int = 0          # 0 = giữ nguyên
    quality: str = "vừa"
    encoder: str = "auto"
    container: str = ".mp4"
    keep_orig_audio: bool = True
    hardsub: bool = False


@dataclass
class Project:
    video: str = ""
    srt: str = ""
    dub: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    regions: List[Region] = field(default_factory=list)
    speeds: List[Speed] = field(default_factory=list)
    clips: List[Clip] = field(default_factory=list)
    dub_clips: List[Clip] = field(default_factory=list)   # rỗng = cắt y hệt hình
    ripple: bool = True             # True = clip hít sát nhau, xoá thì dồn lên
    fps: float = 25.0
    sync_offset: float = 0.0        # dương = giọng thuyết minh đọc muộn hơn hình
    export: ExportSettings = field(default_factory=ExportSettings)

    # ------------------------------------------------------------ lưu / mở

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        p = cls()
        for k, v in d.items():
            if k == "regions":
                p.regions = [Region(**r) for r in v]
            elif k == "speeds":
                p.speeds = [Speed(**r) for r in v]
            elif k == "clips":
                p.clips = [Clip(**r) for r in v]
            elif k == "dub_clips":
                p.dub_clips = [Clip(**r) for r in v]
            elif k == "export":
                p.export = ExportSettings(**v)
            elif hasattr(p, k):
                setattr(p, k, v)
        return p

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1),
                              encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Optional["Project"]:
        p = Path(path)
        if not p.exists():
            return None
        try:
            return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return None

    # --------------------------------------------------------- xuất bản

    def out_height(self) -> int:
        return self.export.height or self.height or 1080

    def segments(self) -> List[Tuple[float, float, float]]:
        return timeline(self.speeds, self.duration)

    def live_clips(self) -> List[Clip]:
        return ensure(self.clips, self.duration)

    def items(self) -> List[tuple]:
        """Việc cần làm theo đúng thứ tự xuất ra: clip nào, tốc độ bao nhiêu."""
        return compose(self.live_clips(), self.segments(), self.ripple)

    def dub_items(self) -> List[tuple]:
        """Nhát cắt riêng của track thuyết minh; chưa tách thì dùng chung với hình."""
        if not self.dub_clips:
            return self.items()
        return compose(ensure(self.dub_clips, self.duration),
                       self.segments(), self.ripple)

    def audio_detached(self) -> bool:
        return bool(self.dub_clips)

    def final_duration(self) -> float:
        """Thời lượng sau khi cắt clip và đổi tốc độ — số dùng để ước tính."""
        return items_duration(self.items())

    def est_bytes(self) -> int:
        """Ước tính dung lượng theo bitrate mục tiêu — chỉ đúng khi encode VBR."""
        h = self.out_height()
        nearest = min(BITRATE, key=lambda k: abs(k - h))
        v = BITRATE[nearest] * QUALITY.get(self.export.quality, 1.0)
        a = AUDIO_KBPS * (2 if self.export.keep_orig_audio else 1)
        return int((v + a) * 1000 / 8 * max(self.final_duration(), 1.0))

    def target_kbps(self) -> int:
        h = self.out_height()
        nearest = min(BITRATE, key=lambda k: abs(k - h))
        return int(BITRATE[nearest] * QUALITY.get(self.export.quality, 1.0))


def human_size(n: int) -> str:
    if n >= 2 ** 30:
        return f"{n / 2**30:.2f} GB"
    return f"{n / 2**20:.0f} MB"


# ------------------------------------------------------------------ undo/redo

class History:
    """Ảnh chụp toàn bộ dự án sau mỗi thay đổi.

    Dự án chỉ là vài chục vùng nên chụp cả cây rẻ hơn nhiều so với viết
    lệnh undo riêng cho từng thao tác, mà lại không bao giờ lệch trạng thái.
    """

    def __init__(self, project: Project, limit: int = 120):
        self.limit = limit
        self._undo: List[dict] = [copy.deepcopy(project.to_dict())]
        self._redo: List[dict] = []

    def push(self, project: Project) -> None:
        snap = copy.deepcopy(project.to_dict())
        if snap == self._undo[-1]:
            return                      # không có gì đổi thì đừng làm bẩn ngăn xếp
        self._undo.append(snap)
        if len(self._undo) > self.limit:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self) -> bool:
        return len(self._undo) > 1

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> Optional[Project]:
        if not self.can_undo():
            return None
        self._redo.append(self._undo.pop())
        return Project.from_dict(copy.deepcopy(self._undo[-1]))

    def redo(self) -> Optional[Project]:
        if not self._redo:
            return None
        snap = self._redo.pop()
        self._undo.append(snap)
        return Project.from_dict(copy.deepcopy(snap))


# ------------------------------------------------------------ dựng filtergraph

def _enable(r: Region) -> str:
    if r.end > r.start:
        return f":enable='between(t,{r.start:.3f},{r.end:.3f})'"
    return ""


def build_video_chain(proj: Project, vw: int, vh: int,
                      srt_escaped: str = "",
                      logo_base: int = 2,
                      do_scale: bool = True) -> Tuple[str, List[str], str]:
    """Trả về (chuỗi filter, danh sách input phụ, nhãn ra).

    Input phụ là các file logo, thêm vào dòng lệnh bằng -i. `logo_base` là chỉ
    số input của logo đầu tiên: khi xuất bản là 2 (0=video, 1=audio thuyết minh),
    còn khi xem trước một khung hình thì là 1 vì không cần nạp audio.
    """
    parts: List[str] = []
    extra_inputs: List[str] = []
    cur = "0:v"
    n = 0

    # delogo xử lý thẳng trên luồng, nối tiếp được nên làm trước
    delogos = [r for r in proj.regions if r.enabled and r.kind == DELOGO]
    if delogos:
        chain = []
        for r in delogos:
            x, y, w, h = r.px(vw, vh)
            # delogo nội suy từ viền nên vùng phải nằm gọn trong khung
            x, y = max(1, x), max(1, y)
            w, h = min(w, vw - x - 1), min(h, vh - y - 1)
            chain.append(f"delogo=x={x}:y={y}:w={max(2, w)}:h={max(2, h)}{_enable(r)}")
        parts.append(f"[{cur}]" + ",".join(chain) + f"[v{n}]")
        cur = f"v{n}"
        n += 1

    # mỗi vùng mờ: tách luồng, cắt, làm mờ, dán đè lại
    for r in [x for x in proj.regions if x.enabled and x.kind == BLUR]:
        x, y, w, h = r.px(vw, vh)
        parts.append(f"[{cur}]split=2[b{n}a][b{n}b]")
        parts.append(f"[b{n}b]crop={w}:{h}:{x}:{y},gblur=sigma={max(1, r.strength)}[b{n}c]")
        parts.append(f"[b{n}a][b{n}c]overlay={x}:{y}{_enable(r)}[v{n}]")
        cur = f"v{n}"
        n += 1

    # logo chèn thêm: mỗi cái là một input ảnh
    for r in [x for x in proj.regions if x.enabled and x.kind == LOGO and x.path]:
        idx = logo_base + len(extra_inputs)
        extra_inputs.append(r.path)
        x, y, w, h = r.px(vw, vh)
        parts.append(f"[{idx}:v]scale={w}:{h},format=rgba,"
                     f"colorchannelmixer=aa={max(0.05, min(1.0, r.opacity)):.2f}[lg{n}]")
        parts.append(f"[{cur}][lg{n}]overlay={x}:{y}{_enable(r)}[v{n}]")
        cur = f"v{n}"
        n += 1

    if srt_escaped:
        parts.append(f"[{cur}]subtitles='{srt_escaped}'[v{n}]")
        cur = f"v{n}"
        n += 1

    if do_scale and proj.export.height and proj.export.height != vh:
        parts.append(f"[{cur}]scale=-2:{proj.export.height}[v{n}]")
        cur = f"v{n}"
        n += 1

    return ";".join(parts), extra_inputs, cur


def needs_reencode(proj: Project) -> bool:
    return bool([r for r in proj.regions if r.enabled]) \
        or has_speed(proj.segments()) \
        or abs(proj.sync_offset) > 0.005 \
        or proj.export.hardsub \
        or bool(proj.export.height and proj.export.height != proj.height)

# ------------------------------------------------- ghép toàn bộ chuỗi filter

AF = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"


def build_audio_graph(proj: "Project", duck: str = "sidechain",
                      orig_vol: float = 0.35, dub_vol: float = 1.6) -> List[str]:
    """Tiếng gốc + thuyết minh (đã dời khớp), trộn xong rồi mới đổi tốc độ.

    Đổi tốc độ sau khi trộn thì chỉ phải làm một lần, và tiếng chắc chắn
    không lệch với hình vì cả hai dùng chung một bảng thời gian.
    """
    sync = sync_filter(proj.sync_offset)
    dub_pre = AF + f",volume={dub_vol}" + (("," + sync) if sync else "")

    # Cắt từng nhánh TRƯỚC khi trộn. Cắt sau khi trộn thì track thuyết minh có
    # nhát cắt riêng sẽ bị áp cắt hai lần.
    parts = [f"[0:a]{AF}[aorig0]", f"[1:a]{dub_pre}[avoice0]"]
    op, aorig = build_items_audio(proj.items(), "aorig0", tag="cao")
    parts.extend(op)
    dp, avoice = build_items_audio(proj.dub_items(), "avoice0", tag="cad")
    parts.extend(dp)

    if duck == "sidechain":
        parts += [
            f"[{avoice}]asplit=2[avc][asc]",
            f"[{aorig}][asc]sidechaincompress=threshold=0.02:ratio=12:"
            "attack=15:release=350[aduck]",
            f"[aduck]volume={orig_vol}[abg]",
            "[abg][avc]amix=inputs=2:duration=first:normalize=0[amix]",
        ]
    else:
        parts += [
            f"[{aorig}]volume={orig_vol}[abg]",
            f"[abg][{avoice}]amix=inputs=2:duration=first:normalize=0[amix]",
        ]

    parts.append("[amix]alimiter=limit=0.95[aout]")
    return parts


def build_full_graph(proj: "Project", vw: int, vh: int, srt_escaped: str = "",
                     has_dub: bool = True, duck: str = "sidechain",
                     orig_vol: float = 0.35, dub_vol: float = 1.6):
    """Trả về (graph, input phụ, nhãn video, nhãn tiếng).

    Thứ tự bắt buộc: hiệu ứng chạy trên thời gian gốc (vì enable=between dùng
    mốc gốc), rồi mới đổi tốc độ, rồi mới nung phụ đề (phụ đề đã được ánh xạ
    sang thời gian mới), cuối cùng đổi cỡ.
    """
    parts: List[str] = []
    chain, extra, cur = build_video_chain(proj, vw, vh, "", logo_base=2,
                                          do_scale=False)
    if chain:
        parts.append(chain)

    items = proj.items()
    vparts, cur = build_items_video(items, cur, vw, vh, proj.fps or 25.0, tag="cv")
    parts.extend(vparts)

    if srt_escaped:
        parts.append(f"[{cur}]subtitles='{srt_escaped}'[vsub]")
        cur = "vsub"

    if proj.export.height and proj.export.height != vh:
        parts.append(f"[{cur}]scale=-2:{proj.export.height}[vfin]")
        cur = "vfin"

    alabel = ""
    if has_dub:
        parts.extend(build_audio_graph(proj, duck, orig_vol, dub_vol))
        alabel = "aout"

    return ";".join(parts), extra, cur, alabel
