# themes/components/top_right.py
"""Style widget pada bagian kanan atas aplikasi."""

from themes.colors import get_theme_colors
from utils.typography import get_master_font


def get_top_right_styles(is_dark: bool) -> tuple:
    colors = get_theme_colors(is_dark)
    palette = colors["palette"]
    ui = colors["ui"]

    if is_dark:
        btn_background = ui["panel_background"]
        btn_text = ui["on_primary"]
        btn_border = "#24334d"
        btn_hover_background = "#2c3e50"
        btn_pressed_background = palette["shadow"]
        hover_border_rule = f"border: 1px solid {ui['primary']};"
        pressed_border_rule = f"border: 1px solid {ui['primary_hover']};"
    else:
        btn_background = "#edf2f7"
        btn_text = "#2d3748"
        btn_border = ui["field_border"]
        btn_hover_background = palette["button"]
        btn_pressed_background = ui["field_border"]
        hover_border_rule = ""
        pressed_border_rule = ""

    btn_style = f"""
        QPushButton {{
            font-family: '{get_master_font()}';
            background-color: {btn_background};
            color: {btn_text};
            border: 1px solid {btn_border};
            font-weight: bold;
            border-radius: 4px;
        }}
        QPushButton:hover {{
            background-color: {btn_hover_background};
            {hover_border_rule}
        }}
        QPushButton:pressed {{
            background-color: {btn_pressed_background};
            {pressed_border_rule}
        }}
    """

    # Warna label cabang merupakan aksen khusus komponen top-right.
    lbl_style = f"""
        font-family: '{get_master_font()}';
        font-size: 13px;
        color: #f59e0b;
        padding: 5px;
        margin-right: 10px;
    """

    return btn_style, lbl_style