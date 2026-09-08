# -*- coding: utf-8 -*-
"""Hàm phụ dùng chung cho các file test.

Đặt tên có gạch dưới đầu để chắc chắn không đụng tên module nào của dự án.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]

# Nhãn ra của một mắt xích filter là (các) nhóm [...] nằm ở cuối chuỗi
_NHAN_CUOI = re.compile(r"((?:\[[^\]]+\])+)\s*$")


def he_so_atempo(chain: str) -> List[float]:
    """Tách chuỗi 'atempo=0.5,atempo=0.8' thành [0.5, 0.8]."""
    ra = []
    for phan in chain.split(","):
        ten, _, gia_tri = phan.partition("=")
        assert ten == "atempo", f"mắt xích lạ trong chuỗi atempo: {phan!r}"
        ra.append(float(gia_tri))
    return ra


def tich(xs: Iterable[float]) -> float:
    p = 1.0
    for x in xs:
        p *= x
    return p


def nhan_ra(parts: Sequence[str]) -> List[str]:
    """Danh sách nhãn ra của từng mắt xích trong chuỗi filter."""
    ra: List[str] = []
    for part in parts:
        m = _NHAN_CUOI.search(part)
        if m:
            ra += re.findall(r"\[([^\]]+)\]", m.group(1))
    return ra


def nhan_trung(parts: Sequence[str]) -> List[str]:
    """Nhãn bị ghi ra hai lần — ffmpeg từ chối chạy nếu có (xem CLAUDE.md)."""
    ns = nhan_ra(parts)
    return sorted({n for n in ns if ns.count(n) > 1})


def bo_ba(cues) -> List[tuple]:
    """Đổi danh sách Cue thành tuple đã làm tròn cho dễ so sánh."""
    return [(round(c.start, 4), round(c.end, 4), c.text) for c in cues]


def bo_bon(clips) -> List[tuple]:
    """Đổi danh sách Clip thành tuple (đầu_gốc, cuối_gốc, vị_trí, bật)."""
    return [(round(c.src_start, 4), round(c.src_end, 4), round(c.at, 4), c.enabled)
            for c in clips]


def lien_tuc(segs: Sequence[tuple], dung_sai: float = 1e-9) -> bool:
    """Các đoạn có nối đuôi nhau không (không hở, không chồng)."""
    for truoc, sau in zip(segs, segs[1:]):
        if abs(truoc[1] - sau[0]) > dung_sai:
            return False
    return True
