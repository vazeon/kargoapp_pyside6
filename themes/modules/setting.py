# themes/modules/setting.py
from themes.colors import get_theme_colors
from themes.components.table import get_table_styles, TableMetrics
from utils.typography import get_master_font, ukuran_font_px_ke_pt


def _warna_tema(is_dark: bool, gelap: str, terang: str) -> str:
    """Pilih warna tanpa menjauhkan kode warna dari blok style pemakainya."""
    return gelap if is_dark else terang


def get_setting_styles(
    is_dark: bool,
    sz_base: int,
    sz_input: int,
    sz_title: int,
) -> dict:
    ui = get_theme_colors(is_dark)["ui"]
    return {
        'table': get_table_styles(
            is_dark,
            metrics=TableMetrics(
                font_family=get_master_font(),
                font_size_pt=ukuran_font_px_ke_pt(sz_base),
            ),
        ),
        'form_label': f"""
            color: {_warna_tema(is_dark, "#94a3b8", "#475569")};
            font-size: {sz_base}px;
            font-family: '{get_master_font()}';
            font-weight: normal;
        """,
        'btn_simpan': f"""
            QPushButton {{
                background-color: #2563eb;
                color: #ffffff;
                font-size: {sz_input}px;
                font-family: '{get_master_font()}';
                font-weight: 600;
                letter-spacing: 0.8px;
                border: none;
                border-radius: 8px;
                padding: 0px 0px;
                margin-top: 6px;
            }}
            QPushButton:hover {{
                background-color: #1d4ed8;
            }}
            QPushButton:pressed {{
                background-color: #1e40af;
            }}
            QPushButton:disabled {{
                background-color: {_warna_tema(is_dark, "#334155", "#94a3b8")};
                color: {_warna_tema(is_dark, "#94a3b8", "#e2e8f0")};
            }}
        """,
        'btn_secondary': f"""
            QPushButton {{
                background-color: transparent;
                color: {_warna_tema(is_dark, "#93c5fd", "#2563eb")};
                font-size: {sz_base}px;
                font-family: '{get_master_font()}';
                font-weight: 600;
                border: 1px solid {_warna_tema(is_dark, "#60a5fa", "#2563eb")};
                border-radius: 6px;
                padding: 8px 8px;
            }}
            QPushButton:hover {{
                background-color: {_warna_tema(is_dark, "#1e3a5f", "#eff6ff")};
                border-color: {_warna_tema(is_dark, "#93c5fd", "#1d4ed8")};
            }}
            QPushButton:pressed {{
                background-color: {_warna_tema(is_dark, "#24476e", "#dbeafe")};
            }}
            QPushButton:disabled {{
                color: {ui["text_muted"]};
                border-color: {ui["field_border"]};
                background-color: transparent;
            }}
        """,
        'sidebar_container': f"""
            QWidget {{ background-color: {_warna_tema(is_dark, "#14171c", "#e2e8f0")}; }}
            QLabel {{ background-color: transparent; }}
        """,
        'sidebar_list': f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
                font-family: '{get_master_font()}';
                font-size: {sz_input}px;
            }}
            QListWidget::item {{
                padding: 8px 16px;
                border-radius: 6px;
                margin-bottom: 4px;
                color: {_warna_tema(is_dark, "#cbd5e1", "#334155")};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {_warna_tema(is_dark, "#1e222b", "#cbd5e1")};
            }}
            QListWidget::item:selected,
            QListWidget::item:selected:!active {{
                background-color: #3b82f6;
                color: #ffffff;
                font-weight: bold;
            }}
        """,
        'custom_groupbox': f"""
            QGroupBox {{
                font-weight: 500;
                font-size: {sz_title}px;
                font-family: '{get_master_font()}';
                color: {ui["text_primary"]};
                background-color: transparent;
                border: none;
                margin-top: 10px;
            }}
            QGroupBox::title {{
                padding: 0;
                background-color: transparent;
            }}
        """,
        'lbl_page_title': f"""
            font-size: {sz_title + 2}px;
            font-weight: 600;
            font-family: '{get_master_font()}';
            margin-bottom: 20px;
            color: {ui["text_primary"]};
        """,
        'lbl_info_italic': f"""
            color: {_warna_tema(is_dark, "#94a3b8", "#64748b")};
            font-style: italic;
        """,
        'btn_add_rekening': f"""
            QPushButton {{
                color: #3b82f6;
                font-size: 26px;
                font-weight: bold;
                background: transparent;
                border: none;
                font-family: "{get_master_font()}";
            }}
        """,
        'btn_row_delete': f"""
            QPushButton {{
                color: #ef4444;
                font-size: 26px;
                font-weight: bold;
                background: transparent;
                border: none;
                font-family: "{get_master_font()}";
            }}
        """,
        'btn_row_delete_disabled': f"""
            QPushButton {{
                color: #94a3b8;
                font-size: 26px;
                font-weight: bold;
                background: transparent;
                border: none;
                font-family: "{get_master_font()}";
            }}
        """,
        'lbl_menu': f"""
            font-weight: 500;
            font-size: 18px;
            color: #94a3b8;
            margin-bottom: 10px;
        """
    }