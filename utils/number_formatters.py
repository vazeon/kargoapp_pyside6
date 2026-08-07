# utils/number_formatters.py
"""Helper parsing dan formatting angka dengan gaya Indonesia."""

import re
from decimal import Decimal, InvalidOperation
from numbers import Integral, Real
from typing import Any, Iterable

from PySide6.QtWidgets import QLineEdit

from .widget_helpers import blokir_signal_sementara


NOL = Decimal("0")
_POLA_ANGKA_PERTAMA = re.compile(r"-?\d[\d.,]*")
_POLA_RIBUAN_TITIK = re.compile(r"-?\d{1,3}(?:\.\d{3})+")
_POLA_RIBUAN_TITIK_POSITIF = re.compile(r"\d{1,3}(?:\.\d{3})+")
_POLA_RIBUAN_KOMA_POSITIF = re.compile(r"\d{1,3}(?:,\d{3})+")
_POLA_RUPIAH = re.compile(r"(?i)\brp\.?\s*")
_POLA_BUKAN_ANGKA = re.compile(r"[^0-9,.\-]")


def _ambil_digit(nilai: Any) -> str:
    """Ambil seluruh karakter digit dari ``nilai``."""
    return "".join(karakter for karakter in str(nilai) if karakter.isdigit())


def _format_integer_indonesia(angka: int) -> str:
    """Format integer dengan pemisah ribuan titik."""
    return f"{angka:,}".replace(",", ".")


def _normalisasi_angka_pertama(angka: str) -> str:
    """Normalisasi token angka seperti perilaku ``ambil_angka_dari_teks``."""
    if "." in angka and "," in angka:
        return angka.replace(".", "").replace(",", ".")
    if "," in angka:
        return angka.replace(",", ".")
    if "." in angka and _POLA_RIBUAN_TITIK.fullmatch(angka):
        return angka.replace(".", "")
    return angka


def _normalisasi_teks_angka(nilai: Any) -> str:
    """Normalisasi teks angka Indonesia/internasional untuk Decimal."""
    teks = _POLA_RUPIAH.sub("", str(nilai).strip())
    teks = _POLA_BUKAN_ANGKA.sub("", teks)

    if teks in {"", "-", ".", ","}:
        return ""

    negatif = teks.startswith("-")
    teks = teks.lstrip("-")

    if "." in teks and "," in teks:
        if teks.rfind(",") > teks.rfind("."):
            teks = teks.replace(".", "").replace(",", ".")
        else:
            teks = teks.replace(",", "")
    elif "," in teks:
        teks = (
            teks.replace(",", "")
            if _POLA_RIBUAN_KOMA_POSITIF.fullmatch(teks)
            else teks.replace(",", ".")
        )
    elif "." in teks and _POLA_RIBUAN_TITIK_POSITIF.fullmatch(teks):
        teks = teks.replace(".", "")

    return f"-{teks}" if negatif else teks


def format_ke_rupiah(nilai: Any) -> str:
    """Format nilai sebagai rupiah bulat, mis. ``1500000 -> '1.500.000'``."""
    if nilai is None or nilai == "":
        return ""

    negatif = False
    if isinstance(nilai, bool):
        angka = int(nilai)
    elif isinstance(nilai, (Integral, Real)):
        angka = int(nilai)
        negatif = angka < 0
        angka = abs(angka)
    else:
        teks = str(nilai).strip()
        if not teks:
            return ""
        negatif = teks.startswith("-")
        angka_saja = _ambil_digit(teks)
        if not angka_saja:
            return ""
        angka = int(angka_saja)

    hasil = _format_integer_indonesia(angka)
    return f"-{hasil}" if negatif and angka != 0 else hasil


def format_input_ribuan_gaya_indonesia(edit_widget: QLineEdit) -> None:
    """Format otomatis isi QLineEdit sebagai ribuan Indonesia dan jaga kursor."""
    text = edit_widget.text()
    angka_saja = _ambil_digit(text)

    if not angka_saja:
        with blokir_signal_sementara(edit_widget):
            edit_widget.clear()
        return

    text_baru = format_ke_rupiah(angka_saja)
    pos_lama = edit_widget.cursorPosition()

    with blokir_signal_sementara(edit_widget):
        edit_widget.setText(text_baru)
        panjang_baru = len(text_baru)
        pos_baru = pos_lama + panjang_baru - len(text)
        edit_widget.setCursorPosition(max(0, min(pos_baru, panjang_baru)))


def rupiah_to_int(rupiah_str: Any) -> int:
    """Ubah nilai rupiah Indonesia menjadi integer murni."""
    if rupiah_str is None or rupiah_str == "":
        return 0

    if isinstance(rupiah_str, bool):
        return int(rupiah_str)
    if isinstance(rupiah_str, (Integral, Real)):
        return int(rupiah_str)

    teks = str(rupiah_str).strip()
    if not teks:
        return 0

    negatif = teks.startswith("-")
    angka_saja = _ambil_digit(teks)
    if not angka_saja:
        return 0

    hasil = int(angka_saja)
    return -hasil if negatif and hasil != 0 else hasil


def ambil_angka_dari_teks(nilai: Any) -> Decimal:
    """Ambil angka pertama dari teks, mis. ``'1,5 KARUNG' -> Decimal('1.5')``."""
    if nilai is None:
        return NOL

    teks = str(nilai).strip()
    if not teks:
        return NOL

    cocok = _POLA_ANGKA_PERTAMA.search(teks)
    if not cocok:
        return NOL

    try:
        return Decimal(_normalisasi_angka_pertama(cocok.group(0)))
    except InvalidOperation:
        return NOL


def jumlahkan_angka_dari_teks(daftar_nilai: Iterable[Any]) -> Decimal:
    """Jumlahkan angka pertama dari setiap elemen iterable."""
    return sum((ambil_angka_dari_teks(nilai) for nilai in daftar_nilai), NOL)


def format_decimal_indonesia(nilai: Any) -> str:
    """Format angka Decimal ke gaya Indonesia tanpa nol desimal berlebih."""
    try:
        angka = Decimal(str(nilai))
    except (InvalidOperation, TypeError, ValueError):
        return "-"

    if not angka.is_finite():
        return "-"
    if angka == angka.to_integral_value():
        return _format_integer_indonesia(int(angka))

    bagian_bulat, bagian_desimal = format(angka.normalize(), "f").split(".", 1)
    bulat_terformat = _format_integer_indonesia(int(bagian_bulat))
    bagian_desimal = bagian_desimal.rstrip("0")
    return bulat_terformat if not bagian_desimal else f"{bulat_terformat},{bagian_desimal}"


def angka_indonesia_to_decimal(nilai: Any) -> Decimal:
    """Ubah angka biasa atau teks Indonesia/internasional menjadi Decimal."""
    if nilai is None:
        return NOL

    if isinstance(nilai, Decimal):
        return nilai if nilai.is_finite() else NOL
    if isinstance(nilai, bool):
        return Decimal(int(nilai))
    if isinstance(nilai, Integral):
        return Decimal(int(nilai))

    if isinstance(nilai, Real):
        try:
            hasil = Decimal(str(nilai))
            return hasil if hasil.is_finite() else NOL
        except (InvalidOperation, TypeError, ValueError):
            return NOL

    teks = str(nilai).strip()
    if not teks:
        return NOL

    teks = _normalisasi_teks_angka(teks)
    if not teks:
        return NOL

    try:
        hasil = Decimal(teks)
    except (InvalidOperation, TypeError, ValueError):
        return NOL

    return hasil if hasil.is_finite() else NOL


def format_angka_indonesia(
    nilai: Any,
    maksimum_desimal: int = 2,
    kosong_jika_nol: bool = False,
    nilai_kosong: str = "",
) -> str:
    """Format berat, CBM, atau nilai desimal lain dengan gaya Indonesia."""
    if nilai is None or (isinstance(nilai, str) and not nilai.strip()):
        return str(nilai_kosong)

    try:
        jumlah_desimal = max(0, int(maksimum_desimal))
    except (TypeError, ValueError):
        jumlah_desimal = 2

    angka = angka_indonesia_to_decimal(nilai)
    if kosong_jika_nol and angka == 0:
        return str(nilai_kosong)

    pola_desimal = Decimal("1") if jumlah_desimal == 0 else Decimal("1." + "0" * jumlah_desimal)
    return format_decimal_indonesia(angka.quantize(pola_desimal))