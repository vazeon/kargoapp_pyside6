# utils/table_helper.py
from typing import Any, Iterable, Optional, Sequence

from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QRect,
    QSize,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QStyle,
    QStyleOptionHeader,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
)


def pasang_style_tabel(tabel, stylesheet: str) -> str:
    """Pasang QSS tabel dan sinkronkan ke frozen overlay bila tersedia.

    Fungsi ini hanya menerapkan stylesheet; aturan visual tetap didefinisikan
    oleh themes/components/table.py atau theme module pemiliknya.
    """
    if tabel is None:
        return ""

    qss = str(stylesheet or "")
    tabel.setStyleSheet(qss)

    frozen = getattr(tabel, "frozen_table", None)
    if frozen is not None and frozen.styleSheet() != qss:
        frozen.setStyleSheet(qss)

    return qss


def terapkan_tema_tabel(
    tabel,
    is_dark: bool,
    *,
    metrics=None,
    font_size_pt: Optional[float] = None,
    ui_colors=None,
    extra_stylesheet: str = "",
    cell_editors: bool = False,
) -> str:
    """Bangun dan terapkan tema tabel dari komponen tema bersama.

    Helper ini menjadi lapisan penerapan tema. Nilai font_size_pt dapat
    diberikan oleh pemanggil yang memiliki konteks zoom; helper ini tidak
    mengimpor atau menjalankan utils.zoom.
    """
    if tabel is None:
        return ""

    from dataclasses import replace
    from themes.components.table import TableMetrics, get_table_styles

    table_metrics = metrics or TableMetrics()
    if font_size_pt is not None:
        table_metrics = replace(
            table_metrics,
            font_size_pt=max(1.0, float(font_size_pt)),
        )

    stylesheet = get_table_styles(
        is_dark,
        metrics=table_metrics,
        ui_colors=ui_colors,
        cell_editors=cell_editors,
    )
    extra = str(extra_stylesheet or "").strip()
    if extra:
        stylesheet = f"{stylesheet.rstrip()}\n{extra}"

    return pasang_style_tabel(tabel, stylesheet)


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



class WrappedHeaderView(QHeaderView):
    """Header tabel yang membungkus teks pada batas kata saat kolom menyempit."""

    wrapHeightChanged = Signal(int)

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None, *, manage_height=True):
        super().__init__(orientation, parent)
        self._manage_wrap_height = bool(manage_height)
        self._bound_header_model = None
        self._last_wrap_height = None
        self._wrap_timer = QTimer(self)
        self._wrap_timer.setSingleShot(True)
        self._wrap_timer.timeout.connect(self._perbarui_geometri_wrap)
        self.sectionResized.connect(self._jadwalkan_perbarui_wrap)
        self.sectionCountChanged.connect(self._jadwalkan_perbarui_wrap)
        self.geometriesChanged.connect(self._jadwalkan_perbarui_wrap)

    def set_height_managed(self, enabled):
        self._manage_wrap_height = bool(enabled)
        self._jadwalkan_perbarui_wrap()

    def bind_model(self, model):
        if model is self._bound_header_model:
            return
        old_model = self._bound_header_model
        if old_model is not None:
            for signal_name in ("headerDataChanged", "modelReset", "columnsInserted", "columnsRemoved"):
                signal = getattr(old_model, signal_name, None)
                if signal is not None:
                    try:
                        signal.disconnect(self._jadwalkan_perbarui_wrap)
                    except (RuntimeError, TypeError):
                        pass
        self._bound_header_model = model
        if model is not None:
            for signal_name in ("headerDataChanged", "modelReset", "columnsInserted", "columnsRemoved"):
                signal = getattr(model, signal_name, None)
                if signal is not None:
                    signal.connect(self._jadwalkan_perbarui_wrap)
        self._jadwalkan_perbarui_wrap()

    def _jadwalkan_perbarui_wrap(self, *_args):
        if not self._manage_wrap_height:
            self.viewport().update()
            return
        if not self._wrap_timer.isActive():
            self._wrap_timer.start(0)

    def _teks_dan_font_section(self, logical_index):
        model = self.model()
        if model is None:
            return "", self.font()
        value = model.headerData(
            logical_index,
            self.orientation(),
            Qt.ItemDataRole.DisplayRole,
        )
        text = "" if value is None else str(value)
        section_font = model.headerData(
            logical_index,
            self.orientation(),
            Qt.ItemDataRole.FontRole,
        )
        font = section_font if isinstance(section_font, QFont) else self.font()
        return text, font

    def _label_rect(self, logical_index, width, height):
        option = QStyleOptionHeader()
        self.initStyleOption(option)
        self.initStyleOptionForIndex(option, logical_index)
        option.rect = QRect(0, 0, max(1, int(width)), max(1, int(height)))
        rect = self.style().subElementRect(
            QStyle.SubElement.SE_HeaderLabel,
            option,
            self,
        )
        if not rect.isValid() or rect.width() <= 0:
            rect = option.rect.adjusted(3, 2, -3, -2)
        return rect

    def _tinggi_teks_section(self, logical_index, base_height):
        text, font = self._teks_dan_font_section(logical_index)
        if not text:
            return 0
        width = self.sectionSize(logical_index)
        if width <= 0:
            return 0
        label_rect = self._label_rect(logical_index, width, base_height)
        available_width = max(1, label_rect.width())
        metrics = QFontMetrics(font)
        flags = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter)
        bounds = metrics.boundingRect(
            QRect(0, 0, available_width, max(1000, base_height * 8)),
            flags,
            text,
        )
        return max(metrics.height(), bounds.height())

    def sizeHint(self):
        base = super().sizeHint()
        if self.orientation() != Qt.Orientation.Horizontal or self.count() <= 0:
            return base

        max_extra = 0
        base_height = max(1, base.height())
        for logical_index in range(self.count()):
            if self.isSectionHidden(logical_index):
                continue
            text_height = self._tinggi_teks_section(logical_index, base_height)
            if text_height:
                metrics = QFontMetrics(self._teks_dan_font_section(logical_index)[1])
                max_extra = max(max_extra, text_height - metrics.height())

        return base if max_extra <= 0 else base + QSize(0, max_extra)

    def _bungkus_teks_section(self, text, width, font):
        """Sisipkan line break pada spasi; kata tidak dipotong di tengah."""
        metrics = QFontMetrics(font)
        max_width = max(1, int(width))
        lines = []
        for paragraph in str(text or "").split("\n"):
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = words[0]
            for word in words[1:]:
                candidate = f"{current} {word}"
                if metrics.horizontalAdvance(candidate) <= max_width:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        return "\n".join(lines)

    def paintSection(self, painter, rect, logicalIndex):
        if self.orientation() != Qt.Orientation.Horizontal or not rect.isValid():
            return super().paintSection(painter, rect, logicalIndex)

        option = QStyleOptionHeader()
        self.initStyleOption(option)
        self.initStyleOptionForIndex(option, logicalIndex)
        option.rect = rect

        text = str(option.text or "")
        if text:
            label_rect = self.style().subElementRect(
                QStyle.SubElement.SE_HeaderLabel,
                option,
                self,
            )
            if not label_rect.isValid() or label_rect.width() <= 0:
                label_rect = rect.adjusted(3, 2, -3, -2)
            _section_text, section_font = self._teks_dan_font_section(logicalIndex)
            option.text = self._bungkus_teks_section(
                text,
                label_rect.width(),
                section_font,
            )

        # Gunakan paint native QStyle agar warna, font QSS, state, border,
        # ikon, dan indikator sorting tetap mengikuti tema aplikasi.
        self.style().drawControl(
            QStyle.ControlElement.CE_Header,
            option,
            painter,
            self,
        )

    def _perbarui_geometri_wrap(self):
        target_height = self.sizeHint().height()
        changed = target_height != self._last_wrap_height
        self._last_wrap_height = target_height

        if self._manage_wrap_height and changed:
            self.updateGeometry()
            parent = self.parentWidget()
            if parent is not None:
                # QTableView mengatur viewport berdasarkan sizeHint header.
                updater = getattr(parent, "updateGeometries", None)
                if callable(updater):
                    try:
                        updater()
                    except (AttributeError, RuntimeError, TypeError):
                        pass
                parent.updateGeometry()
                parent.update()
            self.wrapHeightChanged.emit(target_height)
        self.viewport().update()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
        ):
            self._jadwalkan_perbarui_wrap()


def _ambil_konfigurasi_header(header):
    """Ambil state header sebelum widget header native diganti."""
    return {
        "default_alignment": header.defaultAlignment(),
        "minimum_section_size": header.minimumSectionSize(),
        "maximum_section_size": header.maximumSectionSize(),
        "default_section_size": header.defaultSectionSize(),
        "stretch_last_section": header.stretchLastSection(),
        "highlight_sections": header.highlightSections(),
        "sections_clickable": header.sectionsClickable(),
        "sections_movable": header.sectionsMovable(),
        "first_section_movable": header.isFirstSectionMovable(),
        "cascading_resizes": header.cascadingSectionResizes(),
        "sort_shown": header.isSortIndicatorShown(),
        "sort_section": header.sortIndicatorSection() if header.isSortIndicatorShown() else -1,
        "sort_order": header.sortIndicatorOrder() if header.isSortIndicatorShown() else Qt.SortOrder.AscendingOrder,
        "sections": tuple(
            (
                header.sectionResizeMode(index),
                header.sectionSize(index),
                header.isSectionHidden(index),
            )
            for index in range(header.count())
        ),
        "visual_order": tuple(
            header.logicalIndex(visual_index)
            for visual_index in range(header.count())
        ),
    }


def _salin_konfigurasi_header(konfigurasi, header):
    """Pulihkan perilaku header agar pemasangan wrap tidak mengubah tabel."""
    header.setDefaultAlignment(konfigurasi["default_alignment"])
    header.setMinimumSectionSize(konfigurasi["minimum_section_size"])
    header.setMaximumSectionSize(konfigurasi["maximum_section_size"])
    header.setDefaultSectionSize(konfigurasi["default_section_size"])
    header.setStretchLastSection(konfigurasi["stretch_last_section"])
    header.setHighlightSections(konfigurasi["highlight_sections"])
    header.setSectionsClickable(konfigurasi["sections_clickable"])
    header.setSectionsMovable(konfigurasi["sections_movable"])
    header.setFirstSectionMovable(konfigurasi["first_section_movable"])
    header.setCascadingSectionResizes(konfigurasi["cascading_resizes"])
    header.setSortIndicatorShown(konfigurasi["sort_shown"])

    jumlah = min(len(konfigurasi["sections"]), header.count())
    for logical_index, section_state in enumerate(konfigurasi["sections"][:jumlah]):
        resize_mode, width, hidden = section_state
        header.setSectionResizeMode(logical_index, resize_mode)
        header.resizeSection(logical_index, width)
        header.setSectionHidden(logical_index, hidden)

    if konfigurasi["sort_shown"]:
        sort_section = konfigurasi["sort_section"]
        if 0 <= sort_section < header.count():
            header.setSortIndicator(sort_section, konfigurasi["sort_order"])

    visual_order = konfigurasi["visual_order"][:jumlah]
    for target_visual, logical_index in enumerate(visual_order):
        if logical_index < 0 or logical_index >= header.count():
            continue
        current_visual = header.visualIndex(logical_index)
        if current_visual != target_visual:
            header.moveSection(current_visual, target_visual)


def _pasang_header_wrap_satu_view(tabel, *, manage_height=True):
    if tabel is None or not hasattr(tabel, "horizontalHeader"):
        return None

    header_lama = tabel.horizontalHeader()
    if isinstance(header_lama, WrappedHeaderView):
        header_lama.set_height_managed(manage_height)
        header_lama.bind_model(tabel.model())
        return header_lama

    konfigurasi_header = _ambil_konfigurasi_header(header_lama)
    header_baru = WrappedHeaderView(
        Qt.Orientation.Horizontal,
        tabel,
        manage_height=manage_height,
    )
    tabel.setHorizontalHeader(header_baru)
    _salin_konfigurasi_header(konfigurasi_header, header_baru)
    header_baru.bind_model(tabel.model())
    header_baru._jadwalkan_perbarui_wrap()
    return header_baru


def pasang_header_wrap(tabel, *, manage_height=True):
    """Pasang header word-wrap; overlay frozen mengikuti tinggi header utama."""
    header = _pasang_header_wrap_satu_view(
        tabel,
        manage_height=manage_height,
    )
    frozen = getattr(tabel, "frozen_table", None)
    if frozen is not None and frozen is not tabel:
        _pasang_header_wrap_satu_view(frozen, manage_height=False)
    return header

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

    # 3. Header kolom dengan pembungkusan teks otomatis.
    pasang_header_wrap(tabel)
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
        pasang_header_wrap(self)
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
    "WrappedHeaderView",
    "pasang_header_wrap",
    "ModelTableModel",
    "ModelTableView",
    "ModelCellProxy",
]
