# tabs/tab_setting.py
import json
import re
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from config import CURRENT_SESSION, DATA_CLIENT, refresh_data_client

import services.database_service as db_service

from themes.modules.setting import get_setting_styles
from themes.components.combobox import terapkan_popup_bawah_combobox

from utils.typography import (
    get_master_font,
    perbarui_font_master,
)
from utils.placeholder_helper import terap_semua_placeholder_dinamis


class TabSettingSistem(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_current_settings()

    def init_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── 1. SIDEBAR KIRI (Navigasi) ──
        self.sidebar_container = QWidget()
        self.sidebar_container.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)
        sidebar_layout.setSpacing(8)

        self.lbl_menu = QLabel("Preferences")
        sidebar_layout.addWidget(self.lbl_menu)

        self.sidebar_list = QListWidget()
        self.sidebar_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        menus = [
            "🏢  Identitas & Sistem",
            "📦  Format & Resi",
            "🏦  Rekening Bank",
            "📍  Kantor Cabang",
            "🎨  Tampilan & Font"
        ]
        self.sidebar_list.addItems(menus)
        self.sidebar_list.setCurrentRow(0)

        sidebar_layout.addWidget(self.sidebar_list)
        root_layout.addWidget(self.sidebar_container)

        # ── 2. KONTEN KANAN (Tumpukan Halaman) ──
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(32, 24, 40, 24)
        right_layout.setSpacing(20)

        self.stacked_widget = QStackedWidget()

        self.page_general = QWidget()
        self.page_resi = QWidget()
        self.page_bank = QWidget()
        self.page_cabang = QWidget()
        self.page_font = QWidget()

        self._build_page_general()
        self._build_page_resi()
        self._build_page_bank()
        self._build_page_cabang()
        self._build_page_font()

        terapkan_popup_bawah_combobox(
            (
                self.cmb_format_resi_manual,
                self.combo_font,
            )
        )

        self.stacked_widget.addWidget(self.page_general)
        self.stacked_widget.addWidget(self.page_resi)
        self.stacked_widget.addWidget(self.page_bank)
        self.stacked_widget.addWidget(self.page_cabang)
        self.stacked_widget.addWidget(self.page_font)

        self.sidebar_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

        right_layout.addWidget(self.stacked_widget)

        # ── 3. TOMBOL SIMPAN GLOBAL (Selalu Terlihat di Bawah) ──
        self.btn_simpan_all = QPushButton("💾 SIMPAN PENGATURAN")
        self.btn_simpan_all.setFixedHeight(48)
        self.btn_simpan_all.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.btn_simpan_all.clicked.connect(self.simpan_pengaturan)
        right_layout.addWidget(self.btn_simpan_all)

        root_layout.addWidget(right_container)

        self.sesuaikan_tema_lokal()

        # 🌟 VALIDASI HAK AKSES USER SETELAH UI TERBENTUK
        self.validasi_hak_akses_setting()

    def _build_page_general(self):
        layout = QVBoxLayout(self.page_general)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Identitas & Sistem")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        # --- GROUP 1: IDENTITAS PERUSAHAAN ---
        self.group_pt = QGroupBox("Identitas Perusahaan (White-Label)")
        form_pt = QFormLayout(self.group_pt)
        self._init_form(form_pt)

        self.txt_nama_perusahaan = QLineEdit()
        self.txt_nama_perusahaan.setPlaceholderText("Contoh: PT CINTA SEJATI")

        self.txt_alamat_perusahaan = QLineEdit()
        self.txt_alamat_perusahaan.setPlaceholderText(
            "Contoh: Jl. Indonesia No. 77, Surabaya",
        )

        self.txt_telp_perusahaan = QLineEdit()
        self.txt_telp_perusahaan.setPlaceholderText("Contoh: 0812-3456-7890")

        form_pt.addRow("Nama Perusahaan:", self.txt_nama_perusahaan)
        form_pt.addRow("Alamat:", self.txt_alamat_perusahaan)
        form_pt.addRow("Telepon:", self.txt_telp_perusahaan)
        layout.addWidget(self.group_pt)

        # --- 🌟 GROUP 2: BRANDING TEKS LOGO (SATU WARNA FLAT) 🌟 ---
        self.group_logo_html = QGroupBox("Branding Teks Logo Aplikasi")
        form_logo = QFormLayout(self.group_logo_html)
        self._init_form(form_logo)

        self.txt_logo_aplikasi = QLineEdit()
        self.txt_logo_aplikasi.setPlaceholderText("Contoh: MAHKOTA KARGO")
        self.txt_logo_aplikasi.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_logo_aplikasi),
        )

        lbl_hint_logo = QLabel(
            "💡 Teks logo akan tampil dengan satu warna solid yang serasi di seluruh aplikasi.",
        )
        lbl_hint_logo.setProperty("setting_hint_italic", True)

        form_logo.addRow("Teks Logo Utama:", self.txt_logo_aplikasi)
        form_logo.addRow("", lbl_hint_logo)
        layout.addWidget(self.group_logo_html)

        # --- GROUP 3: DATABASE AKTIF ---
        self.group_db = QGroupBox("Database Aktif")
        form_db = QFormLayout(self.group_db)
        self._init_form(form_db)
        self.txt_db_path = QLineEdit()
        self.txt_db_path.setReadOnly(True)
        self.txt_db_path.setToolTip(
            "Database ditentukan dari app_env.json dan tidak dipindahkan dari menu ini."
        )

        form_db.addRow("Path Database (.db):", self.txt_db_path)
        layout.addWidget(self.group_db)
        layout.addStretch()

    def _build_page_resi(self):
        layout = QVBoxLayout(self.page_resi)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Format & Resi")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        self.group_resi = QGroupBox("Format Nomor Resi & Wilayah Dropdown")
        form_resi = QFormLayout(self.group_resi)
        self._init_form(form_resi)

        self.txt_template_resi = QLineEdit()
        self.txt_template_resi.setPlaceholderText("Contoh: [PREFIX][COUNTER][SUFFIX]")

        self.txt_suffix_pajak = QLineEdit()
        self.txt_suffix_pajak.setMaximumWidth(160)
        self.txt_suffix_pajak.setPlaceholderText("Contoh: -P")

        self.txt_prefix_invoice = QLineEdit()
        self.txt_prefix_invoice.setMaximumWidth(180)
        self.txt_prefix_invoice.setPlaceholderText("Contoh: INV")

        self.cmb_format_resi_manual = QComboBox()
        self.cmb_format_resi_manual.addItem("OTOMATIS", False)
        self.cmb_format_resi_manual.addItem("MANUAL", True)
        self.cmb_format_resi_manual.setMaximumWidth(180)

        self.txt_provinsi_tujuan = QTextEdit()
        self.txt_provinsi_tujuan.setPlaceholderText(
            "Pisahkan dengan koma. Contoh: KALIMANTAN TIMUR, BALI"
        )
        self.txt_provinsi_tujuan.setFixedHeight(70)

        form_resi.addRow("Template Nomor Resi:", self.txt_template_resi)
        form_resi.addRow("Akhiran Pajak (Suffix):", self.txt_suffix_pajak)
        form_resi.addRow("Prefix Invoice:", self.txt_prefix_invoice)
        form_resi.addRow("Input Nomor Resi:", self.cmb_format_resi_manual)
        form_resi.addRow("List Wilayah Dropdown:", self.txt_provinsi_tujuan)
        layout.addWidget(self.group_resi)
        layout.addStretch()

    def _build_page_bank(self):
        layout = QVBoxLayout(self.page_bank)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Rekening Bank")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        # --- 1. TABEL NON-PAJAK ---
        self.group_np = QGroupBox("Daftar Rekening Non-Pajak")
        vbox_np = QVBoxLayout(self.group_np)
        vbox_np.setContentsMargins(16, 22, 16, 16)
        vbox_np.setSpacing(8)

        self.table_np = QTableWidget(0, 4)
        self.setup_tabel_rekening(self.table_np)
        vbox_np.addWidget(self.table_np)

        hbox_in_np = QHBoxLayout()
        hbox_in_np.setSpacing(4)

        self.txt_in_bank_np = QLineEdit()
        self.txt_in_bank_np.setPlaceholderText("BANK...")
        self.txt_in_bank_np.setFixedWidth(100)
        self.txt_in_bank_np.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_bank_np),
        )

        self.txt_in_norek_np = QLineEdit()
        self.txt_in_norek_np.setPlaceholderText("NO. REK...")
        self.txt_in_norek_np.setFixedWidth(160)
        self.txt_in_norek_np.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_norek_np),
        )

        self.txt_in_nama_np = QLineEdit()
        self.txt_in_nama_np.setPlaceholderText("NAMA...")
        self.txt_in_nama_np.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_nama_np),
        )

        self.btn_add_np = QPushButton("+")
        self.btn_add_np.setFixedWidth(40)
        self.btn_add_np.clicked.connect(self.tambah_rek_np)

        hbox_in_np.addWidget(self.txt_in_bank_np)
        hbox_in_np.addWidget(self.txt_in_norek_np)
        hbox_in_np.addWidget(self.txt_in_nama_np, stretch=1)
        hbox_in_np.addWidget(self.btn_add_np)

        vbox_np.addLayout(hbox_in_np)
        layout.addWidget(self.group_np)

        # --- 2. TABEL PAJAK ---
        self.group_p = QGroupBox("Daftar Rekening Pajak (PT)")
        vbox_p = QVBoxLayout(self.group_p)
        vbox_p.setContentsMargins(16, 22, 16, 16)
        vbox_p.setSpacing(8)

        self.table_p = QTableWidget(0, 4)
        self.setup_tabel_rekening(self.table_p)
        vbox_p.addWidget(self.table_p)

        hbox_in_p = QHBoxLayout()
        hbox_in_p.setSpacing(4)

        self.txt_in_bank_p = QLineEdit()
        self.txt_in_bank_p.setPlaceholderText("BANK...")
        self.txt_in_bank_p.setFixedWidth(100)
        self.txt_in_bank_p.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_bank_p),
        )

        self.txt_in_norek_p = QLineEdit()
        self.txt_in_norek_p.setPlaceholderText("NO. REK...")
        self.txt_in_norek_p.setFixedWidth(160)
        self.txt_in_norek_p.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_norek_p),
        )

        self.txt_in_nama_p = QLineEdit()
        self.txt_in_nama_p.setPlaceholderText("NAMA...")
        self.txt_in_nama_p.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_nama_p),
        )

        self.btn_add_p = QPushButton("+")
        self.btn_add_p.setFixedWidth(40)
        self.btn_add_p.clicked.connect(self.tambah_rek_p)

        hbox_in_p.addWidget(self.txt_in_bank_p)
        hbox_in_p.addWidget(self.txt_in_norek_p)
        hbox_in_p.addWidget(self.txt_in_nama_p, stretch=1)
        hbox_in_p.addWidget(self.btn_add_p)

        vbox_p.addLayout(hbox_in_p)
        layout.addWidget(self.group_p)

    def _build_page_cabang(self):
        layout = QVBoxLayout(self.page_cabang)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Jaringan Kantor Cabang")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        self.group_branches = QGroupBox("Manajemen Data Cabang")
        vbox_branch = QVBoxLayout(self.group_branches)
        vbox_branch.setContentsMargins(16, 22, 16, 16)
        vbox_branch.setSpacing(8)

        self.table_cabang = QTableWidget()
        self.table_cabang.setColumnCount(5)
        self.table_cabang.setHorizontalHeaderLabels([
            "KODE",
            "NAMA KANTOR CABANG",
            "PREFIX NOTA",
            "START COUNTER (JSON)",
            "KAMUS ROUTE (JSON)",
        ])
        self.table_cabang.setRowCount(10)
        self.table_cabang.setAlternatingRowColors(True)
        self.table_cabang.verticalHeader().setVisible(True)
        self.table_cabang.setFixedHeight(280)
        self.table_cabang.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.table_cabang.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked,
        )

        hdr = self.table_cabang.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_cabang.setColumnWidth(0, 64)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table_cabang.setColumnWidth(2, 96)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table_cabang.setColumnWidth(3, 185)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table_cabang.setColumnWidth(4, 185)

        self._tbl_hint_label = QLabel(
            "💡 Double-click sel untuk mengedit. Kolom JSON harus berformat valid.",
        )

        vbox_branch.addWidget(self.table_cabang)
        vbox_branch.addWidget(self._tbl_hint_label)
        layout.addWidget(self.group_branches)
        layout.addStretch()

    def _build_page_font(self):
        layout = QVBoxLayout(self.page_font)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Tampilan & Font")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        self.group_font = QGroupBox(
            "Pengaturan Font"
        )

        form_font = QFormLayout(self.group_font)
        self._init_form(form_font)

        self.combo_font = QComboBox()
        self.combo_font.setFixedHeight(36)

        font_kandidat = [
            "Roboto",
            "Aptos Narrow",
            "Open Sans",
            "Segoe UI",
            "Arial",
        ]

        font_tersedia = set(
            QFontDatabase.families()
        )

        font_valid = [
            nama_font
            for nama_font in font_kandidat
            if nama_font in font_tersedia
        ]

        # Roboto menjadi fallback apabila daftar tidak terdeteksi.
        if not font_valid:
            font_valid = ["Roboto"]

        self.combo_font.addItems(font_valid)

        font_sekarang = get_master_font()

        idx_sekarang = self.combo_font.findText(
            font_sekarang,
            Qt.MatchFlag.MatchFixedString,
        )

        if idx_sekarang >= 0:
            self.combo_font.setCurrentIndex(
                idx_sekarang
            )

        # activated hanya berjalan ketika pengguna benar-benar memilih.
        self.combo_font.textActivated.connect(
            self.aksi_simpan_font_baru
        )

        lbl_info = QLabel(
            "Pilih font yang akan digunakan.\n"
            "Restart aplikasi untuk menerapkan."
        )
        lbl_info.setProperty("setting_hint_italic", True)

        form_font.addRow(
            "Pilih Font Aplikasi:",
            self.combo_font,
        )
        form_font.addRow("", lbl_info)

        layout.addWidget(self.group_font)
        layout.addStretch()

    @staticmethod
    def _init_form(form: QFormLayout):
        form.setContentsMargins(16, 22, 16, 16)
        form.setVerticalSpacing(16)
        form.setHorizontalSpacing(16)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

    # ─────────────────────────────────────────────────────────────────
    # HAK AKSES ROLE VALIDATION
    # ─────────────────────────────────────────────────────────────────

    def validasi_hak_akses_setting(self):
        role = str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper()
        boleh_edit = role == "SUPER_ADMIN"

        self.btn_simpan_all.setEnabled(boleh_edit)
        self.btn_simpan_all.setText(
            "💾 SIMPAN PENGATURAN"
            if boleh_edit
            else "🔒 PENGATURAN TERKUNCI (VIEW-ONLY MODE)"
        )
        self.btn_simpan_all.setToolTip(
            "" if boleh_edit else
            "Hanya SUPER_ADMIN yang dapat memodifikasi konfigurasi sistem."
        )

        self.btn_add_np.setEnabled(boleh_edit)
        self.btn_add_p.setEnabled(boleh_edit)

        for widget_type in (QLineEdit, QTextEdit):
            for widget in self.findChildren(widget_type):
                widget.setReadOnly(not boleh_edit)

        for widget_type in (QComboBox, QTableWidget):
            for widget in self.findChildren(widget_type):
                widget.setEnabled(boleh_edit)

        # Database selalu ditentukan dari app_env.json.
        self.txt_db_path.setReadOnly(True)

    # ─────────────────────────────────────────────────────────────────
    # AKSI TAMBAHAN KHUSUS (REKENING & FONT)
    # ─────────────────────────────────────────────────────────────────

    def paksa_kapital_lineedit(self, edit_widget):
        edit_widget.blockSignals(True)
        pos = edit_widget.cursorPosition()
        edit_widget.setText(edit_widget.text().upper())
        edit_widget.setCursorPosition(pos)
        edit_widget.blockSignals(False)

    def setup_tabel_rekening(self, table: QTableWidget):
        table.setHorizontalHeaderLabels(["BANK", "NO. REK", "ATAS NAMA", ""])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(120)

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(0, 100)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(1, 160)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(3, 40)

    def tambah_rek_np(self):
        self._tambah_ke_tabel(
            self.table_np,
            self.txt_in_bank_np,
            self.txt_in_norek_np,
            self.txt_in_nama_np,
        )

    def tambah_rek_p(self):
        self._tambah_ke_tabel(
            self.table_p,
            self.txt_in_bank_p,
            self.txt_in_norek_p,
            self.txt_in_nama_p,
        )

    def _tambah_ke_tabel(self, table, w_bank, w_norek, w_nama):
        bank = w_bank.text().strip()
        norek = w_norek.text().strip()
        nama = w_nama.text().strip()

        if not bank or not norek or not nama:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Data Bank, No. Rekening, dan Atas Nama wajib diisi!",
            )
            return

        self._insert_row_with_button(table, bank, norek, nama)

        w_bank.clear()
        w_norek.clear()
        w_nama.clear()

    def _insert_row_with_button(self, table, bank, norek, nama):
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(bank))
        table.setItem(row, 1, QTableWidgetItem(norek))
        table.setItem(row, 2, QTableWidgetItem(nama))

        btn_del = QPushButton("-")
        btn_del.setProperty("setting_row_delete", True)

        if CURRENT_SESSION.get('role', 'ADMIN') != "SUPER_ADMIN":
            btn_del.setEnabled(False)
        else:
            btn_del.clicked.connect(
                lambda _, t=table, b=btn_del: self.hapus_baris_via_tombol(t, b),
            )

        styles = getattr(self, "_setting_styles", {})
        style_key = (
            "btn_row_delete"
            if btn_del.isEnabled()
            else "btn_row_delete_disabled"
        )
        btn_del.setStyleSheet(styles.get(style_key, ""))

        table.setCellWidget(row, 3, btn_del)

    def hapus_baris_via_tombol(self, table, btn):
        for row in range(table.rowCount()):
            if table.cellWidget(row, 3) == btn:
                bank = table.item(row, 0).text() if table.item(row, 0) else "-"
                norek = table.item(row, 1).text() if table.item(row, 1) else "-"
                nama = table.item(row, 2).text() if table.item(row, 2) else "-"

                pesan_konfirmasi = (
                    "Hapus rekening berikut?\n\n"
                    f"Bank\t\t: {bank}\n"
                    f"No. Rek\t: {norek}\n"
                    f"Atas Nama\t: {nama}"
                )

                konfirmasi = QMessageBox.question(
                    self,
                    "Konfirmasi Hapus",
                    pesan_konfirmasi,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )

                if konfirmasi == QMessageBox.StandardButton.Yes:
                    table.removeRow(row)
                break

    def aksi_simpan_font_baru(
            self,
            font_terpilih: str,
    ):
        if (
                CURRENT_SESSION.get("role", "ADMIN")
                != "SUPER_ADMIN"
        ):
            return

        font_terpilih = str(
            font_terpilih or ""
        ).strip()

        if not font_terpilih:
            return

        perbarui_font_master(
            font_terpilih
        )

        QMessageBox.information(
            self,
            "Font Diperbarui",
            (
                f"Font utama berhasil diubah menjadi "
                f"{font_terpilih}.\n\n"
                "Tutup dan buka kembali aplikasi agar "
                "perubahan font diterapkan sepenuhnya."
            ),
        )

    # ─────────────────────────────────────────────────────────────────
    # TEMA (STYLING KHUSUS FDM LAYOUT)
    # ─────────────────────────────────────────────────────────────────

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            self.sesuaikan_tema_lokal()

    def showEvent(self, event):
        super().showEvent(event)
        self.sesuaikan_tema_lokal()

    def sesuaikan_tema_lokal(self):
        win = self.window()
        if win and hasattr(win, 'current_theme'):
            is_dark = win.current_theme == "dark"
        else:
            app = QApplication.instance()
            qss = app.styleSheet().lower() if app else ""
            is_dark = "#25282e" in qss or "#1d2024" in qss

        terap_semua_placeholder_dinamis(
            self,
            is_dark=is_dark,
        )

        settings = QSettings("AplikasiEkspedisi", "PengaturanUI")
        z = int(settings.value(f"zoom_{self.__class__.__name__}", 0))
        sz_base, sz_input, sz_title = 13 + z, 14 + z, 15 + z

        s = get_setting_styles(is_dark, sz_base, sz_input, sz_title)
        self._setting_styles = s

        self.sidebar_container.setStyleSheet(s['sidebar_container'])
        self.sidebar_list.setStyleSheet(s['sidebar_list'])

        self._tbl_hint_label.setStyleSheet(s['lbl_hint'])
        if hasattr(self, 'lbl_menu'):
            self.lbl_menu.setStyleSheet(s['lbl_menu'])

        # 🎯 FIX PETIK GANTUNG: Diperbaiki total dari versi sebelumnya
        groups = [
            self.group_pt,
            self.group_logo_html,
            self.group_resi,
            self.group_branches,
            self.group_db,
            self.group_font,
        ]
        if hasattr(self, 'group_np'):
            groups.extend([self.group_np, self.group_p])

        for grp in groups:
            grp.setStyleSheet(s['custom_groupbox'])

        for lbl in self.findChildren(QLabel):
            if lbl.property("is_page_title"):
                lbl.setStyleSheet(s['lbl_page_title'])
            elif lbl.property("setting_hint_italic"):
                lbl.setStyleSheet(s["lbl_info_italic"])
            elif not lbl.property(
                "is_page_title",
            ) and lbl not in (self._tbl_hint_label,):
                if hasattr(self, 'lbl_menu') and lbl == self.lbl_menu:
                    continue
                lbl.setStyleSheet(s['form_label'])

        # QLineEdit/QTextEdit tetap memakai theme Setting.
        for widget_type in (QLineEdit, QTextEdit):
            for w in self.findChildren(widget_type):
                w.setStyleSheet(s['input'])

        # QComboBox sengaja tanpa QSS agar dirender native Fusion/QPalette.
        # Font tetap mengikuti ukuran TabSetting yang sudah berlaku sebelumnya.
        for combo in (
            self.cmb_format_resi_manual,
            self.combo_font,
        ):
            combo.setStyleSheet("")
            font_combo = combo.font()
            font_combo.setFamily(get_master_font())
            font_combo.setPixelSize(max(1, sz_input))
            combo.setFont(font_combo)

            combo_view = combo.view()
            if combo_view is not None:
                combo_view.setFont(font_combo)

        self.txt_db_path.setStyleSheet(s['input_readonly'])

        self.table_cabang.setStyleSheet(s['input'])
        self.btn_simpan_all.setStyleSheet(s['btn_simpan'])

        if hasattr(self, 'table_np'):
            self.table_np.setStyleSheet(s.get('input', ''))
            self.table_p.setStyleSheet(s.get('input', ''))

            self.btn_add_np.setStyleSheet(s["btn_add_rekening"])
            self.btn_add_p.setStyleSheet(s["btn_add_rekening"])

        for button in self.findChildren(QPushButton):
            if not button.property("setting_row_delete"):
                continue
            style_key = (
                "btn_row_delete"
                if button.isEnabled()
                else "btn_row_delete_disabled"
            )
            button.setStyleSheet(s[style_key])

        self.validasi_hak_akses_setting()

    # ─────────────────────────────────────────────────────────────────
    # LOAD & SIMPAN DATA (🎯 SEKARANG AMAN DI DALAM CLASS)
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _as_list(value):
        if isinstance(value, list):
            return value
        if not value:
            return []
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else [value]
            except (json.JSONDecodeError, TypeError):
                return [value]
        return list(value) if isinstance(value, tuple) else []

    def load_current_settings(self):
        try:
            settings = refresh_data_client()
        except Exception as exc:
            print(f"[TabSetting] Gagal refresh pengaturan: {exc}")
            settings = DATA_CLIENT

        self.txt_nama_perusahaan.setText(settings.get("nama_perusahaan", ""))
        self.txt_alamat_perusahaan.setText(settings.get("alamat_perusahaan", ""))
        self.txt_telp_perusahaan.setText(settings.get("telp_perusahaan", ""))
        self.txt_template_resi.setText(
            settings.get("template_no_resi", "[PREFIX][COUNTER][SUFFIX]")
        )
        self.txt_suffix_pajak.setText(settings.get("kode_akhiran_pajak", "-P"))
        self.txt_prefix_invoice.setText(settings.get("prefix_invoice", "INV"))
        self.txt_db_path.setText(CURRENT_SESSION.get("db_name", "database_cargo.db"))

        manual = str(settings.get("format_resi_manual", "0")).lower() in {
            "1", "true", "yes", "ya", "manual"
        }
        idx_manual = self.cmb_format_resi_manual.findData(manual)
        self.cmb_format_resi_manual.setCurrentIndex(max(idx_manual, 0))

        raw_logo = str(settings.get("logo_text_html", "KARGO EKSPEDISI"))
        self.txt_logo_aplikasi.setText(re.sub(r"<[^>]*>", "", raw_logo).strip())

        provinsi = self._as_list(settings.get("provinsi_tujuan", []))
        self.txt_provinsi_tujuan.setText(
            ", ".join(str(item).strip() for item in provinsi if str(item).strip())
        )

        def load_rekening(table, values):
            table.setRowCount(0)
            for value in self._as_list(values):
                if isinstance(value, dict):
                    bank = value.get("bank", "")
                    norek = value.get("no_rekening", value.get("nomor", ""))
                    nama = value.get("atas_nama", value.get("nama", ""))
                else:
                    parts = [p.strip() for p in str(value).split(",", 2)]
                    bank = parts[0] if len(parts) > 0 else ""
                    norek = parts[1] if len(parts) > 1 else ""
                    nama = parts[2] if len(parts) > 2 else ""
                if bank or norek or nama:
                    self._insert_row_with_button(table, bank, norek, nama)

        load_rekening(self.table_np, settings.get("rekening_nonpajak", []))
        load_rekening(self.table_p, settings.get("rekening_pajak", []))

        self.table_cabang.clearContents()
        try:
            rows = db_service.ambil_semua_data_cabang(limit=100) or []
            self.table_cabang.setRowCount(max(10, len(rows)))
            for row_index, row_data in enumerate(rows):
                if isinstance(row_data, dict):
                    values = [
                        row_data.get("kode_cabang", ""),
                        row_data.get("nama_cabang", ""),
                        row_data.get("resi_prefix", ""),
                        row_data.get("start_seq_json", "{}"),
                        row_data.get("aturan_prefix", "{}"),
                    ]
                else:
                    values = list(row_data)[:5]

                while len(values) < 5:
                    values.append("")
                for column, value in enumerate(values):
                    self.table_cabang.setItem(
                        row_index, column, QTableWidgetItem(str(value or ""))
                    )
        except Exception as exc:
            self.table_cabang.setRowCount(10)
            print(f"[TabSetting] Gagal memuat data cabang: {exc}")

        self.validasi_hak_akses_setting()

    def _ambil_rekening_tabel(self, table, label):
        result = []
        for row in range(table.rowCount()):
            bank = table.item(row, 0).text().strip().upper() if table.item(
                row,
                0,
            ) else ""
            norek = table.item(row, 1).text().strip() if table.item(row, 1) else ""
            nama = table.item(row, 2).text().strip().upper() if table.item(
                row,
                2,
            ) else ""

            if not any((bank, norek, nama)):
                continue
            if not all((bank, norek, nama)):
                raise ValueError(
                    f"{label} baris {row + 1} belum lengkap."
                )
            result.append(f"{bank}, {norek}, {nama}")
        return result

    def _ambil_cabang_tabel(self):
        branches = []
        kode_terpakai = set()

        for row in range(self.table_cabang.rowCount()):
            item_kode = self.table_cabang.item(row, 0)
            if not item_kode or not item_kode.text().strip():
                continue

            kode = item_kode.text().strip().upper()
            nama = (
                self.table_cabang.item(row, 1).text().strip().upper()
                if self.table_cabang.item(row, 1) else ""
            )
            prefix = (
                self.table_cabang.item(row, 2).text().strip().upper()
                if self.table_cabang.item(row, 2) else ""
            )
            seq_text = (
                self.table_cabang.item(row, 3).text().strip()
                if self.table_cabang.item(row, 3) else '{"DEFAULT": 1000}'
            ) or '{"DEFAULT": 1000}'
            route_text = (
                self.table_cabang.item(row, 4).text().strip()
                if self.table_cabang.item(row, 4) else '{"DEFAULT": "INV"}'
            ) or '{"DEFAULT": "INV"}'

            if not nama or not prefix:
                raise ValueError(
                    f"Nama dan prefix cabang baris {row + 1} wajib diisi."
                )
            if kode in kode_terpakai:
                raise ValueError(f"Kode cabang '{kode}' digunakan dua kali.")

            try:
                seq_data = json.loads(seq_text)
                route_data = json.loads(route_text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Format JSON cabang baris {row + 1} tidak valid."
                ) from exc

            if not isinstance(seq_data, dict) or not isinstance(route_data, dict):
                raise ValueError(
                    f"Kolom JSON cabang {kode} harus berupa object JSON."
                )

            branches.append({
                "kode_cabang": kode,
                "nama_cabang": nama,
                "resi_prefix": prefix,
                "start_seq_json": json.dumps(seq_data, ensure_ascii=False),
                "aturan_prefix": json.dumps(route_data, ensure_ascii=False),
            })
            kode_terpakai.add(kode)

        if not branches:
            raise ValueError("Minimal harus tersedia satu kantor cabang.")

        return branches

    def simpan_pengaturan(self):
        if str(CURRENT_SESSION.get("role", "ADMIN")).upper() != "SUPER_ADMIN":
            QMessageBox.warning(
                self, "Akses Ditolak",
                "Hanya SUPER_ADMIN yang dapat menyimpan pengaturan."
            )
            return

        nama = self.txt_nama_perusahaan.text().strip().upper()
        alamat = self.txt_alamat_perusahaan.text().strip().upper()
        telp = self.txt_telp_perusahaan.text().strip()
        logo = self.txt_logo_aplikasi.text().strip().upper()
        template = self.txt_template_resi.text().strip().upper()
        suffix = self.txt_suffix_pajak.text().strip().upper()
        prefix_invoice = self.txt_prefix_invoice.text().strip().upper()

        wajib = {
            "Nama perusahaan": nama,
            "Alamat": alamat,
            "Telepon": telp,
            "Teks logo": logo,
            "Template resi": template,
            "Prefix invoice": prefix_invoice,
        }
        kosong = [label for label, value in wajib.items() if not value]
        if kosong:
            QMessageBox.warning(
                self, "Data Belum Lengkap",
                "Kolom berikut wajib diisi:\n- " + "\n- ".join(kosong)
            )
            return

        provinsi = [
            value.strip().upper()
            for value in re.split(
                r"[,;\n]+", self.txt_provinsi_tujuan.toPlainText()
            )
            if value.strip()
        ]
        provinsi = list(dict.fromkeys(provinsi))
        if not provinsi:
            QMessageBox.warning(
                self, "Wilayah Belum Diisi",
                "Minimal masukkan satu wilayah tujuan."
            )
            return

        try:
            rekening_np = self._ambil_rekening_tabel(
                self.table_np, "Rekening non-pajak"
            )
            rekening_p = self._ambil_rekening_tabel(
                self.table_p, "Rekening pajak"
            )
            branches = self._ambil_cabang_tabel()
        except ValueError as exc:
            QMessageBox.warning(self, "Data Tidak Valid", str(exc))
            return

        settings_to_save = [
            ("nama_perusahaan", nama),
            ("alamat_perusahaan", alamat),
            ("telp_perusahaan", telp),
            ("logo_text_html", logo),
            ("template_no_resi", template),
            ("kode_akhiran_pajak", suffix),
            ("prefix_invoice", prefix_invoice),
            (
                "format_resi_manual",
                "1" if self.cmb_format_resi_manual.currentData() else "0"
            ),
            ("provinsi_tujuan", json.dumps(provinsi, ensure_ascii=False)),
            ("rekening_nonpajak", json.dumps(rekening_np, ensure_ascii=False)),
            ("rekening_pajak", json.dumps(rekening_p, ensure_ascii=False)),
        ]

        try:
            sukses, pesan = db_service.simpan_semua_pengaturan_dan_cabang(
                settings_to_save, branches
            )
            if not sukses:
                QMessageBox.critical(
                    self, "Gagal Menyimpan",
                    str(pesan or "Service database menolak penyimpanan.")
                )
                return

            refresh_data_client()

            kode_aktif = str(
                CURRENT_SESSION.get("kode_cabang", "")
            ).strip().upper()
            for branch in branches:
                if branch["kode_cabang"] == kode_aktif:
                    CURRENT_SESSION.update({
                        "nama_cabang": branch["nama_cabang"],
                        "resi_prefix": branch["resi_prefix"],
                        "aturan_prefix": json.loads(branch["aturan_prefix"]),
                    })
                    break

            self.load_current_settings()
            QMessageBox.information(
                self, "Pengaturan Tersimpan",
                "Pengaturan berhasil disimpan dan langsung diterapkan.\n\n"
                "Path database dan akun developer tetap aman di app_env.json."
            )

        except Exception as exc:
            QMessageBox.critical(
                self, "Error",
                f"Gagal menyimpan data ke database:\n{exc}"
            )