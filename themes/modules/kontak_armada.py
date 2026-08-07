# themes/modules/kontak_armada.py
"""Stylesheet untuk tab Kontak (Penerima, Pengirim) dan tab Armada (Truk, Kapal)."""

from __future__ import annotations

from typing import Dict, Tuple

ARMADA_PREVIEW_FOTO_STYLE = """
    border: 2px dashed #9ca3af;
    border-radius: 8px;
    color: #9ca3af;
    background-color: transparent;
"""


def get_kontak_riwayat_styles(is_dark: bool) -> Dict[str, str]:
    """Style bersama untuk subtab Pengirim dan Penerima."""
    if is_dark:
        return {
            "judul": f"""
                color: #ffffff;
                font-weight: bold;
            """,
            "judul_histori": f"""
                color: #60a5fa;
                font-weight: bold;
            """,
            "input": f"""
                background-color: #1d2024;
                color: white;
                border: 1px solid #4c525e;
                border-radius: 4px;
            """,
            "panel": f"""
                QFrame#panelHistori {{
                    background-color: #1e293b;
                    border-radius: 8px;
                    border: 1px solid #334155;
                }}
            """,
        }

    return {
        "judul": f"""
            color: #1e293b;
            font-weight: bold;
        """,
        "judul_histori": f"""
            color: #2563eb;
            font-weight: bold;
        """,
        "input": f"""
            background-color: white;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
        """,
        "panel": f"""
            QFrame#panelHistori {{
                background-color: #f8fafc;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
            }}
        """,
    }


def get_armada_styles(is_dark: bool, mode: str) -> Dict[str, str]:
    """Menghasilkan style SubTab Truk dan SubTab Armada berdasarkan tema dan mode form."""
    mode_normalized = str(mode or "IDLE").upper()
    is_primary_mode = mode_normalized in {"IDLE", "PREVIEW"}
    warna_btn_utama = "#3b82f6" if is_primary_mode else "#22c55e"
    warna_btn_utama_hover = "#2563eb" if is_primary_mode else "#16a34a"
    warna_btn_utama_pressed = "#1d4ed8" if is_primary_mode else "#15803d"

    if is_dark:
        styles = {
            "panel_kanan": f"""
                QFrame#panelEditor {{
                    background-color: #1e293b;
                    border-radius: 8px;
                    border: 1px solid #334155;
                }}
            """,
            "input_normal": f"""
                background-color: #0f172a;
                color: #ffffff;
                border: 1px solid #4c525e;
                border-radius: 4px;
            """,
            "input_locked": f"""
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px dashed #475569;
                border-radius: 4px;
            """,
            "btn_batal": f"""
                QPushButton {{
                    background-color: transparent;
                    color: #ef4444;
                    border: 1px solid #ef4444;
                    font-weight: bold;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background-color: #7f1d1d;
                    color: white;
                }}
                QPushButton:pressed {{
                    background-color: #450a0a;
                    color: white;
                }}
            """,
            "btn_foto": f"""
                QPushButton {{
                    background-color: #334155;
                    color: white;
                    border: 1px solid #475569;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background-color: #475569;
                }}
                QPushButton:pressed {{
                    background-color: #1e293b;
                }}
            """,
            "label_judul": f"""
                color: #ffffff;
                font-weight: bold;
            """,
            "label_judul_kanan": f"""
                color: #60a5fa;
                font-weight: bold;
            """,
        }
    else:
        styles = {
            "panel_kanan": f"""
                QFrame#panelEditor {{
                    background-color: #f8fafc;
                    border-radius: 8px;
                    border: 1px solid #e2e8f0;
                }}
            """,
            "input_normal": f"""
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
            """,
            "input_locked": f"""
                background-color: #f1f5f9;
                color: #64748b;
                border: 1px dashed #cbd5e1;
                border-radius: 4px;
            """,
            "btn_batal": f"""
                QPushButton {{
                    background-color: transparent;
                    color: #ef4444;
                    border: 1px solid #ef4444;
                    font-weight: bold;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background-color: #fef2f2;
                }}
                QPushButton:pressed {{
                    background-color: #fee2e2;
                }}
            """,
            "btn_foto": f"""
                QPushButton {{
                    background-color: #e2e8f0;
                    color: #0f172a;
                    border: 1px solid #cbd5e1;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background-color: #cbd5e1;
                }}
                QPushButton:pressed {{
                    background-color: #94a3b8;
                }}
            """,
            "label_judul": f"""
                color: #0f172a;
                font-weight: bold;
            """,
            "label_judul_kanan": f"""
                color: #2563eb;
                font-weight: bold;
            """,
        }

    styles["btn_aksi"] = f"""
        QPushButton {{
            background-color: {warna_btn_utama};
            color: white;
            font-weight: bold;
            border-radius: 4px;
        }}
        QPushButton:hover {{
            background-color: {warna_btn_utama_hover};
        }}
        QPushButton:pressed {{
            background-color: {warna_btn_utama_pressed};
        }}
    """
    styles["preview_foto"] = ARMADA_PREVIEW_FOTO_STYLE
    return styles


def get_penerima_blacklist_colors(is_dark: bool) -> Tuple[str, str]:
    """Warna khusus baris penerima berstatus BLACKLIST."""
    if is_dark:
        return "#7f1d1d", "#ffffff"
    return "#fee2e2", "#991b1b"