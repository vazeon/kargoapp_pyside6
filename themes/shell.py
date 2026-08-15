# themes/shell.py
"""Style ringan untuk kerangka utama aplikasi."""

from themes.colors import get_theme_colors
from utils.typography import get_master_font


def get_main_shell_styles(is_dark: bool) -> dict:
    colors = get_theme_colors(is_dark)
    palette = colors["palette"]

    # Warna global mengikuti source of truth themes/colors.py.
    bg_main = palette["window"]
    bg_pane = palette["window"]
    text = palette["window_text"]

    # Warna berikut khusus shell/tab utama dan sengaja tetap lokal.
    if is_dark:
        bg_tab = "#242932"
        bg_tab_hover = "#2b313c"
        text_muted = "#aeb7c4"
        accent = "#4f9cff"
        border = "#3a414d"
    else:
        bg_tab = "#e9edf3"
        bg_tab_hover = "#f2f5f9"
        text_muted = "#475569"
        accent = "#2563eb"
        border = "#c8d0dc"

    return {
        "central": f"""
            QWidget#CentralWidget {{
                background-color: {bg_main};
                color: {text};
            }}
        """,
        "tabs": f"""
            QTabWidget#MainTabs {{
                background-color: transparent;
            }}
            QTabWidget#MainTabs::pane {{
                background-color: {bg_pane};
                border: 1px solid {border};
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
                top: -1px;
                /* Menarik pane tepat ke atas garis bawah tab */
            }}
            QTabWidget#MainTabs::tab-bar {{
                alignment: left;
            }}
        """,
        "tab_bar": f"""
            QTabBar#MainTabBar {{
                background-color: transparent;
                qproperty-drawBase: 0;
                /* Menghilangkan garis default Qt di bawah tab bar */
            }}
            QTabBar#MainTabBar::tab {{
                background-color: {bg_tab};
                color: {text_muted};
                font-family: "{get_master_font()}";
                font-size: 12px;
                font-weight: 500;
                min-width: 130px;
                padding: 11px 16px;
                margin-top: 4px;
                margin-right: 2px;
                border: 1px solid {border};
                border-bottom: 1px solid {border};
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }}
            QTabBar#MainTabBar::tab:selected {{
                background-color: {bg_pane};
                color: {text};
                font-weight: 600;
                font-size: 13px;
                border-left: 1px solid {border};
                border-right: 1px solid {border};
                border-top: 2px solid {accent};
                border-bottom: 1px solid {bg_pane};
                /* Menyamarkan garis bawah dengan warna background pane */
                margin-top: 2px;
                margin-bottom: -2px;
                /* Mendorong bagian bawah tab menutupi border top milik pane */
            }}
            QTabBar#MainTabBar::tab:hover:!selected {{
                background-color: {bg_tab_hover};
                color: {text};
                border-color: {accent};
            }}
            QTabBar#MainTabBar::tab:disabled {{
                background-color: transparent;
                color: {text_muted};
            }}
        """,
        "corner": "background-color: transparent;",
    }