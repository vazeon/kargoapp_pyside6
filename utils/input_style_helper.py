# utils/input_style_helper.py
from typing import Any

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QApplication, QCalendarWidget,
    QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QWidget,
)
from themes.colors import get_theme_colors
from themes.components.inputs import get_global_input_qss
from utils.ui_metrics import skalakan_px
from utils.widget_helpers import blokir_signal_sementara


DEFAULT_TINGGI_INPUT = 32


def atur_tinggi_input(widgets: Any, tinggi: int | None = None) -> int:
    """Atur tinggi input dari ukuran desain dasar, lalu skalakan sekali."""
    if isinstance(widgets, QWidget):
        daftar_widget = (widgets,)
    else:
        try:
            daftar_widget = tuple(widget for widget in widgets if widget is not None)
        except TypeError:
            daftar_widget = (widgets,) if widgets is not None else ()

    tinggi_dasar = DEFAULT_TINGGI_INPUT if tinggi is None else int(tinggi)
    tinggi_dasar = max(1, tinggi_dasar)
    tinggi_target = skalakan_px(tinggi_dasar)

    for widget in daftar_widget:
        if widget is not None:
            # ResponsiveUIScaler harus memakai baseline, bukan hasil scale terakhir.
            widget.setProperty("_ui_base_min_height", tinggi_dasar)
            widget.setProperty("_ui_base_max_height", tinggi_dasar)
            widget.setProperty("_ui_scaler_explicit_geometry", True)
            widget.setFixedHeight(tinggi_target)

    return tinggi_target


def paksa_kapital_lineedit(edit_widget: QLineEdit) -> None:
    """Kapitalkan isi QLineEdit tanpa signal berulang; placeholder tetap."""
    teks_lama = edit_widget.text()
    teks_baru = teks_lama.upper()
    if teks_baru == teks_lama:
        return

    pos_lama = edit_widget.cursorPosition()
    with blokir_signal_sementara(edit_widget):
        edit_widget.setText(teks_baru)
        edit_widget.setCursorPosition(min(pos_lama, len(teks_baru)))


INPUT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox)


def is_input_form(widget) -> bool:
    """Lewati delegate editor, cellWidget, frozen view, dan input internal."""
    if not isinstance(widget, INPUT_TYPES):
        return False
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, (QAbstractItemView, *INPUT_TYPES, QCalendarWidget)):
            return False
        parent = parent.parentWidget()
    return True


def _tema_gelap(root) -> bool:
    widget = root
    while widget is not None:
        theme = str(getattr(widget, "current_theme", "") or widget.property("current_theme") or "").lower()
        if theme in {"dark", "light"}:
            return theme == "dark"
        widget = widget.parentWidget()
    app = QApplication.instance()
    if app is not None:
        theme = str(getattr(app, "current_theme", "") or app.property("current_theme") or "").lower()
        if theme in {"dark", "light"}:
            return theme == "dark"
        themes = {
            str(getattr(w, "current_theme", "")).lower()
            for w in app.topLevelWidgets()
        } & {"dark", "light"}
        if len(themes) == 1:
            return themes == {"dark"}
    palette = app.palette() if app else root.palette()
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


class _FormInputStyles(QObject):
    """Satu pengelola per modul/dialog, termasuk input yang muncul belakangan."""

    def __init__(self, root):
        super().__init__(root)
        self._applying = False
        self._dark = False
        # Widget tree pada tab tersembunyi tidak perlu di-scan setiap tema
        # aplikasi berubah. Refresh ditunda sampai tab itu ditampilkan lagi.
        self._pending_theme_refresh = False
        # Cache input widgets yang benar-benar dimiliki root ini. Pemindaian
        # seluruh subtree mahal pada tab berisi banyak cell/widget tabel, jadi
        # setelah scan awal pembaruan tema cukup mengunjungi input yang relevan.
        self._input_widgets = {}
        self._input_cache_initialized = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh)

    def _owns(self, widget):
        """Return True only for QWidget instances owned by this manager."""
        if not isinstance(widget, QWidget):
            return False

        parent = widget
        while isinstance(parent, QWidget):
            owner = getattr(parent, "_global_form_input_styles", None)
            if owner is not None:
                return owner is self
            parent = parent.parentWidget()

        return False

    def _remember_input(self, widget):
        """Cache input widget wrappers without retaining deleted Qt objects."""
        if not isinstance(widget, QWidget):
            return
        key = id(widget)
        existing = self._input_widgets.get(key)
        if existing is widget:
            return
        if existing is not None:
            # Python wrapper bisa tersisa setelah objek C++ Qt dihapus.
            try:
                existing.parentWidget()
            except RuntimeError:
                self._input_widgets.pop(key, None)
            else:
                # Jangan menimpa widget yang masih hidup (id collision sangat
                # jarang, tetapi aman untuk diabaikan jika terjadi).
                return
        self._input_widgets[key] = widget

    def _apply(self, widget):
        """Apply global input styling only to actual QWidget instances."""
        if not isinstance(widget, QWidget):
            return

        if not self._owns(widget) or not is_input_form(widget):
            return
        self._remember_input(widget)
        if not widget.property("globalFormInput"):
            widget.setProperty("globalFormInput", True)
        readonly = bool(getattr(widget, "isReadOnly", lambda: False)())
        qss = get_global_input_qss(self._dark, readonly)
        if widget.styleSheet() != qss:
            widget.setStyleSheet(qss)

        # Jangan mengganti subcontrol panah, spin button, atau popup kalender.
        if isinstance(widget, (QComboBox, QAbstractSpinBox)):
            ui = get_theme_colors(self._dark)["ui"]
            palette = widget.palette()
            for role, color in (
                (QPalette.ColorRole.Base, ui['field_background']),
                (QPalette.ColorRole.Text, ui['table_text']),
                (QPalette.ColorRole.ButtonText, ui['table_text']),
                (QPalette.ColorRole.Highlight, '#0081db'),
                (QPalette.ColorRole.HighlightedText, '#ffffff'),
                (QPalette.ColorRole.PlaceholderText, ui['placeholder_text']),
            ):
                palette.setColor(role, QColor(color))
            for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
                palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(ui['text_muted']))
            if widget.palette() != palette:
                widget.setPalette(palette)

    def refresh(self, is_dark=None):
        if self._applying:
            return
        self._timer.stop()
        self._pending_theme_refresh = False
        self._applying = True
        try:
            root = self.parent()
            self._dark = _tema_gelap(root) if is_dark is None else bool(is_dark)

            if not self._input_cache_initialized:
                # Satu kali scan awal menemukan input yang sudah ada. Widget
                # yang dibuat kemudian ditambahkan dari event Show di bawah.
                for widget in (root, *root.findChildren(QWidget)):
                    try:
                        self._apply(widget)
                    except RuntimeError:
                        # Widget Qt bisa terhapus di tengah pembaruan.
                        continue
                self._input_cache_initialized = True
            else:
                # Theme switch berikutnya hanya memproses input form yang
                # relevan, bukan ribuan widget internal/sel tabel lainnya.
                for key, widget in tuple(self._input_widgets.items()):
                    try:
                        self._apply(widget)
                    except RuntimeError:
                        self._input_widgets.pop(key, None)
        finally:
            self._applying = False


class _FormInputStyleEventRouter(QObject):
    """Satu event filter aplikasi untuk seluruh pengelola style input.

    Setiap modul tetap memiliki cache dan timer sendiri, tetapi event aplikasi
    dirutekan satu kali agar tidak menumpuk banyak filter global yang identik.
    """

    def __init__(self, app: QApplication):
        super().__init__(app)
        self._app = app
        self._managers = {}
        app.installEventFilter(self)

    def register(self, manager: _FormInputStyles) -> None:
        key = id(manager)
        self._managers[key] = manager
        # Parent Qt yang dihancurkan akan menghancurkan manager juga. Lepaskan
        # referensinya dari registry ketika objek C++ benar-benar dihapus.
        manager.destroyed.connect(
            lambda *_args, manager_id=key: self._managers.pop(manager_id, None)
        )

    def _manager_for_widget(self, widget):
        """Cari pengelola pemilik input melalui hierarki QWidget."""
        current = widget
        while isinstance(current, QWidget):
            try:
                manager = getattr(current, "_global_form_input_styles", None)
                if manager is not None:
                    return manager
                current = current.parentWidget()
            except RuntimeError:
                return None
        return None

    def _managers_snapshot(self):
        # Gunakan snapshot agar perubahan registry saat penghancuran widget
        # tidak mengubah koleksi yang sedang diproses.
        return tuple(self._managers.values())

    def eventFilter(self, watched, event):
        try:
            kind = event.type()
        except RuntimeError:
            # Wrapper event/Qt bisa menjadi tidak valid saat penghancuran.
            return False

        if watched is self._app:
            if kind not in (
                QEvent.Type.ApplicationPaletteChange, QEvent.Type.StyleChange,
            ):
                return False

            for manager in self._managers_snapshot():
                try:
                    if manager._applying:
                        continue
                    root = manager.parent()
                    if not isinstance(root, QWidget):
                        continue
                    # Tab tersembunyi diperbarui setelah ditampilkan kembali.
                    if not root.isVisible():
                        manager._pending_theme_refresh = True
                    else:
                        manager._timer.start(0)
                except RuntimeError:
                    continue
            return False

        # Perbarui tema yang ditunda ketika root modul/dialog muncul kembali.
        if isinstance(watched, QWidget) and kind == QEvent.Type.Show:
            try:
                manager_root = getattr(watched, "_global_form_input_styles", None)
                if (
                    manager_root is not None
                    and not manager_root._applying
                    and manager_root._pending_theme_refresh
                ):
                    manager_root._timer.start(0)
            except RuntimeError:
                pass

        if isinstance(watched, INPUT_TYPES) and kind in (
            QEvent.Type.Show, QEvent.Type.ReadOnlyChange,
        ):
            manager = self._manager_for_widget(watched)
            if manager is None or manager._applying:
                return False
            try:
                manager._applying = True
                manager._apply(watched)
            except RuntimeError:
                # Abaikan widget yang sedang dihancurkan oleh Qt.
                pass
            finally:
                try:
                    manager._applying = False
                except RuntimeError:
                    pass
        return False


_ROUTER_ATTRIBUTE = "_kargo_form_input_style_event_router"


def _router_input_styles_global(app):
    """Ambil atau buat router global; hanya satu per QApplication."""
    router = getattr(app, _ROUTER_ATTRIBUTE, None)
    if router is not None:
        try:
            if router._app is app:
                return router
        except RuntimeError:
            pass

    router = _FormInputStyleEventRouter(app)
    setattr(app, _ROUTER_ATTRIBUTE, router)
    return router


def terapkan_style_input_global(root, is_dark=None):
    """Daftarkan modul/dialog; aman dipanggil ulang saat pergantian tema."""
    manager = getattr(root, "_global_form_input_styles", None)
    if manager is None:
        manager = _FormInputStyles(root)
        root._global_form_input_styles = manager

    app = QApplication.instance()
    if app is not None:
        router = _router_input_styles_global(app)
        if id(manager) not in router._managers:
            router.register(manager)

    manager.refresh(is_dark)