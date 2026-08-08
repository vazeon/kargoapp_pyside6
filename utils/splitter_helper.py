# utils/splitter_helper
from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QWidget

from themes.components.splitter import get_splitter_style


def _deteksi_mode_gelap(widget: QWidget | None) -> bool:
    """Mendeteksi tema aktif dari window induk."""
    if widget is None:
        return False
    window = widget.window()
    return bool(window is not None and hasattr(window, "current_theme") and window.current_theme == "dark")


def buat_splitter(
    *widgets: QWidget,
    orientation: Qt.Orientation = Qt.Orientation.Horizontal,
    ukuran_awal: Sequence[int] | None = None,
    lebar_handle: int = 2,
    bisa_diciutkan: bool = False,
    parent: QWidget | None = None,
) -> QSplitter:
    """Membuat splitter dengan konfigurasi dan style global."""
    splitter = QSplitter(orientation, parent)
    splitter.setHandleWidth(max(1, lebar_handle))
    splitter.setChildrenCollapsible(bisa_diciutkan)

    for index, widget in enumerate(widgets):
        splitter.addWidget(widget)
        splitter.setCollapsible(index, bisa_diciutkan)

    if ukuran_awal is not None:
        ukuran = list(ukuran_awal)
        if len(ukuran) != len(widgets):
            raise ValueError("Jumlah ukuran_awal harus sama dengan jumlah widget splitter.")
        splitter.setSizes(ukuran)

    splitter.setStyleSheet(get_splitter_style(_deteksi_mode_gelap(parent)))
    return splitter


def perbarui_semua_style_splitter(root: QWidget, is_dark: bool) -> None:
    """Memperbarui semua splitter yang berada di bawah root widget."""
    style = get_splitter_style(is_dark)
    for splitter in root.findChildren(QSplitter):
        splitter.setStyleSheet(style)