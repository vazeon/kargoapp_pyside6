# file: themes/shell.py
"""Style ringan untuk kerangka utama aplikasi."""

from themes.colors import get_theme_colors
from utils.typography import get_master_font


def get_main_shell_styles(is_dark: bool) -> str:
    colors = get_theme_colors(is_dark)
    palette = colors["palette"]
    ui = colors["ui"]

    # Warna global
    bg_main = ui["main_background"]
    bg_pane = ui["main_background"]
    text = palette["window_text"]

    if is_dark:
        bg_tab = "#242932"
        bg_tab_hover = "#2b313c"
        bg_tab_selected = ui["main_background"]
        text_muted = "#aeb7c4"
        accent = "#4f9cff"
        border = "#3a414d"

        # Warna Top Right
        btn_background = ui["panel_background"]
        btn_text = ui["on_primary"]
        btn_border = "#24334d"
        btn_hover_background = "#2c3e50"
        btn_pressed_background = palette["shadow"]
        hover_border_rule = f"border: 1px solid {ui['primary']};"
        pressed_border_rule = f"border: 1px solid {ui['primary_hover']};"
    else:
        bg_tab = "#e9edf3"
        bg_tab_hover = "#f2f5f9"
        bg_tab_selected = bg_pane
        text_muted = "#475569"
        accent = "#2563eb"
        border = "#c8d0dc"

        # Warna Top Right
        btn_background = "#edf2f7"
        btn_text = "#2d3748"
        btn_border = ui["field_border"]
        btn_hover_background = palette["button"]
        btn_pressed_background = ui["field_border"]
        hover_border_rule = ""
        pressed_border_rule = ""

    return f"""
        /* --- CENTRAL WIDGET --- */
        QWidget#CentralWidget {{
            background-color: {bg_main};
            color: {text};
        }}

        /* --- TABS --- */
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
        }}

        /* --- TAB BAR --- */
        QTabBar#MainTabBar {{
            background-color: transparent;
            qproperty-drawBase: 0;
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
            background-color: {bg_tab_selected};
            color: {text};
            font-weight: 600;
            font-size: 13px;
            border-left: 1px solid {border};
            border-right: 1px solid {border};
            border-top: 2px solid {accent};
            border-bottom: 1px solid {bg_tab_selected};
            margin-top: 2px;
            margin-bottom: -2px;
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

        /* --- TOP RIGHT CONTAINER & KOMPONEN --- */
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