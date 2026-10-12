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
    QMenu,
    QLabel,
    QLineEdit,
    QInputDialog,
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
import services.numbering_service as numbering_service

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
            "Manajemen User",
            "Tampilan & Font",
        ]
        self.sidebar_list.addItems(menus)
        self.sidebar_list.setCurrentRow(0)

        sidebar_layout.addWidget(self.sidebar_list, 1)

        # ── INFO SESI LOGIN (selalu terlihat di bawah menu) ──
        self.session_info_box = QWidget()
        self.session_info_box.setObjectName("SessionInfoBox")
        self.session_info_box.setMinimumHeight(66)
        self.session_info_box.setMaximumHeight(82)
        session_info_layout = QVBoxLayout(self.session_info_box)
        session_info_layout.setContentsMargins(10, 8, 10, 8)
        session_info_layout.setSpacing(2)

        self.lbl_session_user = QLabel()
        self.lbl_session_user.setObjectName("SessionInfoUser")
        self.lbl_session_user.setWordWrap(True)
        self.lbl_session_user.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.lbl_session_branch = QLabel()
        self.lbl_session_branch.setObjectName("SessionInfoBranch")
        self.lbl_session_branch.setWordWrap(True)
        self.lbl_session_branch.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        session_info_layout.addWidget(self.lbl_session_user)
        session_info_layout.addWidget(self.lbl_session_branch)
        sidebar_layout.addWidget(self.session_info_box, 0)

        self.btn_logout = QPushButton("Logout")
        self.btn_logout.setObjectName("BtnLogoutText")
        self.btn_logout.setProperty("access_safe_action", True)
        self.btn_logout.setFlat(True)
        self.btn_logout.setAutoDefault(False)
        self.btn_logout.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.btn_logout.clicked.connect(self._logout_dari_aplikasi)
        sidebar_layout.addWidget(
            self.btn_logout,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

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
        self.page_user_access = QWidget()
        self.page_font = QWidget()

        self._build_page_general()
        self._build_page_document()
        self._build_page_bank()
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
        self.stacked_widget.addWidget(self.page_user_access)
        self.stacked_widget.addWidget(self.page_font)

        self.sidebar_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

        right_layout.addWidget(self.stacked_widget)

        # ── 3. TOMBOL SIMPAN GLOBAL (Selalu Terlihat di Bawah) ──
        self.btn_simpan_all = QPushButton("Simpan")
        self.btn_simpan_all.setFixedHeight(SETTING_SAVE_BUTTON_HEIGHT)
        self.btn_simpan_all.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.btn_simpan_all.clicked.connect(self.simpan_pengaturan)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        action_layout.addStretch(1)
        action_layout.addWidget(
            self.btn_simpan_all,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        )
        right_layout.addLayout(action_layout)

        root_layout.addWidget(right_container)

        self._setting_ui_ready = True
        self._refresh_session_info()
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

        form.addRow("Path database (.db):", self.txt_db_path)

        layout.addLayout(form)
        layout.addStretch()

    def _build_page_document(self):
        """Dokumen & Penomoran.

        Format/seri nomor Mahkota bersifat fixed. Tabel menjadi satu-satunya
        tempat konfigurasi counter: SUPER dapat mengubah NOMOR AWAL dan PADDING
        melalui klik kanan. TERAKHIR selalu read-only dan dikelola otomatis.
        """
        layout = QVBoxLayout(self.page_document)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl_title = QLabel("Dokumen & Penomoran")
        lbl_title.setProperty("is_page_title", True)
        layout.addWidget(lbl_title)

        lbl_numbering = QLabel("Penomoran Dokumen")
        lbl_numbering.setStyleSheet("font-weight: 700; margin-top: 2px;")
        layout.addWidget(lbl_numbering)

        self.table_numbering = QTableWidget(0, 6)
        self.table_numbering.setHorizontalHeaderLabels([
            "CABANG", "DOKUMEN", "SERI", "NOMOR AWAL", "TERAKHIR", "PADDING",
        ])
        self.table_numbering.setAlternatingRowColors(True)
        self.table_numbering.verticalHeader().setVisible(False)
        self.table_numbering.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table_numbering.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table_numbering.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table_numbering.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table_numbering.customContextMenuRequested.connect(
            self._show_numbering_context_menu
        )
        self.table_numbering.setMinimumHeight(190)
        self.table_numbering.setFixedHeight(320)

        hdr = self.table_numbering.horizontalHeader()
        for col, width in ((0, 90), (1, 105), (2, 100), (3, 105), (4, 95), (5, 80)):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table_numbering.setColumnWidth(col, width)
        layout.addWidget(self.table_numbering)

        hint = QLabel(
            "Klik kanan pada kolom untuk mengubah nilai."
        )
        hint.setProperty("setting_hint_italic", True)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # =============================================================
        # PENGATURAN TAMBAHAN - TETAP DIPERTAHANKAN
        # =============================================================
        lbl_tambahan = QLabel("Pengaturan Tambahan")
        lbl_tambahan.setStyleSheet("font-weight: bold; margin-top: 12px;")
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

    def _build_page_user_access(self):
        layout = QVBoxLayout(self.page_user_access)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("Manajemen User")
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
        central_full_homes = {"SBY"}
        return (
                role_bersih in CENTRAL_BRANCH_ROLES
                or home_bersih == "PUSAT"
                or home_bersih in central_full_homes
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
                    else:
                        item.setFlags(flags & ~Qt.ItemFlag.ItemIsUserCheckable)
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
        txt_username.setPlaceholderText("Contoh: sinta@mkt.log")
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

        form.addRow("Username / Email:", txt_username)
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
            "Akun online dikelola terpusat di Supabase. HOME selalu aktif. "
            "Role SUPER memakai akses AUTO ke seluruh cabang bisnis."
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
        sync_access()

        hasil_dialog = {}

        def validasi_dan_terima():
            """Validasi form sebelum dialog boleh ditutup."""
            username = txt_username.text().strip().upper()
            nama = txt_nama.text().strip()
            role = cmb_role.currentText().strip().upper()
            # UI memakai label SUPER; service memetakan ke role database SUPABASE SUPER.
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

    def _ambil_main_window(self):
        """Cari MainWindow tanpa bergantung pada kedalaman parent widget."""
        current = self
        while current is not None:
            parent = current.parentWidget() if hasattr(current, "parentWidget") else None
            if parent is None:
                break
            current = parent
            if current.__class__.__name__ == "MainWindow":
                return current
        return None

    def _refresh_session_info(self):
        """Tampilkan identitas user dan cabang yang sedang aktif."""
        nama = str(
            CURRENT_SESSION.get("nama_lengkap")
            or CURRENT_SESSION.get("username")
            or "-"
        ).strip()
        kode_cabang = str(CURRENT_SESSION.get("kode_cabang") or "").strip().upper()
        nama_cabang = str(
            CURRENT_SESSION.get("nama_cabang")
            or kode_cabang
            or "-"
        ).strip()
        # Tampilkan hanya nama cabang, tanpa label/kode tambahan.
        nama_cabang = nama_cabang.split("(", 1)[0].strip() or kode_cabang or "-"
        role = str(CURRENT_SESSION.get("role") or "ADMIN").strip().upper()

        self.lbl_session_user.setText(f"{nama}  •  {role}")
        self.lbl_session_branch.setText(nama_cabang)

    def _logout_dari_aplikasi(self):
        main_window = self._ambil_main_window()
        if main_window is None:
            QMessageBox.warning(
                self,
                "Logout",
                "Jendela utama aplikasi tidak ditemukan.",
            )
            return
        main_window.logout_session()

    def validasi_hak_akses_setting(self):
        role = str(CURRENT_SESSION.get("role", "ADMIN")).strip().upper()
        boleh_edit = role in {"SUPER", "SUPER_ADMIN"}
        boleh_lihat_user = role in {"SUPER", "SUPER_ADMIN", "OWNER", "ADMIN"}

        self.btn_simpan_all.setEnabled(boleh_edit)
        self.btn_simpan_all.setText(
            "SIMPAN"
            if boleh_edit
            else "PENGATURAN TERKUNCI"
        )
        if hasattr(self, "btn_logout"):
            self.btn_logout.setEnabled(True)

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

    def _wilayah_connection(self):
        conn = db_service.get_db_connection(
            CURRENT_SESSION.get("db_name", "database_cargo.db")
        )
        conn.execute("PRAGMA busy_timeout = 20000")
        return conn

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
        self._refresh_session_info()
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

        if hasattr(self, 'session_info_box'):
            # Info sesi ditampilkan sebagai teks biasa tanpa kotak/border.
            self.session_info_box.setStyleSheet("background: transparent; border: none;")
            self.lbl_session_user.setStyleSheet(
                "font-weight: 700; border: none; background: transparent;"
            )
            self.lbl_session_branch.setStyleSheet(
                "font-size: 11px; border: none; background: transparent;"
            )

        if hasattr(self, 'lbl_menu'):
            self.lbl_menu.setStyleSheet(s['lbl_menu'])

        groups = [
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
                getattr(self, "table_user_access", None),
                getattr(self, "table_numbering", None),
                getattr(self, "table_np", None),
                getattr(self, "table_p", None),
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
        # Tombol simpan memakai style default global PyQtDarkTheme.
        if hasattr(self, 'btn_logout'):
            # Logout sengaja tanpa border/background custom; hanya teks.
            self.btn_logout.setStyleSheet('border: none; background: transparent; padding: 0;')

        if hasattr(self, 'table_np'):
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
    # DOKUMEN & PENOMORAN - TABLE EDITOR
    # ─────────────────────────────────────────────────────────────────

    def _load_numbering_settings(self):
        """Muat seluruh counter aktif ke tabel; tidak ada form kedua."""
        conn = self._wilayah_connection()
        try:
            rows = conn.execute("""
                SELECT kode_cabang, document_type, series_code,
                       starting_count, current_count, padding, sync_id
                FROM numbering_counters
                WHERE aktif=1 AND deleted_at IS NULL
                ORDER BY kode_cabang, document_type, series_code
            """).fetchall()
        finally:
            conn.close()

        table = self.table_numbering
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(0)
            for row in rows:
                self._insert_numbering_row(*row)
        finally:
            table.setUpdatesEnabled(True)
            table.blockSignals(False)

        table.resizeRowsToContents()
        self.validasi_hak_akses_setting()

    def _insert_numbering_row(
            self, kode_cabang, doc_type, series, start, current, padding, sync_id=None
    ):
        row = self.table_numbering.rowCount()
        self.table_numbering.insertRow(row)
        values = [
            str(kode_cabang or "").strip().upper(),
            str(doc_type or "").strip().upper(),
            str(series or "").strip().upper(),
            str(int(start or 0)),
            str(int(current or 0)),
            str(max(1, int(padding or 1))),
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, sync_id or "")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_numbering.setItem(row, col, item)

        # Tandai kolom read-only secara semantik; seluruh tabel tetap non-editable
        # dan perubahan hanya lewat context menu.

    def _show_numbering_context_menu(self, pos):
        if not self._boleh_edit_setting():
            return

        index = self.table_numbering.indexAt(pos)
        if not index.isValid():
            return

        row = index.row()
        col = index.column()
        if col not in (3, 5):
            return

        item = self.table_numbering.item(row, col)
        if item is None:
            return

        menu = QMenu(self.table_numbering)
        action_edit = menu.addAction("Edit")
        action = menu.exec(self.table_numbering.viewport().mapToGlobal(pos))
        if action == action_edit:
            self._edit_numbering_cell(row, col)

    def _edit_numbering_cell(self, row: int, col: int):
        if not self._boleh_edit_setting():
            return

        branch_item = self.table_numbering.item(row, 0)
        doc_item = self.table_numbering.item(row, 1)
        series_item = self.table_numbering.item(row, 2)
        start_item = self.table_numbering.item(row, 3)
        current_item = self.table_numbering.item(row, 4)
        padding_item = self.table_numbering.item(row, 5)
        if not all((branch_item, doc_item, series_item, start_item, current_item, padding_item)):
            return

        branch = branch_item.text().strip().upper()
        doc = doc_item.text().strip().upper()
        series = series_item.text().strip().upper()
        old_start = int(start_item.text() or 0)
        current = int(current_item.text() or 0)
        old_padding = max(1, int(padding_item.text() or 1))

        if col == 3:
            value, ok = QInputDialog.getInt(
                self,
                "Edit Nomor Awal",
                f"Nomor awal {branch} / {doc} / {series}:",
                old_start,
                0,
                2_000_000_000,
                1,
            )
            if not ok or value == old_start:
                return

            next_number = max(value, current + 1)
            jawaban = QMessageBox.question(
                self,
                "Konfirmasi Nomor Awal",
                f"Nomor Awal akan diubah dari {old_start:,} menjadi {value:,}.\n\n"
                f"Nomor berikutnya yang dapat dipakai: {next_number:,}.\n"
                "Nomor yang sudah pernah digunakan tidak akan dipakai kembali.\n\n"
                "Lanjutkan?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if jawaban != QMessageBox.StandardButton.Yes:
                return

            new_start = value
            new_padding = old_padding
        else:
            value, ok = QInputDialog.getInt(
                self,
                "Edit Padding",
                f"Padding {branch} / {doc} / {series}:",
                old_padding,
                1,
                12,
                1,
            )
            if not ok or value == old_padding:
                return

            new_start = old_start
            new_padding = value

        try:
            numbering_service.update_counter_settings(
                branch,
                doc,
                series,
                starting_count=new_start,
                current_count=None,
                padding=new_padding,
                db_name=CURRENT_SESSION.get("db_name"),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Gagal Mengubah Penomoran",
                str(exc),
            )
            return

        self._load_numbering_settings()

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

        self._load_numbering_settings()

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
            rekening_np = self._ambil_rekening_tabel(
                self.table_np, "Rekening non-pajak"
            )
            rekening_p = self._ambil_rekening_tabel(
                self.table_p, "Rekening pajak"
            )
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
            ("rekening_nonpajak", json.dumps(rekening_np, ensure_ascii=False)),
            ("rekening_pajak", json.dumps(rekening_p, ensure_ascii=False)),
        ]

        try:
            # Simpan hanya pengaturan sistem. Data cabang dikelola oleh
            # bootstrap/seed dan bukan melalui halaman Settings.
            sukses, pesan = db_service.simpan_semua_pengaturan_dan_cabang(
                settings_to_save, []
            )
            if not sukses:
                QMessageBox.critical(
                    self, "Gagal Menyimpan",
                    str(pesan or "Service database menolak penyimpanan.")
                )
                return

            refresh_data_client()

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