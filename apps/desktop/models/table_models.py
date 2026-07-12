"""Qt table models over service dataclasses (TDD 8.2 Model/View).

These are the only place Qt touches service data. Each model takes a list of
plain dataclasses and exposes them as rows/columns. Kept tiny and declarative.
"""
from __future__ import annotations

from dataclasses import astuple, fields
from typing import Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class DataclassTableModel(QAbstractTableModel):
    """Generic read-only table model over a homogeneous list of dataclasses."""

    def __init__(self, rows: Sequence[object], columns: Sequence[str] | None = None,
                 headers: Sequence[str] | None = None) -> None:
        super().__init__()
        self._rows = list(rows)
        if self._rows:
            all_fields = [f.name for f in fields(self._rows[0])]
        else:
            all_fields = list(columns or [])
        self._columns = list(columns) if columns else all_fields
        self._headers = list(headers) if headers else [
            c.replace("_", " ").title() for c in self._columns]

    def set_rows(self, rows: Sequence[object]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_object(self, row: int) -> object | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        obj = self._rows[index.row()]
        value = getattr(obj, self._columns[index.column()], "")
        if isinstance(value, (list, dict)):
            return ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        return "" if value is None else str(value)

    def headerData(self, section: int, orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._headers):
            return self._headers[section]
        return str(section + 1)
