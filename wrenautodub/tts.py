# -*- coding: utf-8 -*-
"""Stage 3: đọc phụ đề tiếng Việt và ráp thành 1 track thuyết minh khớp timing.

Hai engine:
  vieneu — VieNeu-TTS v3 Turbo, chạy ONNX trên CPU, giọng tự nhiên, chạy offline
  edge   — Microsoft edge-tts, cần mạng, nhanh, nhẹ
"""

from __future__ import annotations

import asyncio
import random
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import soundfile as sf

from .srtutil import Cue, read_srt

SR = 48000

EDGE_VOICES = {"nam": "vi-VN-NamMinhNeural", "nu": "vi-VN-HoaiMyNeural"}
VIENEU_DEFAULT = "Thái Sơn"          # nam, giọng kể chuyện — hợp thuyết minh phim

_CLEAN = re.compile(r"[\[\(（【][^\]\)）】]*[\]\)）】]|[♪♫#*_<>]")
_errors: List[str] = []


def clean_text(t: str) -> str:
    """Bỏ ký hiệu âm thanh/markup mà giọng đọc không nên phát ra."""
    t = _CLEAN.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—…")
    return t.strip()


def _src_path(pieces_dir: Path, i: int, engine: str) -> Path:
    return pieces_dir / (f"{i:05d}.mp3" if engine == "edge" else f"{i:05d}.src.wav")


# ---------------------------------------------------------------- engine: edge

async def _synth_edge(text: str, voice: str, rate: str, out: Path,
                      sem: asyncio.Semaphore, retries: int = 5) -> bool:
    import edge_tts

    if text and text[-1] not in ".!?…":
        text += "."          # endpoint hay trả rỗng với câu cụt
    kwargs = {"voice": voice}
    if rate and rate not in ("+0%", "0%"):
        kwargs["rate"] = rate

    async with sem:
        last = None
        for attempt in range(retries):
            try:
                comm = edge_tts.Communicate(text, **kwargs)
                data = bytearray()
                async for ch in comm.stream():
                    if ch["type"] == "audio":
                        data.extend(ch["data"])
                if data:
                    out.write_bytes(bytes(data))
                    return True
                last = "endpoint không trả về audio"
            except ValueError as e:
                last = f"tham số sai: {e}"   # retry vô ích, thoát luôn
                break
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
            await asyncio.sleep(1.5 + attempt * 2.0 + random.random())
    _errors.append(last or "?")
    return False


async def _edge_all(jobs: List[Tuple[int, str, Path]], voice: str, rate: str,
                    concurrency: int) -> List[int]:
    sem = asyncio.Semaphore(concurrency)
    done = [0]
    failed: List[int] = []

    async def one(idx: int, text: str, path: Path):
        if not await _synth_edge(text, voice, rate, path, sem):
            failed.append(idx)
        done[0] += 1
        if done[0] % 10 == 0 or done[0] == len(jobs):
            sys.stdout.write(f"\r  [tts] tổng hợp {done[0]}/{len(jobs)}   ")
            sys.stdout.flush()

    await asyncio.gather(*(one(i, t, p) for i, t, p in jobs))
    print()
    return failed


def synth_edge(jobs, voice: str, rate: str, concurrency: int,
               cues: List[Cue], pieces_dir: Path) -> List[int]:
    voice_id = EDGE_VOICES.get(voice, voice)
    print(f"  [tts] engine=edge | giọng {voice_id} | rate {rate}")
    failed = asyncio.run(_edge_all(jobs, voice_id, rate, concurrency))

    # Endpoint Microsoft rớt ngẫu nhiên vài %; vét lại tuần tự thường ăn hết.
    for rnd in range(2):
        if not failed:
            break
        print(f"  [tts] vét lại {len(failed)} câu rớt (lượt {rnd + 1}/2, tuần tự) ...")
        retry = [(i, cues[i].text, _src_path(pieces_dir, i, "edge")) for i in failed]
        failed = asyncio.run(_edge_all(retry, voice_id, rate, 1))
    return failed


# -------------------------------------------------------------- engine: vieneu

_vieneu = None


def load_vieneu(precision: str = "int8"):
    """Nạp VieNeu-TTS một lần rồi giữ lại (khởi động mất ~20 giây)."""
    global _vieneu
    if _vieneu is None:
        from . import models
        models.ensure_vieneu()
        from vieneu import Vieneu
        print("  [tts] nạp VieNeu-TTS v3 Turbo (ONNX/CPU) ...")
        _vieneu = Vieneu(mode="v3turbo", precision=precision)
    return _vieneu


def list_vieneu_voices() -> List[Tuple[str, str]]:
    return load_vieneu().list_preset_voices()


def synth_vieneu(jobs, voice: str, batch_size: int, precision: str) -> List[int]:
    tts = load_vieneu(precision)
    voice = voice if voice not in EDGE_VOICES else VIENEU_DEFAULT
    print(f"  [tts] engine=vieneu | giọng {voice} | lô {batch_size}")

    failed: List[int] = []
    done = 0
    for s in range(0, len(jobs), batch_size):
        chunk = jobs[s:s + batch_size]
        texts = [t for _, t, _ in chunk]
        try:
            outs = tts.infer_batch(texts, voice=voice)
        except Exception as e:
            _errors.append(f"lô lỗi ({type(e).__name__}), chuyển sang đọc lẻ")
            outs = []
            for t in texts:
                try:
                    outs.append(tts.infer(t, voice=voice))
                except Exception as e2:
                    _errors.append(f"{type(e2).__name__}: {e2}")
                    outs.append(None)

        for (idx, _t, path), audio in zip(chunk, outs):
            if audio is None or len(audio) == 0:
                failed.append(idx)
                continue
            a = np.asarray(audio, dtype=np.float32)
            if a.ndim > 1:
                a = a.mean(axis=1)
            sf.write(str(path), a, SR, subtype="PCM_16")

        done += len(chunk)
        sys.stdout.write(f"\r  [tts] tổng hợp {done}/{len(jobs)}   ")
        sys.stdout.flush()
    print()
    return failed


# ------------------------------------------------------------------ ép timing

# edge-tts luôn chèn ~0.2s im lặng ở đầu file -> cắt đi cho giọng bám đúng mốc phụ đề
TRIM = ("silenceremove=start_periods=1:start_duration=0:"
        "start_threshold=-50dB:start_silence=0.03:detection=peak")


def _fit(src: Path, wav: Path, slot: float, max_tempo: float) -> Tuple[float, bool]:
    """Cắt lặng đầu rồi ép đoạn thoại vào khung; rubberband giữ nguyên cao độ giọng."""
    tmp = wav.with_name(wav.stem + ".trim.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-filter:a", f"{TRIM},aresample={SR}", "-ac", "1", str(tmp)],
        check=True)

    try:
        d = sf.info(str(tmp)).duration      # đọc header, không tốn thêm process
    except Exception:
        d = 0.0
    if d <= 0:
        tmp.unlink(missing_ok=True)
        return 0.0, False

    clipped = False
    if slot > 0.05 and d > slot:
        tempo = d / slot
        if tempo > max_tempo:
            tempo = max_tempo
            clipped = True      # vẫn tràn sang câu sau, chấp nhận để còn nghe rõ
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(tmp),
             "-filter:a", f"rubberband=tempo={tempo:.4f}", "-ac", "1", str(wav)],
            check=True)
        tmp.unlink(missing_ok=True)
    else:
        tmp.replace(wav)

    try:
        return sf.info(str(wav)).duration, clipped
    except Exception:
        return 0.0, clipped


# --------------------------------------------------------------------- ráp track

def build_dub(
    vi_srt: str | Path,
    out_wav: str | Path,
    work_dir: str | Path,
    engine: str = "vieneu",
    voice: Optional[str] = None,
    rate: str = "+8%",
    precision: str = "int8",
    batch_size: int = 16,
    total_dur: float = 0.0,
    max_overflow: float = 1.5,
    max_tempo: float = 1.7,
    concurrency: int = 5,
    force: bool = False,
) -> Path:
    out_wav = Path(out_wav)
    if out_wav.exists() and not force:
        print(f"  [skip] đã có {out_wav.name}")
        return out_wav

    if voice is None:
        voice = VIENEU_DEFAULT if engine == "vieneu" else "nam"

    pieces_dir = Path(work_dir) / "pieces"
    pieces_dir.mkdir(parents=True, exist_ok=True)

    cues = [Cue(c.start, c.end, clean_text(c.text)) for c in read_srt(vi_srt)]
    cues = [c for c in cues if c.text]
    if not cues:
        raise RuntimeError(f"{vi_srt} không có nội dung để đọc")

    # Khung thời gian cho mỗi câu: dài nhất là tới lúc câu kế bắt đầu
    slots: List[float] = []
    for i, c in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else c.end + max_overflow + 3.0
        slots.append(max(0.4, min(nxt - c.start - 0.05, c.dur + max_overflow)))

    jobs = [(i, c.text, _src_path(pieces_dir, i, engine))
            for i, c in enumerate(cues)
            if force or not _src_path(pieces_dir, i, engine).exists()]
    print(f"  [tts] {len(cues)} câu | cần tổng hợp {len(jobs)}")

    if jobs:
        if engine == "vieneu":
            failed = synth_vieneu(jobs, voice, batch_size, precision)
        else:
            failed = synth_edge(jobs, voice, rate, concurrency, cues, pieces_dir)
        if failed:
            print(f"  [tts] CẢNH BÁO: {len(failed)} câu không tổng hợp được, sẽ bị bỏ trống")
            for msg in list(dict.fromkeys(_errors))[-3:]:
                print(f"        lý do: {msg}")

    print("  [tts] ép timing + resample ...")
    results: List[Tuple[int, Path, float]] = []
    clipped_n = 0

    def work(i: int):
        src = _src_path(pieces_dir, i, engine)
        wav = pieces_dir / f"{i:05d}.fit.wav"
        if not src.exists() or src.stat().st_size == 0:
            return None
        if wav.exists() and not force:
            try:
                return (i, wav, sf.info(str(wav)).duration, False)
            except Exception:
                pass
        return (i, wav, *_fit(src, wav, slots[i], max_tempo))

    with ThreadPoolExecutor(max_workers=4) as ex:
        for n, r in enumerate(ex.map(work, range(len(cues))), 1):
            if r:
                results.append((r[0], r[1], r[2]))
                clipped_n += 1 if r[3] else 0
            if n % 50 == 0 or n == len(cues):
                sys.stdout.write(f"\r  [tts] ép timing {n}/{len(cues)}   ")
                sys.stdout.flush()
    print()
    if clipped_n:
        print(f"  [tts] {clipped_n} câu dài quá khung (đã tăng tốc tối đa {max_tempo}x, có thể tràn)")

    tail = max((cues[i].start + d) for i, _, d in results) if results else 0.0
    total = max(total_dur, tail) + 1.0
    master = np.zeros(int(total * SR) + SR, dtype=np.float32)

    for i, wav, _d in results:
        try:
            audio, _sr = sf.read(str(wav), dtype="float32", always_2d=False)
        except Exception:
            continue
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        off = int(cues[i].start * SR)
        end = off + len(audio)
        if end > len(master):
            audio = audio[: len(master) - off]
            end = len(master)
        if len(audio) > 0:
            master[off:end] += audio      # chồng lấn nhẹ khi câu trước tràn

    peak = float(np.max(np.abs(master))) if master.size else 0.0
    if peak > 0.99:
        master *= 0.99 / peak

    sf.write(str(out_wav), master, SR, subtype="PCM_16")
    print(f"  [tts] xong: {out_wav} ({total/60:.1f} phút, {len(results)} câu)")
    return out_wav
