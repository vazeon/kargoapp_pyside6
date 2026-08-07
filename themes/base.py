# themes/base.py
"""Stylesheet dasar aplikasi."""

from utils.typography import get_master_font


BASE_STYLE = f"""
    QWidget {{
        font-family: "{get_master_font()}";
    }}
"""