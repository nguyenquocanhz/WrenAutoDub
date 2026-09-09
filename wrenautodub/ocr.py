# -*- coding: utf-8 -*-
"""Đọc phụ đề NUNG SẴN trên hình bằng OCR, thay cho nhận dạng tiếng nói.

Nhiều bản phim tải về đã có phụ đề dán chết vào khung hình. Khi đó chữ gốc
nằm ngay trước mắt, mà bắt Whisper đoán lại từ âm thanh là tự làm khó mình:
đo trên một phim thật, Whisper đúng 2/4 câu mẫu, còn OCR đúng cả 4 — kể cả
câu Whisper nghe sót ba chữ đầu và câu nó nghe sai hẳn.

Cách làm, học từ VideoSubFinder:

1. Rút dải phụ đề ở độ phân giải THẤP, 2.5 khung mỗi giây. Cả phim 15 phút
   chỉ mất 20 giây.
2. Ngưỡng hoá lấy nét chữ sáng rồi mới so hai khung liền nhau. So thẳng ảnh
   xám là hỏng: hình nền phía sau chữ cũng động, đo được 1626/2302 khung bị
   coi là "đổi" trong khi thật ra chỉ có ~150 câu.
3. Chỗ nào mặt nạ chữ đổi mới gọi OCR. Nhờ vậy chỉ chạy OCR ~177 lần thay vì
   2302 lần — 5 phút thay vì hơn một tiếng.

Chỉ dùng RapidOCR đã cài sẵn (ONNX, chạy CPU). Model đi kèm nhận tiếng Trung
và tiếng Anh rất tốt. KHÔNG đọc được tiếng Việt có dấu: model Latin của
PP-OCRv3 chỉ có 17/67 ký tự có dấu, thiếu hẳn ă ơ ư và dấu hỏi/ngã/nặng.
Muốn đọc luôn dòng tiếng Việt thì phải huấn luyện model riêng.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from .srtutil import Cue

FPS_QUET = 4.0          # số khung lấy ra mỗi giây để dò
                        # 2.5 bỏ sót câu hiện dưới 0.4 giây (vùng thoại
                        # dày chỉ ra 92 đoạn, lên 4.0 thì 98); 5.0 không
                        # thêm được gì nữa nên dừng ở đây
W_NHO, H_NHO = 480, 42  # cỡ dải phụ đề sau khi thu nhỏ
NGUONG_SANG = 230       # nét chữ phụ đề là trắng gắt, nền phim hiếm khi tới đây
DAC_TOI_THIEU = 0.006   # tỉ lệ điểm sáng để coi là "có chữ"
NGUONG_GOP = 0.035      # mặt nạ đổi quá mức này thì tính là câu mới
NGAN = 12               # dải đen ngăn giữa hai ảnh xếp chồng, pixel
LO = 6                  # số đoạn xếp chồng vào một lần gọi OCR;
                        # đúng bằng rec_batch_num mặc định của RapidOCR


def _co_numpy():
    try:
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def _rut_dai(video: str | Path, y: int, cao: int,
             ss: float = 0.0, dai: float = 0.0,
             h_nho: int = 0) -> Tuple[object, int]:
    """Rút dải ngang [y, y+cao) ở cỡ nhỏ, trả về mảng xám.

    `ss`/`dai` để chỉ lấy một khúc — lúc DÒ thì không cần cả phim.
    """
    import numpy as np

    cmd = ["ffmpeg", "-v", "error"]
    if ss > 0:
        cmd += ["-ss", f"{ss:.2f}"]
    cmd += ["-i", str(video)]
    if dai > 0:
        cmd += ["-t", f"{dai:.2f}"]
    # Nén dọc quá tay là hỏng: dải cao 311px ép xuống 42 hàng (7,4 lần) làm
    # nét chữ mảnh bị bình quân hoá mất, hồ sơ hàng tụt còn 0.03 và không dò
    # ra biên chữ nữa. Giữ tỉ lệ nén dọc quanh 4 lần.
    hn = h_nho or H_NHO
    cmd += ["-vf",
            f"fps={FPS_QUET},crop=iw:{cao}:0:{y},"
            f"scale={W_NHO}:{hn},format=gray",
            "-f", "rawvideo", "-"]
    r = subprocess.run(cmd, capture_output=True)
    o = W_NHO * hn
    n = len(r.stdout) // o
    if n == 0:
        return None, 0
    return np.frombuffer(r.stdout[:n * o], np.uint8).reshape(n, hn, W_NHO), n


def do_vung(video: str | Path, cao_video: int = 0) -> Optional[Tuple[int, int]]:
    """Phim này có phụ đề nung sẵn không, và nằm ở dải nào?

    Trả về (y, cao) theo pixel của phim gốc, hoặc None nếu không thấy.
    Thử vài dải ở nửa dưới khung hình vì phụ đề gần như luôn nằm đó.
    """
    if not _co_numpy():
        return None
    import numpy as np

    h = cao_video or _cao(video)
    if h <= 0:
        return None
    tong = _thoi_luong(video)

    # ĐO biên thật của chữ thay vì thử vài cửa sổ rồi chấm điểm. Cách chấm
    # điểm chọn ra dải điểm cao nhất, mà dải thấp nhất thường điểm cao nhất —
    # nó cắt ngang qua dòng chữ trên và OCR đọc ra 0 dòng. Đã dính đúng vậy.
    y0 = int(h * 0.62)                      # soi cả phần dưới khung hình
    hn = max(H_NHO, (h - y0) // 4)          # giữ nén dọc ~4 lần
    a, n = _rut_dai(video, y0, h - y0,
                    ss=max(0.0, tong * 0.35), dai=min(180.0, tong * 0.25),
                    h_nho=hn)
    if a is None or n < 20:
        return None

    m = a > NGUONG_SANG
    # Xét theo HÀNG ĐẬM NHẤT, không phải trung bình cả dải: dải càng cao thì
    # trung bình càng loãng, cùng một dòng chữ mà dải 310px cho mật độ chỉ
    # bằng nửa dải 170px — ngưỡng cố định sẽ trượt.
    co = m.mean(axis=2).max(axis=1) > 0.04
    if float(co.mean()) < 0.12:
        # Dưới 12% thời lượng có chữ thì gần như chắc không có phụ đề nung;
        # mấy điểm sáng lác đác chỉ là cảnh sáng hoặc watermark.
        return None

    # Hàng nào thường xuyên có nét chữ? Chỉ tính trên khung ĐANG có chữ.
    hang = m[co].mean(axis=(0, 2))          # H_NHO giá trị, 0..1
    nguong = max(0.02, hang.max() * 0.18)
    idx = [i for i, v in enumerate(hang) if v >= nguong]
    if not idx:
        return None

    # Đổi từ toạ độ ảnh đã thu nhỏ về pixel thật, nới thêm biên cho chắc.
    ty = (h - y0) / hn
    # Nới rộng tay. Cắt sát biên chữ là OCR đọc ra 0 dòng — đo được: dải
    # 670..731 (sát) không đọc được gì, còn 646..816 đọc đủ hai dòng. Chênh
    # có 24px ở mép trên. Mép dưới thì kéo thẳng tới đáy khung, không mất gì.
    tren = max(0, y0 + int(idx[0] * ty) - int(h * 0.03))
    tren = min(tren, h - 60)
    return tren, h - tren


def _cao(video: str | Path) -> int:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=60)
        return int((r.stdout or "0").strip() or 0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0


def _thoi_luong(video: str | Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=60)
        return float((r.stdout or "0").strip() or 0.0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0.0


def _doan(a, n: int) -> List[Tuple[int, int]]:
    """Các đoạn khung liên tiếp cùng hiển thị một câu -> [(đầu, cuối)]."""
    import numpy as np

    m = (a > NGUONG_SANG)
    co = m.mean(axis=(1, 2)) > DAC_TOI_THIEU
    mi = m.astype(np.int8)

    ra, dau = [], -1
    for i in range(n):
        if not co[i]:
            if dau >= 0:
                ra.append((dau, i - 1))
                dau = -1
            continue
        if dau < 0:
            dau = i
            continue
        # So với khung ĐẦU ĐOẠN, không phải khung ngay trước. So khung liền
        # nhau thì hai câu khác nhau mà bố cục giống nhau chỉ chênh chút một,
        # lọt lưới và bị gộp làm một — đo được: đoạn thoại dày ra 78 câu
        # trong khi thực tế có khoảng 113.
        if float(np.abs(mi[i] - mi[dau]).mean()) > NGUONG_GOP:
            ra.append((dau, i - 1))
            dau = i
    if dau >= 0:
        ra.append((dau, n - 1))
    return [(x, y) for x, y in ra if y >= x]


def _khung(video: str | Path, t: float, y: int, cao: int):
    """Một khung hình ở giây t, chỉ lấy dải phụ đề, giữ nguyên độ phân giải."""
    import numpy as np

    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"crop=iw:{cao}:0:{y}",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        capture_output=True)
    if not r.stdout:
        return None
    rong = len(r.stdout) // (cao * 3)
    if rong <= 0:
        return None
    return np.frombuffer(r.stdout[:cao * rong * 3], np.uint8).reshape(cao, rong, 3)


def _khung_hang_loat(video, moc_giay, y, cao, luong: int = 4):
    """Lấy nhiều khung, seek SONG SONG.

    Đã thử gộp thành một lệnh ffmpeg với filter `select='eq(n,a)+eq(n,b)+...'`
    để chỉ giải mã một lần: với 250 điều kiện thì ffmpeg đổ
    "Cannot allocate memory" — biểu thức quá lớn cho bộ phân tích của nó.

    Seek riêng từng khung mất 273 ms, nhưng các tiến trình ffmpeg độc lập nhau
    nên chạy song song được. Bốn luồng là vừa: nhiều hơn thì tranh ổ đĩa.
    """
    from concurrent.futures import ThreadPoolExecutor

    ra = {}
    if not moc_giay:
        return ra

    def mot(t):
        return t, _khung(video, t, y, cao)

    with ThreadPoolExecutor(max_workers=luong) as ex:
        for t, im in ex.map(mot, moc_giay):
            if im is not None:
                ra[t] = im
    return ra


def _rong(video) -> int:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=60)
        return int((r.stdout or "0").strip() or 0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0


def quet(video: str | Path, vung: Tuple[int, int],
         lang_goc: str = "zh") -> List[Cue]:
    """Quét cả phim, trả về các câu đọc được từ phụ đề nung.

    `lang_goc` chỉ dùng để chọn dòng nào khi khung có nhiều dòng chữ.
    """
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    y, cao = vung
    a, n = _rut_dai(video, y, cao)
    if a is None:
        return []
    doan = _doan(a, n)
    print(f"  [ocr] dải phụ đề y={y} cao={cao} | {n} khung | "
          f"{len(doan)} đoạn cần đọc")

    moc = [round((i0 + i1) / 2.0 / FPS_QUET, 2) for i0, i1 in doan]
    t0 = time.time()
    khung = _khung_hang_loat(video, sorted(set(moc)), y, cao)
    print(f"  [ocr] lấy {len(khung)} khung trong {time.time()-t0:.0f}s")

    ocr = RapidOCR()
    cues: List[Cue] = []
    for b0 in range(0, len(doan), LO):
        lo = list(range(b0, min(b0 + LO, len(doan))))
        anh, mep_k = [], []
        for k in lo:
            im = khung.get(moc[k])
            if im is None:
                continue
            # Bỏ hai bên: chữ luôn nằm giữa, mà ảnh quá rộng thì bộ dò co nhỏ
            # ảnh lại làm chữ teo mất — đã đo, để nguyên bề ngang đọc ra 0 dòng.
            g = im[:, int(im.shape[1] * 0.18):int(im.shape[1] * 0.82)]
            mep_k.append((0, g.shape[0], k))
            anh.append(g)
        if not anh:
            continue

        # XẾP CHỒNG cả lô vào một ảnh rồi gọi OCR MỘT lần. Cấu hình RapidOCR
        # có rec_batch_num=6, gọi từng ảnh một là bỏ phí. Đo được: 6 ảnh gọi
        # riêng hết 19,1 giây, xếp chồng còn 2,5 giây — nhanh 7,6 lần.
        # Chèn dải đen giữa hai ảnh: không có thì bộ dò nối liền dòng cuối
        # ảnh trên với dòng đầu ảnh dưới, mất câu ở chỗ giáp ranh.
        W = max(x.shape[1] for x in anh)
        mep = []
        oy = 0
        for k, x in zip([m for _o, _h, m in mep_k], anh):
            mep.append((oy, x.shape[0], k))
            oy += x.shape[0] + NGAN
        chong = np.zeros((oy, W, 3), np.uint8)
        for (o2, _h, _k), x in zip(mep, anh):
            chong[o2:o2 + x.shape[0], :x.shape[1]] = x
        try:
            kq, _ = ocr(chong)
        except Exception:
            kq = None

        # Chia kết quả về từng đoạn theo toạ độ dọc của hộp chữ
        theo = {k: [] for _o, _h, k in mep}
        for it in (kq or []):
            hop = it[0]
            try:
                ym = sum(pt[1] for pt in hop) / len(hop)
            except Exception:
                continue
            for oy, h, k in mep:
                if oy <= ym < oy + h:
                    t = str(it[1]).strip()
                    if t:
                        theo[k].append(t)
                    break

        for k in lo:
            dong = theo.get(k) or []
            if not dong:
                continue
            txt = _chon_dong(dong, lang_goc)
            if not txt:
                continue
            i0, i1 = doan[k]
            cues.append(Cue(i0 / FPS_QUET, (i1 + 1) / FPS_QUET, txt))

        el = time.time() - t0
        xong = min(b0 + LO, len(doan))
        con = el / max(xong, 1) * (len(doan) - xong)
        sys.stdout.write(f"\r  [ocr] {xong}/{len(doan)} đoạn | "
                         f"{len(cues)} câu | còn ~{con/60:.1f}p   ")
        sys.stdout.flush()
    print()
    cues = _don(cues)
    print(f"  [ocr] xong: {len(cues)} câu trong {(time.time()-t0)/60:.1f} phút")
    return cues


def _fps(video) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0",
             str(video)], capture_output=True, text=True, timeout=60)
        t = (r.stdout or "").strip()
        if "/" in t:
            a, b = t.split("/")
            return float(a) / max(1.0, float(b))
        return float(t or 0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0.0


def _chon_dong(dong: List[str], lang: str) -> str:
    """Khung song ngữ thì chọn đúng dòng ngôn ngữ gốc.

    Phim hardsub hay có hai dòng: bản dịch ở trên, chữ gốc ở dưới. Chọn theo
    tỉ lệ chữ Hán chứ không theo thứ tự, vì thứ tự mỗi bản phát hành một khác.
    """
    def han(s: str) -> float:
        if not s:
            return 0.0
        return sum(1 for c in s if "一" <= c <= "鿿") / len(s)

    if not lang:
        # Không biết ngôn ngữ nguồn. Nhưng đích LUÔN là tiếng Việt, nên dòng
        # nguồn là dòng KHÔNG phải tiếng Việt — nhận ra bằng dấu đặc trưng.
        # Có chữ Hán thì chắc chắn đó là dòng gốc.
        if any(han(x) > 0.15 for x in dong):
            return max(dong, key=han)
        return min(dong, key=_viet)

    if lang.startswith("zh") or lang in ("ja", "ko", "yue"):
        # Kiểm cả khi chỉ có MỘT dòng: credit cuối phim hay ra đúng một mảnh
        # rác kiểu "451" hoặc "AZTEC", thoát sớm là lọt.
        tot = max(dong, key=han)
        # Không dòng nào có chữ Hán mà phim lại là tiếng Hán -> đây không phải
        # lời thoại. Gần như luôn là phần credit cuối phim: đo trên phim thật,
        # một khung ở giây 902 trả về 7 dòng vụn kiểu "oodacgap", "d 38.039.14",
        # "TIN DUNG". Lọc theo ĐIỂM TIN CẬY không ăn thua — rác đó đạt tới
        # 0.79, cao hơn nhiều câu thoại thật.
        return tot if han(tot) > 0.15 else ""
    if len(dong) == 1:
        return dong[0]
    return min(dong, key=han)


_VIET = set("ăâđêôơưĂÂĐÊÔƠƯ"
            "áàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩị"
            "óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
_VIET |= {c.upper() for c in _VIET}


def _viet(s: str) -> float:
    """Tỉ lệ ký tự có dấu tiếng Việt — để nhận ra dòng nào là bản dịch."""
    if not s:
        return 0.0
    return sum(1 for c in s if c in _VIET) / len(s)


def _don(cues: List[Cue], khe: float = 0.25) -> List[Cue]:
    """Gộp câu liền nhau trùng chữ, bỏ câu quá ngắn."""
    ra: List[Cue] = []
    for c in cues:
        if ra and c.text == ra[-1].text and c.start - ra[-1].end <= khe:
            ra[-1].end = c.end
            continue
        ra.append(c)
    return [c for c in ra if c.end - c.start >= 0.2 and c.text.strip()]
