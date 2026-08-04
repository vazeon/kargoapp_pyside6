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
    """
    Membuat ``QTableWidgetItem`` dengan konfigurasi umum dalam satu fungsi.

    Nilai ``None`` diubah menjadi string kosong. Warna yang tidak valid
    diabaikan agar helper tidak menghasilkan item dengan brush invalid.
    """
    item = QTableWidgetItem(
        "" if text is None else str(text)
    )

    if not editable:
        item.setFlags(
            item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )

    if alignment is not None:
        item.setTextAlignment(int(alignment))

    warna_latar = _warna_valid(bg_color)
    if warna_latar is not None:
        item.setBackground(QBrush(warna_latar))

    warna_teks = _warna_valid(fg_color)
    if warna_teks is not None:
        item.setForeground(QBrush(warna_teks))

    return item
