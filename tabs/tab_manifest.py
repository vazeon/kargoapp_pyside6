# tabs/tab_manifest.py
import re
from PySide6.QtCore import QDate, QSettings, QStringListModel, Qt
from PySide6.QtGui import QBrush, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION, DATA_CLIENT

from delegates.status_delegate import (
    attach_status_delegate,
    update_status_delegate_theme,
)

import services.database_service as db_service
from themes.modules.manifest import (
    get_manifest_history_date_appearance,
    get_manifest_row_highlight,
    get_manifest_styles,
)

from utils.printer.print_manifest import cetak_manifest_ke_printer
from utils.frozen_table_helper import FrozenTableWidget
from utils.typography import get_global_font_sizes
from utils import zoom as zoom_helper
from utils.number_formatters import (
    format_angka_indonesia,
    format_ke_rupiah,
)
from utils.table_helper import buat_tabel_item
from utils.widget_helpers import (
    paksa_kapital_lineedit,
    terapkan_popup_combobox_bawah,
)
from utils.date_ind_format import format_tanggal_ke_ui
from utils.placeholder_helper import terap_semua_placeholder_dinamis


def _get_manifest_delegate_colors(
        is_dark,
        status,
        is_alternate_row=False,
):
    """Adapter warna highlight Manifest untuk StatusColorDelegate global."""
    del is_alternate_row
    belong = str(status or "").strip().upper() == "BELONG"
    return get_manifest_row_highlight(is_dark, belong), None


class TabManifest(QWidget):
    KOL_CHECK = 0
    KOL_NO = 1
    KOL_RESI = 2
    KOL_TGL_MASUK = 3
    KOL_PENGIRIM = 4
    KOL_PENERIMA = 5
    KOL_TUJUAN = 6
    KOL_NAMA_BARANG = 7
    KOL_KOLI = 8
    KOL_BERAT = 9
    KOL_CBM = 10
    KOL_ONGKIR = 11
    KOL_KET = 12

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "TabManifest"
    SETTINGS_KEY_LEBAR_KOLOM = "lebar_kolom"

    DEFAULT_COLUMN_WIDTHS = (
        22,   # CHECK
        45,   # NO.
        125,  # RESI
        105,  # TGL MASUK
        150,  # PENGIRIM
        150,  # PENERIMA
        125,  # TUJUAN
        180,  # NAMA BARANG
        70,   # KOLI
        85,   # BERAT
        85,   # CBM
        110,  # ONGKIR
        180,  # KETERANGAN
    )

    NAMA_BULAN = {
        "01": "Januari",
        "02": "Februari",
        "03": "Maret",
        "04": "April",
        "05": "Mei",
        "06": "Juni",
        "07": "Juli",
        "08": "Agustus",
        "09": "September",
        "10": "Oktober",
        "11": "November",
        "12": "Desember",
    }

    def __init__(self):
        super().__init__()
        self.is_edit_mode = False
        self.edit_manifest_id = ""
        self._tanggal_edit_manifest = ""
        self._show_event_pertama = True
        self._sedang_menerapkan_zoom = False
        self._sedang_memuat_tabel = False
        self._sedang_memproses_manifest = False

        # Cache master Kapal untuk autocomplete, autofill, dan pencegahan duplikat.
        self._kapal_master_by_key = {}

        self.init_ui()

    def init_ui(self):
        layout_utama = QHBoxLayout(self)
        layout_utama.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)
        layout_utama.addWidget(self.splitter)

        self.panel_kiri = QWidget()
        # Batas lebar panel kiri agar tidak dapat digeser sampai hilang.
        self.panel_kiri.setMinimumWidth(700)
        self.panel_kiri.setMaximumWidth(1800)
        layout_kiri = QVBoxLayout(self.panel_kiri)
        layout_kiri.setContentsMargins(8, 8, 8, 8)
        layout_kiri.setSpacing(8)

        # Header dibungkus QWidget dengan tinggi tetap. Tanpa pembungkus ini,
        # QGridLayout dapat ikut menerima sisa tinggi panel dan mendorong kartu
        # input serta tabel menjauh.
        self.wadah_header_manifest = QWidget()
        self.wadah_header_manifest.setObjectName("wadahHeaderManifest")
        self.wadah_header_manifest.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.wadah_header_manifest.setFixedHeight(48)

        layout_header = QGridLayout(self.wadah_header_manifest)
        layout_header.setContentsMargins(0, 0, 0, 2)
        layout_header.setHorizontalSpacing(12)
        layout_header.setColumnStretch(0, 1)
        layout_header.setColumnStretch(1, 1)
        layout_header.setColumnStretch(2, 1)

        self.lbl_title = QLabel("📦 Pembuatan Manifest Pengiriman")
        layout_header.addWidget(
            self.lbl_title,
            0,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        wadah_tanggal = QWidget()
        layout_tanggal = QHBoxLayout(wadah_tanggal)
        layout_tanggal.setContentsMargins(0, 0, 0, 0)
        layout_tanggal.setSpacing(6)
        self.lbl_tanggal_manifest = QLabel("Tanggal Transaksi:")
        self.txt_tanggal_manifest = QLineEdit()
        self.txt_tanggal_manifest.setReadOnly(True)
        self.txt_tanggal_manifest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_tanggal_manifest.setFixedSize(180, 30)
        self.txt_tanggal_manifest.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout_tanggal.addWidget(self.lbl_tanggal_manifest)
        layout_tanggal.addWidget(self.txt_tanggal_manifest)
        layout_header.addWidget(
            wadah_tanggal,
            0,
            1,
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
        )

        wadah_nomor = QWidget()
        layout_nomor = QHBoxLayout(wadah_nomor)
        layout_nomor.setContentsMargins(0, 0, 0, 0)
        layout_nomor.setSpacing(8)
        self.lbl_no_manifest = QLabel("No. Manifest:")
        self.txt_no_manifest = QLineEdit()
        self.txt_no_manifest.setReadOnly(True)
        self.txt_no_manifest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_no_manifest.setFixedSize(200, 36)
        self.txt_no_manifest.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout_nomor.addWidget(self.lbl_no_manifest)
        layout_nomor.addWidget(self.txt_no_manifest)
        layout_header.addWidget(
            wadah_nomor,
            0,
            2,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        layout_kiri.addWidget(self.wadah_header_manifest, 0)
        self.perbarui_tanggal_header()

        # Area input detail dibuat seperti kartu input pada Tab Resi.
        # Panel kiri berisi informasi rute, panel kanan berisi armada,
        # sedangkan tombol aksi tetap berdiri sendiri di sisi kanan.
        # Bungkus area detail dalam QWidget dengan tinggi tetap agar QVBoxLayout
        # tidak membagikan ruang kosong vertikal ke area kartu.
        self.wadah_detail_manifest = QWidget()
        self.wadah_detail_manifest.setObjectName("wadahDetailManifest")
        self.wadah_detail_manifest.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.wadah_detail_manifest.setFixedHeight(172)

        layout_detail = QHBoxLayout(self.wadah_detail_manifest)
        layout_detail.setContentsMargins(0, 0, 0, 0)
        layout_detail.setSpacing(14)

        self.card_rute_manifest = QFrame()
        self.card_rute_manifest.setObjectName("cardRuteManifest")
        self.card_rute_manifest.setFixedHeight(164)
        self.card_rute_manifest.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        grid_rute = QGridLayout(self.card_rute_manifest)
        grid_rute.setContentsMargins(26, 18, 26, 18)
        grid_rute.setHorizontalSpacing(14)
        grid_rute.setVerticalSpacing(12)
        grid_rute.setColumnStretch(0, 0)
        grid_rute.setColumnStretch(1, 1)

        self.lbl_input_tujuan = QLabel("Tujuan:")
        self.lbl_input_kapal = QLabel("Kapal:")
        self.lbl_input_note = QLabel("Note:")
        self.lbl_input_tujuan.setMinimumWidth(70)
        self.lbl_input_kapal.setMinimumWidth(70)
        self.lbl_input_note.setMinimumWidth(70)

        self.cb_filter_wilayah = QComboBox()
        self.cb_filter_wilayah.addItems(
            DATA_CLIENT.get(
                'provinsi_tujuan',
                ["PROVINSI A", "PROVINSI B", "PROVINSI C"],
            )
        )
        self.cb_filter_wilayah.setMinimumWidth(230)
        self.cb_filter_wilayah.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.cb_filter_wilayah.currentTextChanged.connect(
            self.on_wilayah_changed
        )

        # Nama Kapal bersifat opsional. Hanya nama yang disimpan ke Manifest.
        self.txt_nama_kapal = QLineEdit()
        self.txt_nama_kapal.setPlaceholderText("Nama Kapal (Opsional)")
        self.txt_nama_kapal.setMinimumWidth(230)
        self.txt_nama_kapal.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.txt_nama_kapal.textChanged.connect(
            lambda: paksa_kapital_lineedit(self.txt_nama_kapal)
        )
        self.txt_nama_kapal.editingFinished.connect(
            self.autofill_kapal_dari_input
        )

        self.txt_note_manifest = QLineEdit()
        self.txt_note_manifest.setPlaceholderText("Note (Wajib jika tanpa detail truk)")
        self.txt_note_manifest.setMinimumWidth(230)
        self.txt_note_manifest.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.txt_note_manifest.textChanged.connect(
            lambda: paksa_kapital_lineedit(self.txt_note_manifest)
        )

        grid_rute.addWidget(
            self.lbl_input_tujuan,
            0,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        grid_rute.addWidget(self.cb_filter_wilayah, 0, 1)
        grid_rute.addWidget(
            self.lbl_input_kapal,
            1,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        grid_rute.addWidget(self.txt_nama_kapal, 1, 1)
        grid_rute.addWidget(
            self.lbl_input_note,
            2,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        grid_rute.addWidget(self.txt_note_manifest, 2, 1)

        self.card_armada_manifest = QFrame()
        self.card_armada_manifest.setObjectName("cardArmadaManifest")
        self.card_armada_manifest.setFixedHeight(164)
        self.card_armada_manifest.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        grid_armada = QGridLayout(self.card_armada_manifest)
        grid_armada.setContentsMargins(26, 18, 26, 18)
        grid_armada.setHorizontalSpacing(14)
        grid_armada.setVerticalSpacing(10)
        grid_armada.setColumnStretch(0, 0)
        grid_armada.setColumnStretch(1, 1)

        self.lbl_input_truk = QLabel("Truk:")
        self.lbl_input_sopir = QLabel("Sopir:")
        self.lbl_input_keterangan = QLabel("Ket:")
        for label_input in (
                self.lbl_input_truk,
                self.lbl_input_sopir,
                self.lbl_input_keterangan,
        ):
            label_input.setMinimumWidth(70)

        # ComboBox Jenis Truk dengan placeholder.
        self.cb_jenis_truk = QComboBox()
        self.cb_jenis_truk.addItem("- Pilih jenis -")
        self.cb_jenis_truk.addItems(
            ["TB", "Tronton", "CDD", "Pick-up", "Lainnya..."]
        )
        self.cb_jenis_truk.setMinimumWidth(150)
        self.cb_jenis_truk.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        def ubah_font_placeholder(idx):
            font_utama = self.cb_jenis_truk.font()
            font_utama.setItalic(idx == 0)
            self.cb_jenis_truk.setFont(font_utama)

            font_italic = QFont(font_utama)
            font_italic.setItalic(True)
            self.cb_jenis_truk.setItemData(
                0,
                font_italic,
                Qt.ItemDataRole.FontRole,
            )

            font_normal = QFont(font_utama)
            font_normal.setItalic(False)
            for i in range(1, self.cb_jenis_truk.count()):
                self.cb_jenis_truk.setItemData(
                    i,
                    font_normal,
                    Qt.ItemDataRole.FontRole,
                )

        self.cb_jenis_truk.currentIndexChanged.connect(
            ubah_font_placeholder
        )
        self.cb_jenis_truk.currentIndexChanged.connect(
            self.on_jenis_truk_manifest_changed
        )
        ubah_font_placeholder(0)

        self.txt_jenis_truk_lain = QLineEdit()
        self.txt_jenis_truk_lain.setPlaceholderText("Jenis lainnya")
        self.txt_jenis_truk_lain.setMinimumWidth(130)
        self.txt_jenis_truk_lain.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.txt_jenis_truk_lain.textChanged.connect(
            lambda: paksa_kapital_lineedit(self.txt_jenis_truk_lain)
        )
        self.txt_jenis_truk_lain.hide()

        self.txt_no_pol = QLineEdit()
        self.txt_no_pol.setPlaceholderText("No. Pol")
        self.txt_no_pol.setMinimumWidth(130)
        self.txt_no_pol.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.txt_no_pol.textChanged.connect(
            lambda: paksa_kapital_lineedit(self.txt_no_pol)
        )

        wadah_truk = QWidget()
        layout_truk = QHBoxLayout(wadah_truk)
        layout_truk.setContentsMargins(0, 0, 0, 0)
        layout_truk.setSpacing(8)
        layout_truk.addWidget(self.cb_jenis_truk, 5)
        layout_truk.addWidget(self.txt_jenis_truk_lain, 4)
        layout_truk.addWidget(self.txt_no_pol, 4)

        self.txt_sopir = QLineEdit()
        self.txt_sopir.setPlaceholderText("Nama Sopir")
        self.txt_sopir.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.txt_sopir.textChanged.connect(
            lambda: paksa_kapital_lineedit(self.txt_sopir)
        )

        self.txt_keterangan = QLineEdit()
        self.txt_keterangan.setPlaceholderText("Keterangan")
        self.txt_keterangan.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.txt_keterangan.textChanged.connect(
            lambda: paksa_kapital_lineedit(self.txt_keterangan)
        )

        grid_armada.addWidget(
            self.lbl_input_truk,
            0,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        grid_armada.addWidget(wadah_truk, 0, 1)
        grid_armada.addWidget(
            self.lbl_input_sopir,
            1,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        grid_armada.addWidget(self.txt_sopir, 1, 1)
        grid_armada.addWidget(
            self.lbl_input_keterangan,
            2,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        grid_armada.addWidget(self.txt_keterangan, 2, 1)

        wadah_tombol_manifest = QWidget()
        wadah_tombol_manifest.setFixedSize(210, 132)
        wadah_tombol_manifest.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        layout_tombol_manifest = QVBoxLayout(wadah_tombol_manifest)
        layout_tombol_manifest.setContentsMargins(4, 0, 0, 0)
        layout_tombol_manifest.setSpacing(8)
        layout_tombol_manifest.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.btn_proses = QPushButton("⚡ BUAT MANIFEST")
        self.btn_proses.setMinimumWidth(190)
        self.btn_proses.setMinimumHeight(38)
        layout_tombol_manifest.addWidget(
            self.btn_proses,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        self.btn_batal_edit = QPushButton("❌ BATAL")
        self.btn_batal_edit.setMinimumWidth(190)
        self.btn_batal_edit.clicked.connect(self.batal_edit)
        self.btn_batal_edit.hide()
        layout_tombol_manifest.addWidget(
            self.btn_batal_edit,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        layout_detail.addWidget(self.card_rute_manifest, 5)
        layout_detail.addWidget(self.card_armada_manifest, 6)
        layout_detail.addWidget(
            wadah_tombol_manifest,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        layout_kiri.addWidget(
            self.wadah_detail_manifest,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        self.tabel_manifest = FrozenTableWidget(
            frozen_cols=3,
            fixed_cols=[0],
            fixed_widths={0: 22}
        )

        self.tabel_manifest.setColumnCount(13)
        self.tabel_manifest.setHorizontalHeaderLabels(
            [
                "✔",
                "NO.",
                "RESI",
                "TGL MASUK",
                "PENGIRIM",
                "PENERIMA",
                "TUJUAN",
                "NAMA BARANG",
                "KOLI",
                "BERAT (kg)",
                "KUBIK (m3)",
                "ONGKIR (Rp)",
                "KETERANGAN",
            ])
        self.tabel_manifest.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.tabel_manifest.verticalHeader().setVisible(False)
        self.tabel_manifest.setAlternatingRowColors(True)

        win = self.window()
        is_dark = (
            win.current_theme == "dark"
            if win and hasattr(win, "current_theme")
            else False
        )
        attach_status_delegate(
            self.tabel_manifest,
            status_column=self.KOL_CHECK,
            status_role=Qt.ItemDataRole.UserRole,
            color_provider=_get_manifest_delegate_colors,
            is_dark=is_dark,
        )

        if hasattr(self.tabel_manifest, "frozen_table"):
            attach_status_delegate(
                self.tabel_manifest.frozen_table,
                status_column=self.KOL_CHECK,
                status_role=Qt.ItemDataRole.UserRole,
                color_provider=_get_manifest_delegate_colors,
                is_dark=is_dark,
            )

        self.load_lebar_kolom(self.tabel_manifest)
        self.tabel_manifest.horizontalHeader().sectionResized.connect(
            lambda: self.simpan_lebar_kolom(self.tabel_manifest))
        # Hanya tabel yang boleh mengambil sisa tinggi panel. Header dan kartu
        # selalu menempel di atas tanpa ruang kosong tambahan.
        self.tabel_manifest.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout_kiri.addWidget(self.tabel_manifest, 1)
        layout_kiri.setStretch(0, 0)
        layout_kiri.setStretch(1, 0)
        layout_kiri.setStretch(2, 1)

        self.panel_kanan = QWidget()
        # Batas lebar panel kanan agar tidak dapat digeser sampai hilang.
        self.panel_kanan.setMinimumWidth(260)
        self.panel_kanan.setMaximumWidth(520)
        layout_kanan = QVBoxLayout(self.panel_kanan)
        layout_kanan.addWidget(QLabel("🕒 Histori Manifest:"))

        hbox_filter = QHBoxLayout()
        hbox_filter.addWidget(QLabel("Tahun:"))
        self.cb_tahun_filter = QComboBox()
        self.cb_tahun_filter.setFixedWidth(80)
        self.cb_tahun_filter.currentTextChanged.connect(self.load_histori)
        hbox_filter.addWidget(self.cb_tahun_filter)

        self.txt_cari_histori = QLineEdit()
        self.txt_cari_histori.setPlaceholderText("Cari manifest...")
        self.txt_cari_histori.textChanged.connect(
            lambda: paksa_kapital_lineedit(self.txt_cari_histori),
        )
        self.txt_cari_histori.textChanged.connect(self.filter_histori)
        hbox_filter.addWidget(self.txt_cari_histori)
        layout_kanan.addLayout(hbox_filter)

        self.list_histori = QTreeWidget()
        self.list_histori.setColumnCount(2)
        self.list_histori.setHeaderHidden(True)
        self.list_histori.header().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.list_histori.header().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.list_histori.itemDoubleClicked.connect(self.preview_histori_manifest)
        self.list_histori.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_histori.customContextMenuRequested.connect(
            self.buka_menu_klik_kanan_histori,
        )
        layout_kanan.addWidget(self.list_histori)

        self.splitter.addWidget(self.panel_kiri)
        self.splitter.addWidget(self.panel_kanan)
        # Cegah kedua panel diciutkan menjadi 0 piksel.
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([800, 200])

        self.btn_proses.clicked.connect(self.update_truk_ke_manifest)
        self.refresh_tahun_filter()
        self.load_data_resi_gudang()
        self.generate_no_manifest()
        self.sesuaikan_tema_lokal()
        self.setup_autocomplete_truk()
        terapkan_popup_combobox_bawah(self)

    def refresh_session_ui(self, refresh_autocomplete=True):
        """Menyegarkan data tab tanpa menghapus draft atau mode edit aktif."""
        self.perbarui_tanggal_header()

        if refresh_autocomplete:
            self.setup_autocomplete_truk()

        self.load_data_resi_gudang()
        self.generate_no_manifest()
        self.filter_histori(self.txt_cari_histori.text())

    def on_jenis_truk_manifest_changed(self, _index=None):
        """Menampilkan kolom jenis lainnya hanya saat diperlukan."""
        pilih_lainnya = self.cb_jenis_truk.currentText().strip() == "Lainnya..."
        self.txt_jenis_truk_lain.setVisible(pilih_lainnya)
        if not pilih_lainnya:
            self.txt_jenis_truk_lain.clear()

    def ambil_jenis_truk_manifest(self):
        """Menghasilkan jenis truk baku untuk payload Manifest."""
        pilihan = self.cb_jenis_truk.currentText().strip()
        if pilihan == "Lainnya...":
            return self.txt_jenis_truk_lain.text().strip().upper()
        if self.cb_jenis_truk.currentIndex() <= 0:
            return ""
        return pilihan

    def set_jenis_truk_manifest(self, jenis):
        """Memilih jenis umum atau mengisi kolom Lainnya untuk jenis khusus."""
        jenis_bersih = str(jenis or "").strip()
        if not jenis_bersih:
            self.cb_jenis_truk.setCurrentIndex(0)
            return

        for index in range(1, self.cb_jenis_truk.count()):
            item_text = self.cb_jenis_truk.itemText(index)
            if item_text == "Lainnya...":
                continue
            if item_text.casefold() == jenis_bersih.casefold():
                self.cb_jenis_truk.setCurrentIndex(index)
                return

        idx_lainnya = self.cb_jenis_truk.findText(
            "Lainnya...",
            Qt.MatchFlag.MatchFixedString,
        )
        self.cb_jenis_truk.setCurrentIndex(idx_lainnya)
        self.txt_jenis_truk_lain.setText(jenis_bersih.upper())

    def setup_autocomplete_truk(self):
        try:
            rows = db_service.ambil_truk_list() or []
            sopirs = sorted(
                {
                    str(row[1]).strip().upper()
                    for row in rows
                    if len(row) > 1 and row[1]
                },
            )

            completer_lama = getattr(self, 'completer_sopir', None)
            if completer_lama is not None:
                try:
                    completer_lama.activated.disconnect(self.on_sopir_selected)
                except (TypeError, RuntimeError):
                    pass
                completer_lama.deleteLater()

            self.completer_sopir = QCompleter(sopirs, self)
            self.completer_sopir.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self.txt_sopir.setCompleter(self.completer_sopir)
            self.completer_sopir.activated.connect(self.on_sopir_selected)

            self.txt_no_pol.setCompleter(None)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Warning Database",
                f"Gagal memuat autocomplete truk: {e}",
            )
        finally:
            # Saat Tab Manifest dibuka, refresh Truk sekaligus menyegarkan
            # daftar nama Kapal dari Subtab Kapal.
            self.setup_autocomplete_kapal()

    @staticmethod
    def _normalisasi_kunci_kapal(nama):
        """Menyamakan huruf, spasi, titik, dan tanda baca untuk cek duplikat."""
        return re.sub(
            r"[^A-Z0-9]+",
            "",
            str(nama or "").strip().upper(),
        )

    def setup_autocomplete_kapal(self):
        """Memuat master Kapal untuk autocomplete dan autofill Manifest."""
        try:
            rows = db_service.ambil_semua_kapal_full() or []
            master_by_key = {}

            for row in rows:
                if not row:
                    continue

                nama = str(row[0] or "").strip().upper()
                if not nama:
                    continue

                tujuan = str(row[1] or "").strip().upper() if len(row) > 1 else ""
                keterangan = str(row[2] or "").strip().upper() if len(row) > 2 else ""
                foto = str(row[3] or "").strip() if len(row) > 3 else ""

                key = self._normalisasi_kunci_kapal(nama)
                if key and key not in master_by_key:
                    master_by_key[key] = {
                        "nama": nama,
                        "tujuan": tujuan,
                        "keterangan": keterangan,
                        "foto": foto,
                    }

            self._kapal_master_by_key = master_by_key
            daftar_nama = sorted(
                item["nama"]
                for item in master_by_key.values()
            )

            if not hasattr(self, "model_autocomplete_kapal"):
                self.model_autocomplete_kapal = QStringListModel(self)
                self.completer_kapal = QCompleter(
                    self.model_autocomplete_kapal,
                    self,
                )
                self.completer_kapal.setCaseSensitivity(
                    Qt.CaseSensitivity.CaseInsensitive
                )
                self.completer_kapal.setFilterMode(
                    Qt.MatchFlag.MatchContains
                )
                self.completer_kapal.setCompletionMode(
                    QCompleter.CompletionMode.PopupCompletion
                )
                self.completer_kapal.activated[str].connect(
                    self.on_kapal_selected
                )
                self.txt_nama_kapal.setCompleter(
                    self.completer_kapal
                )

            self.model_autocomplete_kapal.setStringList(
                daftar_nama
            )

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Warning Database",
                f"Gagal memuat autocomplete kapal: {exc}",
            )

    def _cari_master_kapal(self, nama):
        key = self._normalisasi_kunci_kapal(nama)
        if not key:
            return None
        return self._kapal_master_by_key.get(key)

    def on_kapal_selected(self, nama):
        """Mengisi nama resmi dan tujuan Manifest dari master Kapal."""
        data = self._cari_master_kapal(nama)
        if not data:
            return

        nama_resmi = data["nama"]
        if self.txt_nama_kapal.text().strip().upper() != nama_resmi:
            self.txt_nama_kapal.setText(nama_resmi)

        tujuan = data.get("tujuan", "")
        if tujuan:
            index_tujuan = self.cb_filter_wilayah.findText(
                tujuan,
                Qt.MatchFlag.MatchFixedString,
            )
            if index_tujuan >= 0:
                self.cb_filter_wilayah.setCurrentIndex(
                    index_tujuan
                )

        detail_tooltip = []
        if tujuan:
            detail_tooltip.append(f"Tujuan: {tujuan}")
        if data.get("keterangan"):
            detail_tooltip.append(
                f"Keterangan: {data['keterangan']}"
            )
        self.txt_nama_kapal.setToolTip(
            "\n".join(detail_tooltip)
        )

    def autofill_kapal_dari_input(self):
        """Menangkap nama yang diketik manual tetapi sebenarnya sudah terdaftar."""
        nama = self.txt_nama_kapal.text().strip()
        if not nama:
            self.txt_nama_kapal.setToolTip("")
            return

        data = self._cari_master_kapal(nama)
        if data:
            self.on_kapal_selected(data["nama"])

    def _refresh_subtab_kapal(self):
        """Menyegarkan Subtab Kapal bila widget-nya sudah dibuat."""
        window = self.window()
        if not window:
            return

        for widget in window.findChildren(QWidget):
            if widget.__class__.__name__ != "SubTabKapal":
                continue

            refresh = getattr(widget, "refresh_tabel", None)
            if callable(refresh):
                try:
                    refresh()
                except RuntimeError:
                    pass
            break

    def pastikan_kapal_terdaftar(self, nama_kapal):
        """
        Memastikan Nama Kapal Manifest tersedia di master Kapal.

        Kapal lama dipakai ulang berdasarkan nama yang dinormalisasi.
        Kapal baru dibuat satu kali dengan tujuan Manifest aktif.
        """
        nama_kapal = str(nama_kapal or "").strip().upper()
        if not nama_kapal:
            return True, ""

        # Baca ulang agar cache selalu mencerminkan perubahan dari Subtab Kapal.
        self.setup_autocomplete_kapal()

        data_lama = self._cari_master_kapal(nama_kapal)
        if data_lama:
            self.on_kapal_selected(data_lama["nama"])
            return True, data_lama["nama"]

        tujuan = self.cb_filter_wilayah.currentText().strip().upper()
        sukses, pesan = db_service.simpan_atau_update_kapal_full(
            nama_kapal,
            tujuan,
            "",
            "",
            mode="TAMBAH",
        )

        if not sukses:
            # Antisipasi data dibuat oleh proses lain setelah cache dibaca.
            self.setup_autocomplete_kapal()
            data_lama = self._cari_master_kapal(nama_kapal)
            if data_lama:
                self.on_kapal_selected(data_lama["nama"])
                return True, data_lama["nama"]

            return False, str(pesan or "Gagal menyimpan master Kapal.")

        self.setup_autocomplete_kapal()
        data_baru = self._cari_master_kapal(nama_kapal)
        nama_resmi = (
            data_baru["nama"]
            if data_baru
            else nama_kapal
        )

        self.txt_nama_kapal.setText(nama_resmi)
        self._refresh_subtab_kapal()
        return True, nama_resmi

    def on_sopir_selected(self, sopir):
        row = db_service.ambil_detail_truk_by_sopir(sopir)
        if row:
            no_polisi = row[0] if len(row) > 0 else ""
            jenis_truk = row[1] if len(row) > 1 else ""
            ket_truk = row[2] if len(row) > 2 else ""

            if no_polisi:
                self.txt_no_pol.setText(str(no_polisi))

            if jenis_truk:
                self.set_jenis_truk_manifest(jenis_truk)

            if ket_truk and str(ket_truk).strip() not in ('', '-'):
                self.txt_keterangan.setText(str(ket_truk))

    @staticmethod
    def _format_tanggal_header(tanggal):
        """Format tanggal header dalam bahasa Indonesia."""
        nama_hari = {
            1: "Senin",
            2: "Selasa",
            3: "Rabu",
            4: "Kamis",
            5: "Jumat",
            6: "Sabtu",
            7: "Minggu",
        }
        return (
            f"{nama_hari.get(tanggal.dayOfWeek(), '')}, "
            f"{tanggal.toString('dd/MM/yyyy')}"
        )

    def perbarui_tanggal_header(self):
        """Menampilkan tanggal transaksi hari ini pada header Manifest."""
        if hasattr(self, "txt_tanggal_manifest"):
            self.txt_tanggal_manifest.setText(
                self._format_tanggal_header(QDate.currentDate())
            )

    def generate_no_manifest(self):
        if self.is_edit_mode:
            self.txt_no_manifest.setText(self.edit_manifest_id)
            return

        aturan_prefix = CURRENT_SESSION.get("aturan_prefix", {}) or {}
        wilayah = self.cb_filter_wilayah.currentText()
        prefix = f"M-{aturan_prefix.get(wilayah, 'MF')}"
        seq = 1

        try:
            rows = db_service.ambil_no_manifest_list_by_prefix(
                prefix,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
            ) or []

            nomor_urut = []
            for row in rows:
                no_manifest = str(row[0] if row else "").strip()
                match = re.search(r"-(\d+)$", no_manifest)
                if match:
                    nomor_urut.append(int(match.group(1)))

            if nomor_urut:
                seq = max(nomor_urut) + 1

        except Exception as exc:
            print(f"[Manifest] Gagal menghasilkan nomor manifest: {exc}")

        self.txt_no_manifest.setText(f"{prefix}-{seq:04d}")

    def refresh_tahun_filter(self):
        pilihan_sebelumnya = self.cb_tahun_filter.currentText().strip()
        tahun_sekarang = str(QDate.currentDate().year())
        self.cb_tahun_filter.blockSignals(True)

        try:
            rows = db_service.ambil_daftar_tahun_manifest(
                CURRENT_SESSION.get("kode_cabang", "PUSAT")
            ) or []
            daftar_tahun = {
                str(row[0]).strip()
                for row in rows
                if row and str(row[0] or "").strip().isdigit()
            }
            daftar_tahun.add(tahun_sekarang)

            self.cb_tahun_filter.clear()
            self.cb_tahun_filter.addItem("Semua")
            self.cb_tahun_filter.addItems(
                sorted(daftar_tahun, reverse=True)
            )

            target = pilihan_sebelumnya or tahun_sekarang
            index_target = self.cb_tahun_filter.findText(
                target,
                Qt.MatchFlag.MatchFixedString,
            )
            self.cb_tahun_filter.setCurrentIndex(
                index_target if index_target >= 0 else 0
            )

        except Exception as exc:
            print(f"[Manifest] Gagal memuat daftar tahun: {exc}")
            self.cb_tahun_filter.clear()
            self.cb_tahun_filter.addItems(["Semua", tahun_sekarang])
            self.cb_tahun_filter.setCurrentIndex(1)

        finally:
            self.cb_tahun_filter.blockSignals(False)

    def load_data_resi_gudang(self):
        if self._sedang_memuat_tabel:
            return

        self._sedang_memuat_tabel = True

        if not hasattr(self.tabel_manifest, "_zoom_base_column_widths"):
            self.tabel_manifest._zoom_base_column_widths = {
                index: self.tabel_manifest.columnWidth(index)
                for index in range(self.tabel_manifest.columnCount())
            }

        self.tabel_manifest.blockSignals(True)
        self.tabel_manifest.setUpdatesEnabled(False)
        self.tabel_manifest.setRowCount(0)

        win = self.window()
        is_dark = bool(
            win
            and hasattr(win, "current_theme")
            and win.current_theme == "dark"
        )

        try:
            rows = db_service.ambil_resi_untuk_manifest(
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                self.cb_filter_wilayah.currentText(),
                self.is_edit_mode,
                self.edit_manifest_id,
            ) or []

            for row in rows:
                row = tuple(row or ())
                pos = self.tabel_manifest.rowCount()
                self.tabel_manifest.insertRow(pos)

                manifest_row = (
                    str(row[9] or "").strip()
                    if len(row) > 9
                    else ""
                )
                belong = bool(
                    self.is_edit_mode
                    and manifest_row == self.edit_manifest_id
                )

                chk = QTableWidgetItem()
                chk.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                chk.setCheckState(
                    Qt.CheckState.Checked
                    if belong
                    else Qt.CheckState.Unchecked
                )
                chk.setData(
                    Qt.ItemDataRole.UserRole,
                    "BELONG" if belong else "",
                )
                self.tabel_manifest.setItem(pos, self.KOL_CHECK, chk)

                item_no = buat_tabel_item(
                    text=str(pos + 1),
                    editable=False,
                    alignment=Qt.AlignmentFlag.AlignCenter,
                )
                self.tabel_manifest.setItem(pos, self.KOL_NO, item_no)

                for index in range(9):
                    data = row[index] if index < len(row) else ""
                    value = str(data) if data is not None else ""
                    column = index + 2

                    if column == self.KOL_TGL_MASUK and value:
                        value = format_tanggal_ke_ui(value)
                    elif column == self.KOL_TUJUAN and " - " in value:
                        value = value.split(" - ")[-1]
                    elif column in (
                        self.KOL_KOLI,
                        self.KOL_BERAT,
                        self.KOL_CBM,
                    ):
                        value = format_angka_indonesia(
                            data,
                            kosong_jika_nol=True,
                            nilai_kosong="-",
                        )

                    if column in (
                        self.KOL_KOLI,
                        self.KOL_BERAT,
                        self.KOL_CBM,
                    ):
                        alignment = (
                            Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter
                        )
                    elif column == self.KOL_TGL_MASUK:
                        alignment = (
                            Qt.AlignmentFlag.AlignCenter
                            | Qt.AlignmentFlag.AlignVCenter
                        )
                    else:
                        alignment = (
                            Qt.AlignmentFlag.AlignLeft
                            | Qt.AlignmentFlag.AlignVCenter
                        )

                    item = buat_tabel_item(
                        text=value,
                        editable=False,
                        alignment=alignment,
                    )
                    self.tabel_manifest.setItem(pos, column, item)

                ongkir = row[10] if len(row) > 10 else 0
                value_ongkir = format_ke_rupiah(ongkir) if ongkir else "-"
                item_ongkir = buat_tabel_item(
                    text=value_ongkir,
                    editable=False,
                    alignment=(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    ),
                )
                self.tabel_manifest.setItem(
                    pos,
                    self.KOL_ONGKIR,
                    item_ongkir,
                )

                txt_ket_row = QLineEdit()
                txt_ket_row.setObjectName("manifestKetCell")
                txt_ket_row.setFrame(False)
                txt_ket_row.setPlaceholderText("Ket...")
                txt_ket_row.textChanged.connect(
                    lambda _text, editor=txt_ket_row: (
                        paksa_kapital_lineedit(editor)
                    )
                )
                if belong and len(row) > 11 and row[11]:
                    txt_ket_row.setText(str(row[11]).strip().upper())
                self.tabel_manifest.setCellWidget(
                    pos,
                    self.KOL_KET,
                    txt_ket_row,
                )

            self.load_histori()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error Load Data",
                f"Gagal memuat data resi manifest:\n{exc}",
            )

        finally:
            self.tabel_manifest.blockSignals(False)
            self.tabel_manifest.setUpdatesEnabled(True)
            self.tabel_manifest.viewport().update()
            self._sedang_memuat_tabel = False

    def load_histori(self):
        self.list_histori.setUpdatesEnabled(False)
        self.list_histori.clear()
        win = self.window()
        is_dark = bool(
            win
            and hasattr(win, "current_theme")
            and win.current_theme == "dark"
        )

        try:
            rows = db_service.ambil_histori_manifest(
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                self.cb_tahun_filter.currentText(),
            ) or []

            parents = {}
            for row in rows:
                row = tuple(row or ())
                tanggal_raw = str(row[0] or "") if len(row) > 0 else ""
                manifest_id = str(row[1] or "") if len(row) > 1 else ""
                truk = str(row[2] or "") if len(row) > 2 else ""
                nama_kapal = str(row[3] or "") if len(row) > 3 else ""
                jumlah_resi = row[4] if len(row) > 4 else 0
                note_manifest = str(row[5] or "") if len(row) > 5 else ""

                tanggal_ui = format_tanggal_ke_ui(tanggal_raw)
                bulan = tanggal_ui[3:5] if len(tanggal_ui) >= 5 else ""
                nama_bulan = self.NAMA_BULAN.get(
                    bulan,
                    "Tidak Diketahui",
                )
                title = f"📂 {nama_bulan}"

                if title not in parents:
                    parents[title] = QTreeWidgetItem(self.list_histori)
                    parents[title].setText(0, title)

                child = QTreeWidgetItem(parents[title])
                child.setText(0, tanggal_ui)

                ukuran_dasar = self.list_histori.font().pointSize()
                font_tanggal, warna_abu = get_manifest_history_date_appearance(
                    is_dark,
                    ukuran_dasar,
                )
                child.setFont(0, font_tanggal)
                child.setForeground(0, QBrush(warna_abu))

                is_note_only = bool(
                    note_manifest
                    and truk.strip().upper() == note_manifest.strip().upper()
                )
                if is_note_only:
                    truk_display = f" | NOTE: {note_manifest}"
                else:
                    truk_display = (
                        f" | {truk}"
                        if truk and truk.strip() != "-"
                        else ""
                    )
                kapal_display = (
                    f" | 🚢 {nama_kapal}"
                    if nama_kapal
                    else ""
                )
                child.setText(
                    1,
                    (
                        f"{manifest_id}{truk_display}{kapal_display} "
                        f"({jumlah_resi} Resi)"
                    ),
                )

                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    manifest_id,
                )
                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole + 1,
                    truk,
                )
                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole + 2,
                    nama_kapal,
                )
                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole + 3,
                    note_manifest,
                )
                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole + 4,
                    tanggal_raw,
                )

            self.list_histori.expandAll()
            self.filter_histori(self.txt_cari_histori.text())

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error Histori",
                f"Gagal memuat histori manifest:\n{exc}",
            )

        finally:
            self.list_histori.setUpdatesEnabled(True)
            self.list_histori.viewport().update()

    def update_truk_ke_manifest(self):
        if self._sedang_memproses_manifest:
            return

        manifest_id = (
            self.edit_manifest_id
            if self.is_edit_mode
            else self.txt_no_manifest.text().strip()
        )
        if not manifest_id:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Nomor manifest belum tersedia.",
            )
            return

        resi = []
        for row in range(self.tabel_manifest.rowCount()):
            if self.tabel_manifest.isRowHidden(row):
                continue

            item_check = self.tabel_manifest.item(row, self.KOL_CHECK)
            item_resi = self.tabel_manifest.item(row, self.KOL_RESI)
            if (
                item_check
                and item_resi
                and item_check.checkState() == Qt.CheckState.Checked
            ):
                widget_ket = self.tabel_manifest.cellWidget(
                    row,
                    self.KOL_KET,
                )
                ket_text = (
                    widget_ket.text().strip().upper()
                    if widget_ket
                    else ""
                )
                nomor_resi = item_resi.text().strip()
                if nomor_resi:
                    resi.append((nomor_resi, ket_text))

        if not resi:
            QMessageBox.warning(self, "Warning", "Centang minimal 1 resi!")
            return

        truk_idx = self.cb_jenis_truk.currentIndex()
        truk_text = self.ambil_jenis_truk_manifest()
        nopol = self.txt_no_pol.text().strip().upper()
        sopir = self.txt_sopir.text().strip().upper()
        keterangan = self.txt_keterangan.text().strip().upper()
        nama_kapal = self.txt_nama_kapal.text().strip().upper()
        note_manifest = self.txt_note_manifest.text().strip().upper()

        if truk_idx == 0:
            if nopol or sopir or keterangan:
                QMessageBox.warning(
                    self,
                    "Peringatan",
                    "No. Polisi, Sopir, dan Keterangan hanya untuk detail truk. "
                    "Pilih Jenis Truk, atau kosongkan detail truk lalu isi Note!",
                )
                self.cb_jenis_truk.setFocus()
                return

            if not note_manifest:
                QMessageBox.warning(
                    self,
                    "Peringatan",
                    "Isi Note jika manifest tidak menggunakan detail truk!",
                )
                self.txt_note_manifest.setFocus()
                return

            dict_update = {
                "no_polisi": "",
                "nama_sopir": "",
                "jenis_truk": "",
                "nama_truk": note_manifest,
                "ket_truk": "",
                "nama_kapal": nama_kapal,
                "note_manifest": note_manifest,
            }
        else:
            if (
                self.cb_jenis_truk.currentText().strip() == "Lainnya..."
                and not truk_text
            ):
                QMessageBox.warning(
                    self,
                    "Peringatan",
                    "Jenis truk lainnya wajib diisi!",
                )
                self.txt_jenis_truk_lain.setFocus()
                return

            if not nopol and not sopir:
                QMessageBox.warning(
                    self,
                    "Peringatan",
                    "Isi minimal No. Polisi atau Nama Sopir jika jenis truk dipilih!",
                )
                self.txt_no_pol.setFocus()
                return

            nopol_val = nopol or "BELUM DIKETAHUI"
            sopir_val = sopir or "BELUM ADA SOPIR"
            truk_full = f"{truk_text} - {nopol_val} - {sopir_val}"
            if keterangan:
                truk_full += f" ({keterangan})"

            dict_update = {
                "no_polisi": nopol,
                "nama_sopir": sopir,
                "jenis_truk": truk_text,
                "nama_truk": truk_full,
                "ket_truk": keterangan,
                "nama_kapal": nama_kapal,
                "note_manifest": note_manifest,
            }

        self._sedang_memproses_manifest = True
        self.btn_proses.setEnabled(False)

        try:
            kapal_ok, nama_kapal_resmi = self.pastikan_kapal_terdaftar(
                nama_kapal
            )
            if not kapal_ok:
                QMessageBox.warning(
                    self,
                    "Data Kapal",
                    nama_kapal_resmi,
                )
                self.txt_nama_kapal.setFocus()
                return

            dict_update["nama_kapal"] = nama_kapal_resmi
            tanggal_manifest = (
                self._tanggal_edit_manifest
                if self.is_edit_mode and self._tanggal_edit_manifest
                else QDate.currentDate().toString("yyyy-MM-dd")
            )

            sukses, pesan = db_service.simpan_atau_update_manifest_data(
                manifest_id,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                dict_update,
                resi,
                self.is_edit_mode,
                tanggal_manifest,
            )

            if not sukses:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Gagal memproses manifest:\n{pesan}",
                )
                return

            QMessageBox.information(
                self,
                "Sukses",
                "Manifest berhasil diproses!",
            )
            self.setup_autocomplete_truk()

            if self.is_edit_mode:
                self.batal_edit()
            else:
                self.cb_jenis_truk.setCurrentIndex(0)
                self.txt_jenis_truk_lain.clear()
                self.txt_no_pol.clear()
                self.txt_sopir.clear()
                self.txt_keterangan.clear()
                self.txt_nama_kapal.clear()
                self.txt_note_manifest.clear()
                self.refresh_tahun_filter()
                self.load_data_resi_gudang()
                self.generate_no_manifest()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error",
                f"Gagal memproses manifest:\n{exc}",
            )

        finally:
            self._sedang_memproses_manifest = False
            self.btn_proses.setEnabled(True)

    @staticmethod
    def _format_tanggal_cetak(tanggal_manifest):
        tanggal = QDate.fromString(
            str(tanggal_manifest or "").strip(),
            "yyyy-MM-dd",
        )
        if tanggal.isValid():
            return tanggal.toString("dd/MM/yyyy")
        return QDate.currentDate().toString("dd/MM/yyyy")

    def preview_histori_manifest(self, item):
        if item.parent():
            m_id = str(item.data(0, Qt.ItemDataRole.UserRole) or "").strip()
            truk = str(item.data(0, Qt.ItemDataRole.UserRole + 1) or "").strip()
            nama_kapal = str(item.data(0, Qt.ItemDataRole.UserRole + 2) or "").strip()
            note_manifest = str(item.data(
                0,
                Qt.ItemDataRole.UserRole + 3,
            ) or "").strip()
            tanggal_manifest = str(item.data(
                0,
                Qt.ItemDataRole.UserRole + 4,
            ) or "").strip()

            if not m_id:
                m_id = item.text(1).split(" | ")[0].strip()

            self.siapkan_dan_cetak_dari_id(
                m_id,
                truk,
                nama_kapal,
                note_manifest,
                tanggal_manifest,
            )

    def siapkan_dan_cetak_dari_id(
            self,
            m_id,
            truk,
            nama_kapal="",
            note_manifest="",
            tanggal_manifest="",
    ):
        try:
            kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')
            daftar_resi = db_service.ambil_resi_list_by_manifest(
                m_id,
                kode_cabang,
            ) or []
            data = db_service.ambil_resi_detail_untuk_cetak(
                kode_cabang,
                daftar_resi,
            ) or []

            if not data:
                QMessageBox.warning(
                    self,
                    "Data Manifest",
                    f"Tidak ada data resi untuk manifest {m_id}.",
                )
                return

            items_cetak = []
            for r in data:
                # r[8] = total_ongkir, r[9] = ket_manifest
                ongkir_val = format_ke_rupiah(r[8]) if len(r) > 8 and r[8] else "-"
                ket_val = str(r[9] or "-").strip() if len(r) > 9 else "-"

                items_cetak.append((
                    r[0],
                    r[1],
                    r[2],
                    (
                        str(r[3] or "").split(" - ")[-1]
                        if " - " in str(r[3] or "")
                        else str(r[3] or "")
                    ),
                    r[4],
                    format_angka_indonesia(
                        r[5],
                        kosong_jika_nol=True,
                        nilai_kosong="-",
                    ),
                    format_angka_indonesia(
                        r[6],
                        kosong_jika_nol=True,
                        nilai_kosong="-",
                    ),
                    format_angka_indonesia(
                        r[7],
                        kosong_jika_nol=True,
                        nilai_kosong="-",
                    ),
                    ongkir_val,
                    ket_val,
                ))

            if not nama_kapal:
                nama_kapal = db_service.ambil_nama_kapal_manifest(m_id, kode_cabang)

            if not note_manifest:
                note_manifest = db_service.ambil_note_manifest(
                    m_id,
                    kode_cabang,
                )

            truk_cetak = str(truk or "").strip()
            note_manifest = str(note_manifest or "").strip()

            if (
                    note_manifest
                    and truk_cetak.upper() == note_manifest.upper()
            ):
                truk_cetak = ""

            cetak_manifest_ke_printer(
                {
                    "no_manifest": m_id,
                    "armada": truk_cetak,
                    "note_manifest": note_manifest,
                    "nama_kapal": nama_kapal,
                    "tanggal": self._format_tanggal_cetak(
                        tanggal_manifest
                    ),
                    "items": items_cetak,
                },
                self,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Gagal cetak: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        terapkan_popup_combobox_bawah(self)

        if self._show_event_pertama:
            self._show_event_pertama = False
            self.perbarui_tanggal_header()
            return

        self.refresh_session_ui()

    def sesuaikan_tema_lokal(self):
        win = self.window()
        is_dark = win.current_theme == "dark" if win and hasattr(
            win,
            'current_theme',
        ) else False

        terap_semua_placeholder_dinamis(
            self,
            is_dark=is_dark,
        )

        z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        font_statis = get_global_font_sizes(0)
        font_dinamis = get_global_font_sizes(z)

        styles_statis = get_manifest_styles(is_dark, self.is_edit_mode, 0)
        styles_dinamis = get_manifest_styles(is_dark, self.is_edit_mode, z)

        self.panel_kiri.setStyleSheet(styles_statis['panel_kiri'])
        self.panel_kanan.setStyleSheet(styles_statis['panel_kanan'])
        self.lbl_title.setStyleSheet(styles_statis['lbl_title'])
        self.btn_proses.setStyleSheet(styles_statis['btn_proses'])
        self.splitter.setStyleSheet(styles_statis['splitter'])

        for w in [self.txt_jenis_truk_lain, self.txt_no_pol, self.txt_sopir,
                  self.txt_keterangan, self.txt_nama_kapal,
                  self.txt_note_manifest,
                  self.cb_filter_wilayah, self.cb_jenis_truk,
                  self.cb_tahun_filter, self.txt_cari_histori]:
            w.setStyleSheet(styles_statis['style_input'])

        # Kartu input mengikuti karakter visual panel Pengirim/Penerima
        # pada Tab Resi, termasuk warna adaptif untuk mode terang/gelap.
        if is_dark:
            warna_bg_kartu = "#171B23"
            warna_border_kartu = "#3A4556"
            warna_label_kartu = "#F2F4F7"
        else:
            warna_bg_kartu = "#FFFFFF"
            warna_border_kartu = "#C8D4E3"
            warna_label_kartu = "#172033"

        style_kartu_manifest = f"""
            QFrame#cardRuteManifest, QFrame#cardArmadaManifest {{
                background-color: {warna_bg_kartu};
                border: 1px solid {warna_border_kartu};
                border-radius: 11px;
            }}
        """
        self.card_rute_manifest.setStyleSheet(style_kartu_manifest)
        self.card_armada_manifest.setStyleSheet(style_kartu_manifest)

        style_label_input = f"""
            QLabel {{
                color: {warna_label_kartu};
                background: transparent;
                border: none;
                font-size: {font_statis['sz_base']}px;
                font-weight: 600;
            }}
        """
        for label_input in (
                self.lbl_input_tujuan,
                self.lbl_input_kapal,
                self.lbl_input_note,
                self.lbl_input_truk,
                self.lbl_input_sopir,
                self.lbl_input_keterangan,
        ):
            label_input.setStyleSheet(style_label_input)

        # Style khusus header agar konsisten dengan tampilan header Tab Resi.
        ukuran_header = font_statis["sz_base"]
        if is_dark:
            warna_label = "#C8D1E0"
            warna_teks_tanggal = "#F8FAFC"
            bg_tanggal = "#181C24"
            border_tanggal = "#4B5563"
            warna_nomor = "#FFC400"
            bg_nomor = "#171B23"
            border_nomor = "#3B82F6"
        else:
            warna_label = "#4B5C73"
            warna_teks_tanggal = "#10233F"
            bg_tanggal = "#FFFFFF"
            border_tanggal = "#C8D4E3"
            warna_nomor = "#C90000"
            bg_nomor = "#FFF2F2"
            border_nomor = "#FF4D5E"

        style_label_header = f"""
            QLabel {{
                color: {warna_label};
                background: transparent;
                font-size: {ukuran_header}px;
                font-weight: 600;
            }}
        """
        self.lbl_tanggal_manifest.setStyleSheet(style_label_header)
        self.lbl_no_manifest.setStyleSheet(style_label_header)

        self.txt_tanggal_manifest.setStyleSheet(
            f"""
                QLineEdit {{
                    color: {warna_teks_tanggal};
                    background: {bg_tanggal};
                    border: 1px solid {border_tanggal};
                    border-radius: 5px;
                    padding: 2px 8px;
                    font-size: {ukuran_header}px;
                }}
            """
        )
        self.txt_no_manifest.setStyleSheet(
            f"""
                QLineEdit {{
                    color: {warna_nomor};
                    background: {bg_nomor};
                    border: 2px solid {border_nomor};
                    border-radius: 6px;
                    padding: 2px 10px;
                    font-size: {ukuran_header + 3}px;
                    font-weight: 800;
                    letter-spacing: 1px;
                }}
            """
        )

        # Integrasi tabel responsif
        self.tabel_manifest.setStyleSheet(styles_dinamis['style_tabel'])
        update_status_delegate_theme(self.tabel_manifest, is_dark)

        if hasattr(self.tabel_manifest, "frozen_table"):
            update_status_delegate_theme(
                self.tabel_manifest.frozen_table,
                is_dark,
            )

        font = self.tabel_manifest.font()
        font.setPointSize(font_dinamis["sz_base"])
        self.tabel_manifest.setFont(font)

        header_font = self.tabel_manifest.horizontalHeader().font()
        header_font.setPointSize(font_dinamis["sz_base"])
        self.tabel_manifest.horizontalHeader().setFont(header_font)
        self.tabel_manifest.verticalHeader().setFont(header_font)

        faktor = max(0.68, min(1.0 + (z * 0.08), 1.80))
        tinggi_baris = max(24, int(32 * faktor))
        self.tabel_manifest.verticalHeader().setDefaultSectionSize(tinggi_baris)

        if hasattr(self.tabel_manifest, "frozen_table"):
            self.tabel_manifest.frozen_table.horizontalHeader().setFont(header_font)
            self.tabel_manifest.frozen_table.verticalHeader().setDefaultSectionSize(
                tinggi_baris,
            )

        header = self.tabel_manifest.horizontalHeader()
        header.blockSignals(True)
        self._sedang_menerapkan_zoom = True
        try:
            zoom_helper._skalakan_kolom_tableview(
                self.tabel_manifest,
                z,
            )
        finally:
            self._sedang_menerapkan_zoom = False
            header.blockSignals(False)

        # Histori Manifest responsif ke zoom
        self.list_histori.setStyleSheet(styles_dinamis['list_histori'])
        font_histori = self.list_histori.font()
        font_histori.setPointSize(font_dinamis["sz_base"])
        self.list_histori.setFont(font_histori)

    def _settings_kolom(self):
        return QSettings(
            self.SETTINGS_ORGANIZATION,
            self.SETTINGS_APPLICATION,
        )

    @staticmethod
    def _normalisasi_daftar_lebar(value, jumlah_kolom):
        if not isinstance(value, (list, tuple)):
            return None
        if len(value) != jumlah_kolom:
            return None

        hasil = []
        try:
            for width in value:
                hasil.append(min(max(20, int(width)), 1500))
        except (TypeError, ValueError):
            return None
        return hasil

    def simpan_lebar_kolom(self, tabel):
        if self._sedang_menerapkan_zoom:
            return

        z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        faktor = max(0.68, min(1.0 + (z * 0.08), 1.80))

        lebar_dasar = []
        for index in range(tabel.columnCount()):
            lebar_asli = min(
                max(20, int(tabel.columnWidth(index) / faktor)),
                1500,
            )
            if index == self.KOL_CHECK:
                lebar_asli = 22
            lebar_dasar.append(lebar_asli)

            if hasattr(tabel, "_zoom_base_column_widths"):
                tabel._zoom_base_column_widths[index] = lebar_asli

        settings = self._settings_kolom()
        settings.setValue(
            self.SETTINGS_KEY_LEBAR_KOLOM,
            lebar_dasar,
        )
        settings.sync()

    def load_lebar_kolom(self, tabel):
        saved_widths = self._normalisasi_daftar_lebar(
            self._settings_kolom().value(
                self.SETTINGS_KEY_LEBAR_KOLOM
            ),
            tabel.columnCount(),
        )
        base_widths = list(
            saved_widths or self.DEFAULT_COLUMN_WIDTHS
        )

        while len(base_widths) < tabel.columnCount():
            base_widths.append(110)

        header = tabel.horizontalHeader()
        header.blockSignals(True)
        self._sedang_menerapkan_zoom = True

        try:
            for index in range(tabel.columnCount()):
                width = (
                    22
                    if index == self.KOL_CHECK
                    else base_widths[index]
                )
                tabel.setColumnWidth(index, int(width))

            tabel._zoom_base_column_widths = {
                index: int(
                    22
                    if index == self.KOL_CHECK
                    else base_widths[index]
                )
                for index in range(tabel.columnCount())
            }

        finally:
            self._sedang_menerapkan_zoom = False
            header.blockSignals(False)

    def on_wilayah_changed(self):
        if self.is_edit_mode:
            self.batal_edit()
            return

        self.generate_no_manifest()
        self.load_data_resi_gudang()

    def filter_histori(self, text):
        keyword = str(text or "").strip().lower()

        for index_parent in range(self.list_histori.topLevelItemCount()):
            parent = self.list_histori.topLevelItem(index_parent)
            parent_visible = False

            for index_child in range(parent.childCount()):
                child = parent.child(index_child)
                haystack = f"{child.text(0)} {child.text(1)}".lower()
                match = keyword in haystack
                child.setHidden(not match)
                parent_visible = parent_visible or match

            parent.setHidden(not parent_visible)

    def buka_menu_klik_kanan_histori(self, pos):
        item = self.list_histori.itemAt(pos)
        if not item or not item.parent(): return
        menu = QMenu()
        act_print = menu.addAction("🖨 Preview Cetak")
        act_edit = menu.addAction("✏️ Edit Workspace")
        action = menu.exec(
            self.list_histori.viewport().mapToGlobal(pos)
        )

        m_id = str(
            item.data(0, Qt.ItemDataRole.UserRole)
            or ""
        ).strip()
        truk = str(
            item.data(0, Qt.ItemDataRole.UserRole + 1)
            or ""
        ).strip()
        nama_kapal = str(
            item.data(0, Qt.ItemDataRole.UserRole + 2)
            or ""
        ).strip()
        note_manifest = str(
            item.data(0, Qt.ItemDataRole.UserRole + 3)
            or ""
        ).strip()
        tanggal_manifest = str(
            item.data(0, Qt.ItemDataRole.UserRole + 4)
            or ""
        ).strip()

        if not m_id:
            m_id = item.text(1).split(" | ")[0].strip()

        if action == act_print:
            self.siapkan_dan_cetak_dari_id(
                m_id,
                truk,
                nama_kapal,
                note_manifest,
                tanggal_manifest,
            )
        elif action == act_edit:
            self.aktifkan_mode_edit(
                m_id,
                truk,
                nama_kapal,
                note_manifest,
                tanggal_manifest,
            )

    def aktifkan_mode_edit(
            self,
            m_id,
            truk_str,
            nama_kapal="",
            note_manifest="",
            tanggal_manifest="",
    ):
        m_id = str(m_id or "").strip().upper()
        if not m_id:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Nomor manifest tidak valid.",
            )
            return

        self.is_edit_mode = True
        self.edit_manifest_id = m_id
        self._tanggal_edit_manifest = str(
            tanggal_manifest or ""
        ).strip()

        self.cb_jenis_truk.setCurrentIndex(0)
        self.txt_jenis_truk_lain.clear()
        self.txt_no_pol.clear()
        self.txt_sopir.clear()
        self.txt_keterangan.clear()
        self.txt_nama_kapal.clear()
        self.txt_note_manifest.clear()

        kode_cabang = CURRENT_SESSION.get("kode_cabang", "PUSAT")

        nama_kapal = str(nama_kapal or "").strip().upper()
        if not nama_kapal:
            nama_kapal = db_service.ambil_nama_kapal_manifest(m_id, kode_cabang)
        self.txt_nama_kapal.setText(nama_kapal)

        if not note_manifest:
            note_manifest = db_service.ambil_note_manifest(
                m_id,
                kode_cabang,
            )
        note_manifest = str(note_manifest or "").strip().upper()
        self.txt_note_manifest.setText(note_manifest)

        truk_bersih = str(truk_str or '').strip()
        is_note_only = bool(
            note_manifest
            and truk_bersih.upper() == note_manifest.upper()
        )

        if truk_bersih and truk_bersih != "-" and not is_note_only:
            parts = truk_bersih.split(" - ", 2)

            if len(parts) >= 3:
                jenis_text, nopol_text, sopir_ket = parts
                self.set_jenis_truk_manifest(jenis_text.strip())

                nopol_text = nopol_text.strip()
                if nopol_text not in ("-", "BELUM DIKETAHUI"):
                    self.txt_no_pol.setText(nopol_text)

                sopir_text = sopir_ket.strip()
                keterangan_text = ""
                if " (" in sopir_text and sopir_text.endswith(")"):
                    sopir_text, keterangan_text = sopir_text.rsplit(" (", 1)
                    keterangan_text = keterangan_text[:-1]

                if sopir_text.strip() not in ("", "-", "BELUM ADA SOPIR"):
                    self.txt_sopir.setText(sopir_text.strip())
                if keterangan_text:
                    self.txt_keterangan.setText(keterangan_text.strip())
            elif not note_manifest:
                # Kompatibilitas manifest lama sebelum kolom Note tersedia.
                self.txt_note_manifest.setText(truk_bersih.upper())

        self.lbl_title.setText(f"✏️ Edit Manifest: {m_id}")
        self.txt_no_manifest.setText(m_id)
        self.btn_proses.setText("💾 SIMPAN MANIFEST")
        self.btn_batal_edit.show()
        self.sesuaikan_tema_lokal()
        self.load_data_resi_gudang()

    def batal_edit(self):
        self.is_edit_mode = False
        self.edit_manifest_id = ""
        self._tanggal_edit_manifest = ""
        self.lbl_title.setText("📦 Pembuatan Manifest Pengiriman")
        self.btn_proses.setText("⚡ BUAT MANIFEST")
        self.btn_batal_edit.hide()

        self.cb_jenis_truk.setCurrentIndex(0)
        self.txt_jenis_truk_lain.clear()
        self.txt_sopir.clear()
        self.txt_no_pol.clear()
        self.txt_keterangan.clear()
        self.txt_nama_kapal.clear()
        self.txt_note_manifest.clear()

        self.sesuaikan_tema_lokal()
        self.generate_no_manifest()
        self.load_data_resi_gudang()