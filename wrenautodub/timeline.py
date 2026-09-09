# -*- coding: utf-8 -*-
"""Dòng thời gian nhiều lớp: phụ đề, hình, thuyết minh, tốc độ, hiệu ứng.

Lớp Hình vẽ bằng filmstrip trích sẵn, lớp Thuyết minh vẽ sóng âm — nhìn một
cái là biết đoạn nào có tiếng, đoạn nào im. Zoom bằng Ctrl+lăn chuột, cuộn
bằng lăn chuột thường.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from PyQt6.QtCore import QLine, QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from .edit import BLUR, DELOGO, LOGO, Region
from .media_strip import FilmStrip, Waveform
from .clips import Clip, ensure, layout as clip_layout, ripple_close
from .timing import Speed, normalize

RULER_H = 22
LEFT_W = 96
EDGE = 5

LANES = [("Phụ đề", 24), ("Hình", 46), ("Thuyết minh", 34),
         ("Tốc độ", 22), ("Hiệu ứng", 20)]
L_SUB, L_VIDEO, L_DUB, L_SPEED, L_FX = range(5)
LANE_GAP = 3
LANE_MIN = 16       # chieu cao toi thieu cua mot lop, pixel
LANE_EDGE = 4       # be rong vung bat de keo bien giua hai lop

C_BG = QColor(20, 21, 24)
C_LANE = QColor(30, 32, 36)
C_GRID = QColor(48, 51, 56)
C_TEXT = QColor(150, 154, 160)
C_HEAD = QColor(232, 84, 76)
C_DUB = QColor(96, 176, 132)
C_SUBCHIP = QColor(72, 132, 196)
C_SUBCHIP_ON = QColor(108, 174, 240)
C_FAST = QColor(214, 132, 52)
C_SLOW = QColor(150, 112, 210)
C_CUT = QColor(250, 230, 120)      # vạch cắt giữa hai clip
C_GAP = QColor(58, 60, 66)
C_SEL = QColor(252, 250, 238)      # viền + tay nắm khi đang chọn
C_FX = {BLUR: QColor(90, 170, 250), DELOGO: QColor(240, 140, 70),
        LOGO: QColor(120, 220, 140)}


class Timeline(QWidget):
    seeked = pyqtSignal(float)
    seekDone = pyqtSignal(float)        # tha tay sau khi keo dau doc
    speedsChanged = pyqtSignal()
    committed = pyqtSignal()
    speedSelected = pyqtSignal(int)
    cueClicked = pyqtSignal(int)
    cuesChanged = pyqtSignal()          # kéo chip phụ đề -> đổi mốc thời gian
    regionsChanged = pyqtSignal()       # kéo thanh hiệu ứng
    selectionChanged = pyqtSignal(int, int)     # (lớp, chỉ số)
    clipsChanged = pyqtSignal()                 # kéo / trim clip
    dubClipsChanged = pyqtSignal()              # kéo / trim clip thuyết minh

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 1.0
        self.playhead = 0.0
        self.dub_clips = []                # nhat cat rieng cua track tieng
        self.lane_w = [1.0] * len(LANES)   # trong so chieu cao tung lop
        self._lane_edge = -1               # bien dang keo, -1 = khong
        self._wave_key = None       # cache cot song am, xem _paint_wave
        self._wave_cot = []
        self.speeds: List[Speed] = []
        self.regions: List[Region] = []
        self.cues: Sequence = []
        self.dub_offset = 0.0
        self.new_factor = 2.0
        self.sel_lane = L_SPEED
        self.sel_idx = -1
        self.cur_cue = -1
        self.tool_speed = False
        self.clips: List[Clip] = []
        self.ripple = True
        self.sel_clip = -1

        self.zoom = 1.0                 # 1.0 = vừa khít bề ngang
        self.fps = 25.0                 # để thước hiện được mốc khung hình
        self.scroll_t = 0.0             # giây ở mép trái

        self.strip = FilmStrip(self)
        self.wave = Waveform(self)
        self.strip.ready.connect(self.update)
        self.wave.ready.connect(self.update)

        self._drag = ""            # "" = rảnh, -2 = kéo đầu đọc, còn lại là chỉ số lớp
        self._mode = ""            # move / l / r / new / head
        self._x0 = 0
        self._orig = (0.0, 0.0)
        self._moved = False
        self._hover = (-1, -1)

        self._nat = RULER_H + sum(x[1] + LANE_GAP for x in LANES) + 8
        self.setMinimumHeight(self._nat)
        self.setMouseTracking(True)

    # --------------------------------------------------------------- dữ liệu

    def set_media(self, video: str, dub: str, duration: float) -> None:
        self.duration = max(0.01, duration)
        self.strip.load(video, self.duration)
        self.wave.load(dub)
        self.update()

    # --------------------------------------------------------------- toạ độ

    def track_rect(self) -> QRect:
        return QRect(LEFT_W, 0, max(10, self.width() - LEFT_W - 6), self.height())

    def visible_span(self) -> float:
        return self.duration / max(self.zoom, 0.05)

    def x_of(self, t: float) -> int:
        r = self.track_rect()
        return int(r.x() + (t - self.scroll_t) / self.visible_span() * r.width())

    def t_of(self, x: int) -> float:
        r = self.track_rect()
        t = self.scroll_t + (x - r.x()) / max(1, r.width()) * self.visible_span()
        return max(0.0, min(self.duration, t))

    def scale(self) -> float:
        """Kéo widget cao lên thì mọi lớp dày ra theo — ảnh và sóng âm to hơn.

        Tính theo tổng trọng số nên khi người dùng kéo cao một lớp lên, các lớp
        còn lại co lại vừa đủ — thanh thời gian không bao giờ tràn ra ngoài.
        """
        base = sum(LANES[i][1] * self.lane_w[i] for i in range(len(LANES)))
        room = self.height() - RULER_H - LANE_GAP * len(LANES) - 8
        return max(1.0, room / max(1.0, base))

    def lane_h(self, i: int) -> int:
        return max(LANE_MIN, int(LANES[i][1] * self.lane_w[i] * self.scale()))

    def lane_edge_at(self, y: int) -> int:
        """Con trỏ đang ở mép dưới của lớp nào (để kéo co dãn)? -1 nếu không."""
        for i in range(len(LANES) - 1):
            bien = self.lane_y(i) + self.lane_h(i) + LANE_GAP // 2
            if abs(y - bien) <= LANE_EDGE:
                return i
        return -1

    def keo_bien_lop(self, i: int, dy: int) -> None:
        """Kéo mép giữa lớp i và i+1: lớp trên dày ra, lớp dưới mỏng đi."""
        if not (0 <= i < len(LANES) - 1):
            return
        sc = self.scale()
        h1 = LANES[i][1] * self.lane_w[i] * sc
        h2 = LANES[i + 1][1] * self.lane_w[i + 1] * sc
        # KEP vao gioi han, dung tu choi ca cu keo. Keo nhanh mot phat 40px se
        # bi huy sach neu chi kiem roi return, nguoi dung tuong tinh nang hong.
        dy = max(LANE_MIN - h1, min(dy, h2 - LANE_MIN))
        if abs(dy) < 0.5:
            return
        self.lane_w[i] = (h1 + dy) / max(0.001, LANES[i][1] * sc)
        self.lane_w[i + 1] = (h2 - dy) / max(0.001, LANES[i + 1][1] * sc)
        self._wave_key = None       # đổi chiều cao thì sóng âm phải vẽ lại
        self.update()

    def reset_lane_heights(self) -> None:
        self.lane_w = [1.0] * len(LANES)
        self._wave_key = None
        self.update()

    def lane_y(self, i: int) -> int:
        return RULER_H + sum(self.lane_h(j) + LANE_GAP for j in range(i))

    def lane_at(self, y: int) -> int:
        for i in range(len(LANES)):
            top = self.lane_y(i)
            if top <= y < top + self.lane_h(i):
                return i
        return -1

    def speed_rect(self, s: Speed) -> QRect:
        return QRect(self.x_of(s.start), self.lane_y(L_SPEED),
                     max(3, self.x_of(s.end) - self.x_of(s.start)), self.lane_h(L_SPEED))

    # ------------------------------------------------------------------ vẽ

    def _fmt(self, t: float, buoc: float = 1.0) -> str:
        """Nhãn thước. Phóng sâu thì thêm số khung, phim dài thì thêm giờ.

        Bản cũ luôn là phút:giây nên phim 2 tiếng hiện '125:30' thay vì
        '2:05:30', và phóng tới mức khung hình cũng không hiện được khung nào.
        """
        # Tính THẲNG bằng số khung rồi mới tách ra. Tách giây trước rồi mới
        # làm tròn phần lẻ thì t=6.0 lưu thành 5.999999 sẽ ra "5 giây, khung
        # 25" -> kẹp xuống thành 5:24, trong khi đúng phải là 6:00.
        fps = max(1, int(round(self.fps)))
        tong = max(0, int(round(max(0.0, t) * fps)))
        khung = tong % fps
        giay_tong = tong // fps
        gio, con = divmod(giay_tong, 3600)
        phut, giay = divmod(con, 60)
        if buoc < 1.0:
            # Mức khung hình dùng timecode ĐỦ BỐN PHẦN h:mm:ss:ff. Rút gọn
            # thành '0:01:21' thì đọc ra "1 phút 21 giây" trong khi nó là
            # "1 giây, khung 21".
            return f"{gio}:{phut:02d}:{giay:02d}:{khung:02d}"
        if self.duration >= 3600:
            return f"{gio}:{phut:02d}:{giay:02d}"
        return f"{phut}:{giay:02d}"

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), C_BG)
        r = self.track_rect()
        p.setClipRect(QRect(0, 0, self.width(), self.height()))

        f = QFont()
        f.setPointSize(7)
        p.setFont(f)

        t0, t1 = self.scroll_t, self.scroll_t + self.visible_span()

        # thước: vạch phụ ngắn trong dải thước, vạch chính kẻ suốt chiều cao
        chinh, phu = self._ruler_step()
        if phu > 0:
            t = int(t0 / phu) * phu
            p.setPen(QPen(C_GRID.darker(115), 1))
            vach = []
            while t <= t1 + phu:
                x = self.x_of(t)
                if r.x() <= x <= r.right():
                    vach.append(QLine(x, RULER_H - 6, x, RULER_H - 1))
                t += phu
            if vach:
                p.drawLines(vach)

        t = int(t0 / chinh) * chinh
        while t <= t1 + chinh:
            x = self.x_of(t)
            if r.x() <= x <= r.right():
                p.setPen(C_GRID)
                p.drawLine(x, 0, x, self.height())
                p.setPen(C_TEXT)
                p.drawText(x + 3, RULER_H - 7, self._fmt(t, chinh))
            t += chinh

        # nền + nhãn lớp
        for i, (name, _h0) in enumerate(LANES):
            y, h = self.lane_y(i), self.lane_h(i)
            p.fillRect(QRect(r.x(), y, r.width(), h), C_LANE)
            p.setPen(C_TEXT)
            p.drawText(QRect(4, y, LEFT_W - 10, h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, name)

        self._paint_subs(p, r)
        self._paint_film(p, r)
        self._paint_wave(p, r)
        self._paint_clips(p, r)
        self._paint_speed(p)
        self._paint_fx(p)

        x = self.x_of(self.playhead)
        if r.x() - 2 <= x <= r.right() + 2:
            p.setPen(QPen(C_HEAD, 2))
            p.drawLine(x, 0, x, self.height())
            p.setBrush(QBrush(C_HEAD))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRect(x - 5, 0, 10, 8))
        p.end()

    def _paint_subs(self, p: QPainter, r: QRect) -> None:
        y, h = self.lane_y(L_SUB), self.lane_h(L_SUB)
        fm = QFontMetrics(p.font())
        # Thu phong ca phim thi ca 154 chip deu nam trong khung. Ve rieng tung
        # cai la 154 lenh drawRoundedRect (do duoc 4.8 ms moi lan ve). Gop het
        # chip THUONG vao mot QPainterPath roi ve mot lan; chi cai dang doc,
        # dang chon va dang di chuot moi ve rieng vi khac mau.
        duong = QPainterPath()
        rieng = []
        for i, c in enumerate(self.cues):
            x1, x2 = self.x_of(c.start), self.x_of(c.end)
            if x2 < r.x() or x1 > r.right():
                continue
            w = max(6, x2 - x1)
            rc = QRect(x1, y + 2, w, h - 4)
            on = i == self.cur_cue
            picked = self.sel_lane == L_SUB and i == self.sel_idx
            hovered = self._hover == (L_SUB, i)
            if on or picked or hovered:
                rieng.append((rc, w, c, on, picked, hovered))
            else:
                duong.addRoundedRect(QRectF(rc), 4, 4)
                if w > 34:
                    rieng.append((rc, w, c, False, False, None))

        if not duong.isEmpty():
            p.setBrush(QBrush(C_SUBCHIP))
            p.setPen(QPen(C_SUBCHIP.lighter(130), 1))
            p.drawPath(duong)

        for rc, w, c, on, picked, hovered in rieng:
            if hovered is not None:     # chip khac mau -> ve ca nen
                col = C_SUBCHIP_ON if on else (C_SUBCHIP.lighter(118) if hovered
                                               else C_SUBCHIP)
                p.setBrush(QBrush(col))
                p.setPen(QPen(C_SEL if picked else col.lighter(130),
                              2 if picked else 1))
                p.drawRoundedRect(rc, 4, 4)
            if w > 34:
                p.setPen(QColor(250, 250, 252) if on else QColor(228, 234, 242))
                p.drawText(rc.adjusted(5, 0, -3, 0),
                           Qt.AlignmentFlag.AlignVCenter,
                           fm.elidedText(c.text, Qt.TextElideMode.ElideRight, w - 8))

    def _paint_film(self, p: QPainter, r: QRect) -> None:
        y, h = self.lane_y(L_VIDEO), self.lane_h(L_VIDEO)
        if not self.strip.pixmap or self.strip.pixmap.isNull():
            p.setPen(C_TEXT)
            p.drawText(QRect(r.x() + 8, y, 240, h),
                       Qt.AlignmentFlag.AlignVCenter, "đang lấy ảnh khung hình…")
            return
        tw = max(24, int(h * 16 / 9))
        x = r.x()
        while x < r.right():
            frac = (self.t_of(x)) / max(self.duration, .001)
            src = self.strip.tile_rect(frac)
            if src is not None:
                p.drawPixmap(QRect(x, y, tw, h), self.strip.pixmap, src)
            x += tw
        # Phải bỏ brush: lớp phụ đề vẽ trước để lại brush xanh, không xoá thì
        # cái khung viền dưới đây tô đè kín cả filmstrip.
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(C_GRID, 1))
        p.drawRect(QRect(r.x(), y, r.width() - 1, h - 1))

    def _paint_wave(self, p: QPainter, r: QRect) -> None:
        y, h = self.lane_y(L_DUB), self.lane_h(L_DUB)
        mid = y + h // 2
        if self.wave.peaks is None:
            p.setPen(C_TEXT)
            p.drawText(QRect(r.x() + 8, y, 240, h),
                       Qt.AlignmentFlag.AlignVCenter, "đang đọc sóng âm…")
            return
        # Gom thanh MOT lenh drawLines. Goi drawLine tung cot la ~1470 lenh
        # QPainter moi lan ve, nhan 25 fps thanh hon 36.000 lenh mot giay.
        # Luc phat, song am KHONG doi - chi vach dau phat chay. Dung lai cac
        # cot da tinh thay vi lap 1500 vong moi khung hinh (do duoc 13.9 ms
        # moi lan ve, chiem 62% toan bo thoi gian ve thanh thoi gian).
        # Khoa duoi day liet ke du moi thu ma hinh dang song phu thuoc vao,
        # nen khong co trang thai an nao lam cache lech.
        khoa = (r.x(), r.right(), mid, h,
                round(self.scroll_t, 4), round(self.visible_span(), 6),
                round(self.dub_offset, 4), round(self.duration, 4),
                id(self.wave.peaks), len(self.wave.peaks))
        if khoa != self._wave_key:
            dl = self.duration if self.duration > 0.001 else 0.001
            bien = h / 2 - 2
            cot = []
            for x in range(r.x(), r.right()):
                t = self.t_of(x) - self.dub_offset
                if t < 0 or t > self.duration:
                    continue
                a = self.wave.at(t / dl) * bien
                cot.append(QLine(x, int(mid - a), x, int(mid + a)))
            self._wave_cot, self._wave_key = cot, khoa
        p.setPen(QPen(C_DUB, 1))
        if self._wave_cot:
            p.drawLines(self._wave_cot)

    def _paint_clips(self, p: QPainter, r: QRect) -> None:
        """Mỗi clip là một khối bo góc có viền, nhãn và tay nắm trim.

        Vẽ clip thành khối thay vì mấy vạch cắt là khác biệt lớn nhất: nhìn là
        biết ngay đâu là một đoạn kéo được, mép nào nắm được.
        """
        top = self.lane_y(L_VIDEO)
        bot = self.lane_y(L_DUB) + self.lane_h(L_DUB)
        lay = clip_layout(self.clips, self.ripple)
        if not lay:
            return
        hov_lane, hov_i = self._hover

        for a, b, i in lay:
            x1, x2 = self.x_of(a), self.x_of(b)
            if x2 < r.x() - 4 or x1 > r.right() + 4:
                continue
            w = max(3, x2 - x1)

            if i < 0:                       # khoảng trống: gạch chéo mờ
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(C_GAP, Qt.BrushStyle.BDiagPattern))
                p.drawRoundedRect(QRect(x1, top, w, bot - top), 5, 5)
                continue

            picked = i == self.sel_clip
            hovered = hov_lane == L_VIDEO and hov_i == i
            rc = QRect(x1 + 1, top + 1, w - 2, bot - top - 2)

            p.setBrush(Qt.BrushStyle.NoBrush)
            if picked:
                p.setPen(QPen(C_SEL, 2))
            elif hovered:
                p.setPen(QPen(C_CUT.lighter(115), 2))
            else:
                p.setPen(QPen(C_CUT.darker(135), 1))
            p.drawRoundedRect(rc, 5, 5)

            if len(lay) > 1 and w > 46:     # nhãn clip
                p.setPen(QColor(248, 246, 232) if picked else C_CUT)
                p.drawText(rc.adjusted(7, 2, -6, 0),
                           Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                           f"{i + 1}")

            if picked and w > 18:           # tay nắm trim hai mép
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(C_SEL))
                for hx in (rc.left(), rc.right() - 5):
                    p.drawRoundedRect(QRect(hx, rc.top() + 4, 5,
                                            rc.height() - 8), 2, 2)
        p.setBrush(Qt.BrushStyle.NoBrush)

    def clip_at(self, t: float) -> int:
        for a, b, i in clip_layout(self.clips, self.ripple):
            if a <= t < b:
                return i
        return -1

    def _paint_speed(self, p: QPainter) -> None:
        hov_lane, hov_i = self._hover
        for i, s in enumerate(normalize(self.speeds, self.duration)):
            col = C_FAST if s.factor > 1 else C_SLOW
            rc = self.speed_rect(s).adjusted(0, 2, 0, -2)
            picked = self.sel_lane == L_SPEED and i == self.sel_idx
            hovered = hov_lane == L_SPEED and hov_i == i
            alpha = 210 if picked else (185 if hovered else 155)
            p.setBrush(QBrush(QColor(col.red(), col.green(), col.blue(), alpha)))
            p.setPen(QPen(C_SEL if picked else col.lighter(125),
                          2 if picked else 1))
            p.drawRoundedRect(rc, 4, 4)
            if rc.width() > 26:
                p.setPen(QColor(250, 250, 252))
                p.drawText(rc, Qt.AlignmentFlag.AlignCenter, f"{s.factor:g}×")

    def _paint_fx(self, p: QPainter) -> None:
        y, h = self.lane_y(L_FX), self.lane_h(L_FX)
        for i, reg in enumerate(self.regions):
            a = reg.start
            b = reg.end if reg.end > reg.start else self.duration
            col = C_FX.get(reg.kind, QColor(190, 190, 190))
            if not reg.enabled:
                col = QColor(110, 112, 116)
            x1, x2 = self.x_of(a), self.x_of(b)
            rc = QRect(x1, y + 3, max(3, x2 - x1), h - 6)
            picked = self.sel_lane == L_FX and i == self.sel_idx
            hovered = self._hover == (L_FX, i)
            p.setPen(QPen(C_SEL if picked else col.lighter(120),
                          2 if picked else 1))
            p.setBrush(QBrush(QColor(col.red(), col.green(), col.blue(),
                                     195 if picked else (170 if hovered else 140))))
            p.drawRoundedRect(rc, 4, 4)

    def _ruler_step(self):
        """(bước chính, bước phụ) tính bằng giây, chọn theo mức thu phóng.

        Bản cũ dừng ở 1 giây nên phóng hết cỡ vẫn chỉ có nhãn mỗi giây, cách
        nhau 600px — không đặt được đầu đọc vào đúng khung hình nào. Thang này
        đi xuống tới TỪNG KHUNG, và trả thêm bước phụ để vẽ vạch nhỏ, vì giữa
        hai nhãn mà trống trơn thì không ước lượng được vị trí.
        """
        r = self.track_rect()
        px = r.width() / max(self.visible_span(), 0.001)     # pixel mỗi giây
        f = 1.0 / max(self.fps, 1.0)
        thang = [(f, 1), (2 * f, 2), (5 * f, 5), (10 * f, 5), (30 * f, 3),
                 (1, 4), (2, 2), (5, 5), (10, 5), (15, 3), (30, 3),
                 (60, 4), (120, 2), (300, 5), (600, 5), (900, 3),
                 (1800, 3), (3600, 4), (7200, 2)]
        for chinh, chia in thang:
            if chinh * px >= 74:
                return chinh, chinh / chia
        chinh, chia = thang[-1]
        return chinh, chinh / chia

    # --------------------------------------------------------- zoom & cuộn

    def wheelEvent(self, e) -> None:
        d = e.angleDelta().y()
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            anchor = self.t_of(e.position().toPoint().x())
            self.zoom = max(1.0, min(400.0, self.zoom * (1.25 if d > 0 else 0.8)))
            # giữ nguyên điểm dưới con trỏ khi phóng to
            self.scroll_t = anchor - (anchor - self.scroll_t) * 1.0
            span = self.visible_span()
            self.scroll_t = max(0.0, min(anchor - span / 2, self.duration - span))
        else:
            self.scroll_t += (-d / 120) * self.visible_span() * 0.12
            self.scroll_t = max(0.0, min(self.scroll_t,
                                         max(0.0, self.duration - self.visible_span())))
        self.update()

    def set_zoom(self, z: float) -> None:
        span_before = self.visible_span()
        self.zoom = max(1.0, min(400.0, z))
        span = self.visible_span()
        self.scroll_t = max(0.0, min(self.playhead - span / 2,
                                     max(0.0, self.duration - span)))
        if span_before == span:
            return
        self.update()

    def update_playhead(self, t: float) -> None:
        """Doi vach dau phat ma khong ve lai ca thanh thoi gian.

        Ve lai toan bo ton 21.7 ms tren phim 15 phut (154 chip phu de, dai
        anh khung hinh, song am). Nhan 25 lan mot giay chi de dich mot vach
        doc la het 41.8% mot loi CPU. Chi lam ban dai hep quanh vach cu va
        vach moi thi Qt cat phan con lai.
        """
        x_cu = self.x_of(self.playhead)
        self.playhead = t
        cuon_truoc = self.scroll_t
        self.ensure_visible(t)
        if self.scroll_t != cuon_truoc:
            return                      # ensure_visible da goi update() day du
        x_moi = self.x_of(t)
        lo, hi = (x_cu, x_moi) if x_cu <= x_moi else (x_moi, x_cu)
        self.update(QRect(lo - 3, 0, (hi - lo) + 7, self.height()))

    def ensure_visible(self, t: float) -> None:
        span = self.visible_span()
        if t < self.scroll_t or t > self.scroll_t + span:
            self.scroll_t = max(0.0, min(t - span / 2, max(0.0, self.duration - span)))
            self.update()

    # ------------------------------------------------------- chọn & kéo thả

    @property
    def sel(self) -> int:
        """Chỉ số đoạn tốc độ đang chọn (-1 nếu đang chọn thứ khác)."""
        return self.sel_idx if self.sel_lane == L_SPEED else -1

    @sel.setter
    def sel(self, v: int) -> None:
        self.sel_lane, self.sel_idx = L_SPEED, v

    def _items(self, lane: int):
        """(đầu, cuối) của từng phần tử trên lớp — dùng chung cho hit-test."""
        if lane == L_SUB:
            return [(c.start, c.end) for c in self.cues]
        if lane == L_SPEED:
            return [(s.start, s.end) for s in self.speeds]
        if lane == L_FX:
            return [(r.start, r.end if r.end > r.start else self.duration)
                    for r in self.regions]
        if lane == L_VIDEO:
            return [(a, b) for a, b, i in clip_layout(self.clips, self.ripple)
                    if i >= 0]
        if lane == L_DUB:
            # dub_clips rỗng = track thuyết minh cắt y hệt hình. Vẫn cho kéo,
            # chạm vào là tách ra thành nhát cắt riêng (xem _apply_dub).
            src = self.dub_clips if self.dub_clips else self.clips
            return [(a, b) for a, b, i in clip_layout(src, self.ripple)
                    if i >= 0]
        return []

    def _hit(self, pos: QPoint):
        """Trả về (lớp, chỉ số, kiểu kéo) — kiểu là move / l / r."""
        lane = self.lane_at(pos.y())
        if lane not in (L_SUB, L_SPEED, L_FX, L_VIDEO, L_DUB):
            return -1, -1, ""
        for i, (a, b) in enumerate(self._items(lane)):
            x1, x2 = self.x_of(a), self.x_of(b)
            if x1 - 2 <= pos.x() <= x2 + 2:
                if pos.x() - x1 <= EDGE:
                    return lane, i, "l"
                if x2 - pos.x() <= EDGE:
                    return lane, i, "r"
                return lane, i, "move"
        return lane, -1, ""

    def _snap(self, t: float, skip: tuple = ()) -> float:
        """Bắt dính vào đầu đọc và mốc của các phần tử khác."""
        r = self.track_rect()
        tol = self.visible_span() / max(1, r.width()) * 7
        cands = [self.playhead, 0.0, self.duration]
        for lane in (L_SUB, L_SPEED, L_FX, L_VIDEO, L_DUB):
            for i, (a, b) in enumerate(self._items(lane)):
                if (lane, i) in skip:
                    continue
                cands += [a, b]
        best = min(cands, key=lambda c: abs(c - t))
        return best if abs(best - t) <= tol else t

    def _apply_clip(self, i: int, a: float, b: float) -> None:
        """Kéo clip trên dòng thời gian -> ghi ngược về lát cắt trong file gốc.

        Kéo hai mép là trim (đổi lát nào của file gốc được dùng); kéo giữa là
        dời chỗ, chỉ có nghĩa khi tắt nam châm.
        """
        lay = [(x, y, k) for x, y, k in clip_layout(self.clips, self.ripple) if k >= 0]
        if not (0 <= i < len(lay)):
            return
        da, db, _k = lay[i]
        seq = (ripple_close(self.clips) if self.ripple
               else sorted(self.clips, key=lambda x: x.at))
        c = seq[i]

        if abs((b - a) - (db - da)) < 0.01:          # dời nguyên khối
            c.at = max(0.0, a)
        else:                                        # trim
            c.src_start = max(0.0, c.src_start + (a - da))
            c.src_end = min(self.duration, c.src_end + (b - db))
            if c.src_end - c.src_start < 0.1:
                c.src_end = c.src_start + 0.1
        self.clips = ripple_close(seq) if self.ripple else seq
        self.clipsChanged.emit()

    def _apply_dub(self, i: int, a: float, b: float) -> None:
        """Kéo / trim clip trên lớp thuyết minh.

        Giống _apply_clip nhưng ghi vào dub_clips. dub_clips rỗng nghĩa là
        track tiếng cắt y hệt hình; vừa chạm vào là phải sao chép nhát cắt của
        hình ra thành bản riêng, không thì sửa tiếng lại đổi luôn cả hình.
        """
        if not self.dub_clips:
            self.dub_clips = [Clip(c.src_start, c.src_end, c.at)
                              for c in ensure(self.clips, self.duration)]
        lay = [(x, y, k) for x, y, k in clip_layout(self.dub_clips, self.ripple)
               if k >= 0]
        if not (0 <= i < len(lay)):
            return
        da, db, _k = lay[i]
        seq = (ripple_close(self.dub_clips) if self.ripple
               else sorted(self.dub_clips, key=lambda x: x.at))
        c = seq[i]
        if abs((b - a) - (db - da)) < 0.01:          # dời nguyên khối
            c.at = max(0.0, a)
        else:                                        # trim hai mép
            c.src_start = max(0.0, c.src_start + (a - da))
            c.src_end = min(self.duration, c.src_end + (b - db))
            if c.src_end - c.src_start < 0.1:
                c.src_end = c.src_start + 0.1
        self.dub_clips = ripple_close(seq) if self.ripple else seq
        self.dubClipsChanged.emit()

    def _apply(self, lane: int, i: int, a: float, b: float) -> None:
        a, b = max(0.0, a), min(self.duration, b)
        if b - a < 0.05:
            return
        if lane == L_VIDEO:
            self._apply_clip(i, a, b)
            return
        if lane == L_DUB:
            self._apply_dub(i, a, b)
            return
        if lane == L_SUB:
            self.cues[i].start, self.cues[i].end = a, b
            self.cuesChanged.emit()
        elif lane == L_SPEED:
            self.speeds[i].start, self.speeds[i].end = a, b
            self.speedsChanged.emit()
        elif lane == L_FX:
            self.regions[i].start, self.regions[i].end = a, b
            self.regionsChanged.emit()

    # ------------------------------------------------------------- chuột

    def mousePressEvent(self, e) -> None:
        pos = e.pos()
        # Kéo biên co dãn lớp: bắt cả ở cột nhãn bên trái, vì đó là chỗ người
        # ta đưa chuột tới theo phản xạ.
        k = self.lane_edge_at(pos.y())
        if k >= 0:
            self._drag, self._mode, self._lane_edge = -3, "lane", k
            self._y0 = pos.y()
            return
        if pos.x() < LEFT_W:
            return
        self._moved = False
        self._hover = (-1, -1)

        lane, i, mode = self._hit(pos)
        if lane == L_VIDEO and i >= 0:
            self.sel_clip = i
            self.sel_lane, self.sel_idx = lane, i
            self._drag, self._mode = lane, mode
            self._x0 = pos.x()
            self._orig = self._items(lane)[i]
            if mode == "move":              # bấm giữa clip thì tua luôn tới đó
                self.playhead = self.t_of(pos.x())
                self.seeked.emit(self.playhead)
            self.selectionChanged.emit(lane, i)
            self.update()
            return

        if i >= 0:
            self.sel_lane, self.sel_idx = lane, i
            self._drag, self._mode = lane, mode
            self._x0 = pos.x()
            self._orig = self._items(lane)[i]
            self.selectionChanged.emit(lane, i)
            self.update()
            return

        if self.tool_speed and lane == L_SPEED:
            t = self.t_of(pos.x())
            self.speeds.append(Speed(t, t, self.new_factor))
            self.sel_lane, self.sel_idx = L_SPEED, len(self.speeds) - 1
            self._drag, self._mode = L_SPEED, "new"
            self._x0, self._orig = pos.x(), (t, t)
            self.update()
            return

        self._drag, self._mode = -2, "head"      # -2 = kéo đầu đọc
        self.playhead = self.t_of(pos.x())
        self.seeked.emit(self.playhead)
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._drag == -3 and self._mode == "lane":
            self.keo_bien_lop(self._lane_edge, e.pos().y() - self._y0)
            self._y0 = e.pos().y()
            return
        if self._drag == "":
            if self.lane_edge_at(e.pos().y()) >= 0:
                self.setCursor(Qt.CursorShape.SizeVerCursor)
                if self._hover != (-1, -1):
                    self._hover = (-1, -1)
                    self.update()
                return
            lane, i, mode = self._hit(e.pos())
            if (lane, i) != self._hover:
                self._hover = (lane, i)
                self.update()
            self.setCursor(Qt.CursorShape.SizeHorCursor if mode in ("l", "r")
                           else (Qt.CursorShape.OpenHandCursor if i >= 0
                                 else Qt.CursorShape.ArrowCursor))
            return

        self._moved = True
        if self._mode == "head":
            self.playhead = self.t_of(e.pos().x())
            self.seeked.emit(self.playhead)
            self.update()
            return

        lane, i = self._drag, self.sel_idx
        if not (0 <= i < len(self._items(lane))):
            return
        a0, b0 = self._orig
        dt = self.t_of(e.pos().x()) - self.t_of(self._x0)
        skip = ((lane, i),)

        if self._mode == "new":
            t = self._snap(self.t_of(e.pos().x()), skip)
            a, b = min(a0, t), max(a0, t)
        elif self._mode == "move":
            span = b0 - a0
            a = self._snap(max(0.0, min(a0 + dt, self.duration - span)), skip)
            a = max(0.0, min(a, self.duration - span))
            b = a + span
        elif self._mode == "l":
            a = self._snap(min(a0 + dt, b0 - 0.1), skip)
            a, b = max(0.0, a), b0
        else:
            b = self._snap(max(b0 + dt, a0 + 0.1), skip)
            a, b = a0, min(self.duration, b)

        self._apply(lane, i, a, b)
        self.update()

    def leaveEvent(self, _e) -> None:
        if self._hover != (-1, -1):
            self._hover = (-1, -1)
            self.update()

    def mouseReleaseEvent(self, _e) -> None:
        if self._drag == "":
            return
        lane, mode = self._drag, self._mode
        self._drag, self._mode = "", ""

        if mode == "lane":
            self._lane_edge = -1
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return          # co dãn lớp không phải sửa dự án, đừng đẩy vào undo
        if mode == "head":
            self.seekDone.emit(self.playhead)   # chot dung vi tri cuoi, khong gop
            return

        # Bấm mà không kéo trên chip phụ đề = nhảy tới câu đó
        if lane == L_SUB and not self._moved:
            i = self.sel_idx
            if 0 <= i < len(self.cues):
                self.cueClicked.emit(i)
                self.playhead = self.cues[i].start
                self.seeked.emit(self.playhead)
        elif lane == L_SPEED:
            # Sua TAI CHO. Gan bang dau '=' se tao list moi, cat dut tham chieu
            # dung chung voi proj.speeds -> tren man hinh thay doan da xoa,
            # nhung luc xuat van con nguyen.
            self.speeds[:] = normalize(self.speeds, self.duration)
            self.sel_idx = min(self.sel_idx, len(self.speeds) - 1)
            self.speedsChanged.emit()

        self.committed.emit()
        self.update()

    def delete_selected(self) -> bool:
        """Xoá phần tử đang chọn. Phụ đề chỉ xoá khi người dùng chủ động chọn."""
        i = self.sel_idx
        if self.sel_lane == L_SPEED and 0 <= i < len(self.speeds):
            self.speeds.pop(i)
        elif self.sel_lane == L_FX and 0 <= i < len(self.regions):
            self.regions.pop(i)
        else:
            return False
        self.sel_idx = -1
        self.committed.emit()
        self.update()
        return True
