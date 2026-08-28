# utils/table_helper.py
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)


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
    """Membuat QTableWidgetItem dengan konfigurasi umum."""
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


def setup_tabel_modern(
        tabel: QTableWidget,
        *,
        row_height: int = 28,
        stretch_last_column: bool = True,
        hide_row_numbers: bool = True,
) -> None:
    """Terapkan konfigurasi perilaku data dan fungsional standar untuk QTableWidget.

    Catatan: Seluruh aturan styling (border, warna hover, font, scrollbar)
    diserahkan sepenuhnya ke sistem tema di folder themes/.
    """
    # 1. Aktifkan fitur alternating rows (warna otomatis diatur oleh tema)
    tabel.setAlternatingRowColors(True)

    # 2. Perilaku Seleksi & Scroll (Standar Enterprise Desktop)
    tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tabel.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    tabel.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    tabel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tabel.setMouseTracking(False)

    # 3. Konfigurasi Header Kolom (Horizontal)
    h_header = tabel.horizontalHeader()
    h_header.setStretchLastSection(stretch_last_column)
    h_header.setHighlightSections(False)
    h_header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # 4. Konfigurasi Header Baris (Vertikal)
    v_header = tabel.verticalHeader()
    v_header.setDefaultSectionSize(row_height)
    v_header.setHighlightSections(False)
    if hide_row_numbers:
        v_header.setVisible(False)