# themes/modules/resi.py
from utils.typography import get_master_font, get_global_font_sizes


def get_resi_static_styles(is_dark: bool) -> dict:
    """Style awal yang dapat dipakai sebelum proses refresh tema lengkap."""
    if is_dark:
        bg_card = "#1d2024"
        border_card = "#3f434d"
    else:
        bg_card = "#f8fafc"
        border_card = "#cbd5e1"

    return {
        "scroll_kiri": f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
        """,
        "rekening_card": f"""
            background-color: {bg_card};
            border: 1px solid {border_card};
            border-radius: 6px;
        """,
    }


def get_resi_rekening_styles(is_dark: bool, z: int = 0) -> dict:
    """Style dinamis kartu dan kelompok rekening pada TabResi."""
    txt_top_color = "#ffffff" if is_dark else "#0f172a"
    txt_bottom_color = "#64748b"
    bg_card = "#1d2024" if is_dark else "#f8fafc"
    border_card = "#3f434d" if is_dark else "#cbd5e1"
    group_text = "#94a3b8" if is_dark else "#64748b"
    group_bg = "#181a1e" if is_dark else "#ffffff"

    sizes = get_global_font_sizes(z)
    sz_sm = sizes["sz_sm"]
    sz_card_title = max(11, 13 + z)
    sz_card_desc = max(10, 12 + z)

    return {
        "group_box": f"""
            QGroupBox {{
                font-weight: bold;
                font-size: {sz_sm}px;
                font-family: '{get_master_font()}';
                color: {group_text};
                border: 1px solid {border_card};
                border-radius: 8px;
                margin-top: 3px;
                padding-top: 20px;
                background-color: {group_bg};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                top: 10px;
                padding: 0 4px;
            }}
        """,
        "label_top": f"""
            color: {txt_top_color};
            font-size: {sz_card_title}px;
            border: none;
            background: transparent;
            font-family: '{get_master_font()}';
        """,
        "label_bottom": f"""
            color: {txt_bottom_color};
            font-size: {sz_card_desc}px;
            font-weight: normal;
            border: none;
            background: transparent;
            font-family: '{get_master_font()}';
        """,
        "card": f"""
            background-color: {bg_card};
            border: 1px solid {border_card};
            border-radius: 6px;
        """,
    }


def get_resi_detail_barang_theme(
    is_dark: bool,
    sz_base: int,
) -> dict:
    """Warna dan style khusus tabel Detail Barang tanpa mengubah scrollbar."""

    if is_dark:
        table_bg = "#1d2024"
        table_alt = "#25282e"
        table_text = "#ffffff"
        table_grid = "#2d3139"
        input_border = "#4c525e"
        placeholder = "#9ca3af"
        header_bg = "#31353d"
        header_separator = "#64748b"
        selection_bg = "#3b82f6"
    else:
        table_bg = "#ffffff"
        table_alt = "#f8fafc"
        table_text = "#0f172a"
        table_grid = "#e2e8f0"
        input_border = "#cbd5e1"
        placeholder = "#94a3b8"
        header_bg = "#243752"
        header_separator = "#a8b7c8"
        selection_bg = "#2563eb"

    return {
        "background": table_bg,
        "alternate_background": table_alt,
        "text": table_text,
        "grid": table_grid,
        "selection_background": selection_bg,
        "selection_text": "#ffffff",

        "header": f"""
            QHeaderView::section {{
                font-size: {sz_base}px;
                font-family: '{get_master_font()}';
                background-color: {header_bg};
                color: #ffffff;
                font-weight: bold;
                padding: 6px;
                border: none;
                border-right: 2px solid {header_separator};
                border-bottom: 1px solid {header_separator};
            }}
        """,

        "cell_input": f"""
            QLineEdit {{
                font-size: {sz_base}px;
                font-family: '{get_master_font()}';
                background-color: {table_bg};
                color: {table_text};
                border: 1px solid {input_border};
                border-radius: 0px;
                padding: 4px;
            }}
            QLineEdit:focus {{
                border: 1px solid {selection_bg};
            }}
            QLineEdit[custom_italic="true"][is_empty="true"] {{
                font-style: italic;
                color: {placeholder};
            }}
            QLineEdit[custom_italic="true"][is_empty="false"] {{
                font-style: normal;
            }}
        """,
    }


def get_btn_simpan_cetak_style(z: int = 0) -> str:
    """Style tombol utama Simpan dan Cetak khusus untuk TabResi."""
    return f"""
        QPushButton {{
            background-color: #22c55e;
            color: white;
            font-weight: bold;
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
    if is_dark:
        c_bg, c_card, c_bord, c_bord_card = (
            "#1d2024",
            "#25282e",
            "#4c525e",
            "#3f434d",
        )
        c_text, c_text_mut, c_text_dim = "#ffffff", "#cbd5e1", "#9ca3af"
        c_foc, c_bg_foc = "#3b82f6", "#20242b"
        c_hist_bg = "#25282e"
        c_resi_bg, c_resi_bord, c_resi_txt = "#1d2024", "#3b82f6", "#fbbf24"

        c_btn_add_bg, c_btn_add_txt, c_btn_add_bord = "#31353d", "#3b82f6", "#3b82f6"
        c_btn_add_hover_bg = "#1e293b"
        c_btn_add_pressed_bg = "#172554"

        c_btn_del_bg, c_btn_del_txt, c_btn_del_bord = "#31353d", "#ef4444", "#4c525e"
        c_btn_del_hover_bg = "#3f2324"
        c_btn_del_pressed_bg = "#450a0a"
    else:
        c_bg, c_card, c_bord, c_bord_card = (
            "#ffffff",
            "#ffffff",
            "#cbd5e1",
            "#cbd5e1",
        )
        c_text, c_text_mut, c_text_dim = "#0f172a", "#1e293b", "#64748b"
        c_foc, c_bg_foc = "#2563eb", "#ffffff"
        c_hist_bg = "#f1f5f9"
        c_resi_bg, c_resi_bord, c_resi_txt = "#fef2f2", "#ef4444", "#b91c1c"

        c_btn_add_bg, c_btn_add_txt, c_btn_add_bord = "#ffffff", "#2563eb", "#2563eb"
        c_btn_add_hover_bg = "#eff6ff"
        c_btn_add_pressed_bg = "#dbeafe"

        c_btn_del_bg, c_btn_del_txt, c_btn_del_bord = "#ffffff", "#dc2626", "#fca5a5"
        c_btn_del_hover_bg = "#fef2f2"
        c_btn_del_pressed_bg = "#fee2e2"

    input_style = f"""
        QLineEdit, QTextEdit, QComboBox, QDateEdit {{
            font-size: {sz_input}px;
            background-color: {c_bg};
            color: {c_text};
            border: 1px solid {c_bord};
            border-radius: 4px;
            padding: 6px;
            font-family: '{get_master_font()}';
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus {{
            border: 1px solid {c_foc};
            background-color: {c_bg_foc};
        }}
        QLineEdit[custom_italic="true"][is_empty="true"],
        QTextEdit[custom_italic="true"][is_empty="true"] {{
            font-style: italic;
            font-size: {sz_input}px;
            color: {c_text_dim};
        }}
        QLineEdit[custom_italic="true"][is_empty="false"],
        QTextEdit[custom_italic="true"][is_empty="false"] {{
            font-style: normal;
        }}
    """

    qss_group_umum = f"""
        QGroupBox {{
            font-weight: bold;
            font-size: {sz_base}px;
            color: {c_text};
            background-color: {c_card};
            border: 1px solid {c_bord_card};
            border-radius: 8px;
            margin-top: 2px;
            padding: 8px 12px;
            font-family: '{get_master_font()}';
        }}
        QGroupBox::title {{
            color: {c_text};
        }}
        QLabel {{
            color: {c_text_mut};
            font-size: {sz_sm}px;
            font-weight: bold;
            background-color: transparent;
            font-family: '{get_master_font()}';
        }}
        {input_style}
    """

    qss_group_tabel = f"""
        QGroupBox {{
            font-weight: bold;
            font-size: {sz_base}px;
            color: {c_text};
            background-color: {c_card};
            border: 1px solid {c_bord_card};
            border-radius: 8px;
            margin-top: 2px;
            padding: 6px 12px;
            font-family: '{get_master_font()}';
        }}
        QGroupBox::title {{
            color: {c_text};
        }}
        QLabel {{
            color: {c_text_mut};
            font-size: {sz_sm}px;
            font-family: '{get_master_font()}';
        }}
    """

    rekening_styles = get_resi_rekening_styles(is_dark, z)
    static_styles = get_resi_static_styles(is_dark)

    return {
        "lbl_main_title": f"""
            color: {c_text};
            font-size: {sz_title}px;
            font-weight: bold;
            margin-bottom: 1px;
            font-family: '{get_master_font()}';
        """,
        "lbl_tgl_tag": f"""
            color: {c_text_mut};
            font-weight: bold;
            font-family: '{get_master_font()}';
            font-size: {sz_tag}px;
        """,
        "lbl_resi_tag": f"""
            font-size: {sz_sm}px;
            color: {c_text_dim};
            font-weight: bold;
            font-family: '{get_master_font()}';
        """,
        "lbl_histori_title": f"""
            color: {c_text};
            font-size: {sz_base + 1}px;
            font-weight: bold;
            font-family: '{get_master_font()}';
        """,
        "txt_resi_display": f"""
            background-color: {c_resi_bg};
            border: 2px solid {c_resi_bord};
            border-radius: 6px;
            padding: 6px 12px;
            color: {c_resi_txt};
            font-weight: bold;
            font-size: {sz_total}px;
            letter-spacing: 1px;
            font-family: '{get_master_font()}';
        """,
        "date_input": f"""
            QDateEdit {{
                font-size: {sz_input}px;
                font-family: '{get_master_font()}';
                padding: 2px 10px;
                border: 1px solid {c_bord};
                border-radius: 4px;
                background-color: {c_bg};
                color: {c_text};
            }}
        """,
        "date_histori": f"""
            QDateEdit {{
                font-size: {sz_input}px;
                font-family: '{get_master_font()}';
                padding: 2px 10px;
                background-color: {c_hist_bg};
                color: {c_text_mut};
                border: 1px solid {c_bord};
                border-radius: 4px;
            }}
        """,
        "list_histori": f"""
            QListWidget {{
                background-color: {c_bg};
                color: {c_text_mut};
                border: 1px solid {c_bord};
                border-radius: 6px;
                padding: 5px;
                font-size: {sz_base}px;
                font-family: '{get_master_font()}';
            }}
            QListWidget::item {{
                padding: {6 + (z // 2)}px;
            }}
        """,
        "txt_search": f"""
            QLineEdit {{
                font-size: {sz_input}px;
                background-color: {c_bg};
                color: {c_text};
                border: 1px solid {c_bord};
                border-radius: 4px;
                padding: 6px;
                font-family: '{get_master_font()}';
            }}
            QLineEdit[custom_italic="true"][is_empty="true"] {{
                font-style: italic;
                font-size: {sz_input}px;
                color: {c_text_dim};
            }}
            QLineEdit[custom_italic="true"][is_empty="false"] {{
                font-style: normal;
            }}
        """,
        "btn_reset_tgl": f"""
            QPushButton {{
                background-color: #ef4444;
                color: white;
                font-weight: bold;
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
                background-color: {c_btn_add_bg};
                color: {c_btn_add_txt};
                border: 1px solid {c_btn_add_bord};
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-family: '{get_master_font()}';
            }}
            QPushButton:hover {{
                background-color: {c_btn_add_hover_bg};
            }}
            QPushButton:pressed {{
                background-color: {c_btn_add_pressed_bg};
            }}
        """,
        "btn_hapus_baris": f"""
            QPushButton {{
                font-size: {sz_base}px;
                background-color: {c_btn_del_bg};
                color: {c_btn_del_txt};
                border: 1px solid {c_btn_del_bord};
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-family: '{get_master_font()}';
            }}
            QPushButton:hover {{
                background-color: {c_btn_del_hover_bg};
                border-color: {c_btn_del_txt};
            }}
            QPushButton:pressed {{
                background-color: {c_btn_del_pressed_bg};
                border-color: {c_btn_del_txt};
            }}
        """,
        "txt_total_ongkir": f"""
            QLineEdit {{
                font-size: {sz_total}px;
                font-weight: bold;
                color: {c_foc};
                background-color: {c_bg};
                border: 1px solid {c_bord};
                padding: 6px;
                font-family: '{get_master_font()}';
            }}
            QLineEdit[custom_italic="true"][is_empty="true"] {{
                font-style: italic;
                font-size: {sz_total}px;
                color: {c_text_dim};
                font-weight: normal;
            }}
        """,
        "input_utama": input_style,
        "scroll_kiri": static_styles["scroll_kiri"],

        "btn_generate_simpan": get_btn_simpan_cetak_style(z),
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


def get_btn_clear_container_style(is_dark: bool = False, sz_sm: int = 12) -> str:
    """Style QToolButton reset/clear container khusus untuk Tab Resi."""
    if is_dark:
        normal_color = "#d1d5db"  # Light grey saat mode gelap
        hover_color = "#f87171"   # Merah terang saat hover
        pressed_color = "#ef4444" # Merah lebih gelap/solid saat diklik
    else:
        normal_color = "#808d8b"  # Hitam/Dark navy saat mode terang
        hover_color = "#ef4444"   # Merah saat hover
        pressed_color = "#b91c1c" # Merah tua saat diklik

    tt_bg = "#1d2024" if is_dark else "#ffffff"
    tt_text = "#ffffff" if is_dark else "#000000"
    tt_border = "#4c525e" if is_dark else "#d1d5db"

    return f"""
        QToolButton {{
            color: {normal_color};
            background-color: transparent;
            border: none;
            border-radius: 4px;
            font-size: 16pt;
            font-weight: 400;
            padding: 0px;
            font-family: '{get_master_font()}';
        }}
        QToolButton:hover {{
            color: {hover_color};
            background-color: transparent;
        }}
        QToolButton:pressed {{
            color: {pressed_color};
            background-color: transparent;
            /* Opsional: Efek sedikit geser ke bawah saat diklik agar terasa 'membal' */
            padding-top: 2px;
        }}
        QToolTip {{
            background-color: {tt_bg};
            color: {tt_text};
            border: 1px solid {tt_border};
            padding: 2px 5px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: normal;
            font-family: '{get_master_font()}';
        }}
    """