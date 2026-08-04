from typing import Dict

from PySide6.QtCore import QSettings

ORGANIZATION_NAME = "AplikasiEkspedisi"
APPLICATION_NAME = "PengaturanUI"

DEFAULT_FONT = "Roboto"
MIN_FONT_SIZE = 8

settings_ui = QSettings(
    ORGANIZATION_NAME,
    APPLICATION_NAME,
)


def get_master_font() -> str:
    font_tersimpan = settings_ui.value(
        "font_aplikasi",
        DEFAULT_FONT,
    )

    return (
        str(font_tersimpan or DEFAULT_FONT).strip()
        or DEFAULT_FONT
    )

MASTER_FONT = get_master_font()


def perbarui_font_master(nama_font_baru: str) -> None:
    """
    Menyimpan font baru sebagai font utama aplikasi.
    """
    global MASTER_FONT

    nama_font_baru = (
        str(nama_font_baru or "").strip()
        or DEFAULT_FONT
    )

    settings_ui.setValue(
        "font_aplikasi",
        nama_font_baru,
    )
    settings_ui.sync()

    MASTER_FONT = nama_font_baru


def get_global_font_sizes(z: int = 0) -> Dict[str, int]:
    try:
        zoom = int(z)
    except (TypeError, ValueError):
        zoom = 0

    return {
        "sz_title": max(MIN_FONT_SIZE, 22 + zoom),
        "sz_tag": max(MIN_FONT_SIZE, 13 + zoom),
        "sz_sm": max(MIN_FONT_SIZE, 13 + zoom),
        "sz_base": max(MIN_FONT_SIZE, 13 + zoom),
        "sz_input": max(MIN_FONT_SIZE, 13 + zoom),
        "sz_total": max(MIN_FONT_SIZE, 17 + zoom),
    }
