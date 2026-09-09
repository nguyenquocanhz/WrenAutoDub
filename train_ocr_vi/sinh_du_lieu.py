# -*- coding: utf-8 -*-
"""Sinh ảnh chữ tiếng Việt để huấn luyện model nhận dạng.

Không dùng ảnh chữ chung chung. Model này sẽ đọc PHỤ ĐỀ PHIM, nên dữ liệu
phải giống hệt phụ đề phim: chữ trắng viền đen, nằm giữa, đè lên khung hình
thật đang chuyển động. Huấn luyện bằng chữ đen trên nền trắng rồi đem đọc
phụ đề là lệch miền, model sẽ đoán bừa.

Nguồn chữ trộn hai loại:
  - câu phụ đề THẬT (lấy từ vi.srt đã dịch) — cho đúng văn phong, độ dài
  - âm tiết ghép NGẪU NHIÊN — để mọi ký tự có dấu đều xuất hiện đủ nhiều.
    Chỉ dùng câu thật thì mấy chữ hiếm như "ỡ" "ẵ" "ự" xuất hiện vài lần,
    model không học nổi.

Nguồn nền lấy thẳng từ file phim: khung hình thật có đủ sáng tối, nhiễu,
chuyển động — thứ mà nền trơn không có.

Chạy:
    python sinh_du_lieu.py --video "phim.mp4" --srt "vi.srt" --so 200000
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from pathlib import Path
from typing import List

# ---- cấu trúc âm tiết tiếng Việt, đủ để ghép ra chữ trông như thật ----
DAU_AM = ["", "b", "c", "ch", "d", "đ", "g", "gh", "gi", "h", "k", "kh", "l",
          "m", "n", "ng", "ngh", "nh", "p", "ph", "qu", "r", "s", "t", "th",
          "tr", "v", "x"]
VAN = ["a", "ai", "an", "ang", "anh", "ao", "ap", "at", "ac", "ach",
       "ăm", "ăn", "ăng", "ăp", "ăt", "âm", "ân", "âng", "âp", "ât", "âu", "ây",
       "e", "em", "en", "eo", "ep", "et", "ê", "êm", "ên", "êp", "êt", "êu",
       "i", "ia", "im", "in", "inh", "ip", "it", "iu",
       "o", "oa", "oai", "oan", "oang", "oc", "oi", "om", "on", "ong", "op", "ot",
       "ô", "ôi", "ôm", "ôn", "ông", "ôp", "ôt", "ơ", "ơi", "ơm", "ơn", "ơp", "ơt",
       "u", "ua", "uc", "ui", "um", "un", "ung", "uôi", "uôn", "uông", "up", "ut",
       "ư", "ưa", "ưc", "ưi", "ưng", "ươi", "ương", "ươu", "ưt", "ưu",
       "y", "yên", "yêu"]
# dấu thanh: (không dấu, huyền, sắc, hỏi, ngã, nặng)
THANH = [
    {},
    {"a": "à", "ă": "ằ", "â": "ầ", "e": "è", "ê": "ề", "i": "ì", "o": "ò",
     "ô": "ồ", "ơ": "ờ", "u": "ù", "ư": "ừ", "y": "ỳ"},
    {"a": "á", "ă": "ắ", "â": "ấ", "e": "é", "ê": "ế", "i": "í", "o": "ó",
     "ô": "ố", "ơ": "ớ", "u": "ú", "ư": "ứ", "y": "ý"},
    {"a": "ả", "ă": "ẳ", "â": "ẩ", "e": "ẻ", "ê": "ể", "i": "ỉ", "o": "ỏ",
     "ô": "ổ", "ơ": "ở", "u": "ủ", "ư": "ử", "y": "ỷ"},
    {"a": "ã", "ă": "ẵ", "â": "ẫ", "e": "ẽ", "ê": "ễ", "i": "ĩ", "o": "õ",
     "ô": "ỗ", "ơ": "ỡ", "u": "ũ", "ư": "ữ", "y": "ỹ"},
    {"a": "ạ", "ă": "ặ", "â": "ậ", "e": "ẹ", "ê": "ệ", "i": "ị", "o": "ọ",
     "ô": "ộ", "ơ": "ợ", "u": "ụ", "ư": "ự", "y": "ỵ"},
]


def am_tiet(rnd: random.Random) -> str:
    """Một âm tiết ghép ngẫu nhiên, có bỏ dấu đúng chỗ nguyên âm."""
    v = rnd.choice(VAN)
    b = rnd.choice(THANH)
    if b:
        for i, c in enumerate(v):
            if c in b:
                v = v[:i] + b[c] + v[i + 1:]
                break
    s = rnd.choice(DAU_AM) + v
    return s.capitalize() if rnd.random() < 0.12 else s


def cau_ngau_nhien(rnd: random.Random) -> str:
    n = rnd.randint(2, 9)
    s = " ".join(am_tiet(rnd) for _ in range(n))
    if rnd.random() < 0.35:
        s += rnd.choice([".", ",", "!", "?", "...", ""])
    return s


def doc_srt(p: Path) -> List[str]:
    """Lấy các dòng lời thoại thật trong file .srt."""
    if not p.exists():
        return []
    ra = []
    for d in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        d = d.strip()
        if not d or d.isdigit() or "-->" in d:
            continue
        ra.append(d)
    return ra


def lay_nen(video: Path, so: int, cao: int, rong: int, thu_muc: Path) -> List[Path]:
    """Trích `so` khung hình rải đều cả phim làm nền."""
    import numpy as np

    thu_muc.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    dai = float((r.stdout or "0").strip() or 0)
    if dai <= 0:
        return []
    ra = []
    # Lấy một lượt bằng fps thay vì seek từng khung: seek `so` lần vào file
    # vài trăm MB rất chậm, đã đo trên bước OCR.
    fps = max(0.05, so / dai)
    # CẮT một dải ở NỬA TRÊN khung hình, không ép dẹt cả khung. Hai lý do:
    #  - phim nguồn có phụ đề nung ở đáy, lấy cả khung là phụ đề gốc lọt vào
    #    nền, model học nhầm rằng nền hay có chữ mờ
    #  - ép 1920x816 xuống 1248x144 làm méo hẳn kết cấu ảnh, không còn giống
    #    nền thật mà model sẽ gặp
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vf",
         f"fps={fps},crop=iw:ih*0.5:0:ih*0.08,scale={rong}:{cao}",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True)
    o = rong * cao * 3
    n = len(p.stdout) // o
    import cv2
    for i in range(min(n, so)):
        a = np.frombuffer(p.stdout[i*o:(i+1)*o], np.uint8).reshape(cao, rong, 3)
        f = thu_muc / f"nen_{i:05d}.jpg"
        cv2.imwrite(str(f), a)
        ra.append(f)
    return ra


def ve(text: str, nen, fonts: List[Path], rnd: random.Random):
    """Vẽ một dòng phụ đề lên nền, trả về ảnh đã cắt sát chữ."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    im = Image.fromarray(nen[:, :, ::-1]).convert("RGB")
    W, H = im.size
    cao_chu = rnd.randint(int(H * 0.34), int(H * 0.62))
    try:
        ft = ImageFont.truetype(str(rnd.choice(fonts)), cao_chu)
    except Exception:
        return None, None

    d = ImageDraw.Draw(im)
    hop = d.textbbox((0, 0), text, font=ft)
    tw, th = hop[2] - hop[0], hop[3] - hop[1]
    if tw <= 4 or tw > W * 3:
        return None, None
    if tw > W - 8:                      # chữ dài hơn nền thì nới nền ra
        moi = Image.new("RGB", (tw + 24, H))
        for x in range(0, tw + 24, W):
            moi.paste(im, (x, 0))
        im = moi
        W = im.size[0]
        d = ImageDraw.Draw(im)

    x = (W - tw) // 2 + rnd.randint(-6, 6)
    y = (H - th) // 2 - hop[1] + rnd.randint(-3, 3)

    # Phụ đề phim: chữ trắng, viền đen dày. Thỉnh thoảng hơi ngả vàng.
    mau = (255, 255, 255) if rnd.random() < 0.85 else (
        rnd.randint(235, 255), rnd.randint(225, 255), rnd.randint(180, 240))
    vien = max(2, cao_chu // 12)
    d.text((x, y), text, font=ft, fill=mau,
           stroke_width=vien, stroke_fill=(0, 0, 0))

    a = np.array(im)[:, :, ::-1].copy()
    # cắt sát chữ, chừa lề như lúc OCR thật cắt dải phụ đề
    le = rnd.randint(4, 14)
    x0 = max(0, x - le)
    x1 = min(a.shape[1], x + tw + le)
    return a[:, x0:x1], text


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh ảnh chữ tiếng Việt cho PP-OCR")
    ap.add_argument("--video", required=True, help="phim lấy khung hình làm nền")
    ap.add_argument("--srt", default="", help="file .srt lấy câu thoại thật")
    ap.add_argument("--so", type=int, default=50000, help="số ảnh cần sinh")
    ap.add_argument("--ra", default="data_vi", help="thư mục kết quả")
    ap.add_argument("--cao", type=int, default=48, help="chiều cao ảnh (PP-OCR dùng 48)")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as e:
        print(f"thiếu thư viện: {e}")
        return 1

    rnd = random.Random(a.seed)
    ra = Path(a.ra)
    (ra / "anh").mkdir(parents=True, exist_ok=True)

    fonts = _fonts_viet()
    if not fonts:
        print("không tìm thấy font nào đủ ký tự tiếng Việt")
        return 1
    print(f"  {len(fonts)} font có đủ dấu tiếng Việt")

    cau_that = doc_srt(Path(a.srt)) if a.srt else []
    print(f"  {len(cau_that)} câu thoại thật làm mẫu")

    print("  đang lấy khung hình nền...")
    nen = lay_nen(Path(a.video), min(2000, a.so // 8 + 50),
                  a.cao * 3, a.cao * 26, ra / "nen")
    if not nen:
        print("không lấy được khung hình nào")
        return 1
    print(f"  {len(nen)} khung nền")

    import cv2
    nhan = []
    i = 0
    while i < a.so:
        txt = (rnd.choice(cau_that) if cau_that and rnd.random() < 0.35
               else cau_ngau_nhien(rnd))
        txt = txt.strip()
        if not txt or len(txt) > 60:
            continue
        b = cv2.imread(str(rnd.choice(nen)))
        if b is None:
            continue
        im, lab = ve(txt, b, fonts, rnd)
        if im is None or im.shape[1] < 16:
            continue
        im = cv2.resize(im, (max(16, int(im.shape[1] * a.cao / im.shape[0])), a.cao))
        f = f"anh/{i:07d}.jpg"
        cv2.imwrite(str(ra / f), im, [cv2.IMWRITE_JPEG_QUALITY, rnd.randint(72, 96)])
        nhan.append(f"{f}\t{lab}")
        i += 1
        if i % 5000 == 0:
            sys.stdout.write(f"\r  {i}/{a.so}   ")
            sys.stdout.flush()
    print()

    rnd.shuffle(nhan)
    k = max(1, len(nhan) // 50)
    (ra / "nhan_val.txt").write_text("\n".join(nhan[:k]) + "\n", encoding="utf-8")
    (ra / "nhan_train.txt").write_text("\n".join(nhan[k:]) + "\n", encoding="utf-8")
    print(f"  xong: {len(nhan)-k} ảnh train, {k} ảnh val -> {ra}")
    return 0


def _fonts_viet() -> List[Path]:
    """Font có đủ 134 chữ có dấu. Font thiếu glyph sẽ vẽ ra ô vuông rỗng."""
    import glob
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return [Path(p) for p in glob.glob(r"C:\Windows\Fonts\arial*.ttf")]

    can = set()
    for c in ("ăâđêôơư" "ắằẳẵặấầẩẫậ" "ếềểễệ" "ốồổỗộớờởỡợ" "ứừửữự" "ỳỷỹỵ"):
        can.add(ord(c)); can.add(ord(c.upper()))
    ra = []
    for f in glob.glob(r"C:\Windows\Fonts\*.tt*"):
        try:
            t = TTFont(f, fontNumber=0, lazy=True)
            cm = set()
            for tb in t["cmap"].tables:
                cm |= set(tb.cmap.keys())
            t.close()
        except Exception:
            continue
        if can <= cm:
            ra.append(Path(f))
    return ra


if __name__ == "__main__":
    raise SystemExit(main())
