# -*- coding: utf-8 -*-
"""Cấu hình chung cho bộ test tầng logic.

Bộ test này chỉ đụng tới tầng logic thuần Python: không import Qt, không gọi
mạng, không cần GPU, không cần ffmpeg. Nhờ vậy cả bộ chạy trong vài giây.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Console Windows mặc định là cp1252 khi bị pipe, gặp tên test tiếng Việt sẽ in
# ra \uXXXX không đọc được. Ép UTF-8 cho cả bốn luồng — pytest giữ tham chiếu
# tới file object nào thì reconfigure cũng đổi đúng object đó.
for _stream in (sys.__stdout__, sys.__stderr__, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:      # luồng bị pytest thay bằng đối tượng không reconfigure được
        pass

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
