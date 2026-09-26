# tabs/tab_setting.py
import json
import re
import uuid
from datetime import datetime
from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtGui import QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from config import (
    CENTRAL_BRANCH_ROLES,
    CURRENT_SESSION,
    DATA_CLIENT,
    refresh_data_client,
)

import services.database_service as db_service

from themes.modules.setting import get_setting_styles
from utils.input_style_helper import atur_tinggi_input, terapkan_style_input_global

from utils.typography import (
    get_master_font,
    get_fixed_font_sizes,
    perbarui_font_master,
)
from utils.modules.setting_metrics import (
    SETTING_ACCOUNT_ACTION_WIDTH,
    SETTING_ACCOUNT_GROUP_MARGINS,
    SETTING_ACCOUNT_GROUP_SPACING,
    SETTING_ACCOUNT_INPUT_SPACING,
    SETTING_ACCOUNT_NUMBER_WIDTH,
    SETTING_ACCOUNT_TABLE_MIN_HEIGHT,
    SETTING_BANK_FIELD_WIDTH,
    SETTING_BRANCH_CODE_WIDTH,
    SETTING_BRANCH_GROUP_MARGINS,
    SETTING_BRANCH_GROUP_SPACING,
    SETTING_BRANCH_PREFIX_WIDTH,
    SETTING_CONTENT_MARGINS,
    SETTING_CONTENT_SPACING,
    SETTING_FORM_HORIZONTAL_SPACING,
    SETTING_FORM_MARGINS,
    SETTING_FORM_VERTICAL_SPACING,
    SETTING_RESI_MODE_MAX_WIDTH,
    SETTING_ROOT_MARGINS,
    SETTING_ROOT_SPACING,
    SETTING_SAVE_BUTTON_HEIGHT,
    SETTING_SIDEBAR_MARGINS,
    SETTING_SIDEBAR_SPACING,
    SETTING_SIDEBAR_WIDTH,
    SETTING_SUFFIX_MAX_WIDTH,
)


class TabSettingSistem(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setting_ui_ready = False
        self._setting_theme_applying = False
        self._setting_theme_timer = QTimer(self)
        self._setting_theme_timer.setSingleShot(True)
        self._setting_theme_timer.timeout.connect(self.sesuaikan_tema_lokal)
        self.init_ui()
        self.load_current_settings()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def init_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(*SETTING_ROOT_MARGINS)
        root_layout.setSpacing(SETTING_ROOT_SPACING)

        # ── 1. SIDEBAR KIRI (Navigasi) ──
        self.sidebar_container = QWidget()
        self.sidebar_container.setFixedWidth(SETTING_SIDEBAR_WIDTH)
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(*SETTING_SIDEBAR_MARGINS)
        sidebar_layout.setSpacing(SETTING_SIDEBAR_SPACING)

        self.lbl_menu = QLabel("Pengaturan")
        sidebar_layout.addWidget(self.lbl_menu)

        self.sidebar_list = QListWidget()
        self.sidebar_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        menus = [
            "Identitas & Sistem",
            "Dokumen & Penomoran",
            "Rekening Bank",
            "Cabang & Wilayah",
            "Operasional",
            "Manajemen User",
            "Tampilan & Font",
        ]
        self.sidebar_list.addItems(menus)
        self.sidebar_list.setCurrentRow(0)

        sidebar_layout.addWidget(self.sidebar_list)
        root_layout.addWidget(self.sidebar_container)

        # ── 2. KONTEN KANAN (Tumpukan Halaman) ──
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(*SETTING_CONTENT_MARGINS)
        right_layout.setSpacing(SETTING_CONTENT_SPACING)

        self.stacked_widget = QStackedWidget()

        self.page_general = QWidget()
        self.page_document = QWidget()
        self.page_bank = QWidget()
        self.page_cabang = QWidget()
        self.page_operasional = QWidget()
        self.page_user_access = QWidget()
        self.page_font = QWidget()

        self._build_page_general()
        self._build_page_document()
        self._build_page_bank()
        self._build_page_cabang()
        self._build_page_operasional()
        self._build_page_user_access()
        self._build_page_font()

        atur_tinggi_input((
            self.txt_nama_perusahaan,
            self.txt_alamat_perusahaan,
            self.txt_telp_perusahaan,
            self.txt_logo_aplikasi,
            self.txt_db_path,
            self.txt_suffix_pajak,
            self.cmb_format_resi_manual,
            self.txt_num_format,
            self.txt_option_code,
            self.txt_option_label,
            self.txt_kode_wilayah,
            self.txt_nama_wilayah,
            self.txt_in_bank_np,
            self.txt_in_norek_np,
            self.txt_in_nama_np,
            self.txt_in_bank_p,
            self.txt_in_norek_p,
            self.txt_in_nama_p,
            self.combo_font,
        ))

        self.stacked_widget.addWidget(self.page_general)
        self.stacked_widget.addWidget(self.page_document)
        self.stacked_widget.addWidget(self.page_bank)
        self.stacked_widget.addWidget(self.page_cabang)
        self.stacked_widget.addWidget(self.page_operasional)
        self.stacked_widget.addWidget(self.page_user_access)
        self.stacked_widget.addWidget(self.page_font)

        self.sidebar_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

        right_layout.addWidget(self.stacked_widget)

        # ── 3. TOMBOL SIMPAN GLOBAL (Selalu Terlihat di Bawah) ──
        self.btn_simpan_all = QPushButton("Simpan")
        self.btn_simpan_all.setFixedHeight(SETTING_SAVE_BUTTON_HEIGHT)
        self.btn_simpan_all.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.btn_simpan_all.clicked.connect(self.simpan_pengaturan)
        right_layout.addWidget(self.btn_simpan_all)

        root_layout.addWidget(right_container)

        self._setting_ui_ready = True
        self.sesuaikan_tema_lokal()
        self.validasi_hak_akses_setting()

    def _build_page_general(self):
        layout = QVBoxLayout(self.page_general)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Identitas & Sistem")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        # =========================================================
        # SATU FORM UNTUK IDENTITAS, BRANDING, DAN DATABASE
        # =========================================================
        form = QFormLayout()
        self._init_form(form)

        # --- IDENTITAS PERUSAHAAN ---
        self.txt_nama_perusahaan = QLineEdit()
        self.txt_nama_perusahaan.setPlaceholderText("contoh: PT CINTA SEJATI")

        self.txt_alamat_perusahaan = QLineEdit()
        self.txt_alamat_perusahaan.setPlaceholderText(
            "Contoh: Jl. Indonesia No. 77, Surabaya",
        )

        self.txt_telp_perusahaan = QLineEdit()
        self.txt_telp_perusahaan.setPlaceholderText("contoh: 0812-3456-7890")

        form.addRow("Nama perusahaan:", self.txt_nama_perusahaan)
        form.addRow("Alamat perusahaan:", self.txt_alamat_perusahaan)
        form.addRow("Telepon perusahaan:", self.txt_telp_perusahaan)

        # --- BRANDING TEKS LOGO ---
        self.txt_logo_aplikasi = QLineEdit()
        self.txt_logo_aplikasi.setPlaceholderText("contoh: ABCDE KARGO")
        self.txt_logo_aplikasi.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_logo_aplikasi),
        )

        lbl_hint_logo = QLabel(
            "💡 Teks logo akan tampil di header dokumen.",
        )
        lbl_hint_logo.setProperty("setting_hint_italic", True)

        form.addRow("Teks logo perusahaan:", self.txt_logo_aplikasi)
        form.addRow("", lbl_hint_logo)

        # --- DATABASE AKTIF ---
        self.txt_db_path = QLineEdit()
        self.txt_db_path.setReadOnly(True)
        self.txt_db_path.setToolTip(
            "Database ditentukan dari app_env.json dan tidak dipindahkan dari menu ini."
        )

        form.addRow("Path database (.db):", self.txt_db_path)

        layout.addLayout(form)
        layout.addStretch()

    def _build_page_document(self):
        """Dokumen & Penomoran: konfigurasi client-side yang disimpan di SQLite + sync.

        Tanpa QGroupBox/container berlapis — hanya judul section + tabel
        langsung, mengikuti pola halaman Cabang & Wilayah, agar tidak ada
        overlap antara tabel, form input, dan teks bantuan.
        """
        layout = QVBoxLayout(self.page_document)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl_title = QLabel("Dokumen & Penomoran")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        # =============================================================
        # 1. FORMAT NOMOR DOKUMEN
        # =============================================================
        lbl_numbering = QLabel("Format Nomor Dokumen")
        lbl_numbering.setStyleSheet("font-weight: 700; margin-top: 2px;")
        layout.addWidget(lbl_numbering)

        self.table_numbering = QTableWidget(0, 6)
        self.table_numbering.setHorizontalHeaderLabels([
            "CABANG", "DOKUMEN", "FORMAT", "START", "CURRENT", "PADDING",
        ])
        self.table_numbering.setAlternatingRowColors(True)
        self.table_numbering.verticalHeader().setVisible(False)
        self.table_numbering.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_numbering.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_numbering.setMinimumHeight(160)
        self.table_numbering.setMaximumHeight(220)
        hdr = self.table_numbering.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_numbering.setColumnWidth(0, 90)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table_numbering.setColumnWidth(1, 120)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table_numbering.setColumnWidth(3, 80)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table_numbering.setColumnWidth(4, 90)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table_numbering.setColumnWidth(5, 80)
        self.table_numbering.itemDoubleClicked.connect(self._edit_numbering_row)
        layout.addWidget(self.table_numbering)

        hint = QLabel(
            "💡 Gunakan {CABANG}, {WILAYAH}, {TAHUN}, {BULAN}, {HARI}, {SEQ}. "
            "CURRENT adalah nomor terakhir yang terpakai."
        )
        hint.setProperty("setting_hint_italic", True)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── Form Input Penomoran (Dua Baris Rapi) ──
        row1 = QHBoxLayout()
        row1.setSpacing(SETTING_ACCOUNT_INPUT_SPACING)
        row2 = QHBoxLayout()
        row2.setSpacing(SETTING_ACCOUNT_INPUT_SPACING)

        self.cmb_num_branch = QComboBox()
        self.cmb_num_branch.setMinimumWidth(90)

        self.cmb_num_document = QComboBox()
        self.cmb_num_document.addItems(["RESI", "MANIFEST", "INVOICE"])

        self.txt_num_format = QLineEdit()
        self.txt_num_format.setPlaceholderText("{CABANG}-{WILAYAH}-{SEQ}")

        self.sp_num_start = QSpinBox()
        self.sp_num_start.setRange(0, 2_000_000_000)
        self.sp_num_start.setValue(1)

        self.sp_num_current = QSpinBox()
        self.sp_num_current.setRange(0, 2_000_000_000)
        self.sp_num_current.setValue(0)
        self.sp_num_current.setEnabled(False)

        self.sp_num_padding = QSpinBox()
        self.sp_num_padding.setRange(1, 12)
        self.sp_num_padding.setValue(5)

        self.btn_num_add = QPushButton("+")
        self.btn_num_add.setFixedWidth(SETTING_ACCOUNT_ACTION_WIDTH)
        self.btn_num_add.clicked.connect(self._save_numbering_from_form)

        # Baris 1: Cabang, Dokumen, Format Template
        row1.addWidget(self.cmb_num_branch)
        row1.addWidget(self.cmb_num_document)
        row1.addWidget(self.txt_num_format, stretch=1)

        # Baris 2: Start, Current, Padding, Tombol Simpan
        row2.addWidget(QLabel("Start:"))
        row2.addWidget(self.sp_num_start)
        row2.addWidget(QLabel("Current:"))
        row2.addWidget(self.sp_num_current)
        row2.addWidget(QLabel("Padding:"))
        row2.addWidget(self.sp_num_padding)
        row2.addStretch(1)
        row2.addWidget(self.btn_num_add)

        layout.addLayout(row1)
        layout.addLayout(row2)

        # =============================================================
        # 2. PENGATURAN TAMBAHAN
        # =============================================================
        lbl_tambahan = QLabel("Pengaturan Tambahan")
        lbl_tambahan.setStyleSheet("font-weight: 700; margin-top: 12px;")
        layout.addWidget(lbl_tambahan)

        form_tambahan = QFormLayout()
        self._init_form(form_tambahan)

        self.txt_suffix_pajak = QLineEdit()
        self.txt_suffix_pajak.setMaximumWidth(SETTING_SUFFIX_MAX_WIDTH)
        self.txt_suffix_pajak.setPlaceholderText("contoh: -P")

        self.cmb_format_resi_manual = QComboBox()
        self.cmb_format_resi_manual.addItem("Otomatis", False)
        self.cmb_format_resi_manual.addItem("Manual", True)
        self.cmb_format_resi_manual.setMaximumWidth(SETTING_RESI_MODE_MAX_WIDTH)

        form_tambahan.addRow("Akhiran pajak:", self.txt_suffix_pajak)
        form_tambahan.addRow("Input nomor resi:", self.cmb_format_resi_manual)

        layout.addLayout(form_tambahan)
        layout.addStretch()

    def _build_page_operasional(self):
        layout = QVBoxLayout(self.page_operasional)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl_title = QLabel("Operasional")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        self.group_ops = QGroupBox("Pilihan Operasional")
        v = QVBoxLayout(self.group_ops)
        v.setContentsMargins(*SETTING_ACCOUNT_GROUP_MARGINS)
        v.setSpacing(SETTING_ACCOUNT_GROUP_SPACING)

        self.table_options = QTableWidget(0, 4)
        self.table_options.setHorizontalHeaderLabels(["KELOMPOK", "NILAI", "NAMA TAMPILAN", ""])
        self.table_options.setAlternatingRowColors(True)
        self.table_options.verticalHeader().setVisible(False)
        self.table_options.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_options.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_options.setMinimumHeight(320)
        h = self.table_options.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_options.setColumnWidth(0, 230)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table_options.setColumnWidth(1, 150)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table_options.setColumnWidth(3, SETTING_ACCOUNT_ACTION_WIDTH)
        self.table_options.itemDoubleClicked.connect(self._edit_option_row)
        v.addWidget(self.table_options)

        hint = QLabel(
            "Kelompok yang tersedia: Status Gudang, Status Tagihan, Metode Pembayaran, Jenis Truk, Tujuan Kapal.")
        hint.setProperty("setting_hint_italic", True)
        v.addWidget(hint)

        form = QHBoxLayout()
        self.cmb_option_group = QComboBox()
        self.cmb_option_group.addItem("STATUS_GUDANG", "BUKU_STATUS_GUDANG")
        self.cmb_option_group.addItem("STATUS_TAGIHAN", "BUKU_STATUS_TAGIHAN")
        self.cmb_option_group.addItem("METODE_PEMBAYARAN", "BUKU_METODE_PEMBAYARAN")
        self.cmb_option_group.addItem("JENIS_TRUK", "ARMADA_JENIS_TRUK")
        self.cmb_option_group.addItem("TUJUAN_KAPAL", "ARMADA_TUJUAN_KAPAL")
        self.txt_option_code = QLineEdit()
        self.txt_option_code.setPlaceholderText("NILAI / KODE")
        self.txt_option_label = QLineEdit()
        self.txt_option_label.setPlaceholderText("NAMA TAMPILAN")
        self.btn_option_add = QPushButton("+")
        self.btn_option_add.setFixedWidth(SETTING_ACCOUNT_ACTION_WIDTH)
        self.btn_option_add.clicked.connect(self._save_option_from_form)
        form.addWidget(self.cmb_option_group)
        form.addWidget(self.txt_option_code)
        form.addWidget(self.txt_option_label, stretch=1)
        form.addWidget(self.btn_option_add)
        v.addLayout(form)
        layout.addWidget(self.group_ops)
        layout.addStretch()

    def _build_page_bank(self):
        layout = QVBoxLayout(self.page_bank)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Rekening Bank")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        # --- 1. TABEL NON-PAJAK ---
        self.group_np = QGroupBox("Daftar rekening nonpajak")
        vbox_np = QVBoxLayout(self.group_np)
        vbox_np.setContentsMargins(*SETTING_ACCOUNT_GROUP_MARGINS)
        vbox_np.setSpacing(SETTING_ACCOUNT_GROUP_SPACING)

        self.table_np = QTableWidget(0, 4)
        self.setup_tabel_rekening(self.table_np)
        vbox_np.addWidget(self.table_np)

        hbox_in_np = QHBoxLayout()
        hbox_in_np.setSpacing(SETTING_ACCOUNT_INPUT_SPACING)

        self.txt_in_bank_np = QLineEdit()
        self.txt_in_bank_np.setPlaceholderText("BANK...")
        self.txt_in_bank_np.setFixedWidth(SETTING_BANK_FIELD_WIDTH)
        self.txt_in_bank_np.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_bank_np),
        )

        self.txt_in_norek_np = QLineEdit()
        self.txt_in_norek_np.setPlaceholderText("NO. REK...")
        self.txt_in_norek_np.setFixedWidth(SETTING_ACCOUNT_NUMBER_WIDTH)
        self.txt_in_norek_np.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_norek_np),
        )

        self.txt_in_nama_np = QLineEdit()
        self.txt_in_nama_np.setPlaceholderText("NAMA...")
        self.txt_in_nama_np.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_nama_np),
        )

        self.btn_add_np = QPushButton("+")
        self.btn_add_np.setFixedWidth(SETTING_ACCOUNT_ACTION_WIDTH)
        self.btn_add_np.clicked.connect(self.tambah_rek_np)

        hbox_in_np.addWidget(self.txt_in_bank_np)
        hbox_in_np.addWidget(self.txt_in_norek_np)
        hbox_in_np.addWidget(self.txt_in_nama_np, stretch=1)
        hbox_in_np.addWidget(self.btn_add_np)

        vbox_np.addLayout(hbox_in_np)
        layout.addWidget(self.group_np)

        # --- 2. TABEL PAJAK ---
        self.group_p = QGroupBox("Daftar rekening pajak (PT)")
        vbox_p = QVBoxLayout(self.group_p)
        vbox_p.setContentsMargins(*SETTING_ACCOUNT_GROUP_MARGINS)
        vbox_p.setSpacing(SETTING_ACCOUNT_GROUP_SPACING)

        self.table_p = QTableWidget(0, 4)
        self.setup_tabel_rekening(self.table_p)
        vbox_p.addWidget(self.table_p)

        hbox_in_p = QHBoxLayout()
        hbox_in_p.setSpacing(SETTING_ACCOUNT_INPUT_SPACING)

        self.txt_in_bank_p = QLineEdit()
        self.txt_in_bank_p.setPlaceholderText("BANK...")
        self.txt_in_bank_p.setFixedWidth(SETTING_BANK_FIELD_WIDTH)
        self.txt_in_bank_p.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_bank_p),
        )

        self.txt_in_norek_p = QLineEdit()
        self.txt_in_norek_p.setPlaceholderText("NO. REK...")
        self.txt_in_norek_p.setFixedWidth(SETTING_ACCOUNT_NUMBER_WIDTH)
        self.txt_in_norek_p.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_norek_p),
        )

        self.txt_in_nama_p = QLineEdit()
        self.txt_in_nama_p.setPlaceholderText("NAMA...")
        self.txt_in_nama_p.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_in_nama_p),
        )

        self.btn_add_p = QPushButton("+")
        self.btn_add_p.setFixedWidth(SETTING_ACCOUNT_ACTION_WIDTH)
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
        layout.setSpacing(8)

        lbl_title = QLabel("Cabang & Wilayah")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        scroll = QScrollArea(self.page_cabang)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        # =============================================================
        # 1. CABANG
        # =============================================================
        lbl_cabang = QLabel("Manajemen Data Cabang")
        lbl_cabang.setStyleSheet("font-weight: 700; margin-top: 2px;")
        content_layout.addWidget(lbl_cabang)

        self.table_cabang = QTableWidget(0, 3)
        self.table_cabang.setHorizontalHeaderLabels([
            "KODE", "NAMA KANTOR CABANG", "PREFIX NOTA",
        ])
        self.table_cabang.setAlternatingRowColors(True)
        self.table_cabang.verticalHeader().setVisible(False)
        self.table_cabang.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.table_cabang.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked,
        )
        self.table_cabang.setMinimumHeight(120)
        self.table_cabang.setMaximumHeight(175)
        self.table_cabang.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        hdr = self.table_cabang.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_cabang.setColumnWidth(0, SETTING_BRANCH_CODE_WIDTH)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table_cabang.setColumnWidth(2, SETTING_BRANCH_PREFIX_WIDTH)
        content_layout.addWidget(self.table_cabang)

        hint_cabang = QLabel("💡 Double-click baris untuk mengedit data cabang.")
        hint_cabang.setProperty("setting_hint_italic", True)
        hint_cabang.setWordWrap(True)
        content_layout.addWidget(hint_cabang)

        # =============================================================
        # 2. MASTER WILAYAH
        # =============================================================
        lbl_wilayah = QLabel("Master Wilayah")
        lbl_wilayah.setStyleSheet("font-weight: 700; margin-top: 2px;")
        content_layout.addWidget(lbl_wilayah)

        self.table_wilayah = QTableWidget(0, 3)
        self.table_wilayah.setHorizontalHeaderLabels([
            "KODE WILAYAH", "NAMA WILAYAH", "",
        ])
        self.table_wilayah.setAlternatingRowColors(True)
        self.table_wilayah.verticalHeader().setVisible(False)
        self.table_wilayah.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.table_wilayah.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.table_wilayah.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        self.table_wilayah.setMinimumHeight(120)
        self.table_wilayah.setMaximumHeight(175)
        self.table_wilayah.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        hdr_w = self.table_wilayah.horizontalHeader()
        hdr_w.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_wilayah.setColumnWidth(0, SETTING_BRANCH_CODE_WIDTH + 30)
        hdr_w.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr_w.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table_wilayah.setColumnWidth(2, SETTING_ACCOUNT_ACTION_WIDTH)
        content_layout.addWidget(self.table_wilayah)

        form_wilayah = QHBoxLayout()
        form_wilayah.setSpacing(SETTING_ACCOUNT_INPUT_SPACING)

        self.txt_kode_wilayah = QLineEdit()
        self.txt_kode_wilayah.setPlaceholderText("KODE WILAYAH...")
        self.txt_kode_wilayah.setFixedWidth(SETTING_BRANCH_CODE_WIDTH + 30)
        self.txt_kode_wilayah.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_kode_wilayah)
        )

        self.txt_nama_wilayah = QLineEdit()
        self.txt_nama_wilayah.setPlaceholderText("NAMA WILAYAH...")
        self.txt_nama_wilayah.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_nama_wilayah)
        )

        self.btn_add_wilayah = QPushButton("+")
        self.btn_add_wilayah.setFixedWidth(SETTING_ACCOUNT_ACTION_WIDTH)
        self.btn_add_wilayah.setProperty("setting_wilayah_add", True)
        self.btn_add_wilayah.clicked.connect(self.tambah_atau_update_wilayah)

        form_wilayah.addWidget(self.txt_kode_wilayah)
        form_wilayah.addWidget(self.txt_nama_wilayah, stretch=1)
        form_wilayah.addWidget(self.btn_add_wilayah)
        content_layout.addLayout(form_wilayah)

        hint_wilayah = QLabel(
            "💡 Semua wilayah dianggap provinsi dan aktif. Double-click baris untuk edit."
        )
        hint_wilayah.setProperty("setting_hint_italic", True)
        hint_wilayah.setWordWrap(True)
        content_layout.addWidget(hint_wilayah)

        self.table_wilayah.itemDoubleClicked.connect(self.edit_wilayah_row)
        self._editing_wilayah_row = None
        self._editing_wilayah_original_code = ""
        self._wilayah_pending_delete = set()

        # =============================================================
        # 3. ATURAN PREFIX PER CABANG
        # =============================================================
        lbl_prefix = QLabel("Aturan Prefix Resi per Cabang")
        lbl_prefix.setStyleSheet("font-weight: 700; margin-top: 2px;")
        content_layout.addWidget(lbl_prefix)

        self.table_cabang_wilayah = QTableWidget(0, 4)
        self.table_cabang_wilayah.setHorizontalHeaderLabels([
            "CABANG", "WILAYAH", "PREFIX RESI", "",
        ])
        self.table_cabang_wilayah.setAlternatingRowColors(True)
        self.table_cabang_wilayah.verticalHeader().setVisible(False)
        self.table_cabang_wilayah.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.table_cabang_wilayah.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.table_cabang_wilayah.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        self.table_cabang_wilayah.setMinimumHeight(120)
        self.table_cabang_wilayah.setMaximumHeight(175)
        self.table_cabang_wilayah.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        hdr_cw = self.table_cabang_wilayah.horizontalHeader()
        hdr_cw.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_cabang_wilayah.setColumnWidth(0, SETTING_BRANCH_CODE_WIDTH + 10)
        hdr_cw.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr_cw.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table_cabang_wilayah.setColumnWidth(2, SETTING_BRANCH_PREFIX_WIDTH)
        hdr_cw.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table_cabang_wilayah.setColumnWidth(3, SETTING_ACCOUNT_ACTION_WIDTH)
        content_layout.addWidget(self.table_cabang_wilayah)

        form_cw = QHBoxLayout()
        form_cw.setSpacing(SETTING_ACCOUNT_INPUT_SPACING)

        self.cmb_cabang_rule = QComboBox()
        self.cmb_wilayah_rule = QComboBox()
        self.txt_prefix_rule = QLineEdit()
        self.txt_prefix_rule.setPlaceholderText("PREFIX RESI...")
        self.txt_prefix_rule.setFixedWidth(SETTING_BRANCH_PREFIX_WIDTH)
        self.txt_prefix_rule.textChanged.connect(
            lambda: self.paksa_kapital_lineedit(self.txt_prefix_rule)
        )

        self.btn_add_cabang_wilayah = QPushButton("+")
        self.btn_add_cabang_wilayah.setFixedWidth(SETTING_ACCOUNT_ACTION_WIDTH)
        self.btn_add_cabang_wilayah.clicked.connect(
            self.tambah_atau_update_cabang_wilayah
        )

        form_cw.addWidget(self.cmb_cabang_rule, 1)
        form_cw.addWidget(self.cmb_wilayah_rule, 2)
        form_cw.addWidget(self.txt_prefix_rule)
        form_cw.addWidget(self.btn_add_cabang_wilayah)
        content_layout.addLayout(form_cw)

        hint_cw = QLabel(
            "💡 Satu kombinasi cabang + wilayah hanya boleh memiliki satu prefix."
        )
        hint_cw.setProperty("setting_hint_italic", True)
        hint_cw.setWordWrap(True)
        content_layout.addWidget(hint_cw)

        self.table_cabang_wilayah.itemDoubleClicked.connect(
            self.edit_cabang_wilayah_row
        )
        self._editing_cabang_wilayah_row = None

        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def _build_page_user_access(self):
        layout = QVBoxLayout(self.page_user_access)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Manajemen User & Akses Cabang")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        self.group_user_access = QGroupBox("Akun User dan Hak Akses Cabang")
        vbox = QVBoxLayout(self.group_user_access)
        vbox.setContentsMargins(*SETTING_BRANCH_GROUP_MARGINS)
        vbox.setSpacing(SETTING_BRANCH_GROUP_SPACING)

        action_bar = QHBoxLayout()
        self.btn_tambah_user = QPushButton("Tambah User")
        self.btn_edit_user = QPushButton("Edit User")
        self.btn_reset_password_user = QPushButton("Reset Password")
        self.btn_toggle_status_user = QPushButton("Nonaktifkan")
        self.btn_tambah_user.clicked.connect(self.tambah_user)
        self.btn_edit_user.clicked.connect(self.edit_user_terpilih)
        self.btn_reset_password_user.clicked.connect(self.reset_password_user_terpilih)
        self.btn_toggle_status_user.clicked.connect(self.toggle_status_user_terpilih)
        for button in (
                self.btn_tambah_user,
                self.btn_edit_user,
                self.btn_reset_password_user,
                self.btn_toggle_status_user,
        ):
            action_bar.addWidget(button)
        action_bar.addStretch()

        self.table_user_access = QTableWidget()
        self.table_user_access.setAlternatingRowColors(True)
        self.table_user_access.verticalHeader().setVisible(False)
        self.table_user_access.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.table_user_access.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.table_user_access.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        self.table_user_access.setMinimumHeight(300)
        self.table_user_access.itemSelectionChanged.connect(
            self._update_user_action_state
        )
        self.table_user_access.itemDoubleClicked.connect(
            lambda _item: self.edit_user_terpilih()
        )

        self.lbl_user_access_hint = QLabel(
            "💡 SUPER dapat membuat/edit/reset/nonaktifkan user. ADMIN hanya "
            "dapat melihat. HOME selalu aktif. Role pusat memakai akses AUTO ke "
            "seluruh cabang bisnis. User tidak dihapus agar histori tetap utuh."
        )
        self.lbl_user_access_hint.setWordWrap(True)
        self.lbl_user_access_hint.setProperty("setting_hint_italic", True)

        self.btn_simpan_akses_user = QPushButton("SIMPAN")
        self.btn_simpan_akses_user.clicked.connect(self.simpan_akses_user)

        vbox.addLayout(action_bar)
        vbox.addWidget(self.table_user_access)
        vbox.addWidget(self.lbl_user_access_hint)
        vbox.addWidget(self.btn_simpan_akses_user)
        layout.addWidget(self.group_user_access)
        layout.addStretch()

    @staticmethod
    def _boleh_edit_setting():
        role = str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper()
        return role in {"SUPER", "SUPER_ADMIN"}

    @staticmethod
    def _akses_user_otomatis(role, home):
        role_bersih = str(role or "ADMIN").strip().upper()
        home_bersih = str(home or "").strip().upper()
        return (
                role_bersih in CENTRAL_BRANCH_ROLES
                or home_bersih == "PUSAT"
        )

    def load_user_branch_access(self):
        try:
            payload = db_service.ambil_data_akses_cabang_user() or {}
            branches = list(payload.get("branches") or [])
            users = list(payload.get("users") or [])
        except Exception as exc:
            print(f"[TabSetting] Gagal memuat akses user: {exc}")
            branches, users = [], []

        self._user_access_branches = branches
        self._user_access_users = users
        base_headers = [
            "USERNAME", "NAMA LENGKAP", "ROLE", "HOME BRANCH", "STATUS", "MODE"
        ]
        branch_headers = [
            str(branch.get("kode_cabang") or "").strip().upper()
            for branch in branches
        ]
        headers = base_headers + branch_headers

        table = self.table_user_access

        # Optimasi Rendering Tabel
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        try:
            table.clear()
            table.setColumnCount(len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.setRowCount(len(users))

            hdr = table.horizontalHeader()
            for column in range(len(headers)):
                hdr.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
            if len(headers) > 1:
                hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

            role_session = str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper()
            boleh_edit = role_session in {"SUPER", "SUPER_ADMIN"}

            for row_index, user in enumerate(users):
                id_user = str(user.get("id_user") or "").strip()
                username = str(user.get("username") or "").strip().upper()
                nama_lengkap = str(user.get("nama_lengkap") or "").strip()
                role = str(user.get("role") or "ADMIN").strip().upper()
                home = str(user.get("kode_cabang") or "").strip().upper()
                home_nama = str(user.get("nama_cabang") or home).strip()
                status = str(user.get("status_user") or "AKTIF").strip().upper()
                akses = {
                    str(kode or "").strip().upper()
                    for kode in user.get("akses_cabang", [])
                    if str(kode or "").strip()
                }
                otomatis = bool(
                    user.get("akses_otomatis")
                    or self._akses_user_otomatis(role, home)
                )

                item_user = QTableWidgetItem(username or id_user)
                item_user.setData(Qt.ItemDataRole.UserRole, id_user)
                table.setItem(row_index, 0, item_user)
                table.setItem(row_index, 1, QTableWidgetItem(nama_lengkap))
                table.setItem(row_index, 2, QTableWidgetItem(role))
                table.setItem(
                    row_index, 3,
                    QTableWidgetItem(f"{home_nama} ({home})" if home else home_nama),
                )
                table.setItem(row_index, 4, QTableWidgetItem(status))
                table.setItem(
                    row_index, 5,
                    QTableWidgetItem("AUTO (ROLE)" if otomatis else "MANUAL"),
                )

                for branch_offset, branch in enumerate(branches, start=6):
                    kode = str(branch.get("kode_cabang") or "").strip().upper()
                    item = QTableWidgetItem("")
                    checked = otomatis or kode == home or kode in akses
                    item.setCheckState(
                        Qt.CheckState.Checked if checked
                        else Qt.CheckState.Unchecked
                    )

                    editable = boleh_edit and not otomatis and kode != home
                    flags = item.flags()
                    if editable:
                        item.setFlags(flags | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setToolTip(f"Izinkan user mengakses cabang {kode}")
                    else:
                        item.setFlags(flags & ~Qt.ItemFlag.ItemIsUserCheckable)
                        if otomatis:
                            item.setToolTip("Akses otomatis berdasarkan role/home PUSAT")
                        elif kode == home:
                            item.setToolTip("Home branch wajib selalu aktif")
                        elif not boleh_edit:
                            item.setToolTip("Mode read-only")
                    table.setItem(row_index, branch_offset, item)
        finally:
            table.setUpdatesEnabled(True)
            table.blockSignals(False)

        if users and table.currentRow() < 0:
            table.selectRow(0)
        self.validasi_hak_akses_setting()
        self._update_user_action_state()

    def _user_terpilih(self):
        row = self.table_user_access.currentRow()
        if row < 0:
            return None
        item = self.table_user_access.item(row, 0)
        if item is None:
            return None
        id_user = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        return next(
            (
                dict(user)
                for user in getattr(self, "_user_access_users", [])
                if str(user.get("id_user") or "").strip() == id_user
            ),
            None,
        )

    def _update_user_action_state(self):
        if not hasattr(self, "btn_tambah_user"):
            return
        role_session = str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper()
        boleh_edit = role_session in {"SUPER", "SUPER_ADMIN"}
        user = self._user_terpilih()
        punya_pilihan = user is not None

        self.btn_tambah_user.setEnabled(boleh_edit)
        self.btn_edit_user.setEnabled(boleh_edit and punya_pilihan)
        self.btn_reset_password_user.setEnabled(boleh_edit and punya_pilihan)

        is_self = bool(
            user
            and str(user.get("id_user") or "").strip()
            == str(CURRENT_SESSION.get("id_user") or "").strip()
        )
        self.btn_toggle_status_user.setEnabled(
            boleh_edit and punya_pilihan and not is_self
        )
        status = str((user or {}).get("status_user") or "AKTIF").strip().upper()
        self.btn_toggle_status_user.setText(
            "AKTIFKAN" if status == "NONAKTIF" else "NONAKTIFKAN"
        )
        self.btn_simpan_akses_user.setEnabled(boleh_edit)

    def _ambil_akses_user_tabel(self):
        branches = list(getattr(self, "_user_access_branches", []) or [])
        result = []
        for row in range(self.table_user_access.rowCount()):
            user_item = self.table_user_access.item(row, 0)
            if user_item is None:
                continue
            id_user = str(
                user_item.data(Qt.ItemDataRole.UserRole) or ""
            ).strip()
            if not id_user:
                continue

            selected = []
            for branch_offset, branch in enumerate(branches, start=6):
                item = self.table_user_access.item(row, branch_offset)
                if item is not None and item.checkState() == Qt.CheckState.Checked:
                    kode = str(branch.get("kode_cabang") or "").strip().upper()
                    if kode:
                        selected.append(kode)
            result.append({
                "id_user": id_user,
                "kode_cabang": selected,
            })
        return result

    def simpan_akses_user(self):
        if not self._boleh_edit_setting():
            QMessageBox.warning(
                self,
                "Akses Ditolak",
                "Hanya SUPER_ADMIN yang dapat mengubah akses cabang user.",
            )
            return

        rows = self._ambil_akses_user_tabel()
        if not rows:
            QMessageBox.information(
                self,
                "Tidak Ada User",
                "Belum ada akun database yang dapat diatur akses cabangnya.",
            )
            return

        sukses, pesan = db_service.simpan_akses_cabang_users(rows)
        if not sukses:
            QMessageBox.critical(
                self,
                "Gagal Menyimpan Akses",
                str(pesan or "Akses cabang user gagal disimpan."),
            )
            return

        self.load_user_branch_access()
        QMessageBox.information(
            self,
            "Akses User Tersimpan",
            "Hak akses cabang user berhasil diperbarui. Perubahan berlaku pada "
            "login berikutnya; user yang sedang aktif dapat melakukan refresh "
            "session/branch selector sesuai hak akses terbarunya.",
        )

    def _buat_dialog_user(self, user=None):
        is_edit = isinstance(user, dict)
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # Mencegah memory leak
        terapkan_style_input_global(dialog, self._tema_gelap_setting())
        dialog.setWindowTitle("Edit User" if is_edit else "Tambah User Baru")
        dialog.setModal(True)
        dialog.setMinimumWidth(520)
        root = QVBoxLayout(dialog)

        form = QFormLayout()
        self._init_form(form)
        txt_username = QLineEdit()
        txt_username.setPlaceholderText("Contoh: ADMINSBY")
        txt_nama = QLineEdit()
        txt_nama.setPlaceholderText("Nama lengkap user")
        cmb_role = QComboBox()
        cmb_role.addItems(["ADMIN", "FINANCE", "ADMIN_PUSAT", "OWNER", "SUPER"])
        cmb_home = QComboBox()

        branches = list(getattr(self, "_user_access_branches", []) or [])
        for branch in branches:
            kode = str(branch.get("kode_cabang") or "").strip().upper()
            nama = str(branch.get("nama_cabang") or kode).strip()
            if kode:
                cmb_home.addItem(f"{nama} ({kode})", kode)

        form.addRow("Username:", txt_username)
        form.addRow("Nama Lengkap:", txt_nama)
        form.addRow("Role:", cmb_role)
        form.addRow("Home Branch:", cmb_home)

        txt_password = None
        txt_konfirmasi = None
        if not is_edit:
            txt_password = QLineEdit()
            txt_password.setEchoMode(QLineEdit.EchoMode.Password)
            txt_konfirmasi = QLineEdit()
            txt_konfirmasi.setEchoMode(QLineEdit.EchoMode.Password)
            chk_tampilkan_password = QCheckBox("Tampilkan Password")

            def atur_tampilan_password(ditampilkan):
                mode = (
                    QLineEdit.EchoMode.Normal
                    if ditampilkan
                    else QLineEdit.EchoMode.Password
                )
                txt_password.setEchoMode(mode)
                txt_konfirmasi.setEchoMode(mode)

            chk_tampilkan_password.toggled.connect(atur_tampilan_password)
            form.addRow("Password:", txt_password)
            form.addRow("Konfirmasi:", txt_konfirmasi)
            form.addRow("", chk_tampilkan_password)

        root.addLayout(form)

        group_access = QGroupBox("Akses Cabang")
        access_layout = QVBoxLayout(group_access)
        checkboxes = {}
        for branch in branches:
            kode = str(branch.get("kode_cabang") or "").strip().upper()
            nama = str(branch.get("nama_cabang") or kode).strip()
            if not kode:
                continue
            checkbox = QCheckBox(f"{nama} ({kode})")
            checkboxes[kode] = checkbox
            access_layout.addWidget(checkbox)
        root.addWidget(group_access)

        lbl_info = QLabel(
            "HOME selalu aktif. Role pusat (SUPER_ADMIN/OWNER/ADMIN_PUSAT/FINANCE) "
            "mendapat akses AUTO ke seluruh cabang bisnis."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setProperty("setting_hint_italic", True)
        root.addWidget(lbl_info)

        def sync_access():
            role = str(cmb_role.currentText() or "ADMIN").strip().upper()
            home = str(cmb_home.currentData() or "").strip().upper()
            otomatis = self._akses_user_otomatis(role, home)
            for kode, checkbox in checkboxes.items():
                if otomatis:
                    checkbox.setChecked(True)
                    checkbox.setEnabled(False)
                elif kode == home:
                    checkbox.setChecked(True)
                    checkbox.setEnabled(False)
                else:
                    checkbox.setEnabled(True)

        cmb_role.currentTextChanged.connect(lambda _text: sync_access())
        cmb_home.currentIndexChanged.connect(lambda _index: sync_access())

        if is_edit:
            txt_username.setText(str(user.get("username") or ""))
            txt_username.setReadOnly(True)
            txt_nama.setText(str(user.get("nama_lengkap") or ""))
            role_value = str(user.get("role") or "ADMIN").upper()
            if role_value == "SUPER_ADMIN":
                role_value = "SUPER"
            idx_role = cmb_role.findText(role_value)
            cmb_role.setCurrentIndex(max(0, idx_role))
            idx_home = cmb_home.findData(str(user.get("kode_cabang") or "").upper())
            if idx_home >= 0:
                cmb_home.setCurrentIndex(idx_home)
            existing_access = {
                str(kode or "").strip().upper()
                for kode in user.get("akses_cabang", [])
            }
            for kode, checkbox in checkboxes.items():
                checkbox.setChecked(kode in existing_access)

            if str(user.get("id_user") or "") == str(CURRENT_SESSION.get("id_user") or ""):
                cmb_role.setEnabled(False)
                cmb_role.setToolTip("Role akun SUPER yang sedang login dikunci.")
        sync_access()

        hasil_dialog = {}

        def validasi_dan_terima():
            """Validasi form sebelum dialog boleh ditutup."""
            username = txt_username.text().strip().upper()
            nama = txt_nama.text().strip()
            role = cmb_role.currentText().strip().upper()
            # Local database_service lama masih mengenal SUPER_ADMIN; mapping sementara.
            role_service = "SUPER_ADMIN" if role == "SUPER" else role
            home = str(cmb_home.currentData() or "").strip().upper()

            if not username or not nama or not home:
                QMessageBox.warning(
                    dialog,
                    "Data Belum Lengkap",
                    "Username, Nama Lengkap, dan Home Branch wajib diisi.",
                )
                return

            payload = {
                "username": username,
                "nama_lengkap": nama,
                "role": role_service,
                "kode_cabang": home,
                "akses_cabang": [
                    kode for kode, checkbox in checkboxes.items()
                    if checkbox.isChecked()
                ],
            }

            if is_edit:
                payload["id_user"] = str(user.get("id_user") or "")
            else:
                password = txt_password.text() if txt_password is not None else ""
                konfirmasi = txt_konfirmasi.text() if txt_konfirmasi is not None else ""
                if not password:
                    QMessageBox.warning(
                        dialog,
                        "Password Kosong",
                        "Password wajib diisi.",
                    )
                    return
                if password != konfirmasi:
                    QMessageBox.warning(
                        dialog,
                        "Konfirmasi Password",
                        "Password dan konfirmasi password tidak sama.",
                    )
                    return
                payload["password"] = password

            hasil_dialog["payload"] = payload
            dialog.accept()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(validasi_dan_terima)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        return hasil_dialog.get("payload")

    def tambah_user(self):
        if not self._boleh_edit_setting():
            return
        payload = self._buat_dialog_user()
        if not payload:
            return
        sukses, pesan = db_service.buat_user_baru(payload)
        if not sukses:
            QMessageBox.critical(self, "Gagal Membuat User", str(pesan))
            return
        self.load_user_branch_access()
        QMessageBox.information(self, "User Dibuat", str(pesan))

    def edit_user_terpilih(self):
        if not self._boleh_edit_setting():
            return
        user = self._user_terpilih()
        if not user:
            QMessageBox.information(self, "Pilih User", "Pilih user yang ingin diedit.")
            return
        payload = self._buat_dialog_user(user)
        if not payload:
            return
        sukses, pesan = db_service.ubah_user(payload)
        if not sukses:
            QMessageBox.critical(self, "Gagal Mengubah User", str(pesan))
            return
        self.load_user_branch_access()
        QMessageBox.information(self, "User Diperbarui", str(pesan))

    def reset_password_user_terpilih(self):
        if not self._boleh_edit_setting():
            return
        user = self._user_terpilih()
        if not user:
            QMessageBox.information(self, "Pilih User", "Pilih user terlebih dahulu.")
            return

        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # Mencegah memory leak
        terapkan_style_input_global(dialog, self._tema_gelap_setting())
        dialog.setWindowTitle(f"Reset Password - {user.get('username', '')}")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        self._init_form(form)
        txt_password = QLineEdit()
        txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        txt_confirm = QLineEdit()
        txt_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        chk_tampilkan_password = QCheckBox("Tampilkan Password")

        def atur_tampilan_password(ditampilkan):
            mode = (
                QLineEdit.EchoMode.Normal
                if ditampilkan
                else QLineEdit.EchoMode.Password
            )
            txt_password.setEchoMode(mode)
            txt_confirm.setEchoMode(mode)

        chk_tampilkan_password.toggled.connect(atur_tampilan_password)
        form.addRow("Password Baru:", txt_password)
        form.addRow("Konfirmasi:", txt_confirm)
        form.addRow("", chk_tampilkan_password)
        layout.addLayout(form)

        password_tervalidasi = {}

        def validasi_dan_terima():
            password = txt_password.text()
            if not password:
                QMessageBox.warning(
                    dialog,
                    "Password Kosong",
                    "Password baru wajib diisi.",
                )
                return
            if password != txt_confirm.text():
                QMessageBox.warning(
                    dialog,
                    "Konfirmasi Password",
                    "Password dan konfirmasi password tidak sama.",
                )
                return
            password_tervalidasi["password"] = password
            dialog.accept()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(validasi_dan_terima)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        password = password_tervalidasi.get("password", "")
        sukses, pesan = db_service.reset_password_user(
            user.get("id_user"), password
        )
        if not sukses:
            QMessageBox.critical(self, "Gagal Reset Password", str(pesan))
            return
        QMessageBox.information(self, "Password Direset", str(pesan))

    def toggle_status_user_terpilih(self):
        if not self._boleh_edit_setting():
            return
        user = self._user_terpilih()
        if not user:
            return
        status = str(user.get("status_user") or "AKTIF").strip().upper()
        aktifkan = status == "NONAKTIF"
        aksi = "aktifkan" if aktifkan else "nonaktifkan"
        konfirmasi = QMessageBox.question(
            self,
            "Konfirmasi Status User",
            f"Yakin ingin {aksi} user {user.get('username', '')}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if konfirmasi != QMessageBox.StandardButton.Yes:
            return
        sukses, pesan = db_service.set_status_user(user.get("id_user"), aktifkan)
        if not sukses:
            QMessageBox.critical(self, "Gagal Mengubah Status", str(pesan))
            return
        self.load_user_branch_access()
        QMessageBox.information(self, "Status User", str(pesan))

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
        form.setContentsMargins(*SETTING_FORM_MARGINS)
        form.setVerticalSpacing(SETTING_FORM_VERTICAL_SPACING)
        form.setHorizontalSpacing(SETTING_FORM_HORIZONTAL_SPACING)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

    # ─────────────────────────────────────────────────────────────────
    # HAK AKSES ROLE VALIDATION
    # ─────────────────────────────────────────────────────────────────

    def validasi_hak_akses_setting(self):
        role = str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper()
        boleh_edit = role in {"SUPER", "SUPER_ADMIN"}
        boleh_lihat_user = role in {"SUPER", "SUPER_ADMIN", "OWNER", "ADMIN"}

        self.btn_simpan_all.setEnabled(boleh_edit)
        self.btn_simpan_all.setText(
            "SIMPAN PENGATURAN"
            if boleh_edit
            else "🔒 PENGATURAN TERKUNCI (VIEW-ONLY MODE)"
        )
        self.btn_simpan_all.setToolTip(
            "" if boleh_edit else
            "Hanya SUPER yang dapat memodifikasi konfigurasi sistem."
        )

        self.btn_add_np.setEnabled(boleh_edit)
        self.btn_add_p.setEnabled(boleh_edit)

        for widget_type in (QLineEdit, QTextEdit):
            for widget in self.findChildren(widget_type):
                widget.setReadOnly(not boleh_edit)

        for widget_type in (QComboBox, QTableWidget):
            for widget in self.findChildren(widget_type):
                widget.setEnabled(boleh_edit)

        if hasattr(self, "table_user_access"):
            self.table_user_access.setEnabled(boleh_lihat_user)
        if hasattr(self, "btn_simpan_akses_user"):
            self.btn_simpan_akses_user.setEnabled(boleh_edit)
        if hasattr(self, "btn_tambah_user"):
            self._update_user_action_state()

        self.txt_db_path.setReadOnly(True)

    # ─────────────────────────────────────────────────────────────────
    # MASTER WILAYAH
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalisasi_kode_wilayah(value):
        return re.sub(
            r"[^A-Z0-9_-]+",
            "",
            str(value or "").strip().upper(),
        )[:20]

    @staticmethod
    def _normalisasi_nama_wilayah(value):
        return " ".join(str(value or "").strip().upper().split())

    def _wilayah_connection(self):
        conn = db_service.get_db_connection(
            CURRENT_SESSION.get("db_name", "database_cargo.db")
        )
        conn.execute("PRAGMA busy_timeout = 20000")
        return conn

    def _style_wilayah_delete_button(self, button):
        styles = getattr(self, "_setting_styles", {})
        key = (
            "btn_row_delete"
            if button.isEnabled()
            else "btn_row_delete_disabled"
        )
        button.setStyleSheet(styles.get(key, ""))

    def _insert_wilayah_row(self, kode, nama, sync_id=""):
        row = self.table_wilayah.rowCount()
        self.table_wilayah.insertRow(row)

        item_kode = QTableWidgetItem(str(kode or "").strip().upper())
        item_kode.setData(Qt.ItemDataRole.UserRole, str(sync_id or ""))
        self.table_wilayah.setItem(row, 0, item_kode)
        self.table_wilayah.setItem(
            row, 1, QTableWidgetItem(self._normalisasi_nama_wilayah(nama))
        )

        button = QPushButton("-")
        button.setProperty("setting_row_delete", True)
        button.clicked.connect(
            lambda _, b=button: self.hapus_wilayah_via_tombol(b)
        )
        self.table_wilayah.setCellWidget(row, 2, button)
        self._style_wilayah_delete_button(button)

    def load_master_wilayah(self):
        if not hasattr(self, "table_wilayah"):
            return

        self.table_wilayah.setUpdatesEnabled(False)
        self.table_wilayah.blockSignals(True)
        try:
            self.table_wilayah.setRowCount(0)
            conn = self._wilayah_connection()
            try:
                rows = conn.execute(
                    """
                    SELECT kode_wilayah, nama_wilayah, tipe_wilayah,
                           aktif, sync_id
                    FROM master_wilayah
                    WHERE COALESCE(aktif, 1) = 1
                    ORDER BY COALESCE(urutan, 0), nama_wilayah COLLATE NOCASE
                    """
                ).fetchall()
            finally:
                conn.close()

            for row in rows:
                self._insert_wilayah_row(
                    kode=row[0],
                    nama=row[1],
                    sync_id=row[4],
                )
        except Exception as exc:
            print(f"[TabSetting] Gagal memuat master wilayah: {exc}")
        finally:
            self.table_wilayah.blockSignals(False)
            self.table_wilayah.setUpdatesEnabled(True)

    def _reset_form_wilayah(self):
        self._editing_wilayah_row = None
        self._editing_wilayah_original_code = ""
        self.txt_kode_wilayah.clear()
        self.txt_nama_wilayah.clear()
        self.btn_add_wilayah.setText("+")
        self.btn_add_wilayah.setToolTip("Tambah wilayah")

    def tambah_atau_update_wilayah(self):
        if not self._boleh_edit_setting():
            QMessageBox.warning(
                self,
                "Akses Ditolak",
                "Hanya SUPER yang dapat menambah atau mengubah wilayah.",
            )
            return

        kode = self._normalisasi_kode_wilayah(self.txt_kode_wilayah.text())
        nama = self._normalisasi_nama_wilayah(self.txt_nama_wilayah.text())

        if len(kode) < 2:
            QMessageBox.warning(
                self, "Data Belum Lengkap", "Kode wilayah minimal 2 karakter."
            )
            return
        if not nama:
            QMessageBox.warning(
                self, "Data Belum Lengkap", "Nama wilayah wajib diisi."
            )
            return

        edit_row = self._editing_wilayah_row
        for row in range(self.table_wilayah.rowCount()):
            if row == edit_row:
                continue
            item = self.table_wilayah.item(row, 0)
            if item and self._normalisasi_kode_wilayah(item.text()) == kode:
                QMessageBox.warning(
                    self,
                    "Kode Duplikat",
                    f"Kode wilayah '{kode}' sudah digunakan.",
                )
                return

        if edit_row is not None and 0 <= edit_row < self.table_wilayah.rowCount():
            original_code = self._normalisasi_kode_wilayah(
                self._editing_wilayah_original_code
            )
            item_code = self.table_wilayah.item(edit_row, 0)
            if original_code and original_code != kode:
                self._wilayah_pending_delete.add(original_code)
                if item_code is not None:
                    item_code.setData(Qt.ItemDataRole.UserRole, str(uuid.uuid4()))

            self.table_wilayah.item(edit_row, 0).setText(kode)
            self.table_wilayah.item(edit_row, 1).setText(nama)
            self._wilayah_pending_delete.discard(kode)
        else:
            self._insert_wilayah_row(
                kode=kode,
                nama=nama,
                sync_id=str(uuid.uuid4()),
            )

        self._reset_form_wilayah()

    def edit_wilayah_row(self, item):
        row = item.row()
        if row < 0 or row >= self.table_wilayah.rowCount():
            return

        self._editing_wilayah_row = row
        self._editing_wilayah_original_code = (
            self.table_wilayah.item(row, 0).text().strip().upper()
            if self.table_wilayah.item(row, 0) else ""
        )
        self.txt_kode_wilayah.setText(
            self.table_wilayah.item(row, 0).text()
            if self.table_wilayah.item(row, 0) else ""
        )
        self.txt_nama_wilayah.setText(
            self.table_wilayah.item(row, 1).text()
            if self.table_wilayah.item(row, 1) else ""
        )
        self.btn_add_wilayah.setText("✓")
        self.btn_add_wilayah.setToolTip("Terapkan perubahan baris ini")

    def hapus_wilayah_via_tombol(self, button):
        for row in range(self.table_wilayah.rowCount()):
            if self.table_wilayah.cellWidget(row, 2) is not button:
                continue

            kode = (
                self.table_wilayah.item(row, 0).text().strip().upper()
                if self.table_wilayah.item(row, 0)
                else ""
            )
            nama = (
                self.table_wilayah.item(row, 1).text().strip()
                if self.table_wilayah.item(row, 1)
                else kode
            )

            answer = QMessageBox.question(
                self,
                "Nonaktifkan Wilayah",
                f"Nonaktifkan wilayah berikut?\n\n"
                f"{kode} — {nama}\n\n"
                "Wilayah tidak dihapus permanen agar histori sinkronisasi tetap aman.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

            item_kode = self.table_wilayah.item(row, 0)
            sync_id = (
                str(item_kode.data(Qt.ItemDataRole.UserRole) or "").strip()
                if item_kode else ""
            )
            if sync_id:
                self._wilayah_pending_delete.add(kode)

            self.table_wilayah.removeRow(row)
            self._editing_wilayah_row = None
            self._reset_form_wilayah()
            return

    def _ambil_wilayah_tabel(self):
        rows = []
        codes = set()

        for row in range(self.table_wilayah.rowCount()):
            item_kode = self.table_wilayah.item(row, 0)
            item_nama = self.table_wilayah.item(row, 1)

            kode = self._normalisasi_kode_wilayah(
                item_kode.text() if item_kode else ""
            )
            nama = self._normalisasi_nama_wilayah(
                item_nama.text() if item_nama else ""
            )
            sync_id = (
                str(item_kode.data(Qt.ItemDataRole.UserRole) or "").strip()
                if item_kode else ""
            )

            if not kode and not nama:
                continue
            if not kode or not nama:
                raise ValueError(f"Baris wilayah {row + 1} belum lengkap.")
            if kode in codes:
                raise ValueError(f"Kode wilayah '{kode}' digunakan dua kali.")

            rows.append({
                "kode_wilayah": kode,
                "nama_wilayah": nama,
                "tipe_wilayah": "PROVINSI",
                "aktif": 1,
                "urutan": (row + 1) * 10,
                "sync_id": sync_id or str(uuid.uuid4()),
            })
            codes.add(kode)

        return rows

    # ────────────────────────────────────────────────────────────────
    # ATURAN PREFIX PER CABANG
    # ────────────────────────────────────────────────────────────────

    def _reset_form_cabang_wilayah(self):
        self._editing_cabang_wilayah_row = None
        self.cmb_cabang_rule.setCurrentIndex(
            0 if self.cmb_cabang_rule.count() else -1
        )
        self.cmb_wilayah_rule.setCurrentIndex(
            0 if self.cmb_wilayah_rule.count() else -1
        )
        self.txt_prefix_rule.clear()
        self.btn_add_cabang_wilayah.setText("+")
        self.btn_add_cabang_wilayah.setToolTip("Tambah aturan prefix")

    def _load_cabang_wilayah_combos(self):
        try:
            conn = self._wilayah_connection()
            try:
                branch_rows = conn.execute(
                    "SELECT kode_cabang, nama_cabang "
                    "FROM data_cabang ORDER BY kode_cabang"
                ).fetchall()
                wilayah_rows = conn.execute(
                    """
                    SELECT kode_wilayah, nama_wilayah
                    FROM master_wilayah
                    WHERE COALESCE(aktif, 1) = 1
                    ORDER BY COALESCE(urutan, 0), nama_wilayah COLLATE NOCASE
                    """
                ).fetchall()
            finally:
                conn.close()

            current_branch = self.cmb_cabang_rule.currentData()
            current_wilayah = self.cmb_wilayah_rule.currentData()

            self.cmb_cabang_rule.blockSignals(True)
            self.cmb_wilayah_rule.blockSignals(True)
            try:
                self.cmb_cabang_rule.clear()
                for kode, nama in branch_rows:
                    kode = str(kode or "").strip().upper()
                    nama = str(nama or kode).strip()
                    if kode:
                        self.cmb_cabang_rule.addItem(
                            f"{kode} — {nama}", kode
                        )

                self.cmb_wilayah_rule.clear()
                for kode, nama in wilayah_rows:
                    kode = str(kode or "").strip().upper()
                    nama = str(nama or kode).strip()
                    if kode:
                        self.cmb_wilayah_rule.addItem(
                            f"{kode} — {nama}", kode
                        )
            finally:
                self.cmb_cabang_rule.blockSignals(False)
                self.cmb_wilayah_rule.blockSignals(False)

            if current_branch is not None:
                idx = self.cmb_cabang_rule.findData(
                    str(current_branch).upper()
                )
                if idx >= 0:
                    self.cmb_cabang_rule.setCurrentIndex(idx)

            if current_wilayah is not None:
                idx = self.cmb_wilayah_rule.findData(
                    str(current_wilayah).upper()
                )
                if idx >= 0:
                    self.cmb_wilayah_rule.setCurrentIndex(idx)
        except Exception as exc:
            print(
                f"[TabSetting] Gagal memuat pilihan cabang/wilayah: {exc}"
            )

    def _insert_cabang_wilayah_row(
            self,
            kode_cabang,
            kode_wilayah,
            prefix_resi,
            sync_id="",
            nama_wilayah=None,
    ):
        row = self.table_cabang_wilayah.rowCount()
        self.table_cabang_wilayah.insertRow(row)

        kode_cabang = str(kode_cabang or "").strip().upper()
        kode_wilayah = str(kode_wilayah or "").strip().upper()
        prefix_resi = str(prefix_resi or "").strip().upper()
        nama_wilayah = str(nama_wilayah or kode_wilayah).strip()

        item_cabang = QTableWidgetItem(kode_cabang)
        item_cabang.setData(
            Qt.ItemDataRole.UserRole,
            {
                "sync_id": str(sync_id or ""),
                "kode_cabang": kode_cabang,
                "kode_wilayah": kode_wilayah,
            },
        )
        self.table_cabang_wilayah.setItem(row, 0, item_cabang)
        self.table_cabang_wilayah.setItem(
            row,
            1,
            QTableWidgetItem(f"{kode_wilayah} — {nama_wilayah}"),
        )
        self.table_cabang_wilayah.setItem(
            row, 2, QTableWidgetItem(prefix_resi)
        )

        button = QPushButton("-")
        button.setProperty("setting_row_delete", True)
        button.clicked.connect(
            lambda _, b=button: self.hapus_cabang_wilayah_via_tombol(b)
        )
        self.table_cabang_wilayah.setCellWidget(row, 3, button)
        self._style_wilayah_delete_button(button)

    def load_cabang_wilayah(self):
        if not hasattr(self, "table_cabang_wilayah"):
            return

        self._load_cabang_wilayah_combos()
        self.table_cabang_wilayah.setUpdatesEnabled(False)
        self.table_cabang_wilayah.blockSignals(True)
        try:
            self.table_cabang_wilayah.setRowCount(0)
            conn = self._wilayah_connection()
            try:
                rows = conn.execute(
                    """
                    SELECT cw.kode_cabang,
                           cw.kode_wilayah,
                           cw.prefix_resi,
                           cw.sync_id,
                           COALESCE(mw.nama_wilayah, cw.kode_wilayah)
                    FROM cabang_wilayah cw
                    LEFT JOIN master_wilayah mw
                      ON mw.kode_wilayah = cw.kode_wilayah
                    WHERE COALESCE(cw.aktif, 1) = 1
                      AND cw.deleted_at IS NULL
                    ORDER BY cw.kode_cabang,
                             COALESCE(mw.urutan, 0),
                             mw.nama_wilayah COLLATE NOCASE
                    """
                ).fetchall()
            finally:
                conn.close()

            for row in rows:
                self._insert_cabang_wilayah_row(*row)
        except Exception as exc:
            print(
                f"[TabSetting] Gagal memuat aturan prefix cabang: {exc}"
            )
        finally:
            self.table_cabang_wilayah.blockSignals(False)
            self.table_cabang_wilayah.setUpdatesEnabled(True)

        self._reset_form_cabang_wilayah()

    def _find_cabang_wilayah_duplicate(
            self, kode_cabang, kode_wilayah, skip_row=None
    ):
        for row in range(self.table_cabang_wilayah.rowCount()):
            if row == skip_row:
                continue
            item = self.table_cabang_wilayah.item(row, 0)
            meta = item.data(Qt.ItemDataRole.UserRole) if item else {}
            if not isinstance(meta, dict):
                meta = {}
            row_cabang = str(meta.get("kode_cabang") or "").strip().upper()
            row_wilayah = str(meta.get("kode_wilayah") or "").strip().upper()
            if row_cabang == kode_cabang and row_wilayah == kode_wilayah:
                return row
        return None

    def tambah_atau_update_cabang_wilayah(self):
        if not self._boleh_edit_setting():
            QMessageBox.warning(
                self,
                "Akses Ditolak",
                "Hanya SUPER yang dapat mengatur prefix resi per cabang.",
            )
            return

        kode_cabang = str(
            self.cmb_cabang_rule.currentData() or ""
        ).strip().upper()
        kode_wilayah = str(
            self.cmb_wilayah_rule.currentData() or ""
        ).strip().upper()
        prefix = str(
            self.txt_prefix_rule.text() or ""
        ).strip().upper()

        if not kode_cabang or not kode_wilayah or not prefix:
            QMessageBox.warning(
                self,
                "Data Belum Lengkap",
                "Cabang, wilayah, dan prefix wajib diisi.",
            )
            return

        edit_row = self._editing_cabang_wilayah_row
        duplicate = self._find_cabang_wilayah_duplicate(
            kode_cabang, kode_wilayah, edit_row
        )
        if duplicate is not None:
            QMessageBox.warning(
                self,
                "Data Duplikat",
                f"Aturan {kode_cabang} + {kode_wilayah} sudah ada.",
            )
            return

        if edit_row is not None and 0 <= edit_row < self.table_cabang_wilayah.rowCount():
            item = self.table_cabang_wilayah.item(edit_row, 0)
            meta = item.data(Qt.ItemDataRole.UserRole) if item else {}
            if not isinstance(meta, dict):
                meta = {}
            meta["kode_cabang"] = kode_cabang
            meta["kode_wilayah"] = kode_wilayah
            if not meta.get("sync_id"):
                meta["sync_id"] = str(uuid.uuid4())

            item.setText(kode_cabang)
            item.setData(Qt.ItemDataRole.UserRole, meta)
            self.table_cabang_wilayah.item(edit_row, 1).setText(
                self.cmb_wilayah_rule.currentText()
            )
            self.table_cabang_wilayah.item(edit_row, 2).setText(prefix)
        else:
            self._insert_cabang_wilayah_row(
                kode_cabang,
                kode_wilayah,
                prefix,
                str(uuid.uuid4()),
                self.cmb_wilayah_rule.currentText().split("—", 1)[-1].strip(),
            )

        self._reset_form_cabang_wilayah()

    def edit_cabang_wilayah_row(self, item):
        row = item.row()
        if row < 0 or row >= self.table_cabang_wilayah.rowCount():
            return

        item_cabang = self.table_cabang_wilayah.item(row, 0)
        meta = item_cabang.data(Qt.ItemDataRole.UserRole) if item_cabang else {}
        if not isinstance(meta, dict):
            meta = {}

        kode_cabang = str(meta.get("kode_cabang") or "").strip().upper()
        kode_wilayah = str(meta.get("kode_wilayah") or "").strip().upper()
        prefix_item = self.table_cabang_wilayah.item(row, 2)
        prefix = str(prefix_item.text() if prefix_item else "").strip().upper()

        idx = self.cmb_cabang_rule.findData(kode_cabang)
        if idx >= 0:
            self.cmb_cabang_rule.setCurrentIndex(idx)
        idx = self.cmb_wilayah_rule.findData(kode_wilayah)
        if idx >= 0:
            self.cmb_wilayah_rule.setCurrentIndex(idx)

        self.txt_prefix_rule.setText(prefix)
        self._editing_cabang_wilayah_row = row
        self.btn_add_cabang_wilayah.setText("✓")
        self.btn_add_cabang_wilayah.setToolTip(
            "Terapkan perubahan baris ini"
        )

    def hapus_cabang_wilayah_via_tombol(self, button):
        for row in range(self.table_cabang_wilayah.rowCount()):
            if self.table_cabang_wilayah.cellWidget(row, 3) is not button:
                continue

            item = self.table_cabang_wilayah.item(row, 0)
            meta = item.data(Qt.ItemDataRole.UserRole) if item else {}
            if not isinstance(meta, dict):
                meta = {}

            kode_cabang = str(meta.get("kode_cabang") or "").strip().upper()
            kode_wilayah = str(meta.get("kode_wilayah") or "").strip().upper()

            answer = QMessageBox.question(
                self,
                "Nonaktifkan Aturan Prefix",
                (
                    f"Nonaktifkan aturan {kode_cabang} + {kode_wilayah}?\n\n"
                    "Aturan tidak dihapus permanen."
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

            self.table_cabang_wilayah.removeRow(row)
            self._reset_form_cabang_wilayah()
            return

    def _ambil_cabang_wilayah_tabel(self):
        rows = []
        keys = set()

        for row in range(self.table_cabang_wilayah.rowCount()):
            item_cabang = self.table_cabang_wilayah.item(row, 0)
            item_prefix = self.table_cabang_wilayah.item(row, 2)
            meta = item_cabang.data(Qt.ItemDataRole.UserRole) if item_cabang else {}
            if not isinstance(meta, dict):
                meta = {}

            kode_cabang = str(meta.get("kode_cabang") or "").strip().upper()
            kode_wilayah = str(meta.get("kode_wilayah") or "").strip().upper()
            prefix = str(
                item_prefix.text() if item_prefix else ""
            ).strip().upper()

            if not kode_cabang or not kode_wilayah or not prefix:
                raise ValueError(
                    f"Aturan prefix baris {row + 1} belum lengkap."
                )

            key = (kode_cabang, kode_wilayah)
            if key in keys:
                raise ValueError(
                    f"Aturan {kode_cabang} + {kode_wilayah} digunakan dua kali."
                )

            rows.append(
                {
                    "kode_cabang": kode_cabang,
                    "kode_wilayah": kode_wilayah,
                    "prefix_resi": prefix,
                    "aktif": 1,
                    "sync_id": str(meta.get("sync_id") or uuid.uuid4()),
                }
            )
            keys.add(key)

        return rows

    def _simpan_cabang_wilayah_local(self, desired_rows):
        conn = self._wilayah_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")

            existing_rows = conn.execute(
                """
                SELECT kode_cabang, kode_wilayah, prefix_resi, aktif,
                       sync_id, deleted_at
                FROM cabang_wilayah
                """
            ).fetchall()
            existing = {
                (str(row[0]).strip().upper(), str(row[1]).strip().upper()): {
                    "prefix_resi": row[2],
                    "aktif": row[3],
                    "sync_id": row[4],
                    "deleted_at": row[5],
                }
                for row in existing_rows
            }

            desired_keys = set()

            def enqueue(operation, payload):
                record_key = str(
                    payload.get("sync_id")
                    or f"{payload.get('kode_cabang')}::{payload.get('kode_wilayah')}"
                )
                conn.execute(
                    """
                    DELETE FROM sync_outbox
                    WHERE table_name = 'cabang_wilayah'
                      AND record_key = ?
                      AND status = 'PENDING'
                    """,
                    (record_key,),
                )
                conn.execute(
                    """
                    INSERT INTO sync_outbox(
                        table_name, record_key, operation, payload_json
                    ) VALUES ('cabang_wilayah', ?, ?, ?)
                    """,
                    (
                        record_key,
                        operation,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )

            for row in desired_rows:
                key = (row["kode_cabang"], row["kode_wilayah"])
                desired_keys.add(key)
                old = existing.get(key)
                sync_id = str(
                    row.get("sync_id")
                    or (old or {}).get("sync_id")
                    or uuid.uuid4()
                )
                payload = dict(row)
                payload["sync_id"] = sync_id

                if old is None:
                    conn.execute(
                        """
                        INSERT INTO cabang_wilayah(
                            kode_cabang, kode_wilayah, prefix_resi, aktif,
                            sync_id, created_at, updated_at, deleted_at
                        ) VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP,
                                  CURRENT_TIMESTAMP, NULL)
                        """,
                        (
                            row["kode_cabang"],
                            row["kode_wilayah"],
                            row["prefix_resi"],
                            sync_id,
                        ),
                    )
                    enqueue("INSERT", payload)
                    continue

                changed = (
                        str(old.get("prefix_resi") or "").upper()
                        != row["prefix_resi"]
                        or int(old.get("aktif") or 0) != 1
                        or old.get("deleted_at") is not None
                        or str(old.get("sync_id") or "") != sync_id
                )
                if changed:
                    conn.execute(
                        """
                        UPDATE cabang_wilayah
                        SET prefix_resi = ?,
                            aktif = 1,
                            sync_id = ?,
                            updated_at = CURRENT_TIMESTAMP,
                            deleted_at = NULL
                        WHERE kode_cabang = ?
                          AND kode_wilayah = ?
                        """,
                        (
                            row["prefix_resi"],
                            sync_id,
                            row["kode_cabang"],
                            row["kode_wilayah"],
                        ),
                    )
                    enqueue("UPDATE", payload)

            for key, old in existing.items():
                if key in desired_keys:
                    continue
                if int(old.get("aktif") or 0) != 1:
                    continue
                if old.get("deleted_at") is not None:
                    continue

                payload = {
                    "kode_cabang": key[0],
                    "kode_wilayah": key[1],
                    "prefix_resi": old.get("prefix_resi"),
                    "aktif": 0,
                    "sync_id": old.get("sync_id") or str(uuid.uuid4()),
                    "deleted_at": datetime.now().astimezone().isoformat(),
                }
                conn.execute(
                    """
                    UPDATE cabang_wilayah
                    SET aktif = 0,
                        updated_at = CURRENT_TIMESTAMP,
                        deleted_at = CURRENT_TIMESTAMP
                    WHERE kode_cabang = ?
                      AND kode_wilayah = ?
                    """,
                    key,
                )
                enqueue("DELETE", payload)

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _enqueue_wilayah(cursor, operation, payload):
        cursor.execute(
            """
            INSERT INTO sync_outbox(
                table_name, record_key, operation, payload_json
            ) VALUES ('master_wilayah', ?, ?, ?)
            """,
            (
                str(payload.get("sync_id") or payload.get("kode_wilayah")),
                operation,
                json.dumps(payload, ensure_ascii=False),
            ),
        )

    def _simpan_master_wilayah_local(self, rows):
        conn = self._wilayah_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")

            existing_rows = {
                str(row[0]).strip().upper(): row
                for row in conn.execute(
                    """
                    SELECT kode_wilayah, nama_wilayah, tipe_wilayah, aktif,
                           urutan, sync_id, created_at, updated_at, deleted_at
                    FROM master_wilayah
                    """
                ).fetchall()
            }

            for row in rows:
                kode = row["kode_wilayah"]
                existing = existing_rows.get(kode)

                if existing:
                    (
                        _old_kode,
                        old_nama,
                        old_tipe,
                        old_aktif,
                        old_urutan,
                        old_sync_id,
                        _old_created,
                        _old_updated,
                        old_deleted,
                    ) = existing

                    changed = (
                            self._normalisasi_nama_wilayah(old_nama) != row["nama_wilayah"]
                            or str(old_tipe or "PROVINSI").upper() != row["tipe_wilayah"]
                            or int(old_aktif or 0) != int(row["aktif"])
                            or int(old_urutan or 0) != int(row["urutan"])
                            or bool(old_deleted) != (not bool(row["aktif"]))
                    )
                    if not changed:
                        continue

                    conn.execute(
                        """
                        UPDATE master_wilayah
                        SET nama_wilayah = ?,
                            tipe_wilayah = ?,
                            aktif = ?,
                            urutan = ?,
                            updated_at = CURRENT_TIMESTAMP,
                            deleted_at = ?
                        WHERE kode_wilayah = ?
                        """,
                        (
                            row["nama_wilayah"],
                            row["tipe_wilayah"],
                            int(row["aktif"]),
                            int(row["urutan"]),
                            None if row["aktif"] else None,
                            kode,
                        ),
                    )
                    if not row["aktif"]:
                        conn.execute(
                            """
                            UPDATE master_wilayah
                            SET deleted_at = CURRENT_TIMESTAMP
                            WHERE kode_wilayah = ?
                            """,
                            (kode,),
                        )

                    fresh = conn.execute(
                        """
                        SELECT kode_wilayah, nama_wilayah, tipe_wilayah, aktif,
                               urutan, sync_id, created_at, updated_at, deleted_at
                        FROM master_wilayah
                        WHERE kode_wilayah = ?
                        LIMIT 1
                        """,
                        (kode,),
                    ).fetchone()

                    payload = {
                        "kode_wilayah": fresh[0],
                        "nama_wilayah": fresh[1],
                        "tipe_wilayah": fresh[2],
                        "aktif": int(fresh[3] or 0),
                        "urutan": int(fresh[4] or 0),
                        "sync_id": fresh[5],
                        "created_at": fresh[6],
                        "updated_at": fresh[7],
                        "deleted_at": fresh[8],
                    }
                    self._enqueue_wilayah(
                        conn,
                        "DELETE" if not row["aktif"] else "UPDATE",
                        payload,
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO master_wilayah(
                            kode_wilayah, nama_wilayah, tipe_wilayah,
                            aktif, urutan, sync_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            kode,
                            row["nama_wilayah"],
                            row["tipe_wilayah"],
                            int(row["aktif"]),
                            int(row["urutan"]),
                            row["sync_id"],
                        ),
                    )
                    fresh = conn.execute(
                        """
                        SELECT kode_wilayah, nama_wilayah, tipe_wilayah, aktif,
                               urutan, sync_id, created_at, updated_at, deleted_at
                        FROM master_wilayah
                        WHERE kode_wilayah = ?
                        LIMIT 1
                        """,
                        (kode,),
                    ).fetchone()
                    payload = {
                        "kode_wilayah": fresh[0],
                        "nama_wilayah": fresh[1],
                        "tipe_wilayah": int(1 if fresh[3] else 0),
                        "aktif": int(fresh[3] or 0),
                        "urutan": int(fresh[4] or 0),
                        "sync_id": fresh[5],
                        "created_at": fresh[6],
                        "updated_at": fresh[7],
                        "deleted_at": fresh[8],
                    }
                    payload["tipe_wilayah"] = fresh[2]
                    self._enqueue_wilayah(conn, "INSERT", payload)

            for kode in list(self._wilayah_pending_delete):
                existing = conn.execute(
                    """
                    SELECT kode_wilayah, nama_wilayah, tipe_wilayah,
                           aktif, urutan, sync_id, created_at, updated_at, deleted_at
                    FROM master_wilayah
                    WHERE kode_wilayah = ?
                    LIMIT 1
                    """,
                    (kode,),
                ).fetchone()
                if existing is None:
                    continue

                conn.execute(
                    """
                    UPDATE master_wilayah
                    SET aktif = 0,
                        updated_at = CURRENT_TIMESTAMP,
                        deleted_at = CURRENT_TIMESTAMP
                    WHERE kode_wilayah = ?
                    """,
                    (kode,),
                )
                fresh = conn.execute(
                    """
                    SELECT kode_wilayah, nama_wilayah, tipe_wilayah, aktif,
                           urutan, sync_id, created_at, updated_at, deleted_at
                    FROM master_wilayah
                    WHERE kode_wilayah = ?
                    LIMIT 1
                    """,
                    (kode,),
                ).fetchone()
                self._enqueue_wilayah(
                    conn,
                    "DELETE",
                    {
                        "kode_wilayah": fresh[0],
                        "nama_wilayah": fresh[1],
                        "tipe_wilayah": fresh[2],
                        "aktif": 0,
                        "urutan": int(fresh[4] or 0),
                        "sync_id": fresh[5],
                        "created_at": fresh[6],
                        "updated_at": fresh[7],
                        "deleted_at": fresh[8],
                    },
                )

            active_names = [
                row["nama_wilayah"]
                for row in rows
                if int(row["aktif"]) == 1
            ]
            conn.execute(
                """
                INSERT INTO pengaturan_sistem(kunci, nilai)
                VALUES ('provinsi_tujuan', ?)
                ON CONFLICT(kunci) DO UPDATE SET nilai = excluded.nilai
                """,
                (json.dumps(active_names, ensure_ascii=False),),
            )

            conn.commit()
            self._wilayah_pending_delete.clear()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

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
        table.setMinimumHeight(SETTING_ACCOUNT_TABLE_MIN_HEIGHT)

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(0, SETTING_BANK_FIELD_WIDTH)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(1, SETTING_ACCOUNT_NUMBER_WIDTH)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(3, SETTING_ACCOUNT_ACTION_WIDTH)

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

        if not self._boleh_edit_setting():
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
        if not self._boleh_edit_setting():
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
        if event.type() in (
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
                QEvent.Type.StyleChange,
        ):
            self._jadwalkan_tema_setting()

    def eventFilter(self, watched, event):
        if watched is QApplication.instance() and event.type() in (
                QEvent.Type.ApplicationPaletteChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.StyleChange,
        ):
            self._jadwalkan_tema_setting()
        return super().eventFilter(watched, event)

    def _jadwalkan_tema_setting(self):
        if getattr(self, "_setting_ui_ready", False) and not self._setting_theme_applying:
            self._setting_theme_timer.start(0)

    def _tema_gelap_setting(self):
        widget = self
        while widget is not None:
            theme = str(getattr(widget, "current_theme", "") or widget.property("current_theme") or "").lower()
            if theme in {"dark", "light"}:
                return theme == "dark"
            widget = widget.parentWidget()

        app = QApplication.instance()
        if app is not None:
            theme = str(getattr(app, "current_theme", "") or app.property("current_theme") or "").lower()
            if theme in {"dark", "light"}:
                return theme == "dark"

            themes = {
                         str(getattr(window, "current_theme", "")).lower()
                         for window in app.topLevelWidgets()
                     } & {"dark", "light"}
            if len(themes) == 1:
                return themes == {"dark"}

        palette = app.palette() if app is not None else self.palette()
        return palette.color(QPalette.ColorRole.Window).lightness() < 128

    def showEvent(self, event):
        super().showEvent(event)
        self.sesuaikan_tema_lokal()

    def sesuaikan_tema_lokal(self):
        if not getattr(self, "_setting_ui_ready", False) or self._setting_theme_applying:
            return
        self._setting_theme_timer.stop()
        self._setting_theme_applying = True
        try:
            self._terapkan_tema_setting(self._tema_gelap_setting())
        finally:
            self._setting_theme_applying = False

    def _terapkan_tema_setting(self, is_dark):
        sizes = get_fixed_font_sizes()
        sz_base = sizes["sz_base"]
        sz_input = sizes["sz_input"]
        sz_title = sizes["sz_title"]

        s = get_setting_styles(is_dark, sz_base, sz_input, sz_title)
        self._setting_styles = s

        self.sidebar_container.setStyleSheet(s['sidebar_container'])
        self.sidebar_list.setStyleSheet(s['sidebar_list'])

        if hasattr(self, 'lbl_menu'):
            self.lbl_menu.setStyleSheet(s['lbl_menu'])

        groups = [
            self.group_ops,
            self.group_user_access,
            self.group_font,
        ]
        if hasattr(self, 'group_np'):
            groups.extend([self.group_np, self.group_p])

        for grp in groups:
            if grp is not None:
                grp.setStyleSheet(s['custom_groupbox'])

        for lbl in self.findChildren(QLabel):
            if lbl.property("is_page_title"):
                lbl.setStyleSheet(s['lbl_page_title'])
            elif lbl.property("setting_hint_italic"):
                lbl.setStyleSheet(s["lbl_info_italic"])
            elif not lbl.property(
                    "is_page_title",
            ):
                if hasattr(self, 'lbl_menu') and lbl == self.lbl_menu:
                    continue
                lbl.setStyleSheet(s['form_label'])

        tabel_setting = tuple(
            table for table in (
                getattr(self, "table_cabang", None),
                getattr(self, "table_user_access", None),
                getattr(self, "table_wilayah", None),
                getattr(self, "table_cabang_wilayah", None),
                getattr(self, "table_numbering", None),
                getattr(self, "table_np", None),
                getattr(self, "table_p", None),
                getattr(self, "table_options", None),
            ) if table is not None
        )

        for combo in (
                self.cmb_format_resi_manual,
                self.combo_font,
        ):
            font_combo = combo.font()
            font_combo.setFamily(get_master_font())
            font_combo.setPixelSize(max(1, sz_input))
            combo.setFont(font_combo)

            combo_view = combo.view()
            if combo_view is not None:
                combo_view.setFont(font_combo)

        for table in tabel_setting:
            table.setStyleSheet(s['table'])

        for button in (
                self.btn_tambah_user,
                self.btn_edit_user,
                self.btn_reset_password_user,
                self.btn_toggle_status_user,
                self.btn_simpan_akses_user,
        ):
            button.setStyleSheet(s.get('btn_secondary', ''))
        self.btn_simpan_all.setStyleSheet(s['btn_simpan'])

        if hasattr(self, 'table_np'):
            self.btn_add_np.setStyleSheet(s["btn_add_rekening"])
            self.btn_add_p.setStyleSheet(s["btn_add_rekening"])
        if hasattr(self, "btn_add_wilayah"):
            self.btn_add_wilayah.setStyleSheet(s.get("btn_add_rekening", ""))

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
        terapkan_style_input_global(self, is_dark)

    # ─────────────────────────────────────────────────────────────────
    # LOAD & SIMPAN DATA
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

    # ─────────────────────────────────────────────────────────────────
    # DOKUMEN & OPERASIONAL - GENERIC SETTINGS
    # ─────────────────────────────────────────────────────────────────

    def _load_numbering_branches(self):
        self.cmb_num_branch.blockSignals(True)
        try:
            self.cmb_num_branch.clear()
            rows = db_service.ambil_semua_data_cabang(limit=200) or []
            for row in rows:
                kode = str(row.get("kode_cabang") if isinstance(row, dict) else row[0]).strip().upper()
                nama = str(row.get("nama_cabang") if isinstance(row, dict) else row[1]).strip()
                if kode:
                    self.cmb_num_branch.addItem(f"{kode} — {nama}", kode)
        finally:
            self.cmb_num_branch.blockSignals(False)

    def _load_numbering_settings(self):
        self._load_numbering_branches()
        self.table_numbering.setRowCount(0)
        conn = self._wilayah_connection()
        try:
            rows = conn.execute("""
                SELECT kode_cabang, document_type, format_template, starting_count,
                       current_count, padding, aktif, sync_id
                FROM numbering_settings
                WHERE aktif = 1 AND document_type != 'BUKU_GUDANG'
                ORDER BY kode_cabang, document_type
            """).fetchall()
        finally:
            conn.close()
        for row in rows:
            self._insert_numbering_row(*row)
        self._reset_numbering_form()

    def _insert_numbering_row(self, kode_cabang, doc_type, fmt, start, current, padding, aktif=1,
                              sync_id=None):
        row = self.table_numbering.rowCount();
        self.table_numbering.insertRow(row)
        vals = [kode_cabang, doc_type, fmt, str(start), str(current), str(padding)]
        for col, val in enumerate(vals): self.table_numbering.setItem(row, col, QTableWidgetItem(str(val)))
        for col in range(6): self.table_numbering.item(row, col).setData(Qt.ItemDataRole.UserRole, sync_id or "")

    def _reset_numbering_form(self):
        self.txt_num_format.clear();
        self.sp_num_start.setValue(1);
        self.sp_num_current.setValue(0);
        self.sp_num_padding.setValue(5);
        self.btn_num_add.setText("+")
        if self.cmb_num_branch.count(): self.cmb_num_branch.setCurrentIndex(0)

    def _edit_numbering_row(self, item):
        row = item.row()
        self.cmb_num_branch.setCurrentIndex(
            max(0, self.cmb_num_branch.findData(self.table_numbering.item(row, 0).text())))
        idx = self.cmb_num_document.findText(self.table_numbering.item(row, 1).text(), Qt.MatchFlag.MatchFixedString)
        if idx >= 0: self.cmb_num_document.setCurrentIndex(idx)
        self.txt_num_format.setText(self.table_numbering.item(row, 2).text())
        self.sp_num_start.setValue(int(self.table_numbering.item(row, 3).text() or 0));
        self.sp_num_current.setValue(int(self.table_numbering.item(row, 4).text() or 0));
        self.sp_num_padding.setValue(int(self.table_numbering.item(row, 5).text() or 5))
        self.btn_num_add.setText("✓")

    def _save_numbering_from_form(self):
        if not self._boleh_edit_setting(): QMessageBox.warning(self, "Akses Ditolak",
                                                                     "Hanya SUPER yang dapat mengubah penomoran."); return
        branch = str(self.cmb_num_branch.currentData() or "").strip().upper();
        doc = self.cmb_num_document.currentText().strip().upper();
        fmt = self.txt_num_format.text().strip()
        if not branch or not fmt: QMessageBox.warning(self, "Data Belum Lengkap",
                                                      "Cabang dan format nomor wajib diisi."); return
        current = self.sp_num_current.value();
        start = self.sp_num_start.value()
        if current and current < start - 1: QMessageBox.warning(self, "Counter Tidak Valid",
                                                                "CURRENT tidak boleh lebih kecil dari START-1."); return
        conn = self._wilayah_connection()
        try:
            old = conn.execute("SELECT sync_id FROM numbering_settings WHERE kode_cabang=? AND document_type=?",
                               (branch, doc)).fetchone()
            sid = old[0] if old and old[0] else str(uuid.uuid4())
            conn.execute("""
                INSERT INTO numbering_settings(kode_cabang, document_type, format_template, starting_count, current_count, padding, reset_rule, aktif, sync_id, updated_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP, NULL)
                ON CONFLICT(kode_cabang, document_type) DO UPDATE SET
                    format_template=excluded.format_template, starting_count=excluded.starting_count, current_count=excluded.current_count,
                    padding=excluded.padding, reset_rule=excluded.reset_rule, aktif=1, sync_id=excluded.sync_id, updated_at=CURRENT_TIMESTAMP, deleted_at=NULL
            """, (branch, doc, fmt, start, current, self.sp_num_padding.value(), "NONE", sid))
            row = conn.execute(
                "SELECT kode_cabang,document_type,format_template,starting_count,current_count,padding,reset_rule,aktif,sync_id,created_at,updated_at,deleted_at FROM numbering_settings WHERE kode_cabang=? AND document_type=?",
                (branch, doc)).fetchone()
            payload = {"kode_cabang": row[0], "document_type": row[1], "format_template": row[2],
                       "starting_count": row[3], "current_count": row[4], "padding": row[5], "reset_rule": row[6],
                       "aktif": row[7], "sync_id": row[8], "created_at": row[9], "updated_at": row[10],
                       "deleted_at": row[11]}
            conn.execute(
                "INSERT INTO sync_outbox(table_name,record_key,operation,payload_json) VALUES ('numbering_settings',?,?,?)",
                (sid, "UPDATE" if old else "INSERT", json.dumps(payload, ensure_ascii=False)))
            conn.commit()
        except Exception:
            conn.rollback();
            raise
        finally:
            conn.close()
        self._load_numbering_settings()

    def _load_option_settings(self):
        self.table_options.setRowCount(0)
        conn = self._wilayah_connection()
        try:
            rows = conn.execute(
                "SELECT option_group, option_code, option_label, aktif, sync_id FROM master_option WHERE aktif=1 ORDER BY option_group, urutan, option_label").fetchall()
        finally:
            conn.close()
        labels = {"BUKU_STATUS_GUDANG": "Status Gudang", "BUKU_STATUS_TAGIHAN": "Status Tagihan",
                  "BUKU_METODE_PEMBAYARAN": "Metode Pembayaran", "ARMADA_JENIS_TRUK": "Jenis Truk",
                  "ARMADA_TUJUAN_KAPAL": "Tujuan Kapal"}
        for group, code, label, _aktif, sid in rows:
            row = self.table_options.rowCount();
            self.table_options.insertRow(row)
            vals = [labels.get(group, group), code, label, "-"]
            for c, val in enumerate(vals): self.table_options.setItem(row, c, QTableWidgetItem(str(val)))
            self.table_options.item(row, 1).setData(Qt.ItemDataRole.UserRole, group)
            self.table_options.item(row, 1).setData(Qt.ItemDataRole.UserRole + 1, sid)
            btn = QPushButton("-");
            btn.setFixedWidth(SETTING_ACCOUNT_ACTION_WIDTH)
            if self._boleh_edit_setting():
                btn.clicked.connect(lambda _, b=btn: self._delete_option_row(b))
            else:
                btn.setEnabled(False)
            self.table_options.setCellWidget(row, 3, btn)

    def _edit_option_row(self, item):
        row = item.row();
        group = str(self.table_options.item(row, 1).data(Qt.ItemDataRole.UserRole) or "")
        idx = self.cmb_option_group.findData(group);
        self.cmb_option_group.setCurrentIndex(max(0, idx));
        self.txt_option_code.setText(self.table_options.item(row, 1).text());
        self.txt_option_label.setText(self.table_options.item(row, 2).text());
        self.btn_option_add.setText("✓")

    def _save_option_from_form(self):
        if not self._boleh_edit_setting(): QMessageBox.warning(self, "Akses Ditolak",
                                                                     "Hanya SUPER yang dapat mengubah pengaturan operasional."); return
        group = str(self.cmb_option_group.currentData() or "").strip().upper();
        code = self.txt_option_code.text().strip().upper();
        label = self.txt_option_label.text().strip().upper()
        if not code or not label: QMessageBox.warning(self, "Data Belum Lengkap",
                                                      "Nilai dan nama tampilan wajib diisi."); return
        conn = self._wilayah_connection()
        try:
            old = conn.execute(
                "SELECT sync_id FROM master_option WHERE option_group=? AND option_code=? AND kode_cabang='*'",
                (group, code)).fetchone()
            sid = old[0] if old and old[0] else str(uuid.uuid4())
            conn.execute("""
                INSERT INTO master_option(option_group, option_code, option_label, kode_cabang, urutan, aktif, sync_id, updated_at, deleted_at)
                VALUES (?, ?, ?, '*', 999, 1, ?, CURRENT_TIMESTAMP, NULL)
                ON CONFLICT(kode_cabang, option_group, option_code) DO UPDATE SET option_label=excluded.option_label, aktif=1, sync_id=excluded.sync_id, updated_at=CURRENT_TIMESTAMP, deleted_at=NULL
            """, (group, code, label, sid))
            row = conn.execute(
                "SELECT option_group,option_code,option_label,kode_cabang,urutan,aktif,sync_id,created_at,updated_at,deleted_at FROM master_option WHERE option_group=? AND option_code=? AND kode_cabang='*'",
                (group, code)).fetchone()
            payload = {"option_group": row[0], "option_code": row[1], "option_label": row[2], "kode_cabang": row[3],
                       "urutan": row[4], "aktif": row[5], "sync_id": row[6], "created_at": row[7], "updated_at": row[8],
                       "deleted_at": row[9]}
            conn.execute(
                "INSERT INTO sync_outbox(table_name,record_key,operation,payload_json) VALUES ('master_option',?,?,?)",
                (sid, "UPDATE" if old else "INSERT", json.dumps(payload, ensure_ascii=False)))
            conn.commit()
        except Exception:
            conn.rollback();
            raise
        finally:
            conn.close()
        self._load_option_settings();
        self._reset_option_form()

    def _reset_option_form(self):
        self.txt_option_code.clear();
        self.txt_option_label.clear();
        self.btn_option_add.setText("+")

    def _delete_option_row(self, button):
        for row in range(self.table_options.rowCount()):
            if self.table_options.cellWidget(row, 3) is button:
                group = str(self.table_options.item(row, 1).data(Qt.ItemDataRole.UserRole) or "");
                code = self.table_options.item(row, 1).text().strip().upper()
                if QMessageBox.question(self, "Konfirmasi",
                                        f"Nonaktifkan '{code}'?") != QMessageBox.StandardButton.Yes: return
                conn = self._wilayah_connection()
                try:
                    conn.execute(
                        "UPDATE master_option SET aktif=0, updated_at=CURRENT_TIMESTAMP, deleted_at=CURRENT_TIMESTAMP WHERE option_group=? AND option_code=? AND kode_cabang='*'",
                        (group, code))
                    r = conn.execute(
                        "SELECT option_group,option_code,option_label,kode_cabang,urutan,aktif,sync_id,created_at,updated_at,deleted_at FROM master_option WHERE option_group=? AND option_code=? AND kode_cabang='*'",
                        (group, code)).fetchone()
                    if r:
                        payload = {"option_group": r[0], "option_code": r[1], "option_label": r[2], "kode_cabang": r[3],
                                   "urutan": r[4], "aktif": r[5], "sync_id": r[6], "created_at": r[7],
                                   "updated_at": r[8], "deleted_at": r[9]}
                        conn.execute(
                            "INSERT INTO sync_outbox(table_name,record_key,operation,payload_json) VALUES ('master_option',?,?,?)",
                            (r[6], "DELETE", json.dumps(payload, ensure_ascii=False)))
                    conn.commit()
                except Exception:
                    conn.rollback();
                    raise
                finally:
                    conn.close()
                self._load_option_settings();
                return

    def load_current_settings(self):
        try:
            settings = refresh_data_client()
        except Exception as exc:
            print(f"[TabSetting] Gagal refresh pengaturan: {exc}")
            settings = DATA_CLIENT

        self.txt_nama_perusahaan.setText(settings.get("nama_perusahaan", ""))
        self.txt_alamat_perusahaan.setText(settings.get("alamat_perusahaan", ""))
        self.txt_telp_perusahaan.setText(settings.get("telp_perusahaan", ""))
        self.txt_suffix_pajak.setText(settings.get("kode_akhiran_pajak", "-P"))
        self.txt_db_path.setText(CURRENT_SESSION.get("db_name", "database_cargo.db"))

        manual = str(settings.get("format_resi_manual", "0")).lower() in {
            "1", "true", "yes", "ya", "manual"
        }
        idx_manual = self.cmb_format_resi_manual.findData(manual)
        self.cmb_format_resi_manual.setCurrentIndex(max(idx_manual, 0))

        raw_logo = str(settings.get("logo_text_html", "KARGO EKSPEDISI"))
        self.txt_logo_aplikasi.setText(re.sub(r"<[^>]*>", "", raw_logo).strip())

        self.load_master_wilayah()
        self.load_cabang_wilayah()
        self._reset_form_wilayah()
        self._reset_form_cabang_wilayah()
        self._load_numbering_settings()
        self._load_option_settings()

        def load_rekening(table, values):
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
            try:
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
            finally:
                table.blockSignals(False)
                table.setUpdatesEnabled(True)

        load_rekening(self.table_np, settings.get("rekening_nonpajak", []))
        load_rekening(self.table_p, settings.get("rekening_pajak", []))

        self.table_cabang.setUpdatesEnabled(False)
        self.table_cabang.blockSignals(True)
        try:
            self.table_cabang.clearContents()
            rows = db_service.ambil_semua_data_cabang(limit=100) or []
            self.table_cabang.setRowCount(max(10, len(rows)))

            for row_index, row_data in enumerate(rows):
                if isinstance(row_data, dict):
                    kode = row_data.get("kode_cabang", "")
                    nama = row_data.get("nama_cabang", "")
                    prefix = row_data.get("resi_prefix", "")
                    start_seq = row_data.get("start_seq_json", '{"DEFAULT": 0}')
                    aturan_prefix = row_data.get(
                        "aturan_prefix", '{"DEFAULT": "INV"}'
                    )
                else:
                    values = list(row_data)
                    kode = values[0] if len(values) > 0 else ""
                    nama = values[1] if len(values) > 1 else ""
                    prefix = values[2] if len(values) > 2 else ""
                    start_seq = values[3] if len(values) > 3 and values[3] else '{"DEFAULT": 0}'
                    aturan_prefix = values[4] if len(values) > 4 and values[4] else '{"DEFAULT": "INV"}'

                item_kode = QTableWidgetItem(str(kode or "").strip().upper())
                item_kode.setData(
                    Qt.ItemDataRole.UserRole,
                    {
                        "start_seq_json": str(start_seq or '{"DEFAULT": 0}').strip(),
                        "aturan_prefix": str(aturan_prefix or '{"DEFAULT": "INV"}').strip(),
                    },
                )
                self.table_cabang.setItem(row_index, 0, item_kode)
                self.table_cabang.setItem(
                    row_index,
                    1,
                    QTableWidgetItem(str(nama or "").strip().upper()),
                )
                self.table_cabang.setItem(
                    row_index,
                    2,
                    QTableWidgetItem(str(prefix or "").strip().upper()),
                )
        except Exception as exc:
            self.table_cabang.setRowCount(10)
            print(f"[TabSetting] Gagal memuat data cabang: {exc}")
        finally:
            self.table_cabang.blockSignals(False)
            self.table_cabang.setUpdatesEnabled(True)

        self.load_user_branch_access()
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
        """Ambil tiga kolom yang terlihat dan pertahankan metadata DB lama."""
        branches = []
        kode_terpakai = set()
        default_start_seq = '{"DEFAULT": 0}'
        default_aturan = '{"DEFAULT": "INV"}'

        for row in range(self.table_cabang.rowCount()):
            item_kode = self.table_cabang.item(row, 0)
            kode = str(item_kode.text() if item_kode else "").strip().upper()
            if not kode:
                continue

            nama_item = self.table_cabang.item(row, 1)
            prefix_item = self.table_cabang.item(row, 2)
            nama = str(nama_item.text() if nama_item else "").strip().upper()
            prefix = str(prefix_item.text() if prefix_item else "").strip().upper()

            if not nama or not prefix:
                raise ValueError(
                    f"Nama dan prefix cabang baris {row + 1} wajib diisi."
                )
            if kode in kode_terpakai:
                raise ValueError(f"Kode cabang '{kode}' digunakan dua kali.")

            metadata = item_kode.data(Qt.ItemDataRole.UserRole)
            if not isinstance(metadata, dict):
                metadata = {}

            seq_text = str(metadata.get("start_seq_json") or default_start_seq).strip()
            route_text = str(metadata.get("aturan_prefix") or default_aturan).strip()
            try:
                seq_data = json.loads(seq_text)
                route_data = json.loads(route_text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Metadata cabang '{kode}' tidak valid sebagai JSON."
                ) from exc

            if not isinstance(seq_data, dict) or not isinstance(route_data, dict):
                raise ValueError(
                    f"Metadata cabang '{kode}' harus berupa object JSON."
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
        if not self._boleh_edit_setting():
            QMessageBox.warning(
                self, "Akses Ditolak",
                "Hanya SUPER yang dapat menyimpan pengaturan."
            )
            return

        nama = self.txt_nama_perusahaan.text().strip().upper()
        alamat = self.txt_alamat_perusahaan.text().strip().upper()
        telp = self.txt_telp_perusahaan.text().strip()
        logo = self.txt_logo_aplikasi.text().strip().upper()
        suffix = self.txt_suffix_pajak.text().strip().upper()

        wajib = {
            "Nama perusahaan": nama,
            "Alamat": alamat,
            "Telepon": telp,
            "Teks logo": logo,
        }
        kosong = [label for label, value in wajib.items() if not value]
        if kosong:
            QMessageBox.warning(
                self, "Data Belum Lengkap",
                "Kolom berikut wajib diisi:\n- " + "\n- ".join(kosong)
            )
            return

        try:
            wilayah_rows = self._ambil_wilayah_tabel()
            if not wilayah_rows:
                raise ValueError("Minimal harus tersedia satu wilayah.")

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
            ("kode_akhiran_pajak", suffix),
            (
                "format_resi_manual",
                "1" if self.cmb_format_resi_manual.currentData() else "0"
            ),
            ("provinsi_tujuan",
             json.dumps([row["nama_wilayah"] for row in wilayah_rows if int(row["aktif"])], ensure_ascii=False)),
            ("rekening_nonpajak", json.dumps(rekening_np, ensure_ascii=False)),
            ("rekening_pajak", json.dumps(rekening_p, ensure_ascii=False)),
        ]

        try:
            self._simpan_master_wilayah_local(wilayah_rows)

            sukses, pesan = db_service.simpan_semua_pengaturan_dan_cabang(
                settings_to_save, branches
            )
            if not sukses:
                QMessageBox.critical(
                    self, "Gagal Menyimpan",
                    str(pesan or "Service database menolak penyimpanan.")
                )
                return

            self._simpan_cabang_wilayah_local(
                self._ambil_cabang_wilayah_tabel()
            )
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