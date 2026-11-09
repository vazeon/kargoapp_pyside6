# tabs/tab_buku_gudang.py
from collections import OrderedDict
from enum import Enum
from datetime import datetime
from time import perf_counter
from weakref import ref
from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QEvent,
    QSettings,
    QLocale,
    QTimer,
    Qt,
    QThread,
    Signal,
    Slot,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
)
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCompleter,
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStyledItemDelegate,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from config import CURRENT_SESSION, DATA_CLIENT

import services.database_service as db_service

from utils import zoom as zoom_helper
from utils.frozen_table_helper import FrozenTableView
from utils.smooth_scroll_helper import pasang_scroll_halus
from utils.typography import (
    APPLICATION_NAME,
    ORGANIZATION_NAME,
    get_fixed_font_sizes,
    konversi_font_qss_ke_point,
    konversi_style_font_ke_point,
)
from utils.number_formatters import (
    format_ke_rupiah,
    rupiah_to_int,
    format_angka_indonesia,
    format_decimal_indonesia,
    angka_indonesia_to_decimal,
)
from utils.date_ind_format import format_tanggal_ke_ui
from utils.table_helper import atur_editor_sel, setup_tabel_modern
from utils.validators import UppercaseValidator, get_decimal_validator, get_integer_validator
from themes.modules.buku_gudang import (
    get_buku_gudang_action_styles,
    get_buku_gudang_tabbar_styles,
    get_buku_gudang_menu_style,
    get_buku_gudang_styles,
    get_buku_gudang_tooltip_style,
    get_buku_gudang_status_colors,
    get_dialog_pilih_penagih_styles,
)
from utils.input_style_helper import paksa_kapital_lineedit, terapkan_style_input_global

BUKU_GUDANG_DIALOG_PENAGIH_MIN_WIDTH = 350
BUKU_GUDANG_DIALOG_ACTION_GAP = 10
BUKU_GUDANG_HEADER_MARGINS = (8, 0, 8, 0)
BUKU_GUDANG_HEADER_SPACING = 6
BUKU_GUDANG_PRIMARY_ROW_SPACING = 8
BUKU_GUDANG_SEARCH_WIDTH = 340
BUKU_GUDANG_HEADER_CONTROL_HEIGHT = 32
BUKU_GUDANG_YEAR_BUTTON_SIZE = (90, 30)
BUKU_GUDANG_MONTH_BUTTON_SIZE = (115, 30)
BUKU_GUDANG_BILLING_STATUS_BUTTON_SIZE = (140, 30)
BUKU_GUDANG_RESET_FILTER_BUTTON_SIZE = (82, 30)
BUKU_GUDANG_MONTH_CHECKBOX_MIN_WIDTH = 170
BUKU_GUDANG_MAIN_MARGINS = (0, 6, 0, 0)
BUKU_GUDANG_MAIN_SPACING = 6
BUKU_GUDANG_TABLE_TAB_MARGINS = (6, 6, 6, 6)
BUKU_GUDANG_DEFAULT_COLUMN_WIDTHS = (
    115,  # RESI
    95,   # MASUK
    95,   # KELUAR
    115,  # STATUS RESI
    230,  # STATUS PENAGIHAN
    165,  # TRUK
    180,  # PENGIRIM
    130,  # KOTA ASAL
    180,  # PENERIMA
    135,  # KOTA TUJUAN
    180,  # NAMA BARANG
    70,   # KOLI
    90,   # BERAT
    90,   # CBM
    125,  # ONGKIR
    120,  # PAYMENT
    220,  # KETERANGAN
)
BUKU_GUDANG_COLUMN_WIDTH_MIN = 20
BUKU_GUDANG_COLUMN_WIDTH_MAX = 1500
BUKU_GUDANG_FALLBACK_COLUMN_WIDTH = 110
BUKU_GUDANG_TABLE_ROW_BASE_HEIGHT = 28
BUKU_GUDANG_AUTOCOMPLETE_MAX_VISIBLE_ITEMS = 12

class _BukuGudangRow:
    """Satu resi dalam slot tetap; tidak membuat objek Qt untuk setiap sel."""

    __slots__ = (
        "values", "no_resi", "detail_id", "revision", "invoice_no",
        "invoice_status", "status_highlight", "detail_rows",
        "search_text", "tooltips",
    )

    def __init__(self, values, roles=None, tooltips=None):
        roles = roles or {}
        # DisplayRole selalu berupa teks. Normalisasi sekali saat row dibuat,
        # bukan mengonversi nilai pada setiap siklus paint.
        self.values = tuple("" if value is None else str(value) for value in values)
        self.no_resi = roles.get(TabBukuGudang.ROLE_NO_RESI)
        self.detail_id = roles.get(TabBukuGudang.ROLE_DETAIL_ID)
        self.revision = roles.get(TabBukuGudang.ROLE_REVISION)
        self.invoice_no = roles.get(TabBukuGudang.ROLE_INVOICE_NO)
        self.invoice_status = roles.get(TabBukuGudang.ROLE_INVOICE_STATUS)
        self.status_highlight = roles.get(TabBukuGudang.ROLE_STATUS_HIGHLIGHT)
        self.detail_rows = roles.get(TabBukuGudang.ROLE_DETAIL_ROWS)
        self.search_text = str(roles.get(TabBukuGudang.ROLE_SEARCH_TEXT, "") or "")
        self.tooltips = dict(tooltips) if tooltips else None

    def role_value(self, role):
        if role == TabBukuGudang.ROLE_NO_RESI:
            return self.no_resi
        if role == TabBukuGudang.ROLE_DETAIL_ID:
            return self.detail_id
        if role == TabBukuGudang.ROLE_REVISION:
            return self.revision
        if role == TabBukuGudang.ROLE_INVOICE_NO:
            return self.invoice_no
        if role == TabBukuGudang.ROLE_INVOICE_STATUS:
            return self.invoice_status
        if role == TabBukuGudang.ROLE_STATUS_HIGHLIGHT:
            return self.status_highlight
        if role == TabBukuGudang.ROLE_DETAIL_ROWS:
            return self.detail_rows
        if role == TabBukuGudang.ROLE_SEARCH_TEXT:
            return self.search_text
        return None

    def set_role_value(self, role, value):
        if role == TabBukuGudang.ROLE_NO_RESI:
            self.no_resi = value
        elif role == TabBukuGudang.ROLE_DETAIL_ID:
            self.detail_id = value
        elif role == TabBukuGudang.ROLE_REVISION:
            self.revision = value
        elif role == TabBukuGudang.ROLE_INVOICE_NO:
            self.invoice_no = value
        elif role == TabBukuGudang.ROLE_INVOICE_STATUS:
            self.invoice_status = value
        elif role == TabBukuGudang.ROLE_STATUS_HIGHLIGHT:
            self.status_highlight = value
        elif role == TabBukuGudang.ROLE_DETAIL_ROWS:
            self.detail_rows = value
        elif role == TabBukuGudang.ROLE_SEARCH_TEXT:
            self.search_text = str(value or "")
        else:
            return False
        return True


class BukuGudangTableModel(QAbstractTableModel):
    """Model tabel Buku Gudang yang hanya menyimpan data, bukan item per sel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._headers = []
        self._rows = []
        self._column_count = 0
        self._alignments = ()
        self._pending_first_row = None
        self._pending_last_row = None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._column_count

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row_number = index.row()
        column = index.column()
        if row_number < 0 or row_number >= len(self._rows):
            return None
        row = self._rows[row_number]
        if row is None or column < 0 or column >= self._column_count:
            return None

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return row.values[column]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column < len(self._alignments):
                return self._alignments[column]
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        if role == Qt.ItemDataRole.ToolTipRole:
            return row.tooltips.get(column) if row.tooltips is not None else None
        if role == TabBukuGudang.ROLE_STATUS_HIGHLIGHT:
            return row.status_highlight
        if role == TabBukuGudang.ROLE_DETAIL_COUNT:
            return len(row.detail_rows) if row.detail_rows else 1
        if column == 0:
            return row.role_value(int(role))
        return None

    def displayTextAt(self, row_number, column):
        """Akses teks tampilan langsung tanpa round-trip QModelIndex.data()."""
        if not (0 <= row_number < len(self._rows) and 0 <= column < self._column_count):
            return ""
        row = self._rows[row_number]
        if row is None:
            return ""
        return row.values[column]

    def statusHighlightAt(self, row_number):
        """Ambil status satu kali per baris tanpa meminta role Qt untuk setiap sel."""
        if 0 <= row_number < len(self._rows):
            row = self._rows[row_number]
            return row.status_highlight if row is not None else None
        return None

    def alignmentAt(self, column):
        """Ambil alignment kolom yang statis untuk cache delegate."""
        if 0 <= column < len(self._alignments):
            return self._alignments[column]
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False

        row_number = index.row()
        column = index.column()
        if (
            row_number < 0
            or row_number >= len(self._rows)
            or column < 0
            or column >= self._column_count
        ):
            return False

        role_id = int(role)
        is_display_role = role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole,
        )
        is_tooltip_role = role == Qt.ItemDataRole.ToolTipRole
        is_writable_row_role = (
            column == 0 and role_id in TabBukuGudang.MODEL_WRITABLE_ROLES
        )

        # Jangan menerima role yang tidak disimpan model atau metadata turunan.
        if not (is_display_role or is_tooltip_role or is_writable_row_role):
            return False

        row = self._rows[row_number]
        if row is None:
            row = _BukuGudangRow([""] * self._column_count)
            self._rows[row_number] = row

        if is_display_role:
            values = list(row.values)
            values[column] = str(value or "")
            row.values = tuple(values)
        elif is_tooltip_role:
            if value is None:
                if row.tooltips is not None:
                    row.tooltips.pop(column, None)
            else:
                if row.tooltips is None:
                    row.tooltips = {}
                row.tooltips[column] = str(value)
        elif not row.set_role_value(role_id, value):
            return False

        self.dataChanged.emit(index, index, [role_id])
        return True

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self._headers):
            return self._headers[section]
        return None

    def setColumnCount(self, count):
        count = max(0, int(count))
        self.beginResetModel()
        self._column_count = count
        self._headers = (self._headers[:count] + [""] * max(0, count - len(self._headers)))
        self._rows = []
        self._pending_first_row = None
        self._pending_last_row = None
        self.endResetModel()

    def setHeaders(self, labels):
        self._headers = list(labels or [])[:self._column_count]
        if self._headers:
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(self._headers) - 1)

    def setAlignments(self, alignments):
        self._alignments = tuple(alignments or ())

    def setRowCount(self, count):
        count = max(0, int(count))
        self.beginResetModel()
        self._rows = [None] * count
        self._pending_first_row = None
        self._pending_last_row = None
        self.endResetModel()

    def insertRows(self, row, count=1, parent=QModelIndex()):
        if parent.isValid() or count <= 0 or row < 0 or row > len(self._rows):
            return False
        self.beginInsertRows(parent, row, row + count - 1)
        self._rows[row:row] = [None] * count
        self.endInsertRows()
        return True

    def removeRows(self, row, count=1, parent=QModelIndex()):
        if parent.isValid() or count <= 0 or row < 0 or row + count > len(self._rows):
            return False
        self.beginRemoveRows(parent, row, row + count - 1)
        del self._rows[row:row + count]
        self.endRemoveRows()
        return True

    def setRowData(self, row_number, values, roles=None, tooltips=None):
        if row_number < 0 or row_number >= len(self._rows):
            return False
        self._rows[row_number] = _BukuGudangRow(values, roles, tooltips)
        if self._pending_first_row is None:
            self._pending_first_row = row_number
            self._pending_last_row = row_number
        else:
            self._pending_first_row = min(self._pending_first_row, row_number)
            self._pending_last_row = max(self._pending_last_row, row_number)
        return True

    def flushPendingChanges(self):
        """Kirim satu sinyal perubahan untuk semua baris pada batch render."""
        first_row = self._pending_first_row
        last_row = self._pending_last_row
        self._pending_first_row = None
        self._pending_last_row = None
        if first_row is None or last_row is None or self._column_count <= 0:
            return
        self.dataChanged.emit(
            self.index(first_row, 0),
            self.index(last_row, self._column_count - 1),
            [],
        )

    def hasRowData(self, row_number):
        return 0 <= row_number < len(self._rows) and self._rows[row_number] is not None

    def searchText(self, row_number):
        if 0 <= row_number < len(self._rows):
            row = self._rows[row_number]
            return row.search_text if row is not None else ""
        return ""

    def detailCountAt(self, row_number):
        if 0 <= row_number < len(self._rows):
            row = self._rows[row_number]
            return len(row.detail_rows) if row is not None and row.detail_rows else 1
        return 1

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if not 0 <= column < self._column_count:
            return
        reverse = order == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        self._rows.sort(
            key=lambda row: (row.values[column] if row is not None else ""),
            reverse=reverse,
        )
        self.layoutChanged.emit()

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class _BukuGudangItemProxy:
    """Adapter ringan agar helper lama yang membaca item tetap kompatibel."""

    __slots__ = ("_table", "_row", "_column")

    def __init__(self, table, row, column):
        self._table = table
        self._row = row
        self._column = column

    def _index(self):
        return self._table.model().index(self._row, self._column)

    def text(self):
        value = self._table.model().data(self._index(), Qt.ItemDataRole.DisplayRole)
        return str(value or "")

    def setText(self, value):
        return self.setData(value, Qt.ItemDataRole.DisplayRole)

    def data(self, role=Qt.ItemDataRole.UserRole):
        return self._table.model().data(self._index(), role)

    def setData(self, value, role=Qt.ItemDataRole.UserRole):
        return self._table.model().setData(self._index(), value, role)

    def setToolTip(self, value):
        return self.setData(value, Qt.ItemDataRole.ToolTipRole)

    def row(self):
        return self._row

    def column(self):
        return self._column

    def isSelected(self):
        selection = self._table.selectionModel()
        return bool(selection and selection.isSelected(self._index()))


class BukuGudangTableView(FrozenTableView):
    """QTableView dengan adapter API minimal untuk kompatibilitas TabBukuGudang."""

    def __init__(self, parent=None):
        # Bekukan kolom RESI (kolom pertama), sama seperti implementasi
        # FrozenTableWidget pada versi Buku Gudang sebelumnya.
        super().__init__(parent, frozen_cols=1)
        self._buku_gudang_model = BukuGudangTableModel(self)
        self.setModel(self._buku_gudang_model)

    def setColumnCount(self, count):
        self._buku_gudang_model.setColumnCount(count)
        self.sync_frozen_columns()

    def setHorizontalHeaderLabels(self, labels):
        self._buku_gudang_model.setHeaders(labels)

    def setRowCount(self, count):
        self._buku_gudang_model.setRowCount(count)

    def rowCount(self):
        return self._buku_gudang_model.rowCount()

    def columnCount(self):
        return self._buku_gudang_model.columnCount()

    def insertRow(self, row):
        return self._buku_gudang_model.insertRows(row, 1)

    def removeRow(self, row):
        return self._buku_gudang_model.removeRows(row, 1)

    def setRowData(self, row, values, roles=None, tooltips=None):
        return self._buku_gudang_model.setRowData(row, values, roles, tooltips)

    def searchText(self, row):
        return self._buku_gudang_model.searchText(row)

    def item(self, row, column):
        if not self._buku_gudang_model.hasRowData(row) or not (0 <= column < self.columnCount()):
            return None
        return _BukuGudangItemProxy(self, row, column)

    def setItem(self, row, column, item):
        if item is None or not (0 <= row < self.rowCount() and 0 <= column < self.columnCount()):
            return
        proxy = _BukuGudangItemProxy(self, row, column)
        proxy.setText(item.text())

    def itemAt(self, position):
        index = self.indexAt(position)
        if not index.isValid():
            return None
        return _BukuGudangItemProxy(self, index.row(), index.column())

    def selectedItems(self):
        return [
            _BukuGudangItemProxy(self, index.row(), index.column())
            for index in self.selectedIndexes()
            if index.isValid()
        ]

    def setCellWidget(self, row, column, widget):
        index = self.model().index(row, column)
        if index.isValid():
            self.setIndexWidget(index, widget)

    def cellWidget(self, row, column):
        index = self.model().index(row, column)
        return self.indexWidget(index) if index.isValid() else None

    def currentRow(self):
        index = self.currentIndex()
        return index.row() if index.isValid() else -1

    def currentColumn(self):
        index = self.currentIndex()
        return index.column() if index.isValid() else -1


class BukuGudangFastPaintDelegate(QStyledItemDelegate):
    """Delegate paint ringan dengan cache metadata per baris/kolom."""

    PADDING_LEFT = 6
    PADDING_RIGHT = 6

    def __init__(self, parent=None, *, is_dark=False, status_role=None):
        super().__init__(parent)
        self._is_dark = bool(is_dark)
        self._status_role = (
            TabBukuGudang.ROLE_STATUS_HIGHLIGHT
            if status_role is None else int(status_role)
        )
        self._status_foreground_cache = {}
        self._row_foreground_cache = {}
        self._alignment_cache = {}
        # Hanya menyimpan layout multiline yang benar-benar pernah terlihat.
        # Batas tetap mencegah penggunaan RAM tumbuh mengikuti seluruh dataset.
        self._multiline_line_cache = OrderedDict()
        self._multiline_line_cache_limit = 4096
        # Simpan hanya nilai metrik font yang immutable, bukan wrapper QFont
        # dari QStyleOptionViewItem yang dapat kedaluwarsa setelah paint().
        self._line_pitch_metrics_key = None
        self._line_pitch_value = 0
        self._palette_cache_key = None
        self._palette_cache_values = None
        self._bound_model = None
        self._display_text_getter = None
        self._status_getter = None
        self._alignment_getter = None
        self._bind_model()

    def _bind_model(self):
        view = self.parent()
        model = view.model() if isinstance(view, QAbstractItemView) else None
        if model is None or model is self._bound_model:
            return
        self._bound_model = model
        # Simpan bound method sekali; paint() dipanggil berulang kali per sel.
        self._display_text_getter = getattr(model, "displayTextAt", None)
        self._status_getter = getattr(model, "statusHighlightAt", None)
        self._alignment_getter = getattr(model, "alignmentAt", None)
        # Role status dapat berubah melalui edit/status invoice; invalidasi cache
        # sekaligus untuk kedua view ketika model mengirim dataChanged.
        model.dataChanged.connect(self._invalidate_changed_rows)
        model.modelReset.connect(self._invalidate_paint_cache)
        model.rowsInserted.connect(self._invalidate_paint_cache)
        model.rowsRemoved.connect(self._invalidate_paint_cache)
        model.layoutChanged.connect(self._invalidate_paint_cache)

    def _invalidate_changed_rows(self, top_left=None, bottom_right=None, *_args):
        if top_left is None or bottom_right is None:
            self._row_foreground_cache.clear()
            self._multiline_line_cache.clear()
            return

        first_row = max(0, int(top_left.row()))
        last_row = max(first_row, int(bottom_right.row()))
        first_column = max(0, int(top_left.column()))
        last_column = max(first_column, int(bottom_right.column()))
        for row_number in range(first_row, last_row + 1):
            self._row_foreground_cache.pop(row_number, None)

        # Evict hanya layout sel yang berubah; cache sel lain tetap berguna
        # untuk horizontal scrolling berikutnya.
        for key in tuple(self._multiline_line_cache):
            row_number, column = key
            if (
                first_row <= row_number <= last_row
                and first_column <= column <= last_column
            ):
                self._multiline_line_cache.pop(key, None)

    def _invalidate_paint_cache(self, *_args):
        self._row_foreground_cache.clear()
        self._alignment_cache.clear()
        self._multiline_line_cache.clear()

    def set_theme(self, is_dark):
        is_dark = bool(is_dark)
        if self._is_dark == is_dark:
            return
        self._is_dark = is_dark
        self._status_foreground_cache.clear()
        self._row_foreground_cache.clear()
        self._palette_cache_key = None
        self._palette_cache_values = None
        view = self.parent()
        if isinstance(view, QAbstractItemView):
            view.viewport().update()

    @staticmethod
    def jarak_baris(font_metrics):
        """Jarak antardetail, mempertahankan spasi nyaman dari tampilan lama."""
        return font_metrics.lineSpacing() + max(3, round(font_metrics.height() * 0.25))

    def _status_foreground(self, index):
        row_number = index.row()
        if row_number in self._row_foreground_cache:
            cached = self._row_foreground_cache[row_number]
            return None if cached is False else cached

        getter = self._status_getter
        status = getter(row_number) if callable(getter) else index.data(self._status_role)
        if not status:
            self._row_foreground_cache[row_number] = False
            return None
        if not isinstance(status, str):
            status = str(status)

        is_alternate = bool(row_number & 1)
        # Helper tema hanya mengubah background berdasarkan parity; foreground
        # tetap sama. Karena delegate memakai background palette tabel, cache
        # foreground cukup memakai status sebagai key.
        cache_key = status
        color = self._status_foreground_cache.get(cache_key)
        if color is None:
            status_invoice, separator, status_resi = status.partition("|")
            if (
                separator
                and status_resi.strip() == "DI GUDANG"
                and status_invoice.strip() != "MACET"
            ):
                self._status_foreground_cache[cache_key] = False
                self._row_foreground_cache[row_number] = False
                return None

            _background, foreground = get_buku_gudang_status_colors(
                is_dark=self._is_dark,
                status=status,
                is_alternate_row=is_alternate,
            )
            if foreground is None:
                self._status_foreground_cache[cache_key] = False
                self._row_foreground_cache[row_number] = False
                return None
            self._status_foreground_cache[cache_key] = foreground
            color = foreground

        self._row_foreground_cache[row_number] = color
        # Batasi memori bila pengguna menelusuri tabel dengan baris sangat banyak.
        if len(self._row_foreground_cache) > 8192:
            self._row_foreground_cache.clear()
            self._row_foreground_cache[row_number] = color
        return color

    def _alignment_for(self, index):
        column = index.column()
        alignment = self._alignment_cache.get(column)
        if alignment is None:
            getter = self._alignment_getter
            alignment = getter(column) if callable(getter) else index.data(
                Qt.ItemDataRole.TextAlignmentRole
            )
            if alignment is None:
                alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            self._alignment_cache[column] = alignment
        return alignment

    def _palette_values(self, palette):
        """Cache brush/warna palette agar lookup tidak diulang pada setiap sel."""
        try:
            cache_key = (palette.cacheKey(), palette.currentColorGroup())
        except (AttributeError, RuntimeError):
            cache_key = None

        if cache_key is None:
            return (
                palette.brush(QPalette.ColorRole.Base),
                palette.brush(QPalette.ColorRole.AlternateBase),
                palette.brush(QPalette.ColorRole.Highlight),
                palette.color(QPalette.ColorRole.Text),
                palette.color(QPalette.ColorRole.HighlightedText),
            )

        if cache_key != self._palette_cache_key:
            self._palette_cache_key = cache_key
            self._palette_cache_values = (
                palette.brush(QPalette.ColorRole.Base),
                palette.brush(QPalette.ColorRole.AlternateBase),
                palette.brush(QPalette.ColorRole.Highlight),
                palette.color(QPalette.ColorRole.Text),
                palette.color(QPalette.ColorRole.HighlightedText),
            )
        return self._palette_cache_values

    def _multiline_lines(self, row_number, column, text):
        """Split teks multiline sekali per sel dengan cache LRU yang dibatasi."""
        key = (int(row_number), int(column))
        lines = self._multiline_line_cache.get(key)
        if lines is not None:
            self._multiline_line_cache.move_to_end(key)
            return lines

        lines = tuple(text.split("\n"))
        self._multiline_line_cache[key] = lines
        if len(self._multiline_line_cache) > self._multiline_line_cache_limit:
            self._multiline_line_cache.popitem(last=False)
        return lines

    def _line_pitch(self, painter):
        """Cache jarak baris tanpa menyimpan wrapper objek QFont dari Qt."""
        metrics = painter.fontMetrics()
        metrics_key = (metrics.lineSpacing(), metrics.height())
        if metrics_key != self._line_pitch_metrics_key:
            self._line_pitch_metrics_key = metrics_key
            self._line_pitch_value = self.jarak_baris(metrics)
        return self._line_pitch_value

    def paint(self, painter, option, index):
        row_number = index.row()
        column = index.column()
        # Ambil teks langsung melalui bound method yang disiapkan sekali saat
        # delegate dipasang, tanpa lookup atribut/dispatch role per sel.
        text_getter = self._display_text_getter
        value = (
            text_getter(row_number, column)
            if callable(text_getter)
            else index.data(Qt.ItemDataRole.DisplayRole)
        )
        text = value if isinstance(value, str) else ("" if value is None else str(value))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        (
            base_brush,
            alternate_brush,
            highlight_brush,
            text_color,
            highlighted_text_color,
        ) = self._palette_values(option.palette)

        if selected:
            background_brush = highlight_brush
            foreground = highlighted_text_color
        else:
            background_brush = alternate_brush if row_number & 1 else base_brush
            foreground = self._status_foreground(index)
            if foreground is None:
                foreground = text_color

        painter.save()
        try:
            # Pertahankan clipping pada batas sel agar teks multiline tidak
            # terpotong/terhapus oleh perubahan geometri painter.
            painter.setClipRect(option.rect)
            painter.fillRect(option.rect, background_brush)
            painter.setFont(option.font)
            painter.setPen(foreground)

            if not text:
                return

            text_rect = option.rect.adjusted(
                self.PADDING_LEFT, 0, -self.PADDING_RIGHT, 0
            )
            alignment = int(self._alignment_for(index))
            if "\n" not in text:
                painter.drawText(text_rect, alignment, text)
            else:
                # Geometri ini sengaja mengikuti jalur multiline yang sudah
                # terbukti benar pada Tahap 5. Cache hanya menghindari split()
                # berulang; koordinat tiap baris tetap dihitung dengan cara lama.
                lines = self._multiline_lines(row_number, column, text)
                line_pitch = self._line_pitch(painter)
                bottom = text_rect.bottom()
                for line_number, line in enumerate(lines):
                    top = text_rect.top() + line_number * line_pitch
                    if top > bottom:
                        break
                    line_rect = text_rect.adjusted(
                        0, line_number * line_pitch, 0, 0
                    )
                    line_rect.setHeight(
                        min(line_pitch + 8, bottom - top + 1)
                    )
                    painter.drawText(line_rect, alignment, line)
        finally:
            painter.restore()


class StatusTagihan(str, Enum):
    SEMUA = "SEMUA"
    BELUM_INVOICE = "BELUM INVOICE"
    BELUM_LUNAS = "BELUM LUNAS"
    LUNAS = "LUNAS"
    MACET = "MACET"


class DBIndex(int, Enum):
    RESI = 0
    MASUK = 1
    KELUAR = 2
    STATUS_RESI = 3
    TRUK = 4
    PENGIRIM = 5
    KOTA_ASAL = 6
    PENERIMA = 7
    KOTA_TUJUAN = 8
    NAMA_BARANG = 9
    KOLI = 10
    BERAT = 11
    CBM = 12
    ONGKIR = 13
    PAYMENT = 14
    KETERANGAN = 15
    DETAIL_ID = 16
    URUTAN = 17
    REVISION = 18
    NO_INVOICE = 19
    STATUS_INVOICE = 20
    TANGGAL_INVOICE = 21
    JUMLAH_INVOICE = 22
    NAMA_KAPAL = 23  # Metadata tampilan dari histori Manifest; bukan kolom Resi.


NAMA_BULAN = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)


def _kelompokkan_baris_resi(rows):
    """Kelompokkan detail berdasarkan resi dengan urutan sumber tetap terjaga."""
    grouped = {}
    for row in rows or ():
        no_resi = str(row[DBIndex.RESI] or "").strip()
        grouped.setdefault(no_resi, []).append(row)
    return list(grouped.values())


class DatabaseWorkerBukuGudang(QThread):
    """Satu query aktif per tab; umur worker mengikuti aplikasi."""

    _active_workers = set()
    data_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, kode_cabang, wilayah, tahun, filters):
        app = QApplication.instance()
        super().__init__(app)
        self.kode_cabang = kode_cabang
        self.wilayah = wilayah
        self.tahun = tahun
        self.filters = dict(filters)
        self._active_workers.add(self)
        self.finished.connect(self._selesai)
        if app is not None and not getattr(app, "_buku_gudang_shutdown_hook", False):
            app.aboutToQuit.connect(self._tunggu_worker_aktif)
            app._buku_gudang_shutdown_hook = True

    @Slot()
    def _selesai(self):
        self._active_workers.discard(self)
        self.deleteLater()

    @staticmethod
    def _tunggu_worker_aktif():
        for worker in tuple(DatabaseWorkerBukuGudang._active_workers):
            worker.requestInterruption()
            worker.wait()

    @db_service.profile_performance("BukuGudang.database_worker", threshold=0.05)
    def run(self):
        try:
            rows = db_service.ambil_data_buku_gudang(
                self.kode_cabang,
                self.wilayah,
                self.tahun,
                self.filters,
            ) or []

            if rows and not self.isInterruptionRequested():
                try:
                    tahun_keluar = {
                        str(row[DBIndex.KELUAR] or "").strip()[:4]
                        for row in rows
                        if len(row) > DBIndex.KELUAR
                        and str(row[DBIndex.KELUAR] or "").strip()[:4].isdigit()
                    }
                    histori_manifest = []
                    for tahun in sorted(tahun_keluar):
                        if self.isInterruptionRequested():
                            break
                        histori_manifest.extend(
                            db_service.ambil_histori_manifest(
                                self.kode_cabang,
                                tahun,
                            ) or []
                        )

                    kapal_by_trip = {}
                    trip_ambiguous = set()
                    for manifest in histori_manifest:
                        if len(manifest) < 4:
                            continue
                        tanggal = str(manifest[0] or "").strip()
                        truk = str(manifest[2] or "").strip().casefold()
                        nama_kapal = str(manifest[3] or "").strip().upper()
                        if not tanggal or not truk or not nama_kapal:
                            continue
                        key = (tanggal, truk)
                        existing = kapal_by_trip.get(key)
                        if existing is None:
                            kapal_by_trip[key] = nama_kapal
                        elif existing.casefold() != nama_kapal.casefold():
                            trip_ambiguous.add(key)

                    for key in trip_ambiguous:
                        kapal_by_trip.pop(key, None)

                    rows = [
                        tuple(row) + (
                            kapal_by_trip.get((
                                str(row[DBIndex.KELUAR] or "").strip(),
                                str(row[DBIndex.TRUK] or "").strip().casefold(),
                            ), ""),
                        )
                        for row in rows
                    ]
                except Exception:
                    rows = [tuple(row) + ("",) for row in rows]

            if not self.isInterruptionRequested():
                # Grouping is pure Python work and can be significant for a large
                # result set. Keep it in the worker so the GUI thread can stay
                # responsive and start its existing incremental render promptly.
                groups = _kelompokkan_baris_resi(rows)
                if not self.isInterruptionRequested():
                    self.data_ready.emit(groups)
        except Exception as e:
            self.error_occurred.emit(str(e))


class DialogPilihPenagih(QDialog):
    def __init__(self, nama_pengirim, nama_penerima, parent=None):
        super().__init__(parent)
        terapkan_style_input_global(self)
        self.setWindowTitle("Pilih Pihak Tertagih")
        self.setMinimumWidth(BUKU_GUDANG_DIALOG_PENAGIH_MIN_WIDTH)
        self.nama_pengirim = str(nama_pengirim or "").strip()
        self.nama_penerima = str(nama_penerima or "").strip()
        dialog_styles = konversi_style_font_ke_point(get_dialog_pilih_penagih_styles())
        self.setStyleSheet(dialog_styles["dialog"])
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Invoice ini akan ditagihkan kepada:</b>"))
        self.rb_pengirim = QRadioButton(f"Pengirim ({self.nama_pengirim})")
        self.rb_penerima = QRadioButton(f"Penerima ({self.nama_penerima})")
        self.rb_ketiga = QRadioButton("Pihak Ketiga:")
        self.rb_pengirim.setChecked(True)
        self.txt_ketiga = QLineEdit()
        self.txt_ketiga.setPlaceholderText("Ketik nama pihak ketiga...")
        self.txt_ketiga.setEnabled(False)
        self.txt_ketiga.setValidator(UppercaseValidator(self.txt_ketiga))
        self.rb_ketiga.toggled.connect(
            lambda: self.txt_ketiga.setEnabled(self.rb_ketiga.isChecked())
        )
        for widget in (
            self.rb_pengirim,
            self.rb_penerima,
            self.rb_ketiga,
            self.txt_ketiga,
        ):
            layout.addWidget(widget)
        layout.addSpacing(BUKU_GUDANG_DIALOG_ACTION_GAP)
        hbox_btn = QHBoxLayout()
        self.btn_lanjut = QPushButton("Lanjutkan ke Invoice")
        self.btn_lanjut.setStyleSheet(dialog_styles["btn_lanjut"])
        self.btn_batal = QPushButton("Batal")
        self.btn_batal.setStyleSheet(dialog_styles["btn_batal"])
        hbox_btn.addWidget(self.btn_lanjut)
        hbox_btn.addWidget(self.btn_batal)
        layout.addLayout(hbox_btn)
        self.btn_lanjut.clicked.connect(self.validasi_dan_lanjut)
        self.btn_batal.clicked.connect(self.reject)

    def validasi_dan_lanjut(self):
        if self.rb_ketiga.isChecked() and not self.txt_ketiga.text().strip():
            QMessageBox.warning(
                self,
                "Peringatan",
                "Nama Pihak Ketiga tidak boleh kosong!",
            )
            self.txt_ketiga.setFocus()
            return
        self.accept()

    def get_nama_client(self):
        if self.rb_pengirim.isChecked():
            return self.nama_pengirim
        if self.rb_penerima.isChecked():
            return self.nama_penerima
        return self.txt_ketiga.text().strip().upper()


class BukuGudangApprovalDialog(QDialog):
    def __init__(self, action, detail, parent=None):
        super().__init__(parent)
        terapkan_style_input_global(self)
        self.setWindowTitle("Konfirmasi Approval")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Aksi: {action}"))
        layout.addWidget(QLabel(detail))
        self.alasan = QTextEdit()
        self.alasan.setPlaceholderText("Alasan tindakan...")
        layout.addWidget(self.alasan)
        self.btn_ok = QPushButton("Setujui")
        self.btn_cancel = QPushButton("Batal")
        row = QHBoxLayout()
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        layout.addLayout(row)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)


class TabBukuGudang(QWidget):
    KOL_RESI = 0
    KOL_MASUK = 1
    KOL_KELUAR = 2
    KOL_STATUS = 3
    KOL_STATUS_RESI = KOL_STATUS
    KOL_STATUS_PENAGIHAN = 4
    KOL_TRUK = 5
    KOL_PENGIRIM = 6
    KOL_KOTA_ASAL = 7
    KOL_PENERIMA = 8
    KOL_KOTA_TUJUAN = 9
    KOL_NAMA_BARANG = 10
    KOL_KOLI = 11
    KOL_BERAT = 12
    KOL_CBM = 13
    KOL_ONGKIR = 14
    KOL_PAYMENT = 15
    KOL_KETERANGAN = 16

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "BukuGudang"
    SETTINGS_KEY_LEBAR = "lebar_kolom_gudang_v3"

    # Posisi kolom Qt dipetakan ke identitas field; database tidak menerima indeks UI.
    FILTER_KEY_BY_COLUMN = {
        KOL_RESI: db_service.BukuGudangFilter.NO_RESI,
        KOL_MASUK: db_service.BukuGudangFilter.TANGGAL_MASUK,
        KOL_KELUAR: db_service.BukuGudangFilter.TANGGAL_KELUAR,
        KOL_STATUS: db_service.BukuGudangFilter.STATUS_RESI,
        KOL_STATUS_PENAGIHAN: db_service.BukuGudangFilter.STATUS_PENAGIHAN_KOLOM,
        KOL_TRUK: db_service.BukuGudangFilter.TRUK,
        KOL_PENGIRIM: db_service.BukuGudangFilter.PENGIRIM,
        KOL_KOTA_ASAL: db_service.BukuGudangFilter.KOTA_ASAL,
        KOL_PENERIMA: db_service.BukuGudangFilter.PENERIMA,
        KOL_KOTA_TUJUAN: db_service.BukuGudangFilter.KOTA_TUJUAN,
        KOL_NAMA_BARANG: db_service.BukuGudangFilter.NAMA_BARANG,
        KOL_KOLI: db_service.BukuGudangFilter.KOLI,
        KOL_BERAT: db_service.BukuGudangFilter.BERAT,
        KOL_CBM: db_service.BukuGudangFilter.CBM,
        KOL_ONGKIR: db_service.BukuGudangFilter.ONGKIR,
        KOL_PAYMENT: db_service.BukuGudangFilter.PEMBAYARAN,
        KOL_KETERANGAN: db_service.BukuGudangFilter.KETERANGAN,
    }

    ROLE_NO_RESI = 256
    ROLE_DETAIL_ID = ROLE_NO_RESI + 1
    ROLE_IS_PARENT = ROLE_NO_RESI + 2
    ROLE_URUTAN_DETAIL = ROLE_NO_RESI + 3
    ROLE_REVISION = ROLE_NO_RESI + 4
    ROLE_INVOICE_NO = ROLE_NO_RESI + 5
    ROLE_INVOICE_DATE = ROLE_NO_RESI + 6
    ROLE_INVOICE_STATUS = ROLE_NO_RESI + 7
    ROLE_INVOICE_COUNT = ROLE_NO_RESI + 8
    ROLE_STATUS_HIGHLIGHT = ROLE_NO_RESI + 9
    ROLE_DETAIL_ROWS = ROLE_NO_RESI + 10
    ROLE_SEARCH_TEXT = ROLE_NO_RESI + 11
    ROLE_DETAIL_COUNT = ROLE_NO_RESI + 12
    MODEL_WRITABLE_ROLES = frozenset({
        ROLE_NO_RESI,
        ROLE_DETAIL_ID,
        ROLE_REVISION,
        ROLE_INVOICE_NO,
        ROLE_INVOICE_STATUS,
        ROLE_STATUS_HIGHLIGHT,
        ROLE_DETAIL_ROWS,
        ROLE_SEARCH_TEXT,
    })

    RENDER_BATCH_SIZE = 100
    RENDER_TIME_BUDGET = 0.008

    AUTOCOMPLETE_CACHE_TTL = 60.0

    KOLOM_PENCARIAN = tuple(range(KOL_RESI, KOL_KETERANGAN + 1))
    DEFAULT_LEBAR_KOLOM = BUKU_GUDANG_DEFAULT_COLUMN_WIDTHS

    HEADERS = (
        "RESI", "MASUK", "KELUAR", "STATUS RESI", "STATUS PENAGIHAN",
        "TRUK", "PENGIRIM", "KOTA ASAL", "PENERIMA", "KOTA TUJUAN",
        "NAMA BARANG", "KOLI", "BERAT (kg)", "KUBIK (m3)", "ONGKIR (Rp)",
        "PAYMENT", "KETERANGAN",
    )

    KOLOM_NUMERIK = (KOL_KOLI, KOL_BERAT, KOL_CBM, KOL_ONGKIR)
    KOLOM_DESIMAL = (KOL_BERAT, KOL_CBM)
    KOLOM_RATA_KANAN = (KOL_KOLI, KOL_BERAT, KOL_CBM, KOL_ONGKIR)
    KOLOM_TANGGAL = (KOL_MASUK, KOL_KELUAR)
    KOLOM_DETAIL_DB = {
        KOL_NAMA_BARANG: DBIndex.NAMA_BARANG,
        KOL_KOLI: DBIndex.KOLI,
        KOL_BERAT: DBIndex.BERAT,
        KOL_CBM: DBIndex.CBM,
    }
    KOLOM_DB = {
        KOL_PENGIRIM: "pengirim",
        KOL_KOTA_ASAL: "kota_asal",
        KOL_PENERIMA: "penerima",
        KOL_KOTA_TUJUAN: "kota_tujuan",
        KOL_NAMA_BARANG: "nama_barang",
        KOL_KOLI: "koli",
        KOL_BERAT: "berat",
        KOL_CBM: "cbm",
        KOL_ONGKIR: "total_ongkir",
        KOL_PAYMENT: "pembayaran",
        KOL_KETERANGAN: "ket_buku_gudang",
    }

    def __init__(self):
        super().__init__()
        self.tabs_list = []
        self.row_sedang_diedit = -1
        self._show_event_pertama = True
        self._tabel_lebar_pending = None
        sekarang = datetime.now()
        self._bulan_terpilih = {sekarang.month}
        self._status_penagihan_terpilih = "SEMUA"
        self._sinkronisasi_checkbox_bulan = False
        self._checkbox_bulan = {}
        self._checkbox_semua_bulan = None

        self._table_state = {}

        self._cache_lebar_kolom_dasar = None
        self._autocomplete_cache = {}

        self.ALIGNMENT_KOLOM = tuple(
            (Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            if col in self.KOLOM_RATA_KANAN
            else (Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            if col in self.KOLOM_TANGGAL
            else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            for col in range(len(self.HEADERS))
        )

        self._timer_simpan_lebar = QTimer(self)
        self._timer_simpan_lebar.setSingleShot(True)
        self._timer_simpan_lebar.setInterval(250)
        self._timer_simpan_lebar.timeout.connect(
            self._simpan_lebar_kolom_tertunda,
        )

        self._timer_pencarian = QTimer(self)
        self._timer_pencarian.setSingleShot(True)
        self._timer_pencarian.setInterval(300)
        self._timer_pencarian.timeout.connect(self.filter_pencarian_tabel)

        self.init_ui()

    def _bangun_header_buku_gudang(self):
        layout_header = QVBoxLayout()
        layout_header.setContentsMargins(*BUKU_GUDANG_HEADER_MARGINS)
        layout_header.setSpacing(BUKU_GUDANG_HEADER_SPACING)

        baris_utama = QHBoxLayout()
        baris_utama.setSpacing(BUKU_GUDANG_PRIMARY_ROW_SPACING)

        self.lbl_judul = QLabel("Buku Gudang")
        baris_utama.addWidget(self.lbl_judul)
        self.lbl_status_data = QLabel("")
        self.lbl_status_data.setObjectName("lblStatusBukuGudang")
        self.lbl_status_data.setMinimumWidth(0)
        baris_utama.addWidget(self.lbl_status_data)
        baris_utama.addStretch()

        tahun_sekarang = datetime.now().year
        self.btn_tahun = QPushButton()
        self.btn_tahun.setText(str(tahun_sekarang))
        self.btn_tahun.setFixedSize(*BUKU_GUDANG_YEAR_BUTTON_SIZE)
        self.menu_tahun = QMenu(self)
        self.setup_menu_tahun(tahun_sekarang)
        self.btn_tahun.setMenu(self.menu_tahun)
        baris_utama.addWidget(self.btn_tahun)

        self.btn_bulan = QPushButton()
        self.btn_bulan.setFixedSize(*BUKU_GUDANG_MONTH_BUTTON_SIZE)
        self.menu_bulan = QMenu(self)
        self.setup_menu_bulan()
        self.btn_bulan.setMenu(self.menu_bulan)
        baris_utama.addWidget(self.btn_bulan)

        self.btn_status_penagihan = QPushButton()
        self.btn_status_penagihan.setText("Semua Tagihan")
        self.btn_status_penagihan.setFixedSize(*BUKU_GUDANG_BILLING_STATUS_BUTTON_SIZE)
        self.menu_status_penagihan = QMenu(self)
        self.setup_menu_status_penagihan()
        self.btn_status_penagihan.setMenu(self.menu_status_penagihan)
        baris_utama.addWidget(self.btn_status_penagihan)

        self.btn_reset_filter = QToolButton()
        self.btn_reset_filter.setText("Reset")
        self.btn_reset_filter.setFixedSize(*BUKU_GUDANG_RESET_FILTER_BUTTON_SIZE)
        self.btn_reset_filter.clicked.connect(self.reset_semua_filter)
        baris_utama.addWidget(self.btn_reset_filter)

        baris_utama.addStretch()

        self.txt_cari = QLineEdit()
        self.txt_cari.setPlaceholderText("Cari resi, truk, pengirim, barang...")
        self.txt_cari.setFixedWidth(BUKU_GUDANG_SEARCH_WIDTH)
        self.txt_cari.setFixedHeight(BUKU_GUDANG_HEADER_CONTROL_HEIGHT)
        self.txt_cari.textChanged.connect(lambda: paksa_kapital_lineedit(self.txt_cari))
        self.txt_cari.textChanged.connect(
            lambda: self._timer_pencarian.start()
        )
        baris_utama.addWidget(self.txt_cari)

        action_styles = konversi_style_font_ke_point(get_buku_gudang_action_styles())
        self.btn_buat_invoice = QPushButton("Buat Invoice")
        self.btn_buat_invoice.setStyleSheet(action_styles["btn_buat_invoice"])
        self.btn_simpan_inv = QPushButton("Simpan")
        self.btn_simpan_inv.setStyleSheet(action_styles["btn_simpan_inv"])
        self.btn_simpan_inv.setVisible(False)
        self.btn_batal_inv = QPushButton("Batal")
        self.btn_batal_inv.setStyleSheet(action_styles["btn_batal_inv"])
        self.btn_batal_inv.setVisible(False)
        for tombol in (self.btn_buat_invoice, self.btn_simpan_inv, self.btn_batal_inv):
            tombol.setFixedHeight(BUKU_GUDANG_HEADER_CONTROL_HEIGHT)
            baris_utama.addWidget(tombol)
        self.btn_buat_invoice.clicked.connect(self.aktifkan_mode_invoice)
        self.btn_batal_inv.clicked.connect(self.batalkan_mode_invoice)
        self.btn_simpan_inv.clicked.connect(self.proses_simpan_ke_invoice)

        self._perbarui_label_bulan()
        layout_header.addLayout(baris_utama)
        return layout_header

    def _bangun_tabs_wilayah(self):
        self.tabs_wilayah = QTabWidget()
        provinsi_tujuan = DATA_CLIENT.get(
            "provinsi_tujuan",
            ["PROVINSI A", "PROVINSI B", "PROVINSI C"],
        )
        for wilayah in provinsi_tujuan:
            widget_tabel = self.create_tabel_tab(wilayah)
            self.tabs_list.append(widget_tabel)
            self.tabs_wilayah.addTab(widget_tabel, wilayah.title())

        self.tabs_wilayah.currentChanged.connect(self._on_wilayah_changed)
        return self.tabs_wilayah

    def init_ui(self):
        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(*BUKU_GUDANG_MAIN_MARGINS)
        layout_utama.setSpacing(BUKU_GUDANG_MAIN_SPACING)
        layout_utama.addLayout(self._bangun_header_buku_gudang())
        layout_utama.addWidget(self._bangun_tabs_wilayah())
        self.refresh_session_ui()
        self.sesuaikan_tema_lokal()

    def minta_approval_aksi(self, aksi, detail):
        dialog = BukuGudangApprovalDialog(aksi, detail, self)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def aktifkan_mode_invoice(self):
        self.btn_buat_invoice.setVisible(False)
        self.btn_simpan_inv.setVisible(True)
        self.btn_batal_inv.setVisible(True)
        QMessageBox.information(
            self,
            "Mode Invoice",
            "Silakan blok/pilih baris resi yang ingin dijadikan Invoice, lalu klik 'Simpan'.",
        )

    def batalkan_mode_invoice(self):
        self.btn_buat_invoice.setVisible(True)
        self.btn_simpan_inv.setVisible(False)
        self.btn_batal_inv.setVisible(False)
        if self.tabs_wilayah.currentWidget() and hasattr(
            self.tabs_wilayah.currentWidget(), 'tabel'
        ):
            self.tabs_wilayah.currentWidget().tabel.clearSelection()

    def _ambil_baris_terseleksi_invoice(self, tabel):
        rows = []
        selection_model = tabel.selectionModel()
        if selection_model:
            rows = [idx.row() for idx in selection_model.selectedRows()]
        if not rows:
            rows = [item.row() for item in tabel.selectedItems()]
        return sorted(set(rows))

    def _ambil_text_item(self, tabel, row, col):
        item = tabel.item(row, col)
        return item.text().strip() if item else ""

    def _ambil_tab_widget_dari_tabel(self, tabel):
        widget = tabel.parentWidget()
        while widget is not None:
            if hasattr(widget, "wilayah") and hasattr(widget, "filter_data"):
                return widget
            widget = widget.parentWidget()
        return None

    @db_service.profile_performance("BukuGudang.apply_search_to_table", threshold=0.025)
    def _terapkan_pencarian_ke_tabel(self, tabel):
        keyword = self.txt_cari.text().strip().casefold()
        if getattr(tabel, "_render_state", None) is not None:
            return

        hidden_rows = getattr(tabel, "_buku_gudang_hidden_rows", None)
        if hidden_rows is None:
            hidden_rows = set()
            tabel._buku_gudang_hidden_rows = hidden_rows

        if not keyword:
            if hidden_rows:
                previous_updates = tabel.updatesEnabled()
                try:
                    tabel.setUpdatesEnabled(False)
                    row_count = tabel.rowCount()
                    for row in hidden_rows:
                        if 0 <= row < row_count and tabel.isRowHidden(row):
                            tabel.setRowHidden(row, False)
                    hidden_rows.clear()
                finally:
                    tabel.setUpdatesEnabled(previous_updates)
            tabel._buku_gudang_search_keyword = ""
            return

        previous_keyword = getattr(tabel, "_buku_gudang_search_keyword", "")
        narrowing = bool(previous_keyword and keyword.startswith(previous_keyword))
        row_count = tabel.rowCount()

        if narrowing:
            candidate_rows = (
                row for row in range(row_count) if row not in hidden_rows
            )
            next_hidden_rows = set(hidden_rows)
        else:
            candidate_rows = range(row_count)
            next_hidden_rows = set()

        previous_updates = tabel.updatesEnabled()
        try:
            tabel.setUpdatesEnabled(False)
            for row in candidate_rows:
                teks = tabel.searchText(row)
                hidden = keyword not in (teks or "")
                if hidden:
                    next_hidden_rows.add(row)
                if tabel.isRowHidden(row) != hidden:
                    tabel.setRowHidden(row, hidden)
            tabel._buku_gudang_hidden_rows = next_hidden_rows
            tabel._buku_gudang_search_keyword = keyword
        finally:
            tabel.setUpdatesEnabled(previous_updates)

    def _settings_kolom(self):
        return QSettings(
            self.SETTINGS_ORGANIZATION,
            self.SETTINGS_APPLICATION,
        )

    @staticmethod
    def _normalisasi_daftar_lebar(value, jumlah_kolom):
        if not isinstance(value, (list, tuple)):
            return None
        if len(value) != jumlah_kolom:
            return None

        hasil = []
        try:
            for width in value:
                hasil.append(min(max(BUKU_GUDANG_COLUMN_WIDTH_MIN, int(width)), BUKU_GUDANG_COLUMN_WIDTH_MAX))
        except (TypeError, ValueError):
            return None
        return hasil

    def _cari_tab_invoice(self):
        win = self.window()
        if not win:
            return None
        tab_invoice = getattr(win, "tab_invoice", None)
        if tab_invoice and hasattr(tab_invoice, "terima_data_baru"):
            return tab_invoice
        for widget in win.findChildren(QWidget):
            if widget.__class__.__name__ == "TabInvoice" and hasattr(widget, "terima_data_baru"):
                return widget
        for widget in win.findChildren(QWidget):
            if hasattr(widget, "terima_data_baru") and hasattr(widget, "tabel_item_invoice"):
                return widget
        return None

    def _pindah_ke_tab_invoice(self, tab_invoice):
        win = self.window()
        if not win or not tab_invoice:
            return False

        tabs_utama = getattr(win, 'tabs_utama', None)
        if isinstance(tabs_utama, QTabWidget) and tabs_utama.indexOf(tab_invoice) != -1:
            tabs_utama.setCurrentWidget(tab_invoice)
            return True

        for tab_widget in win.findChildren(QTabWidget):
            idx = tab_widget.indexOf(tab_invoice)
            if idx != -1:
                tab_widget.setCurrentIndex(idx)
                return True

        return False

    def _no_resi_dari_baris(self, tabel, row):
        item = tabel.item(row, self.KOL_RESI)
        if item is None:
            return ""
        no_resi = item.data(self.ROLE_NO_RESI)
        if no_resi:
            return str(no_resi).strip()
        teks = item.text().strip()
        return teks if teks and not teks.startswith("↳") else ""

    def _detail_id_dari_baris(self, tabel, row):
        item = tabel.item(row, self.KOL_RESI)
        return item.data(self.ROLE_DETAIL_ID) if item is not None else None

    def _revision_dari_baris(self, tabel, row):
        item = tabel.item(row, self.KOL_RESI)
        if item is None:
            return None
        revision = item.data(self.ROLE_REVISION)
        try:
            return int(revision)
        except (TypeError, ValueError):
            return None

    def _baris_induk_resi(self, tabel, row):
        # Tampilan Buku Gudang saat ini memakai satu baris per Resi.
        # Detail barang disimpan pada metadata baris, bukan sebagai baris anak.
        return row

    def _data_invoice_dari_baris(self, tabel, row):
        no_resi = self._no_resi_dari_baris(tabel, row)
        if not no_resi:
            return None

        parent_row = self._baris_induk_resi(tabel, row)
        detail = db_service.ambil_detail_resi(no_resi)
        if not detail:
            return None

        revision_ui = self._revision_dari_baris(tabel, parent_row)
        try:
            revision_db = int(detail[20] or 0)
        except (TypeError, ValueError):
            revision_db = None
        if revision_ui is not None and revision_db is not None and revision_ui != revision_db:
            QMessageBox.warning(
                self,
                "Data Resi Sudah Berubah",
                f"Resi {no_resi} telah berubah setelah Buku Gudang dimuat.\n\n"
                "Invoice tidak dapat diproses dari data lama. Silakan refresh Buku Gudang "
                "lalu pilih Resi kembali.",
            )
            return None

        return {
            "no_resi": no_resi,
            "pengirim": self._ambil_text_item(tabel, parent_row, self.KOL_PENGIRIM),
            "penerima": self._ambil_text_item(tabel, parent_row, self.KOL_PENERIMA),
            "tujuan": self._ambil_text_item(tabel, parent_row, self.KOL_KOTA_TUJUAN),
            "nama_barang": str(detail[8] or ""),
            "koli": str(detail[10] or "0"),
            "berat": str(detail[9] or "0"),
            "kubik": str(detail[11] or "0"),
            # Invoice harus menerima dasar pengenaan pajak, bukan total yang
            # sudah termasuk PPN, agar pajak tidak dihitung dua kali.
            "ongkir": str(detail[19] if detail[19] is not None else detail[12] or "0"),
            "subtotal_ongkir": str(detail[19] if detail[19] is not None else detail[12] or "0"),
            "jenis_pajak": str(detail[18] or "NONPAJAK").strip().upper(),
            "revision": revision_db,
            "kode_cabang": str(CURRENT_SESSION.get("kode_cabang", "PUSAT") or "PUSAT").strip().upper(),
        }

    def _kumpulkan_data_invoice(self, tabel, baris_terseleksi):
        hasil = []
        pengirim_pertama = penerima_pertama = None
        beda_pengirim_dikonfirmasi = False
        resi_sudah_diproses = set()
        for row in baris_terseleksi:
            if tabel.isRowHidden(row):
                continue
            no_resi = self._no_resi_dari_baris(tabel, row)
            if not no_resi or no_resi in resi_sudah_diproses:
                continue
            resi_sudah_diproses.add(no_resi)
            data = self._data_invoice_dari_baris(tabel, row)
            if data is None:
                continue
            # Satu Invoice dari Resi tidak boleh mencampur PAJAK dan NONPAJAK.
            jenis_pajak_data = str(data.get("jenis_pajak") or "NONPAJAK").strip().upper()
            jenis_pajak_pertama = None
            if hasil:
                jenis_pajak_pertama = str(
                    hasil[0].get("jenis_pajak") or "NONPAJAK"
                ).strip().upper()
            if jenis_pajak_pertama and jenis_pajak_data != jenis_pajak_pertama:
                QMessageBox.warning(
                    self,
                    "Invoice Tidak Dapat Diproses",
                    "Resi yang dipilih mengandung campuran PAJAK dan NONPAJAK.\n\n"
                    "Satu Invoice hanya boleh berisi satu jenis pajak.\n"
                    "Silakan pilih Resi dengan jenis pajak yang sama.",
                )
                return None
            if not pengirim_pertama:
                pengirim_pertama = data["pengirim"]
                penerima_pertama = data["penerima"]
            elif data["pengirim"] != pengirim_pertama and not beda_pengirim_dikonfirmasi:
                jawaban = QMessageBox.question(
                    self,
                    "Konfirmasi",
                    "Resi yang dipilih memiliki nama PENGIRIM yang berbeda-beda.\n"
                    "Yakin ingin menggabungkannya ke dalam 1 Invoice?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if jawaban == QMessageBox.StandardButton.No:
                    return None
                beda_pengirim_dikonfirmasi = True
            hasil.append(data)
        return hasil, pengirim_pertama, penerima_pertama

    def _context_invoice_terpilih(self):
        current_tab = self.tabs_wilayah.currentWidget()
        if not current_tab or not hasattr(current_tab, "tabel"):
            QMessageBox.warning(self, "Peringatan", "Tabel Buku Gudang tidak ditemukan.")
            return None

        tabel = current_tab.tabel
        if getattr(current_tab, "_loading", False):
            QMessageBox.information(self, "Memuat Data", "Tunggu sampai data selesai dimuat.")
            return None
        baris = self._ambil_baris_terseleksi_invoice(tabel)
        if not baris:
            QMessageBox.warning(self, "Peringatan", "Anda belum memilih resi satupun!")
            return None

        kumpulan = self._kumpulkan_data_invoice(tabel, baris)
        if kumpulan is None:
            return None

        list_resi_data, pengirim, penerima = kumpulan
        if not list_resi_data:
            QMessageBox.warning(
                self, "Peringatan", "Data resi yang dipilih tidak valid atau kosong."
            )
            return None
        return list_resi_data, pengirim, penerima

    def proses_simpan_ke_invoice(self):
        context = self._context_invoice_terpilih()
        if context is None:
            return

        list_resi_data, pengirim, penerima = context
        dialog = DialogPilihPenagih(pengirim, penerima, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        tab_invoice = self._cari_tab_invoice()
        if not tab_invoice:
            QMessageBox.critical(
                self,
                "Tab Invoice Tidak Ditemukan",
                "Data berhasil dibaca dari Buku Gudang, tetapi widget TabInvoice tidak ditemukan.\n"
                "Pastikan tab invoice sudah dibuat di MainWindow dan instance-nya tidak dibuat ulang.",
            )
            return

        tab_invoice.terima_data_baru(dialog.get_nama_client(), list_resi_data)
        if not self._pindah_ke_tab_invoice(tab_invoice):
            QMessageBox.information(
                self,
                "Data Invoice Siap",
                "Data sudah dikirim ke draft invoice, tetapi aplikasi tidak menemukan "
                "QTabWidget utama untuk berpindah otomatis.",
            )
        self.batalkan_mode_invoice()

    def _konfigurasi_tabel_gudang(self, tabel):
        tabel.setColumnCount(len(self.HEADERS))
        tabel.setHorizontalHeaderLabels(self.HEADERS)
        tabel._buku_gudang_model.setAlignments(self.ALIGNMENT_KOLOM)

        setup_tabel_modern(
            tabel,
            row_height=BUKU_GUDANG_TABLE_ROW_BASE_HEIGHT,
            stretch_last_column=False,
            hide_row_numbers=True,
        )

        self.load_lebar_kolom(tabel)

        header = tabel.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(
            lambda pos, t=tabel: self.show_header_menu(pos, t)
        )
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsClickable(False)
        header.setSectionsMovable(False)
        header.sectionResized.connect(
            lambda _i, _old, _new, t=tabel: self.jadwalkan_simpan_lebar_kolom(t)
        )
        frozen = getattr(tabel, "frozen_table", None)
        if frozen is not None:
            # Saat kolom RESI diubah lewat header overlay, perubahan juga
            # masuk ke mekanisme penyimpanan lebar kolom seperti header utama.
            frozen.horizontalHeader().sectionResized.connect(
                lambda col, _old, _new, t=tabel: (
                    self.jadwalkan_simpan_lebar_kolom(t) if col == self.KOL_RESI else None
                )
            )
            frozen.horizontalHeader().customContextMenuRequested.connect(
                lambda pos, t=tabel, h=frozen.horizontalHeader(): self.show_header_menu(
                    pos,
                    t,
                    forced_col=self.KOL_RESI,
                    menu_global_pos=h.viewport().mapToGlobal(pos),
                )
            )
            frozen.customContextMenuRequested.connect(
                lambda pos, t=tabel, v=frozen: self.show_cell_context_menu(
                    pos, t, frozen_view=v
                )
            )

        # Profil scrolling: hindari jalur paint QStyledItemDelegate/QStyle untuk
        # setiap sel. Delegate khusus juga dipasang pada view kolom beku.
        is_dark = self._tema_gelap_aktif()
        tabel.setItemDelegate(
            BukuGudangFastPaintDelegate(
                tabel,
                is_dark=is_dark,
                status_role=self.ROLE_STATUS_HIGHLIGHT,
            )
        )
        frozen = getattr(tabel, "frozen_table", None)
        if frozen is not None:
            frozen.setItemDelegate(
                BukuGudangFastPaintDelegate(
                    frozen,
                    is_dark=is_dark,
                    status_role=self.ROLE_STATUS_HIGHLIGHT,
                )
            )

        # Satu controller menangani wheel di kedua viewport. Ini penting karena
        # overlay frozen memiliki QAbstractScrollArea sendiri tetapi scrollbar
        # horizontal yang benar berada di tabel utama.
        if not getattr(tabel, "_buku_gudang_smooth_scroll_controller", None):
            event_targets = [tabel.viewport()]
            if frozen is not None:
                event_targets.append(frozen.viewport())
            tabel._buku_gudang_smooth_scroll_controller = pasang_scroll_halus(
                tabel,
                event_targets=event_targets,
            )

        tabel.setWordWrap(False)
        # Teks dipotong oleh batas sel, tanpa biaya kalkulasi elipsis per paint.
        tabel.setTextElideMode(Qt.TextElideMode.ElideNone)

        tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabel.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Pertahankan tampilan Buku Gudang: warna selang-seling dan garis grid.
        tabel.setAlternatingRowColors(True)
        tabel.setShowGrid(True)
        tabel.setMouseTracking(False)

        vertical_header = tabel.verticalHeader()
        vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vertical_header.setDefaultSectionSize(BUKU_GUDANG_TABLE_ROW_BASE_HEIGHT)
        frozen = getattr(tabel, "frozen_table", None)
        if frozen is not None:
            frozen.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            frozen.verticalHeader().setDefaultSectionSize(
                BUKU_GUDANG_TABLE_ROW_BASE_HEIGHT
            )

        row_timer = QTimer(tabel)
        row_timer.setSingleShot(True)
        row_timer.timeout.connect(lambda t=tabel: self._sinkronkan_baris_resi(t))
        tabel._buku_gudang_row_timer = row_timer
        vertical_header.sectionResized.connect(
            lambda *_args, t=tabel: self._jadwalkan_tinggi_baris(t)
        )

        tabel.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        tabel.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        tabel.verticalScrollBar().setSingleStep(
            BUKU_GUDANG_TABLE_ROW_BASE_HEIGHT * 3
        )

        tabel.model().layoutChanged.connect(
            lambda *_: self._setelah_urutan_berubah(tabel)
        )

        zoom_helper.pasang_ctrl_scroll_zoom(
            tabel,
            lambda arah, t=tabel: self._ubah_zoom_ctrl_scroll(t, arah),
        )

        tabel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tabel.customContextMenuRequested.connect(
            lambda pos, t=tabel: self.show_cell_context_menu(pos, t)
        )

    def create_tabel_tab(self, wilayah):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(*BUKU_GUDANG_TABLE_TAB_MARGINS)

        tabel = BukuGudangTableView()
        self._konfigurasi_tabel_gudang(tabel)

        layout.addWidget(tabel)
        widget.tabel = tabel
        widget.wilayah = wilayah
        widget.filter_data = {}
        widget._load_generation = 0
        widget._load_pending = None
        widget._load_worker = None
        widget._loading = False

        widget._buku_gudang_loaded_signature = None
        widget._buku_gudang_loading_signature = None
        widget._buku_gudang_cache_stale = True
        widget._buku_gudang_data_fingerprint = None
        widget._buku_gudang_invalidation_generation = 0
        widget._buku_gudang_loading_invalidation_generation = 0
        widget._buku_gudang_initial_position_pending = True
        widget._buku_gudang_search_mode = False
        widget._buku_gudang_query_year = str(datetime.now().year)
        timer = QTimer(widget)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._render_batch(widget))
        widget._render_timer = timer
        return widget

    def _parameter_query_buku_gudang(self, tab_widget):
        """Bangun parameter query menggunakan key field yang kanonis."""
        filters = dict(getattr(tab_widget, "filter_data", {}) or {})
        search_all_year = bool(self.txt_cari.text().strip())

        if search_all_year:
            tahun_query = str(
                self.btn_tahun.text() or datetime.now().year
            ).strip()
            filters.pop(db_service.BukuGudangFilter.BULAN, None)
        else:
            tahun_query = str(self.btn_tahun.text() or datetime.now().year).strip()
            if self._bulan_terpilih and len(self._bulan_terpilih) < 12:
                filters[db_service.BukuGudangFilter.BULAN] = tuple(
                    sorted(self._bulan_terpilih)
                )
            else:
                filters.pop(db_service.BukuGudangFilter.BULAN, None)

        if self._status_penagihan_terpilih != "SEMUA":
            filters[db_service.BukuGudangFilter.STATUS_PENAGIHAN] = (
                self._status_penagihan_terpilih
            )
        else:
            filters.pop(db_service.BukuGudangFilter.STATUS_PENAGIHAN, None)

        return (
            str(self._kode_cabang_aktif() or "PUSAT").strip().upper(),
            str(tab_widget.wilayah or ""),
            tahun_query,
            filters,
            search_all_year,
        )

    @staticmethod
    def _signature_query_buku_gudang(cabang, wilayah, tahun, filters):
        """Signature stabil untuk menentukan apakah hasil tabel masih relevan."""
        filter_signature = tuple(
            sorted((str(key), repr(value)) for key, value in filters.items())
        )
        return (
            str(cabang or "").strip().upper(),
            str(wilayah or ""),
            str(tahun or ""),
            filter_signature,
        )

    def _ambil_fingerprint_wilayah(self, tab_widget):
        """Ambil penanda sumber data tanpa memuat ulang seluruh baris tabel."""
        cabang, wilayah, tahun, _filters, _search_all_year = (
            self._parameter_query_buku_gudang(tab_widget)
        )
        return db_service.ambil_fingerprint_data_buku_gudang(
            cabang, wilayah, tahun
        )

    def _periksa_cache_wilayah(self, tab_widget):
        fingerprint = self._ambil_fingerprint_wilayah(tab_widget)
        if fingerprint is None:
            # Bila pemeriksaan gagal, jangan menganggap cache valid berdasarkan
            # data yang tidak berhasil diverifikasi.
            tab_widget._buku_gudang_cache_stale = True
            tab_widget._buku_gudang_loaded_signature = None
            return

        sebelumnya = getattr(tab_widget, "_buku_gudang_data_fingerprint", None)
        if sebelumnya is not None and sebelumnya != fingerprint:
            tab_widget._buku_gudang_cache_stale = True
            tab_widget._buku_gudang_loaded_signature = None

        tab_widget._buku_gudang_data_fingerprint = fingerprint

    def _pastikan_data_wilayah_dimuat(self, tab_widget):
        """Gunakan cache hanya jika filter dan sumber SQLite masih sama."""
        if tab_widget is None or not hasattr(tab_widget, "tabel"):
            return

        cabang, wilayah, tahun, filters, _search_all_year = (
            self._parameter_query_buku_gudang(tab_widget)
        )
        signature = self._signature_query_buku_gudang(
            cabang, wilayah, tahun, filters
        )

        if (
            getattr(tab_widget, "_loading", False)
            and getattr(tab_widget, "_buku_gudang_loading_signature", None) == signature
        ):
            return

        self._periksa_cache_wilayah(tab_widget)

        if (
            not getattr(tab_widget, "_buku_gudang_cache_stale", True)
            and getattr(tab_widget, "_buku_gudang_loaded_signature", None) == signature
        ):
            self._terapkan_pencarian_ke_tabel(tab_widget.tabel)
            self._perbarui_status_data(tab_widget)
            return

        self.load_data(tab_widget)

    def invalidate_data_cache(self, *, refresh_active=True):
        """Tandai cache semua wilayah kedaluwarsa setelah sumber data berubah."""
        for tab_widget in self.tabs_list:
            tab_widget._buku_gudang_cache_stale = True
            tab_widget._buku_gudang_loaded_signature = None
            tab_widget._buku_gudang_invalidation_generation = (
                getattr(tab_widget, "_buku_gudang_invalidation_generation", 0) + 1
            )

        active_tab = self.tabs_wilayah.currentWidget()
        if (
            refresh_active
            and active_tab is not None
            and self.isVisible()
            and getattr(self, "row_sedang_diedit", -1) == -1
        ):
            self.load_data(active_tab)

    def showEvent(self, event):
        super().showEvent(event)
        active_tab = self.tabs_wilayah.currentWidget()
        if self._show_event_pertama:
            self._show_event_pertama = False
            self._pastikan_data_wilayah_dimuat(active_tab)
            self._jadwalkan_posisi_awal_bawah(active_tab)
            return

        self._pastikan_data_wilayah_dimuat(active_tab)
        self._jadwalkan_posisi_awal_bawah(active_tab)

    def eventFilter(self, obj, event):
        if isinstance(obj, (QLineEdit, QComboBox)):
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                if getattr(self, 'row_sedang_diedit', -1) != -1:
                    self.refresh_session_ui()
                    return True

        if isinstance(obj, QLineEdit):
            is_numeric = getattr(obj, 'is_numeric_col', False)
            if event.type() == QEvent.Type.FocusIn:
                if is_numeric and obj.text().strip() == "-":
                    obj.setText("")
            elif event.type() == QEvent.Type.FocusOut:
                if is_numeric and obj.text().strip() == "":
                    obj.setText("-")

        return super().eventFilter(obj, event)

    def _tema_gelap_aktif(self):
        window = self.window()
        tema_window = str(
            getattr(window, "current_theme", "") or ""
        ).strip().lower()

        if tema_window in {"light", "dark"}:
            return tema_window == "dark"

        settings_ui = QSettings(
            ORGANIZATION_NAME,
            APPLICATION_NAME,
        )
        tema_tersimpan = str(
            settings_ui.value("theme", "light") or "light"
        ).strip().lower()
        return tema_tersimpan == "dark"

    def _sinkronkan_editor_inline(self, tabel):
        row = getattr(self, "row_sedang_diedit", -1)
        if row < 0 or row >= tabel.rowCount():
            return

        for column in range(self.KOL_PENGIRIM, self.KOL_KETERANGAN + 1):
            editor = tabel.cellWidget(row, column)
            if isinstance(editor, QLineEdit):
                editor.setStyleSheet(self.inline_editor_style)
                atur_editor_sel(editor)

    def _buat_style_buku_gudang(self, is_dark):
        styles = konversi_style_font_ke_point(
            get_buku_gudang_styles(is_dark=is_dark)
        )
        return styles

    def _terapkan_tema_ke_tabel(self, tabel, is_dark, styles):
        tabel.setUpdatesEnabled(False)
        try:
            self._sinkronkan_editor_inline(tabel)

            zoom_helper.terapkan_zoom_tabel(
                tabel,
                is_dark=is_dark,
                z=zoom_helper.dapatkan_zoom_level(self.__class__.__name__),
                update_geometry=False,
                extra_stylesheet=self._tooltip_qss(is_dark),
            )
            for target in (tabel, getattr(tabel, "frozen_table", None)):
                if target is None:
                    continue
                delegate = target.itemDelegate()
                if isinstance(delegate, BukuGudangFastPaintDelegate):
                    delegate.set_theme(is_dark)

            tabel._buku_gudang_theme_dark = bool(is_dark)
        finally:
            tabel.setUpdatesEnabled(True)

    def _ubah_zoom_ctrl_scroll(self, tabel, arah):
        level = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        level = zoom_helper.simpan_zoom_level(
            self.__class__.__name__,
            level + int(arah),
        )
        zoom_helper.terapkan_zoom_tabel(
            tabel,
            is_dark=self._tema_gelap_aktif(),
            z=level,
        )
        self._jadwalkan_tinggi_baris(tabel)

    def _on_wilayah_changed(self, _index):
        """Perbarui tema hanya untuk tabel wilayah yang akan ditampilkan."""
        active_widget = self.tabs_wilayah.currentWidget()
        tabel = getattr(active_widget, "tabel", None)
        if tabel is not None:
            is_dark = self._tema_gelap_aktif()
            if getattr(tabel, "_buku_gudang_theme_dark", None) != bool(is_dark):
                styles_statis = self._buat_style_buku_gudang(is_dark)
                self.inline_editor_style = styles_statis["inline_editor"]
                self._terapkan_tema_ke_tabel(tabel, is_dark, styles_statis)

        self._pastikan_data_wilayah_dimuat(active_widget)
        self._jadwalkan_posisi_awal_bawah(active_widget)

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()

        try:
            tab_bar = self.tabs_wilayah.tabBar()
            tema_key = "dark" if is_dark else "light"
            if tab_bar.property("_buku_gudang_tabbar_theme") != tema_key:
                tab_bar.setStyleSheet(get_buku_gudang_tabbar_styles(is_dark))
                tab_bar.setProperty("_buku_gudang_tabbar_theme", tema_key)
        except (AttributeError, RuntimeError):
            pass

        styles_statis = self._buat_style_buku_gudang(is_dark)
        self.inline_editor_style = styles_statis["inline_editor"]

        self.lbl_judul.setStyleSheet(styles_statis["lbl_judul"])

        for tombol_filter in (
            self.btn_tahun,
            self.btn_bulan,
            self.btn_status_penagihan,
        ):
            tombol_filter.setStyleSheet(styles_statis["btn_tahun"])
        self.btn_reset_filter.setStyleSheet(styles_statis["btn_reset_filter"])
        terapkan_style_input_global(self, is_dark)

        active_widget = getattr(self, "tabs_wilayah", None)
        active_widget = active_widget.currentWidget() if active_widget is not None else None
        tabel = getattr(active_widget, "tabel", None)
        if tabel is not None:
            self._terapkan_tema_ke_tabel(tabel, is_dark, styles_statis)

    def setup_menu_tahun(self, tahun_sekarang):
        self.menu_tahun.clear()
        ukuran_menu_tahun = max(10, get_fixed_font_sizes()["sz_input"] - 1)
        style_menu = konversi_font_qss_ke_point(
            get_buku_gudang_menu_style(ukuran_menu_tahun, self._tema_gelap_aktif())
        )
        self.menu_tahun.setStyleSheet(style_menu)

        for i in range(3):
            thn = str(tahun_sekarang - i)
            action = self.menu_tahun.addAction(thn)
            action.triggered.connect(lambda _, t=thn: self.ubah_tahun(t))

        self.menu_tahun.addSeparator()
        submenu_lainnya = self.menu_tahun.addMenu("Lainnya...")
        submenu_lainnya.setStyleSheet(style_menu)

        for i in range(3, 8):
            thn = str(tahun_sekarang - i)
            action = submenu_lainnya.addAction(thn)
            action.triggered.connect(lambda _, t=thn: self.ubah_tahun(t))

    def ubah_tahun(self, tahun_pilihan):
        self.btn_tahun.setText(tahun_pilihan)
        self.refresh_session_ui()

    def _style_menu_filter_periode(self):
        ukuran = max(10, get_fixed_font_sizes()["sz_input"] - 1)
        return konversi_font_qss_ke_point(get_buku_gudang_menu_style(ukuran, self._tema_gelap_aktif()))

    def _buat_checkbox_menu_bulan(self, label):
        checkbox = QCheckBox(label, self.menu_bulan)
        checkbox.setMinimumWidth(BUKU_GUDANG_MONTH_CHECKBOX_MIN_WIDTH)
        checkbox.setStyleSheet("QCheckBox { padding: 4px 8px; }")
        action = QWidgetAction(self.menu_bulan)
        action.setDefaultWidget(checkbox)
        self.menu_bulan.addAction(action)
        return checkbox

    def setup_menu_bulan(self):
        self.menu_bulan.clear()
        self.menu_bulan.setStyleSheet(self._style_menu_filter_periode())
        self._checkbox_bulan = {}

        self._checkbox_semua_bulan = self._buat_checkbox_menu_bulan("Semua Bulan")
        self._checkbox_semua_bulan.toggled.connect(
            self._on_checkbox_semua_bulan_changed
        )
        self.menu_bulan.addSeparator()

        for nomor, nama in enumerate(NAMA_BULAN, start=1):
            checkbox = self._buat_checkbox_menu_bulan(nama)
            checkbox.toggled.connect(
                lambda checked, n=nomor: self._on_checkbox_bulan_changed(n, checked)
            )
            self._checkbox_bulan[nomor] = checkbox

        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()

    def _sinkronkan_checkbox_bulan(self):
        if not self._checkbox_bulan:
            return
        pilihan = set(self._bulan_terpilih or ())
        self._sinkronisasi_checkbox_bulan = True
        try:
            if self._checkbox_semua_bulan is not None:
                self._checkbox_semua_bulan.setChecked(len(pilihan) == 12)
            for nomor, checkbox in self._checkbox_bulan.items():
                checkbox.setChecked(nomor in pilihan)
        finally:
            self._sinkronisasi_checkbox_bulan = False

    def _perbarui_label_bulan(self):
        pilihan = sorted(set(self._bulan_terpilih or ()))
        if len(pilihan) == 12:
            label = "Semua Bulan"
        elif len(pilihan) == 1:
            label = NAMA_BULAN[pilihan[0] - 1]
        else:
            label = f"{len(pilihan)} Bulan"

        if hasattr(self, "btn_bulan"):
            self.btn_bulan.setText(label)
            daftar = ", ".join(NAMA_BULAN[nomor - 1] for nomor in pilihan)
            self.btn_bulan.setToolTip(
                f"Bulan terpilih: {daftar}" if daftar else "Tidak ada bulan terpilih"
            )

    def _on_checkbox_semua_bulan_changed(self, checked):
        if self._sinkronisasi_checkbox_bulan:
            return
        self._bulan_terpilih = (
            set(range(1, 13))
            if checked
            else {datetime.now().month}
        )
        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()
        self.refresh_session_ui()

    def _on_checkbox_bulan_changed(self, nomor, checked):
        if self._sinkronisasi_checkbox_bulan:
            return

        pilihan = set(self._bulan_terpilih or ())
        if checked:
            pilihan.add(int(nomor))
        else:
            pilihan.discard(int(nomor))

        if not pilihan:
            pilihan.add(int(nomor))

        self._bulan_terpilih = pilihan
        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()
        self.refresh_session_ui()

    def ubah_bulan(self, bulan):
        if bulan is None:
            pilihan = set(range(1, 13))
        elif isinstance(bulan, (list, tuple, set, frozenset)):
            pilihan = {
                int(nilai)
                for nilai in bulan
                if str(nilai).strip().isdigit() and 1 <= int(nilai) <= 12
            }
        else:
            try:
                nomor = int(bulan)
            except (TypeError, ValueError):
                nomor = 0
            pilihan = {nomor} if 1 <= nomor <= 12 else set()

        if not pilihan:
            pilihan = {datetime.now().month}

        self._bulan_terpilih = pilihan
        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()
        self.refresh_session_ui()

    def setup_menu_status_penagihan(self):
        self.menu_status_penagihan.clear()
        self.menu_status_penagihan.setStyleSheet(self._style_menu_filter_periode())
        pilihan = (
            ("Semua Tagihan", StatusTagihan.SEMUA),
            ("Belum Invoice", StatusTagihan.BELUM_INVOICE),
            ("Belum Lunas", StatusTagihan.BELUM_LUNAS),
            ("Lunas", StatusTagihan.LUNAS),
            ("Macet", StatusTagihan.MACET),
        )
        for label, nilai in pilihan:
            action = self.menu_status_penagihan.addAction(label)
            action.triggered.connect(
                lambda _, l=label, n=nilai: self.ubah_status_penagihan(l, n)
            )

    def ubah_status_penagihan(self, label, nilai):
        nilai_status = getattr(nilai, "value", nilai)
        self._status_penagihan_terpilih = str(
            nilai_status or StatusTagihan.SEMUA.value
        ).strip().upper()
        self.btn_status_penagihan.setText(str(label or "Semua Tagihan"))
        self.refresh_session_ui()

    def reset_semua_filter(self):
        sekarang = datetime.now()
        self.btn_tahun.setText(str(sekarang.year))
        self._bulan_terpilih = {sekarang.month}
        self._status_penagihan_terpilih = "SEMUA"
        self.btn_status_penagihan.setText("Semua Tagihan")
        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()

        for tab_widget in self.tabs_list:
            if hasattr(tab_widget, "filter_data"):
                tab_widget.filter_data.clear()

        if self.txt_cari.text():
            status_signal = self.txt_cari.blockSignals(True)
            try:
                self.txt_cari.clear()
            finally:
                self.txt_cari.blockSignals(status_signal)

        self.refresh_session_ui()

    @staticmethod
    def _kode_cabang_aktif():
        return CURRENT_SESSION.get("kode_cabang", "PUSAT")

    def _buat_menu_buku_gudang(self):
        menu = QMenu()
        ukuran = get_fixed_font_sizes()["sz_input"]
        menu.setStyleSheet(
            konversi_font_qss_ke_point(get_buku_gudang_menu_style(ukuran, self._tema_gelap_aktif()))
        )
        return menu

    def get_editor_type(self, col_index):
        if col_index in (self.KOL_MASUK, self.KOL_KELUAR):
            return "date"
        if col_index == self.KOL_STATUS:
            return "status"
        if col_index == self.KOL_STATUS_PENAGIHAN:
            return "billing_status"
        if col_index == self.KOL_PAYMENT:
            return "payment"
        return "text"

    @db_service.profile_performance("BukuGudang.search_filter", threshold=0.025)
    def filter_pencarian_tabel(self):
        current_tab = self.tabs_wilayah.currentWidget()
        if not current_tab or not hasattr(current_tab, "tabel"):
            return

        search_all_year = bool(self.txt_cari.text().strip())
        if search_all_year != getattr(current_tab, "_buku_gudang_search_mode", False):
            self.load_data(current_tab)
            return

        self._terapkan_pencarian_ke_tabel(current_tab.tabel)
        if not getattr(current_tab, "_loading", False):
            self._perbarui_status_data(current_tab)

    def _buat_editor_filter(self, editor_type):
        if editor_type == "date":
            editor = QDateEdit()
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
            editor.setDate(QDate.currentDate())
            return editor
        if editor_type == "status":
            editor = QComboBox()
            editor.addItems(["", "DI GUDANG", "PERJALANAN", "SELESAI"])
            return editor
        if editor_type == "billing_status":
            editor = QComboBox()
            editor.addItems(["", "BELUM INVOICE", "BELUM LUNAS", "LUNAS", "MACET"])
            return editor
        if editor_type == "payment":
            editor = QComboBox()
            editor.addItems(["TF / INVOICE", "CASH"])
            return editor
        return QLineEdit()

    def show_header_menu(self, pos, tabel, *, forced_col=None, menu_global_pos=None):
        col = (
            int(forced_col)
            if forced_col is not None
            else tabel.horizontalHeader().logicalIndexAt(pos)
        )
        if col < 0 or col >= tabel.columnCount():
            return

        menu = self._buat_menu_buku_gudang()
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel(f"Filter {self.HEADERS[col]}:"))
        editor = self._buat_editor_filter(self.get_editor_type(col))
        layout.addWidget(editor)

        action = QWidgetAction(menu)
        action.setDefaultWidget(container)
        menu.addAction(action)
        menu.addSeparator()
        menu.addAction(
            "Pasang Filter",
            lambda: self.apply_filter(tabel, col, editor, menu),
        )
        menu.addAction("Hapus Filter", lambda: self.reset_filter(tabel, col, menu))
        global_pos = (
            menu_global_pos
            if menu_global_pos is not None
            else tabel.horizontalHeader().viewport().mapToGlobal(pos)
        )
        menu.exec(global_pos)

    def apply_filter(self, tabel, col, editor, menu):
        tab_widget = self._ambil_tab_widget_dari_tabel(tabel)
        if tab_widget is None:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Container tab Buku Gudang tidak ditemukan.",
            )
            menu.close()
            return

        val = editor.date().toString("yyyy-MM-dd") if isinstance(
            editor,
            QDateEdit,
        ) else editor.currentText() if isinstance(
            editor,
            QComboBox,
        ) else editor.text().strip()

        filter_key = self.FILTER_KEY_BY_COLUMN.get(col)
        if filter_key is None:
            QMessageBox.warning(
                self,
                "Filter tidak tersedia",
                "Kolom ini tidak memiliki definisi filter.",
            )
            menu.close()
            return

        if val:
            tab_widget.filter_data[filter_key] = val
        else:
            tab_widget.filter_data.pop(filter_key, None)

        self.load_data(tab_widget)
        menu.close()

    def reset_filter(self, tabel, col, menu):
        tab_widget = self._ambil_tab_widget_dari_tabel(tabel)
        filter_key = self.FILTER_KEY_BY_COLUMN.get(col)
        if tab_widget is not None and filter_key is not None:
            tab_widget.filter_data.pop(filter_key, None)
            self.load_data(tab_widget)
        menu.close()

    def _jumlah_resi_context(self, tabel, row):
        baris_awal = {item.row() for item in tabel.selectedItems()}
        if row not in baris_awal:
            tabel.selectRow(row)

        resi = {
            self._no_resi_dari_baris(tabel, baris)
            for baris in {item.row() for item in tabel.selectedItems()}
            if self._no_resi_dari_baris(tabel, baris)
        }
        return len(resi)

    def _buat_action_context(self, menu, item, item_resi, row, jumlah_resi):
        mode_normal = self.row_sedang_diedit == -1
        no_invoice = (
            str(item_resi.data(self.ROLE_INVOICE_NO) or "").strip().upper()
            if item_resi else ""
        )

        if jumlah_resi > 1:
            return (
                menu.addAction(f"🧾 Buat Invoice Gabungan ({jumlah_resi} Resi)")
                if mode_normal else None,
                None,
                None,
                None,
                menu.addAction("✅ Tandai 'SELESAI' Massal") if mode_normal else None,
                None,  # Aksi lihat invoice untuk multi-row
            )

        # Aksi Lihat Invoice (Secara Umum per Baris)
        action_lihat = menu.addAction("📄 Lihat Invoice") if mode_normal else None
        if action_lihat:
            action_lihat.setEnabled(bool(no_invoice))

        return (
            menu.addAction("🧾 Buat Invoice dari Resi Ini") if mode_normal else None,
            menu.addAction("✏️ Edit Baris Ini") if mode_normal else None,
            menu.addAction("💾 Simpan Perubahan") if self.row_sedang_diedit == row else None,
            menu.addAction("❌ Batalkan Edit") if self.row_sedang_diedit == row else None,
            menu.addAction("✅ Tandai 'SELESAI'")
            if item.column() == self.KOL_STATUS and mode_normal else None,
            action_lihat,  # Tambahkan ke tuple return
        )

    def _actions_status_penagihan(self, menu, item, item_resi):
        if item is None or item.column() != self.KOL_STATUS_PENAGIHAN or item_resi is None:
            return {}
        no_invoice = str(item_resi.data(self.ROLE_INVOICE_NO) or "").strip().upper()
        if not no_invoice:
            return {}

        status = str(item_resi.data(self.ROLE_INVOICE_STATUS) or "").strip().upper()
        menu.addSeparator()
        action_lunas = menu.addAction("Tandai LUNAS")
        action_macet = menu.addAction("Tandai MACET")
        action_reset = menu.addAction("Kembalikan ke Belum Lunas")

        action_lunas.setEnabled(status != StatusTagihan.LUNAS)
        action_macet.setEnabled(status != StatusTagihan.MACET)
        action_reset.setEnabled(status in {StatusTagihan.LUNAS, StatusTagihan.MACET})

        return {
            action_lunas: (no_invoice, StatusTagihan.LUNAS),
            action_macet: (no_invoice, StatusTagihan.MACET),
            action_reset: (no_invoice, StatusTagihan.BELUM_LUNAS),
        }

    def _konfirmasi_status_penagihan(self, no_invoice, status_baru):
        if status_baru == "LUNAS":
            pesan = (
                f"Tandai Invoice {no_invoice} sebagai LUNAS?\n\n"
                "Seluruh Resi aktif dalam Invoice ini akan otomatis ditandai SELESAI."
            )
        elif status_baru == "MACET":
            pesan = (
                f"Tandai Invoice {no_invoice} sebagai MACET?\n\n"
                "Status Resi tidak akan diubah dan highlight merah akan menjadi prioritas."
            )
        else:
            pesan = (
                f"Kembalikan Invoice {no_invoice} ke BELUM LUNAS?\n\n"
                "Status Resi yang sudah SELESAI tidak akan dibatalkan otomatis."
            )
        jawaban = QMessageBox.question(
            self,
            "Konfirmasi Status Penagihan",
            pesan,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return jawaban == QMessageBox.StandardButton.Yes

    def ubah_status_penagihan_invoice(self, no_invoice, status_baru):
        invoice = str(no_invoice or "").strip().upper()
        status = str(getattr(status_baru, "value", status_baru) or "").strip().upper()
        if not invoice or not self._konfirmasi_status_penagihan(invoice, status):
            return False
        try:
            sukses, pesan = db_service.ubah_status_penagihan_invoice(
                invoice, status, self._kode_cabang_aktif()
            )
            if not sukses:
                QMessageBox.warning(
                    self, "Status Penagihan", pesan or "Status penagihan gagal diperbarui."
                )
                return False
            self.refresh_session_ui()
            QMessageBox.information(
                self, "Status Penagihan", pesan or f"Invoice {invoice} diperbarui."
            )
            return True
        except Exception as error:
            QMessageBox.critical(
                self, "Error", f"Gagal mengubah status penagihan:\n{error}"
            )
            self.refresh_session_ui()
            return False

    def buka_popup_edit_buku_gudang(self, tabel, row):
        try:
            no_resi = self._no_resi_dari_baris(tabel, row)
            cabang = self._kode_cabang_aktif()
            snapshot = db_service.ambil_data_edit_buku_gudang(no_resi, cabang)
            if snapshot is None:
                QMessageBox.warning(self, "Edit Data", "Resi tidak ditemukan. Muat ulang tabel.")
                return
            header = snapshot["header"]
            data = {
                **header,
                "wilayah": getattr(self._ambil_tab_widget_dari_tabel(tabel), "wilayah", ""),
                "keterangan": header.get("ket_buku_gudang") or "",
                "detail_barang": snapshot["barang"],
            }

            def simpan(hasil):
                updates = {
                    key: hasil[key]
                    for key in ("pengirim", "kota_asal", "penerima", "kota_tujuan", "total_ongkir")
                }
                updates["ket_buku_gudang"] = hasil["keterangan"]
                if not self._konfirmasi_edit_resi_terinvoice(no_resi, updates):
                    return False
                berhasil = db_service.update_baris_buku_gudang(
                    no_resi, cabang, updates,
                    expected_revision=snapshot["revision"],
                    detail_barang=hasil["detail_barang"],
                )
                if not berhasil:
                    QMessageBox.warning(
                        self, "Gagal Menyimpan",
                        "Perubahan belum tersimpan. Resi mungkin sudah berubah atau database gagal diakses. "
                        "Isian tetap ada di editor. Jika resi sudah berubah, tutup editor dan muat ulang tabel.",
                    )
                return berhasil

            hasil = open_buku_gudang_edit_popup(self, data, on_save=simpan)
            if hasil is None:
                return
            self.refresh_session_ui()
            QMessageBox.information(
                self, "Edit Data", f"Data dan detail barang Resi {no_resi} berhasil disimpan.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Edit Data", str(exc))

    def show_cell_context_menu(self, pos, tabel, *, frozen_view=None):
        if frozen_view is not None:
            row = frozen_view.rowAt(pos.y())
            item = tabel.item(row, self.KOL_RESI) if row >= 0 else None
            menu_global_pos = frozen_view.viewport().mapToGlobal(pos)
        else:
            item = tabel.itemAt(pos)
            row = item.row() if item is not None else -1
            menu_global_pos = tabel.viewport().mapToGlobal(pos)
        if item is None:
            return

        if not item.isSelected():
            tabel.clearSelection()
            tabel.selectRow(row)
        menu = self._buat_menu_buku_gudang()
        item_resi = tabel.item(row, self.KOL_RESI)
        actions_penagihan = self._actions_status_penagihan(menu, item, item_resi)
        actions = self._buat_action_context(
            menu, item, item_resi, row, self._jumlah_resi_context(tabel, row)
        )
        action = menu.exec(menu_global_pos)
        if action is None:
            return

        if action in actions_penagihan:
            no_invoice, status_baru = actions_penagihan[action]
            self.ubah_status_penagihan_invoice(no_invoice, status_baru)
            return

        # Unpack 6 tuple aksi
        buat_invoice, edit, simpan, batal, selesai, lihat_invoice = actions

        if action == lihat_invoice:
            no_invoice = (
                str(item_resi.data(self.ROLE_INVOICE_NO) or "").strip()
                if item_resi else ""
            )
            if no_invoice:
                self.buka_invoice_dari_buku_gudang(no_invoice)
        elif action == edit:
            self.buka_popup_edit_buku_gudang(tabel, row)
        elif action == simpan:
            self.eksekusi_simpan_baris_ke_db(tabel, row)
        elif action == batal:
            self.refresh_session_ui()
        elif action == selesai:
            self.tandai_selesai_massal(tabel)
        elif action == buat_invoice:
            self.proses_simpan_ke_invoice()

    def _pasang_validator_editor_inline(self, editor, col):
        if col == self.KOL_KOLI:
            editor.setValidator(
                get_integer_validator(parent=editor, minimum=0, maximum=999_999)
            )
        elif col == self.KOL_ONGKIR:
            editor.setValidator(
                get_integer_validator(parent=editor, minimum=0, maximum=2_147_483_647)
            )
        elif col in self.KOLOM_DESIMAL:
            editor.setValidator(
                get_decimal_validator(
                    parent=editor,
                    decimals=2,
                    minimum=0.0,
                    maximum=999_999_999.99,
                )
            )
        else:
            editor.textChanged.connect(
                lambda _, le=editor: paksa_kapital_lineedit(le)
            )

    def _ambil_autocomplete_nama_buku_gudang(self):
        cabang = self._kode_cabang_aktif()
        sekarang = perf_counter()
        cache = self._autocomplete_cache.get(cabang)
        if cache is not None and (sekarang - cache[0]) < self.AUTOCOMPLETE_CACHE_TTL:
            return cache[1]

        try:
            pengirim, penerima = db_service.ambil_data_autocomplete(cabang)
        except Exception:
            return [], []

        def normalisasi(data):
            return sorted({
                str(item).strip().upper()
                for item in (data or [])
                if str(item).strip()
            })

        hasil = (normalisasi(pengirim), normalisasi(penerima))
        self._autocomplete_cache[cabang] = (sekarang, hasil)
        return hasil

    @staticmethod
    def _pasang_autocomplete_nama(editor, daftar_nama):
        if not isinstance(editor, QLineEdit) or not daftar_nama:
            return

        completer = QCompleter(daftar_nama, editor)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(BUKU_GUDANG_AUTOCOMPLETE_MAX_VISIBLE_ITEMS)
        editor.setCompleter(completer)
        editor.textEdited.connect(
            lambda text, c=completer: c.complete() if str(text).strip() else None
        )

    def _buat_editor_inline(self, tabel, row, col, teks_asal):
        if col == self.KOL_PAYMENT:
            editor = QComboBox()
            editor.addItems(["", "TF / INVOICE", "CASH"])
            editor.setCurrentText(teks_asal)
            editor.activated.connect(lambda: self.eksekusi_simpan_baris_ke_db(tabel, row))
        else:
            editor = QLineEdit()
            editor.is_numeric_col = col in self.KOLOM_NUMERIK
            teks = teks_asal.strip()
            editor.setText("" if editor.is_numeric_col and teks == "-" else (
                teks.replace(".", "") if editor.is_numeric_col else teks
            ))
            editor.setStyleSheet(getattr(self, "inline_editor_style", ""))
            atur_editor_sel(editor)
            self._pasang_validator_editor_inline(editor, col)
            editor.returnPressed.connect(lambda: self.eksekusi_simpan_baris_ke_db(tabel, row))

        editor.installEventFilter(self)
        return editor

    def aktifkan_mode_edit_baris(self, tabel, row):
        item_resi = tabel.item(row, self.KOL_RESI)
        details = item_resi.data(self.ROLE_DETAIL_ROWS) if item_resi else []
        if len(details or []) > 1:
            self.buka_popup_edit_buku_gudang(tabel, row)
            return
        self.row_sedang_diedit = row
        is_parent = True
        pengirim_autocomplete, penerima_autocomplete = (
            self._ambil_autocomplete_nama_buku_gudang()
            if is_parent
            else ([], [])
        )
        kolom_edit = (
            range(self.KOL_PENGIRIM, self.KOL_KETERANGAN + 1)
            if is_parent
            else range(self.KOL_NAMA_BARANG, self.KOL_CBM + 1)
        )
        for col in kolom_edit:
            item = tabel.item(row, col)
            editor = self._buat_editor_inline(
                tabel, row, col, item.text() if item else ""
            )
            if col == self.KOL_PENGIRIM:
                self._pasang_autocomplete_nama(editor, pengirim_autocomplete)
            elif col == self.KOL_PENERIMA:
                self._pasang_autocomplete_nama(editor, penerima_autocomplete)
            tabel.setCellWidget(row, col, editor)

        kolom_fokus = self.KOL_PENGIRIM if is_parent else self.KOL_NAMA_BARANG
        editor_awal = tabel.cellWidget(row, kolom_fokus)
        if editor_awal:
            editor_awal.setFocus()

    @staticmethod
    def _teks_status_penagihan(no_invoice, status):
        """Tampilkan status tagihan saja, tanpa nomor invoice atau tanggal."""
        status_norm = str(status or "").strip().upper()
        if status_norm:
            return status_norm

        return (
            "BELUM INVOICE"
            if not str(no_invoice or "").strip()
            else "BELUM LUNAS"
        )

    @staticmethod
    def _tooltip_qss(is_dark):
        return get_buku_gudang_tooltip_style(is_dark)

    def buka_invoice_dari_buku_gudang(self, no_invoice):
        invoice = str(no_invoice or "").strip().upper()
        if not invoice:
            return False
        tab_invoice = self._cari_tab_invoice()
        if tab_invoice is None or not hasattr(tab_invoice, "load_invoice_by_no"):
            QMessageBox.critical(
                self,
                "Tab Invoice Tidak Ditemukan",
                "Tab Invoice tidak ditemukan atau tidak mendukung pembukaan invoice langsung.",
            )
            return False
        if not tab_invoice.load_invoice_by_no(invoice):
            return False
        if not self._pindah_ke_tab_invoice(tab_invoice):
            QMessageBox.information(
                self,
                "Invoice Dibuka",
                f"Invoice {invoice} sudah dimuat, tetapi tab utama tidak dapat dipindahkan otomatis.",
            )
        return True

    def _format_cell_buku_gudang(self, data, col, wilayah):
        if col == self.KOL_KOTA_TUJUAN:
            display = str(data).upper() if data is not None else ""
            prefix = str(wilayah or "").strip().upper()
            if prefix and display.startswith(prefix):
                sisa = display[len(prefix):].lstrip()
                if not sisa or sisa.startswith("-"):
                    return sisa.removeprefix("-").strip()
            return display
        if col in self.KOLOM_TANGGAL:
            if data and "-" in str(data):
                return format_tanggal_ke_ui(data)
            return str(data).upper() if data is not None else ""
        if col == self.KOL_KOLI:
            teks = str(data).strip() if data is not None else ""
            return teks.upper() if teks and teks != "0" else "-"
        if col == self.KOL_ONGKIR:
            teks = str(data).strip() if data is not None else ""
            return format_ke_rupiah(data) if teks not in {"", "0", "0.0", "None"} else "-"
        if col in self.KOLOM_DESIMAL:
            return format_angka_indonesia(data, kosong_jika_nol=True, nilai_kosong="-")
        return str(data).upper() if data is not None else ""


    def _jadwalkan_tinggi_baris(self, tabel):
        timer = getattr(tabel, "_buku_gudang_row_timer", None)
        if (
            timer is not None
            and not getattr(tabel, "_syncing_row_heights", False)
            and getattr(tabel, "_render_state", None) is None
        ):
            timer.start(0)

    def _sinkronkan_baris_resi(self, tabel):
        """Atur tinggi baris sesuai jumlah detail dan sinkronkan Frozen Table."""
        if getattr(tabel, "_syncing_row_heights", False):
            return
        timer = getattr(tabel, "_buku_gudang_row_timer", None)
        if timer is not None:
            timer.stop()

        model = tabel.model()
        if model is None or tabel.rowCount() <= 0:
            return

        base_height = max(1, tabel.verticalHeader().defaultSectionSize())
        line_pitch = BukuGudangFastPaintDelegate.jarak_baris(tabel.fontMetrics())
        tabel._syncing_row_heights = True
        try:
            detail_count_at = getattr(model, "detailCountAt", None)
            for row in range(tabel.rowCount()):
                if detail_count_at is not None:
                    count = detail_count_at(row)
                else:
                    index = model.index(row, self.KOL_RESI)
                    count = model.data(index, self.ROLE_DETAIL_COUNT) or 1
                try:
                    count = max(1, int(count))
                except (TypeError, ValueError):
                    count = 1
                height = base_height + (count - 1) * line_pitch
                if tabel.rowHeight(row) != height:
                    # FrozenTableView.setRowHeight also updates the frozen view.
                    tabel.setRowHeight(row, height)
        finally:
            tabel._syncing_row_heights = False


    def _setelah_urutan_berubah(self, tabel):
        self._jadwalkan_tinggi_baris(tabel)
        if getattr(tabel, "_render_state", None) is None:
            tabel._buku_gudang_search_keyword = ""
            tabel._buku_gudang_hidden_rows = set()
            self._terapkan_pencarian_ke_tabel(tabel)

    def _isi_baris_tabel(self, tabel, wilayah, detail_rows, target_row=None):
        """Siapkan satu record model untuk satu resi, tanpa QTableWidgetItem per sel."""
        row = detail_rows[0]
        pos = tabel.rowCount() if target_row is None else target_row
        if target_row is None:
            tabel.insertRow(pos)

        def val(idx, default=""):
            return row[idx] if len(row) > idx and row[idx] is not None else default

        no_resi = str(val(DBIndex.RESI)).strip()
        detail_id = val(DBIndex.DETAIL_ID, None)
        revision = int(val(DBIndex.REVISION, 0))
        no_invoice = str(val(DBIndex.NO_INVOICE)).strip().upper()
        status_invoice = str(val(DBIndex.STATUS_INVOICE)).strip().upper()
        status_resi = str(val(DBIndex.STATUS_RESI)).strip().upper()
        status_penagihan = self._teks_status_penagihan(no_invoice, status_invoice)

        values = (
            val(DBIndex.RESI), val(DBIndex.MASUK), val(DBIndex.KELUAR),
            val(DBIndex.STATUS_RESI), status_penagihan, val(DBIndex.TRUK),
            val(DBIndex.PENGIRIM), val(DBIndex.KOTA_ASAL), val(DBIndex.PENERIMA),
            val(DBIndex.KOTA_TUJUAN), val(DBIndex.NAMA_BARANG), val(DBIndex.KOLI),
            val(DBIndex.BERAT), val(DBIndex.CBM), val(DBIndex.ONGKIR),
            val(DBIndex.PAYMENT), val(DBIndex.KETERANGAN),
        )

        display_values = []
        tooltips = {}
        kolom_detail = self.KOLOM_DETAIL_DB
        for col, data in enumerate(values):
            idx = kolom_detail.get(col)
            if idx is not None:
                detail_values = [
                    " ".join(
                        self._format_cell_buku_gudang(detail[idx], col, wilayah).split()
                    ) or "-"
                    for detail in detail_rows
                ]
                tampil = "\n".join(detail_values)
                if len(detail_rows) > 1:
                    tooltips[col] = " • ".join(detail_values)
            else:
                tampil = self._format_cell_buku_gudang(data, col, wilayah)
                if col == self.KOL_TRUK:
                    nama_kapal = str(val(DBIndex.NAMA_KAPAL)).strip()
                    if nama_kapal and nama_kapal.casefold() not in str(tampil).casefold():
                        if str(tampil).strip() in ("", "-"):
                            tampil = nama_kapal
                        else:
                            tampil = f"{tampil} | {nama_kapal}"
            display_values.append(tampil)

        roles = {
            self.ROLE_NO_RESI: no_resi,
            self.ROLE_DETAIL_ID: detail_id,
            self.ROLE_REVISION: revision,
            self.ROLE_INVOICE_NO: no_invoice,
            self.ROLE_INVOICE_STATUS: status_invoice,
            self.ROLE_STATUS_HIGHLIGHT: f"{status_invoice}|{status_resi}",
            self.ROLE_SEARCH_TEXT: " ".join(display_values).replace("\n", " ").casefold(),
        }
        if len(detail_rows) > 1:
            roles[self.ROLE_DETAIL_ROWS] = detail_rows

        tabel.setRowData(pos, display_values, roles, tooltips)

    @db_service.profile_performance("BukuGudang.save_table_state", threshold=0.025)
    def _simpan_state_tabel(self, tabel):
        if tabel is None:
            return
        rows = self._ambil_baris_terseleksi_invoice(tabel)
        self._table_state[id(tabel)] = {
            "vertical": tabel.verticalScrollBar().value(),
            "horizontal": tabel.horizontalScrollBar().value(),
            "selected_resi": {self._no_resi_dari_baris(tabel, row) for row in rows},
            "current_resi": self._no_resi_dari_baris(tabel, tabel.currentRow()),
            "current_column": max(0, tabel.currentColumn()),
        }

    @db_service.profile_performance("BukuGudang.restore_table_state", threshold=0.025)
    def _pulihkan_state_tabel(self, tabel):
        state = self._table_state.get(id(tabel)) if tabel is not None else None
        if not state:
            return
        selection_model = tabel.selectionModel()
        wanted = state.get("selected_resi", set()) or set()
        current_resi = state.get("current_resi")
        if selection_model is not None and (wanted or current_resi):
            selection = QItemSelection()
            model = tabel.model()
            current_index = None
            current_column = state.get("current_column", 0)
            last_column = tabel.columnCount() - 1
            for row in range(tabel.rowCount()):
                no_resi = self._no_resi_dari_baris(tabel, row)
                if current_resi and no_resi == current_resi:
                    current_index = model.index(row, current_column)
                if no_resi in wanted and not tabel.isRowHidden(row):
                    selection.select(model.index(row, 0), model.index(row, last_column))
            selection_model.clearSelection()
            if current_index is not None:
                selection_model.setCurrentIndex(
                    current_index, QItemSelectionModel.SelectionFlag.NoUpdate
                )
            if not selection.isEmpty():
                selection_model.select(selection, QItemSelectionModel.SelectionFlag.Select)
        tabel.verticalScrollBar().setValue(state.get("vertical", 0))
        tabel.horizontalScrollBar().setValue(state.get("horizontal", 0))

    def _perbarui_status_data(self, tab_widget=None, status=None):
        """Tampilkan status pemuatan dan jumlah hasil tanpa mengubah data tabel."""
        label = getattr(self, "lbl_status_data", None)
        if label is None:
            return

        if tab_widget is None:
            tab_widget = self.tabs_wilayah.currentWidget()
        if tab_widget is None or self.tabs_wilayah.currentWidget() is not tab_widget:
            return

        if status == "loading":
            label.setText("Memuat data...")
            return
        if status == "error":
            label.setText("Gagal memuat data")
            return

        tabel = getattr(tab_widget, "tabel", None)
        if tabel is None:
            label.clear()
            return

        total = tabel.rowCount()
        keyword = self.txt_cari.text().strip()
        visible = (
            total - len(getattr(tabel, "_buku_gudang_hidden_rows", ()))
            if keyword else total
        )
        if keyword:
            tahun_cakupan = getattr(
                tab_widget, "_buku_gudang_query_year", str(datetime.now().year)
            )
            if visible == 0:
                label.setText(f"Pencarian {tahun_cakupan} · Tidak ada hasil")
            else:
                label.setText(
                    f"Pencarian {tahun_cakupan} · {visible} dari {total} resi"
                )
        else:
            label.setText(f"{total} resi")

    @db_service.profile_performance("BukuGudang.request_table_load", threshold=0.025)
    def load_data(self, tab_widget):
        tabel = tab_widget.tabel
        cabang, wilayah, tahun_query, filters, search_all_year = (
            self._parameter_query_buku_gudang(tab_widget)
        )
        signature = self._signature_query_buku_gudang(
            cabang, wilayah, tahun_query, filters
        )

        tab_widget._buku_gudang_search_mode = search_all_year
        tab_widget._buku_gudang_query_year = tahun_query
        tab_widget._buku_gudang_loading_signature = signature
        tab_widget._buku_gudang_cache_stale = True
        tab_widget._buku_gudang_loading_invalidation_generation = getattr(
            tab_widget, "_buku_gudang_invalidation_generation", 0
        )

        if not tab_widget._loading:
            self._simpan_state_tabel(tabel)
            tab_widget._table_was_enabled = tabel.isEnabled()
        tab_widget._load_generation += 1
        tab_widget._loading = True
        self._perbarui_status_data(tab_widget, "loading")
        tab_widget._render_timer.stop()
        if getattr(tabel, "_render_state", None) is not None:
            tabel._render_state = None
            self._pulihkan_tabel_setelah_loading(tabel)
        tabel.setEnabled(False)
        tab_widget._load_pending = (
            tab_widget._load_generation, cabang,
            wilayah, tahun_query, filters,
        )
        if tab_widget._load_worker is None:
            self._mulai_request_data(tab_widget)

    def _mulai_request_data(self, tab_widget):
        request = tab_widget._load_pending
        if request is None:
            return
        tab_widget._load_pending = None
        generation, cabang, wilayah, tahun, filters = request
        worker = DatabaseWorkerBukuGudang(cabang, wilayah, tahun, filters)
        worker.tab_ref = ref(tab_widget)
        worker.generation = generation
        tab_widget._load_worker = worker
        worker.data_ready.connect(self._hasil_worker_data, Qt.ConnectionType.QueuedConnection)
        worker.error_occurred.connect(self._error_worker_data, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._worker_data_selesai, Qt.ConnectionType.QueuedConnection)
        worker.start()

    @Slot(list)
    def _hasil_worker_data(self, rows):
        worker = self.sender()
        tab_widget = worker.tab_ref()
        if tab_widget is not None and worker.generation == tab_widget._load_generation:
            self._proses_hasil_data(rows, tab_widget)

    @Slot(str)
    def _error_worker_data(self, error_msg):
        worker = self.sender()
        tab_widget = worker.tab_ref()
        if tab_widget is not None and worker.generation == tab_widget._load_generation:
            self._tampilkan_error_db(error_msg, tab_widget)

    @Slot()
    def _worker_data_selesai(self):
        worker = self.sender()
        tab_widget = worker.tab_ref()
        if tab_widget is not None and tab_widget._load_worker is worker:
            tab_widget._load_worker = None
            self._mulai_request_data(tab_widget)

    @db_service.profile_performance("BukuGudang.prepare_table_render", threshold=0.025)
    def _proses_hasil_data(self, groups, tab_widget):
        tabel = tab_widget.tabel
        try:
            groups = groups or []
            targets = [tabel]
            tabel._loading_view_state = (
                tabel.isSortingEnabled(),
                [(target, target.signalsBlocked(), target.updatesEnabled()) for target in targets],
            )
            tabel._buku_gudang_hidden_rows = set()
            tabel._buku_gudang_search_keyword = ""
            tabel._render_state = {
                "generation": tab_widget._load_generation,
                "groups": groups, "position": 0,
            }
            for target in targets:
                target.blockSignals(True)
                target.setUpdatesEnabled(False)
            tabel.setSortingEnabled(False)
            tabel.setRowCount(len(groups))
            tab_widget._render_timer.start(0)
        except Exception as error:
            self._gagal_render(error, tab_widget)

    @db_service.profile_performance("BukuGudang.render_table_batch", threshold=0.025)
    def _render_batch(self, tab_widget):
        tabel = tab_widget.tabel
        state = getattr(tabel, "_render_state", None)
        if state is None or state["generation"] != tab_widget._load_generation:
            return
        try:
            started = perf_counter()
            batch_start = state["position"]
            stop = min(batch_start + self.RENDER_BATCH_SIZE, len(state["groups"]))
            while state["position"] < stop:
                pos = state["position"]
                self._isi_baris_tabel(tabel, tab_widget.wilayah, state["groups"][pos], pos)
                state["position"] += 1
                if (
                    (state["position"] - batch_start) % 8 == 0
                    and perf_counter() - started >= self.RENDER_TIME_BUDGET
                ):
                    break
            tabel._buku_gudang_model.flushPendingChanges()
            if state["position"] < len(state["groups"]):
                tab_widget._render_timer.start(0)
                return
            self._selesaikan_render(tab_widget)
        except Exception as error:
            self._gagal_render(error, tab_widget)

    @db_service.profile_performance("BukuGudang.finish_table_render", threshold=0.025)
    def _selesaikan_render(self, tab_widget):
        tabel = tab_widget.tabel
        self._pulihkan_tabel_setelah_loading(tabel)
        tabel._render_state = None
        tab_widget._loading = False

        self._sinkronkan_baris_resi(tabel)
        self._terapkan_pencarian_ke_tabel(tabel)
        request_invalidation_generation = getattr(
            tab_widget, "_buku_gudang_loading_invalidation_generation", 0
        )
        current_invalidation_generation = getattr(
            tab_widget, "_buku_gudang_invalidation_generation", 0
        )
        invalidated_during_load = (
            request_invalidation_generation != current_invalidation_generation
        )

        tab_widget._buku_gudang_loaded_signature = (
            None if invalidated_during_load
            else getattr(tab_widget, "_buku_gudang_loading_signature", None)
        )
        tab_widget._buku_gudang_loading_signature = None
        fingerprint = self._ambil_fingerprint_wilayah(tab_widget)
        if fingerprint is not None:
            tab_widget._buku_gudang_data_fingerprint = fingerprint
        tab_widget._buku_gudang_cache_stale = (
            invalidated_during_load or fingerprint is None
        )
        tabel.setEnabled(getattr(tab_widget, "_table_was_enabled", True))
        self._perbarui_status_data(tab_widget)

        if (
            invalidated_during_load
            and self.isVisible()
            and self.tabs_wilayah.currentWidget() is tab_widget
            and getattr(self, "row_sedang_diedit", -1) == -1
        ):
            tab_widget_ref = ref(tab_widget)
            QTimer.singleShot(
                0,
                lambda w=tab_widget_ref: (
                    self._pastikan_data_wilayah_dimuat(w()) if w() is not None else None
                ),
            )

        tab_widget_ref = ref(tab_widget)
        generation = tab_widget._load_generation
        QTimer.singleShot(
            0,
            lambda w=tab_widget_ref, g=generation: (
                self._pulihkan_posisi_loading(w(), g) if w() is not None else None
            ),
        )

    def _pulihkan_posisi_loading(self, tab_widget, generation):
        if generation != tab_widget._load_generation or tab_widget._loading:
            return
        tabel = tab_widget.tabel

        if (
            tabel.rowCount()
            and getattr(tab_widget, "_buku_gudang_initial_position_pending", False)
        ):
            self._jadwalkan_posisi_awal_bawah(tab_widget, generation)
            return

        self._pulihkan_state_tabel(tabel)

    def _jadwalkan_posisi_awal_bawah(self, tab_widget, generation=None):
        """Jadwalkan posisi awal setelah tab dan viewport benar-benar terlihat."""
        if (
            tab_widget is None
            or not getattr(tab_widget, "_buku_gudang_initial_position_pending", False)
            or getattr(tab_widget, "_loading", False)
            or not hasattr(tab_widget, "tabel")
            or tab_widget.tabel.rowCount() <= 0
        ):
            return

        if generation is None:
            generation = tab_widget._load_generation
        tab_ref = ref(tab_widget)
        QTimer.singleShot(
            0,
            lambda w=tab_ref, g=generation: (
                self._tetapkan_posisi_awal_bawah(w(), g) if w() is not None else None
            ),
        )

    def _tetapkan_posisi_awal_bawah(self, tab_widget, generation, attempt=0):
        if (
            tab_widget is None
            or generation != tab_widget._load_generation
            or tab_widget._loading
            or not getattr(tab_widget, "_buku_gudang_initial_position_pending", False)
        ):
            return

        tabel = tab_widget.tabel
        if tabel.rowCount() <= 0:
            return

        if (
            not self.isVisible()
            or not tab_widget.isVisible()
            or not tabel.isVisible()
            or tabel.viewport().height() <= 0
        ):
            return

        model = tabel.model()
        tabel.doItemsLayout()
        tabel.updateGeometries()

        if model is not None and model.rowCount() > 0 and model.columnCount() > 0:
            target_column = min(max(1, tabel.frozen_cols), model.columnCount() - 1)
            last_index = model.index(model.rowCount() - 1, target_column)
            tabel.scrollTo(
                last_index,
                QAbstractItemView.ScrollHint.PositionAtBottom,
            )

        tabel.doItemsLayout()
        tabel.updateGeometries()
        scrollbar = tabel.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        frozen = getattr(tabel, "frozen_table", None)
        if frozen is not None:
            frozen.doItemsLayout()
            frozen.updateGeometries()
            frozen.verticalScrollBar().setValue(scrollbar.value())

        if attempt < 1:
            tab_ref = ref(tab_widget)
            QTimer.singleShot(
                0,
                lambda w=tab_ref, g=generation: (
                    self._tetapkan_posisi_awal_bawah(w(), g, attempt + 1)
                    if w() is not None else None
                ),
            )
        else:
            tab_widget._buku_gudang_initial_position_pending = False

    def _gagal_render(self, error, tab_widget):
        tab_widget._render_timer.stop()
        tabel = tab_widget.tabel
        tabel._render_state = None
        tabel.setRowCount(0)
        self._pulihkan_tabel_setelah_loading(tabel)
        tab_widget._loading = False
        tab_widget._buku_gudang_loaded_signature = None
        tab_widget._buku_gudang_loading_signature = None
        tab_widget._buku_gudang_cache_stale = True
        tabel.setEnabled(getattr(tab_widget, "_table_was_enabled", True))
        self._perbarui_status_data(tab_widget, "error")
        QMessageBox.critical(self, "Error Rendering", f"Gagal memproses data masuk:\n{error}")

    def _tampilkan_error_db(self, error_msg, tab_widget):
        tab_widget.tabel.setRowCount(0)
        tab_widget._loading = False
        tab_widget._buku_gudang_loaded_signature = None
        tab_widget._buku_gudang_loading_signature = None
        tab_widget._buku_gudang_cache_stale = True
        tab_widget.tabel.setEnabled(getattr(tab_widget, "_table_was_enabled", True))
        self._perbarui_status_data(tab_widget, "error")
        QMessageBox.critical(
            self, "Error Database", f"Gagal memuat data buku gudang:\n{error_msg}"
        )

    def _pulihkan_tabel_setelah_loading(self, tabel):
        state = getattr(tabel, "_loading_view_state", None)
        if state is None:
            return
        tabel._loading_view_state = None
        sorting, targets = state
        try:
            tabel.setSortingEnabled(sorting)
        finally:
            for target, blocked, enabled in targets:
                target.blockSignals(blocked)
                target.setUpdatesEnabled(enabled)
                target.viewport().update()

    def _nilai_editor_baris(self, tabel, row, col):
        widget = tabel.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            return widget.currentText().strip().upper()
        return widget.text().strip().upper() if widget else ""

    def _normalisasi_update_baris(self, tabel, row, col, val):
        if col in (*self.KOLOM_DESIMAL, self.KOL_ONGKIR) and val in {"", "-"}:
            val = "0"
        elif col == self.KOL_KOLI and val == "-":
            val = ""

        if col == self.KOL_ONGKIR:
            return str(rupiah_to_int(val))
        if col in self.KOLOM_DESIMAL:
            return str(angka_indonesia_to_decimal(val))
        if col == self.KOL_KOTA_TUJUAN:
            tab_widget = self._ambil_tab_widget_dari_tabel(tabel)
            wilayah = str(getattr(tab_widget, "wilayah", "")).strip().upper()
            if wilayah and wilayah not in val:
                return f"{wilayah} - {val}" if val else wilayah
        return val

    def _kumpulkan_update_baris(self, tabel, row):
        return {
            field: self._normalisasi_update_baris(
                tabel, row, col, self._nilai_editor_baris(tabel, row, col)
            )
            for col, field in self.KOLOM_DB.items()
        }

    @staticmethod
    def _pesan_proteksi_invoice(no_resi, teks_invoice, perubahan_finansial):
        pembuka = f"Resi {no_resi} sudah digunakan pada Invoice:\n{teks_invoice}\n\n"
        if perubahan_finansial:
            return (
                pembuka
                + "Anda mengubah data finansial (ongkir atau payment). Perubahan "
                  "di Buku Gudang TIDAK otomatis memperbarui Invoice yang sudah dibuat."
                  "\n\nTetap simpan perubahan Resi?"
            )
        return (
            pembuka
            + "Invoice tersebut tetap menjadi snapshot lama dan tidak ikut berubah."
              "\n\nTetap simpan perubahan Resi?"
        )

    def _konfirmasi_edit_resi_terinvoice(self, no_resi, updates):
        try:
            proteksi = db_service.cek_proteksi_invoice_resi(
                no_resi, updates, self._kode_cabang_aktif()
            )
        except Exception as error:
            QMessageBox.warning(
                self, "Pemeriksaan Invoice Gagal",
                f"Status keterkaitan invoice belum dapat diperiksa. "
                f"Perubahan belum disimpan. Coba lagi.\n\n{error}",
            )
            return False

        if not proteksi.get("terkait"):
            return True

        daftar = []
        for info in proteksi.get("invoices", []):
            nomor = str(info.get("no_invoice") or "").strip()
            status = str(info.get("status") or "").strip()
            daftar.append(f"{nomor} ({status})" if status else nomor)
        teks_invoice = ", ".join(item for item in daftar if item) or "Invoice terkait"

        pesan = self._pesan_proteksi_invoice(
            no_resi,
            teks_invoice,
            proteksi.get("perubahan_finansial"),
        )
        jawaban = QMessageBox.warning(
            self,
            "Resi Sudah Masuk Invoice",
            pesan,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return jawaban == QMessageBox.StandardButton.Yes

    def _updates_editor_baris(self, tabel, row, is_parent):
        if is_parent:
            return self._kumpulkan_update_baris(tabel, row)

        return {
            self.KOLOM_DB[col]: self._normalisasi_update_baris(
                tabel, row, col, self._nilai_editor_baris(tabel, row, col)
            )
            for col in (
                self.KOL_NAMA_BARANG,
                self.KOL_KOLI,
                self.KOL_BERAT,
                self.KOL_CBM,
            )
        }

    def _tampilkan_gagal_simpan_baris(self, no_resi, revision_awal):
        revision_sekarang = None
        try:
            detail = db_service.ambil_detail_resi(no_resi)
            if detail and len(detail) > 20:
                revision_sekarang = int(detail[20] or 0)
        except Exception:
            pass
        konflik = (
            revision_awal is not None
            and revision_sekarang is not None
            and revision_sekarang != revision_awal
        )
        if konflik:
            QMessageBox.warning(
                self,
                "Data Resi Berubah",
                "Data Resi telah berubah dari modul lain. "
                "Data akan dimuat ulang sebelum Anda mengedit kembali.",
            )
        else:
            QMessageBox.critical(
                self,
                "Gagal Menyimpan",
                f"Perubahan data Resi {no_resi} tidak tersimpan. "
                "Data mungkin sudah tidak tersedia atau database menolak pembaruan.",
            )
        self.refresh_session_ui()

    def eksekusi_simpan_baris_ke_db(self, tabel, row):
        if self.row_sedang_diedit == -1:
            return

        no_resi = self._no_resi_dari_baris(tabel, row)
        if not no_resi:
            QMessageBox.warning(
                self, "Peringatan", "Nomor resi pada baris yang diedit tidak tersedia."
            )
            self.refresh_session_ui()
            return

        item_resi = tabel.item(row, self.KOL_RESI)
        is_parent = True
        detail_id = self._detail_id_dari_baris(tabel, row)

        try:
            updates = self._updates_editor_baris(tabel, row, is_parent)
            payload = {
                key: updates[key]
                for key in ("nama_barang", "koli", "berat", "cbm")
                if key in updates
            }
            if not self._konfirmasi_edit_resi_terinvoice(no_resi, updates):
                return

            revision_awal = self._revision_dari_baris(tabel, row)
            berhasil = db_service.update_baris_buku_gudang(
                no_resi,
                self._kode_cabang_aktif(),
                updates,
                payload,
                detail_id=detail_id,
                expected_revision=revision_awal,
            )
            if not berhasil:
                self._tampilkan_gagal_simpan_baris(no_resi, revision_awal)
                return

            self.refresh_session_ui()
            QMessageBox.information(self, "Sukses", f"Data Resi {no_resi} berhasil disimpan!")
        except Exception as error:
            QMessageBox.critical(self, "Error", f"Gagal: {error}")
            self.refresh_session_ui()

    def _resi_terpilih_terlihat(self, tabel):
        return sorted({
            no_resi
            for row in self._ambil_baris_terseleksi_invoice(tabel)
            if not tabel.isRowHidden(row)
            for no_resi in [self._no_resi_dari_baris(tabel, row)]
            if no_resi
        })

    def tandai_selesai_massal(self, tabel):
        resi_list = self._resi_terpilih_terlihat(tabel)
        if not resi_list:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Tidak ada resi valid yang dipilih "
                "(atau resi sedang disembunyikan oleh filter).",
            )
            return

        jawaban = QMessageBox.question(
            self,
            "Konfirmasi",
            f"Tandai {len(resi_list)} resi menjadi SELESAI?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if jawaban != QMessageBox.StandardButton.Yes:
            return

        try:
            berhasil = db_service.tandai_resi_selesai_massal(
                resi_list, self._kode_cabang_aktif()
            )
            if not berhasil:
                QMessageBox.critical(
                    self,
                    "Gagal Memperbarui Status",
                    "Status resi tidak berhasil diperbarui di database.",
                )
                self.refresh_session_ui()
                return

            self.refresh_session_ui()
            QMessageBox.information(
                self, "Sukses", f"{len(resi_list)} resi berhasil ditandai SELESAI."
            )
        except Exception as error:
            QMessageBox.critical(self, "Error", f"Gagal: {error}")

    @db_service.profile_performance("BukuGudang.refresh_session_ui", threshold=0.025)
    def refresh_session_ui(self):
        """Paksa refresh setelah aksi/perubahan sesi, bukan saat navigasi tab."""
        self.row_sedang_diedit = -1
        for tab_widget in self.tabs_list:
            tab_widget._buku_gudang_cache_stale = True
            tab_widget._buku_gudang_loaded_signature = None
            tab_widget._buku_gudang_data_fingerprint = None
            tab_widget._buku_gudang_invalidation_generation = (
                getattr(tab_widget, "_buku_gudang_invalidation_generation", 0) + 1
            )

        active_tab = self.tabs_wilayah.currentWidget()
        if active_tab is not None:
            self.load_data(active_tab)

    def jadwalkan_simpan_lebar_kolom(self, tabel):
        if tabel is None:
            return

        self._tabel_lebar_pending = tabel
        self._timer_simpan_lebar.start()

    def _simpan_lebar_kolom_tertunda(self):
        tabel = self._tabel_lebar_pending
        self._tabel_lebar_pending = None

        if tabel is None:
            return

        try:
            self.simpan_lebar_kolom(tabel)
        except RuntimeError:
            return

    def simpan_lebar_kolom(self, tabel):
        lebar_dasar = []
        for index in range(tabel.columnCount()):
            lebar_asli = int(tabel.columnWidth(index))
            lebar_asli = min(max(BUKU_GUDANG_COLUMN_WIDTH_MIN, lebar_asli), BUKU_GUDANG_COLUMN_WIDTH_MAX)
            lebar_dasar.append(lebar_asli)

            if hasattr(tabel, "_zoom_base_column_widths"):
                tabel._zoom_base_column_widths[index] = lebar_asli

        settings = self._settings_kolom()
        settings.setValue(self.SETTINGS_KEY_LEBAR, lebar_dasar)
        settings.sync()

        self._cache_lebar_kolom_dasar = None

    def _dapatkan_lebar_kolom_dasar(self, jumlah_kolom):
        cache = self._cache_lebar_kolom_dasar
        if cache is not None and cache[0] == jumlah_kolom:
            return list(cache[1])

        saved_widths = self._normalisasi_daftar_lebar(
            self._settings_kolom().value(self.SETTINGS_KEY_LEBAR),
            jumlah_kolom,
        )
        widths = saved_widths or list(self.DEFAULT_LEBAR_KOLOM[:jumlah_kolom])

        while len(widths) < jumlah_kolom:
            widths.append(BUKU_GUDANG_FALLBACK_COLUMN_WIDTH)

        self._cache_lebar_kolom_dasar = (jumlah_kolom, list(widths))
        return widths

    def load_lebar_kolom(self, tabel):
        widths = self._dapatkan_lebar_kolom_dasar(tabel.columnCount())

        header = tabel.horizontalHeader()
        status_signal_sebelumnya = header.blockSignals(True)
        try:
            for index, width in enumerate(widths):
                if index < tabel.columnCount():
                    tabel.setColumnWidth(index, int(width))
        finally:
            header.blockSignals(status_signal_sebelumnya)

        tabel._zoom_base_column_widths = {
            index: int(widths[index])
            for index in range(tabel.columnCount())
        }


class NamaBarangKapitalDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setValidator(UppercaseValidator(editor))
        return editor


class BukuGudangEditDialog(QDialog):
    def __init__(self, parent=None, data=None, on_save=None):
        super().__init__(parent)
        terapkan_style_input_global(self)
        self.setWindowTitle("Edit Data Gudang")
        self.resize(900, 600)
        self.data = data or {}
        self._on_save = on_save
        self._hasil = None

        main = QVBoxLayout(self)

        form = QFormLayout()
        self.pengirim = QLineEdit(str(self.data.get("pengirim") or ""))
        self.kota_asal = QLineEdit(str(self.data.get("kota_asal") or ""))
        self.penerima = QLineEdit(str(self.data.get("penerima") or ""))
        tujuan = str(self.data.get("kota_tujuan") or "").strip()
        self._wilayah_tujuan = ""
        wilayah_list = list(DATA_CLIENT.get("provinsi_tujuan") or [])
        wilayah_list.append(self.data.get("wilayah") or "")
        for wilayah in sorted(set(wilayah_list), key=len, reverse=True):
            wilayah = wilayah.strip()
            if not wilayah or not tujuan.casefold().startswith(wilayah.casefold()):
                continue
            sisa = tujuan[len(wilayah):].lstrip()
            if not sisa or sisa.startswith("-"):
                self._wilayah_tujuan = wilayah.upper()
                tujuan = sisa.removeprefix("-").strip()
                break
        self.kota_tujuan = QLineEdit(tujuan)
        for widget in (self.pengirim, self.kota_asal, self.penerima, self.kota_tujuan):
            paksa_kapital_lineedit(widget)
            widget.setValidator(UppercaseValidator(widget))
        self.total_ongkir = QLineEdit(format_ke_rupiah(self.data.get("total_ongkir") or 0))

        form.addRow("Pengirim", self.pengirim)
        form.addRow("Kota Asal", self.kota_asal)
        form.addRow("Penerima", self.penerima)
        form.addRow("Kota Tujuan", self.kota_tujuan)
        form.addRow("Total Ongkir (Rp)", self.total_ongkir)
        main.addLayout(form)

        main.addWidget(QLabel("Detail Barang"))
        self.table_detail = QTableWidget(0, 4)
        self.table_detail.setItemDelegateForColumn(
            0, NamaBarangKapitalDelegate(self.table_detail)
        )
        self.table_detail.setHorizontalHeaderLabels([
            "Nama Barang", "Koli", "Berat (kg)", "Kubik (m³)"
        ])
        self.table_detail.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        main.addWidget(self.table_detail)
        main.addWidget(QLabel("Gunakan koma untuk desimal, contoh: 1,5."))

        for item in self.data.get("detail_barang", []):
            self.tambah_detail(item)

        row_btn = QHBoxLayout()
        self.btn_tambah = QPushButton("+ Tambah Barang")
        self.btn_hapus = QPushButton("- Hapus Barang")
        self.btn_tambah.clicked.connect(lambda: self.tambah_detail())
        self.btn_hapus.clicked.connect(self.hapus_detail)
        row_btn.addWidget(self.btn_tambah)
        row_btn.addWidget(self.btn_hapus)
        main.addLayout(row_btn)

        self.keterangan = QTextEdit(str(self.data.get("keterangan", "")))
        main.addWidget(QLabel("Keterangan"))
        main.addWidget(self.keterangan)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._simpan)
        buttons.rejected.connect(self.reject)
        main.addWidget(buttons)
        terapkan_style_input_global(self)

    def tambah_detail(self, item=None):
        row = self.table_detail.rowCount()
        self.table_detail.insertRow(row)
        values = item or {}
        data = [
            str(values.get("nama_barang") or "").upper(),
            values.get("koli", ""),
            format_decimal_indonesia(values.get("berat") or 0),
            format_decimal_indonesia(values.get("cbm") or 0),
        ]
        for col, value in enumerate(data):
            self.table_detail.setItem(row, col, QTableWidgetItem(str(value)))
        if item is None:
            self.table_detail.setCurrentCell(row, 0)
            self.table_detail.scrollToItem(
                self.table_detail.item(row, 0),
                QAbstractItemView.ScrollHint.PositionAtBottom,
            )
            self.table_detail.setFocus()
            self.table_detail.editItem(self.table_detail.item(row, 0))

    def hapus_detail(self):
        row = self.table_detail.currentRow()
        if row >= 0:
            self.table_detail.removeRow(row)

    def get_data(self):
        from math import isfinite
        locale = QLocale(QLocale.Language.Indonesian, QLocale.Country.Indonesia)

        def angka(teks, label, bulat=False):
            teks = teks.strip()
            if teks in ("", "-"):
                return 0
            value, valid = locale.toLongLong(teks) if bulat else locale.toDouble(teks)
            if not valid or not isfinite(value) or value < 0:
                raise ValueError(f"{label}: masukkan angka nonnegatif yang valid.")
            return value

        detail = []
        for row in range(self.table_detail.rowCount()):
            values = [
                self.table_detail.item(row, col).text().strip() if self.table_detail.item(row, col) else ""
                for col in range(4)
            ]
            koli = angka(values[1], f"Koli baris {row + 1}", bulat=True)
            berat = angka(values[2], f"Berat baris {row + 1}")
            cbm = angka(values[3], f"Kubik baris {row + 1}")
            if values[0] or koli or berat or cbm:
                detail.append({
                    "nama_barang": values[0].upper(),
                    "koli": str(koli) if koli else "",
                    "berat": berat,
                    "cbm": cbm,
                })

        tujuan = self.kota_tujuan.text().strip().upper()
        if self._wilayah_tujuan:
            tujuan = f"{self._wilayah_tujuan} - {tujuan}" if tujuan else self._wilayah_tujuan

        return {
            "pengirim": self.pengirim.text().strip().upper(),
            "kota_asal": self.kota_asal.text().strip().upper(),
            "penerima": self.penerima.text().strip().upper(),
            "kota_tujuan": tujuan,
            "total_ongkir": angka(self.total_ongkir.text(), "Total Ongkir", bulat=True),
            "detail_barang": detail,
            "keterangan": self.keterangan.toPlainText().strip().upper(),
        }

    def _simpan(self):
        self.table_detail.setFocus()
        try:
            hasil = self.get_data()
            if self._on_save is not None and not self._on_save(hasil):
                return
        except (ValueError, TypeError) as error:
            QMessageBox.warning(self, "Periksa Isian", str(error))
            return
        except Exception as error:
            QMessageBox.critical(self, "Gagal Menyimpan", str(error))
            return
        self._hasil = hasil
        self.accept()


def open_buku_gudang_edit_popup(parent=None, data=None, on_save=None):
    dialog = BukuGudangEditDialog(parent, data, on_save=on_save)
    if dialog.exec():
        return dialog._hasil
    return None
