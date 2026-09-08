# -*- coding: utf-8 -*-
"""Model danh sách đưa sang QML cho ListView dùng.

QML không đọc được list Python thẳng khi cần sửa từng dòng, nên gói qua
QAbstractListModel. Đổi một dòng chỉ phát tín hiệu cho đúng dòng đó, danh
sách vài nghìn câu vẫn cuộn mượt.
"""

from __future__ import annotations

from typing import List, Sequence

from PyQt6.QtCore import (QAbstractListModel, QModelIndex, Qt, pyqtSignal,
                          pyqtSlot)

from .srtutil import Cue, fmt_ts, parse_ts


class CueModel(QAbstractListModel):
    """Danh sách phụ đề: sửa lời thoại và mốc thời gian ngay trong QML."""

    StartRole = Qt.ItemDataRole.UserRole + 1
    EndRole = Qt.ItemDataRole.UserRole + 2
    TextRole = Qt.ItemDataRole.UserRole + 3
    NumRole = Qt.ItemDataRole.UserRole + 4

    edited = pyqtSignal()

    def __init__(self, cues: Sequence[Cue] | None = None, parent=None):
        super().__init__(parent)
        self._cues: List[Cue] = list(cues or [])

    def roleNames(self):
        return {
            self.StartRole: b"start",
            self.EndRole: b"end",
            self.TextRole: b"line",
            self.NumRole: b"num",
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._cues)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._cues)):
            return None
        c = self._cues[index.row()]
        if role == self.StartRole:
            return fmt_ts(c.start)
        if role == self.EndRole:
            return fmt_ts(c.end)
        if role == self.TextRole:
            return c.text
        if role == self.NumRole:
            return index.row() + 1
        return None

    # ---------------------------------------------------- gọi từ QML

    @pyqtSlot(int, str)
    def setLine(self, row: int, text: str) -> None:
        if 0 <= row < len(self._cues) and self._cues[row].text != text:
            self._cues[row].text = text
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [self.TextRole])
            self.edited.emit()

    @pyqtSlot(int, str, str, result=bool)
    def setTimes(self, row: int, start: str, end: str) -> bool:
        """Trả về False nếu gõ sai định dạng — QML tự trả lại giá trị cũ."""
        if not (0 <= row < len(self._cues)):
            return False
        try:
            a, b = parse_ts(start), parse_ts(end)
        except Exception:
            return False
        if b - a < 0.05:
            return False
        self._cues[row].start, self._cues[row].end = a, b
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [self.StartRole, self.EndRole])
        self.edited.emit()
        return True

    @pyqtSlot(int, result=float)
    def startOf(self, row: int) -> float:
        return self._cues[row].start if 0 <= row < len(self._cues) else 0.0

    @pyqtSlot(float, result=int)
    def rowAt(self, t: float) -> int:
        for i, c in enumerate(self._cues):
            if c.start <= t <= c.end:
                return i
        return -1

    def cues(self) -> List[Cue]:
        return self._cues

    def reset(self, cues: Sequence[Cue]) -> None:
        self.beginResetModel()
        self._cues = list(cues)
        self.endResetModel()
