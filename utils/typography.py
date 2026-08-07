# utils/typography.py
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TypeVar

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

ORGANIZATION_NAME = "AplikasiEkspedisi"
APPLICATION_NAME = "PengaturanUI"

DEFAULT_FONT = "Roboto"
DEFAULT_FONT_SIZE_PT = 9.0
DEFAULT_FONT_SIZE = DEFAULT_FONT_SIZE_PT  # Alias kompatibilitas lama.

MIN_FONT_SIZE = 8
MIN_FONT_SIZE_PT = 7.5
REFERENCE_DPI = 96.0
POINTS_PER_INCH = 72.0

_FONT_EXTENSIONS = (".ttf", ".otf")
_FONT_SIZE_PX_PATTERN = re.compile(
    r"(?P<prefix>font-size\s*:\s*)(?P<value>-?\d+(?:\.\d+)?)px\b",
    flags=re.IGNORECASE,
)
_fonts_sudah_dimuat = False
_family_font_termuat: Tuple[str, ...] = ()

T = TypeVar("T")


def _get_settings_ui() -> QSettings:
    """Akses QSettings UI tanpa menyimpan instance global mutable."""
    return QSettings(ORGANIZATION_NAME, APPLICATION_NAME)


def _dapatkan_folder_font() -> Optional[Path]:
    """Cari assets/fonts dari top-level maupun folder utils."""
    module_dir = Path(__file__).resolve().parent
    for folder in (module_dir / "assets" / "fonts", module_dir.parent / "assets" / "fonts"):
        if folder.is_dir():
            return folder
    return None


def _cari_font_tersedia(nama_font: str, font_tersedia: Dict[str, str]) -> Optional[str]:
    """Kembalikan nama family kanonis secara case-insensitive."""
    nama = str(nama_font or "").strip()
    return font_tersedia.get(nama.casefold()) if nama else None


def _angka_float_aman(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _format_angka_css(value: float) -> str:
    angka = round(float(value), 3)
    return str(int(angka)) if angka.is_integer() else f"{angka:.3f}".rstrip("0").rstrip(".")


def px_ke_pt(value: Any, default: float = 0.0) -> float:
    """Ubah logical pixel desain ke point pada referensi 96 DPI."""
    return _angka_float_aman(value, default) * POINTS_PER_INCH / REFERENCE_DPI


def ukuran_font_px_ke_pt(value: Any, default: float = 0.0) -> float:
    """Konversi token font px ke point dengan batas keterbacaan minimum."""
    return max(MIN_FONT_SIZE_PT, px_ke_pt(value, default))


def pt_ke_px(value: Any, default: float = 0.0) -> float:
    """Ubah point ke logical pixel desain pada referensi 96 DPI."""
    return _angka_float_aman(value, default) * REFERENCE_DPI / POINTS_PER_INCH


def konversi_font_qss_ke_point(qss: Any) -> Any:
    """Ubah hanya deklarasi ``font-size: ...px`` menjadi point."""
    if not isinstance(qss, str) or "font-size" not in qss.lower():
        return qss

    def pengganti(match: re.Match[str]) -> str:
        nilai_pt = ukuran_font_px_ke_pt(match.group("value"))
        return f"{match.group('prefix')}{_format_angka_css(nilai_pt)}pt"

    return _FONT_SIZE_PX_PATTERN.sub(pengganti, qss)


def konversi_style_font_ke_point(value: T) -> T:
    """Konversi font-size pada string atau koleksi style secara rekursif."""
    if isinstance(value, str):
        return konversi_font_qss_ke_point(value)  # type: ignore[return-value]
    if isinstance(value, dict):
        return {key: konversi_style_font_ke_point(item) for key, item in value.items()}  # type: ignore[return-value]
    if isinstance(value, list):
        return [konversi_style_font_ke_point(item) for item in value]  # type: ignore[return-value]
    if isinstance(value, tuple):
        return tuple(konversi_style_font_ke_point(item) for item in value)  # type: ignore[return-value]
    return value


def get_master_font() -> str:
    font = _get_settings_ui().value("font_aplikasi", DEFAULT_FONT)
    return str(font or DEFAULT_FONT).strip() or DEFAULT_FONT


def dapatkan_font_aplikasi_aktif() -> str:
    """Ambil family font yang benar-benar sedang dipakai QApplication."""
    app = QApplication.instance()
    if app is not None:
        family = str(app.font().family() or "").strip()
        if family:
            return family
    return get_master_font()


def perbarui_font_master(nama_font_baru: str) -> None:
    nama = str(nama_font_baru or "").strip() or DEFAULT_FONT
    settings = _get_settings_ui()
    settings.setValue("font_aplikasi", nama)
    settings.sync()


def muat_font_aplikasi() -> Tuple[str, ...]:
    """Muat seluruh font lokal sekali dan kembalikan family yang terbaca."""
    global _fonts_sudah_dimuat, _family_font_termuat
    if _fonts_sudah_dimuat:
        return _family_font_termuat

    folder_font = _dapatkan_folder_font()
    if folder_font is None:
        folder_diharapkan = Path(__file__).resolve().parent.parent / "assets" / "fonts"
        print(f"❌ Folder font tidak ditemukan: {folder_diharapkan}")
        _fonts_sudah_dimuat = True
        _family_font_termuat = ()
        return _family_font_termuat

    family_termuat = []
    for font_path in sorted(folder_font.iterdir(), key=lambda path: path.name.lower()):
        if not font_path.is_file() or font_path.suffix.lower() not in _FONT_EXTENSIONS:
            continue

        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id == -1:
            print(f"❌ Font gagal dimuat: {font_path.name}")
            continue

        families = QFontDatabase.applicationFontFamilies(font_id)
        family_termuat.extend(families)
        print(f"✅ {font_path.name} → {', '.join(families)}")

    _family_font_termuat = tuple(dict.fromkeys(family_termuat))
    _fonts_sudah_dimuat = True
    return _family_font_termuat


def konfigurasi_font_aplikasi(app: QApplication) -> str:
    """Muat, validasi, dan terapkan font utama pada QApplication."""
    if app is None:
        raise ValueError("QApplication tidak boleh None.")

    muat_font_aplikasi()
    daftar_font = {family.casefold(): family for family in QFontDatabase.families()}
    font_diminta = get_master_font()
    font_aktif = _cari_font_tersedia(font_diminta, daftar_font)

    if font_aktif is None:
        print(f"⚠️ Font '{font_diminta}' tidak tersedia.")
        font_aktif = (
            _cari_font_tersedia(DEFAULT_FONT, daftar_font)
            or str(app.font().family() or "").strip()
            or DEFAULT_FONT
        )

    font = QFont(font_aktif)
    font.setPointSizeF(DEFAULT_FONT_SIZE_PT)
    font.setWeight(QFont.Weight.Normal)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    print("====================================")
    print("Font diterapkan:", app.font().family())
    print("====================================")
    return app.font().family()


def get_global_font_sizes(z: int = 0) -> Dict[str, int]:
    """Token ukuran desain lama dalam logical pixel untuk kompatibilitas theme."""
    try:
        zoom = int(z)
    except (TypeError, ValueError, OverflowError):
        zoom = 0

    return {
        "sz_title": 18,
        "sz_total": max(MIN_FONT_SIZE, 15 + zoom),
        "sz_input": max(MIN_FONT_SIZE, 13 + zoom),
        "sz_base": max(MIN_FONT_SIZE, 12 + zoom),
        "sz_tag": max(MIN_FONT_SIZE, 11 + zoom),
        "sz_sm": max(MIN_FONT_SIZE, 10 + zoom),
    }


def get_global_font_sizes_pt(z: int = 0) -> Dict[str, float]:
    """Ukuran font kanonis dalam point untuk QFont dan QSS baru."""
    return {key: ukuran_font_px_ke_pt(value) for key, value in get_global_font_sizes(z).items()}