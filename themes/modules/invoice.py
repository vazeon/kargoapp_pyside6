# themes/modules/invoice.py
from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QPalette

from themes.palette import get_theme_palette
from utils.typography import get_master_font


def _warna_tema(is_dark: bool, gelap: str, terang: str) -> str:
    """Pilih warna tanpa menjauhkan kode warna dari blok style pemakainya."""
    return gelap if is_dark else terang


def _warna_placeholder(is_dark: bool) -> str:
    """Ambil warna placeholder langsung dari themes/palette.py."""
    palette = get_theme_palette(is_dark)
    return palette.color(QPalette.ColorRole.PlaceholderText).name()


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
    placeholder = _warna_placeholder(is_dark)
    if is_dark:
        history_qss = f"""
            QTableWidget {{
                background:#1a1d24;
                alternate-background:#20242b;
                color:#f8fafc;
                gridline-color:#334155;
                font-size:{size_base}px;
                font-family:'{get_master_font()}';
            }}
            QHeaderView::section {{
                background:#1e293b;
                color:#f8fafc;
                border:1px solid #334155;
                font-weight:bold;
                padding:7px;
            }}
            QTableWidget::item:selected {{
                background:#3b82f6;
                color:white;
            }}
        """
        editor_qss = f"""
            QTableWidget {{
                background:#1d2024;
                alternate-background:#25282e;
                color:#f8fafc;
                gridline-color:#4c525e;
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
                background:#0ea5e9;
                color:white;
            }}
        """
    else:
        history_qss = f"""
            QTableWidget {{
                background:white;
                alternate-background:#f1f5f9;
                color:#0f172a;
                gridline-color:#e2e8f0;
                font-size:{size_base}px;
                font-family:'{get_master_font()}';
            }}
            QHeaderView::section {{
                background:#243752;
                color:white;
                border:1px solid #cbd5e1;
                font-weight:bold;
                padding:7px;
            }}
            QTableWidget::item:selected {{
                background:#2563eb;
                color:white;
            }}
        """
        editor_qss = f"""
            QTableWidget {{
                background:white;
                alternate-background:#f8fafc;
                color:#0f172a;
                gridline-color:#cbd5e1;
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
                background:#bfdbfe;
                color:#0f172a;
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
            color:{_warna_tema(is_dark, "#ffffff", "#0f172a")};
        """,
        "lbl_title_editor": f"""
            font-size:{size_title + 1}px;
            font-weight:bold;
            font-family:'{get_master_font()}';
            color:{_warna_tema(is_dark, "#60a5fa", "#2563eb")};
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
            background:{_warna_tema(is_dark, "#1d2024", "#ffffff")};
            color:{_warna_tema(is_dark, "#ffffff", "#0f172a")};
            placeholder-text-color:{placeholder};
            border:1px solid {_warna_tema(is_dark, "#4c525e", "#cbd5e1")};
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
                background-color: {_warna_tema(is_dark, "#1d2024", "#ffffff")};
                color: {_warna_tema(is_dark, "#ffffff", "#0f172a")};
                border: 1px solid {_warna_tema(is_dark, "#4c525e", "#cbd5e1")};
            }}
            QMenu::item:selected {{
                background-color: #2563eb;
                color: white;
            }}
        """,

    }