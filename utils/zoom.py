# utils/zoom.py
"""Helper zoom UI global untuk aplikasi PySide6.

Fungsi utama:
- menyimpan dan membaca level zoom per modul;
- memperbesar font, input, tombol, ikon, layout, scrollbar;
- memperbesar tabel, header, tinggi baris, dan lebar kolom;
- menjaga ukuran dasar agar zoom berulang tidak menumpuk.
"""

from typing import Any, Optional

from PySide6.QtCore import QSettings, QSize
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLayout,
    QLineEdit,
    QListView,
    QListWidget,
    QMenu,
    QMenuBar,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableView,
    QTableWidget,
    QTabWidget,
    QTextEdit,
    QTimeEdit,
    QToolBar,
    QToolButton,
    QTreeView,
    QTreeWidget,
    QWidget,
)

from utils import typography

ORGANIZATION_NAME = "AplikasiEkspedisi"
APPLICATION_NAME = "PengaturanUI"
MIN_ZOOM_LEVEL = -4
MAX_ZOOM_LEVEL = 10
DEFAULT_ICON_SIZE = 18
DEFAULT_TABLE_ROW_HEIGHT = 32
DEFAULT_TABLE_HEADER_HEIGHT = 36

# Batas aman sebelum nilai diteruskan ke API C++ milik Qt.
QT_GEOMETRY_MAX = 16_777_215
MAX_COLUMN_WIDTH = 100_000
MAX_FONT_SIZE = 96
MAX_ICON_BASE_SIZE = 256
MAX_ICON_RENDER_SIZE = 512

settings_ui = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)


def _int_aman(
        value: Any,
        default: int = 0,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
) -> int:
    """Konversi ke int dan batasi agar aman untuk binding Qt/C++."""
    try:
        hasil = int(value)
    except (TypeError, ValueError, OverflowError):
        hasil = int(default)

    if minimum is not None:
        hasil = max(int(minimum), hasil)
    if maximum is not None:
        hasil = min(int(maximum), hasil)
    return hasil


def batasi_ukuran_font(value: Any, default: int = 10) -> int:
    """Ukuran font aman untuk QFont.setPointSize/QFont constructor."""
    minimum = _int_aman(getattr(typography, "MIN_FONT_SIZE", 8), 8, 1, 32)
    return _int_aman(value, default, minimum, MAX_FONT_SIZE)


def _batasi_zoom(z: Any) -> int:
    return _int_aman(z, 0, MIN_ZOOM_LEVEL, MAX_ZOOM_LEVEL)


def _faktor_zoom(z: Any) -> float:
    zoom = _batasi_zoom(z)
    return max(0.68, min(1.0 + (zoom * 0.08), 1.80))


def _skalakan(
        nilai: Any,
        z: Any,
        minimum: int = 0,
        maximum: int = QT_GEOMETRY_MAX,
) -> int:
    angka = _int_aman(nilai, minimum, minimum, maximum)
    try:
        hasil = round(angka * _faktor_zoom(z))
    except (TypeError, ValueError, OverflowError):
        hasil = minimum
    return _int_aman(hasil, minimum, minimum, maximum)


def _ambil_atau_simpan_dasar(objek: Any, nama: str, nilai: Any) -> Any:
    atribut = f"_zoom_base_{nama}"
    if not hasattr(objek, atribut):
        setattr(objek, atribut, nilai)
    return getattr(objek, atribut)


def _qsize_icon_aman(
        objek: Any,
        nama_cache: str,
        ukuran_saat_ini: Any,
        default_size: int = DEFAULT_ICON_SIZE,
) -> QSize:
    """Mengambil ukuran dasar ikon yang valid dan menimpa cache rusak.

    QSize.isValid() hanya memastikan dimensi tidak negatif. Nilai positif yang
    sangat besar tetap dianggap valid oleh Qt, sehingga harus dibatasi manual.
    """
    atribut = f"_zoom_base_{nama_cache}"
    kandidat = getattr(objek, atribut, ukuran_saat_ini)

    try:
        width = kandidat.width()
        height = kandidat.height()
    except (AttributeError, TypeError, RuntimeError):
        width = default_size
        height = default_size

    width = _int_aman(
        width,
        default=default_size,
        minimum=1,
        maximum=MAX_ICON_BASE_SIZE,
    )
    height = _int_aman(
        height,
        default=default_size,
        minimum=1,
        maximum=MAX_ICON_BASE_SIZE,
    )

    ukuran_aman = QSize(width, height)

    # Penting: cache lama yang sudah berisi nilai abnormal harus ditimpa.
    setattr(objek, atribut, ukuran_aman)
    return ukuran_aman


def _ukuran_icon_terzoom(
        ukuran_dasar: QSize,
        faktor: float,
        minimum: int = 12,
) -> QSize:
    """Menghasilkan QSize ikon yang aman untuk setIconSize()."""
    try:
        width = round(ukuran_dasar.width() * faktor)
        height = round(ukuran_dasar.height() * faktor)
    except (AttributeError, TypeError, ValueError, OverflowError):
        width = DEFAULT_ICON_SIZE
        height = DEFAULT_ICON_SIZE

    return QSize(
        _int_aman(
            width,
            default=DEFAULT_ICON_SIZE,
            minimum=minimum,
            maximum=MAX_ICON_RENDER_SIZE,
        ),
        _int_aman(
            height,
            default=DEFAULT_ICON_SIZE,
            minimum=minimum,
            maximum=MAX_ICON_RENDER_SIZE,
        ),
    )


def _master_font() -> str:
    return str(getattr(typography, "MASTER_FONT", "Roboto") or "Roboto")


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


def generate_style_tabel(is_dark: bool, z: int = 0) -> str:
    zoom = _batasi_zoom(z)
    sizes = typography.get_global_font_sizes(zoom)
    sz_base = batasi_ukuran_font(
        sizes.get("sz_base", max(_ukuran_font_minimum(), 13 + zoom)),
        default=13,
    )
    font_family = _font_family_qss()

    padding_item = max(2, 4 + zoom)
    padding_header_v = max(4, 6 + zoom)
    padding_header_h = max(6, 8 + (zoom * 2))
    indicator = _skalakan(16, zoom, minimum=12)

    if is_dark:
        bg = "#1a1d24"
        alt_bg = "#20242b"
        text = "#f8fafc"
        grid = "#334155"
        header_bg = "#1e293b"
        header_text = "#ffffff"
        selected_bg = "#3b82f6"
    else:
        bg = "#ffffff"
        alt_bg = "#f1f5f9"
        text = "#0f172a"
        grid = "#e2e8f0"
        header_bg = "#243752"
        header_text = "#ffffff"
        selected_bg = "#2563eb"

    return f"""
        QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {{
            background-color: {bg};
            alternate-background-color: {alt_bg};
            color: {text};
            gridline-color: {grid};
            border: 1px solid {grid};
            font-family: '{font_family}';
            font-size: {sz_base}pt;
        }}
        QTableWidget::item,
        QTableView::item,
        QTreeWidget::item,
        QTreeView::item,
        QListWidget::item,
        QListView::item {{
            padding: {padding_item}px;
        }}
        QHeaderView::section {{
            background-color: {header_bg};
            color: {header_text};
            border: 1px solid {grid};
            font-family: '{font_family}';
            font-size: {sz_base}pt;
            font-weight: bold;
            padding: {padding_header_v}px {padding_header_h}px;
        }}
        QTableWidget::item:selected,
        QTableView::item:selected,
        QTreeWidget::item:selected,
        QTreeView::item:selected,
        QListWidget::item:selected,
        QListView::item:selected {{
            background-color: {selected_bg};
            color: #ffffff;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: {indicator}px;
            height: {indicator}px;
        }}
    """


def _pasang_stylesheet_zoom(widget: QWidget, qss_zoom: str) -> None:
    if not hasattr(widget, "_zoom_base_stylesheet"):
        widget._zoom_base_stylesheet = widget.styleSheet()

    dasar = getattr(widget, "_zoom_base_stylesheet", "")
    gabungan = f"{dasar}\n/* ZOOM OTOMATIS */\n{qss_zoom}" if dasar else qss_zoom
    widget.setStyleSheet(gabungan)


def _terapkan_font(widget: QWidget, z: int, key_ukuran: str) -> None:
    sizes = typography.get_global_font_sizes(z)
    key_property = widget.property("zoom_font_key")
    if key_property:
        key_ukuran = str(key_property)

    ukuran = batasi_ukuran_font(
        sizes.get(key_ukuran, max(_ukuran_font_minimum(), 13 + z)),
        default=13,
    )
    font = widget.font()
    font.setFamily(_master_font())
    font.setPointSize(ukuran)
    widget.setFont(font)


def _terapkan_icon(widget: QWidget, z: int) -> None:
    faktor = _faktor_zoom(z)

    if isinstance(widget, (QAbstractButton, QComboBox)):
        ukuran = widget.iconSize()
        dasar = _qsize_icon_aman(
            widget,
            "icon_size",
            ukuran,
            default_size=DEFAULT_ICON_SIZE,
        )
        widget.setIconSize(
            _ukuran_icon_terzoom(dasar, faktor, minimum=12)
        )

    elif isinstance(widget, QToolBar):
        ukuran = widget.iconSize()
        dasar = _qsize_icon_aman(
            widget,
            "toolbar_icon_size",
            ukuran,
            default_size=24,
        )
        widget.setIconSize(
            _ukuran_icon_terzoom(dasar, faktor, minimum=14)
        )

    elif isinstance(widget, QTabWidget):
        tab_bar = widget.tabBar()
        ukuran = tab_bar.iconSize()
        dasar = _qsize_icon_aman(
            tab_bar,
            "icon_size",
            ukuran,
            default_size=DEFAULT_ICON_SIZE,
        )
        tab_bar.setIconSize(
            _ukuran_icon_terzoom(dasar, faktor, minimum=12)
        )


def _terapkan_tinggi_widget(widget: QWidget, z: int) -> None:
    tipe_satu_baris = (
        QAbstractButton,
        QLineEdit,
        QComboBox,
        QSpinBox,
        QDoubleSpinBox,
        QDateEdit,
        QDateTimeEdit,
        QTimeEdit,
        QProgressBar,
    )
    if not isinstance(widget, tipe_satu_baris):
        return

    minimum_lama = widget.minimumHeight()
    maksimum_lama = widget.maximumHeight()

    # 💡 PERBAIKAN: Jika widget adalah input field, paksa tinggi dasar ideal = 36px agar lebih lega
    if isinstance(
        widget,
        (
            QLineEdit,
            QComboBox,
            QDateEdit,
            QDateTimeEdit,
            QTimeEdit,
            QSpinBox,
            QDoubleSpinBox,
        ),
    ):
        tinggi_default = 42
    else:
        tinggi_default = max(minimum_lama, widget.sizeHint().height(), 24)

    dasar = _ambil_atau_simpan_dasar(
        widget,
        "minimum_height",
        tinggi_default,
    )
    fixed_dasar = _ambil_atau_simpan_dasar(
        widget,
        "fixed_height",
        maksimum_lama < 16777215 and maksimum_lama == minimum_lama,
    )

    tinggi = _skalakan(dasar, z, minimum=20)
    widget.setMinimumHeight(tinggi)
    if fixed_dasar:
        widget.setMaximumHeight(tinggi)


def _terapkan_padding(widget: QWidget, z: int) -> None:
    zoom = _batasi_zoom(z)
    kecil = max(2, 4 + zoom)
    vertikal = max(3, 5 + zoom)
    horizontal = max(5, 8 + (zoom * 2))
    radius = max(2, 4 + (zoom // 2))

    if isinstance(widget, (QPushButton, QToolButton)):
        _pasang_stylesheet_zoom(widget, f"""
            QPushButton, QToolButton {{
                padding: {vertikal}px {horizontal}px;
                border-radius: {radius}px;
            }}
        """)
    elif isinstance(widget, (QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
                             QDateEdit, QDateTimeEdit, QTimeEdit)):
        _pasang_stylesheet_zoom(widget, f"""
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit {{
                padding: {kecil}px {horizontal}px;
            }}
        """)
    elif isinstance(widget, (QTextEdit, QPlainTextEdit)):
        _pasang_stylesheet_zoom(widget, f"""
            QTextEdit, QPlainTextEdit {{
                padding: {kecil}px;
            }}
        """)
    elif isinstance(widget, QTabWidget):
        _pasang_stylesheet_zoom(widget, f"""
            QTabBar::tab {{
                padding: {vertikal}px {horizontal}px;
            }}
        """)
    elif isinstance(widget, QMenuBar):
        _pasang_stylesheet_zoom(widget, f"""
            QMenuBar::item {{
                padding: {vertikal}px {horizontal}px;
            }}
        """)
    elif isinstance(widget, QMenu):
        _pasang_stylesheet_zoom(widget, f"""
            QMenu::item {{
                padding: {vertikal}px {horizontal * 2}px;
            }}
        """)
    elif isinstance(widget, QGroupBox):
        margin_top = max(8, 12 + (zoom * 2))
        _pasang_stylesheet_zoom(widget, f"""
            QGroupBox {{
                margin-top: {margin_top}px;
            }}
            QGroupBox::title {{
                padding: 0 {kecil}px;
            }}
        """)


def terapkan_zoom_widget_standar(
        widget: QWidget,
        z: int,
        key_ukuran: str = "sz_base",
) -> None:
    if widget is None:
        return
    zoom = _batasi_zoom(z)
    _terapkan_font(widget, zoom, key_ukuran)
    _terapkan_icon(widget, zoom)
    _terapkan_tinggi_widget(widget, zoom)
    _terapkan_padding(widget, zoom)

    # 💡 PERBAIKAN: Jika widget punya properti 'base_width', set lebar dinamis yang ikut ter-zoom
    lebar_dasar = widget.property("base_width")
    if lebar_dasar is not None:
        lebar_dasar = _int_aman(lebar_dasar, 140, 100, MAX_COLUMN_WIDTH)
        widget.setFixedWidth(
            _skalakan(lebar_dasar, zoom, minimum=140, maximum=MAX_COLUMN_WIDTH)
        )


def _skalakan_kolom_tableview(table: QTableView, z: int) -> None:
    # --- TAMBAHKAN PENGECEKAN INI ---
    # Cek apakah tabel secara eksplisit melarang scaling kolom
    scale_columns = table.property("zoom_scale_columns")
    if scale_columns is False:
        return
    # ---------------------------------

    model = table.model()
    if model is None:
        return

    if not hasattr(table, "_zoom_base_column_widths"):
        table._zoom_base_column_widths = {}

    header = table.horizontalHeader()
    for kolom in range(model.columnCount()):
        if kolom not in table._zoom_base_column_widths:
            table._zoom_base_column_widths[kolom] = table.columnWidth(kolom)

        # Cache lama bisa saja sudah berisi angka abnormal. Normalisasi ulang
        # sebelum dipakai sebagai argumen kedua setColumnWidth().
        lebar_dasar = _int_aman(
            table._zoom_base_column_widths.get(kolom),
            default=max(20, table.columnWidth(kolom)),
            minimum=20,
            maximum=MAX_COLUMN_WIDTH,
        )
        table._zoom_base_column_widths[kolom] = lebar_dasar

        if header.sectionResizeMode(kolom) != QHeaderView.ResizeMode.Stretch:
            table.setColumnWidth(
                kolom,
                _skalakan(
                    lebar_dasar, z, minimum=20, maximum=MAX_COLUMN_WIDTH
                ),
            )


def _skalakan_kolom_treeview(tree: QTreeView, z: int) -> None:
    model = tree.model()
    if model is None:
        return

    if not hasattr(tree, "_zoom_base_column_widths"):
        tree._zoom_base_column_widths = {}

    header = tree.header()
    for kolom in range(model.columnCount()):
        if kolom not in tree._zoom_base_column_widths:
            tree._zoom_base_column_widths[kolom] = tree.columnWidth(kolom)

        lebar_dasar = _int_aman(
            tree._zoom_base_column_widths.get(kolom),
            default=max(20, tree.columnWidth(kolom)),
            minimum=20,
            maximum=MAX_COLUMN_WIDTH,
        )
        tree._zoom_base_column_widths[kolom] = lebar_dasar

        if header.sectionResizeMode(kolom) != QHeaderView.ResizeMode.Stretch:
            tree.setColumnWidth(
                kolom,
                _skalakan(
                    lebar_dasar, z, minimum=20, maximum=MAX_COLUMN_WIDTH
                ),
            )

    dasar_indent = _ambil_atau_simpan_dasar(
        tree,
        "indentation",
        max(10, tree.indentation()),
    )
    tree.setIndentation(_skalakan(dasar_indent, z, minimum=8))


def terapkan_zoom_tabel(
        table: QAbstractItemView,
        is_dark: bool,
        z: int = 0,
) -> None:
    if table is None:
        return

    zoom = _batasi_zoom(z)
    sizes = typography.get_global_font_sizes(zoom)
    size_base = batasi_ukuran_font(
        sizes.get("sz_base", max(_ukuran_font_minimum(), 13 + zoom)),
        default=13,
    )

    table.setStyleSheet(generate_style_tabel(is_dark, zoom))
    font = table.font()
    font.setFamily(_master_font())
    font.setPointSize(size_base)
    table.setFont(font)

    # Tinggi tabel tidak cukup hanya diskalakan dari konstanta.
    # QSS memberi padding atas dan bawah pada setiap item, sehingga tinggi
    # baris harus memperhitungkan tinggi font aktual + seluruh padding.
    item_padding = max(2, 4 + zoom)
    header_padding_v = max(4, 6 + zoom)

    base_row_height = _skalakan(
        DEFAULT_TABLE_ROW_HEIGHT,
        zoom,
        minimum=24,
        maximum=10_000,
    )
    base_header_height = _skalakan(
        DEFAULT_TABLE_HEADER_HEIGHT,
        zoom,
        minimum=26,
        maximum=10_000,
    )

    text_height = max(1, int(table.fontMetrics().height()))
    row_height = _int_aman(
        max(
            base_row_height,
            text_height + (item_padding * 2) + 8,
        ),
        default=base_row_height,
        minimum=24,
        maximum=10_000,
    )

    icon_size = _skalakan(
        DEFAULT_ICON_SIZE,
        zoom,
        minimum=12,
        maximum=4_096,
    )
    table.setIconSize(QSize(icon_size, icon_size))

    if isinstance(table, QTableView):
        h_header = table.horizontalHeader()
        v_header = table.verticalHeader()

        header_font = h_header.font()
        header_font.setFamily(_master_font())
        header_font.setPointSize(size_base)
        header_font.setBold(True)
        h_header.setFont(header_font)
        v_header.setFont(header_font)

        header_text_height = max(1, int(h_header.fontMetrics().height()))
        header_height = _int_aman(
            max(
                base_header_height,
                header_text_height + (header_padding_v * 2) + 8,
            ),
            default=base_header_height,
            minimum=26,
            maximum=10_000,
        )

        # Lepaskan batas maksimum lama jika header sebelumnya memakai
        # setFixedHeight(), agar tinggi dapat mengikuti zoom.
        if h_header.maximumHeight() < header_height:
            h_header.setMaximumHeight(QT_GEOMETRY_MAX)

        h_header.setMinimumHeight(header_height)

        # DefaultSectionSize berlaku juga untuk baris baru setelah tabel
        # di-refresh. MinimumSectionSize mencegah baris menyusut kembali.
        v_header.setMinimumSectionSize(row_height)
        v_header.setDefaultSectionSize(row_height)

        # Simpan untuk modul yang ingin menyelaraskan tinggi setelah refresh.
        table._zoom_current_row_height = row_height
        table._zoom_current_header_height = header_height

        _skalakan_kolom_tableview(table, zoom)
        model = table.model()
        if model is not None:
            for row in range(model.rowCount()):
                table.setRowHeight(row, row_height)

    elif isinstance(table, QTreeView):
        header = table.header()
        header.setMinimumHeight(header_height)
        header_font = header.font()
        header_font.setFamily(_master_font())
        header_font.setPointSize(size_base)
        header_font.setBold(True)
        header.setFont(header_font)
        _skalakan_kolom_treeview(table, zoom)

    elif isinstance(table, QListView):
        grid = table.gridSize()
        if grid.isValid():
            dasar = _ambil_atau_simpan_dasar(table, "grid_size", grid)
            table.setGridSize(QSize(
                _skalakan(dasar.width(), zoom, minimum=20),
                _skalakan(dasar.height(), zoom, minimum=20),
            ))


def _terapkan_zoom_layout(layout: Optional[QLayout], z: int) -> None:
    if layout is None:
        return

    margins = layout.contentsMargins()
    dasar_margin = _ambil_atau_simpan_dasar(
        layout,
        "layout_margins",
        (margins.left(), margins.top(), margins.right(), margins.bottom()),
    )
    layout.setContentsMargins(*[
        _skalakan(nilai, z, minimum=0) for nilai in dasar_margin
    ])

    spacing = layout.spacing()
    dasar_spacing = _ambil_atau_simpan_dasar(layout, "layout_spacing", spacing)
    if dasar_spacing >= 0:
        layout.setSpacing(_skalakan(dasar_spacing, z, minimum=0))

    if isinstance(layout, QGridLayout):
        h_spacing = _ambil_atau_simpan_dasar(
            layout, "horizontal_spacing", layout.horizontalSpacing()
        )
        v_spacing = _ambil_atau_simpan_dasar(
            layout, "vertical_spacing", layout.verticalSpacing()
        )
        if h_spacing >= 0:
            layout.setHorizontalSpacing(_skalakan(h_spacing, z, minimum=0))
        if v_spacing >= 0:
            layout.setVerticalSpacing(_skalakan(v_spacing, z, minimum=0))

    for index in range(layout.count()):
        child_layout = layout.itemAt(index).layout()
        if child_layout is not None:
            _terapkan_zoom_layout(child_layout, z)


def terapkan_zoom_semua_elemen(
        container_widget: QWidget,
        z: int,
        is_dark: bool = False,
) -> None:
    """Menerapkan zoom rekursif pada container beserta seluruh anaknya (VERSI AMAN)."""
    if container_widget is None:
        return

    zoom = _batasi_zoom(z)
    _terapkan_zoom_layout(container_widget.layout(), zoom)

    semua_widget = [container_widget]
    semua_widget.extend(container_widget.findChildren(QWidget))

    tipe_item_view = (
        QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView,
    )

    for widget in semua_widget:
        if hasattr(widget, "_zoom_base_stylesheet"):
            try:
                widget.setStyleSheet(widget._zoom_base_stylesheet)
            except Exception:
                pass

        if isinstance(widget, tipe_item_view):
            if hasattr(widget, "_zoom_base_stylesheet"):
                delattr(widget, "_zoom_base_stylesheet")
            terapkan_zoom_tabel(widget, is_dark, zoom)
            continue

        key = "sz_input" if isinstance(
            widget,
            (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox,
             QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit),
        ) else "sz_base"

        property_key = widget.property("zoom_font_key")
        if property_key:
            key = str(property_key)

        terapkan_zoom_widget_standar(widget, zoom, key)

    if hasattr(container_widget, "updateGeometry"):
        container_widget.updateGeometry()


def terapkan_zoom_ke_seluruh_ui(
        container_widget: QWidget,
        z: int,
        is_dark: bool = False,
) -> None:
    terapkan_zoom_semua_elemen(container_widget, z, is_dark)
