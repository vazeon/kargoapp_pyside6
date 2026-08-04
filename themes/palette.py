# themes/pallete.py

"""Palette warna terang dan gelap aplikasi."""

from PySide6.QtGui import QColor, QPalette


def get_theme_palette(is_dark: bool) -> QPalette:
    """Membuat palette gelap/terang tanpa mengganti stylesheet global."""
    palette = QPalette()

    if is_dark:
        colors = {
            QPalette.ColorRole.Window: "#1a1d24",
            QPalette.ColorRole.WindowText: "#f8fafc",
            QPalette.ColorRole.Base: "#1a1d24",
            QPalette.ColorRole.AlternateBase: "#20242b",
            QPalette.ColorRole.ToolTipBase: "#0f172a",
            QPalette.ColorRole.ToolTipText: "#f8fafc",
            QPalette.ColorRole.Text: "#f8fafc",
            QPalette.ColorRole.Button: "#1e222b",
            QPalette.ColorRole.ButtonText: "#f8fafc",
            QPalette.ColorRole.BrightText: "#ffffff",
            QPalette.ColorRole.Link: "#60a5fa",
            QPalette.ColorRole.Highlight: "#3b82f6",
            QPalette.ColorRole.HighlightedText: "#ffffff",
            QPalette.ColorRole.Light: "#475569",
            QPalette.ColorRole.Midlight: "#3f434d",
            QPalette.ColorRole.Mid: "#4c525e",
            QPalette.ColorRole.Dark: "#64748b",
            QPalette.ColorRole.Shadow: "#0f172a",
        }
    else:
        colors = {
            QPalette.ColorRole.Window: "#f8fafc",
            QPalette.ColorRole.WindowText: "#0f172a",
            QPalette.ColorRole.Base: "#ffffff",
            QPalette.ColorRole.AlternateBase: "#f1f5f9",
            QPalette.ColorRole.ToolTipBase: "#ffffff",
            QPalette.ColorRole.ToolTipText: "#0f172a",
            QPalette.ColorRole.Text: "#0f172a",
            QPalette.ColorRole.Button: "#e2e8f0",
            QPalette.ColorRole.ButtonText: "#0f172a",
            QPalette.ColorRole.BrightText: "#000000",
            QPalette.ColorRole.Link: "#2563eb",
            QPalette.ColorRole.Highlight: "#2563eb",
            QPalette.ColorRole.HighlightedText: "#ffffff",
            QPalette.ColorRole.Light: "#ffffff",
            QPalette.ColorRole.Midlight: "#e2e8f0",
            QPalette.ColorRole.Mid: "#94a3b8",
            QPalette.ColorRole.Dark: "#64748b",
            QPalette.ColorRole.Shadow: "#334155",
        }

    for role, color in colors.items():
        palette.setColor(role, QColor(color))

    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor("#94a3b8"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor("#94a3b8"),
    )

    return palette
