# themes/modules/manifest.py
from typing import Optional, Tuple

from PySide6.QtGui import QColor, QFont

from themes.colors import get_theme_colors
from utils.typography import (
    get_fixed_font_sizes,
    get_fixed_font_sizes_pt,
    get_font_weights,
    get_master_font,
)


_FONT_WEIGHTS = get_font_weights()

def _warna_tema(is_dark: bool, gelap: str, terang: str) -> str:
    """Pilih warna tanpa menjauhkan kode warna dari blok style pemakainya."""
    return gelap if is_dark else terang


def get_manifest_styles(is_dark: bool, is_edit_mode: bool) -> dict:
    """Menghasilkan seluruh QSS utama milik TabManifest (tanpa QSS Tabel)."""
    sizes = get_fixed_font_sizes()
    body_small_size = sizes["body_small"]
    body_size = sizes["body"]
    page_title_size = sizes["subtitle"]
    subtitle_size = sizes["subtitle"]

    ui = get_theme_colors(is_dark)["ui"]
    placeholder = ui["placeholder_text"]

    warna_btn = "#f97316" if is_edit_mode else "#22c55e"
    warna_btn_hover = "#ea580c" if is_edit_mode else "#16a34a"
    warna_btn_pressed = "#c2410c" if is_edit_mode else "#15803d"

    lbl_title = f"""
        color: {ui["text_primary"]};
        font-size: {page_title_size}px;
        font-weight: {_FONT_WEIGHTS["medium"]};
        font-family: '{get_master_font()}';
    """

    lbl_history_title = f"""
        color: {ui["text_primary"]};
        font-size: {body_size}px;
        font-weight: {_FONT_WEIGHTS["medium"]};
        font-family: '{get_master_font()}';
    """

    style_input = f"""
        QLineEdit {{
            font-size: {body_size}px;
            background-color: {ui["field_background"]};
            color: {ui["text_primary"]};
            placeholder-text-color: {placeholder};
            border: 1px solid {ui["field_border"]};
            padding: 6px;
            border-radius: 4px;
            font-family: '{get_master_font()}';
        }}
    """

    card_manifest = f"""
        QFrame#cardRuteManifest, QFrame#cardArmadaManifest {{
            background-color: {_warna_tema(is_dark, "#171B23", "#FFFFFF")};
            border: 1px solid {_warna_tema(is_dark, "#3A4556", "#C8D4E3")};
            border-radius: 8px;
        }}
    """

    label_input = f"""
        QLabel {{
            color: {_warna_tema(is_dark, "#F2F4F7", "#172033")};
            background: transparent;
            border: none;
            font-size: {body_size}px;
            font-weight: {_FONT_WEIGHTS["medium"]};
            font-family: '{get_master_font()}';
        }}
    """

    label_header = f"""
        QLabel {{
            color: {_warna_tema(is_dark, "#C8D1E0", "#4B5C73")};
            background: transparent;
            font-size: {body_small_size}px;
            font-weight: {_FONT_WEIGHTS["medium"]};
            font-family: '{get_master_font()}';
        }}
    """

    lbl_no_manifest = f"""
        QLabel {{
            color: {_warna_tema(is_dark, "#9ca3af", "#64748b")};
            font-size: {body_small_size}px;
            font-weight: {_FONT_WEIGHTS["medium"]};
            font-family: '{get_master_font()}';
        }}
    """

    txt_tanggal_manifest = f"""
        QLabel {{
            color: {_warna_tema(is_dark, "#F8FAFC", "#10233F")};
            placeholder-text-color: {placeholder};
            background: transparent;
            border: none;
            padding: 2px 8px;
            font-size: {body_small_size}px;
            font-weight: {_FONT_WEIGHTS["regular"]};
            font-family: '{get_master_font()}';
        }}
    """

    txt_no_manifest = f"""
        QLabel {{
            color: {_warna_tema(is_dark, "#FFC400", "#3B82F6")};
            placeholder-text-color: {placeholder};
            background: {_warna_tema(is_dark, "#171B23", "#F2FCFF")};
            border: 1px solid {_warna_tema(is_dark, "#3B82F6", "#3B82F6")};
            border-radius: 6px;
            padding: 6px 8px;
            font-size: {subtitle_size}px;
            font-weight: {_FONT_WEIGHTS["medium"]};
            letter-spacing: 1px;
            font-family: '{get_master_font()}';
        }}
    """

    list_histori = f"""
        QTreeWidget {{
            background-color: {ui["field_background"]};
            color: {_warna_tema(is_dark, "#cbd5e1", "#1e293b")};
            border: 1px solid {ui["field_border"]};
            border-radius: 6px;
            padding: 4px;
            font-size: {body_small_size}px;
            font-family: '{get_master_font()}';
        }}
        QTreeView::item {{
            padding: 4px;
        }}
    """

    btn_proses = f"""
        QPushButton {{
            background-color: {warna_btn};
            color: #ffffff;
            font-weight: {_FONT_WEIGHTS["medium"]};
            padding: 10px 20px;
            border-radius: 6px;
            font-size: {body_size}px;
            font-family: '{get_master_font()}';
        }}
        QPushButton:hover {{
            background-color: {warna_btn_hover};
        }}
        QPushButton:pressed {{
            background-color: {warna_btn_pressed};
        }}
    """

    menu_histori = f"""
        QMenu {{
            background-color: {ui["field_background"]};
            color: {ui["text_primary"]};
            padding: 5px;
            font-size: {body_small_size}px;
            font-family: '{get_master_font()}';
        }}
        QMenu::item {{
            color: {ui["text_primary"]};
            padding: 6px 20px;
        }}
        QMenu::item:selected {{
            background-color: {ui["selection_background"]};
            color: {ui["text_primary"]};
        }}
        QMenu::item:disabled {{
            color: {placeholder};
        }}
    """

    panel_kiri = f"""
        QLabel {{
            font-size: {body_small_size}px;
            font-family: '{get_master_font()}';
            color: {ui["text_primary"]};
            background-color: transparent;
            border: none;
        }}
    """

    panel_kanan = panel_kiri

    return {
        "lbl_title": lbl_title,
        "lbl_history_title": lbl_history_title,
        "style_input": style_input,
        "card_manifest": card_manifest,
        "label_input": label_input,
        "label_header": label_header,
        "lbl_no_manifest": lbl_no_manifest,
        "txt_tanggal_manifest": txt_tanggal_manifest,
        "txt_no_manifest": txt_no_manifest,
        "btn_proses": btn_proses,
        "menu_histori": menu_histori,
        "list_histori": list_histori,
        "panel_kiri": panel_kiri,
        "panel_kanan": panel_kanan,
    }


def get_manifest_row_highlight(
    is_dark: bool,
    belongs_to_current_manifest: bool,
) -> Optional[QColor]:
    if not belongs_to_current_manifest:
        return None
    return QColor("#3d2a1b" if is_dark else "#fef3c7")


def get_manifest_history_date_appearance(
    is_dark: bool,
) -> Tuple[QFont, QColor]:
    """Gunakan ukuran caption yang konsisten untuk tanggal item histori."""
    font_tanggal = QFont(get_master_font())
    font_tanggal.setPointSizeF(get_fixed_font_sizes_pt()["caption"])
    font_tanggal.setItalic(True)
    warna_tanggal = QColor("#94a3b8" if is_dark else "#64748b")
    return font_tanggal, warna_tanggal
