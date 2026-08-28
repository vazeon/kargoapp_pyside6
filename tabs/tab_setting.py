# tabs/tab_setting.py
import json
import re
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QFontDatabase
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
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
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

from utils.typography import (
    get_master_font,
    perbarui_font_master,
)
from utils.widget_helpers import atur_tinggi_input
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
    SETTING_BRANCH_JSON_WIDTH,
    SETTING_BRANCH_PREFIX_WIDTH,
    SETTING_BRANCH_TABLE_HEIGHT,
    SETTING_CONTENT_MARGINS,
    SETTING_CONTENT_SPACING,
    SETTING_DESTINATION_LIST_HEIGHT,
    SETTING_FORM_HORIZONTAL_SPACING,
    SETTING_FORM_MARGINS,
    SETTING_FORM_VERTICAL_SPACING,
    SETTING_PREFIX_INVOICE_MAX_WIDTH,
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
        self.init_ui()
        self.load_current_settings()

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

        self.lbl_menu = QLabel("Preferences")
        sidebar_layout.addWidget(self.lbl_menu)

        self.sidebar_list = QListWidget()
        self.sidebar_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        menus = [
            "🏢  Identitas & Sistem",
            "📦  Format & Resi",
            "🏦  Rekening Bank",
            "📍  Kantor Cabang",
            "👤  Manajemen User",
            "🎨  Tampilan & Font",
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
        self.page_resi = QWidget()
        self.page_bank = QWidget()
        self.page_cabang = QWidget()
        self.page_user_access = QWidget()
        self.page_font = QWidget()

        self._build_page_general()
        self._build_page_resi()
        self._build_page_bank()
        self._build_page_cabang()
        self._build_page_user_access()
        self._build_page_font()

        atur_tinggi_input((
            self.txt_nama_perusahaan,
            self.txt_alamat_perusahaan,
            self.txt_telp_perusahaan,
            self.txt_logo_aplikasi,
            self.txt_db_path,
            self.txt_template_resi,
            self.txt_suffix_pajak,
            self.txt_prefix_invoice,
            self.cmb_format_resi_manual,
            self.txt_in_bank_np,
            self.txt_in_norek_np,
            self.txt_in_nama_np,
            self.txt_in_bank_p,
            self.txt_in_norek_p,
            self.txt_in_nama_p,
            self.combo_font,
        ))

        self.stacked_widget.addWidget(self.page_general)
        self.stacked_widget.addWidget(self.page_resi)
        self.stacked_widget.addWidget(self.page_bank)
        self.stacked_widget.addWidget(self.page_cabang)
        self.stacked_widget.addWidget(self.page_user_access)
        self.stacked_widget.addWidget(self.page_font)

        self.sidebar_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

        right_layout.addWidget(self.stacked_widget)

        # ── 3. TOMBOL SIMPAN GLOBAL (Selalu Terlihat di Bawah) ──
        self.btn_simpan_all = QPushButton("💾 SIMPAN PENGATURAN")
        self.btn_simpan_all.setFixedHeight(SETTING_SAVE_BUTTON_HEIGHT)
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
        self.txt_suffix_pajak.setMaximumWidth(SETTING_SUFFIX_MAX_WIDTH)
        self.txt_suffix_pajak.setPlaceholderText("Contoh: -P")

        self.txt_prefix_invoice = QLineEdit()
        self.txt_prefix_invoice.setMaximumWidth(SETTING_PREFIX_INVOICE_MAX_WIDTH)
        self.txt_prefix_invoice.setPlaceholderText("Contoh: INV")

        self.cmb_format_resi_manual = QComboBox()
        self.cmb_format_resi_manual.addItem("OTOMATIS", False)
        self.cmb_format_resi_manual.addItem("MANUAL", True)
        self.cmb_format_resi_manual.setMaximumWidth(SETTING_RESI_MODE_MAX_WIDTH)

        self.txt_provinsi_tujuan = QTextEdit()
        self.txt_provinsi_tujuan.setPlaceholderText(
            "Pisahkan dengan koma. Contoh: KALIMANTAN TIMUR, BALI"
        )
        atur_tinggi_input(self.txt_provinsi_tujuan, tinggi=SETTING_DESTINATION_LIST_HEIGHT)

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
        self.group_p = QGroupBox("Daftar Rekening Pajak (PT)")
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

        lbl_title = QLabel("Jaringan Kantor Cabang")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        self.group_branches = QGroupBox("Manajemen Data Cabang")
        vbox_branch = QVBoxLayout(self.group_branches)
        vbox_branch.setContentsMargins(*SETTING_BRANCH_GROUP_MARGINS)
        vbox_branch.setSpacing(SETTING_BRANCH_GROUP_SPACING)

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
        self.table_cabang.setFixedHeight(SETTING_BRANCH_TABLE_HEIGHT)
        self.table_cabang.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.table_cabang.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked,
        )

        hdr = self.table_cabang.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_cabang.setColumnWidth(0, SETTING_BRANCH_CODE_WIDTH)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table_cabang.setColumnWidth(2, SETTING_BRANCH_PREFIX_WIDTH)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table_cabang.setColumnWidth(3, SETTING_BRANCH_JSON_WIDTH)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table_cabang.setColumnWidth(4, SETTING_BRANCH_JSON_WIDTH)

        self._tbl_hint_label = QLabel(
            "💡 Double-click sel untuk mengedit. Kolom JSON harus berformat valid.",
        )

        vbox_branch.addWidget(self.table_cabang)
        vbox_branch.addWidget(self._tbl_hint_label)
        layout.addWidget(self.group_branches)
        layout.addStretch()

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
        self.btn_tambah_user = QPushButton("➕ TAMBAH USER")
        self.btn_edit_user = QPushButton("✏️ EDIT USER")
        self.btn_reset_password_user = QPushButton("🔑 RESET PASSWORD")
        self.btn_toggle_status_user = QPushButton("⛔ NONAKTIFKAN")
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
            "💡 SUPER_ADMIN dapat membuat/edit/reset/nonaktifkan user. OWNER hanya "
            "dapat melihat. HOME selalu aktif. Role pusat memakai akses AUTO ke "
            "seluruh cabang bisnis. User tidak dihapus agar histori tetap utuh."
        )
        self.lbl_user_access_hint.setWordWrap(True)
        self.lbl_user_access_hint.setProperty("setting_hint_italic", True)

        self.btn_simpan_akses_user = QPushButton("💾 SIMPAN AKSES CABANG")
        self.btn_simpan_akses_user.clicked.connect(self.simpan_akses_user)

        vbox.addLayout(action_bar)
        vbox.addWidget(self.table_user_access)
        vbox.addWidget(self.lbl_user_access_hint)
        vbox.addWidget(self.btn_simpan_akses_user)
        layout.addWidget(self.group_user_access)
        layout.addStretch()

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
        table.blockSignals(True)
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
            boleh_edit = role_session == "SUPER_ADMIN"

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
        boleh_edit = role_session == "SUPER_ADMIN"
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
            "✅ AKTIFKAN" if status == "NONAKTIF" else "⛔ NONAKTIFKAN"
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
        if str(CURRENT_SESSION.get("role", "ADMIN")).upper() != "SUPER_ADMIN":
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
        cmb_role.addItems(["ADMIN", "FINANCE", "ADMIN_PUSAT", "OWNER", "SUPER_ADMIN"])
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
            idx_role = cmb_role.findText(str(user.get("role") or "ADMIN").upper())
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
                cmb_role.setToolTip("Role akun SUPER_ADMIN yang sedang login dikunci.")
        sync_access()

        hasil_dialog = {}

        def validasi_dan_terima():
            """Validasi form sebelum dialog boleh ditutup."""
            username = txt_username.text().strip().upper()
            nama = txt_nama.text().strip()
            role = cmb_role.currentText().strip().upper()
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
                "role": role,
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
        if str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper() != "SUPER_ADMIN":
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
        if str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper() != "SUPER_ADMIN":
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
        if str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper() != "SUPER_ADMIN":
            return
        user = self._user_terpilih()
        if not user:
            QMessageBox.information(self, "Pilih User", "Pilih user terlebih dahulu.")
            return

        dialog = QDialog(self)
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
        if str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper() != "SUPER_ADMIN":
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
        boleh_edit = role == "SUPER_ADMIN"
        boleh_lihat_user = role in {"SUPER_ADMIN", "OWNER"}

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

        # OWNER boleh membaca daftar user, tetapi tidak dapat mengubah checkbox/akun.
        if hasattr(self, "table_user_access"):
            self.table_user_access.setEnabled(boleh_lihat_user)
        if hasattr(self, "btn_simpan_akses_user"):
            self.btn_simpan_akses_user.setEnabled(boleh_edit)
        if hasattr(self, "btn_tambah_user"):
            self._update_user_action_state()

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
            self.group_user_access,
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
        self.table_user_access.setStyleSheet(s.get('input', ''))
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