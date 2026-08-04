# utils/date_ind_format.py
from datetime import date, datetime
from typing import Any, Optional

from PySide6.QtWidgets import QLineEdit

from .widget_helpers import blokir_signal_sementara


def _ambil_digit(nilai: Any) -> str:
    """Mengambil karakter digit dari suatu nilai."""
    return "".join(
        karakter
        for karakter in str(nilai)
        if karakter.isdigit()
    )


def _parse_tanggal(nilai: Any) -> Optional[date]:
    """Mengubah nilai tanggal umum menjadi objek ``date`` jika valid."""
    if isinstance(nilai, datetime):
        return nilai.date()

    if isinstance(nilai, date):
        return nilai

    # Mendukung QDate tanpa menjadikan modul ini bergantung langsung pada QDate.
    if hasattr(nilai, "isValid") and hasattr(nilai, "toString"):
        try:
            if nilai.isValid():
                teks_qdate = nilai.toString("yyyy-MM-dd")
                return datetime.strptime(teks_qdate, "%Y-%m-%d").date()
        except (AttributeError, TypeError, ValueError):
            pass

    teks = str(nilai or "").strip()
    if not teks:
        return None

    # Buang komponen waktu dari format SQL/ISO.
    teks_tanggal = teks.split("T", 1)[0].split(" ", 1)[0].strip()

    for pola in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(teks_tanggal, pola).date()
        except ValueError:
            continue

    return None


def format_input_tanggal(edit_widget: QLineEdit) -> None:
    """
    Memformat input angka pada ``QLineEdit`` menjadi DD/MM/YYYY.

    Fungsi ini aman dipasang pada signal ``textChanged`` karena signal
    diblokir sementara ketika teks widget diperbarui.
    """
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

    with blokir_signal_sementara(edit_widget):
        edit_widget.setText(teks_baru)
        panjang_baru = len(teks_baru)
        posisi_baru = posisi_lama + panjang_baru - panjang_lama

        if panjang_baru < panjang_lama and teks_lama.endswith("/"):
            posisi_baru -= 1

        edit_widget.setCursorPosition(
            max(0, min(posisi_baru, panjang_baru))
        )


def format_tanggal_ke_db(tgl_ui: Any) -> str:
    """
    Mengubah tanggal menjadi format database ``YYYY-MM-DD``.

    Format yang didukung antara lain DD/MM/YYYY, DD-MM-YYYY,
    YYYY-MM-DD, timestamp SQL, ISO datetime, ``date``, ``datetime``,
    dan ``QDate``. Nilai yang tidak dikenali dikembalikan apa adanya.
    """
    if tgl_ui is None or str(tgl_ui).strip() == "":
        return ""

    tanggal = _parse_tanggal(tgl_ui)
    if tanggal is None:
        return str(tgl_ui)

    return tanggal.strftime("%Y-%m-%d")


def format_tanggal_ke_ui(tgl_db: Any) -> str:
    """
    Mengubah tanggal menjadi format tampilan Indonesia ``DD/MM/YYYY``.

    Format database yang sudah memiliki komponen waktu akan diproses
    dengan aman tanpa menggunakan slicing posisi karakter.
    """
    if tgl_db is None or str(tgl_db).strip() == "":
        return ""

    tanggal = _parse_tanggal(tgl_db)
    if tanggal is None:
        return str(tgl_db)

    return tanggal.strftime("%d/%m/%Y")
