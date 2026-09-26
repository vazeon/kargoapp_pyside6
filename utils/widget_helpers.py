# utils/widget_helpers.py
"""Helper widget umum: pemblokiran signal dan refresh style."""

from contextlib import contextmanager
from typing import Any, Iterator

from PySide6.QtWidgets import QWidget


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
