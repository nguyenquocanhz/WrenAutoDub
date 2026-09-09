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


def _chua_dich(ra: str, goc: str, tgt: str) -> bool:
    """Câu này vẫn chưa được dịch thật sự?

    Hai dấu hiệu: y hệt câu gốc, hoặc còn chữ Hán trong khi đích không phải
    tiếng dùng chữ Hán.
    """
    if not ra or not ra.strip():
        return True
    if ra.strip() == goc.strip():
        return True
    if not tgt.lower().startswith(("zh", "ja", "ko")):
        han = sum(1 for c in ra if "一" <= c <= "鿿")
        if han and han / max(1, len(ra.strip())) > 0.3:
            return True
    return False


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
    # Rỗng -> "auto": Google tự dò. Trước đây mặc định là "ja" nên video
    # tiếng Anh cũng bị bảo là tiếng Nhật.
    src, tgt = (map_lang(source) if source else "auto"), map_lang(target)
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

    # Lượt vá. Endpoint Google chập chờn nên vẫn còn câu chưa dịch được, mà
    # bản cũ để nguyên câu gốc -> TTS tiếng Việt đọc chữ Hán ra tạp âm. Đo
    # trên phim thật: 13/186 câu (7%) còn nguyên chữ Hán.
    con = [c for c in cues if _chua_dich(cache.get(c.text), c.text, tgt)]
    if con:
        print(f"  [dịch] còn {len(con)} câu chưa dịch được, thử lại chậm hơn")
        for k, c in enumerate(con, 1):
            one = _translate_raw(tr, c.text, retries=5)
            if one and not _chua_dich(one, c.text, tgt):
                cache[c.text] = one
            time.sleep(max(delay, 1.2))
            if k % 5 == 0:
                print(f"\r    [vá] {k}/{len(con)}   ", end="", flush=True)
        print()
        _save_cache(cache_path, cache)

    vi, bo = [], []
    for c in cues:
        t = cache.get(c.text) or c.text
        if _chua_dich(t, c.text, tgt):
            bo.append(c)
            continue
        vi.append(Cue(c.start, c.end, t))
    if bo:
        # Thà thiếu câu còn hơn để TTS đọc chữ Hán thành tiếng vô nghĩa.
        print(f"  [dịch] BỎ {len(bo)} câu không dịch được sau khi vá:")
        for c in bo[:5]:
            print(f"          {c.start:7.1f}s  {c.text[:40]}")
        if len(bo) > 5:
            print(f"          ... và {len(bo) - 5} câu nữa")
    write_srt(out_srt, vi)
    print(f"  [dịch] xong: {out_srt}")
    return vi
