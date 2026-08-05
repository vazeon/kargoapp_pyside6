# themes/components/top_right.py
"""Style widget pada bagian kanan atas aplikasi."""
from utils.typography import get_master_font


def get_top_right_styles(is_dark: bool) -> tuple:
    if is_dark:
        btn_style = f"""
            QPushButton {{
                font-family: '{get_master_font()}';
                background-color: #1e293b;
                color: white;
                border: 1px solid #24334d;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #2c3e50;
                border: 1px solid #3b82f6;
            }}
            QPushButton:pressed {{
                background-color: #0f172a;
                /* Biru sangat gelap saat ditekan */
                border: 1px solid #2563eb;
            }}
        """
    else:
        btn_style = f"""
            QPushButton {{
                font-family: '{get_master_font()}';
                background-color: #edf2f7;
                color: #2d3748;
                border: 1px solid #cbd5e1;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #e2e8f0;
            }}
            QPushButton:pressed {{
                background-color: #cbd5e1;
                /* Abu-abu lebih pekat saat ditekan */
            }}
        """

    lbl_style = f"""
        font-family: '{get_master_font()}';
        font-size: 13px;
        color: #f59e0b;
        padding: 5px;
        margin-right: 10px;
    """

    return btn_style, lbl_style
