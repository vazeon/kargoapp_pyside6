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

from themes.components.combobox import terapkan_popup_bawah_combobox

from utils.splitter_helper import buat_splitter
from utils.printer.print_manifest import cetak_manifest_ke_printer
from utils.frozen_table_helper import FrozenTableWidget
from utils.typography import (
    get_global_font_sizes,
    konversi_style_font_ke_point,
    ukuran_font_px_ke_pt,
)
from utils import zoom as zoom_helper
from utils.number_formatters import (
    format_angka_indonesia,
    format_ke_rupiah,
)
from utils.table_helper import buat_tabel_item
from utils.widget_helpers import paksa_kapital_lineedit
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

        layout_kiri = self._buat_panel_kiri()
        self._bangun_header_manifest(layout_kiri)
        self._bangun_detail_manifest(layout_kiri)
        self._bangun_tabel_manifest(layout_kiri)
        self._bangun_panel_histori()

        self.splitter = buat_splitter(
            self.panel_kiri,
            self.panel_kanan,
            orientation=Qt.Orientation.Horizontal,
            ukuran_awal=(800, 200),
            bisa_diciutkan=False,
            parent=self,
        )
        layout_utama.addWidget(self.splitter)

        self.btn_proses.clicked.connect(self.update_truk_ke_manifest)
        self.refresh_tahun_filter()
        self.load_data_resi_gudang()
        self.generate_no_manifest()
        self.sesuaikan_tema_lokal()
        self.setup_autocomplete_truk()

    def _buat_panel_kiri(self):
        self.panel_kiri = QWidget()
        self.panel_kiri.setMinimumWidth(700)
        self.panel_kiri.setMaximumWidth(1800)

        layout = QVBoxLayout(self.panel_kiri)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        return layout

    @staticmethod
    def _konfigurasi_wadah_tetap(widget, tinggi):
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        widget.setFixedHeight(tinggi)

    @staticmethod
    def _buat_grid_card(card, vertical_spacing):
        grid = QGridLayout(card)
        grid.setContentsMargins(26, 18, 26, 18)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(vertical_spacing)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        return grid

    @staticmethod
    def _buat_wadah_header_field(label_text, ukuran, spacing):
        wadah = QWidget()
        layout = QHBoxLayout(wadah)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)

        label = QLabel(label_text)
        editor = QLineEdit()
        editor.setReadOnly(True)
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setFixedSize(*ukuran)
        editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(label)
        layout.addWidget(editor)
        return wadah, label, editor

    def _bangun_header_manifest(self, layout_kiri):
        self.wadah_header_manifest = QWidget()
        self.wadah_header_manifest.setObjectName("wadahHeaderManifest")
        self._konfigurasi_wadah_tetap(self.wadah_header_manifest, 48)

        layout_header = QGridLayout(self.wadah_header_manifest)
        layout_header.setContentsMargins(0, 0, 0, 2)
        layout_header.setHorizontalSpacing(12)
        for column in range(3):
            layout_header.setColumnStretch(column, 1)

        self.lbl_title = QLabel("📦 Pembuatan Manifest Pengiriman")
        layout_header.addWidget(
            self.lbl_title,
            0,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        (
            wadah_tanggal,
            self.lbl_tanggal_manifest,
            self.txt_tanggal_manifest,
        ) = self._buat_wadah_header_field("Tanggal Transaksi:", (180, 30), 6)
        layout_header.addWidget(
            wadah_tanggal,
            0,
            1,
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
        )

        (
            wadah_nomor,
            self.lbl_no_manifest,
            self.txt_no_manifest,
        ) = self._buat_wadah_header_field("No. Manifest:", (200, 36), 8)
        layout_header.addWidget(
            wadah_nomor,
            0,
            2,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        layout_kiri.addWidget(self.wadah_header_manifest, 0)
        self.perbarui_tanggal_header()

    @staticmethod
    def _konfigurasi_lineedit_kapital(widget, placeholder, minimum_width=None):
        widget.setPlaceholderText(placeholder)
        if minimum_width is not None:
            widget.setMinimumWidth(minimum_width)
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        widget.textChanged.connect(
            lambda _text="", editor=widget: paksa_kapital_lineedit(editor)
        )

    def _bangun_card_rute_manifest(self):
        self.card_rute_manifest = QFrame()
        self.card_rute_manifest.setObjectName("cardRuteManifest")
        self._konfigurasi_wadah_tetap(self.card_rute_manifest, 164)
        grid = self._buat_grid_card(self.card_rute_manifest, 12)

        self.lbl_input_tujuan = QLabel("Tujuan:")
        self.lbl_input_kapal = QLabel("Kapal:")
        self.lbl_input_note = QLabel("Note:")
        for label in (
            self.lbl_input_tujuan,
            self.lbl_input_kapal,
            self.lbl_input_note,
        ):
            label.setMinimumWidth(70)

        self.cb_filter_wilayah = QComboBox()
        self.cb_filter_wilayah.addItems(
            DATA_CLIENT.get(
                "provinsi_tujuan",
                ["PROVINSI A", "PROVINSI B", "PROVINSI C"],
            )
        )
        self.cb_filter_wilayah.setMinimumWidth(230)
        self.cb_filter_wilayah.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.cb_filter_wilayah.currentTextChanged.connect(self.on_wilayah_changed)

        self.txt_nama_kapal = QLineEdit()
        self._konfigurasi_lineedit_kapital(
            self.txt_nama_kapal,
            "Nama Kapal (Opsional)",
            230,
        )
        self.txt_nama_kapal.editingFinished.connect(self.autofill_kapal_dari_input)

        self.txt_note_manifest = QLineEdit()
        self._konfigurasi_lineedit_kapital(
            self.txt_note_manifest,
            "Note (Wajib jika tanpa detail truk)",
            230,
        )

        for row, (label, widget) in enumerate((
            (self.lbl_input_tujuan, self.cb_filter_wilayah),
            (self.lbl_input_kapal, self.txt_nama_kapal),
            (self.lbl_input_note, self.txt_note_manifest),
        )):
            grid.addWidget(
                label,
                row,
                0,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            grid.addWidget(widget, row, 1)

    def _perbarui_font_placeholder_truk(self, index=None):
        if index is None:
            index = self.cb_jenis_truk.currentIndex()

        font_utama = self.cb_jenis_truk.font()
        font_utama.setItalic(index == 0)
        self.cb_jenis_truk.setFont(font_utama)

        font_italic = QFont(font_utama)
        font_italic.setItalic(True)
        self.cb_jenis_truk.setItemData(0, font_italic, Qt.ItemDataRole.FontRole)

        font_normal = QFont(font_utama)
        font_normal.setItalic(False)
        for item_index in range(1, self.cb_jenis_truk.count()):
            self.cb_jenis_truk.setItemData(
                item_index,
                font_normal,
                Qt.ItemDataRole.FontRole,
            )

    def _bangun_card_armada_manifest(self):
        self.card_armada_manifest = QFrame()
        self.card_armada_manifest.setObjectName("cardArmadaManifest")
        self._konfigurasi_wadah_tetap(self.card_armada_manifest, 164)
        grid = self._buat_grid_card(self.card_armada_manifest, 10)

        self.lbl_input_truk = QLabel("Truk:")
        self.lbl_input_sopir = QLabel("Sopir:")
        self.lbl_input_keterangan = QLabel("Ket:")
        for label in (
            self.lbl_input_truk,
            self.lbl_input_sopir,
            self.lbl_input_keterangan,
        ):
            label.setMinimumWidth(70)

        self.cb_jenis_truk = QComboBox()
        self.cb_jenis_truk.addItem("- Pilih jenis -")
        self.cb_jenis_truk.addItems(["TB", "Tronton", "CDD", "Pick-up", "Lainnya..."])
        self.cb_jenis_truk.setMinimumWidth(150)
        self.cb_jenis_truk.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.cb_jenis_truk.currentIndexChanged.connect(
            self._perbarui_font_placeholder_truk
        )
        self.cb_jenis_truk.currentIndexChanged.connect(
            self.on_jenis_truk_manifest_changed
        )
        self._perbarui_font_placeholder_truk(0)

        self.txt_jenis_truk_lain = QLineEdit()
        self._konfigurasi_lineedit_kapital(
            self.txt_jenis_truk_lain,
            "Jenis lainnya",
            130,
        )
        self.txt_jenis_truk_lain.hide()

        self.txt_no_pol = QLineEdit()
        self._konfigurasi_lineedit_kapital(self.txt_no_pol, "No. Pol", 130)

        wadah_truk = QWidget()
        layout_truk = QHBoxLayout(wadah_truk)
        layout_truk.setContentsMargins(0, 0, 0, 0)
        layout_truk.setSpacing(8)
        layout_truk.addWidget(self.cb_jenis_truk, 5)
        layout_truk.addWidget(self.txt_jenis_truk_lain, 4)
        layout_truk.addWidget(self.txt_no_pol, 4)

        self.txt_sopir = QLineEdit()
        self._konfigurasi_lineedit_kapital(self.txt_sopir, "Nama Sopir")

        self.txt_keterangan = QLineEdit()
        self._konfigurasi_lineedit_kapital(self.txt_keterangan, "Keterangan")

        for row, (label, widget) in enumerate((
            (self.lbl_input_truk, wadah_truk),
            (self.lbl_input_sopir, self.txt_sopir),
            (self.lbl_input_keterangan, self.txt_keterangan),
        )):
            grid.addWidget(
                label,
                row,
                0,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            grid.addWidget(widget, row, 1)

    def _bangun_tombol_manifest(self):
        wadah = QWidget()
        wadah.setFixedSize(210, 132)
        wadah.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(wadah)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.btn_proses = QPushButton("BUAT MANIFEST")
        self.btn_proses.setMinimumWidth(190)
        self.btn_proses.setMinimumHeight(38)
        layout.addWidget(self.btn_proses, 0, Qt.AlignmentFlag.AlignHCenter)

        self.btn_batal_edit = QPushButton("❌ BATAL")
        self.btn_batal_edit.setMinimumWidth(190)
        self.btn_batal_edit.clicked.connect(self.batal_edit)
        self.btn_batal_edit.hide()
        layout.addWidget(self.btn_batal_edit, 0, Qt.AlignmentFlag.AlignHCenter)
        return wadah

    def _bangun_detail_manifest(self, layout_kiri):
        self.wadah_detail_manifest = QWidget()
        self.wadah_detail_manifest.setObjectName("wadahDetailManifest")
        self._konfigurasi_wadah_tetap(self.wadah_detail_manifest, 172)

        layout = QHBoxLayout(self.wadah_detail_manifest)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self._bangun_card_rute_manifest()
        self._bangun_card_armada_manifest()
        wadah_tombol = self._bangun_tombol_manifest()

        layout.addWidget(self.card_rute_manifest, 5)
        layout.addWidget(self.card_armada_manifest, 6)
        layout.addWidget(wadah_tombol, 0, Qt.AlignmentFlag.AlignVCenter)
        layout_kiri.addWidget(
            self.wadah_detail_manifest,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

    def _tema_gelap_aktif(self):
        win = self.window()
        return bool(
            win
            and hasattr(win, "current_theme")
            and win.current_theme == "dark"
        )

    def _pasang_delegate_manifest(self, tabel, is_dark):
        attach_status_delegate(
            tabel,
            status_column=self.KOL_CHECK,
            status_role=Qt.ItemDataRole.UserRole,
            color_provider=_get_manifest_delegate_colors,
            is_dark=is_dark,
        )

    def _bangun_tabel_manifest(self, layout_kiri):
        self.tabel_manifest = FrozenTableWidget(
            frozen_cols=3,
            fixed_cols=[0],
            fixed_widths={0: 22},
        )
        self.tabel_manifest.setColumnCount(13)
        self.tabel_manifest.setHorizontalHeaderLabels([
            "✔", "NO.", "RESI", "TGL MASUK", "PENGIRIM", "PENERIMA",
            "TUJUAN", "NAMA BARANG", "KOLI", "BERAT (kg)", "KUBIK (m3)",
            "ONGKIR (Rp)", "KETERANGAN",
        ])
        self.tabel_manifest.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.tabel_manifest.verticalHeader().setVisible(False)
        self.tabel_manifest.setAlternatingRowColors(True)

        is_dark = self._tema_gelap_aktif()
        self._pasang_delegate_manifest(self.tabel_manifest, is_dark)
        frozen_table = getattr(self.tabel_manifest, "frozen_table", None)
        if frozen_table is not None:
            self._pasang_delegate_manifest(frozen_table, is_dark)

        self.load_lebar_kolom(self.tabel_manifest)
        self.tabel_manifest.horizontalHeader().sectionResized.connect(
            lambda: self.simpan_lebar_kolom(self.tabel_manifest)
        )
        self.tabel_manifest.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout_kiri.addWidget(self.tabel_manifest, 1)
        layout_kiri.setStretch(0, 0)
        layout_kiri.setStretch(1, 0)
        layout_kiri.setStretch(2, 1)

    def _bangun_panel_histori(self):
        self.panel_kanan = QWidget()
        self.panel_kanan.setMinimumWidth(260)
        self.panel_kanan.setMaximumWidth(520)
        layout = QVBoxLayout(self.panel_kanan)
        layout.addWidget(QLabel("🕒 Histori Manifest:"))

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Tahun:"))

        self.cb_tahun_filter = QComboBox()
        self.cb_tahun_filter.setFixedWidth(80)
        self.cb_tahun_filter.currentTextChanged.connect(self.load_histori)
        filter_layout.addWidget(self.cb_tahun_filter)

        self.txt_cari_histori = QLineEdit()
        self._konfigurasi_lineedit_kapital(
            self.txt_cari_histori,
            "Cari manifest...",
        )
        self.txt_cari_histori.textChanged.connect(self.filter_histori)
        filter_layout.addWidget(self.txt_cari_histori)
        layout.addLayout(filter_layout)

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
            self.buka_menu_klik_kanan_histori
        )
        layout.addWidget(self.list_histori)


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

    def _buat_item_check_manifest(self, belong):
        item = QTableWidgetItem()
        item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        item.setCheckState(
            Qt.CheckState.Checked if belong else Qt.CheckState.Unchecked
        )
        item.setData(
            Qt.ItemDataRole.UserRole,
            "BELONG" if belong else "",
        )
        return item

    def _format_cell_resi_manifest(self, data, column):
        value = str(data) if data is not None else ""
        if column == self.KOL_TGL_MASUK and value:
            return format_tanggal_ke_ui(value)
        if column == self.KOL_TUJUAN and " - " in value:
            return value.split(" - ")[-1]
        if column in (self.KOL_KOLI, self.KOL_BERAT, self.KOL_CBM):
            return format_angka_indonesia(
                data,
                kosong_jika_nol=True,
                nilai_kosong="-",
            )
        return value

    def _alignment_cell_resi_manifest(self, column):
        if column in (self.KOL_KOLI, self.KOL_BERAT, self.KOL_CBM):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if column == self.KOL_TGL_MASUK:
            return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    @staticmethod
    def _buat_editor_keterangan_manifest(teks=""):
        editor = QLineEdit()
        editor.setObjectName("manifestKetCell")
        editor.setFrame(False)
        editor.setPlaceholderText("Ket...")
        editor.textChanged.connect(
            lambda _text, widget=editor: paksa_kapital_lineedit(widget)
        )
        if teks:
            editor.setText(str(teks).strip().upper())
        return editor

    def _isi_baris_resi_manifest(self, row):
        row = tuple(row or ())
        tabel = self.tabel_manifest
        pos = tabel.rowCount()
        tabel.insertRow(pos)

        manifest_row = str(row[9] or "").strip() if len(row) > 9 else ""
        belong = bool(self.is_edit_mode and manifest_row == self.edit_manifest_id)
        tabel.setItem(pos, self.KOL_CHECK, self._buat_item_check_manifest(belong))
        tabel.setItem(
            pos,
            self.KOL_NO,
            buat_tabel_item(
                text=str(pos + 1),
                editable=False,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
        )

        for index in range(9):
            column = index + 2
            data = row[index] if index < len(row) else ""
            tabel.setItem(
                pos,
                column,
                buat_tabel_item(
                    text=self._format_cell_resi_manifest(data, column),
                    editable=False,
                    alignment=self._alignment_cell_resi_manifest(column),
                ),
            )

        ongkir = row[10] if len(row) > 10 else 0
        tabel.setItem(
            pos,
            self.KOL_ONGKIR,
            buat_tabel_item(
                text=format_ke_rupiah(ongkir) if ongkir else "-",
                editable=False,
                alignment=(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
                ),
            ),
        )

        keterangan = row[11] if belong and len(row) > 11 and row[11] else ""
        tabel.setCellWidget(
            pos,
            self.KOL_KET,
            self._buat_editor_keterangan_manifest(keterangan),
        )

    def load_data_resi_gudang(self):
        if self._sedang_memuat_tabel:
            return

        self._sedang_memuat_tabel = True
        tabel = self.tabel_manifest

        if not hasattr(tabel, "_zoom_base_column_widths"):
            tabel._zoom_base_column_widths = {
                index: tabel.columnWidth(index)
                for index in range(tabel.columnCount())
            }

        tabel.blockSignals(True)
        tabel.setUpdatesEnabled(False)
        tabel.setRowCount(0)

        try:
            rows = db_service.ambil_resi_untuk_manifest(
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                self.cb_filter_wilayah.currentText(),
                self.is_edit_mode,
                self.edit_manifest_id,
            ) or []
            for row in rows:
                self._isi_baris_resi_manifest(row)
            self.load_histori()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error Load Data",
                f"Gagal memuat data resi manifest:\n{exc}",
            )
        finally:
            tabel.blockSignals(False)
            tabel.setUpdatesEnabled(True)
            tabel.viewport().update()
            self._sedang_memuat_tabel = False

    def _buat_item_histori_manifest(self, row, parents, is_dark):
        row = tuple(row or ())
        tanggal_raw = str(row[0] or "") if len(row) > 0 else ""
        manifest_id = str(row[1] or "") if len(row) > 1 else ""
        truk = str(row[2] or "") if len(row) > 2 else ""
        nama_kapal = str(row[3] or "") if len(row) > 3 else ""
        jumlah_resi = row[4] if len(row) > 4 else 0
        note_manifest = str(row[5] or "") if len(row) > 5 else ""

        tanggal_ui = format_tanggal_ke_ui(tanggal_raw)
        bulan = tanggal_ui[3:5] if len(tanggal_ui) >= 5 else ""
        title = f"📂 {self.NAMA_BULAN.get(bulan, 'Tidak Diketahui')}"
        if title not in parents:
            parents[title] = QTreeWidgetItem(self.list_histori)
            parents[title].setText(0, title)

        child = QTreeWidgetItem(parents[title])
        child.setText(0, tanggal_ui)
        font_tanggal, warna_abu = get_manifest_history_date_appearance(
            is_dark,
            self._ukuran_point_histori_aktif(),
        )
        child.setFont(0, font_tanggal)
        child.setForeground(0, QBrush(warna_abu))

        is_note_only = bool(
            note_manifest
            and truk.strip().upper() == note_manifest.strip().upper()
        )
        truk_display = (
            f" | NOTE: {note_manifest}"
            if is_note_only
            else (f" | {truk}" if truk and truk.strip() != "-" else "")
        )
        kapal_display = f" | 🚢 {nama_kapal}" if nama_kapal else ""
        child.setText(
            1,
            f"{manifest_id}{truk_display}{kapal_display} ({jumlah_resi} Resi)",
        )

        for role_offset, value in enumerate((
            manifest_id,
            truk,
            nama_kapal,
            note_manifest,
            tanggal_raw,
        )):
            child.setData(
                0,
                Qt.ItemDataRole.UserRole + role_offset,
                value,
            )

    def load_histori(self):
        self.list_histori.setUpdatesEnabled(False)
        self.list_histori.clear()
        is_dark = self._tema_gelap_aktif()
        try:
            rows = db_service.ambil_histori_manifest(
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                self.cb_tahun_filter.currentText(),
            ) or []
            parents = {}
            for row in rows:
                self._buat_item_histori_manifest(row, parents, is_dark)

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

    def _ukuran_point_histori_aktif(self):
        """Menghasilkan ukuran point valid dari font histori aktif."""
        font_histori = self.list_histori.font()
        ukuran_point = font_histori.pointSize()

        if ukuran_point > 0:
            return ukuran_point

        ukuran_pixel = font_histori.pixelSize()
        if ukuran_pixel <= 0:
            return ukuran_font_px_ke_pt(get_global_font_sizes(0)["sz_base"])

        dpi_y = max(1, self.list_histori.logicalDpiY())
        return max(1.0, ukuran_pixel * 72.0 / dpi_y)

    def _sinkronkan_font_item_histori(self, is_dark):
        """Menyamakan font tanggal histori setelah tema atau zoom berubah."""
        ukuran_point = self._ukuran_point_histori_aktif()
        font_tanggal, warna_abu = get_manifest_history_date_appearance(
            is_dark,
            ukuran_point,
        )

        for parent_index in range(self.list_histori.topLevelItemCount()):
            parent_item = self.list_histori.topLevelItem(parent_index)
            if parent_item is None:
                continue

            for child_index in range(parent_item.childCount()):
                child_item = parent_item.child(child_index)
                if child_item is None:
                    continue

                child_item.setFont(0, font_tanggal)
                child_item.setForeground(0, QBrush(warna_abu))

    def _ambil_resi_terpilih_manifest(self):
        resi = []
        for row in range(self.tabel_manifest.rowCount()):
            if self.tabel_manifest.isRowHidden(row):
                continue

            item_check = self.tabel_manifest.item(row, self.KOL_CHECK)
            item_resi = self.tabel_manifest.item(row, self.KOL_RESI)
            if not (
                item_check
                and item_resi
                and item_check.checkState() == Qt.CheckState.Checked
            ):
                continue

            widget_ket = self.tabel_manifest.cellWidget(row, self.KOL_KET)
            ket_text = (
                widget_ket.text().strip().upper()
                if widget_ket
                else ""
            )
            nomor_resi = item_resi.text().strip()
            if nomor_resi:
                resi.append((nomor_resi, ket_text))
        return resi

    def _buat_data_armada_manifest(self):
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
                return None
            if not note_manifest:
                QMessageBox.warning(
                    self,
                    "Peringatan",
                    "Isi Note jika manifest tidak menggunakan detail truk!",
                )
                self.txt_note_manifest.setFocus()
                return None

            return {
                "no_polisi": "",
                "nama_sopir": "",
                "jenis_truk": "",
                "nama_truk": note_manifest,
                "ket_truk": "",
                "nama_kapal": nama_kapal,
                "note_manifest": note_manifest,
            }

        if self.cb_jenis_truk.currentText().strip() == "Lainnya..." and not truk_text:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Jenis truk lainnya wajib diisi!",
            )
            self.txt_jenis_truk_lain.setFocus()
            return None

        if not nopol and not sopir:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Isi minimal No. Polisi atau Nama Sopir jika jenis truk dipilih!",
            )
            self.txt_no_pol.setFocus()
            return None

        truk_full = (
            f"{truk_text} - {nopol or 'BELUM DIKETAHUI'} "
            f"- {sopir or 'BELUM ADA SOPIR'}"
        )
        if keterangan:
            truk_full += f" ({keterangan})"

        return {
            "no_polisi": nopol,
            "nama_sopir": sopir,
            "jenis_truk": truk_text,
            "nama_truk": truk_full,
            "ket_truk": keterangan,
            "nama_kapal": nama_kapal,
            "note_manifest": note_manifest,
        }

    def _kosongkan_input_manifest(self):
        self.cb_jenis_truk.setCurrentIndex(0)
        self.txt_jenis_truk_lain.clear()
        self.txt_no_pol.clear()
        self.txt_sopir.clear()
        self.txt_keterangan.clear()
        self.txt_nama_kapal.clear()
        self.txt_note_manifest.clear()

    def _tanggal_manifest_aktif(self):
        if self.is_edit_mode and self._tanggal_edit_manifest:
            return self._tanggal_edit_manifest
        return QDate.currentDate().toString("yyyy-MM-dd")

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

        resi = self._ambil_resi_terpilih_manifest()
        if not resi:
            QMessageBox.warning(self, "Warning", "Centang minimal 1 resi!")
            return

        dict_update = self._buat_data_armada_manifest()
        if dict_update is None:
            return

        self._sedang_memproses_manifest = True
        self.btn_proses.setEnabled(False)
        try:
            kapal_ok, nama_kapal_resmi = self.pastikan_kapal_terdaftar(
                dict_update["nama_kapal"]
            )
            if not kapal_ok:
                QMessageBox.warning(self, "Data Kapal", nama_kapal_resmi)
                self.txt_nama_kapal.setFocus()
                return

            dict_update["nama_kapal"] = nama_kapal_resmi
            sukses, pesan = db_service.simpan_atau_update_manifest_data(
                manifest_id,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                dict_update,
                resi,
                self.is_edit_mode,
                self._tanggal_manifest_aktif(),
            )
            if not sukses:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Gagal memproses manifest:\n{pesan}",
                )
                return

            QMessageBox.information(self, "Sukses", "Manifest berhasil diproses!")
            self.setup_autocomplete_truk()
            if self.is_edit_mode:
                self.batal_edit()
            else:
                self._kosongkan_input_manifest()
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

    @staticmethod
    def _data_dari_item_histori(item):
        manifest_id = str(
            item.data(0, Qt.ItemDataRole.UserRole) or ""
        ).strip()
        truk = str(
            item.data(0, Qt.ItemDataRole.UserRole + 1) or ""
        ).strip()
        nama_kapal = str(
            item.data(0, Qt.ItemDataRole.UserRole + 2) or ""
        ).strip()
        note_manifest = str(
            item.data(0, Qt.ItemDataRole.UserRole + 3) or ""
        ).strip()
        tanggal_manifest = str(
            item.data(0, Qt.ItemDataRole.UserRole + 4) or ""
        ).strip()
        if not manifest_id:
            manifest_id = item.text(1).split(" | ")[0].strip()
        return manifest_id, truk, nama_kapal, note_manifest, tanggal_manifest

    def preview_histori_manifest(self, item):
        if not item.parent():
            return
        self.siapkan_dan_cetak_dari_id(*self._data_dari_item_histori(item))

    @staticmethod
    def _format_baris_cetak_manifest(row):
        ongkir_val = format_ke_rupiah(row[8]) if len(row) > 8 and row[8] else "-"
        ket_val = str(row[9] or "-").strip() if len(row) > 9 else "-"
        tujuan = str(row[3] or "")
        if " - " in tujuan:
            tujuan = tujuan.split(" - ")[-1]

        return (
            row[0],
            row[1],
            row[2],
            tujuan,
            row[4],
            format_angka_indonesia(row[5], kosong_jika_nol=True, nilai_kosong="-"),
            format_angka_indonesia(row[6], kosong_jika_nol=True, nilai_kosong="-"),
            format_angka_indonesia(row[7], kosong_jika_nol=True, nilai_kosong="-"),
            ongkir_val,
            ket_val,
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
            kode_cabang = CURRENT_SESSION.get("kode_cabang", "PUSAT")
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

            items_cetak = [self._format_baris_cetak_manifest(row) for row in data]
            if not nama_kapal:
                nama_kapal = db_service.ambil_nama_kapal_manifest(m_id, kode_cabang)
            if not note_manifest:
                note_manifest = db_service.ambil_note_manifest(m_id, kode_cabang)

            truk_cetak = str(truk or "").strip()
            note_manifest = str(note_manifest or "").strip()
            if note_manifest and truk_cetak.upper() == note_manifest.upper():
                truk_cetak = ""

            cetak_manifest_ke_printer(
                {
                    "no_manifest": m_id,
                    "armada": truk_cetak,
                    "note_manifest": note_manifest,
                    "nama_kapal": nama_kapal,
                    "tanggal": self._format_tanggal_cetak(tanggal_manifest),
                    "items": items_cetak,
                },
                self,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Gagal cetak: {exc}")

    def showEvent(self, event):
        super().showEvent(event)


        if self._show_event_pertama:
            self._show_event_pertama = False
            self.perbarui_tanggal_header()
            return

        self.refresh_session_ui()

    def _terapkan_style_form_manifest(self, styles_statis):
        self.panel_kiri.setStyleSheet(styles_statis["panel_kiri"])
        self.panel_kanan.setStyleSheet(styles_statis["panel_kanan"])
        self.lbl_title.setStyleSheet(styles_statis["lbl_title"])
        self.btn_proses.setStyleSheet(styles_statis["btn_proses"])

        for widget in (
            self.txt_jenis_truk_lain,
            self.txt_no_pol,
            self.txt_sopir,
            self.txt_keterangan,
            self.txt_nama_kapal,
            self.txt_note_manifest,
            self.txt_cari_histori,
        ):
            widget.setStyleSheet(styles_statis["style_input"])

        comboboxes = (
            self.cb_filter_wilayah,
            self.cb_jenis_truk,
            self.cb_tahun_filter,
        )
        for combo in comboboxes:
            zoom_helper.terapkan_zoom_widget_standar(combo, 0, "sz_input")

        self.cb_filter_wilayah.setFixedHeight(self.txt_nama_kapal.sizeHint().height())
        self.cb_jenis_truk.setFixedHeight(self.txt_no_pol.sizeHint().height())
        self.cb_tahun_filter.setFixedHeight(self.txt_cari_histori.sizeHint().height())
        self._perbarui_font_placeholder_truk(self.cb_jenis_truk.currentIndex())
        terapkan_popup_bawah_combobox(comboboxes)

        for card in (self.card_rute_manifest, self.card_armada_manifest):
            card.setStyleSheet(styles_statis["card_manifest"])
        for label in (
            self.lbl_input_tujuan,
            self.lbl_input_kapal,
            self.lbl_input_note,
            self.lbl_input_truk,
            self.lbl_input_sopir,
            self.lbl_input_keterangan,
        ):
            label.setStyleSheet(styles_statis["label_input"])

        self.lbl_tanggal_manifest.setStyleSheet(styles_statis["label_header"])
        self.lbl_no_manifest.setStyleSheet(styles_statis["label_header"])
        self.txt_tanggal_manifest.setStyleSheet(styles_statis["txt_tanggal_manifest"])
        self.txt_no_manifest.setStyleSheet(styles_statis["txt_no_manifest"])

    def _terapkan_zoom_tabel_manifest(self, styles_dinamis, font_dinamis, is_dark, z):
        tabel = self.tabel_manifest
        frozen_table = getattr(tabel, "frozen_table", None)
        tabel.setUpdatesEnabled(False)
        if frozen_table is not None:
            frozen_table.setUpdatesEnabled(False)

        try:
            tabel.setStyleSheet(styles_dinamis["style_tabel"])
            update_status_delegate_theme(tabel, is_dark)
            if frozen_table is not None:
                update_status_delegate_theme(frozen_table, is_dark)

            ukuran_pt = ukuran_font_px_ke_pt(font_dinamis["sz_base"])
            font = tabel.font()
            font.setPointSizeF(ukuran_pt)
            tabel.setFont(font)

            header_font = tabel.horizontalHeader().font()
            header_font.setPointSizeF(ukuran_pt)
            tabel.horizontalHeader().setFont(header_font)
            tabel.verticalHeader().setFont(header_font)

            faktor = max(0.68, min(1.0 + (z * 0.08), 1.80))
            tinggi_baris = max(24, int(32 * faktor))
            tabel.verticalHeader().setDefaultSectionSize(tinggi_baris)

            if frozen_table is not None:
                frozen_font = frozen_table.font()
                frozen_font.setPointSizeF(ukuran_pt)
                frozen_table.setFont(frozen_font)
                frozen_table.horizontalHeader().setFont(header_font)
                frozen_table.verticalHeader().setFont(header_font)
                frozen_table.verticalHeader().setDefaultSectionSize(tinggi_baris)

            header = tabel.horizontalHeader()
            status_signal_sebelumnya = header.blockSignals(True)
            self._sedang_menerapkan_zoom = True
            try:
                zoom_helper.skalakan_kolom_tableview(tabel, z)
            finally:
                self._sedang_menerapkan_zoom = False
                header.blockSignals(status_signal_sebelumnya)
        finally:
            if frozen_table is not None:
                frozen_table.setUpdatesEnabled(True)
            tabel.setUpdatesEnabled(True)
            zoom_helper.sinkronkan_frozen_table(tabel, tertunda=True)

    def _terapkan_style_histori_manifest(self, styles_statis, is_dark):
        self.list_histori.setStyleSheet(styles_statis["list_histori"])
        font_histori = self.list_histori.font()
        font_histori.setPointSizeF(
            ukuran_font_px_ke_pt(get_global_font_sizes(0)["sz_base"])
        )
        self.list_histori.setFont(font_histori)
        self._sinkronkan_font_item_histori(is_dark)

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()
        terap_semua_placeholder_dinamis(self, is_dark=is_dark)

        z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        font_dinamis = get_global_font_sizes(z)
        styles_statis = konversi_style_font_ke_point(
            get_manifest_styles(is_dark, self.is_edit_mode, 0)
        )
        styles_dinamis = konversi_style_font_ke_point(
            get_manifest_styles(is_dark, self.is_edit_mode, z)
        )

        self._terapkan_style_form_manifest(styles_statis)
        self._terapkan_zoom_tabel_manifest(
            styles_dinamis,
            font_dinamis,
            is_dark,
            z,
        )
        self._terapkan_style_histori_manifest(styles_statis, is_dark)

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
        if not item or not item.parent():
            return

        menu = QMenu()
        act_print = menu.addAction("🖨 Preview Cetak")
        act_edit = menu.addAction("✏️ Edit Workspace")
        action = menu.exec(self.list_histori.viewport().mapToGlobal(pos))
        data = self._data_dari_item_histori(item)

        if action == act_print:
            self.siapkan_dan_cetak_dari_id(*data)
        elif action == act_edit:
            self.aktifkan_mode_edit(*data)

    def _isi_detail_truk_edit(self, truk_str, note_manifest):
        truk_bersih = str(truk_str or "").strip()
        is_note_only = bool(
            note_manifest
            and truk_bersih.upper() == note_manifest.upper()
        )
        if not truk_bersih or truk_bersih == "-" or is_note_only:
            return

        parts = truk_bersih.split(" - ", 2)
        if len(parts) < 3:
            if not note_manifest:
                self.txt_note_manifest.setText(truk_bersih.upper())
            return

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
            QMessageBox.warning(self, "Peringatan", "Nomor manifest tidak valid.")
            return

        self.is_edit_mode = True
        self.edit_manifest_id = m_id
        self._tanggal_edit_manifest = str(tanggal_manifest or "").strip()
        self._kosongkan_input_manifest()

        kode_cabang = CURRENT_SESSION.get("kode_cabang", "PUSAT")
        nama_kapal = str(nama_kapal or "").strip().upper()
        if not nama_kapal:
            nama_kapal = db_service.ambil_nama_kapal_manifest(m_id, kode_cabang)
        self.txt_nama_kapal.setText(nama_kapal)

        if not note_manifest:
            note_manifest = db_service.ambil_note_manifest(m_id, kode_cabang)
        note_manifest = str(note_manifest or "").strip().upper()
        self.txt_note_manifest.setText(note_manifest)
        self._isi_detail_truk_edit(truk_str, note_manifest)

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
        self._kosongkan_input_manifest()

        self.sesuaikan_tema_lokal()
        self.generate_no_manifest()
        self.load_data_resi_gudang()