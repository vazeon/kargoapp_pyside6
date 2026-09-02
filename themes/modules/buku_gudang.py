# themes/modules/buku_gudang.py
from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtGui import QColor

from themes.colors import get_theme_colors
from utils.typography import get_master_font


def _warna_tema(is_dark: bool, gelap: str, terang: str) -> str:
    """Pilih warna tanpa menjauhkan kode warna dari blok style pemakainya."""
    return gelap if is_dark else terang


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
        padding: 5px 14px;
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
        padding: 5px 14px;
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
        padding: 5px 14px;
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
    ui = get_theme_colors(is_dark)["ui"]
    ukuran_judul = max(14, sz_title - 2)
    ukuran_filter = max(10, sz_input - 1)
    ukuran_label = max(10, sz_input - 2)
    ukuran_tabel = max(10, sz_base - 1)

    return {
        "lbl_judul": f"""
            color: {_warna_tema(is_dark, "#ffffff", "#1e293b")};
            background-color: transparent;
            border: none;
            font-size: {ukuran_judul}px;
            font-weight: 600;
            font-family: '{get_master_font()}';
            margin: 0px;
            padding: 0px;
        """,

        "btn_tahun": f"""
            QPushButton {{
                font-size: {ukuran_filter}px;
                font-weight: 400;
                background-color: {ui["field_background"]};
                color: {ui["text_primary"]};
                border: 1px solid {ui["field_border"]};
                padding: 0px;
                border-radius: 5px;
                font-family: '{get_master_font()}';
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {ui["field_border"]};
            }}
            QPushButton::menu-indicator {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                right: 4px;
            }}
        """,

        "btn_reset_filter": f"""
            QToolButton {{
                font-size: {ukuran_filter}px;
                font-weight: 400;
                background-color: transparent;
                color: {ui["text_primary"]};
                border: 1px solid transparent;
                padding: 4px 8px;
                border-radius: 5px;
                font-family: '{get_master_font()}';
            }}
            QToolButton:hover {{
                background-color: {ui["field_background"]};
                border: 1px solid {ui["field_border"]};
            }}
        """,

        "txt_cari": f"""
            font-size: {ukuran_filter}px;
            background-color: {ui["field_background"]};
            color: {ui["text_primary"]};
            placeholder-text-color: {ui["placeholder_text"]};
            border: 1px solid {ui["field_border"]};
            padding: 5px 9px;
            border-radius: 5px;
            font-family: '{get_master_font()}';
        """,

        "inline_editor": f"""
            background-color: {ui["field_background"]};
            color: {ui["text_primary"]};
            placeholder-text-color: {ui["placeholder_text"]};
            padding: 2px;
            border: 2px solid {ui["primary"]};
            border-radius: 3px;
            selection-background-color: {ui["selection_background"]};
            selection-color: {ui["selection_text"]};
        """,

        "tabel": f"""
            QTableWidget {{
                background-color: {ui["table_background"]};
                alternate-background-color: {ui["table_alternate_background"]};
                color: {ui["table_text"]};
                gridline-color: {ui["table_grid"]};
                font-size: {ukuran_tabel}px;
                font-family: '{get_master_font()}';
            }}
            QHeaderView::section {{
                background-color: {ui["table_header_background"]};
                color: {_warna_tema(is_dark, "#f8fafc", "#ffffff")};
                border: 1px solid {_warna_tema(is_dark, ui["table_grid"], ui["field_border"])};
                font-size: {ukuran_tabel}px;
                font-weight: 600;
                padding: 4px 6px;
                font-family: '{get_master_font()}';
            }}
            QTableWidget::item:selected {{
                background-color: {ui["selection_background"]};
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
    """Menghasilkan warna highlight baris berdasarkan status resi/penagihan."""
    state = str(status or "").strip().upper()

    if "|" in state:
        status_penagihan, status_resi = state.split("|", 1)
    else:
        status_penagihan, status_resi = "", state

    # Prioritas visual: MACET > LUNAS/SELESAI > PERJALANAN.
    if status_penagihan == "MACET":
        status_warna = "MACET"
    elif status_penagihan == "LUNAS" or status_resi == "SELESAI":
        status_warna = "SELESAI"
    elif status_resi == "PERJALANAN":
        status_warna = "PERJALANAN"
    else:
        return None, None

    colors = get_theme_colors(is_dark)
    warna = colors["buku_gudang"]["status"][status_warna]
    background_hex = (
        warna["row_alternate_background"] if is_alternate_row else warna["row_background"]
    )

    return QColor(background_hex), QColor(warna["text_color"])