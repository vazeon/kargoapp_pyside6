# themes/modules/kontak_armada.py
"""Stylesheet untuk tab Kontak (Penerima, Pengirim) dan tab Armada (Truk, Kapal)."""

from __future__ import annotations

from typing import Dict, Tuple

from themes.colors import get_theme_colors


ARMADA_PREVIEW_FOTO_STYLE = """
    border: 2px dashed #9ca3af;
    color: #9ca3af;
    background-color: transparent;
"""


def _warna_tema(is_dark: bool, gelap: str, terang: str) -> str:
    """Pilih warna khusus modul yang memang berbeda antara tema gelap/terang."""
    return gelap if is_dark else terang


def get_kontak_riwayat_styles(is_dark: bool) -> Dict[str, str]:
    """Style bersama untuk subtab Pengirim dan Penerima."""
    ui = get_theme_colors(is_dark)["ui"]

    return {
        "judul": f"""
            color: {_warna_tema(is_dark, "#ffffff", "#1e293b")};
            font-weight: bold;
        """,
        "judul_histori": f"""
            color: {ui["accent"]};
            font-weight: bold;
        """,
        "input": f"""
            background-color: {ui["field_background"]};
            color: {ui["text_primary"]};
            placeholder-text-color: {ui["placeholder_text"]};
            border: 1px solid {ui["field_border"]};
            border-radius: 4px;
        """,
        "panel": f"""
            QFrame#panelHistori {{
                background-color: {ui["panel_background"]};
                border-radius: 8px;
                border: 1px solid {ui["panel_border"]};
            }}
        """,
    }


def get_armada_styles(is_dark: bool, mode: str) -> Dict[str, str]:
    """Menghasilkan style SubTab Truk dan SubTab Armada berdasarkan tema dan mode form."""
    ui = get_theme_colors(is_dark)["ui"]
    mode_normalized = str(mode or "IDLE").upper()
    is_primary_mode = mode_normalized in {"IDLE", "PREVIEW"}
    warna_btn_utama = "#3b82f6" if is_primary_mode else "#22c55e"
    warna_btn_utama_hover = "#2563eb" if is_primary_mode else "#16a34a"
    warna_btn_utama_pressed = "#1d4ed8" if is_primary_mode else "#15803d"

    styles = {
        "panel_kanan": f"""
            QFrame#panelEditor {{
                background-color: {ui["panel_background"]};
                border-radius: 8px;
                border: 1px solid {ui["panel_border"]};
            }}
        """,
        "input_normal": f"""
            background-color: {_warna_tema(is_dark, "#0f172a", "#ffffff")};
            color: {ui["text_primary"]};
            placeholder-text-color: {ui["placeholder_text"]};
            border: 1px solid {ui["field_border"]};
            border-radius: 4px;
        """,
        "input_locked": f"""
            background-color: {ui["locked_background"]};
            color: {ui["locked_text"]};
            placeholder-text-color: {ui["placeholder_text"]};
            border: 1px dashed {ui["locked_border"]};
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
                background-color: {_warna_tema(is_dark, "#7f1d1d", "#fef2f2")};
                {_warna_tema(is_dark, "color: white;", "")}
            }}
            QPushButton:pressed {{
                background-color: {_warna_tema(is_dark, "#450a0a", "#fee2e2")};
                {_warna_tema(is_dark, "color: white;", "")}
            }}
        """,
        "btn_foto": f"""
            QPushButton {{
                background-color: {_warna_tema(is_dark, "#334155", "#e2e8f0")};
                color: {ui["text_primary"]};
                border: 1px solid {_warna_tema(is_dark, "#475569", "#cbd5e1")};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {_warna_tema(is_dark, "#475569", "#cbd5e1")};
            }}
            QPushButton:pressed {{
                background-color: {_warna_tema(is_dark, "#1e293b", "#94a3b8")};
            }}
        """,
        "label_judul": f"""
            color: {ui["text_primary"]};
            font-weight: bold;
        """,
        "label_judul_kanan": f"""
            color: {ui["accent"]};
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