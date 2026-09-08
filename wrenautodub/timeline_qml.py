# -*- coding: utf-8 -*-
"""Bọc Timeline (QWidget) thành một item dùng được trong QML.

Không viết lại phần vẽ: QWidget.render() đổ được vào bất kỳ QPainter nào, kể
cả painter của QQuickPaintedItem. Nhờ vậy toàn bộ timeline đã kiểm chứng —
filmstrip, sóng âm, chip phụ đề, kéo thả, bắt dính — dùng lại nguyên vẹn,
không phải làm lại từ đầu rồi kiểm lại từ đầu.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QMouseEvent, QPainter, QRegion, QWheelEvent
from PyQt6.QtQuick import QQuickPaintedItem
from PyQt6.QtWidgets import QWidget

from .timeline import Timeline


class TimelineItem(QQuickPaintedItem):
    """Item QML hiển thị Timeline và chuyển tiếp chuột xuống cho nó."""

    seeked = pyqtSignal(float)
    committed = pyqtSignal()
    selectionChanged = pyqtSignal(int, int)
    cueClicked = pyqtSignal(int)
    clipsChanged = pyqtSignal()
    cuesChanged = pyqtSignal()
    regionsChanged = pyqtSignal()
    speedsChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setFlag(QQuickPaintedItem.Flag.ItemHasContents, True)

        self.tl = Timeline()
        self.tl.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.tl.show()              # cần show để layout chạy, nhưng không lên màn hình

        for name in ("seeked", "committed", "selectionChanged", "cueClicked",
                     "clipsChanged", "cuesChanged", "regionsChanged",
                     "speedsChanged"):
            getattr(self.tl, name).connect(getattr(self, name))
        self.tl.strip.ready.connect(self.update)
        self.tl.wave.ready.connect(self.update)
        for name in ("seeked", "committed", "clipsChanged", "cuesChanged",
                     "regionsChanged", "speedsChanged", "selectionChanged"):
            getattr(self.tl, name).connect(lambda *_a: self.update())

    # ------------------------------------------------------------------ vẽ

    def paint(self, p: QPainter) -> None:
        w, h = max(1, int(self.width())), max(1, int(self.height()))
        if self.tl.size().width() != w or self.tl.size().height() != h:
            self.tl.resize(w, h)
        self.tl.render(p, QPoint(0, 0), QRegion(),
                       QWidget.RenderFlag.DrawWindowBackground
                       | QWidget.RenderFlag.DrawChildren)

    # ------------------------------------------------- chuyển tiếp sự kiện

    def _forward(self, ev, kind: QEvent.Type) -> None:
        pos = ev.position() if hasattr(ev, "position") else QPointF(ev.pos())
        me = QMouseEvent(kind, pos, ev.globalPosition() if hasattr(ev, "globalPosition")
                         else QPointF(0, 0),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         ev.modifiers())
        self.tl.event(me)
        self.update()

    def mousePressEvent(self, ev) -> None:
        self._forward(ev, QEvent.Type.MouseButtonPress)

    def mouseMoveEvent(self, ev) -> None:
        self._forward(ev, QEvent.Type.MouseMove)

    def mouseReleaseEvent(self, ev) -> None:
        self._forward(ev, QEvent.Type.MouseButtonRelease)

    def hoverMoveEvent(self, ev) -> None:
        self._forward(ev, QEvent.Type.MouseMove)

    def wheelEvent(self, ev) -> None:
        we = QWheelEvent(ev.position(), ev.globalPosition(), ev.pixelDelta(),
                         ev.angleDelta(), Qt.MouseButton.NoButton,
                         ev.modifiers(), Qt.ScrollPhase.NoScrollPhase, False)
        self.tl.wheelEvent(we)
        self.update()

    # ------------------------------------------------- API gọi được từ QML

    @pyqtSlot(float)
    def setPlayhead(self, t: float) -> None:
        self.tl.playhead = t
        self.update()

    @pyqtSlot(result=float)
    def playhead(self) -> float:
        return self.tl.playhead

    @pyqtSlot(float)
    def setZoom(self, z: float) -> None:
        self.tl.set_zoom(z)
        self.update()

    @pyqtSlot(result=float)
    def zoom(self) -> float:
        return self.tl.zoom

    @pyqtSlot(result=bool)
    def deleteSelected(self) -> bool:
        ok = self.tl.delete_selected()
        self.update()
        return ok
