# themes/modules/invoice.py
from __future__ import annotations

from typing import Dict

from themes.colors import get_theme_colors
from utils.typography import get_master_font


def _warna_tema(is_dark: bool, gelap: str, terang: str) -> str:
    """Pilih warna khusus modul yang memang berbeda antara tema gelap/terang."""
    return gelap if is_dark else terang


def get_invoice_dialog_styles(size_total: int) -> Dict[str, str]:
    """Menghasilkan QSS khusus dialog pengaturan kolom Invoice."""
    return {
        "title": f"""
            font-size:{size_total}px;
            font-weight:bold;
            font-family:'{get_master_font()}';
        """,
    }


def get_invoice_styles(
    is_dark: bool,
    size_title: int,
    size_base: int,
    size_input: int,
    size_total: int,
) -> Dict[str, str]:
    """Menghasilkan seluruh style UI Invoice berdasarkan tema dan zoom."""
    ui = get_theme_colors(is_dark)["ui"]

    history_qss = f"""
        QTableWidget {{
            background:{ui["table_background"]};
            alternate-background:{ui["table_alternate_background"]};
            color:{ui["table_text"]};
            gridline-color:{ui["table_grid"]};
            font-size:{size_base}px;
            font-family:'{get_master_font()}';
        }}
        QHeaderView::section {{
            background:{ui["table_header_background"]};
            color:{_warna_tema(is_dark, "#f8fafc", "#ffffff")};
            border:1px solid {_warna_tema(is_dark, "#334155", "#cbd5e1")};
            font-weight:bold;
            padding:7px;
        }}
        QTableWidget::item:selected {{
            background:{ui["selection_background"]};
            color:{ui["selection_text"]};
        }}
    """

    editor_qss = f"""
        QTableWidget {{
            background:{ui["field_background"]};
            alternate-background:{_warna_tema(is_dark, "#25282e", "#f8fafc")};
            color:{ui["table_text"]};
            gridline-color:{ui["field_border"]};
            font-size:{size_base}px;
            font-family:'{get_master_font()}';
        }}
        QHeaderView::section {{
            background:#2563eb;
            color:white;
            border:1px solid #1d4ed8;
            font-weight:bold;
            padding:7px;
        }}
        QTableWidget::item:selected {{
            background:{_warna_tema(is_dark, "#0ea5e9", "#bfdbfe")};
            color:{_warna_tema(is_dark, "#ffffff", "#0f172a")};
        }}
    """

    button_qss = f"""
        QPushButton {{
            font-size:{size_base}px;
            font-family:'{get_master_font()}';
            font-weight:600;
            padding:7px 12px;
            border-radius:5px;
            background:#e2e8f0;
            color:#0f172a;
            border:1px solid #cbd5e1;
        }}
        QPushButton:hover {{
            background:#cbd5e1;
        }}
        QPushButton:pressed {{
            background:#94a3b8;
        }}
        QPushButton:disabled {{
            background:#e5e7eb;
            color:#94a3b8;
        }}
    """

    return {
        "lbl_title_histori": f"""
            font-size:{size_title}px;
            font-weight:bold;
            font-family:'{get_master_font()}';
            color:{ui["text_primary"]};
        """,
        "lbl_title_editor": f"""
            font-size:{size_title + 1}px;
            font-weight:bold;
            font-family:'{get_master_font()}';
            color:{ui["accent"]};
        """,
        "lbl_subtotal": f"""
            font-size:{size_base}px;
            font-weight:bold;
            font-family:'{get_master_font()}';
            color:{_warna_tema(is_dark, "#e2e8f0", "#334155")};
        """,
        "lbl_total_tagihan": f"""
            font-size:{size_total}px;
            font-weight:bold;
            font-family:'{get_master_font()}';
            color:#dc2626;
            margin-top:4px;
        """,
        "input": f"""
            font-size:{size_input}px;
            font-family:'{get_master_font()}';
            padding:6px;
            background:{ui["field_background"]};
            color:{ui["text_primary"]};
            placeholder-text-color:{ui["placeholder_text"]};
            border:1px solid {ui["field_border"]};
            border-radius:4px;
        """,
        "tabel_histori": history_qss,
        "tabel_editor": editor_qss,
        "button_default": button_qss,
        "button_simpan": (
            button_qss
            + f"""
                QPushButton {{
                    background:#16a34a;
                    color:white;
                    border:none;
                }}
            """
            + f"""
                QPushButton:hover {{
                    background:#15803d;
                }}
            """
            + f"""
                QPushButton:pressed {{
                    background:#166534;
                }}
            """
        ),
        "button_preview": (
            button_qss
            + f"""
                QPushButton {{
                    background:#2563eb;
                    color:white;
                    border:none;
                }}
            """
            + f"""
                QPushButton:hover {{
                    background:#1d4ed8;
                }}
            """
            + f"""
                QPushButton:pressed {{
                    background:#1e40af;
                }}
            """
        ),
        "button_cetak": (
            button_qss
            + f"""
                QPushButton {{
                    background:#f59e0b;
                    color:white;
                    border:none;
                }}
            """
            + f"""
                QPushButton:hover {{
                    background:#d97706;
                }}
            """
            + f"""
                QPushButton:pressed {{
                    background:#b45309;
                }}
            """
        ),
        "button_share": (
            button_qss
            + f"""
                QPushButton {{
                    background:#0ea5e9;
                    color:white;
                    border:none;
                }}
            """
            + f"""
                QPushButton:hover {{
                    background:#0284c7;
                }}
            """
            + f"""
                QPushButton:pressed {{
                    background:#0369a1;
                }}
            """
        ),
        "menu_cetak": f"""
            QMenu {{
                background-color: {ui["field_background"]};
                color: {ui["text_primary"]};
                border: 1px solid {ui["field_border"]};
            }}
            QMenu::item:selected {{
                background-color: #2563eb;
                color: white;
            }}
        """,
    }