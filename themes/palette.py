# themes/palette.py

"""Palette warna terang dan gelap aplikasi."""

from PySide6.QtGui import QColor, QPalette

from themes.colors import get_theme_colors


def get_theme_palette(is_dark: bool) -> QPalette:
    """Membuat palette gelap/terang tanpa mengganti stylesheet global."""
    palette = QPalette()
    theme_colors = get_theme_colors(is_dark)
    colors = theme_colors["palette"]

    role_colors = {
        QPalette.ColorRole.Window: colors["window"],
        QPalette.ColorRole.WindowText: colors["window_text"],
        QPalette.ColorRole.Base: colors["base"],
        QPalette.ColorRole.AlternateBase: colors["alternate_base"],
        QPalette.ColorRole.ToolTipBase: colors["tooltip_base"],
        QPalette.ColorRole.ToolTipText: colors["tooltip_text"],
        QPalette.ColorRole.Text: colors["text"],
        QPalette.ColorRole.PlaceholderText: colors["placeholder_text"],
        QPalette.ColorRole.Button: colors["button"],
        QPalette.ColorRole.ButtonText: colors["button_text"],
        QPalette.ColorRole.BrightText: colors["bright_text"],
        QPalette.ColorRole.Link: colors["link"],
        QPalette.ColorRole.Highlight: colors["highlight"],
        QPalette.ColorRole.HighlightedText: colors["highlighted_text"],
        QPalette.ColorRole.Light: colors["light"],
        QPalette.ColorRole.Midlight: colors["midlight"],
        QPalette.ColorRole.Mid: colors["mid"],
        QPalette.ColorRole.Dark: colors["dark"],
        QPalette.ColorRole.Shadow: colors["shadow"],
    }

    for role, color in role_colors.items():
        palette.setColor(role, QColor(color))

    disabled_color = QColor(colors["disabled_text"])
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        disabled_color,
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        disabled_color,
    )

    return palette