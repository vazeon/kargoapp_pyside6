# themes/modules/invoice.py
from __future__ import annotations

from typing import Dict

from utils.typography import MASTER_FONT


def get_invoice_styles(
    is_dark: bool,
    size_title: int,
    size_base: int,
    size_input: int,
    size_total: int,
) -> Dict[str, str]:
    """Menghasilkan seluruh style UI Invoice berdasarkan tema dan zoom."""
    title_color = "#ffffff" if is_dark else "#0f172a"
    accent = "#60a5fa" if is_dark else "#2563eb"
    text_color = "#e2e8f0" if is_dark else "#334155"
    input_bg = "#1d2024" if is_dark else "#ffffff"
    input_border = "#4c525e" if is_dark else "#cbd5e1"

    if is_dark:
        history_qss = f"""
            QTableWidget {{
                background:#1a1d24;
                alternate-background:#20242b;
                color:#f8fafc;
                gridline-color:#334155;
                font-size:{size_base}px;
                font-family:'{MASTER_FONT}';
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
                font-family:'{MASTER_FONT}';
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
                font-family:'{MASTER_FONT}';
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
                font-family:'{MASTER_FONT}';
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
            font-family:'{MASTER_FONT}';
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
            font-family:'{MASTER_FONT}';
            color:{title_color};
        """,
        "lbl_title_editor": f"""
            font-size:{size_title + 1}px;
            font-weight:bold;
            font-family:'{MASTER_FONT}';
            color:{accent};
        """,
        "lbl_subtotal": f"""
            font-size:{size_base}px;
            font-weight:bold;
            font-family:'{MASTER_FONT}';
            color:{text_color};
        """,
        "lbl_total_tagihan": f"""
            font-size:{size_total}px;
            font-weight:bold;
            font-family:'{MASTER_FONT}';
            color:#dc2626;
            margin-top:4px;
        """,
        "input": f"""
            font-size:{size_input}px;
            font-family:'{MASTER_FONT}';
            padding:6px;
            background:{input_bg};
            color:{title_color};
            border:1px solid {input_border};
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
                background-color: {input_bg};
                color: {title_color};
                border: 1px solid {input_border};
            }}
            QMenu::item:selected {{
                background-color: #2563eb;
                color: white;
            }}
        """,

        "splitter": f"""
            QSplitter::handle {{
                background-color: {input_border};
                margin: 14px 1px;
                border-radius: 1px;
            }}
        """,
    }
