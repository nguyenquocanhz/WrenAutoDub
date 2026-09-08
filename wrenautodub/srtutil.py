# -*- coding: utf-8 -*-
"""Đọc/ghi SRT dùng chung cho pipeline JA -> VI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

_TS = r"\d+:\d{2}:\d{2}[,.]\d{1,3}"
_ARROW = re.compile(rf"({_TS})\s*-->\s*({_TS})")


@dataclass
class Cue:
    start: float
    end: float
    text: str

    @property
    def dur(self) -> float:
        return max(0.0, self.end - self.start)


def parse_ts(s: str) -> float:
    h, m, rest = s.split(":")
    sec, ms = re.split(r"[,.]", rest)
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms.ljust(3, "0")) / 1000.0


def fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def read_srt(path: str | Path) -> List[Cue]:
    raw = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    cues: List[Cue] = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        hit = None
        idx = 0
        for i, line in enumerate(lines):
            m = _ARROW.search(line)
            if m:
                hit, idx = m, i
                break
        if not hit:
            continue
        text = " ".join(l.strip() for l in lines[idx + 1:]).strip()
        if text:
            cues.append(Cue(parse_ts(hit.group(1)), parse_ts(hit.group(2)), text))
    return cues


def write_srt(path: str | Path, cues: List[Cue]) -> None:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{fmt_ts(c.start)} --> {fmt_ts(c.end)}\n{c.text}\n")
    Path(path).write_text("\n".join(out), encoding="utf-8")
