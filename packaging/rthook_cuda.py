# -*- coding: utf-8 -*-
"""Runtime hook: nạp DLL CUDA đã gói kèm, chạy trước mọi code của app.

VÌ SAO CẦN FILE NÀY

`wrenautodub/cudafix.py` dò DLL bằng `import nvidia` rồi đọc `nvidia.__path__`.
Cách đó đúng khi chạy từ source, nhưng SAI trong bundle PyInstaller: package
`nvidia` bị nén vào kho lưu trữ nội bộ, `__path__` không còn trỏ tới thư mục
thật trên đĩa, còn DLL thì bị PyInstaller trải ra `_internal/nvidia/*/bin/`.
Nhánh dự phòng quét `sys.path` cũng không cứu được vì `sys.path` trong bundle
không chứa thư mục đó.

Triệu chứng nếu thiếu file này (đã dựng lại được thật, không phải suy đoán):

    !  DLL CUDA          không tìm thấy package nvidia-*
    !  Chạy thử CUDA     Library cublas64_12.dll is not found — sẽ tự lùi về CPU

App vẫn chạy, chỉ là rơi xuống CPU và chậm hàng chục lần. Đây là kiểu hỏng
âm thầm, không ai để ý cho tới khi phàn nàn "bản exe chậm hơn bản Python".

Hook này chỉ có tác dụng khi build với WREN_PACK_CUDA=1. Không bật thì thư mục
`_internal/nvidia` không tồn tại, hook thoát ngay và không làm gì.
"""

import os
import sys

_BIN_DIRS = ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc", "cufft", "curand")


def _nap_dll_cuda() -> None:
    if not sys.platform.startswith("win"):
        return

    # sys._MEIPASS chỉ tồn tại khi đang chạy trong bundle. Chạy từ source thì
    # cudafix.py lo, không đụng vào.
    goc = getattr(sys, "_MEIPASS", None)
    if not goc:
        return

    nvidia = os.path.join(goc, "nvidia")
    if not os.path.isdir(nvidia):
        return  # build không kèm CUDA — bình thường, không phải lỗi.

    for ten in _BIN_DIRS:
        thu_muc = os.path.join(nvidia, ten, "bin")
        if not os.path.isdir(thu_muc):
            continue

        # Cần CẢ HAI cách. add_dll_directory lo cho DLL mà Python nạp trực
        # tiếp; PATH lo cho DLL mà một DLL khác nạp tiếp (cublas64_12.dll
        # được ctranslate2.dll gọi, không phải Python gọi) — trường hợp này
        # add_dll_directory không phủ tới.
        try:
            os.add_dll_directory(thu_muc)
        except OSError:
            pass
        os.environ["PATH"] = thu_muc + os.pathsep + os.environ.get("PATH", "")

    # Chặn cudafix.enable_cuda_dlls() chạy lại và ghi đè: nó đặt cờ _done nội
    # bộ, nhưng ở đây chưa import được module đó (chưa tới lúc). Không sao —
    # cudafix chạy sau cũng chỉ thêm đường dẫn, không xoá cái đã thêm.


_nap_dll_cuda()
