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

# Whisper tra ma ISO 639-1, Google Translate lai dung bo ma rieng cho vai thu
# tieng. Khong anh xa thi buoc 1 chay xong 15 phut roi buoc 2 chet ngay dong
# dau - dung cai da xay ra voi mot phim tieng Trung (Whisper 'zh', Google chi
# nhan 'zh-CN' / 'zh-TW').
LANG_MAP = {
    "zh": "zh-CN",      # Whisper khong phan biet gian the / phon the
    "yue": "zh-TW",     # tieng Quang, Google khong co ma rieng
    "he": "iw",         # Google giu ma Hebrew cu
    "jv": "jw",         # Google giu ma Java cu
    "nb": "no",
    "nn": "no",
}


def map_lang(code: str) -> str:
    """Doi ma ngon ngu cua Whisper sang ma Google Translate hieu."""
    c = (code or "").strip().lower().replace("_", "-")
    if c in LANG_MAP:
        return LANG_MAP[c]
    if c.startswith("zh"):
        return "zh-TW" if ("tw" in c or "hant" in c or "trad" in c) else "zh-CN"
    return c
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
    src, tgt = map_lang(source), map_lang(target)
    if src != source or tgt != target:
        print(f"  [dich] ma ngon ngu: {source}->{src}, {target}->{tgt}")
    try:
        tr = GoogleTranslator(source=src, target=tgt)
    except Exception as e:
        raise RuntimeError(
            f"Google Translate khong nhan cap ngon ngu {src} -> {tgt}. "
            f"Chay lai va chi dinh tay, vi du: --lang zh-CN --target vi"
        ) from e

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
