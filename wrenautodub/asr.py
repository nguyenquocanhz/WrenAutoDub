# -*- coding: utf-8 -*-
"""Stage 1: nhận dạng tiếng Nhật bằng faster-whisper (tối ưu 4GB VRAM)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List

from . import models
from .cudafix import enable_cuda_dlls
from .srtutil import Cue, write_srt

# Thứ tự thử: nhanh nhất -> an toàn nhất. Rơi xuống CPU nếu CUDA hỏng.
FALLBACKS = [
    ("cuda", "int8_float16"),
    ("cuda", "int8"),
    ("cuda", "float16"),
    ("cpu", "int8"),
]

# Gợi ý ngữ cảnh giúp Whisper chấm câu tiếng Nhật tử tế hơn.
DEFAULT_PROMPT = "以下は日本語の映画の台詞です。句読点を付けて書き起こしてください。"

SENT_END = "。．.!?！？…"
SOFT_BREAK = "、,，;；:："


def ffprobe_duration(path: str | Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nk=1:nw=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def extract_audio(video: str | Path, out_wav: str | Path, force: bool = False) -> Path:
    """Tách audio 16kHz mono. Nhanh và ổn định hơn để faster-whisper tự decode mkv/mp4."""
    out_wav = Path(out_wav)
    if out_wav.exists() and not force:
        print(f"  [skip] đã có {out_wav.name}")
        return out_wav
    if not shutil.which("ffmpeg"):
        raise RuntimeError("Không tìm thấy ffmpeg trong PATH")
    print(f"  [ffmpeg] tách audio 16kHz mono -> {out_wav.name}")
    # aresample=async=1 BẮT BUỘC. File tải từ HLS hay bị thiếu segment: mốc thời
    # gian của gói tin vẫn liền mạch nhưng bên trong hụt mất cả phút âm thanh.
    # Không có nó, ffmpeg dồn hai mép lỗ lại với nhau, thoát mã 0, không cảnh báo
    # gì — và mọi câu thoại sau lỗ bị đẩy sớm đúng bằng độ dài lỗ.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video),
         "-vn", "-af", "aresample=async=1",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav)],
        check=True,
    )
    _check_duration(video, out_wav)
    return out_wav


def _probe_duration(path) -> float:
    """Thời lượng theo ffprobe, 0.0 nếu không đọc được."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60)
        return float((r.stdout or "").strip() or 0.0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0.0


def _check_duration(video, wav, tol: float = 1.0) -> None:
    """Audio rút ra phải dài gần bằng phim. Lệch là hỏng cả bản thuyết minh.

    Đây là chốt chặn cho đúng loại lỗi vừa gặp: ffmpeg thoát 0, file nghe vẫn
    bình thường, chỉ có điều nó ngắn hơn phim và mốc thoại lệch dần.
    """
    dv, dw = _probe_duration(video), _probe_duration(wav)
    if dv <= 0 or dw <= 0:
        return
    if abs(dv - dw) <= max(tol, dv * 0.005):
        return
    raise RuntimeError(f"""
Audio tach ra dai {dw:.1f}s nhung phim dai {dv:.1f}s (lech {dv - dw:+.1f}s).
File nguon nhieu kha nang bi thieu doan - hay gap o ban tai HLS.
Neu van muon chay, va lai file roi chay tren ban va:
  ffmpeg -i "{video}" -c:v copy -af aresample=async=1 "phim_va.mp4"
""".strip())


def _smoke_test(model) -> None:
    """Chạy thử 1 giây im lặng để ép nạp cuBLAS/cuDNN ngay tại đây.

    Không có bước này, lỗi thiếu DLL chỉ nổ ra giữa chừng khi đã chạy được vài phút.
    """
    import numpy as np

    segs, _ = model.transcribe(np.zeros(16000, dtype=np.float32),
                               language="ja", vad_filter=False, beam_size=1)
    for _ in segs:
        break


def load_model(model_size: str, device: str = "auto", compute_type: str = "auto"):
    enable_cuda_dlls(verbose=True)
    from faster_whisper import WhisperModel

    # Tải model về trước; sau bước này chỉ đọc từ đĩa nên không sợ rớt mạng giữa chừng.
    model_path = models.ensure_whisper(model_size)

    if device != "auto" and compute_type != "auto":
        combos = [(device, compute_type)]
    elif device != "auto":
        combos = [(d, c) for d, c in FALLBACKS if d == device]
    else:
        combos = FALLBACKS

    last = None
    for dev, ct in combos:
        try:
            print(f"  [model] thử {model_size} | {dev} | {ct} ...")
            m = WhisperModel(model_path, device=dev, compute_type=ct,
                             local_files_only=True)
            _smoke_test(m)
            print(f"  [model] OK: {dev}/{ct}")
            return m
        except Exception as e:  # cuDNN thiếu, hết VRAM, compute_type không hỗ trợ...
            print(f"  [model] hỏng ({type(e).__name__}: {str(e)[:120]}) -> thử tiếp")
            last = e
    raise RuntimeError(f"Không load được model. Lỗi cuối: {last}")


def _split_by_words(words, max_dur: float, max_chars: int) -> List[Cue]:
    """Cắt 1 segment dài thành từng câu, dùng mốc thời gian của từng từ.

    Whisper + VAD hay trả về một khối 15-30 giây; thuyết minh cần câu ngắn
    thì giọng đọc mới bám được hình.
    """
    cues: List[Cue] = []
    buf = []

    def flush(ws):
        if not ws:
            return
        text = "".join(w.word for w in ws).strip()
        if text:
            cues.append(Cue(ws[0].start, ws[-1].end, text))

    for w in words:
        buf.append(w)
        text = "".join(x.word for x in buf).strip()
        if not text:
            continue
        dur = buf[-1].end - buf[0].start

        if text[-1] in SENT_END:
            flush(buf)
            buf = []
            continue

        if dur >= max_dur or len(text) >= max_chars:
            # lùi về dấu phẩy gần nhất để câu không bị cắt giữa ý
            cut = len(buf)
            for i in range(len(buf) - 1, max(0, len(buf) // 3), -1):
                if buf[i].word.strip()[-1:] in SOFT_BREAK:
                    cut = i + 1
                    break
            flush(buf[:cut])
            buf = buf[cut:]

    flush(buf)
    return cues


def _split_by_text(seg, max_chars: int) -> List[Cue]:
    """Không có word timestamps thì chia thời lượng theo tỉ lệ số ký tự."""
    import re

    parts = [p for p in re.split(rf"(?<=[{SENT_END}])", seg.text.strip()) if p.strip()]
    if len(parts) <= 1:
        return [Cue(seg.start, seg.end, seg.text.strip())]

    total = sum(len(p) for p in parts)
    cues: List[Cue] = []
    t = seg.start
    span = seg.end - seg.start
    for p in parts:
        d = span * len(p) / total
        cues.append(Cue(t, min(t + d, seg.end), p.strip()))
        t += d
    return cues


# Whisper hoc tu 680.000 gio video kem phu de cao tren mang, trong do vo so
# phim co NHAC chay tren phan credit con dong phu de luc do ghi ten nhom dich
# hay ten nen tang. No hoc lien ket "nhac -> chu credit", nen gap nhac hieu la
# nha ra nguyen van may cau nay du khong ai noi gi.
#
# Da dinh that: mot phim 15 phut ra 4 cau kieu nay (2,6%), va vi TTS doc het
# nen ban thuyet minh MO DAU bang cau "Phu de boi Amara, cong dong org cung cap".
#
# Chi liet ke cum DAC HIEU - thu khong bao gio la thoai that. Khong loc theo
# mat do chu/giay: da do tren phim that, "十身" (2 chu / 17.6 giay) la thoai
# that, loc kieu do se xoa nham phu de that.
_AO_GIAC = (
    "amara.org", "amara.", "字幕由", "字幕提供", "社群提供", "中文字幕志愿者",
    "优优独播剧场", "yoyo television series", "独播剧场",
    "请不吝点赞", "订阅 转发", "打赏支持", "点点栏目",
    "subtitles by", "subtitled by", "transcribed by", "captions by",
    "thanks for watching", "thank you for watching",
    "字幕組", "字幕组", "翻译:", "校对:", "时间轴:",
    "ご視聴ありがとうございました", "字幕視聴",
)


def loc_ao_giac(cues):
    """Bo may cau credit ma Whisper tu bia ra khi gap nhac hieu.

    Chi BO, khong bao gio sua chu. Cau nao bi bo deu in ra de con soi lai.
    """
    giu, bo = [], []
    for c in cues:
        t = c.text.strip().lower()
        if t and any(m in t for m in _AO_GIAC):
            bo.append(c)
        else:
            giu.append(c)
    if bo:
        print(f"  [asr] bo {len(bo)} cau ao giac (Whisper bia credit khi gap nhac):")
        for c in bo[:6]:
            print(f"          {c.start:7.1f}s  {c.text[:52]}")
        if len(bo) > 6:
            print(f"          ... va {len(bo) - 6} cau nua")
    return giu


def transcribe(
    audio: str | Path,
    out_srt: str | Path,
    model_size: str = "large-v3",
    language: str = "ja",
    device: str = "auto",
    compute_type: str = "auto",
    beam_size: int = 5,
    initial_prompt: str | None = DEFAULT_PROMPT,
    max_cue_dur: float = 8.0,
    max_cue_chars: int = 60,
    force: bool = False,
) -> List[Cue]:
    out_srt = Path(out_srt)
    if out_srt.exists() and not force:
        from .srtutil import read_srt
        cues = read_srt(out_srt)
        print(f"  [skip] đã có {out_srt.name} ({len(cues)} câu)")
        return cues

    model = load_model(model_size, device, compute_type)
    total = ffprobe_duration(audio)

    segments, info = model.transcribe(
        str(audio),
        # Rỗng -> None: Whisper tự dò. Đóng cứng "ja" như trước là video tiếng
        # Anh cũng bị ép nhận dạng thành tiếng Nhật, ra toàn chữ vô nghĩa.
        language=(language or None),
        beam_size=beam_size,
        # KHÔNG khoá temperature=0: cần fallback để thoát vòng lặp lải nhải
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        condition_on_previous_text=False,   # bắt buộc với audio nhiều tạp âm
        compression_ratio_threshold=2.4,    # chặn câu lặp vô hạn
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        initial_prompt=initial_prompt,
        word_timestamps=True,               # cần để cắt câu cho khớp thuyết minh
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=500,
            speech_pad_ms=200,
            threshold=0.5,
        ),
    )

    print(f"  [asr] ngôn ngữ={info.language} (p={info.language_probability:.2f}), "
          f"thời lượng={info.duration:.0f}s")

    cues: List[Cue] = []
    t0 = time.time()
    last_print = 0.0
    for seg in segments:  # generator -> việc nhận dạng chạy ở vòng lặp này
        if not seg.text.strip():
            continue
        words = getattr(seg, "words", None)
        if words:
            cues.extend(_split_by_words(words, max_cue_dur, max_cue_chars))
        else:
            cues.extend(_split_by_text(seg, max_cue_chars))

        if total and seg.end - last_print > 30:
            last_print = seg.end
            pct = min(100.0, seg.end / total * 100)
            el = time.time() - t0
            eta = el / max(pct, 0.1) * (100 - pct)
            sys.stdout.write(
                f"\r  [asr] {pct:5.1f}% | {len(cues)} câu | trôi {el/60:.1f}p | còn ~{eta/60:.1f}p   "
            )
            sys.stdout.flush()
    print()

    cues = loc_ao_giac(cues)
    write_srt(out_srt, cues)
    print(f"  [asr] xong: {out_srt} ({len(cues)} câu, {(time.time()-t0)/60:.1f} phút)")
    return cues
