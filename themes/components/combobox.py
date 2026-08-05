# themes/components/combobox.py

"""Style QComboBox yang dipakai lintas tab aplikasi."""

from __future__ import annotations


COMBOBOX_STYLE_MARKER = "/* GLOBAL_COMBOBOX_STYLE */"


def get_combobox_style(is_dark: bool = False) -> str:
    """Style dropdown QComboBox yang konsisten pada seluruh tab."""

    border = "#4c525e" if is_dark else "#cbd5e1"
    popup_bg = "#1d2024" if is_dark else "#ffffff"
    popup_text = "#f8fafc" if is_dark else "#111827"

    return f"""
        {COMBOBOX_STYLE_MARKER} QComboBox {{
            padding: 2px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {popup_bg};
            color: {popup_text};
            border: 1px solid {border};
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            outline: none;
        }}
    """


def terapkan_style_combobox(
    comboboxes,
    is_dark: bool = False,
) -> None:
    """Tambahkan style dropdown tanpa menghapus style dasar modul."""

    style_global = get_combobox_style(is_dark)

    for combo in comboboxes:
        if combo is None:
            continue

        style_dasar = combo.styleSheet().split(
            COMBOBOX_STYLE_MARKER,
            1,
        )[0].rstrip()

        combo.setStyleSheet(
            f"{style_dasar}\n{style_global}"
            if style_dasar
            else style_global
        )