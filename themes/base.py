# themes/base.py
"""Stylesheet dasar aplikasi.

Layer ini hanya mendefinisikan baseline visual/QSS.
Responsive geometry diterapkan satu kali oleh ``utils.ui_scaler``.
"""

from typing import Optional

from utils.typography import get_master_font
from utils.ui_metrics import TAB_MIN_WIDTH, TAB_PADDING_H, TAB_PADDING_V


def _get_tab_geometry_qss(selector: str = "QTabBar::tab") -> str:
    """Bangun geometry QTabBar dari satu sumber baseline di ui_metrics."""
    selector = str(selector or "QTabBar::tab").strip()
    return f"""
        {selector} {{
            min-width: {TAB_MIN_WIDTH}px;
            padding: {TAB_PADDING_V}px {TAB_PADDING_H}px;
        }}
    """


def get_base_style(*, scale: Optional[float] = None) -> str:
    """Bangun stylesheet baseline aplikasi.

    ``scale`` dipertahankan untuk kompatibilitas caller lama. Layer theme tidak
    melakukan scaling agar tidak overlap/double-scale dengan ResponsiveUIScaler.
    """
    _ = scale

    # Logical-pixel baseline. ui_scaler yang mengubah ke ukuran final.
    padding_v = 4
    padding_h = 10
    combo_right = 28
    combo_left = 12

    return f"""
        QWidget {{
            font-family: "{get_master_font()}";
        }}

        QComboBox {{
            padding: {padding_v}px {padding_h}px;
            padding-right: {combo_right}px;
            padding-left: {combo_left}px;
        }}

        QComboBox QAbstractItemView {{
            padding-left: 5px;
        }}

        /* Satu geometry untuk seluruh subtab aplikasi. */
        {_get_tab_geometry_qss()}
    """
