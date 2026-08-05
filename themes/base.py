# themes/base.py
"""Konstanta dan stylesheet dasar aplikasi."""

from utils.typography import (
    get_master_font,
    get_global_font_sizes,
)

GLOBAL_FONT_SIZES = get_global_font_sizes(0)
GLOBAL_BASE_SIZE = GLOBAL_FONT_SIZES["sz_base"]

BASE_STYLE = f"""
    QWidget {{
        font-family: "{get_master_font()}";
        font-size: {GLOBAL_BASE_SIZE}px;
    }}
    QLineEdit[custom_italic="true"][is_empty="true"],
    QTextEdit[custom_italic="true"][is_empty="true"] {{
        font-style: italic;
        color: palette(mid);
    }}
    QLineEdit[custom_italic="true"][is_empty="false"],
    QTextEdit[custom_italic="true"][is_empty="false"] {{
        font-style: normal;
    }}
"""
