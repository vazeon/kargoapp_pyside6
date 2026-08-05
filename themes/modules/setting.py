# themes/modules/setting.py
from utils.typography import get_master_font


def get_setting_styles(
    is_dark: bool,
    sz_base: int,
    sz_input: int,
    sz_title: int,
) -> dict:
    if is_dark:
        bg_page, bg_card, bg_input, bg_input_foc = (
            "#1a1d24",
            "#25282e",
            "#1d2024",
            "#20242b",
        )
        bg_header, bg_alt_row, border, border_focus = (
            "#1e293b",
            "#20242b",
            "#4c525e",
            "#3b82f6",
        )
        border_grid, text_primary, text_muted, text_title, lbl_color = (
            "#334155",
            "#f8fafc",
            "#94a3b8",
            "#cbd5e1",
            "#94a3b8",
        )
        bg_sidebar, bg_list_hover = "#14171c", "#1e222b"
        list_text_color, page_title_color = "#cbd5e1", "#ffffff"
    else:
        bg_page, bg_card, bg_input, bg_input_foc = (
            "#f1f5f9",
            "#ffffff",
            "#ffffff",
            "#ffffff",
        )
        bg_header, bg_alt_row, border, border_focus = (
            "#243752",
            "#f8fafc",
            "#cbd5e1",
            "#2563eb",
        )
        border_grid, text_primary, text_muted, text_title, lbl_color = (
            "#e2e8f0",
            "#0f172a",
            "#64748b",
            "#0f172a",
            "#475569",
        )
        bg_sidebar, bg_list_hover = "#e2e8f0", "#cbd5e1"
        list_text_color, page_title_color = "#334155", "#0f172a"

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
                color: {text_title};
                background-color: {bg_card};
                border: 1px solid {border};
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
            color: {lbl_color};
            font-size: {sz_base}px;
            font-family: '{get_master_font()}';
            font-weight: 600;
        """,
        'input_readonly': f"""
            QLineEdit {{
                padding: 8px 12px;
                font-size: {sz_base}px;
                font-family: '{get_master_font()}';
                border: 1px solid {border};
                border-radius: 6px;
                background-color: {bg_alt_row};
                color: {text_muted};
                letter-spacing: 0.2px;
            }}
        """,
        'input': f"""
            QLineEdit, QTextEdit, QComboBox {{
                padding: 8px 12px;
                font-size: {sz_input}px;
                font-family: '{get_master_font()}';
                border: 1px solid {border};
                border-radius: 6px;
                background-color: {bg_input};
                color: {text_primary};
                selection-background-color: #3b82f6;
            }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
                border: 1px solid {border_focus};
                background-color: {bg_input_foc};
            }}
            QLineEdit:disabled, QTextEdit:disabled {{
                color: {text_muted};
                background-color: {bg_alt_row};
            }}
            QTextEdit {{
                padding: 6px 10px;
                line-height: 1.4;
            }}
            QDateEdit {{
                font-size: {sz_input}px;
                padding: 2px 10px;
            }}
            /* FIX: Tambahkan font-size agar placeholder terzoom */
            QLineEdit[custom_italic="true"][is_empty="true"],
            QTextEdit[custom_italic="true"][is_empty="true"] {{
                font-style: italic;
                font-size: {sz_input}px;
                color: {text_muted};
            }}
            QLineEdit[custom_italic="true"][is_empty="false"],
            QTextEdit[custom_italic="true"][is_empty="false"] {{
                font-style: normal;
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
        'sidebar_container': f"background-color: {bg_sidebar};",
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
                color: {list_text_color};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {bg_list_hover};
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
                color: {page_title_color};
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
            color: {page_title_color};
        """,
        'lbl_hint': f"""
            color: {text_muted};
            font-size: {sz_base - 1}px;
        """,
        'lbl_menu': f"""
            font-weight: bold;
            font-size: 18px;
            color: #94a3b8;
            margin-bottom: 10px;
        """
    }
