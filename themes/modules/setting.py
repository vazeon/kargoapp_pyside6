# themes/modules/setting.py
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


def get_setting_styles(
    is_dark: bool,
    sz_base: int,
    sz_input: int,
    sz_title: int,
) -> dict:
    placeholder = _warna_placeholder(is_dark)
    return {
        'scroll_area': f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
        """,
        'groupbox': f"""
            QGroupBox {{
                font-weight: bold;
                font-size: {sz_title}px;
                font-family: '{get_master_font()}';
                color: {_warna_tema(is_dark, "#cbd5e1", "#0f172a")};
                background-color: {_warna_tema(is_dark, "#25282e", "#ffffff")};
                border: 1px solid {_warna_tema(is_dark, "#4c525e", "#cbd5e1")};
                border-radius: 10px;
                margin-top: 22px;
                padding-top: 22px;
                padding-left: 4px;
                padding-right: 4px;
                padding-bottom: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                top: 4px;
                padding: 0 6px;
                background-color: transparent;
            }}
        """,
        'form_label': f"""
            color: {_warna_tema(is_dark, "#94a3b8", "#475569")};
            font-size: {sz_base}px;
            font-family: '{get_master_font()}';
            font-weight: 600;
        """,
        'input_readonly': f"""
            QLineEdit {{
                padding: 8px 12px;
                font-size: {sz_base}px;
                font-family: '{get_master_font()}';
                border: 1px solid {_warna_tema(is_dark, "#4c525e", "#cbd5e1")};
                border-radius: 6px;
                background-color: {_warna_tema(is_dark, "#20242b", "#f8fafc")};
                color: {_warna_tema(is_dark, "#94a3b8", "#64748b")};
                placeholder-text-color: {placeholder};
                letter-spacing: 0.2px;
            }}
        """,
        'input': f"""
            QLineEdit, QTextEdit {{
                padding: 8px 12px;
                font-size: {sz_input}px;
                font-family: '{get_master_font()}';
                border: 1px solid {_warna_tema(is_dark, "#4c525e", "#cbd5e1")};
                border-radius: 6px;
                background-color: {_warna_tema(is_dark, "#1d2024", "#ffffff")};
                color: {_warna_tema(is_dark, "#f8fafc", "#0f172a")};
                placeholder-text-color: {placeholder};
                selection-background-color: #3b82f6;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border: 1px solid {_warna_tema(is_dark, "#3b82f6", "#2563eb")};
                background-color: {_warna_tema(is_dark, "#20242b", "#ffffff")};
            }}
            QLineEdit:disabled, QTextEdit:disabled {{
                color: {_warna_tema(is_dark, "#94a3b8", "#64748b")};
                background-color: {_warna_tema(is_dark, "#20242b", "#f8fafc")};
            }}
            QTextEdit {{
                padding: 6px 10px;
                line-height: 1.4;
            }}
        """,
        'btn_simpan': f"""
            QPushButton {{
                background-color: #2563eb;
                color: #ffffff;
                font-size: {sz_input}px;
                font-family: '{get_master_font()}';
                font-weight: bold;
                letter-spacing: 0.8px;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                margin-top: 6px;
            }}
            QPushButton:hover {{
                background-color: #1d4ed8;
            }}
            QPushButton:pressed {{
                background-color: #1e40af;
            }}
            QPushButton:disabled {{
                background-color: #94a3b8;
                color: #e2e8f0;
            }}
        """,
        'btn_secondary': f"""
            QPushButton {{
                background-color: transparent;
                color: #2563eb;
                font-size: {sz_base}px;
                font-family: '{get_master_font()}';
                font-weight: 600;
                border: 1px solid #2563eb;
                border-radius: 6px;
                padding: 7px 16px;
            }}
            QPushButton:hover {{
                background-color: #eff6ff;
                border-color: #1d4ed8;
            }}
            QPushButton:pressed {{
                background-color: #dbeafe;
            }}
        """,
        'sidebar_container': f"background-color: {_warna_tema(is_dark, "#14171c", "#e2e8f0")};",
        'sidebar_list': f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
                font-family: '{get_master_font()}';
                font-size: {sz_input}px;
            }}
            QListWidget::item {{
                padding: 14px 16px;
                border-radius: 6px;
                margin-bottom: 4px;
                color: {_warna_tema(is_dark, "#cbd5e1", "#334155")};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {_warna_tema(is_dark, "#1e222b", "#cbd5e1")};
            }}
            QListWidget::item:selected {{
                background-color: #3b82f6;
                color: #ffffff;
                font-weight: bold;
            }}
        """,
        'custom_groupbox': f"""
            QGroupBox {{
                font-weight: bold;
                font-size: {sz_title}px;
                font-family: '{get_master_font()}';
                color: {_warna_tema(is_dark, "#ffffff", "#0f172a")};
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
            font-size: {sz_title + 8}px;
            font-weight: bold;
            font-family: '{get_master_font()}';
            margin-bottom: 20px;
            color: {_warna_tema(is_dark, "#ffffff", "#0f172a")};
        """,
        'lbl_hint': f"""
            color: {_warna_tema(is_dark, "#94a3b8", "#64748b")};
            font-size: {sz_base - 1}px;
        """,
        'lbl_info_italic': """
            color: #94a3b8;
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
            font-weight: bold;
            font-size: 18px;
            color: #94a3b8;
            margin-bottom: 10px;
        """
    }