# utils/date_ind_format.py
from datetime import date, datetime
from typing import Any, Optional

from PySide6.QtWidgets import QLineEdit

from .widget_helpers import blokir_signal_sementara

_FORMAT_TANGGAL = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y")


def _ambil_digit(nilai: Any) -> str:
    """Mengambil karakter digit dari suatu nilai."""
    return "".join(karakter for karakter in str(nilai) if karakter.isdigit())


def _parse_tanggal(nilai: Any) -> Optional[date]:
    """Mengubah nilai tanggal umum menjadi objek ``date`` jika valid."""
    if isinstance(nilai, datetime):
        return nilai.date()
    if isinstance(nilai, date):
        return nilai

    if hasattr(nilai, "isValid") and hasattr(nilai, "toString"):
        try:
            if nilai.isValid():
                return datetime.strptime(nilai.toString("yyyy-MM-dd"), "%Y-%m-%d").date()
        except (AttributeError, TypeError, ValueError):
            pass

    teks = str(nilai or "").strip()
    if not teks:
        return None

    teks = teks.split("T", 1)[0].split(" ", 1)[0].strip()
    for pola in _FORMAT_TANGGAL:
        try:
            return datetime.strptime(teks, pola).date()
        except ValueError:
            continue
    return None


def _format_tanggal(nilai: Any, pola: str) -> str:
    if nilai is None or str(nilai).strip() == "":
        return ""
    tanggal = _parse_tanggal(nilai)
    return tanggal.strftime(pola) if tanggal is not None else str(nilai)


def format_input_tanggal(edit_widget: QLineEdit) -> None:
    """Memformat input angka pada ``QLineEdit`` menjadi DD/MM/YYYY."""
    teks_lama = edit_widget.text()
    angka_saja = _ambil_digit(teks_lama)[:8]

    if not angka_saja:
        with blokir_signal_sementara(edit_widget):
            edit_widget.clear()
        return

    bagian = [angka_saja[:2]]
    if len(angka_saja) > 2:
        bagian.append(angka_saja[2:4])
    if len(angka_saja) > 4:
        bagian.append(angka_saja[4:8])

    teks_baru = "/".join(bagian)
    if teks_baru == teks_lama:
        return

    posisi_lama = edit_widget.cursorPosition()
    panjang_lama = len(teks_lama)
    panjang_baru = len(teks_baru)
    posisi_baru = posisi_lama + panjang_baru - panjang_lama
    if panjang_baru < panjang_lama and teks_lama.endswith("/"):
        posisi_baru -= 1

    with blokir_signal_sementara(edit_widget):
        edit_widget.setText(teks_baru)
        edit_widget.setCursorPosition(max(0, min(posisi_baru, panjang_baru)))


def format_tanggal_ke_db(tgl_ui: Any) -> str:
    """Mengubah tanggal menjadi format database ``YYYY-MM-DD``."""
    return _format_tanggal(tgl_ui, "%Y-%m-%d")


def format_tanggal_ke_ui(tgl_db: Any) -> str:
    """Mengubah tanggal menjadi format tampilan Indonesia ``DD/MM/YYYY``."""
    return _format_tanggal(tgl_db, "%d/%m/%Y")