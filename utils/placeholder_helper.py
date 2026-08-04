# utils/placeholder_helper.py
from typing import Optional

from PySide6.QtWidgets import QLineEdit, QTextEdit, QWidget

from .widget_helpers import _refresh_style_widget

_INPUT_PLACEHOLDER = (QLineEdit, QTextEdit)


def _input_kosong(widget: QWidget) -> bool:
    """Mengembalikan ``True`` ketika input tidak memiliki isi bermakna."""
    if isinstance(widget, QLineEdit):
        return not widget.text().strip()

    if isinstance(widget, QTextEdit):
        return not widget.toPlainText().strip()

    return True


def _ubah_property_jika_berbeda(
    widget: QWidget,
    nama: str,
    nilai,
) -> bool:
    """Mengubah dynamic property hanya ketika nilainya benar-benar berbeda."""
    if widget.property(nama) == nilai:
        return False

    widget.setProperty(nama, nilai)
    return True


def setup_placeholder_dinamis(
    widget: QWidget,
    is_dark: bool = False,
) -> None:
    """
    Mengatur dynamic property placeholder pada QLineEdit/QTextEdit.

    Repolish hanya dilakukan ketika property yang dipakai QSS benar-benar
    berubah. Signal dipasang satu kali agar tidak terjadi koneksi ganda.
    """
    if not isinstance(widget, _INPUT_PLACEHOLDER):
        return

    if not widget.placeholderText():
        return

    def update_status_kosong() -> None:
        nilai_kosong = (
            "true" if _input_kosong(widget) else "false"
        )

        if _ubah_property_jika_berbeda(
            widget,
            "is_empty",
            nilai_kosong,
        ):
            _refresh_style_widget(widget)

    ada_perubahan = False
    ada_perubahan |= _ubah_property_jika_berbeda(
        widget,
        "custom_italic",
        "false",
    )
    ada_perubahan |= _ubah_property_jika_berbeda(
        widget,
        "is_dark",
        "true" if bool(is_dark) else "false",
    )
    ada_perubahan |= _ubah_property_jika_berbeda(
        widget,
        "is_empty",
        "true" if _input_kosong(widget) else "false",
    )

    if not bool(getattr(widget, "_placeholder_hooked", False)):
        widget._placeholder_hooked = True

        if isinstance(widget, QLineEdit):
            widget.textChanged.connect(
                lambda _teks: update_status_kosong()
            )
        else:
            widget.textChanged.connect(update_status_kosong)

    if ada_perubahan:
        _refresh_style_widget(widget)


def terap_semua_placeholder_dinamis(
    container_widget: QWidget,
    is_dark: Optional[bool] = None,
) -> None:
    """
    Menerapkan placeholder dinamis pada seluruh input di dalam container.

    ``is_dark`` dapat diberikan secara eksplisit. Jika tidak diberikan,
    helper mencoba membaca atribut ``current_theme`` milik container agar
    pemanggilan lama tetap kompatibel dengan light dan dark mode.
    """
    if is_dark is None:
        tema_aktif = str(
            getattr(container_widget, "current_theme", "light")
        ).strip().lower()
        is_dark = tema_aktif == "dark"

    for widget in container_widget.findChildren(QWidget):
        if isinstance(widget, _INPUT_PLACEHOLDER):
            setup_placeholder_dinamis(
                widget,
                is_dark=bool(is_dark),
            )
