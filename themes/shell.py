# themes/shell.py
"""Stylesheet shell utama dengan scope yang sesuai sasaran widget.

Style QTabBar utama diterapkan langsung ke MainTabBar. Style tombol/label shell
kanan atas diterapkan ke ContainerTopRight. Dengan pemisahan ini, aturan untuk
widget di luar subtree target tidak ikut ditulis ulang di stylesheet yang salah.
"""

import re
from functools import lru_cache

from themes.colors import get_theme_colors
from utils.typography import get_master_font
from utils.ui_metrics import (
    MAIN_TAB_BAR_MIN_HEIGHT,
    TAB_MIN_WIDTH,
    TAB_PADDING_H,
    TAB_PADDING_V,
)


@lru_cache(maxsize=4)
def _ambil_qdark_tabbar_rules(qss: str) -> str:
    """Ambil aturan QTabBar dari stylesheet QDarkTheme saja."""
    if not qss:
        return ""

    hasil = []
    for selector_blob, deklarasi in re.findall(
        r"([^{}]+)\{([^{}]*)}",
        qss,
        flags=re.DOTALL,
    ):
        selectors = [
            selector.strip()
            for selector in selector_blob.split(",")
            if selector.strip()
        ]
        selectors_tabbar = [
            selector for selector in selectors if "QTabBar" in selector
        ]
        if not selectors_tabbar:
            continue

        hasil.append(
            ", ".join(selectors_tabbar)
            + " {\n"
            + deklarasi.strip()
            + "\n}"
        )

    return "\n".join(hasil)


def get_main_tab_bar_style(*, qdark_stylesheet: str = "") -> str:
    """Style QTabBar utama; geometri bersumber dari utils.ui_metrics."""
    qdark_tabs = _ambil_qdark_tabbar_rules(qdark_stylesheet)

    return f"""
        {qdark_tabs}

        /* Geometri tab utama mengikuti sumber metrik global. */
        QTabBar#MainTabBar::tab {{
            min-width: {TAB_MIN_WIDTH}px;
            padding: {TAB_PADDING_V}px {TAB_PADDING_H}px;
            margin-top: 4px;
        }}

        QTabBar#MainTabBar {{
            min-height: {MAIN_TAB_BAR_MIN_HEIGHT}px;
        }}
    """


def get_main_shell_styles(is_dark: bool) -> str:
    """Style komponen di dalam ContainerTopRight saja."""
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

    return f"""
        QWidget#ContainerTopRight {{
            background-color: transparent;
        }}
        QPushButton[class="TopRightButton"] {{
            font-family: "{get_master_font()}";
            background-color: {btn_background};
            color: {btn_text};
            border: 1px solid {btn_border};
            font-weight: bold;
            border-radius: 10px;
            padding: 4px;
        }}
        QPushButton[class="TopRightButton"]:hover {{
            background-color: {btn_hover_background};
            {hover_border_rule}
        }}
        QPushButton[class="TopRightButton"]:pressed {{
            background-color: {btn_pressed_background};
            {pressed_border_rule}
        }}
        QLabel#LabelCabang {{
            font-family: "{get_master_font()}";
            font-size: 13px;
            color: #f59e0b;
            padding: 5px;
            margin-right: 10px;
        }}
    """
