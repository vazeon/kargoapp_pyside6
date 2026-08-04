# utils/mixins.py
from typing import List, Optional, Sequence

from PySide6.QtWidgets import QTableView, QWidget

import utils.zoom as zoom_helper


class ZoomTableMixin:
    """Mixin reusable untuk menyimpan lebar dasar kolom tabel saat zoom."""

    MIN_COLUMN_WIDTH = 20
    MAX_COLUMN_WIDTH = 100_000

    @classmethod
    def _lebar_kolom_aman(cls, value, default=100) -> int:
        """Mengubah nilai lebar menjadi integer aman sebelum dipakai Qt."""
        try:
            value = int(value)
        except (TypeError, ValueError, OverflowError):
            value = int(default)

        return max(
            cls.MIN_COLUMN_WIDTH,
            min(value, cls.MAX_COLUMN_WIDTH),
        )

    def _zoom_key(self, zoom_key: Optional[str] = None) -> str:
        """Menentukan key zoom tanpa mengikat mixin ke modul tertentu."""
        if zoom_key:
            return str(zoom_key).strip()

        key_khusus = getattr(self, "ZOOM_KEY", None)
        if key_khusus:
            return str(key_khusus).strip()

        return self.__class__.__name__

    def _faktor_zoom_aktif(
        self,
        zoom_key: Optional[str] = None,
    ) -> float:
        zoom = zoom_helper.dapatkan_zoom_level(
            self._zoom_key(zoom_key)
        )
        return max(
            0.68,
            min(1.0 + (zoom * 0.08), 1.80),
        )

    def _lebar_dasar_tabel(
        self,
        table: QTableView,
        zoom_key: Optional[str] = None,
    ) -> List[int]:
        faktor = self._faktor_zoom_aktif(zoom_key)

        if hasattr(table, "columnCount"):
            jumlah_kolom = int(table.columnCount())
        else:
            model = table.model()
            jumlah_kolom = model.columnCount() if model is not None else 0

        hasil = []
        for index in range(jumlah_kolom):
            try:
                width = round(table.columnWidth(index) / faktor)
            except (TypeError, ValueError, OverflowError, ZeroDivisionError):
                width = 100

            hasil.append(self._lebar_kolom_aman(width))

        return hasil

    def _perbarui_cache_lebar_zoom(
        self,
        table: QTableView,
        widths: Sequence[int],
    ) -> None:
        table._zoom_base_column_widths = {
            index: self._lebar_kolom_aman(width)
            for index, width in enumerate(widths)
        }

    def _set_style_dasar_zoom(
        self,
        widget: QWidget,
        stylesheet: str,
    ) -> None:
        widget.setStyleSheet(str(stylesheet or ""))

        if hasattr(widget, "_zoom_base_stylesheet"):
            delattr(widget, "_zoom_base_stylesheet")
