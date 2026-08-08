# utils/table_helper.py
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTableWidgetItem


def _warna_valid(warna: Optional[str]) -> Optional[QColor]:
    """Membuat QColor hanya ketika nilai warna valid."""
    if not warna:
        return None
    hasil = QColor(str(warna))
    return hasil if hasil.isValid() else None


def buat_tabel_item(
    text: Any,
    editable: bool = True,
    alignment: Optional[int] = None,
    bg_color: Optional[str] = None,
    fg_color: Optional[str] = None,
) -> QTableWidgetItem:
    """Membuat ``QTableWidgetItem`` dengan konfigurasi umum."""
    item = QTableWidgetItem("" if text is None else str(text))
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if alignment is not None:
        item.setTextAlignment(int(alignment))

    for warna, setter in ((bg_color, item.setBackground), (fg_color, item.setForeground)):
        warna_valid = _warna_valid(warna)
        if warna_valid is not None:
            setter(QBrush(warna_valid))
    return item