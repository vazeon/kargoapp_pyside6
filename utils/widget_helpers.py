# utils/widget_helpers.py
from contextlib import contextmanager
from typing import Any, Iterator

from PySide6.QtWidgets import QLineEdit, QWidget


@contextmanager
def blokir_signal_sementara(widget: Any) -> Iterator[None]:
    """Memblokir signal widget sementara dan memulihkan status sebelumnya."""
    status_sebelumnya = widget.blockSignals(True)
    try:
        yield
    finally:
        widget.blockSignals(status_sebelumnya)


@contextmanager
def blokir_signal_opsional(widget: Any, aktif: bool = True) -> Iterator[None]:
    """Memblokir signal hanya ketika ``aktif`` bernilai True."""
    if not aktif:
        yield
        return
    with blokir_signal_sementara(widget):
        yield


_blokir_signal_sementara = blokir_signal_sementara
_blokir_signal_opsional = blokir_signal_opsional


def _refresh_style_widget(widget: QWidget) -> None:
    """Meminta Qt mengevaluasi ulang dynamic property pada stylesheet."""
    if widget is None or bool(getattr(widget, "_refresh_style_aktif", False)):
        return

    widget._refresh_style_aktif = True
    try:
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)
        widget.update()
    except RuntimeError:
        return
    finally:
        try:
            widget._refresh_style_aktif = False
        except RuntimeError:
            pass


def paksa_kapital_lineedit(edit_widget: QLineEdit) -> None:
    """Memaksa isi ``QLineEdit`` menjadi huruf kapital tanpa signal berulang."""
    teks_lama = edit_widget.text()
    teks_baru = teks_lama.upper()
    if teks_baru == teks_lama:
        return

    pos_lama = edit_widget.cursorPosition()
    with blokir_signal_sementara(edit_widget):
        edit_widget.setText(teks_baru)
        edit_widget.setCursorPosition(min(pos_lama, len(teks_baru)))