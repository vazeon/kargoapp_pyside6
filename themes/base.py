# themes/base.py
"""Stylesheet dasar aplikasi.

Layer ini hanya mendefinisikan baseline visual/QSS.
Responsive geometry diterapkan satu kali oleh ``utils.ui_scaler``.
"""

import re
from functools import lru_cache
from typing import Optional

from themes.colors import get_theme_colors
from utils.typography import get_master_font
from utils.ui_metrics import (
    MAIN_TAB_BAR_MIN_HEIGHT,
    TAB_MIN_WIDTH,
    TAB_PADDING_H,
    TAB_PADDING_V,
)


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


@lru_cache(maxsize=4)
def _ambil_qdark_tab_rules(qss: str) -> str:
    """Ambil hanya rule QTabWidget/QTabBar dari stylesheet qdarktheme."""
    if not qss:
        return ""

    hasil = []
    for selector_blob, deklarasi in re.findall(
        r"([^{}]+)\{([^{}]*)\}",
        qss,
        flags=re.DOTALL,
    ):
        selectors = [
            selector.strip()
            for selector in selector_blob.split(",")
            if selector.strip()
        ]
        selectors_tab = [
            selector
            for selector in selectors
            if "QTabWidget" in selector or "QTabBar" in selector
        ]
        if not selectors_tab:
            continue

        hasil.append(
            ", ".join(selectors_tab)
            + " {\n"
            + deklarasi.strip()
            + "\n}"
        )

    return "\n".join(hasil)


def get_main_tabs_base_style(
    is_dark: bool,
    *,
    scale: Optional[float] = None,
    qdark_stylesheet: str = "",
) -> str:
    """Style shell tab utama.

    State/warna tab tetap mengikuti qdarktheme. Hanya geometry tab utama yang
    dioverride dari baseline global yang sama dengan seluruh subtab.
    """
    ui = get_theme_colors(is_dark)["ui"]
    background = ui["main_background"]
    border = ui["panel_border"]
    _ = scale

    qdark_tabs = _ambil_qdark_tab_rules(qdark_stylesheet)
    main_tab_geometry = _get_tab_geometry_qss("QTabBar#MainTabBar::tab")

    return f"""
        {qdark_tabs}

        /* Main tab memakai sumber ukuran yang sama dengan seluruh subtab. */
        {main_tab_geometry}

        /* Beri napas di sisi atas khusus tab utama. */
        QTabBar#MainTabBar {{
            min-height: {MAIN_TAB_BAR_MIN_HEIGHT}px;
        }}

        QTabBar#MainTabBar::tab {{
            margin-top: 4px;
        }}

        QTabWidget#MainTabs {{
            background-color: transparent;
        }}

        QTabWidget#MainTabs::pane {{
            background-color: {background};
            border: 1px solid {border};
            border-top-left-radius: 0px;
            border-top-right-radius: 0px;
            border-bottom-left-radius: 0px;
            border-bottom-right-radius: 0px;
            top: -1px;
        }}

        QTabWidget#MainTabs > QWidget#qt_tabwidget_stackedwidget {{
            background-color: {background};
        }}

        QTabWidget#MainTabs > QWidget#qt_tabwidget_stackedwidget > QWidget {{
            background-color: {background};
        }}
    """