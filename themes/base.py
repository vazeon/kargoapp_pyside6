# themes/base.py
"""Stylesheet dasar aplikasi."""

from typing import Optional

from utils.typography import get_master_font
from utils.ui_metrics import dapatkan_ui_metrics, skalakan_px


def get_base_style(*, scale: Optional[float] = None) -> str:
    """Bangun stylesheet dasar setelah QApplication/screen tersedia.

    ``scale`` opsional dipakai oleh ResponsiveUIScaler saat window berpindah
    monitor, sehingga stylesheet global ikut density screen aktif tanpa perlu
    menyimpan object QScreen.
    """
    if scale is None:
        ui = dapatkan_ui_metrics()
        padding_v = ui.input_padding_v
        padding_h = ui.input_padding_h
        combo_right = ui.combo_padding_right
    else:
        padding_v = skalakan_px(4, scale=scale, minimum=3, maximum=5)
        padding_h = skalakan_px(10, scale=scale, minimum=8, maximum=11)
        combo_right = skalakan_px(28, scale=scale, minimum=24, maximum=30)

    return f"""
        QWidget {{
            font-family: "{get_master_font()}";
        }}

        QComboBox {{
            padding: {padding_v}px {padding_h}px;
            padding-right: {combo_right}px;
        }}
    """