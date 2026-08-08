# themes/modules/buku_gudang.py
from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtGui import QColor, QPalette

from themes.palette import get_theme_palette
from utils.typography import get_master_font


def _warna_tema(is_dark: bool, gelap: str, terang: str) -> str:
    """Pilih warna tanpa menjauhkan kode warna dari blok style pemakainya."""
    return gelap if is_dark else terang


def _warna_placeholder(is_dark: bool) -> str:
    """Ambil warna placeholder langsung dari themes/palette.py."""
    palette = get_theme_palette(is_dark)
    return palette.color(QPalette.ColorRole.PlaceholderText).name()


DIALOG_PILIH_PENAGIH_STYLE = f"""
    font-size: 13px;
    font-family: '{get_master_font()}';
"""

DIALOG_PILIH_PENAGIH_INPUT_STYLE = f"""
    padding: 5px;
    border-radius: 4px;
    border: 1px solid #cbd5e1;
"""

DIALOG_PILIH_PENAGIH_BUTTON_PRIMARY_STYLE = f"""
    QPushButton {{
        background-color: #3b82f6;
        color: white;
        font-weight: bold;
        padding: 6px;
        border-radius: 4px;
        border: none;
    }}
    QPushButton:hover {{
        background-color: #2563eb;
    }}
    QPushButton:pressed {{
        background-color: #1d4ed8;
    }}
"""

DIALOG_PILIH_PENAGIH_BUTTON_DANGER_STYLE = f"""
    QPushButton {{
        background-color: #ef4444;
        color: white;
        font-weight: bold;
        padding: 6px;
        border-radius: 4px;
        border: none;
    }}
    QPushButton:hover {{
        background-color: #dc2626;
    }}
    QPushButton:pressed {{
        background-color: #b91c1c;
    }}
"""

# --- TOMBOL UTAMA & AKSI BUKU GUDANG ---
BUKU_GUDANG_BUTTON_INVOICE_STYLE = f"""
    QPushButton {{
        background-color: #3b82f6;
        color: white;
        font-weight: bold;
        padding: 6px 15px;
        border-radius: 4px;
        border: none;
    }}
    QPushButton:hover {{
        background-color: #2563eb;
    }}
    QPushButton:pressed {{
        background-color: #1d4ed8;
    }}
"""

BUKU_GUDANG_BUTTON_SAVE_STYLE = f"""
    QPushButton {{
        background-color: #10b981;
        color: white;
        font-weight: bold;
        padding: 6px 15px;
        border-radius: 4px;
        border: none;
    }}
    QPushButton:hover {{
        background-color: #059669;
    }}
    QPushButton:pressed {{
        background-color: #047857;
    }}
"""

BUKU_GUDANG_BUTTON_CANCEL_STYLE = f"""
    QPushButton {{
        background-color: #ef4444;
        color: white;
        font-weight: bold;
        padding: 6px 15px;
        border-radius: 4px;
        border: none;
    }}
    QPushButton:hover {{
        background-color: #dc2626;
    }}
    QPushButton:pressed {{
        background-color: #b91c1c;
    }}
"""


def get_dialog_pilih_penagih_styles() -> Dict[str, str]:
    """Mengembalikan style dialog pemilihan pihak tertagih."""
    return {
        "dialog": DIALOG_PILIH_PENAGIH_STYLE,
        "input": DIALOG_PILIH_PENAGIH_INPUT_STYLE,
        "btn_lanjut": DIALOG_PILIH_PENAGIH_BUTTON_PRIMARY_STYLE,
        "btn_batal": DIALOG_PILIH_PENAGIH_BUTTON_DANGER_STYLE,
    }


def get_buku_gudang_action_styles() -> Dict[str, str]:
    """Mengembalikan style tombol aksi tetap pada header Buku Gudang."""
    return {
        "btn_buat_invoice": BUKU_GUDANG_BUTTON_INVOICE_STYLE,
        "btn_simpan_inv": BUKU_GUDANG_BUTTON_SAVE_STYLE,
        "btn_batal_inv": BUKU_GUDANG_BUTTON_CANCEL_STYLE,
    }


def get_buku_gudang_styles(
    is_dark: bool,
    sz_base: int,
    sz_input: int,
    sz_title: int,
) -> Dict[str, str]:
    """Menghasilkan style dinamis Buku Gudang berdasarkan tema dan zoom."""
    placeholder = _warna_placeholder(is_dark)
    return {
        "lbl_judul": f"""
            color: {_warna_tema(is_dark, "#ffffff", "#1e293b")};
            font: bold {sz_title}px '{get_master_font()}';
            margin-bottom: 2px;
        """,

        "btn_tahun": f"""
            font-size: {sz_input + 4}px;
            font-weight: bold;
            background-color: {_warna_tema(is_dark, "#1d2024", "#ffffff")};
            color: {_warna_tema(is_dark, "#ffffff", "#0f172a")};
            border: 1px solid {_warna_tema(is_dark, "#4c525e", "#cbd5e1")};
            padding: 6px 12px;
            border-radius: 6px;
            font-family: '{get_master_font()}';
        """,

        "txt_cari": f"""
            font-size: {sz_input}px;
            background-color: {_warna_tema(is_dark, "#1d2024", "#ffffff")};
            color: {_warna_tema(is_dark, "#ffffff", "#0f172a")};
            placeholder-text-color: {placeholder};
            border: 1px solid {_warna_tema(is_dark, "#4c525e", "#cbd5e1")};
            padding: 6px;
            border-radius: 4px;
            font-family: '{get_master_font()}';
        """,

        "inline_editor": f"""
            background-color: {_warna_tema(is_dark, "#1d2024", "#ffffff")};
            color: {_warna_tema(is_dark, "#ffffff", "#0f172a")};
            placeholder-text-color: {placeholder};
            padding: 2px;
            border: 2px solid {_warna_tema(is_dark, "#3b82f6", "#2563eb")};
            border-radius: 3px;
            selection-background-color: {_warna_tema(is_dark, "#3b82f6", "#2563eb")};
            selection-color: #ffffff;
        """,

        "tabel": f"""
            QTableWidget {{
                background-color: {_warna_tema(is_dark, "#1a1d24", "#ffffff")};
                alternate-background-color: {_warna_tema(is_dark, "#20242b", "#f1f5f9")};
                color: {_warna_tema(is_dark, "#f8fafc", "#0f172a")};
                gridline-color: {_warna_tema(is_dark, "#334155", "#e2e8f0")};
                font-size: {sz_base}px;
                font-family: '{get_master_font()}';
            }}
            QHeaderView::section {{
                background-color: {_warna_tema(is_dark, "#1e293b", "#243752")};
                color: {_warna_tema(is_dark, "#f8fafc", "#ffffff")};
                border: 1px solid {_warna_tema(is_dark, "#334155", "#cbd5e1")};
                font-size: {sz_base}px;
                font-weight: bold;
                padding: 6px;
                font-family: '{get_master_font()}';
            }}
            QTableWidget::item:selected {{
                background-color: {_warna_tema(is_dark, "#3b82f6", "#2563eb")};
                color: white;
            }}
        """,
    }


def get_buku_gudang_menu_style(font_size: Optional[int] = None) -> str:
    """Menghasilkan style menu Buku Gudang dengan ukuran font opsional."""
    ukuran = f" font-size: {font_size}px;" if font_size is not None else ""
    return f"""
        QMenu {{
            padding: 5px;
            {ukuran} font-family: '{get_master_font()}';
        }}
    """


def get_buku_gudang_status_colors(
    is_dark: bool,
    status: str,
    is_alternate_row: bool = False,
) -> Tuple[Optional[QColor], Optional[QColor]]:
    """Menghasilkan warna baris berdasarkan status pengiriman."""
    normalized = str(status or "").strip().upper()

    if is_dark:
        background_map = {
            "PERJALANAN": "#142d22",
            "SELESAI": "#162545",
        }
        foreground_map = {
            "PERJALANAN": "#a7f3d0",
            "SELESAI": "#bfdbfe",
        }
    else:
        background_map = {
            "PERJALANAN": "#bbf7d0",
            "SELESAI": "#c7d2fe",
        }
        foreground_map = {
            "PERJALANAN": "#14532d",
            "SELESAI": "#1e40af",
        }

    background_hex = background_map.get(normalized)
    foreground_hex = foreground_map.get(normalized)

    if not background_hex or not foreground_hex:
        return None, None

    background = QColor(background_hex)
    foreground = QColor(foreground_hex)

    if is_alternate_row:
        background = (
            background.lighter(115)
            if is_dark
            else background.darker(108)
        )

    return background, foreground