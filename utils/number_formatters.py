# utils/number_formatters.py
import re
from decimal import Decimal, InvalidOperation
from typing import Iterable, Any
from numbers import Integral, Real

from PySide6.QtWidgets import QLineEdit

from .widget_helpers import blokir_signal_sementara


def _ambil_digit(nilai: Any) -> str:
    """
    Mengambil seluruh karakter digit dari suatu nilai.
    """
    return "".join(
        karakter
        for karakter in str(nilai)
        if karakter.isdigit()
    )


def format_ke_rupiah(nilai: Any) -> str:
    """
    Mengubah angka atau string biasa menjadi format ribuan
    Indonesia dengan pemisah titik.

    Contoh:
        1500000  -> "1.500.000"
        -1500000 -> "-1.500.000"
        "1500000" -> "1.500.000"

    Nilai rupiah diperlakukan sebagai bilangan bulat
    tanpa pecahan.
    """
    if nilai is None or nilai == "":
        return ""

    negatif = False

    if isinstance(nilai, bool):
        angka = int(nilai)

    elif isinstance(nilai, Integral):
        angka = int(nilai)
        negatif = angka < 0
        angka = abs(angka)

    elif isinstance(nilai, Real):
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

    hasil = f"{angka:,}".replace(",", ".")

    if negatif and angka != 0:
        return f"-{hasil}"

    return hasil


def format_input_ribuan_gaya_indonesia(
    edit_widget: QLineEdit,
) -> None:
    """
    Slot atau fungsi global yang dapat dipasangkan pada signal
    textChanged milik QLineEdit.

    Fungsi menambahkan pemisah ribuan berupa titik dan menjaga
    posisi kursor agar tetap sesuai ketika pengguna mengetik.
    """
    text = edit_widget.text()
    angka_saja = _ambil_digit(text)

    if not angka_saja:
        with blokir_signal_sementara(edit_widget):
            edit_widget.clear()

        return

    text_baru = format_ke_rupiah(angka_saja)

    pos_lama = edit_widget.cursorPosition()
    panjang_lama = len(text)

    with blokir_signal_sementara(edit_widget):
        edit_widget.setText(text_baru)

        panjang_baru = len(text_baru)

        pos_baru = (
            pos_lama
            + panjang_baru
            - panjang_lama
        )

        pos_baru = max(
            0,
            min(
                pos_baru,
                panjang_baru,
            ),
        )

        edit_widget.setCursorPosition(pos_baru)


def rupiah_to_int(
    rupiah_str: Any,
) -> int:
    """
    Mengubah string berformat rupiah Indonesia menjadi
    integer murni untuk penyimpanan ke database atau SQL.

    Contoh:
        "1.500.000"  -> 1500000
        "-1.500.000" -> -1500000
    """
    if rupiah_str is None or rupiah_str == "":
        return 0

    if isinstance(rupiah_str, bool):
        return int(rupiah_str)

    if isinstance(rupiah_str, Integral):
        return int(rupiah_str)

    if isinstance(rupiah_str, Real):
        return int(rupiah_str)

    teks = str(rupiah_str).strip()

    if not teks:
        return 0

    negatif = teks.startswith("-")
    angka_saja = _ambil_digit(teks)

    if not angka_saja:
        return 0

    hasil = int(angka_saja)

    if negatif and hasil != 0:
        return -hasil

    return hasil


def ambil_angka_dari_teks(nilai: Any) -> Decimal:
    """
    Mengambil angka pertama dari teks.

    Contoh:
        "2 DUS"       -> 2
        "4 PALET"     -> 4
        "1,5 KARUNG"  -> 1.5
        "ABC"         -> 0
    """

    if nilai is None:
        return Decimal("0")

    teks = str(nilai).strip()

    if not teks:
        return Decimal("0")

    cocok = re.search(
        r"-?\d[\d.,]*",
        teks,
    )

    if not cocok:
        return Decimal("0")

    angka = cocok.group(0)

    if "." in angka and "," in angka:
        angka = (
            angka
            .replace(".", "")
            .replace(",", ".")
        )

    elif "," in angka:
        angka = angka.replace(",", ".")

    elif "." in angka:
        if re.fullmatch(
            r"-?\d{1,3}(?:\.\d{3})+",
            angka,
        ):
            angka = angka.replace(".", "")

    try:
        return Decimal(angka)

    except InvalidOperation:
        return Decimal("0")


def jumlahkan_angka_dari_teks(
    daftar_nilai: Iterable[Any],
) -> Decimal:
    """
    Menjumlahkan angka yang terdapat dalam teks.

    Contoh:
        [
            "2 DUS",
            "4 PALET",
            "3 KARUNG"
        ]

        hasil:
            9
    """

    total = Decimal("0")

    for nilai in daftar_nilai:
        total += ambil_angka_dari_teks(nilai)

    return total


def format_decimal_indonesia(
    nilai: Any,
) -> str:
    """
    Memformat angka desimal ke format Indonesia.

    Contoh:
        1500     -> "1.500"
        1500.5   -> "1.500,5"
        1500.50  -> "1.500,5"
    """
    try:
        angka = Decimal(
            str(nilai)
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return "-"

    if not angka.is_finite():
        return "-"

    if angka == angka.to_integral_value():
        return (
            f"{int(angka):,}"
            .replace(",", ".")
        )

    hasil = format(
        angka.normalize(),
        "f",
    )

    bagian_bulat, bagian_desimal = (
        hasil.split(".", 1)
    )

    bulat_terformat = (
        f"{int(bagian_bulat):,}"
        .replace(",", ".")
    )

    bagian_desimal = (
        bagian_desimal.rstrip("0")
    )

    if not bagian_desimal:
        return bulat_terformat

    return (
        f"{bulat_terformat},"
        f"{bagian_desimal}"
    )


def angka_indonesia_to_decimal(
    nilai: Any,
) -> Decimal:
    """
    Mengubah angka atau teks format Indonesia menjadi Decimal.

    Contoh:
        1500          -> Decimal("1500")
        1500.5        -> Decimal("1500.5")
        "1.500"       -> Decimal("1500")
        "1.500,75"    -> Decimal("1500.75")
        "12,5"        -> Decimal("12.5")
        "Rp 1.500"    -> Decimal("1500")
    """
    if nilai is None:
        return Decimal("0")

    if isinstance(nilai, Decimal):
        if nilai.is_finite():
            return nilai

        return Decimal("0")

    if isinstance(nilai, bool):
        return Decimal(int(nilai))

    if isinstance(nilai, Integral):
        return Decimal(int(nilai))

    if isinstance(nilai, Real):
        try:
            hasil = Decimal(str(nilai))

            if hasil.is_finite():
                return hasil

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            pass

        return Decimal("0")

    teks = str(nilai).strip()

    if not teks:
        return Decimal("0")

    teks = re.sub(
        r"(?i)\brp\.?\s*",
        "",
        teks,
    )

    teks = re.sub(
        r"[^0-9,.\-]",
        "",
        teks,
    )

    if teks in {
        "",
        "-",
        ".",
        ",",
    }:
        return Decimal("0")

    negatif = teks.startswith("-")
    teks = teks.lstrip("-")

    if "." in teks and "," in teks:
        if teks.rfind(",") > teks.rfind("."):
            # Format Indonesia:
            # 1.500,75 -> 1500.75
            teks = (
                teks
                .replace(".", "")
                .replace(",", ".")
            )

        else:
            # Format internasional:
            # 1,500.75 -> 1500.75
            teks = teks.replace(",", "")

    elif "," in teks:
        if re.fullmatch(
            r"\d{1,3}(?:,\d{3})+",
            teks,
        ):
            # 1,500 -> 1500
            teks = teks.replace(",", "")

        else:
            # 12,5 -> 12.5
            teks = teks.replace(",", ".")

    elif "." in teks:
        if re.fullmatch(
            r"\d{1,3}(?:\.\d{3})+",
            teks,
        ):
            # 1.500 -> 1500
            teks = teks.replace(".", "")

    if negatif:
        teks = f"-{teks}"

    try:
        hasil = Decimal(teks)

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return Decimal("0")

    if not hasil.is_finite():
        return Decimal("0")

    return hasil


def format_angka_indonesia(
    nilai: Any,
    maksimum_desimal: int = 2,
    kosong_jika_nol: bool = False,
    nilai_kosong: str = "",
) -> str:
    """
    Memformat angka biasa atau angka Indonesia.

    Digunakan untuk berat, CBM, dan nilai desimal lain.

    Contoh:
        1500                -> "1.500"
        1500.5              -> "1.500,5"
        "1.500,75"          -> "1.500,75"
        0, kosong_jika_nol=True, nilai_kosong=""  -> ""
        0, kosong_jika_nol=True, nilai_kosong="-" -> "-"
    """
    if nilai is None:
        return str(nilai_kosong)

    if isinstance(nilai, str) and not nilai.strip():
        return str(nilai_kosong)

    try:
        jumlah_desimal = max(
            0,
            int(maksimum_desimal),
        )

    except (
        TypeError,
        ValueError,
    ):
        jumlah_desimal = 2

    angka = angka_indonesia_to_decimal(
        nilai
    )

    if kosong_jika_nol and angka == 0:
        return str(nilai_kosong)

    if jumlah_desimal == 0:
        angka = angka.quantize(
            Decimal("1")
        )

    else:
        pola_desimal = Decimal(
            "1." + ("0" * jumlah_desimal)
        )

        angka = angka.quantize(
            pola_desimal
        )

    return format_decimal_indonesia(
        angka
    )
