# -*- coding: utf-8 -*-
"""Khung xem trước cho QML: video phát thật + vẽ vùng hiệu ứng đè lên.

Bọc lại Preview (QWidget) y như cách làm với Timeline — phần kéo thả vùng,
tay nắm bốn góc, letterbox đều đã kiểm chứng nên dùng lại nguyên vẹn. Khung
hình do VideoPlayer đẩy sang qua QVideoSink, không phải trích bằng ffmpeg.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QMouseEvent, QPainter, QPixmap, QRegion
from PyQt6.QtQuick import QQuickPaintedItem
from PyQt6.QtWidgets import QWidget

from .edit import Project
from .editor import Preview


class PreviewItem(QQuickPaintedItem):
    """Item QML: hiển thị khung hình và cho đặt vùng làm mờ / xoá logo / chèn logo."""

    regionCommitted = pyqtSignal()
    regionSelected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setFlag(QQuickPaintedItem.Flag.ItemHasContents, True)

        self.pv = Preview(Project())
        self.pv.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.pv.show()
        self.pv.committed.connect(self.regionCommitted)
        self.pv.selected.connect(self.regionSelected)
        self.pv.changed.connect(self.update)
        self.pv.committed.connect(self.update)

    # ------------------------------------------------------------------ vẽ

    def paint(self, p: QPainter) -> None:
        w, h = max(1, int(self.width())), max(1, int(self.height()))
        if self.pv.size().width() != w or self.pv.size().height() != h:
            self.pv.resize(w, h)
        self.pv.render(p, QPoint(0, 0), QRegion(),
                       QWidget.RenderFlag.DrawWindowBackground
                       | QWidget.RenderFlag.DrawChildren)

    def set_frame(self, pm: QPixmap) -> None:
        self.pv.frame = pm
        self.update()

    # ------------------------------------------------- chuyển tiếp sự kiện

    def _forward(self, ev, kind: QEvent.Type) -> None:
        pos = ev.position() if hasattr(ev, "position") else QPointF(ev.pos())
        me = QMouseEvent(kind, pos,
                         ev.globalPosition() if hasattr(ev, "globalPosition")
                         else QPointF(0, 0),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         ev.modifiers())
        self.pv.event(me)
        self.update()

    def mousePressEvent(self, ev) -> None:
        self._forward(ev, QEvent.Type.MouseButtonPress)

    def mouseMoveEvent(self, ev) -> None:
        self._forward(ev, QEvent.Type.MouseMove)

    def mouseReleaseEvent(self, ev) -> None:
        self._forward(ev, QEvent.Type.MouseButtonRelease)

    # ------------------------------------------------- API gọi được từ QML

    @pyqtSlot(str)
    def setTool(self, kind: str) -> None:
        """'' = chỉ chọn; blur / delogo / logo = vẽ vùng mới."""
        self.pv.tool = kind
        self.update()

    @pyqtSlot(result=str)
    def tool(self) -> str:
        return self.pv.tool

    @pyqtSlot(result=int)
    def selected(self) -> int:
        return self.pv.sel

    @pyqtSlot(result=bool)
    def deleteSelected(self) -> bool:
        i = self.pv.sel
        if 0 <= i < len(self.pv.proj.regions):
            self.pv.proj.regions.pop(i)
            self.pv.sel = -1
            self.regionCommitted.emit()
            self.update()
            return True
        return False
