from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

ORGANIZATION_NAME = "AplikasiEkspedisi"
APPLICATION_NAME = "PengaturanUI"

DEFAULT_FONT = "Roboto"
DEFAULT_FONT_SIZE = 10
MIN_FONT_SIZE = 8

_FONT_EXTENSIONS = (".ttf", ".otf")
_fonts_sudah_dimuat = False
_family_font_termuat: Tuple[str, ...] = tuple()


def _get_settings_ui() -> QSettings:
    """Membuat akses QSettings UI tanpa menyimpan instance global mutable."""
    return QSettings(
        ORGANIZATION_NAME,
        APPLICATION_NAME,
    )


def _dapatkan_folder_font() -> Optional[Path]:
    """Mencari folder assets/fonts dari modul top-level maupun folder utils."""
    module_dir = Path(__file__).resolve().parent
    kandidat_folder = (
        module_dir / "assets" / "fonts",
        module_dir.parent / "assets" / "fonts",
    )

    for folder in kandidat_folder:
        if folder.is_dir():
            return folder

    return None


def _cari_font_tersedia(
    nama_font: str,
    font_tersedia: Dict[str, str],
) -> Optional[str]:
    """Mengembalikan nama family font kanonis secara case-insensitive."""
    nama_bersih = str(nama_font or "").strip()
    if not nama_bersih:
        return None

    return font_tersedia.get(nama_bersih.casefold())


def get_master_font() -> str:
    settings_ui = _get_settings_ui()
    font_tersimpan = settings_ui.value(
        "font_aplikasi",
        DEFAULT_FONT,
    )

    return (
        str(font_tersimpan or DEFAULT_FONT).strip()
        or DEFAULT_FONT
    )


def perbarui_font_master(nama_font_baru: str) -> None:
    nama_font_baru = (
        str(nama_font_baru or "").strip()
        or DEFAULT_FONT
    )

    settings_ui = _get_settings_ui()
    settings_ui.setValue(
        "font_aplikasi",
        nama_font_baru,
    )
    settings_ui.sync()


def muat_font_aplikasi() -> Tuple[str, ...]:
    """Memuat seluruh font lokal satu kali dan mengembalikan family yang terbaca."""
    global _fonts_sudah_dimuat, _family_font_termuat

    if _fonts_sudah_dimuat:
        return _family_font_termuat

    folder_font = _dapatkan_folder_font()
    if folder_font is None:
        module_dir = Path(__file__).resolve().parent
        folder_diharapkan = module_dir.parent / "assets" / "fonts"
        print(f"❌ Folder font tidak ditemukan: {folder_diharapkan}")
        _fonts_sudah_dimuat = True
        _family_font_termuat = tuple()
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

        print(
            f"✅ {font_path.name} → "
            f"{', '.join(families)}"
        )

    _family_font_termuat = tuple(dict.fromkeys(family_termuat))
    _fonts_sudah_dimuat = True
    return _family_font_termuat


def konfigurasi_font_aplikasi(app: QApplication) -> str:
    """Memuat, memvalidasi, dan menerapkan font utama pada QApplication."""
    if app is None:
        raise ValueError("QApplication tidak boleh None.")

    muat_font_aplikasi()

    daftar_font = {
        family.casefold(): family
        for family in QFontDatabase.families()
    }

    font_diminta = get_master_font()
    font_aktif = _cari_font_tersedia(
        font_diminta,
        daftar_font,
    )

    if font_aktif is None:
        print(f"⚠️ Font '{font_diminta}' tidak tersedia.")
        font_aktif = (
            _cari_font_tersedia(DEFAULT_FONT, daftar_font)
            or str(app.font().family() or "").strip()
            or DEFAULT_FONT
        )

    font_aplikasi = QFont(font_aktif)
    font_aplikasi.setPointSize(DEFAULT_FONT_SIZE)
    font_aplikasi.setWeight(QFont.Weight.Normal)
    font_aplikasi.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias
    )
    app.setFont(font_aplikasi)

    print("====================================")
    print("Font diterapkan:", app.font().family())
    print("====================================")

    return app.font().family()


def get_global_font_sizes(z: int = 0) -> Dict[str, int]:
    try:
        zoom = int(z)
    except (TypeError, ValueError):
        zoom = 0

    return {
        "sz_title": 18,
        "sz_total": max(MIN_FONT_SIZE, 15 + zoom),
        "sz_input": max(MIN_FONT_SIZE, 13 + zoom),
        "sz_base":  max(MIN_FONT_SIZE, 12 + zoom),
        "sz_tag":   max(MIN_FONT_SIZE, 11 + zoom),
        "sz_sm":    max(MIN_FONT_SIZE, 10 + zoom),
    }