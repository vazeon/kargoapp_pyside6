from dataclasses import dataclass
from typing import Any, Optional

from PySide6.QtCore import QSettings, QSignalBlocker, QSize, QTimer, QEvent, Qt, QObject
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QHeaderView,
    QTableView,
    QWidget,
)

from utils import typography
from utils.ui_metrics import dapatkan_ui_scale, skalakan_px
from themes.components.table import get_table_styles, TableMetrics
from themes.colors import get_theme_colors


# Gunakan identitas QSettings yang sama dengan aplikasi utama.
ORGANIZATION_NAME = str(
    getattr(typography, "ORGANIZATION_NAME", "AplikasiEkspedisi")
    or "AplikasiEkspedisi"
)
APPLICATION_NAME = str(
    getattr(typography, "APPLICATION_NAME", "PengaturanUI")
    or "PengaturanUI"
)

MIN_ZOOM_LEVEL = -4
MAX_ZOOM_LEVEL = 10

DEFAULT_TABLE_ROW_HEIGHT = 32
DEFAULT_TABLE_HEADER_HEIGHT = 36
DEFAULT_TABLE_ICON_SIZE = 18

QT_GEOMETRY_MAX = 16_777_215
MAX_COLUMN_WIDTH = 100_000
MAX_FONT_SIZE = 96
MAX_ICON_RENDER_SIZE = 512

# QTableWidget adalah subclass QTableView, jadi otomatis tercakup.
_TABLE_VIEW_TYPES = (QTableView,)

settings_ui = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)


class CtrlWheelZoomFilter(QObject):
    """Menangkap Ctrl + mouse wheel agar tabel tidak ikut scroll.

    Wheel normal tetap diteruskan ke QTableView.
    Callback diberikan oleh aplikasi/tab yang mengetahui cara menerapkan zoom.
    """

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta == 0:
                    return False
                if callable(self.callback):
                    self.callback(1 if delta > 0 else -1)
                event.accept()
                return True

        return False


def pasang_ctrl_scroll_zoom(table, callback):
    """
    Pasang Ctrl+Scroll zoom pada tabel.

    Scroll biasa tetap berfungsi normal.
    """
    if table is None:
        return

    previous = getattr(table, "_ctrl_wheel_zoom_filter", None)
    filter_zoom = CtrlWheelZoomFilter(callback)
    filter_zoom.setParent(table)
    table._ctrl_wheel_zoom_filter = filter_zoom
    for target in (table, getattr(table, "frozen_table", None)):
        if target is None:
            continue
        viewport = getattr(target, "viewport", None)
        for receiver in (target, viewport() if callable(viewport) else None):
            if receiver is not None:
                if previous is not None:
                    receiver.removeEventFilter(previous)
                receiver.installEventFilter(filter_zoom)
    if previous is not None:
        previous.deleteLater()


def _int_aman(
    value: Any,
    default: int = 0,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
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


def _float_aman(
    value: Any,
    default: float = 0.0,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    """Konversi float defensif untuk ukuran font dan faktor zoom."""
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
    minimum = _float_aman(
        getattr(typography, "MIN_FONT_SIZE_PT", 6.0),
        6.0,
        1.0,
        32.0,
    )
    return _float_aman(value, default, minimum, float(MAX_FONT_SIZE))


def _batasi_zoom(z: Any) -> int:
    return _int_aman(z, 0, MIN_ZOOM_LEVEL, MAX_ZOOM_LEVEL)


def _faktor_zoom(z: Any) -> float:
    """Faktor historis aplikasi: +8% per level, dibatasi 0.68..1.80."""
    return max(0.68, min(1.0 + (_batasi_zoom(z) * 0.08), 1.80))


def dapatkan_faktor_zoom(z: Any) -> float:
    """Faktor zoom manual tabel, tanpa responsive screen scale."""
    return _faktor_zoom(z)


def dapatkan_faktor_geometri(z: Any) -> float:
    """Faktor geometry tabel = responsive screen scale × zoom manual."""
    return dapatkan_ui_scale() * _faktor_zoom(z)


def _skalakan(
    nilai: Any,
    z: Any,
    minimum: int = 0,
    maximum: int = QT_GEOMETRY_MAX,
) -> int:
    angka = _int_aman(nilai, minimum, minimum, maximum)
    try:
        hasil = round(angka * dapatkan_faktor_geometri(z))
    except (TypeError, ValueError, OverflowError):
        hasil = minimum
    return _int_aman(hasil, minimum, minimum, maximum)


def _skalakan_zoom_manual(
    nilai: Any,
    z: Any,
    minimum: int = 0,
    maximum: int = QT_GEOMETRY_MAX,
) -> int:
    """Scale untuk token QSS; responsive screen diterapkan ui_scaler."""
    angka = _int_aman(nilai, minimum, minimum, maximum)
    try:
        hasil = round(angka * _faktor_zoom(z))
    except (TypeError, ValueError, OverflowError):
        hasil = minimum
    return _int_aman(hasil, minimum, minimum, maximum)


@dataclass(frozen=True)
class ZoomMetrics:
    """Metrik zoom yang hanya relevan untuk tabel."""

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
    sizes = typography.get_zoom_font_sizes_pt(level)

    return ZoomMetrics(
        level=level,
        factor=dapatkan_faktor_geometri(level),
        font_base_pt=batasi_ukuran_font(sizes.get("sz_base", 9.0), 9.0),
        row_height=_skalakan(DEFAULT_TABLE_ROW_HEIGHT, level, 24, 10_000),
        header_height=_skalakan(DEFAULT_TABLE_HEADER_HEIGHT, level, 26, 10_000),
        icon_size=_skalakan(
            DEFAULT_TABLE_ICON_SIZE,
            level,
            12,
            MAX_ICON_RENDER_SIZE,
        ),
        item_padding=max(2, 4 + level),
        header_padding_v=max(4, 6 + level),
    )


def dapatkan_zoom_level(class_name: str) -> int:
    """Ambil level zoom yang tersimpan untuk satu tab/class."""
    nama = str(class_name or "").strip()
    if not nama:
        return 0
    return _batasi_zoom(settings_ui.value(f"zoom_{nama}", 0))


def simpan_zoom_level(class_name: str, zoom_level: int) -> int:
    """Simpan level zoom untuk satu tab/class."""
    nama = str(class_name or "").strip()
    zoom = _batasi_zoom(zoom_level)

    if nama:
        settings_ui.setValue(f"zoom_{nama}", zoom)
        settings_ui.sync()

    return zoom


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





def _ambil_atau_simpan_dasar(objek: Any, nama: str, nilai: Any) -> Any:
    atribut = f"_zoom_base_{nama}"
    if not hasattr(objek, atribut):
        setattr(objek, atribut, nilai)
    return getattr(objek, atribut)


def _skalakan_kolom(view: Any, header: QHeaderView, z: int) -> None:
    """Menskalakan lebar kolom dari cache lebar dasar, bukan hasil zoom terakhir."""
    if view is None or header is None:
        return

    model = view.model()
    if model is None:
        return

    cache = getattr(view, "_zoom_base_column_widths", None)
    if not isinstance(cache, dict):
        cache = {}
        view._zoom_base_column_widths = cache

    for kolom in range(model.columnCount()):
        lebar_saat_ini = max(20, int(view.columnWidth(kolom)))

        if kolom not in cache:
            cache[kolom] = lebar_saat_ini

        dasar = _int_aman(
            cache.get(kolom),
            lebar_saat_ini,
            20,
            MAX_COLUMN_WIDTH,
        )
        cache[kolom] = dasar

        if header.sectionResizeMode(kolom) == QHeaderView.ResizeMode.Stretch:
            continue

        view.setColumnWidth(
            kolom,
            _skalakan(dasar, z, 20, MAX_COLUMN_WIDTH),
        )


def skalakan_kolom_tableview(table: QTableView, z: int) -> None:
    """API publik untuk menskalakan kolom QTableView/QTableWidget saja."""
    if table is None or not isinstance(table, QTableView):
        return
    if table.property("zoom_scale_columns") is False:
        return

    _skalakan_kolom(table, table.horizontalHeader(), _batasi_zoom(z))


def reset_cache_lebar_kolom(table: QTableView) -> None:
    """Hapus cache lebar dasar bila struktur/lebar dasar tabel diinisialisasi ulang."""
    if table is None:
        return
    if hasattr(table, "_zoom_base_column_widths"):
        delattr(table, "_zoom_base_column_widths")


def _panggil_metode_jika_tersedia(objek: Any, *nama_metode: str) -> bool:
    for nama in nama_metode:
        metode = getattr(objek, nama, None)
        if callable(metode):
            metode()
            return True
    return False


def _sinkronkan_frozen_sekarang(table: QTableView) -> None:
    if table is None:
        return

    try:
        frozen = getattr(table, "frozen_table", None)

        table.doItemsLayout()
        table.updateGeometries()

        if frozen is not None:
            frozen.doItemsLayout()
            frozen.updateGeometries()

        # Geometri dihitung setelah layout agar memakai ukuran viewport terbaru.
        _panggil_metode_jika_tersedia(
            table,
            "update_frozen_geometry",
            "updateFrozenTableGeometry",
            "update_frozen_table_geometry",
            "_update_frozen_table_geometry",
            "perbarui_geometri_frozen",
        )

        if frozen is not None:
            frozen.verticalScrollBar().setValue(
                table.verticalScrollBar().value()
            )
            frozen.raise_()

        table.viewport().update()
        table.update()

        if frozen is not None:
            frozen.viewport().update()
            frozen.update()

    except RuntimeError:
        # Widget mungkin sudah dihancurkan ketika aplikasi ditutup.
        return


def sinkronkan_frozen_table(
    table: QTableView,
    *,
    tertunda: bool = True,
) -> None:
    """Sinkronkan geometri frozen table tanpa menyentuh widget di luar tabel."""
    if table is None:
        return

    _sinkronkan_frozen_sekarang(table)

    if tertunda:
        QTimer.singleShot(
            0,
            lambda table=table: _sinkronkan_frozen_sekarang(table),
        )


def _tinggi_view(
    font_height: Any,
    dasar: int,
    padding: int,
    minimum: int,
) -> int:
    padding_responsive = skalakan_px(padding, minimum=1)
    ekstra_responsive = skalakan_px(8, minimum=4)
    minimum_responsive = skalakan_px(minimum, minimum=18)
    return _int_aman(
        max(
            dasar,
            max(1, int(font_height)) + (padding_responsive * 2) + ekstra_responsive,
        ),
        dasar,
        minimum_responsive,
        10_000,
    )


def _header_font(header: QHeaderView, metrics: ZoomMetrics):
    font = header.font()
    font.setFamily(_master_font())
    font.setPointSizeF(metrics.font_base_pt)
    font.setBold(True)
    return font


def _terapkan_font_item_view(view: QAbstractItemView, metrics: ZoomMetrics) -> None:
    font = view.font()
    font.setFamily(_master_font())
    font.setPointSizeF(metrics.font_base_pt)
    view.setFont(font)
    view.setIconSize(QSize(metrics.icon_size, metrics.icon_size))


def terapkan_zoom_tabel(
        table: QAbstractItemView,
        is_dark: bool = False,
        z: int = 0,
) -> None:
    if table is None or not isinstance(table, _TABLE_VIEW_TYPES):
        return

    zoom = _batasi_zoom(z)
    metrics_font = dapatkan_metrik_zoom(z)
    frozen = getattr(table, "frozen_table", None)

    # Hanya lepaskan kunci yang dipasang oleh pemanggilan ini. False dapat
    # diwarisi dari parent/batch luar; jangan mengubahnya menjadi kunci lokal.
    # Frozen adalah child tabel dan otomatis mengikuti pembaruan parent.
    updates_main = table.updatesEnabled()
    if updates_main:
        table.setUpdatesEnabled(False)

    try:
        # Rakit metrics dengan logika responsive UI
        t_metrics = TableMetrics(
            font_family=_font_family_qss(),
            font_size_pt=metrics_font.font_base_pt,
            item_pad=skalakan_px(max(2, 4 + zoom), minimum=2),
            header_v=skalakan_px(max(4, 6 + zoom), minimum=3),
            header_h=skalakan_px(max(6, 8 + (zoom * 2)), minimum=5),
            indicator_size=skalakan_px(16 + (zoom * 2), minimum=10)
        )

        ui_colors = get_theme_colors(is_dark).get("ui", {})

        # Terapkan styling terpusat
        style_tabel = get_table_styles(is_dark, metrics=t_metrics, ui_colors=ui_colors)
        table.setStyleSheet(style_tabel)
        if frozen is not None:
            frozen.setStyleSheet(style_tabel)

        _terapkan_font_item_view(table, metrics_font)

        if isinstance(table, QTableView):
            h_header = table.horizontalHeader()
            v_header = table.verticalHeader()
            header_font = _header_font(h_header, metrics_font)

            h_header.setFont(header_font)
            v_header.setFont(header_font)

            row_height = _tinggi_view(
                table.fontMetrics().height(),
                metrics_font.row_height,
                metrics_font.item_padding,
                24,
            )
            header_height = _tinggi_view(
                h_header.fontMetrics().height(),
                metrics_font.header_height,
                metrics_font.header_padding_v,
                26,
            )

            if h_header.maximumHeight() < header_height:
                h_header.setMaximumHeight(QT_GEOMETRY_MAX)

            h_header.setMinimumHeight(header_height)
            v_header.setMinimumSectionSize(row_height)
            v_header.setDefaultSectionSize(row_height)

            table._zoom_current_row_height = row_height
            table._zoom_current_header_height = header_height

            from PySide6.QtCore import QSignalBlocker
            blocker = QSignalBlocker(h_header)
            try:
                skalakan_kolom_tableview(table, metrics_font.level)
            finally:
                del blocker

            model = table.model()
            if model is not None:
                for row in range(model.rowCount()):
                    table.setRowHeight(row, row_height)

            if frozen is not None:
                _terapkan_font_item_view(frozen, metrics_font)
                frozen.horizontalHeader().setFont(header_font)
                frozen.verticalHeader().setFont(header_font)
                frozen.verticalHeader().setMinimumSectionSize(row_height)
                frozen.verticalHeader().setDefaultSectionSize(row_height)

                if model is not None:
                    for row in range(model.rowCount()):
                        frozen.setRowHeight(row, row_height)

    finally:
        if updates_main:
            table.setUpdatesEnabled(True)

        if isinstance(table, QTableView):
            sinkronkan_frozen_table(table, tertunda=True)


def _tabel_utama_dalam_container(container_widget: QWidget) -> list[QTableView]:
    """Ambil QTableView utama dan abaikan frozen child agar tidak di-zoom dua kali."""
    if container_widget is None:
        return []

    kandidat: list[QTableView] = []

    if isinstance(container_widget, QTableView):
        kandidat.append(container_widget)

    kandidat.extend(container_widget.findChildren(QTableView))

    frozen_ids = {
        id(frozen)
        for tabel in kandidat
        for frozen in (getattr(tabel, "frozen_table", None),)
        if frozen is not None
    }

    hasil: list[QTableView] = []
    sudah = set()

    for tabel in kandidat:
        identitas = id(tabel)
        if identitas in sudah or identitas in frozen_ids:
            continue
        sudah.add(identitas)
        hasil.append(tabel)

    return hasil

    return hasil