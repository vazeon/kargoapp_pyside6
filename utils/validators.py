from typing import Optional

from PySide6.QtCore import QLocale
from PySide6.QtGui import QDoubleValidator, QIntValidator, QValidator
from PySide6.QtWidgets import QWidget


class UppercaseValidator(QValidator):
    """
    Validator global untuk mengubah input teks
    menjadi huruf kapital.
    """

    def validate(
        self,
        string: str,
        pos: int,
    ):
        return (
            QValidator.State.Acceptable,
            string.upper(),
            pos,
        )


def get_integer_validator(
    parent: Optional[QWidget] = None,
    minimum: int = 0,
    maximum: int = 2_147_483_647,
) -> QIntValidator:
    """
    Membuat validator angka bulat.

    Contoh:
        - Qty
        - Jumlah barang
        - Ongkir tanpa pemisah ribuan
    """
    try:
        nilai_minimum = int(minimum)
    except (TypeError, ValueError):
        nilai_minimum = 0

    try:
        nilai_maksimum = int(maximum)
    except (TypeError, ValueError):
        nilai_maksimum = 2_147_483_647

    if nilai_maksimum < nilai_minimum:
        nilai_maksimum = nilai_minimum

    return QIntValidator(
        nilai_minimum,
        nilai_maksimum,
        parent,
    )


def get_decimal_validator(
    parent: Optional[QWidget] = None,
    decimals: int = 2,
    minimum: float = 0.0,
    maximum: float = 999_999_999.99,
) -> QDoubleValidator:
    """
    Membuat validator angka desimal.

    Contoh:
        - Berat
        - Volume
        - CBM
    """
    try:
        jumlah_desimal = max(
            0,
            int(decimals),
        )
    except (TypeError, ValueError):
        jumlah_desimal = 2

    try:
        nilai_minimum = float(minimum)
    except (TypeError, ValueError):
        nilai_minimum = 0.0

    try:
        nilai_maksimum = float(maximum)
    except (TypeError, ValueError):
        nilai_maksimum = 999_999_999.99

    if nilai_maksimum < nilai_minimum:
        nilai_maksimum = nilai_minimum

    validator = QDoubleValidator(
        nilai_minimum,
        nilai_maksimum,
        jumlah_desimal,
        parent,
    )

    validator.setNotation(
        QDoubleValidator.Notation.StandardNotation
    )

    validator.setLocale(
        QLocale(
            QLocale.Language.Indonesian,
            QLocale.Country.Indonesia,
        )
    )

    return validator
