# utils/zoom.py
"""Helper zoom UI global untuk aplikasi PySide6.

Menyimpan level zoom, menskalakan font/geometri/icon/layout/item-view, dan
menjaga nilai dasar agar perubahan zoom tidak menumpuk.
"""

from dataclasses import dataclass
from typing import Any, Optional

from PySide6.QtCore import QSettings, QSignalBlocker, QSize, QTimer
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QComboBox, QDateEdit,
    QDateTimeEdit, QDoubleSpinBox, QGridLayout, QGroupBox, QHeaderView, QLayout,
    QLineEdit, QListView, QListWidget, QMenu, QMenuBar, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QTableView, QTableWidget, QTabWidget,
    QTextEdit, QTimeEdit, QToolBar, QToolButton, QTreeView, QTreeWidget, QWidget,
)

from utils import typography

ORGANIZATION_NAME = "AplikasiEkspedisi"
APPLICATION_NAME = "PengaturanUI"
MIN_ZOOM_LEVEL, MAX_ZOOM_LEVEL = -4, 10
DEFAULT_ICON_SIZE = 18
DEFAULT_TABLE_ROW_HEIGHT = 32
DEFAULT_TABLE_HEADER_HEIGHT = 36

QT_GEOMETRY_MAX = 16_777_215
MAX_COLUMN_WIDTH = 100_000
MAX_FONT_SIZE = 96
MAX_ICON_BASE_SIZE = 256
MAX_ICON_RENDER_SIZE = 512

_INPUT_WIDGETS = (QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit)
_ZOOM_INPUT_WIDGETS = _INPUT_WIDGETS + (QTextEdit, QPlainTextEdit, QComboBox)
_SINGLE_LINE_WIDGETS = (QAbstractButton, QComboBox, QProgressBar) + _INPUT_WIDGETS
_ITEM_VIEW_WIDGETS = (QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView)

settings_ui = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)


def _int_aman(value: Any, default: int = 0, minimum: Optional[int] = None,
              maximum: Optional[int] = None) -> int:
    """Konversi int defensif sebelum nilai diteruskan ke Qt/C++."""
    try:
        hasil = int(value)
    except (TypeError, ValueError, OverflowError):
        hasil = int(default)
    if minimum is not None:
        hasil = max(int(minimum), hasil)
    if maximum is not None:
        hasil = min(int(maximum), hasil)
    return hasil


def _float_aman(value: Any, default: float = 0.0, minimum: Optional[float] = None,
                maximum: Optional[float] = None) -> float:
    """Konversi float defensif untuk ukuran font dan metrik UI."""
    try:
        hasil = float(value)
    except (TypeError, ValueError, OverflowError):
        hasil = float(default)
    if minimum is not None:
        hasil = max(float(minimum), hasil)
    if maximum is not None:
        hasil = min(float(maximum), hasil)
    return hasil


def batasi_ukuran_font(value: Any, default: float = 9.0) -> float:
    minimum = _float_aman(getattr(typography, "MIN_FONT_SIZE_PT", 6.0), 6.0, 1.0, 32.0)
    return _float_aman(value, default, minimum, float(MAX_FONT_SIZE))


def _batasi_zoom(z: Any) -> int:
    return _int_aman(z, 0, MIN_ZOOM_LEVEL, MAX_ZOOM_LEVEL)


def _faktor_zoom(z: Any) -> float:
    return max(0.68, min(1.0 + (_batasi_zoom(z) * 0.08), 1.80))


def _skalakan(nilai: Any, z: Any, minimum: int = 0,
              maximum: int = QT_GEOMETRY_MAX) -> int:
    angka = _int_aman(nilai, minimum, minimum, maximum)
    try:
        hasil = round(angka * _faktor_zoom(z))
    except (TypeError, ValueError, OverflowError):
        hasil = minimum
    return _int_aman(hasil, minimum, minimum, maximum)


@dataclass(frozen=True)
class ZoomMetrics:
    level: int
    factor: float
    font_base_pt: float
    row_height: int
    header_height: int
    icon_size: int
    item_padding: int
    header_padding_v: int


def dapatkan_metrik_zoom(z: Any) -> ZoomMetrics:
    level = _batasi_zoom(z)
    sizes = typography.get_global_font_sizes_pt(level)
    return ZoomMetrics(
        level=level,
        factor=_faktor_zoom(level),
        font_base_pt=batasi_ukuran_font(sizes.get("sz_base", 9.0), 9.0),
        row_height=_skalakan(DEFAULT_TABLE_ROW_HEIGHT, level, 24, 10_000),
        header_height=_skalakan(DEFAULT_TABLE_HEADER_HEIGHT, level, 26, 10_000),
        icon_size=_skalakan(DEFAULT_ICON_SIZE, level, 12, MAX_ICON_RENDER_SIZE),
        item_padding=max(2, 4 + level),
        header_padding_v=max(4, 6 + level),
    )


def _ambil_atau_simpan_dasar(objek: Any, nama: str, nilai: Any) -> Any:
    atribut = f"_zoom_base_{nama}"
    if not hasattr(objek, atribut):
        setattr(objek, atribut, nilai)
    return getattr(objek, atribut)


def _qsize_icon_aman(objek: Any, nama_cache: str, ukuran_saat_ini: Any,
                     default_size: int = DEFAULT_ICON_SIZE) -> QSize:
    """Ambil ukuran dasar ikon dan normalisasi cache yang abnormal."""
    atribut = f"_zoom_base_{nama_cache}"
    kandidat = getattr(objek, atribut, ukuran_saat_ini)
    try:
        width, height = kandidat.width(), kandidat.height()
    except (AttributeError, TypeError, RuntimeError):
        width = height = default_size

    ukuran = QSize(
        _int_aman(width, default_size, 1, MAX_ICON_BASE_SIZE),
        _int_aman(height, default_size, 1, MAX_ICON_BASE_SIZE),
    )
    setattr(objek, atribut, ukuran)
    return ukuran


def _ukuran_icon_terzoom(ukuran_dasar: QSize, faktor: float,
                         minimum: int = 12) -> QSize:
    try:
        width = round(ukuran_dasar.width() * faktor)
        height = round(ukuran_dasar.height() * faktor)
    except (AttributeError, TypeError, ValueError, OverflowError):
        width = height = DEFAULT_ICON_SIZE
    return QSize(
        _int_aman(width, DEFAULT_ICON_SIZE, minimum, MAX_ICON_RENDER_SIZE),
        _int_aman(height, DEFAULT_ICON_SIZE, minimum, MAX_ICON_RENDER_SIZE),
    )


def _master_font() -> str:
    app = QApplication.instance()
    if app is not None:
        family = str(app.font().family() or "").strip()
        if family:
            return family
    getter = getattr(typography, "get_master_font", None)
    if callable(getter):
        family = str(getter() or "").strip()
        if family:
            return family
    return str(getattr(typography, "DEFAULT_FONT", "Roboto") or "Roboto")


def _font_family_qss() -> str:
    return _master_font().replace("\\", "\\\\").replace("'", "\\'")


def _ukuran_font_minimum() -> int:
    return _int_aman(getattr(typography, "MIN_FONT_SIZE", 8), 8, 1, 32)


def dapatkan_zoom_level(class_name: str) -> int:
    nama = str(class_name or "").strip()
    return _batasi_zoom(settings_ui.value(f"zoom_{nama}", 0))


def simpan_zoom_level(class_name: str, zoom_level: int) -> int:
    nama = str(class_name or "").strip()
    zoom = _batasi_zoom(zoom_level)
    settings_ui.setValue(f"zoom_{nama}", zoom)
    settings_ui.sync()
    return zoom


def generate_font_zoom_tabel_qss(z: int = 0) -> str:
    metrics = dapatkan_metrik_zoom(z)
    family, size_pt = _font_family_qss(), f"{metrics.font_base_pt:g}"
    return f"""
QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {{
    font-family: '{family}'; font-size: {size_pt}pt;
}}
QTableWidget::item, QTableView::item, QTreeWidget::item, QTreeView::item,
QListWidget::item, QListView::item {{
    font-family: '{family}'; font-size: {size_pt}pt;
}}
QHeaderView, QHeaderView::section {{
    font-family: '{family}'; font-size: {size_pt}pt;
}}
QHeaderView::section {{ font-weight: bold; }}
"""


def generate_style_tabel(is_dark: bool, z: int = 0) -> str:
    zoom = _batasi_zoom(z)
    item_pad = max(2, 4 + zoom)
    header_v = max(4, 6 + zoom)
    header_h = max(6, 8 + (zoom * 2))
    indicator = _skalakan(16, zoom, minimum=12)

    if is_dark:
        bg, alt_bg, text, grid = "#1a1d24", "#20242b", "#f8fafc", "#334155"
        header_bg, header_text, selected_bg = "#1e293b", "#ffffff", "#3b82f6"
    else:
        bg, alt_bg, text, grid = "#ffffff", "#f1f5f9", "#0f172a", "#e2e8f0"
        header_bg, header_text, selected_bg = "#243752", "#ffffff", "#2563eb"

    visual = f"""
QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {{
    background-color: {bg}; alternate-background-color: {alt_bg}; color: {text};
    gridline-color: {grid}; border: 1px solid {grid};
}}
QTableWidget::item, QTableView::item, QTreeWidget::item, QTreeView::item,
QListWidget::item, QListView::item {{ padding: {item_pad}px; }}
QHeaderView::section {{
    background-color: {header_bg}; color: {header_text}; border: 1px solid {grid};
    padding: {header_v}px {header_h}px;
}}
QTableWidget::item:selected, QTableView::item:selected,
QTreeWidget::item:selected, QTreeView::item:selected,
QListWidget::item:selected, QListView::item:selected {{
    background-color: {selected_bg}; color: #ffffff;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: {indicator}px; height: {indicator}px;
}}
"""
    return f"{visual}\n{generate_font_zoom_tabel_qss(zoom)}"


def _pasang_stylesheet_zoom(widget: QWidget, qss_zoom: str) -> None:
    if not hasattr(widget, "_zoom_base_stylesheet"):
        widget._zoom_base_stylesheet = widget.styleSheet()
    dasar = getattr(widget, "_zoom_base_stylesheet", "")
    widget.setStyleSheet(f"{dasar}\n/* ZOOM OTOMATIS */\n{qss_zoom}" if dasar else qss_zoom)


def _terapkan_font(widget: QWidget, z: int, key_ukuran: str) -> None:
    sizes = typography.get_global_font_sizes_pt(z)
    key_ukuran = str(widget.property("zoom_font_key") or key_ukuran)
    ukuran = batasi_ukuran_font(sizes.get(key_ukuran, 9.0), 9.0)

    font = widget.font()
    font.setFamily(_master_font())
    font.setPointSizeF(ukuran)
    widget.setFont(font)

    if isinstance(widget, QComboBox):
        view = widget.view()
        if view is not None:
            view.setFont(font)


def _terapkan_icon(widget: QWidget, z: int) -> None:
    faktor = _faktor_zoom(z)
    if isinstance(widget, (QAbstractButton, QComboBox)):
        dasar = _qsize_icon_aman(widget, "icon_size", widget.iconSize(), DEFAULT_ICON_SIZE)
        widget.setIconSize(_ukuran_icon_terzoom(dasar, faktor, 12))
    elif isinstance(widget, QToolBar):
        dasar = _qsize_icon_aman(widget, "toolbar_icon_size", widget.iconSize(), 24)
        widget.setIconSize(_ukuran_icon_terzoom(dasar, faktor, 14))
    elif isinstance(widget, QTabWidget):
        bar = widget.tabBar()
        dasar = _qsize_icon_aman(bar, "icon_size", bar.iconSize(), DEFAULT_ICON_SIZE)
        bar.setIconSize(_ukuran_icon_terzoom(dasar, faktor, 12))


def _terapkan_tinggi_widget(widget: QWidget, z: int) -> None:
    if not isinstance(widget, _SINGLE_LINE_WIDGETS):
        return

    min_lama, max_lama = widget.minimumHeight(), widget.maximumHeight()
    if isinstance(widget, QComboBox):
        tinggi_default = 30
    elif isinstance(widget, _INPUT_WIDGETS):
        tinggi_default = 42
    else:
        tinggi_default = max(min_lama, widget.sizeHint().height(), 24)

    dasar = _ambil_atau_simpan_dasar(widget, "minimum_height", tinggi_default)
    fixed = _ambil_atau_simpan_dasar(
        widget, "fixed_height", max_lama < QT_GEOMETRY_MAX and max_lama == min_lama
    )
    tinggi = _skalakan(dasar, z, minimum=20)
    widget.setMinimumHeight(tinggi)
    if fixed:
        widget.setMaximumHeight(tinggi)


def _terapkan_padding(widget: QWidget, z: int) -> None:
    zoom = _batasi_zoom(z)
    kecil = max(2, 4 + zoom)
    vertikal = max(3, 5 + zoom)
    horizontal = max(5, 8 + (zoom * 2))
    radius = max(2, 4 + (zoom // 2))

    if isinstance(widget, (QPushButton, QToolButton)):
        qss = f"QPushButton, QToolButton {{ padding:{vertikal}px {horizontal}px; border-radius:{radius}px; }}"
    elif isinstance(widget, _INPUT_WIDGETS):
        qss = ("QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit "
               f"{{ padding:{kecil}px {horizontal}px; }}")
    elif isinstance(widget, (QTextEdit, QPlainTextEdit)):
        qss = f"QTextEdit, QPlainTextEdit {{ padding:{kecil}px; }}"
    elif isinstance(widget, QTabWidget):
        qss = f"QTabBar::tab {{ padding:{vertikal}px {horizontal}px; }}"
    elif isinstance(widget, QMenuBar):
        qss = f"QMenuBar::item {{ padding:{vertikal}px {horizontal}px; }}"
    elif isinstance(widget, QMenu):
        qss = f"QMenu::item {{ padding:{vertikal}px {horizontal * 2}px; }}"
    elif isinstance(widget, QGroupBox):
        margin_top = max(8, 12 + (zoom * 2))
        qss = (f"QGroupBox {{ margin-top:{margin_top}px; }} "
               f"QGroupBox::title {{ padding:0 {kecil}px; }}")
    else:
        return
    _pasang_stylesheet_zoom(widget, qss)


def terapkan_zoom_widget_standar(widget: QWidget, z: int,
                                  key_ukuran: str = "sz_base") -> None:
    if widget is None:
        return
    zoom = _batasi_zoom(z)
    _terapkan_font(widget, zoom, key_ukuran)
    _terapkan_icon(widget, zoom)
    _terapkan_tinggi_widget(widget, zoom)
    _terapkan_padding(widget, zoom)

    lebar_dasar = widget.property("base_width")
    if lebar_dasar is not None:
        lebar_dasar = _int_aman(lebar_dasar, 140, 100, MAX_COLUMN_WIDTH)
        widget.setFixedWidth(_skalakan(lebar_dasar, zoom, 140, MAX_COLUMN_WIDTH))


def _skalakan_kolom(view: Any, header: QHeaderView, z: int) -> None:
    """Implementasi bersama untuk kolom QTableView/QTreeView."""
    model = view.model()
    if model is None:
        return

    cache = getattr(view, "_zoom_base_column_widths", None)
    if cache is None:
        cache = view._zoom_base_column_widths = {}

    for kolom in range(model.columnCount()):
        cache.setdefault(kolom, view.columnWidth(kolom))
        dasar = _int_aman(cache[kolom], max(20, view.columnWidth(kolom)), 20, MAX_COLUMN_WIDTH)
        cache[kolom] = dasar
        if header.sectionResizeMode(kolom) != QHeaderView.ResizeMode.Stretch:
            view.setColumnWidth(kolom, _skalakan(dasar, z, 20, MAX_COLUMN_WIDTH))


def _skalakan_kolom_tableview(table: QTableView, z: int) -> None:
    if table.property("zoom_scale_columns") is False:
        return
    _skalakan_kolom(table, table.horizontalHeader(), z)


def skalakan_kolom_tableview(table: QTableView, z: int) -> None:
    _skalakan_kolom_tableview(table, z)


def _panggil_metode_jika_tersedia(objek: Any, *nama_metode: str) -> bool:
    for nama in nama_metode:
        metode = getattr(objek, nama, None)
        if callable(metode):
            metode()
            return True
    return False


def _sinkronkan_frozen_sekarang(table: QTableView) -> None:
    try:
        frozen = getattr(table, "frozen_table", None)
        _panggil_metode_jika_tersedia(
            table, "updateFrozenTableGeometry", "update_frozen_table_geometry",
            "_update_frozen_table_geometry", "perbarui_geometri_frozen",
        )
        table.doItemsLayout()
        table.updateGeometries()
        if frozen is not None:
            frozen.doItemsLayout()
            frozen.updateGeometries()
            frozen.verticalScrollBar().setValue(table.verticalScrollBar().value())
            frozen.raise_()
        table.viewport().update()
        table.update()
        if frozen is not None:
            frozen.viewport().update()
            frozen.update()
    except RuntimeError:
        return


def sinkronkan_frozen_table(table: QTableView, *, tertunda: bool = True) -> None:
    if table is None:
        return
    _sinkronkan_frozen_sekarang(table)
    if tertunda:
        QTimer.singleShot(0, lambda table=table: _sinkronkan_frozen_sekarang(table))


def _skalakan_kolom_treeview(tree: QTreeView, z: int) -> None:
    if tree.model() is None:
        return
    _skalakan_kolom(tree, tree.header(), z)
    dasar = _ambil_atau_simpan_dasar(tree, "indentation", max(10, tree.indentation()))
    tree.setIndentation(_skalakan(dasar, z, minimum=8))


def skalakan_kolom_treeview(tree: QTreeView, z: int) -> None:
    _skalakan_kolom_treeview(tree, z)


def _tinggi_view(font_height: Any, dasar: int, padding: int, minimum: int) -> int:
    return _int_aman(
        max(dasar, max(1, int(font_height)) + (padding * 2) + 8),
        dasar, minimum, 10_000,
    )


def _header_font(header: QHeaderView, metrics: ZoomMetrics):
    font = header.font()
    font.setFamily(_master_font())
    font.setPointSizeF(metrics.font_base_pt)
    font.setBold(True)
    return font


def terapkan_zoom_tabel(table: QAbstractItemView, is_dark: bool, z: int = 0) -> None:
    if table is None:
        return

    metrics = dapatkan_metrik_zoom(z)
    frozen = getattr(table, "frozen_table", None)
    table.setUpdatesEnabled(False)
    if frozen is not None:
        frozen.setUpdatesEnabled(False)

    try:
        table.setStyleSheet(generate_style_tabel(is_dark, metrics.level))
        font = table.font()
        font.setFamily(_master_font())
        font.setPointSizeF(metrics.font_base_pt)
        table.setFont(font)
        table.setIconSize(QSize(metrics.icon_size, metrics.icon_size))

        if isinstance(table, QTableView):
            h_header, v_header = table.horizontalHeader(), table.verticalHeader()
            header_font = _header_font(h_header, metrics)
            h_header.setFont(header_font)
            v_header.setFont(header_font)

            row_height = _tinggi_view(
                table.fontMetrics().height(), metrics.row_height, metrics.item_padding, 24
            )
            header_height = _tinggi_view(
                h_header.fontMetrics().height(), metrics.header_height,
                metrics.header_padding_v, 26,
            )
            if h_header.maximumHeight() < header_height:
                h_header.setMaximumHeight(QT_GEOMETRY_MAX)
            h_header.setMinimumHeight(header_height)
            v_header.setMinimumSectionSize(row_height)
            v_header.setDefaultSectionSize(row_height)
            table._zoom_current_row_height = row_height
            table._zoom_current_header_height = header_height

            blocker = QSignalBlocker(h_header)
            try:
                skalakan_kolom_tableview(table, metrics.level)
            finally:
                del blocker

            model = table.model()
            if model is not None:
                for row in range(model.rowCount()):
                    table.setRowHeight(row, row_height)

            if frozen is not None:
                frozen.setFont(font)
                frozen.horizontalHeader().setFont(header_font)
                frozen.verticalHeader().setFont(header_font)
                frozen.verticalHeader().setMinimumSectionSize(row_height)
                frozen.verticalHeader().setDefaultSectionSize(row_height)
                if model is not None:
                    for row in range(model.rowCount()):
                        frozen.setRowHeight(row, row_height)

        elif isinstance(table, QTreeView):
            header = table.header()
            header.setFont(_header_font(header, metrics))
            header.setMinimumHeight(_tinggi_view(
                header.fontMetrics().height(), metrics.header_height,
                metrics.header_padding_v, 26,
            ))
            skalakan_kolom_treeview(table, metrics.level)

        elif isinstance(table, QListView):
            grid = table.gridSize()
            if grid.isValid():
                dasar = _ambil_atau_simpan_dasar(table, "grid_size", grid)
                table.setGridSize(QSize(
                    _skalakan(dasar.width(), metrics.level, minimum=20),
                    _skalakan(dasar.height(), metrics.level, minimum=20),
                ))
    finally:
        if frozen is not None:
            frozen.setUpdatesEnabled(True)
        table.setUpdatesEnabled(True)
        if isinstance(table, QTableView):
            sinkronkan_frozen_table(table, tertunda=True)


def _terapkan_zoom_layout(layout: Optional[QLayout], z: int) -> None:
    if layout is None:
        return

    margins = layout.contentsMargins()
    dasar_margin = _ambil_atau_simpan_dasar(
        layout, "layout_margins",
        (margins.left(), margins.top(), margins.right(), margins.bottom()),
    )
    layout.setContentsMargins(*[_skalakan(v, z, minimum=0) for v in dasar_margin])

    spacing = layout.spacing()
    dasar_spacing = _ambil_atau_simpan_dasar(layout, "layout_spacing", spacing)
    if dasar_spacing >= 0:
        layout.setSpacing(_skalakan(dasar_spacing, z, minimum=0))

    if isinstance(layout, QGridLayout):
        h_spacing = _ambil_atau_simpan_dasar(layout, "horizontal_spacing", layout.horizontalSpacing())
        v_spacing = _ambil_atau_simpan_dasar(layout, "vertical_spacing", layout.verticalSpacing())
        if h_spacing >= 0:
            layout.setHorizontalSpacing(_skalakan(h_spacing, z, minimum=0))
        if v_spacing >= 0:
            layout.setVerticalSpacing(_skalakan(v_spacing, z, minimum=0))

    for index in range(layout.count()):
        child = layout.itemAt(index).layout()
        if child is not None:
            _terapkan_zoom_layout(child, z)


def terapkan_zoom_semua_elemen(container_widget: QWidget, z: int,
                                is_dark: bool = False) -> None:
    if container_widget is None:
        return

    zoom = _batasi_zoom(z)
    _terapkan_zoom_layout(container_widget.layout(), zoom)
    semua_widget = [container_widget, *container_widget.findChildren(QWidget)]

    for widget in semua_widget:
        if hasattr(widget, "_zoom_base_stylesheet"):
            try:
                widget.setStyleSheet(widget._zoom_base_stylesheet)
            except Exception:
                pass

        if isinstance(widget, _ITEM_VIEW_WIDGETS):
            if hasattr(widget, "_zoom_base_stylesheet"):
                delattr(widget, "_zoom_base_stylesheet")
            terapkan_zoom_tabel(widget, is_dark, zoom)
            continue

        key = "sz_input" if isinstance(widget, _ZOOM_INPUT_WIDGETS) else "sz_base"
        terapkan_zoom_widget_standar(widget, zoom, key)

    if hasattr(container_widget, "updateGeometry"):
        container_widget.updateGeometry()


def terapkan_zoom_ke_seluruh_ui(container_widget: QWidget, z: int,
                                 is_dark: bool = False) -> None:
    terapkan_zoom_semua_elemen(container_widget, z, is_dark)