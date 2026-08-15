# themes/modules/manifest.py
from typing import Optional, Tuple

from PySide6.QtGui import QColor, QFont

from themes.colors import get_theme_colors
from utils.typography import get_master_font, get_global_font_sizes


def _warna_tema(is_dark: bool, gelap: str, terang: str) -> str:
    """Pilih warna tanpa menjauhkan kode warna dari blok style pemakainya."""
    return gelap if is_dark else terang


def get_manifest_styles(is_dark: bool, is_edit_mode: bool, z: int = 0) -> dict:
    """Menghasilkan seluruh QSS utama milik TabManifest."""
    sizes = get_global_font_sizes(z)
    sz_base = sizes["sz_base"]
    sz_input = sizes["sz_input"]
    sz_title = sizes["sz_title"]
    ui = get_theme_colors(is_dark)["ui"]
    placeholder = ui["placeholder_text"]

    warna_btn = "#f97316" if is_edit_mode else "#22c55e"
    warna_btn_hover = "#ea580c" if is_edit_mode else "#16a34a"
    warna_btn_pressed = "#c2410c" if is_edit_mode else "#15803d"

    lbl_title = f"""
        color: {ui["text_primary"]};
        font-size: {sz_title}px;
        font-weight: bold;
        font-family: '{get_master_font()}';
    """

    style_input = f"""
        QLineEdit {{
            font-size: {sz_input}px;
            background-color: {ui["field_background"]};
            color: {ui["text_primary"]};
            placeholder-text-color: {placeholder};
            border: 1px solid {ui["field_border"]};
            padding: 6px;
            border-radius: 4px;
            font-family: '{get_master_font()}';
        }}
    """

    # Kartu detail Manifest. Warna dark/light ditulis langsung pada blok pemakainya.
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
            font-size: {sz_base}px;
            font-weight: 600;
            font-family: '{get_master_font()}';
        }}
    """

    label_header = f"""
        QLabel {{
            color: {_warna_tema(is_dark, "#C8D1E0", "#4B5C73")};
            background: transparent;
            font-size: {sz_base}px;
            font-weight: 600;
            font-family: '{get_master_font()}';
        }}
    """

    txt_tanggal_manifest = f"""
        QLineEdit {{
            color: {_warna_tema(is_dark, "#F8FAFC", "#10233F")};
            placeholder-text-color: {placeholder};
            background: {_warna_tema(is_dark, "#181C24", "#FFFFFF")};
            border: 1px solid {_warna_tema(is_dark, "#4B5563", "#C8D4E3")};
            border-radius: 5px;
            padding: 2px 8px;
            font-size: {sz_base}px;
            font-family: '{get_master_font()}';
        }}
    """

    txt_no_manifest = f"""
        QLineEdit {{
            color: {_warna_tema(is_dark, "#FFC400", "#C90000")};
            placeholder-text-color: {placeholder};
            background: {_warna_tema(is_dark, "#171B23", "#FFF2F2")};
            border: 2px solid {_warna_tema(is_dark, "#3B82F6", "#FF4D5E")};
            border-radius: 6px;
            padding: 2px 10px;
            font-size: {sz_base + 3}px;
            font-weight: 800;
            letter-spacing: 1px;
            font-family: '{get_master_font()}';
        }}
    """

    style_tabel = f"""
        QTableWidget {{
            background-color: {ui["table_background"]};
            alternate-background-color: {ui["table_alternate_background"]};
            color: {ui["table_text"]};
            gridline-color: {ui["table_grid"]};
            font-size: {sz_base}px;
            font-family: '{get_master_font()}';
        }}
        QLineEdit#manifestKetCell {{
            background-color: transparent;
            border: none;
            padding-left: 4px;
            color: {ui["table_text"]};
            placeholder-text-color: {placeholder};
        }}
        QLineEdit#manifestKetCell:focus {{
            border: 1px solid {ui["selection_background"]};
            background-color: transparent;
        }}
        QHeaderView::section {{
            background-color: {ui["table_header_background"]};
            color: #ffffff;
            border: 1px solid {_warna_tema(is_dark, "#334155", "#cbd5e1")};
            font-size: {sz_base}px;
            font-weight: bold;
            padding: 6px;
            font-family: '{get_master_font()}';
        }}
        QTableWidget::item:selected {{
            background-color: {ui["selection_background"]};
            color: #ffffff;
        }}
        QTableWidget::indicator {{
            width: {18 + z}px;
            height: {18 + z}px;
        }}
    """

    list_histori = f"""
        QTreeWidget {{
            background-color: {ui["field_background"]};
            color: {_warna_tema(is_dark, "#cbd5e1", "#1e293b")};
            border: 1px solid {ui["field_border"]};
            border-radius: 6px;
            padding: 5px;
            font-size: {sz_base}px;
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
            font-weight: bold;
            padding: 7px 20px;
            border-radius: 4px;
            font-size: {sz_base}px;
            font-family: '{get_master_font()}';
        }}
        QPushButton:hover {{
            background-color: {warna_btn_hover};
        }}
        QPushButton:pressed {{
            background-color: {warna_btn_pressed};
        }}
    """

    panel_kiri = f"""
        QLabel {{
            font-size: {sz_base}px;
            font-family: '{get_master_font()}';
            color: {ui["text_primary"]};
            background-color: transparent;
            border: none;
        }}
    """

    panel_kanan = panel_kiri

    return {
        "lbl_title": lbl_title,
        "style_input": style_input,
        "card_manifest": card_manifest,
        "label_input": label_input,
        "label_header": label_header,
        "txt_tanggal_manifest": txt_tanggal_manifest,
        "txt_no_manifest": txt_no_manifest,
        "btn_proses": btn_proses,
        "list_histori": list_histori,
        "style_tabel": style_tabel,
        "panel_kiri": panel_kiri,
        "panel_kanan": panel_kanan,
    }


def get_manifest_row_highlight(
    is_dark: bool,
    belongs_to_current_manifest: bool,
) -> Optional[QColor]:
    """Warna baris yang sudah termasuk manifest ketika mode edit aktif."""
    if not belongs_to_current_manifest:
        return None

    return QColor("#3d2a1b" if is_dark else "#fef3c7")


def get_manifest_history_date_appearance(
    is_dark: bool,
    base_point_size: int,
) -> Tuple[QFont, QColor]:
    """Font dan warna untuk tanggal pada histori manifest."""
    font_tanggal = QFont(get_master_font())

    if base_point_size > 0:
        font_tanggal.setPointSize(max(6, base_point_size - 2))

    font_tanggal.setItalic(True)
    warna_tanggal = QColor("#94a3b8" if is_dark else "#64748b")

    return font_tanggal, warna_tanggal