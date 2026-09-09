# -*- coding: utf-8 -*-
"""Sinh bảng ký tự cho model nhận dạng tiếng Việt.

PP-OCR đọc bảng này để biết model có bao nhiêu lớp đầu ra. Model Latin có sẵn
chỉ 185 ký tự và thiếu 50/67 nguyên âm có dấu của tiếng Việt — thiếu hẳn
ă ơ ư cùng toàn bộ dấu hỏi ngã nặng. Đó là lý do phải huấn luyện lại phần đầu.

Chạy: python bang_ky_tu.py  ->  ghi ra chars_vi.txt
"""

from pathlib import Path

# Nguyên âm tiếng Việt đầy đủ, viết thường. Xếp theo nhóm để dễ soát bằng mắt.
NGUYEN_AM = (
    "aàáảãạ" "ăằắẳẵặ" "âầấẩẫậ"
    "eèéẻẽẹ" "êềếểễệ"
    "iìíỉĩị"
    "oòóỏõọ" "ôồốổỗộ" "ơờớởỡợ"
    "uùúủũụ" "ưừứửữự"
    "yỳýỷỹỵ"
)
PHU_AM = "bcdđghklmnpqrstvx"
SO = "0123456789"

# Dấu câu hay gặp trong phụ đề phim. Gồm cả gạch ngang dài và ngoặc kép cong
# vì bản dịch hay dùng, model không học thì nó đoán bừa thành ký tự khác.
DAU_CAU = " !\"#$%&'()*+,-./:;<=>?@[]_`{|}~" "–—‘’“”…°₫"


def bang() -> list:
    ky_tu = []
    for c in NGUYEN_AM + PHU_AM:
        ky_tu.append(c)
        if c.upper() != c:
            ky_tu.append(c.upper())
    # chữ Latin còn lại (f j w z) — tên riêng và từ mượn vẫn dùng
    for c in "fjwz":
        ky_tu += [c, c.upper()]
    ky_tu += list(SO) + list(DAU_CAU)

    ra, da_co = [], set()
    for c in ky_tu:
        if c not in da_co:
            da_co.add(c)
            ra.append(c)
    return ra


if __name__ == "__main__":
    ch = bang()
    p = Path(__file__).with_name("chars_vi.txt")
    p.write_text("\n".join(ch) + "\n", encoding="utf-8")
    co_dau = sum(1 for c in ch if c.lower() not in "abcdefghijklmnopqrstuvwxyz0123456789"
                 and c.isalpha())
    print(f"{len(ch)} ký tự -> {p.name}")
    print(f"  trong đó {co_dau} chữ có dấu (model Latin sẵn có chỉ 17)")
