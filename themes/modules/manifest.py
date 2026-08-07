# themes/modules/manifest.py
from typing import Optional, Tuple

from PySide6.QtGui import QColor, QFont

from utils.typography import get_master_font, get_global_font_sizes


def get_manifest_styles(is_dark: bool, is_edit_mode: bool, z: int = 0) -> dict:
    """Menghasilkan seluruh QSS utama milik TabManifest."""
    sizes = get_global_font_sizes(z)
    sz_base = sizes["sz_base"]
    sz_input = sizes["sz_input"]
    sz_title = sizes["sz_title"]

    warna_btn = "#f97316" if is_edit_mode else "#22c55e"
    warna_btn_hover = "#ea580c" if is_edit_mode else "#16a34a"
    warna_btn_pressed = "#c2410c" if is_edit_mode else "#15803d"

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
        header_border = "#334155"
        selected_bg = "#3b82f6"
        history_bg = "#1d2024"
        history_text = "#cbd5e1"
        panel_text = "#ffffff"
    else:
        title_color = "#0f172a"
        input_bg = "#ffffff"
        input_text = "#0f172a"
        input_border = "#cbd5e1"
        table_bg = "#ffffff"
        table_alt = "#f1f5f9"
        table_text = "#0f172a"
        table_grid = "#e2e8f0"
        header_bg = "#243752"
        header_border = "#cbd5e1"
        selected_bg = "#2563eb"
        history_bg = "#ffffff"
        history_text = "#1e293b"
        panel_text = "#0f172a"

    lbl_title = f"""
        color: {title_color};
        font-size: {sz_title}px;
        font-weight: bold;
        font-family: '{get_master_font()}';
    """

    style_input = f"""
        QLineEdit {{
            font-size: {sz_input}px;
            background-color: {input_bg};
            color: {input_text};
            border: 1px solid {input_border};
            padding: 6px;
            border-radius: 4px;
            font-family: '{get_master_font()}';
        }}
    """

    # Kartu detail Manifest.
    if is_dark:
        card_bg = "#171B23"
        card_border = "#3A4556"
        card_label = "#F2F4F7"
        header_label = "#C8D1E0"
        tanggal_text = "#F8FAFC"
        tanggal_bg = "#181C24"
        tanggal_border = "#4B5563"
        nomor_text = "#FFC400"
        nomor_bg = "#171B23"
        nomor_border = "#3B82F6"
    else:
        card_bg = "#FFFFFF"
        card_border = "#C8D4E3"
        card_label = "#172033"
        header_label = "#4B5C73"
        tanggal_text = "#10233F"
        tanggal_bg = "#FFFFFF"
        tanggal_border = "#C8D4E3"
        nomor_text = "#C90000"
        nomor_bg = "#FFF2F2"
        nomor_border = "#FF4D5E"

    card_manifest = f"""
        QFrame#cardRuteManifest, QFrame#cardArmadaManifest {{
            background-color: {card_bg};
            border: 1px solid {card_border};
            border-radius: 11px;
        }}
    """

    label_input = f"""
        QLabel {{
            color: {card_label};
            background: transparent;
            border: none;
            font-size: {sz_base}px;
            font-weight: 600;
            font-family: '{get_master_font()}';
        }}
    """

    label_header = f"""
        QLabel {{
            color: {header_label};
            background: transparent;
            font-size: {sz_base}px;
            font-weight: 600;
            font-family: '{get_master_font()}';
        }}
    """

    txt_tanggal_manifest = f"""
        QLineEdit {{
            color: {tanggal_text};
            background: {tanggal_bg};
            border: 1px solid {tanggal_border};
            border-radius: 5px;
            padding: 2px 8px;
            font-size: {sz_base}px;
            font-family: '{get_master_font()}';
        }}
    """

    txt_no_manifest = f"""
        QLineEdit {{
            color: {nomor_text};
            background: {nomor_bg};
            border: 2px solid {nomor_border};
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
            background-color: {table_bg};
            alternate-background-color: {table_alt};
            color: {table_text};
            gridline-color: {table_grid};
            font-size: {sz_base}px;
            font-family: '{get_master_font()}';
        }}
        QLineEdit#manifestKetCell {{
            background-color: transparent;
            border: none;
            padding-left: 4px;
            color: {table_text};
        }}
        QLineEdit#manifestKetCell:focus {{
            border: 1px solid {selected_bg};
            background-color: transparent;
        }}
        QHeaderView::section {{
            background-color: {header_bg};
            color: #ffffff;
            border: 1px solid {header_border};
            font-size: {sz_base}px;
            font-weight: bold;
            padding: 6px;
            font-family: '{get_master_font()}';
        }}
        QTableWidget::item:selected {{
            background-color: {selected_bg};
            color: #ffffff;
        }}
        QTableWidget::indicator {{
            width: {18 + z}px;
            height: {18 + z}px;
        }}
    """

    list_histori = f"""
        QTreeWidget {{
            background-color: {history_bg};
            color: {history_text};
            border: 1px solid {input_border};
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
            color: {panel_text};
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