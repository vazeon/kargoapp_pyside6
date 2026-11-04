# utils/wheel_event_policy.py
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QTabBar, QWidget


_controller_global: "KebijakanMouseWheel | None" = None


class KebijakanMouseWheel(QObject):
    """Filter event global yang hanya menerapkan aturan pada mouse wheel."""

    def __init__(self, app: QApplication):
        super().__init__(app)
        self._app = app
        app.installEventFilter(self)

    @staticmethod
    def _widget_induk(widget: QWidget):
        """Temukan tab bar atau ComboBox terdekat tanpa memindai seluruh UI."""
        current = widget
        while current is not None:
            if isinstance(current, (QTabBar, QComboBox)):
                return current
            current = current.parentWidget()
        return None

    @staticmethod
    def _event_berasal_dari_dropdown(combo: QComboBox, widget: QWidget) -> bool:
        """Biarkan wheel bekerja pada daftar pilihan ComboBox yang terbuka."""
        try:
            view = combo.view()
            return bool(
                view is not None
                and view.isVisible()
                and (widget is view or view.isAncestorOf(widget))
            )
        except RuntimeError:
            # Widget Qt mungkin sedang dihancurkan; jangan menghambat event.
            return False

    def eventFilter(self, watched, event):
        # Jalan pintas utama: event selain wheel tidak memerlukan pemeriksaan.
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QWidget):
            return False

        target = self._widget_induk(watched)
        if isinstance(target, QTabBar):
            # Jangan pindah tab hanya karena pointer berada di bar tab/subtab.
            event.accept()
            return True

        if isinstance(target, QComboBox):
            # Wheel pada popup daftar pilihan tetap diperbolehkan.
            if self._event_berasal_dari_dropdown(target, watched):
                return False
            # Pertahankan gesture eksplisit yang mungkin dipakai aplikasi
            # (misalnya Ctrl+wheel untuk fitur khusus).
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                return False
            # Termasuk QLineEdit di dalam ComboBox editable: pilihan tidak
            # berubah hanya karena wheel melewati ComboBox.
            event.accept()
            return True

        # Tabel, overlay/frozen view, dan area scroll lain tetap berfungsi.
        return False


def pasang_kebijakan_mouse_wheel(app: QApplication | None = None) -> KebijakanMouseWheel:
    """Pasang kebijakan satu kali dan kembalikan controller yang aktif.

    Pemanggilan berulang pada QApplication yang sama mengembalikan controller
    yang sudah ada, sehingga filter global tidak terpasang ganda.
    """
    global _controller_global

    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError(
            "QApplication harus dibuat sebelum kebijakan mouse wheel dipasang."
        )

    if _controller_global is not None:
        try:
            if _controller_global._app is app:
                return _controller_global
        except RuntimeError:
            _controller_global = None

    _controller_global = KebijakanMouseWheel(app)
    return _controller_global
