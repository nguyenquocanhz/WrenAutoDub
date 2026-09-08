# -*- coding: utf-8 -*-
"""Icon vẽ thẳng bằng QPainter — không cần file ảnh kèm theo.

Mỗi icon vẽ trong lưới 24x24 rồi scale, nên sắc nét ở mọi cỡ và ăn theo màu
của giao diện.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap,
                         QPolygonF)

FG = "#dfe3e8"       # nét thường
ACCENT = "#5b9dfa"   # hành động chính
WARN = "#e0705c"     # hành động phá huỷ / dừng


def _pen(p: QPainter, color: str, w: float = 2.0) -> None:
    pen = QPen(QColor(color))
    pen.setWidthF(w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)


# --------------------------------------------------------------- từng hình

def _play(p: QPainter, c: str) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c))
    p.drawPolygon(QPolygonF([QPointF(8, 5), QPointF(8, 19), QPointF(19, 12)]))


def _stop(p: QPainter, c: str) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c))
    p.drawRoundedRect(QRectF(7, 7, 10, 10), 2, 2)


def _folder(p: QPainter, c: str) -> None:
    _pen(p, c)
    path = QPainterPath()
    path.moveTo(3, 7)
    path.lineTo(9.5, 7)
    path.lineTo(11.5, 9.5)
    path.lineTo(21, 9.5)
    path.lineTo(21, 19)
    path.lineTo(3, 19)
    path.closeSubpath()
    p.drawPath(path)


def _folder_open(p: QPainter, c: str) -> None:
    _folder(p, c)
    _pen(p, c, 1.8)
    p.drawLine(QPointF(3.5, 19), QPointF(7, 13))
    p.drawLine(QPointF(7, 13), QPointF(23, 13))


def _layers(p: QPainter, c: str) -> None:
    """Ba lớp xếp chồng — gợi ý kho model."""
    _pen(p, c, 1.8)
    for dy, w in ((0, 2.0), (4.5, 1.4), (9, 1.4)):
        _pen(p, c, w)
        p.drawPolygon(QPolygonF([QPointF(12, 3.5 + dy), QPointF(20.5, 8 + dy),
                                 QPointF(12, 12.5 + dy), QPointF(3.5, 8 + dy)]))


def _pulse(p: QPainter, c: str) -> None:
    """Nhịp tim — gợi ý khám máy."""
    _pen(p, c)
    path = QPainterPath()
    path.moveTo(2.5, 12)
    for x, y in ((7.5, 12), (10, 5.5), (13.5, 18.5), (16, 12), (21.5, 12)):
        path.lineTo(x, y)
    p.drawPath(path)


def _subtitle(p: QPainter, c: str) -> None:
    """Khung phụ đề với hai dòng chữ."""
    _pen(p, c, 1.8)
    p.drawRoundedRect(QRectF(3, 5, 18, 14), 2.5, 2.5)
    _pen(p, c, 1.6)
    p.drawLine(QPointF(6.5, 13), QPointF(12, 13))
    p.drawLine(QPointF(14, 13), QPointF(17.5, 13))
    p.drawLine(QPointF(6.5, 16), QPointF(10, 16))


def _download(p: QPainter, c: str) -> None:
    _pen(p, c)
    p.drawLine(QPointF(12, 3.5), QPointF(12, 14.5))
    path = QPainterPath()
    path.moveTo(7.5, 10)
    path.lineTo(12, 14.5)
    path.lineTo(16.5, 10)
    p.drawPath(path)
    p.drawLine(QPointF(4.5, 19.5), QPointF(19.5, 19.5))


def _trash(p: QPainter, c: str) -> None:
    _pen(p, c, 1.8)
    p.drawLine(QPointF(3.5, 6.5), QPointF(20.5, 6.5))
    p.drawLine(QPointF(9.5, 6.5), QPointF(9.5, 4))
    p.drawLine(QPointF(9.5, 4), QPointF(14.5, 4))
    p.drawLine(QPointF(14.5, 4), QPointF(14.5, 6.5))
    path = QPainterPath()
    path.moveTo(5.5, 6.5)
    path.lineTo(6.6, 20)
    path.lineTo(17.4, 20)
    path.lineTo(18.5, 6.5)
    p.drawPath(path)
    _pen(p, c, 1.4)
    p.drawLine(QPointF(10, 10), QPointF(10.4, 16.5))
    p.drawLine(QPointF(14, 10), QPointF(13.6, 16.5))


def _refresh(p: QPainter, c: str) -> None:
    _pen(p, c)
    p.drawArc(QRectF(4.5, 4.5, 15, 15), 60 * 16, 260 * 16)
    p.setBrush(QColor(c))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPolygon(QPolygonF([QPointF(17.5, 3), QPointF(19.5, 9), QPointF(13.5, 7.5)]))


def _close(p: QPainter, c: str) -> None:
    _pen(p, c)
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))


def _app(p: QPainter, c: str) -> None:
    """Bong bóng thoại + nút play — lồng tiếng."""
    _pen(p, ACCENT, 2.0)
    path = QPainterPath()
    path.addRoundedRect(QRectF(2.5, 3.5, 19, 14), 3.5, 3.5)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(ACCENT))
    p.drawPolygon(QPolygonF([QPointF(9.5, 7), QPointF(9.5, 14), QPointF(15.5, 10.5)]))
    p.drawPolygon(QPolygonF([QPointF(7, 17), QPointF(12, 17), QPointF(7.5, 21)]))


def _undo(p: QPainter, c: str) -> None:
    """Mũi tên vòng ngược về trái."""
    _pen(p, c)
    p.drawArc(QRectF(4, 6, 16, 14), 30 * 16, 190 * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c))
    p.drawPolygon(QPolygonF([QPointF(3, 4), QPointF(10.5, 8), QPointF(3.5, 11.5)]))


def _redo(p: QPainter, c: str) -> None:
    """Mũi tên vòng xuôi về phải."""
    _pen(p, c)
    p.drawArc(QRectF(4, 6, 16, 14), -40 * 16, -190 * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c))
    p.drawPolygon(QPolygonF([QPointF(21, 4), QPointF(13.5, 8), QPointF(20.5, 11.5)]))


def _cut(p: QPainter, c: str) -> None:
    """Khung chữ nhật nét đứt — vùng hiệu ứng."""
    pen = QPen(QColor(c))
    pen.setWidthF(2.0)
    pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(4, 6, 16, 12))


def _zoom_in(p: QPainter, c: str) -> None:
    _pen(p, c)
    p.drawEllipse(QRectF(4, 4, 12, 12))
    p.drawLine(QPointF(15, 15), QPointF(20.5, 20.5))
    p.drawLine(QPointF(7, 10), QPointF(13, 10))
    p.drawLine(QPointF(10, 7), QPointF(10, 13))


def _zoom_out(p: QPainter, c: str) -> None:
    _pen(p, c)
    p.drawEllipse(QRectF(4, 4, 12, 12))
    p.drawLine(QPointF(15, 15), QPointF(20.5, 20.5))
    p.drawLine(QPointF(7, 10), QPointF(13, 10))


def _fit(p: QPainter, c: str) -> None:
    """Bốn mũi tên hướng ra — xem vừa khít."""
    _pen(p, c, 1.8)
    p.drawLine(QPointF(3, 8), QPointF(3, 3))
    p.drawLine(QPointF(3, 3), QPointF(8, 3))
    p.drawLine(QPointF(21, 16), QPointF(21, 21))
    p.drawLine(QPointF(21, 21), QPointF(16, 21))
    p.drawLine(QPointF(3.5, 3.5), QPointF(10, 10))
    p.drawLine(QPointF(20.5, 20.5), QPointF(14, 14))


def _scissors(p: QPainter, c: str) -> None:
    """Kéo cắt."""
    _pen(p, c, 1.8)
    p.drawLine(QPointF(8, 8), QPointF(19, 19))
    p.drawLine(QPointF(16, 8), QPointF(7.5, 16.5))
    p.drawEllipse(QRectF(3.5, 15.5, 5, 5))
    p.drawEllipse(QRectF(15.5, 15.5, 5, 5))


def _split_snd(p: QPainter, c: str) -> None:
    """Sóng âm bị cắt đôi."""
    _pen(p, c, 1.6)
    for x, h in ((4, 3), (6.5, 6), (9, 4)):
        p.drawLine(QPointF(x, 12 - h), QPointF(x, 12 + h))
    for x, h in ((15, 4), (17.5, 6), (20, 3)):
        p.drawLine(QPointF(x, 12 - h), QPointF(x, 12 + h))
    pen = QPen(QColor(c))
    pen.setWidthF(1.6)
    pen.setStyle(Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(12, 3), QPointF(12, 21))


def _merge(p: QPainter, c: str) -> None:
    """Hai mũi tên chụm vào nhau."""
    _pen(p, c, 1.8)
    p.drawLine(QPointF(2.5, 12), QPointF(9, 12))
    p.drawLine(QPointF(15, 12), QPointF(21.5, 12))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c))
    p.drawPolygon(QPolygonF([QPointF(11.5, 12), QPointF(7, 8.5), QPointF(7, 15.5)]))
    p.drawPolygon(QPolygonF([QPointF(12.5, 12), QPointF(17, 8.5), QPointF(17, 15.5)]))


def _magnet(p: QPainter, c: str) -> None:
    """Nam châm — bật/tắt hít clip lại."""
    _pen(p, c, 2.0)
    path = QPainterPath()
    path.moveTo(5, 19)
    path.lineTo(5, 11)
    path.arcTo(QRectF(5, 4, 14, 14), 180, -180)
    path.lineTo(19, 19)
    p.drawPath(path)
    p.drawLine(QPointF(5, 15), QPointF(9.5, 15))
    p.drawLine(QPointF(14.5, 15), QPointF(19, 15))


SHAPES = {
    "play": (_play, ACCENT),
    "stop": (_stop, WARN),
    "folder": (_folder, FG),
    "folder_open": (_folder_open, FG),
    "layers": (_layers, FG),
    "pulse": (_pulse, FG),
    "subtitle": (_subtitle, FG),
    "download": (_download, FG),
    "trash": (_trash, WARN),
    "refresh": (_refresh, FG),
    "close": (_close, FG),
    "app": (_app, ACCENT),
    "undo": (_undo, FG),
    "redo": (_redo, FG),
    "region": (_cut, FG),
    "zoom_in": (_zoom_in, FG),
    "zoom_out": (_zoom_out, FG),
    "fit": (_fit, FG),
    "scissors": (_scissors, FG),
    "split_snd": (_split_snd, FG),
    "merge": (_merge, FG),
    "magnet": (_magnet, FG),
}


def icon(name: str, size: int = 18, color: str | None = None) -> QIcon:
    draw, default = SHAPES[name]
    pm = QPixmap(size * 4, size * 4)          # vẽ lớn rồi thu nhỏ cho mượt
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * 4 / 24.0, size * 4 / 24.0)
    draw(p, color or default)
    p.end()
    return QIcon(pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation))
