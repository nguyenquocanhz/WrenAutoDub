# -*- coding: utf-8 -*-
"""Thang màu dùng chung cho cả app — một nguồn duy nhất.

Trước đây mỗi nơi tự khai màu: `dark_palette()` dùng #202124 / #18191c /
#2d2f33, còn thanh thời gian dùng #141518 / #1e2024 / #303338. Không bậc nào
khớp bậc nào, nên panel đặt cạnh nhau trôi vào nhau — không nhìn ra cái nào
nằm trên cái nào.

Cách tổ chức học từ CapCut (365 biến CSS, xem D:/CapCutLearn): tầng gốc chỉ
là giá trị, tầng vai trò trỏ vào tầng gốc. Đổi diện mạo thì sửa tầng vai trò,
không đi lùng mã màu trong các hàm vẽ.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette

# ============================================================ TẦNG 1: giá trị
# Bảy bậc nền, từ sâu nhất tới nổi nhất. Mọi bậc NGẢ XANH (kênh blue cao hơn
# red/green vài đơn vị) — xám trung tính làm giao diện tối trông bẹt và bẩn.
# Bốn bậc là không đủ: panel lồng nhau cần ít nhất ba mức phân biệt được, cộng
# viền và đường kẻ.
NEN_0 = QColor(14, 15, 18)      # #0e0f12  sâu nhất — khung video, vùng lõm
NEN_1 = QColor(20, 21, 24)      # #141518  nền rãnh thời gian
NEN_2 = QColor(25, 27, 31)      # #191b1f  ô danh sách, cột nhãn
NEN_3 = QColor(30, 32, 36)      # #1e2024  nền một lớp, thẻ
NEN_4 = QColor(38, 40, 46)      # #26282e  nền cửa sổ, mặt panel
NEN_5 = QColor(48, 51, 56)      # #303338  nút, đường kẻ
NEN_6 = QColor(58, 60, 66)      # #3a3c42  viền rõ, hover

CHU_0 = QColor(252, 250, 238)   # sáng nhất — thứ đang chọn
CHU_1 = QColor(226, 228, 232)   # chữ chính
CHU_2 = QColor(150, 154, 160)   # chữ phụ
CHU_3 = QColor(110, 114, 120)   # chữ mờ, đã tắt

LAM_1 = QColor(72, 132, 196)    # màu dữ liệu: lớp phụ đề
LAM_2 = QColor(108, 174, 240)
LUC_1 = QColor(96, 176, 132)    # lớp thuyết minh
DO_1 = QColor(232, 84, 76)      # đầu phát
CAM_1 = QColor(214, 132, 52)    # tăng tốc
TIM_1 = QColor(150, 112, 210)   # giảm tốc
VANG_1 = QColor(250, 230, 120)  # nhát cắt
NHAN_1 = QColor(72, 132, 214)   # màu nhấn: nút chính, vùng chọn


def pha(c: QColor, a: float) -> QColor:
    """Bản trong suốt của một màu. Đây là chỗ Qt tiện hơn CSS.

    CapCut phải lưu thêm bộ ba RGB (`--white-0-rgb: 250,250,250`) mới chế được
    `rgba(var(--white-0-rgb), .12)`, vì CSS không tách được kênh từ mã hex.
    QColor cho lấy thẳng, nên chỉ cần một nguồn màu duy nhất.
    """
    return QColor(c.red(), c.green(), c.blue(), int(max(0.0, min(1.0, a)) * 255))


# ========================================================== TẦNG 2: vai trò
CUA_SO = NEN_4          # nền cửa sổ
PANEL = NEN_3           # mặt panel đặt trên nền cửa sổ
O_NHAP = NEN_2          # ô nhập, danh sách — lõm xuống so với panel
LOM_SAU = NEN_0         # khung xem video
NUT = NEN_5
VIEN = NEN_6


def dark_palette() -> QPalette:
    """Bảng màu Qt dựng từ đúng thang trên, không khai màu riêng nữa."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, CUA_SO)
    p.setColor(QPalette.ColorRole.WindowText, CHU_1)
    p.setColor(QPalette.ColorRole.Base, O_NHAP)
    p.setColor(QPalette.ColorRole.AlternateBase, PANEL)
    p.setColor(QPalette.ColorRole.Text, CHU_1)
    p.setColor(QPalette.ColorRole.Button, NUT)
    p.setColor(QPalette.ColorRole.ButtonText, CHU_1)
    p.setColor(QPalette.ColorRole.Highlight, NHAN_1)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.ToolTipBase, O_NHAP)
    p.setColor(QPalette.ColorRole.ToolTipText, CHU_1)
    p.setColor(QPalette.ColorRole.Mid, VIEN)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, CHU_3)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, CHU_3)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, CHU_3)
    return p
