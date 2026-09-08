# -*- coding: utf-8 -*-
"""Stage 2: dịch SRT tiếng Nhật -> tiếng Việt bằng Google Translate (deep-translator)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List

from .srtutil import Cue, read_srt, write_srt

MAX_CHARS = 3500      # Google giới hạn ~5000, để biên an toàn
MAX_LINES = 25        # số câu gộp trong 1 request
SEP = "\n"


def _load_cache(path: Path) -> Dict[str, str]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(path: Path, cache: Dict[str, str]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def _chunks(texts: List[str]) -> List[List[int]]:
    """Gộp các câu thành lô, tôn trọng giới hạn ký tự và số dòng."""
    out, cur, size = [], [], 0
    for i, t in enumerate(texts):
        if cur and (size + len(t) + 1 > MAX_CHARS or len(cur) >= MAX_LINES):
            out.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += len(t) + 1
    if cur:
        out.append(cur)
    return out


def _translate_raw(tr, text: str, retries: int = 4) -> str:
    for attempt in range(retries):
        try:
            res = tr.translate(text)
            if res:
                return res
        except Exception as e:
            if attempt == retries - 1:
                print(f"    [dịch] bỏ qua sau {retries} lần lỗi: {type(e).__name__}")
                return ""
        time.sleep(1.5 * (attempt + 1))
    return ""


def translate_srt(
    in_srt: str | Path,
    out_srt: str | Path,
    source: str = "ja",
    target: str = "vi",
    cache_path: str | Path | None = None,
    delay: float = 0.25,
    force: bool = False,
) -> List[Cue]:
    from deep_translator import GoogleTranslator

    out_srt = Path(out_srt)
    if out_srt.exists() and not force:
        cues = read_srt(out_srt)
        print(f"  [skip] đã có {out_srt.name} ({len(cues)} câu)")
        return cues

    cues = read_srt(in_srt)
    if not cues:
        raise RuntimeError(f"{in_srt} không có câu nào")

    cache_path = Path(cache_path or out_srt.with_suffix(".cache.json"))
    cache = _load_cache(cache_path)
    tr = GoogleTranslator(source=source, target=target)

    texts = [c.text for c in cues]
    todo = [i for i, t in enumerate(texts) if t not in cache]
    print(f"  [dịch] {len(cues)} câu, {len(cache)} đã cache, cần dịch {len(todo)}")

    batches = _chunks([texts[i] for i in todo])
    done = 0
    for bi, batch in enumerate(batches, 1):
        idxs = [todo[j] for j in batch]
        src_lines = [texts[i] for i in idxs]
        joined = SEP.join(src_lines)
        got = _translate_raw(tr, joined)
        parts = [p.strip() for p in got.split(SEP)] if got else []

        if len(parts) == len(src_lines) and all(parts):
            for i, p in zip(idxs, parts):
                cache[texts[i]] = p
        else:
            # Google nuốt/gộp dòng -> lùi về dịch từng câu cho lô này
            print(f"    [dịch] lô {bi} lệch dòng ({len(parts)}/{len(src_lines)}), dịch lẻ")
            for i in idxs:
                one = _translate_raw(tr, texts[i])
                cache[texts[i]] = one or texts[i]
                time.sleep(delay)

        done += len(idxs)
        print(f"\r  [dịch] {done}/{len(todo)} câu ({bi}/{len(batches)} lô)   ", end="", flush=True)
        if bi % 10 == 0:
            _save_cache(cache_path, cache)
        time.sleep(delay)
    print()

    _save_cache(cache_path, cache)
    vi = [Cue(c.start, c.end, cache.get(c.text) or c.text) for c in cues]
    write_srt(out_srt, vi)
    print(f"  [dịch] xong: {out_srt}")
    return vi
