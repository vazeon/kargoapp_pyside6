# utils/table_helper.py
from typing import Any, Iterable, Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
)


def atur_editor_sel(widget: QLineEdit) -> None:
    """Lepaskan tinggi formulir agar editor mengikuti ruang sel tabel.

    Panggil untuk QLineEdit yang akan dipasang lewat setCellWidget().
    Fungsi ini tidak mengubah warna, validator, isi, signal, atau fokus.
    """
    widget.setProperty("_ui_scaler_explicit_geometry", False)
    widget.setProperty("_ui_base_min_height", None)
    widget.setProperty("_ui_base_max_height", None)
    widget.setMinimumHeight(0)
    widget.setMaximumHeight(16_777_215)
    widget.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
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
    h_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

    # 4. Konfigurasi Header Baris (Vertikal)
    v_header = tabel.verticalHeader()
    v_header.setDefaultSectionSize(row_height)
    v_header.setHighlightSections(False)
    if hide_row_numbers:
        v_header.setVisible(False)



class ModelTableModel(QAbstractTableModel):
    """Flat table model with compact tuple-backed rows and optional row colors."""

    def __init__(self, headers: Sequence[str] = (), parent=None):
        super().__init__(parent)
        self._headers = list(headers or ())
        self._rows: list[tuple] = []
        self._search_rows: list[tuple[str, ...]] = []
        self._alignments: tuple = ()
        self._row_backgrounds: dict[int, object] = {}
        self._row_foregrounds: dict[int, object] = {}
        self._tooltips: dict[tuple[int, int], str] = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if not (0 <= row < len(self._rows) and 0 <= col < len(self._headers)):
            return None

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            value = self._rows[row][col]
            return "" if value is None else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col < len(self._alignments) and self._alignments[col] is not None:
                return int(self._alignments[col])
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole:
            return self._row_backgrounds.get(row)
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._row_foregrounds.get(row)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltips.get((row, col))
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        # Edit dilakukan melalui dialog/panel, bukan perubahan langsung pada sel.
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self._headers):
            return self._headers[section]
        return None

    def setHeaders(self, headers: Sequence[str]):
        headers = list(headers or ())
        if headers == self._headers:
            return
        self.beginResetModel()
        self._headers = headers
        self._rows = [tuple(row[:len(headers)]) for row in self._rows]
        self._search_rows = [tuple(str(value or "").casefold() for value in row) for row in self._rows]
        self._row_backgrounds.clear()
        self._row_foregrounds.clear()
        self._tooltips.clear()
        self.endResetModel()

    def setColumnCount(self, count: int):
        count = max(0, int(count))
        if count == len(self._headers):
            return
        self.beginResetModel()
        self._headers = (self._headers[:count] + [""] * max(0, count - len(self._headers)))
        self._rows = []
        self._search_rows = []
        self._row_backgrounds.clear()
        self._row_foregrounds.clear()
        self._tooltips.clear()
        self.endResetModel()

    def setRows(
        self,
        rows: Iterable[Sequence],
        *,
        alignments: Optional[Sequence] = None,
        row_backgrounds: Optional[dict[int, object]] = None,
        row_foregrounds: Optional[dict[int, object]] = None,
    ):
        prepared = []
        count = len(self._headers)
        for row in rows or ():
            values = tuple(row or ())
            if len(values) < count:
                values += ("",) * (count - len(values))
            elif len(values) > count:
                values = values[:count]
            prepared.append(values)

        self.beginResetModel()
        self._rows = prepared
        self._search_rows = [
            tuple(str(value or "").casefold() for value in row)
            for row in prepared
        ]
        if alignments is not None:
            self._alignments = tuple(alignments)
        self._row_backgrounds = dict(row_backgrounds or {})
        self._row_foregrounds = dict(row_foregrounds or {})
        self._tooltips.clear()
        self.endResetModel()

    def rowValues(self, row: int) -> tuple:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return ()

    def valueAt(self, row: int, column: int) -> str:
        if 0 <= row < len(self._rows) and 0 <= column < len(self._headers):
            value = self._rows[row][column]
            return "" if value is None else str(value)
        return ""

    def setRowValues(
        self,
        row: int,
        values: Sequence,
        *,
        background=None,
        foreground=None,
    ) -> bool:
        if not (0 <= row < len(self._rows)):
            return False
        prepared = tuple(values or ())
        count = len(self._headers)
        if len(prepared) < count:
            prepared += ("",) * (count - len(prepared))
        elif len(prepared) > count:
            prepared = prepared[:count]
        self._rows[row] = prepared
        self._search_rows[row] = tuple(str(value or "").casefold() for value in prepared)
        if background is None:
            self._row_backgrounds.pop(row, None)
        else:
            self._row_backgrounds[row] = background
        if foreground is None:
            self._row_foregrounds.pop(row, None)
        else:
            self._row_foregrounds[row] = foreground
        if count:
            self.dataChanged.emit(
                self.index(row, 0),
                self.index(row, count - 1),
                [int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.BackgroundRole), int(Qt.ItemDataRole.ForegroundRole)],
            )
        return True

    def setCell(self, row: int, column: int, value) -> bool:
        if not (0 <= row < len(self._rows) and 0 <= column < len(self._headers)):
            return False
        values = list(self._rows[row])
        values[column] = "" if value is None else str(value)
        self._rows[row] = tuple(values)
        search_values = list(self._search_rows[row])
        search_values[column] = str(values[column] or "").casefold()
        self._search_rows[row] = tuple(search_values)
        index = self.index(row, column)
        self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DisplayRole)])
        return True

    def insertRows(self, row, count=1, parent=QModelIndex()):
        if parent.isValid() or count <= 0 or row < 0 or row > len(self._rows):
            return False
        empty = tuple("" for _ in self._headers)
        self.beginInsertRows(parent, row, row + count - 1)
        self._rows[row:row] = [empty] * count
        self._search_rows[row:row] = [tuple("" for _ in self._headers)] * count
        self.endInsertRows()
        return True

    def removeRows(self, row, count=1, parent=QModelIndex()):
        if parent.isValid() or count <= 0 or row < 0 or row + count > len(self._rows):
            return False
        self.beginRemoveRows(parent, row, row + count - 1)
        del self._rows[row:row + count]
        del self._search_rows[row:row + count]
        self.endRemoveRows()
        self._row_backgrounds = {
            (r if r < row else r - count): value
            for r, value in self._row_backgrounds.items()
            if r < row or r >= row + count
        }
        self._row_foregrounds = {
            (r if r < row else r - count): value
            for r, value in self._row_foregrounds.items()
            if r < row or r >= row + count
        }
        return True

    def searchText(self, row: int, columns: Optional[Sequence[int]] = None) -> str:
        if not (0 <= row < len(self._rows)):
            return ""
        values = self._search_rows[row]
        if columns is None:
            return " ".join(values)
        return " ".join(
            values[col]
            for col in columns
            if 0 <= col < len(values)
        )


class ModelCellProxy:
    """Small compatibility adapter for legacy code that reads table.item()."""

    __slots__ = ("_table", "_row", "_column")

    def __init__(self, table: "ModelTableView", row: int, column: int):
        self._table = table
        self._row = row
        self._column = column

    def _index(self):
        return self._table.model().index(self._row, self._column)

    def text(self) -> str:
        return self._table.model().valueAt(self._row, self._column)

    def setText(self, value):
        return self._table.model().setCell(self._row, self._column, value)

    def data(self, role=Qt.ItemDataRole.UserRole):
        return self._table.model().data(self._index(), role)

    def setData(self, value, role=Qt.ItemDataRole.EditRole):
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self.setText(value)
        return False

    def row(self):
        return self._row

    def column(self):
        return self._column

    def isSelected(self):
        selection = self._table.selectionModel()
        return bool(selection and selection.isSelected(self._index()))


class ModelTableView(QTableView):
    """QTableView convenience wrapper backed exclusively by ModelTableModel."""

    def __init__(self, headers: Sequence[str] = (), parent=None):
        super().__init__(parent)
        self._table_model = ModelTableModel(headers, self)
        self.setModel(self._table_model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setAlternatingRowColors(True)
        self.setMouseTracking(False)

    def rowCount(self):
        return self._table_model.rowCount()

    def columnCount(self):
        return self._table_model.columnCount()

    def setColumnCount(self, count):
        self._table_model.setColumnCount(count)

    def setHorizontalHeaderLabels(self, labels):
        self._table_model.setHeaders(labels)

    def setRowCount(self, count):
        count = max(0, int(count))
        headers = self._table_model._headers
        self._table_model.setRows([tuple("" for _ in headers) for _ in range(count)])

    def insertRow(self, row):
        return self._table_model.insertRows(row, 1)

    def removeRow(self, row):
        return self._table_model.removeRows(row, 1)

    def setRows(self, rows, *, alignments=None, row_backgrounds=None, row_foregrounds=None):
        self._table_model.setRows(
            rows,
            alignments=alignments,
            row_backgrounds=row_backgrounds,
            row_foregrounds=row_foregrounds,
        )

    def setRowValues(self, row, values, *, background=None, foreground=None):
        return self._table_model.setRowValues(
            row, values, background=background, foreground=foreground
        )

    def item(self, row, column):
        if not (0 <= row < self.rowCount() and 0 <= column < self.columnCount()):
            return None
        return ModelCellProxy(self, row, column)

    def setItem(self, row, column, item):
        if item is None or not (0 <= row < self.rowCount() and 0 <= column < self.columnCount()):
            return
        text_getter = getattr(item, "text", None)
        value = text_getter() if callable(text_getter) else str(item)
        self._table_model.setCell(row, column, value)

    def itemAt(self, position):
        index = self.indexAt(position)
        if not index.isValid():
            return None
        return ModelCellProxy(self, index.row(), index.column())

    def currentRow(self):
        index = self.currentIndex()
        return index.row() if index.isValid() else -1

    def currentColumn(self):
        index = self.currentIndex()
        return index.column() if index.isValid() else -1

    def searchText(self, row, columns=None):
        return self._table_model.searchText(row, columns)


__all__ = ["ModelTableModel", "ModelTableView", "ModelCellProxy"]

__all__ = [
    "atur_editor_sel",
    "buat_tabel_item",
    "setup_tabel_modern",
    "ModelTableModel",
    "ModelTableView",
    "ModelCellProxy",
]
