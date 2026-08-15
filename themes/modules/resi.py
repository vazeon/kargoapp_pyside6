# themes/modules/resi.py
from themes.colors import get_theme_colors
from utils.typography import get_master_font


# Caller ukuran font khusus Tab Resi.
# Ubah nilai di sini untuk menyesuaikan tipografi tanpa menyentuh kode widget.
UKURAN_FONT_LABEL = 13
UKURAN_FONT_INPUT = 13
UKURAN_FONT_TOTAL_ONGKIR = 16
UKURAN_FONT_CARD_REKENING_BANK = 13
UKURAN_FONT_HISTORI_RESI = 13


def _warna_tema(is_dark: bool, gelap: str, terang: str) -> str:
    """Pilih warna tanpa menjauhkan kode warna dari blok style pemakainya."""
    return gelap if is_dark else terang


def get_resi_static_styles(is_dark: bool) -> dict:
    """Style awal yang dapat dipakai sebelum proses refresh tema lengkap."""
    ui = get_theme_colors(is_dark)["ui"]
    return {
        "scroll_kiri": f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
        """,
        "rekening_card": f"""
            background-color: {_warna_tema(is_dark, "#1d2024", "#f8fafc")};
            border: 1px solid {_warna_tema(is_dark, "#3f434d", "#cbd5e1")};
            border-radius: 6px;
        """,
    }


def get_resi_rekening_styles(is_dark: bool, z: int = 0) -> dict:
    """Style dinamis kartu dan kelompok rekening pada TabResi."""
    ui = get_theme_colors(is_dark)["ui"]

    return {
        "group_box": f"""
            QGroupBox {{
                font-weight: 500;
                font-size: {UKURAN_FONT_LABEL}px;
                font-family: '{get_master_font()}';
                color: {_warna_tema(is_dark, "#94a3b8", "#64748b")};
                border: 1px solid {_warna_tema(is_dark, "#3f434d", "#cbd5e1")};
                border-radius: 8px;
                margin-top: 3px;
                padding-top: 20px;
                background-color: {_warna_tema(is_dark, "#181a1e", "#ffffff")};
            }}
            QGroupBox::title {{
                font-size: {UKURAN_FONT_LABEL}px;
                font-weight: 500;
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                top: 10px;
                padding: 0 4px;
            }}
        """,
        "label_top": f"""
            color: {_warna_tema(is_dark, "#e2e8f0", "#334155")};
            font-size: {UKURAN_FONT_CARD_REKENING_BANK}px;
            border: none;
            background: transparent;
            font-family: '{get_master_font()}';
        """,
        "label_bottom": f"""
            color: {_warna_tema(is_dark, "#a8b3c5", "#64748b")};
            font-size: {UKURAN_FONT_CARD_REKENING_BANK}px;
            font-weight: normal;
            border: none;
            background: transparent;
            font-family: '{get_master_font()}';
        """,
        "card": f"""
            background-color: {_warna_tema(is_dark, "#1d2024", "#f8fafc")};
            border: 1px solid {_warna_tema(is_dark, "#3f434d", "#cbd5e1")};
            border-radius: 6px;
        """,
    }


def get_resi_detail_barang_theme(
    is_dark: bool,
    sz_base: int,
) -> dict:
    """Warna dan style khusus tabel Detail Barang tanpa mengubah scrollbar."""
    ui = get_theme_colors(is_dark)["ui"]
    placeholder = ui["placeholder_text"]

    return {
        "background": ui["field_background"],
        "alternate_background": _warna_tema(is_dark, "#25282e", "#f8fafc"),
        "text": ui["text_primary"],
        "grid": _warna_tema(is_dark, "#2d3139", "#e2e8f0"),
        "selection_background": ui["selection_background"],
        "selection_text": "#ffffff",

        "header": f"""
            QHeaderView::section {{
                font-size: {UKURAN_FONT_INPUT}px;
                font-family: '{get_master_font()}';
                background-color: {_warna_tema(is_dark, "#31353d", "#243752")};
                color: #ffffff;
                font-weight: 500;
                padding: 6px;
                border: none;
                border-right: 2px solid {_warna_tema(is_dark, "#64748b", "#a8b7c8")};
                border-bottom: 1px solid {_warna_tema(is_dark, "#64748b", "#a8b7c8")};
            }}
        """,

        "cell_input": f"""
            QLineEdit {{
                font-size: {UKURAN_FONT_INPUT}px;
                font-family: '{get_master_font()}';
                background-color: {ui["field_background"]};
                color: {ui["text_primary"]};
                placeholder-text-color: {placeholder};
                border: 1px solid {ui["field_border"]};
                border-radius: 0px;
                padding: 4px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ui["selection_background"]};
            }}
        """,
    }


def get_btn_simpan_cetak_style() -> str:
    """Style tombol utama Simpan dan Cetak khusus untuk TabResi."""
    return f"""
        QPushButton {{
            background-color: #22c55e;
            color: white;
            font-weight: 500;
            font-size: 14px;
            padding: 10px 40px;
            border-radius: 6px;
            border: none;
            font-family: '{get_master_font()}';
        }}
        QPushButton:hover {{
            background-color: #16a34a;
        }}
        QPushButton:pressed {{
            background-color: #15803d;
        }}
        QPushButton:focus {{
            border: 2px solid #ef4444;
        }}
    """


def get_resi_styles(
    is_dark: bool,
    sz_title: int,
    sz_tag: int,
    sz_sm: int,
    sz_base: int,
    sz_input: int,
    sz_total: int,
    z: int = 0,
) -> dict:
    """Menghasilkan seluruh style UI untuk TabResi."""
    ui = get_theme_colors(is_dark)["ui"]
    placeholder = ui["placeholder_text"]
    input_style = f"""
        QLineEdit, QTextEdit, QDateEdit {{
            font-size: {UKURAN_FONT_INPUT}px;
            background-color: {ui["field_background"]};
            color: {ui["text_primary"]};
            border: 1px solid {ui["field_border"]};
            border-radius: 4px;
            padding: 6px;
            font-family: '{get_master_font()}';
        }}
        QLineEdit, QTextEdit {{
            placeholder-text-color: {placeholder};
        }}
        QLineEdit:focus, QTextEdit:focus, QDateEdit:focus {{
            border: 1px solid {ui["selection_background"]};
            background-color: {ui["field_focus_background"]};
        }}
    """

    qss_group_umum = f"""
        QGroupBox {{
            font-weight: 500;
            font-size: {sz_base}px;
            color: {ui["text_primary"]};
            background-color: {_warna_tema(is_dark, "#25282e", "#ffffff")};
            border: 1px solid {_warna_tema(is_dark, "#3f434d", "#cbd5e1")};
            border-radius: 8px;
            margin-top: 2px;
            padding: 0px;
            font-family: '{get_master_font()}';
        }}
        QGroupBox::title {{
            color: {ui["text_primary"]};
        }}
        QLabel {{
            color: {_warna_tema(is_dark, "#cbd5e1", "#1e293b")};
            font-size: {UKURAN_FONT_LABEL}px;
            font-weight: 500;
            background-color: transparent;
            font-family: '{get_master_font()}';
        }}
        {input_style}
    """

    qss_group_tabel = f"""
        QGroupBox {{
            font-weight: 500;
            font-size: {sz_base}px;
            color: {ui["text_primary"]};
            background-color: {_warna_tema(is_dark, "#25282e", "#ffffff")};
            border: 1px solid {_warna_tema(is_dark, "#3f434d", "#cbd5e1")};
            border-radius: 8px;
            margin-top: 2px;
            padding: 0px;
            font-family: '{get_master_font()}';
        }}
        QGroupBox::title {{
            color: {ui["text_primary"]};
        }}
        QLabel {{
            color: {_warna_tema(is_dark, "#cbd5e1", "#1e293b")};
            font-size: {UKURAN_FONT_LABEL}px;
            font-family: '{get_master_font()}';
        }}
    """

    rekening_styles = get_resi_rekening_styles(is_dark, z)
    static_styles = get_resi_static_styles(is_dark)

    return {
        "lbl_main_title": f"""
            color: {ui["text_primary"]};
            font-size: {sz_title}px;
            font-weight: 500;
            margin-bottom: 1px;
            font-family: '{get_master_font()}';
        """,
        "lbl_tgl_tag": f"""
            color: {_warna_tema(is_dark, "#9ca3af", "#64748b")};
            font-weight: 500;
            font-family: '{get_master_font()}';
            font-size: {UKURAN_FONT_LABEL}px;
        """,
        "lbl_resi_tag": f"""
            color: {_warna_tema(is_dark, "#9ca3af", "#64748b")};
            font-size: {UKURAN_FONT_LABEL}px;
            font-weight: 500;
            font-family: '{get_master_font()}';
        """,
        "lbl_histori_title": f"""
            color: {ui["text_primary"]};
            font-size: {UKURAN_FONT_HISTORI_RESI}px;
            font-weight: 500;
            font-family: '{get_master_font()}';
        """,
        "txt_resi_display": f"""
            background-color: {_warna_tema(is_dark, "#1d2024", "#F2FCFF")};
            border: 1px solid {_warna_tema(is_dark, "#3b82f6", "#3b82f6")};
            border-radius: 6px;
            padding: 6px 12px;
            color: {_warna_tema(is_dark, "#fbbf24", "#3b82f6")};
            font-weight: 500;
            font-size: {sz_total}px;
            letter-spacing: 1px;
            font-family: '{get_master_font()}';
        """,
        "date_input": f"""
            QDateEdit {{
                font-size: {UKURAN_FONT_INPUT}px;
                font-family: '{get_master_font()}';
                padding: 2px 10px;
                border: 1px solid {ui["field_border"]};
                border-radius: 4px;
                background-color: {ui["field_background"]};
                color: {ui["text_primary"]};
            }}
        """,
        "list_histori": f"""
            QListWidget {{
                background-color: {ui["field_background"]};
                color: {_warna_tema(is_dark, "#cbd5e1", "#1e293b")};
                border: 1px solid {ui["field_border"]};
                border-radius: 6px;
                padding: 5px;
                font-size: {UKURAN_FONT_HISTORI_RESI}px;
                font-family: '{get_master_font()}';
            }}
            QListWidget::item {{
                padding: 6px;
            }}
        """,
        "txt_search": f"""
            QLineEdit {{
                font-size: {UKURAN_FONT_INPUT}px;
                background-color: {ui["field_background"]};
                color: {ui["text_primary"]};
                placeholder-text-color: {placeholder};
                border: 1px solid {ui["field_border"]};
                border-radius: 4px;
                padding: 6px;
                font-family: '{get_master_font()}';
            }}
        """,
        "btn_reset_tgl": f"""
            QPushButton {{
                background-color: #ef4444;
                color: white;
                font-weight: 500;
                border-radius: 4px;
                padding: 4px;
                font-size: {sz_sm}px;
                font-family: '{get_master_font()}';
            }}
            QPushButton:hover {{
                background-color: #dc2626;
                /* Merah yang sedikit lebih gelap */
            }}
            QPushButton:pressed {{
                background-color: #b91c1c;
                /* Merah tua saat ditekan */
            }}
        """,
        "group_pengirim": qss_group_umum,
        "group_penerima": qss_group_umum,
        "group_finance": qss_group_umum,
        "group_tabel_container": qss_group_tabel,
        "btn_tambah_baris": f"""
            QPushButton {{
                font-size: {sz_base}px;
                background-color: {_warna_tema(is_dark, "#31353d", "#ffffff")};
                color: {ui["selection_background"]};
                border: 1px solid {ui["selection_background"]};
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 500;
                font-family: '{get_master_font()}';
            }}
            QPushButton:hover {{
                background-color: {_warna_tema(is_dark, "#1e293b", "#eff6ff")};
            }}
            QPushButton:pressed {{
                background-color: {_warna_tema(is_dark, "#172554", "#dbeafe")};
            }}
        """,
        "btn_hapus_baris": f"""
            QPushButton {{
                font-size: {sz_base}px;
                background-color: {_warna_tema(is_dark, "#31353d", "#ffffff")};
                color: {_warna_tema(is_dark, "#ef4444", "#dc2626")};
                border: 1px solid {_warna_tema(is_dark, "#4c525e", "#fca5a5")};
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 500;
                font-family: '{get_master_font()}';
            }}
            QPushButton:hover {{
                background-color: {_warna_tema(is_dark, "#3f2324", "#fef2f2")};
                border-color: {_warna_tema(is_dark, "#ef4444", "#dc2626")};
            }}
            QPushButton:pressed {{
                background-color: {_warna_tema(is_dark, "#450a0a", "#fee2e2")};
                border-color: {_warna_tema(is_dark, "#ef4444", "#dc2626")};
            }}
        """,
        "txt_total_ongkir": f"""
            QLineEdit {{
                font-size: {UKURAN_FONT_TOTAL_ONGKIR}px;
                font-weight: 500;
                color: {ui["selection_background"]};
                placeholder-text-color: {placeholder};
                background-color: {ui["field_background"]};
                border: 1px solid {ui["field_border"]};
                padding: 6px;
                font-family: '{get_master_font()}';
            }}
        """,
        "input_utama": input_style,
        "scroll_kiri": static_styles["scroll_kiri"],

        "btn_generate_simpan": get_btn_simpan_cetak_style(),
        "lbl_reset_form": f"""
            QPushButton {{
                color: #ef4444;
                background-color: transparent;
                border: 2px solid transparent;
                border-radius: 6px;
                padding: 5px 9px;
                font-weight: 600;
                text-align: left;
                font-family: '{get_master_font()}';
            }}
            QPushButton:hover {{
                color: #b91c1c;
            }}
            QPushButton:focus {{
                border: 1px solid #3b82f6;
            }}
        """,
        "box_np": rekening_styles["group_box"],
        "box_p": rekening_styles["group_box"],
    }


def get_btn_clear_container_style(is_dark: bool = False) -> str:
    """Style QToolButton reset/clear container khusus untuk Tab Resi."""
    ui = get_theme_colors(is_dark)["ui"]
    return f"""
        QToolButton {{
            color: {_warna_tema(is_dark, "#d1d5db", "#808d8b")};
            background-color: transparent;
            border: none;
            border-radius: 4px;
            font-size: 16pt;
            font-weight: 400;
            padding: 0px;
            font-family: '{get_master_font()}';
        }}
        QToolButton:hover {{
            color: {_warna_tema(is_dark, "#f87171", "#ef4444")};
            background-color: transparent;
        }}
        QToolButton:pressed {{
            color: {_warna_tema(is_dark, "#ef4444", "#b91c1c")};
            background-color: transparent;
            /* Opsional: Efek sedikit geser ke bawah saat diklik agar terasa 'membal' */
            padding-top: 2px;
        }}
        QToolTip {{
            background-color: {ui["field_background"]};
            color: {_warna_tema(is_dark, "#ffffff", "#000000")};
            border: 1px solid {_warna_tema(is_dark, "#4c525e", "#d1d5db")};
            padding: 2px 5px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: normal;
            font-family: '{get_master_font()}';
        }}
    """