# themes/components.py
"""Style komponen umum yang dipakai lintas tab."""

from utils.typography import MASTER_FONT

FADE_NOTIFICATION_STYLE = f"""
    QLabel {{
        background-color: rgba(15, 23, 42, 0.95);
        color: #10b981;
        font-size: 22px;
        font-weight: bold;
        border-radius: 12px;
        padding: 20px 50px;
        border: 2px solid #10b981;
        font-family: '{MASTER_FONT}';
    }}
"""

COMBOBOX_STYLE_MARKER = "/* GLOBAL_COMBOBOX_STYLE */"


def get_combobox_style(is_dark: bool = False) -> str:
    """Style dropdown QComboBox yang konsisten pada seluruh tab."""

    # Kita hanya menyisakan warna untuk border dan popup item-nya saja
    border = "#4c525e" if is_dark else "#cbd5e1"
    popup_bg = "#1d2024" if is_dark else "#ffffff"
    popup_text = "#f8fafc" if is_dark else "#111827"

    return f"""
        {COMBOBOX_STYLE_MARKER} QComboBox {{
            /* Hapus padding-right: 30px karena sistem operasi sudah mengaturnya secara otomatis */
            padding: 2px;
        }}
        /* Kita biarkan styling list pilihan (popup) saat diklik agar tetap rapi */
        QComboBox QAbstractItemView {{
            background-color: {popup_bg};
            color: {popup_text};
            border: 1px solid {border};
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            outline: none;
        }}
    """


def terapkan_style_combobox(comboboxes, is_dark: bool = False) -> None:
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