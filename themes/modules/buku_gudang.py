# themes/modules/buku_gudang.py
from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtGui import QColor

from utils.typography import get_master_font

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
    if is_dark:
        title_color = "#ffffff"
        input_bg = "#1d2024"
        input_text = "#ffffff"
        input_border = "#4c525e"
        table_bg = "#1a1d24"
        table_alt = "#20242b"
        table_text = "#f8fafc"
        table_grid = "#334155"
        header_bg = "#1e293b"
        header_text = "#f8fafc"
        header_border = "#334155"
        selection_bg = "#3b82f6"
    else:
        title_color = "#1e293b"
        input_bg = "#ffffff"
        input_text = "#0f172a"
        input_border = "#cbd5e1"
        table_bg = "#ffffff"
        table_alt = "#f1f5f9"
        table_text = "#0f172a"
        table_grid = "#e2e8f0"
        header_bg = "#243752"
        header_text = "#ffffff"
        header_border = "#cbd5e1"
        selection_bg = "#2563eb"

    return {
        "lbl_judul": f"""
            color: {title_color};
            font: bold {sz_title}px '{get_master_font()}';
            margin-bottom: 2px;
        """,

        "btn_tahun": f"""
            font-size: {sz_input + 4}px;
            font-weight: bold;
            background-color: {input_bg};
            color: {input_text};
            border: 1px solid {input_border};
            padding: 6px 12px;
            border-radius: 6px;
            font-family: '{get_master_font()}';
        """,

        "txt_cari": f"""
            font-size: {sz_input}px;
            background-color: {input_bg};
            color: {input_text};
            border: 1px solid {input_border};
            padding: 6px;
            border-radius: 4px;
            font-family: '{get_master_font()}';
        """,

        "inline_editor": f"""
            background-color: {input_bg};
            color: {input_text};
            padding: 2px;
            border: 2px solid {selection_bg};
            border-radius: 3px;
            selection-background-color: {selection_bg};
            selection-color: #ffffff;
        """,

        "tabel": f"""
            QTableWidget {{
                background-color: {table_bg};
                alternate-background-color: {table_alt};
                color: {table_text};
                gridline-color: {table_grid};
                font-size: {sz_base}px;
                font-family: '{get_master_font()}';
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_text};
                border: 1px solid {header_border};
                font-size: {sz_base}px;
                font-weight: bold;
                padding: 6px;
                font-family: '{get_master_font()}';
            }}
            QTableWidget::item:selected {{
                background-color: {selection_bg};
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
