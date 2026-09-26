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
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _owns(self, widget):
        parent = widget
        while parent is not None:
            owner = getattr(parent, "_global_form_input_styles", None)
            if owner is not None:
                return owner is self
            parent = parent.parentWidget()
        return False

    def _apply(self, widget):
        if not self._owns(widget) or not is_input_form(widget):
            return
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
        self._applying = True
        try:
            root = self.parent()
            self._dark = _tema_gelap(root) if is_dark is None else bool(is_dark)
            for widget in (root, *root.findChildren(QWidget)):
                self._apply(widget)
        finally:
            self._applying = False

    def eventFilter(self, watched, event):
        if self._applying:
            return False
        kind = event.type()
        if watched is QApplication.instance() and kind in (
            QEvent.Type.ApplicationPaletteChange, QEvent.Type.StyleChange,
        ):
            self._timer.start(0)
        elif isinstance(watched, INPUT_TYPES) and kind in (
            QEvent.Type.Show, QEvent.Type.ReadOnlyChange,
        ):
            self._applying = True
            try:
                self._apply(watched)
            finally:
                self._applying = False
        return False


def terapkan_style_input_global(root, is_dark=None):
    """Daftarkan modul/dialog; aman dipanggil ulang saat pergantian tema."""
    manager = getattr(root, "_global_form_input_styles", None)
    if manager is None:
        manager = _FormInputStyles(root)
        root._global_form_input_styles = manager
    manager.refresh(is_dark)