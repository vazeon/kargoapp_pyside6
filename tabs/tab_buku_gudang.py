# tabs/tab_buku_gudang.py
import html
from datetime import datetime
from PySide6.QtCore import QDate, QEvent, QSettings, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QCheckBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    QFrame,
)

from config import CURRENT_SESSION, DATA_CLIENT

import services.database_service as db_service

from utils.frozen_table_helper import FrozenTableWidget
from utils import zoom as zoom_helper
from utils.modules.buku_gudang_metrics import (
    BUKU_GUDANG_AUTOCOMPLETE_MAX_VISIBLE_ITEMS,
    BUKU_GUDANG_BILLING_STATUS_BUTTON_SIZE,
    BUKU_GUDANG_COLUMN_WIDTH_MAX,
    BUKU_GUDANG_COLUMN_WIDTH_MIN,
    BUKU_GUDANG_DEFAULT_COLUMN_WIDTHS,
    BUKU_GUDANG_DIALOG_ACTION_GAP,
    BUKU_GUDANG_DIALOG_PENAGIH_MIN_WIDTH,
    BUKU_GUDANG_FALLBACK_COLUMN_WIDTH,
    BUKU_GUDANG_FILTER_ROW_SPACING,
    BUKU_GUDANG_FILTER_SECTION_GAP,
    BUKU_GUDANG_HEADER_CONTROL_HEIGHT,
    BUKU_GUDANG_HEADER_MARGINS,
    BUKU_GUDANG_HEADER_SPACING,
    BUKU_GUDANG_MAIN_MARGINS,
    BUKU_GUDANG_MAIN_SPACING,
    BUKU_GUDANG_MONTH_BUTTON_SIZE,
    BUKU_GUDANG_MONTH_CHECKBOX_MIN_WIDTH,
    BUKU_GUDANG_PRIMARY_ROW_SPACING,
    BUKU_GUDANG_RESET_FILTER_BUTTON_SIZE,
    BUKU_GUDANG_SEARCH_WIDTH,
    BUKU_GUDANG_TABLE_ROW_BASE_HEIGHT,
    BUKU_GUDANG_TABLE_ROW_MIN_HEIGHT,
    BUKU_GUDANG_TABLE_TAB_MARGINS,
    BUKU_GUDANG_YEAR_BUTTON_SIZE,
)
from utils.typography import (
    APPLICATION_NAME,
    ORGANIZATION_NAME,
    get_global_font_sizes,
    konversi_font_qss_ke_point,
    konversi_style_font_ke_point,
    ukuran_font_px_ke_pt,
)
from utils.number_formatters import (
    format_ke_rupiah,
    rupiah_to_int,
    format_angka_indonesia,
    angka_indonesia_to_decimal,
)
from utils.date_ind_format import format_tanggal_ke_ui
from utils.table_helper import buat_tabel_item
from utils.validators import get_decimal_validator, get_integer_validator
from utils.widget_helpers import paksa_kapital_lineedit
from delegates.status_delegate import (
    attach_status_delegate,
    update_status_delegate_theme,
)

from themes.modules.buku_gudang import (
    get_buku_gudang_action_styles,
    get_buku_gudang_menu_style,
    get_buku_gudang_status_colors,
    get_buku_gudang_styles,
    get_dialog_pilih_penagih_styles,
)


NAMA_BULAN = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)


def _get_buku_gudang_v2_status_colors(*, is_dark, status, is_alternate_row):
    """Provider warna status Buku Gudang dari layer themes."""
    return get_buku_gudang_status_colors(
        is_dark=is_dark,
        status=status,
        is_alternate_row=is_alternate_row,
    )


class DialogPilihPenagih(QDialog):
    def __init__(self, nama_pengirim, nama_penerima, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pilih Pihak Tertagih")
        self.setMinimumWidth(BUKU_GUDANG_DIALOG_PENAGIH_MIN_WIDTH)
        self.nama_pengirim = str(nama_pengirim or "").strip()
        self.nama_penerima = str(nama_penerima or "").strip()
        dialog_styles = konversi_style_font_ke_point(get_dialog_pilih_penagih_styles())
        self.setStyleSheet(dialog_styles["dialog"])
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Invoice ini akan ditagihkan kepada:</b>"))
        self.rb_pengirim = QRadioButton(f"Pengirim ({self.nama_pengirim})")
        self.rb_penerima = QRadioButton(f"Penerima ({self.nama_penerima})")
        self.rb_ketiga = QRadioButton("Pihak Ketiga:")
        self.rb_pengirim.setChecked(True)
        self.txt_ketiga = QLineEdit()
        self.txt_ketiga.setPlaceholderText("Ketik nama pihak ketiga...")
        self.txt_ketiga.setEnabled(False)
        self.txt_ketiga.setStyleSheet(dialog_styles["input"])
        self.rb_ketiga.toggled.connect(
            lambda: self.txt_ketiga.setEnabled(self.rb_ketiga.isChecked())
        )
        for widget in (
            self.rb_pengirim,
            self.rb_penerima,
            self.rb_ketiga,
            self.txt_ketiga,
        ):
            layout.addWidget(widget)
        layout.addSpacing(BUKU_GUDANG_DIALOG_ACTION_GAP)
        hbox_btn = QHBoxLayout()
        self.btn_lanjut = QPushButton("Lanjutkan ke Invoice")
        self.btn_lanjut.setStyleSheet(dialog_styles["btn_lanjut"])
        self.btn_batal = QPushButton("Batal")
        self.btn_batal.setStyleSheet(dialog_styles["btn_batal"])
        hbox_btn.addWidget(self.btn_lanjut)
        hbox_btn.addWidget(self.btn_batal)
        layout.addLayout(hbox_btn)
        self.btn_lanjut.clicked.connect(self.validasi_dan_lanjut)
        self.btn_batal.clicked.connect(self.reject)

    def validasi_dan_lanjut(self):
        if self.rb_ketiga.isChecked() and not self.txt_ketiga.text().strip():
            QMessageBox.warning(
                self,
                "Peringatan",
                "Nama Pihak Ketiga tidak boleh kosong!",
            )
            self.txt_ketiga.setFocus()
            return
        self.accept()

    def get_nama_client(self):
        if self.rb_pengirim.isChecked():
            return self.nama_pengirim
        if self.rb_penerima.isChecked():
            return self.nama_penerima
        return self.txt_ketiga.text().strip().upper()


class TabBukuGudang(QWidget):
    KOL_NO = 0
    KOL_RESI = 1
    KOL_MASUK = 2
    KOL_KELUAR = 3
    KOL_STATUS = 4
    KOL_STATUS_RESI = KOL_STATUS
    KOL_STATUS_PENAGIHAN = 5
    KOL_TRUK = 6
    KOL_PENGIRIM = 7
    KOL_KOTA_ASAL = 8
    KOL_PENERIMA = 9
    KOL_KOTA_TUJUAN = 10
    KOL_NAMA_BARANG = 11
    KOL_KOLI = 12
    KOL_BERAT = 13
    KOL_CBM = 14
    KOL_ONGKIR = 15
    KOL_PAYMENT = 16
    KOL_KETERANGAN = 17

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "BukuGudang"
    SETTINGS_KEY_LEBAR = "lebar_kolom_gudang_v3"

    ROLE_NO_RESI = 256  # Qt.ItemDataRole.UserRole
    ROLE_DETAIL_ID = ROLE_NO_RESI + 1
    ROLE_IS_PARENT = ROLE_NO_RESI + 2
    ROLE_URUTAN_DETAIL = ROLE_NO_RESI + 3
    ROLE_REVISION = ROLE_NO_RESI + 4
    ROLE_INVOICE_NO = ROLE_NO_RESI + 5
    ROLE_INVOICE_DATE = ROLE_NO_RESI + 6
    ROLE_INVOICE_STATUS = ROLE_NO_RESI + 7
    ROLE_INVOICE_COUNT = ROLE_NO_RESI + 8
    ROLE_STATUS_HIGHLIGHT = ROLE_NO_RESI + 9

    KOLOM_PENCARIAN = tuple(range(KOL_RESI, KOL_KETERANGAN + 1))
    DEFAULT_LEBAR_KOLOM = BUKU_GUDANG_DEFAULT_COLUMN_WIDTHS

    HEADERS = (
        "NO.", "RESI", "MASUK", "KELUAR", "STATUS RESI", "STATUS PENAGIHAN",
        "TRUK", "PENGIRIM", "KOTA ASAL", "PENERIMA", "KOTA TUJUAN",
        "NAMA BARANG", "KOLI", "BERAT (kg)", "KUBIK (m3)", "ONGKIR (Rp)",
        "PAYMENT", "KETERANGAN",
    )

    KOLOM_NUMERIK = (KOL_KOLI, KOL_BERAT, KOL_CBM, KOL_ONGKIR)
    KOLOM_DESIMAL = (KOL_BERAT, KOL_CBM)
    KOLOM_RATA_KANAN = (KOL_KOLI, KOL_BERAT, KOL_CBM, KOL_ONGKIR)
    KOLOM_TANGGAL = (KOL_MASUK, KOL_KELUAR)
    KOLOM_DB = {
        KOL_PENGIRIM: "pengirim",
        KOL_KOTA_ASAL: "kota_asal",
        KOL_PENERIMA: "penerima",
        KOL_KOTA_TUJUAN: "kota_tujuan",
        KOL_NAMA_BARANG: "nama_barang",
        KOL_KOLI: "koli",
        KOL_BERAT: "berat",
        KOL_CBM: "cbm",
        KOL_ONGKIR: "total_ongkir",
        KOL_PAYMENT: "pembayaran",
        KOL_KETERANGAN: "ket_buku_gudang",
    }

    def __init__(self):
        super().__init__()
        self.tabs_list = []
        self.row_sedang_diedit = -1
        self._show_event_pertama = True
        self._sedang_menerapkan_zoom = False
        self._tabel_lebar_pending = None
        sekarang = datetime.now()
        self._bulan_terpilih = {sekarang.month}
        self._status_penagihan_terpilih = "SEMUA"
        self._filter_bulan_kotor = False
        self._sinkronisasi_checkbox_bulan = False
        self._checkbox_bulan = {}
        self._checkbox_semua_bulan = None

        # Simpan lebar kolom setelah pengguna selesai menyeret header.
        # Debounce mencegah QSettings.sync() dipanggil berkali-kali selama drag.
        self._timer_simpan_lebar = QTimer(self)
        self._timer_simpan_lebar.setSingleShot(True)
        self._timer_simpan_lebar.setInterval(250)
        self._timer_simpan_lebar.timeout.connect(
            self._simpan_lebar_kolom_tertunda,
        )

        self.init_ui()

    def _bangun_header_buku_gudang(self):
        # Header dua tingkat: identitas/aksi utama di atas, filter operasional di bawah.
        # Seluruh signal dan handler lama tetap dipertahankan.
        layout_header = QVBoxLayout()
        layout_header.setContentsMargins(*BUKU_GUDANG_HEADER_MARGINS)
        layout_header.setSpacing(BUKU_GUDANG_HEADER_SPACING)

        baris_utama = QHBoxLayout()
        baris_utama.setSpacing(BUKU_GUDANG_PRIMARY_ROW_SPACING)
        self.lbl_judul = QLabel("Buku Gudang")
        baris_utama.addWidget(self.lbl_judul)
        baris_utama.addStretch()

        self.txt_cari = QLineEdit()
        self.txt_cari.setPlaceholderText("Cari resi, truk, pengirim, barang...")
        self.txt_cari.setFixedWidth(BUKU_GUDANG_SEARCH_WIDTH)
        self.txt_cari.setFixedHeight(BUKU_GUDANG_HEADER_CONTROL_HEIGHT)
        self.txt_cari.textChanged.connect(lambda: paksa_kapital_lineedit(self.txt_cari))
        self.txt_cari.textChanged.connect(self.filter_pencarian_tabel)
        baris_utama.addWidget(self.txt_cari)

        action_styles = konversi_style_font_ke_point(get_buku_gudang_action_styles())
        self.btn_buat_invoice = QPushButton("🧾 Buat Invoice")
        self.btn_buat_invoice.setStyleSheet(action_styles["btn_buat_invoice"])
        self.btn_simpan_inv = QPushButton("Simpan")
        self.btn_simpan_inv.setStyleSheet(action_styles["btn_simpan_inv"])
        self.btn_simpan_inv.setVisible(False)
        self.btn_batal_inv = QPushButton("Batal")
        self.btn_batal_inv.setStyleSheet(action_styles["btn_batal_inv"])
        self.btn_batal_inv.setVisible(False)
        for tombol in (self.btn_buat_invoice, self.btn_simpan_inv, self.btn_batal_inv):
            tombol.setFixedHeight(BUKU_GUDANG_HEADER_CONTROL_HEIGHT)
            baris_utama.addWidget(tombol)
        self.btn_buat_invoice.clicked.connect(self.aktifkan_mode_invoice)
        self.btn_batal_inv.clicked.connect(self.batalkan_mode_invoice)
        self.btn_simpan_inv.clicked.connect(self.proses_simpan_ke_invoice)
        layout_header.addLayout(baris_utama)

        baris_filter = QHBoxLayout()
        baris_filter.setSpacing(BUKU_GUDANG_FILTER_ROW_SPACING)

        self.lbl_periode = QLabel("Periode")
        baris_filter.addWidget(self.lbl_periode)

        tahun_sekarang = datetime.now().year
        self.btn_tahun = QToolButton()
        self.btn_tahun.setText(str(tahun_sekarang))
        self.btn_tahun.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_tahun.setFixedSize(*BUKU_GUDANG_YEAR_BUTTON_SIZE)
        self.menu_tahun = QMenu(self)
        self.setup_menu_tahun(tahun_sekarang)
        self.btn_tahun.setMenu(self.menu_tahun)
        baris_filter.addWidget(self.btn_tahun)

        self.btn_bulan = QToolButton()
        self.btn_bulan.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_bulan.setFixedSize(*BUKU_GUDANG_MONTH_BUTTON_SIZE)
        self.menu_bulan = QMenu(self)
        self.setup_menu_bulan()
        self.btn_bulan.setMenu(self.menu_bulan)
        baris_filter.addWidget(self.btn_bulan)

        baris_filter.addSpacing(BUKU_GUDANG_FILTER_SECTION_GAP)
        self.lbl_status_penagihan_filter = QLabel("Status Tagihan")
        baris_filter.addWidget(self.lbl_status_penagihan_filter)

        self.btn_status_penagihan = QToolButton()
        self.btn_status_penagihan.setText("Semua Tagihan")
        self.btn_status_penagihan.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.btn_status_penagihan.setFixedSize(*BUKU_GUDANG_BILLING_STATUS_BUTTON_SIZE)
        self.menu_status_penagihan = QMenu(self)
        self.setup_menu_status_penagihan()
        self.btn_status_penagihan.setMenu(self.menu_status_penagihan)
        baris_filter.addWidget(self.btn_status_penagihan)

        self.btn_reset_filter = QToolButton()
        self.btn_reset_filter.setText("↺ Reset")
        self.btn_reset_filter.setFixedSize(*BUKU_GUDANG_RESET_FILTER_BUTTON_SIZE)
        self.btn_reset_filter.clicked.connect(self.reset_semua_filter)
        baris_filter.addWidget(self.btn_reset_filter)
        baris_filter.addStretch()

        self._perbarui_label_bulan()
        layout_header.addLayout(baris_filter)
        return layout_header

    def _bangun_tabs_wilayah(self):
        self.tabs_wilayah = QTabWidget()
        provinsi_tujuan = DATA_CLIENT.get(
            "provinsi_tujuan",
            ["PROVINSI A", "PROVINSI B", "PROVINSI C"],
        )
        for wilayah in provinsi_tujuan:
            widget_tabel = self.create_tabel_tab(wilayah)
            self.tabs_list.append(widget_tabel)
            self.tabs_wilayah.addTab(widget_tabel, wilayah.title())

        self.tabs_wilayah.currentChanged.connect(
            lambda _index: self.refresh_session_ui()
        )
        return self.tabs_wilayah

    def init_ui(self):
        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(*BUKU_GUDANG_MAIN_MARGINS)
        layout_utama.setSpacing(BUKU_GUDANG_MAIN_SPACING)
        layout_utama.addLayout(self._bangun_header_buku_gudang())
        layout_utama.addWidget(self._bangun_tabs_wilayah())
        self.refresh_session_ui()
        self.sesuaikan_tema_lokal()

    def aktifkan_mode_invoice(self):
        self.btn_buat_invoice.setVisible(False)
        self.btn_simpan_inv.setVisible(True)
        self.btn_batal_inv.setVisible(True)
        QMessageBox.information(
            self,
            "Mode Invoice",
            "Silakan blok/pilih baris resi yang ingin dijadikan Invoice, lalu klik 'Simpan'.",
        )

    def batalkan_mode_invoice(self):
        self.btn_buat_invoice.setVisible(True)
        self.btn_simpan_inv.setVisible(False)
        self.btn_batal_inv.setVisible(False)
        if self.tabs_wilayah.currentWidget() and hasattr(
            self.tabs_wilayah.currentWidget(),
            'tabel',
        ):
            self.tabs_wilayah.currentWidget().tabel.clearSelection()

    def _ambil_baris_terseleksi_invoice(self, tabel):
        rows = []
        selection_model = tabel.selectionModel()
        if selection_model:
            rows = [idx.row() for idx in selection_model.selectedRows()]

        if not rows:
            rows = [item.row() for item in tabel.selectedItems()]

        return sorted(set(rows))

    def _ambil_text_item(self, tabel, row, col):
        item = tabel.item(row, col)
        return item.text().strip() if item else ""

    def _ambil_tab_widget_dari_tabel(self, tabel):
        """Mencari container tab yang menyimpan atribut wilayah dan filter_data."""
        widget = tabel.parentWidget()
        while widget is not None:
            if hasattr(widget, "wilayah") and hasattr(widget, "filter_data"):
                return widget
            widget = widget.parentWidget()
        return None

    @staticmethod
    def _ambil_text_cell(tabel, row, col):
        widget = tabel.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QLineEdit):
            return widget.text()
        item = tabel.item(row, col)
        return item.text() if item else ""

    def _terapkan_pencarian_ke_tabel(self, tabel):
        keyword = self.txt_cari.text().strip().casefold()
        if not keyword:
            for row in range(tabel.rowCount()):
                tabel.setRowHidden(row, False)
            return

        grup = {}
        for row in range(tabel.rowCount()):
            no_resi = self._no_resi_dari_baris(tabel, row) or f"__ROW_{row}"
            grup.setdefault(no_resi, []).append(row)

        for rows in grup.values():
            cocok = any(
                keyword in self._ambil_text_cell(tabel, row, col).casefold()
                for row in rows
                for col in self.KOLOM_PENCARIAN
                if col < tabel.columnCount()
            )
            for row in rows:
                tabel.setRowHidden(row, not cocok)

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
                hasil.append(min(max(BUKU_GUDANG_COLUMN_WIDTH_MIN, int(width)), BUKU_GUDANG_COLUMN_WIDTH_MAX))
        except (TypeError, ValueError):
            return None
        return hasil

    def _cari_tab_invoice(self):
        win = self.window()
        if not win:
            return None
        tab_invoice = getattr(win, "tab_invoice", None)
        if tab_invoice and hasattr(tab_invoice, "terima_data_baru"):
            return tab_invoice
        for widget in win.findChildren(QWidget):
            if widget.__class__.__name__ == "TabInvoice" and hasattr(
                widget, "terima_data_baru"
            ):
                return widget
        for widget in win.findChildren(QWidget):
            if hasattr(widget, "terima_data_baru") and hasattr(
                widget, "tabel_item_invoice"
            ):
                return widget
        return None

    def _pindah_ke_tab_invoice(self, tab_invoice):
        win = self.window()
        if not win or not tab_invoice:
            return False

        tabs_utama = getattr(win, 'tabs_utama', None)
        if isinstance(tabs_utama, QTabWidget) and tabs_utama.indexOf(tab_invoice) != -1:
            tabs_utama.setCurrentWidget(tab_invoice)
            return True

        for tab_widget in win.findChildren(QTabWidget):
            idx = tab_widget.indexOf(tab_invoice)
            if idx != -1:
                tab_widget.setCurrentIndex(idx)
                return True

        return False

    def _no_resi_dari_baris(self, tabel, row):
        item = tabel.item(row, self.KOL_RESI)
        if item is None:
            return ""
        no_resi = item.data(self.ROLE_NO_RESI)
        if no_resi:
            return str(no_resi).strip()
        teks = item.text().strip()
        return teks if teks and not teks.startswith("↳") else ""

    def _detail_id_dari_baris(self, tabel, row):
        item = tabel.item(row, self.KOL_RESI)
        return item.data(self.ROLE_DETAIL_ID) if item is not None else None

    def _revision_dari_baris(self, tabel, row):
        item = tabel.item(row, self.KOL_RESI)
        if item is None:
            return None
        revision = item.data(self.ROLE_REVISION)
        try:
            return int(revision)
        except (TypeError, ValueError):
            return None

    def _baris_induk_resi(self, tabel, row):
        no_resi = self._no_resi_dari_baris(tabel, row)
        if not no_resi:
            return row
        for indeks in range(tabel.rowCount()):
            item = tabel.item(indeks, self.KOL_RESI)
            if item is None:
                continue
            if (
                str(item.data(self.ROLE_NO_RESI) or "").strip() == no_resi
                and bool(item.data(self.ROLE_IS_PARENT))
            ):
                return indeks
        return row

    def _data_invoice_dari_baris(self, tabel, row):
        no_resi = self._no_resi_dari_baris(tabel, row)
        if not no_resi:
            return None

        parent_row = self._baris_induk_resi(tabel, row)
        detail = db_service.ambil_detail_resi(no_resi)
        if not detail:
            return None

        return {
            "no_resi": no_resi,
            "pengirim": self._ambil_text_item(tabel, parent_row, self.KOL_PENGIRIM),
            "penerima": self._ambil_text_item(tabel, parent_row, self.KOL_PENERIMA),
            "tujuan": self._ambil_text_item(tabel, parent_row, self.KOL_KOTA_TUJUAN),
            "nama_barang": str(detail[8] or ""),
            "koli": str(detail[10] or "0"),
            "berat": str(detail[9] or "0"),
            "kubik": str(detail[11] or "0"),
            "ongkir": str(detail[12] or "0"),
        }

    def _kumpulkan_data_invoice(self, tabel, baris_terseleksi):
        hasil = []
        pengirim_pertama = penerima_pertama = None
        beda_pengirim_dikonfirmasi = False
        resi_sudah_diproses = set()
        for row in baris_terseleksi:
            if tabel.isRowHidden(row):
                continue
            no_resi = self._no_resi_dari_baris(tabel, row)
            if not no_resi or no_resi in resi_sudah_diproses:
                continue
            resi_sudah_diproses.add(no_resi)
            data = self._data_invoice_dari_baris(tabel, row)
            if data is None:
                continue
            if not pengirim_pertama:
                pengirim_pertama = data["pengirim"]
                penerima_pertama = data["penerima"]
            elif data["pengirim"] != pengirim_pertama and not beda_pengirim_dikonfirmasi:
                jawaban = QMessageBox.question(
                    self,
                    "Konfirmasi",
                    "Resi yang dipilih memiliki nama PENGIRIM yang berbeda-beda.\n"
                    "Yakin ingin menggabungkannya ke dalam 1 Invoice?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if jawaban == QMessageBox.StandardButton.No:
                    return None
                beda_pengirim_dikonfirmasi = True
            hasil.append({k: v for k, v in data.items() if k != "pengirim"})
        return hasil, pengirim_pertama, penerima_pertama

    def _context_invoice_terpilih(self):
        current_tab = self.tabs_wilayah.currentWidget()
        if not current_tab or not hasattr(current_tab, "tabel"):
            QMessageBox.warning(self, "Peringatan", "Tabel Buku Gudang tidak ditemukan.")
            return None

        tabel = current_tab.tabel
        baris = self._ambil_baris_terseleksi_invoice(tabel)
        if not baris:
            QMessageBox.warning(self, "Peringatan", "Anda belum memilih resi satupun!")
            return None

        kumpulan = self._kumpulkan_data_invoice(tabel, baris)
        if kumpulan is None:
            return None

        list_resi_data, pengirim, penerima = kumpulan
        if not list_resi_data:
            QMessageBox.warning(
                self, "Peringatan", "Data resi yang dipilih tidak valid atau kosong."
            )
            return None
        return list_resi_data, pengirim, penerima


    def proses_simpan_ke_invoice(self):
        context = self._context_invoice_terpilih()
        if context is None:
            return

        list_resi_data, pengirim, penerima = context
        dialog = DialogPilihPenagih(pengirim, penerima, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        tab_invoice = self._cari_tab_invoice()
        if not tab_invoice:
            QMessageBox.critical(
                self,
                "Tab Invoice Tidak Ditemukan",
                "Data berhasil dibaca dari Buku Gudang, tetapi widget TabInvoice tidak ditemukan.\n"
                "Pastikan tab invoice sudah dibuat di MainWindow dan instance-nya tidak dibuat ulang.",
            )
            return

        tab_invoice.terima_data_baru(dialog.get_nama_client(), list_resi_data)
        if not self._pindah_ke_tab_invoice(tab_invoice):
            QMessageBox.information(
                self,
                "Data Invoice Siap",
                "Data sudah dikirim ke draft invoice, tetapi aplikasi tidak menemukan "
                "QTabWidget utama untuk berpindah otomatis.",
            )
        self.batalkan_mode_invoice()

    def _pasang_status_delegate(self, tabel, is_dark):
        for target in (tabel, getattr(tabel, "frozen_table", None)):
            if target is not None:
                attach_status_delegate(
                    target,
                    status_column=self.KOL_STATUS_RESI,
                    color_provider=_get_buku_gudang_v2_status_colors,
                    is_dark=is_dark,
                    status_role=self.ROLE_STATUS_HIGHLIGHT,
                )

    def _konfigurasi_tabel_gudang(self, tabel):
        tabel.setColumnCount(len(self.HEADERS))
        tabel.setHorizontalHeaderLabels(self.HEADERS)
        tabel.verticalHeader().setVisible(False)
        self.load_lebar_kolom(tabel)

        header = tabel.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(
            lambda pos, t=tabel: self.show_header_menu(pos, t)
        )
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)
        header.sectionResized.connect(
            lambda _i, _old, _new, t=tabel: self.jadwalkan_simpan_lebar_kolom(t)
        )

        # Seluruh cell Buku Gudang selalu satu baris. Jika kolom terlalu sempit,
        # Qt mengelide teks ke kanan (…) dan OverflowTooltipDelegate menampilkan
        # teks penuh hanya saat memang terpotong. Terapkan juga ke frozen view.
        for target in (tabel, getattr(tabel, "frozen_table", None)):
            if target is None:
                continue
            target.setWordWrap(False)
            target.setTextElideMode(Qt.TextElideMode.ElideRight)

        tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabel.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tabel.setAlternatingRowColors(True)
        tabel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tabel.customContextMenuRequested.connect(
            lambda pos, t=tabel: self.show_cell_context_menu(pos, t)
        )
        tabel.itemSelectionChanged.connect(
            lambda t=tabel: self._sinkronkan_selection_label_status_penagihan(t)
        )

    def create_tabel_tab(self, wilayah):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(*BUKU_GUDANG_TABLE_TAB_MARGINS)

        tabel = FrozenTableWidget(frozen_cols=2)
        win = self.window()
        is_dark = bool(
            win and hasattr(win, "current_theme") and win.current_theme == "dark"
        )
        self._pasang_status_delegate(tabel, is_dark)
        self._konfigurasi_tabel_gudang(tabel)

        layout.addWidget(tabel)
        widget.tabel = tabel
        widget.wilayah = wilayah
        widget.filter_data = {}
        return widget

    def showEvent(self, event):
        super().showEvent(event)

        if self._show_event_pertama:
            self._show_event_pertama = False
            return

        self.refresh_session_ui()

    def eventFilter(self, obj, event):
        if isinstance(obj, QLabel) and bool(obj.property("billing_status_label")):
            if event.type() == QEvent.Type.ToolTip:
                full_text = str(obj.property("billing_full_text") or "").strip()
                available = max(0, obj.contentsRect().width())
                terpotong = bool(
                    full_text
                    and full_text != "-"
                    and obj.sizeHint().width() > available
                )
                if terpotong:
                    QToolTip.showText(event.globalPos(), full_text, obj)
                    return True
                QToolTip.hideText()
                event.ignore()
                return False

        if isinstance(obj, (QLineEdit, QComboBox)):
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                if getattr(self, 'row_sedang_diedit', -1) != -1:
                    self.refresh_session_ui()
                    return True
        if isinstance(obj, QLineEdit):
            is_numeric = getattr(obj, 'is_numeric_col', False)
            if event.type() == QEvent.Type.FocusIn:
                if is_numeric and obj.text().strip() == "-":
                    obj.setText("")
            elif event.type() == QEvent.Type.FocusOut:
                if is_numeric and obj.text().strip() == "":
                    obj.setText("-")
        return super().eventFilter(obj, event)

    def _tema_gelap_aktif(self):
        """Mengambil tema aktif tanpa bergantung pada kode warna stylesheet."""
        window = self.window()
        tema_window = str(
            getattr(window, "current_theme", "") or ""
        ).strip().lower()

        if tema_window in {"light", "dark"}:
            return tema_window == "dark"

        settings_ui = QSettings(
            ORGANIZATION_NAME,
            APPLICATION_NAME,
        )
        tema_tersimpan = str(
            settings_ui.value("theme", "light") or "light"
        ).strip().lower()
        return tema_tersimpan == "dark"

    @staticmethod
    def _skalakan_kolom_tabel(tabel, zoom):
        """Menskalakan kolom melalui API publik utils.zoom."""
        zoom_helper.skalakan_kolom_tableview(tabel, zoom)

    def _sinkronkan_editor_inline(self, tabel):
        """Memperbarui editor baris aktif agar mengikuti tema dan zoom terbaru."""
        row = getattr(self, "row_sedang_diedit", -1)
        if row < 0 or row >= tabel.rowCount():
            return

        for column in range(self.KOL_PENGIRIM, self.KOL_KETERANGAN + 1):
            editor = tabel.cellWidget(row, column)
            if isinstance(editor, QLineEdit):
                editor.setStyleSheet(self.inline_editor_style)

    @staticmethod
    def _terapkan_font_point(widget, ukuran_px):
        """Menerapkan font point ekuivalen dari token logical-pixel lama."""
        if widget is None:
            return

        font = widget.font()
        ukuran_pt = ukuran_font_px_ke_pt(ukuran_px)
        if abs(font.pointSizeF() - ukuran_pt) < 0.01:
            return

        font.setPointSizeF(ukuran_pt)
        widget.setFont(font)

    def _buat_style_buku_gudang(self, is_dark, zoom):
        font = get_global_font_sizes(zoom)
        styles = konversi_style_font_ke_point(
            get_buku_gudang_styles(
                is_dark=is_dark,
                sz_base=font["sz_base"],
                sz_input=font["sz_input"],
                sz_title=font["sz_title"],
            )
        )
        return font, styles

    def _terapkan_tema_ke_tabel(self, tabel, is_dark, z, styles, ukuran_font, tinggi_baris):
        frozen = getattr(tabel, "frozen_table", None)
        tabel.setUpdatesEnabled(False)
        if frozen is not None:
            frozen.setUpdatesEnabled(False)

        try:
            tabel.setStyleSheet(styles["tabel"] + "\n" + self._tooltip_qss(is_dark))
            for target in (tabel, frozen):
                if target is None:
                    continue
                update_status_delegate_theme(target, is_dark)
                self._terapkan_font_point(target, ukuran_font)
                self._terapkan_font_point(target.horizontalHeader(), ukuran_font)
                self._terapkan_font_point(target.verticalHeader(), ukuran_font)
                target.verticalHeader().setDefaultSectionSize(tinggi_baris)

            self._sinkronkan_editor_inline(tabel)
            self._terapkan_tema_label_status_penagihan(
                tabel,
                is_dark,
                ukuran_font,
            )
            header = tabel.horizontalHeader()
            status_signal = header.blockSignals(True)
            self._sedang_menerapkan_zoom = True
            try:
                self._skalakan_kolom_tabel(tabel, z)
            finally:
                self._sedang_menerapkan_zoom = False
                header.blockSignals(status_signal)
        finally:
            if frozen is not None:
                frozen.setUpdatesEnabled(True)
            tabel.setUpdatesEnabled(True)
            zoom_helper.sinkronkan_frozen_table(tabel, tertunda=True)

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()
        z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        _, styles_statis = self._buat_style_buku_gudang(is_dark, 0)
        font_dinamis, styles_dinamis = self._buat_style_buku_gudang(is_dark, z)
        self.inline_editor_style = styles_dinamis["inline_editor"]

        self.lbl_judul.setStyleSheet(styles_statis["lbl_judul"])
        for label_filter in (
            self.lbl_periode,
            self.lbl_status_penagihan_filter,
        ):
            label_filter.setStyleSheet(styles_statis["lbl_filter"])
        for tombol_filter in (
            self.btn_tahun,
            self.btn_bulan,
            self.btn_status_penagihan,
        ):
            tombol_filter.setStyleSheet(styles_statis["btn_tahun"])
        self.btn_reset_filter.setStyleSheet(styles_statis["btn_reset_filter"])
        self.txt_cari.setStyleSheet(styles_statis["txt_cari"])

        faktor = zoom_helper.dapatkan_faktor_geometri(z)
        tinggi_baris = max(BUKU_GUDANG_TABLE_ROW_MIN_HEIGHT, round(BUKU_GUDANG_TABLE_ROW_BASE_HEIGHT * faktor))
        for widget in self.tabs_list:
            tabel = getattr(widget, "tabel", None)
            if tabel is not None:
                self._terapkan_tema_ke_tabel(
                    tabel,
                    is_dark,
                    z,
                    styles_dinamis,
                    font_dinamis["sz_base"],
                    tinggi_baris,
                )

    def setup_menu_tahun(self, tahun_sekarang):
        self.menu_tahun.clear()
        ukuran_menu_tahun = max(10, get_global_font_sizes(0)["sz_input"] - 1)
        style_menu = konversi_font_qss_ke_point(
            get_buku_gudang_menu_style(ukuran_menu_tahun)
        )
        self.menu_tahun.setStyleSheet(style_menu)
        for i in range(3):
            thn = str(tahun_sekarang - i)
            self.menu_tahun.addAction(thn).triggered.connect(
                lambda checked, t=thn: self.ubah_tahun(t)
            )
        self.menu_tahun.addSeparator()
        submenu_lainnya = self.menu_tahun.addMenu("Lainnya...")
        submenu_lainnya.setStyleSheet(style_menu)
        for i in range(3, 8):
            thn = str(tahun_sekarang - i)
            submenu_lainnya.addAction(thn).triggered.connect(
                lambda checked, t=thn: self.ubah_tahun(t)
            )

    def ubah_tahun(self, tahun_pilihan):
        self.btn_tahun.setText(tahun_pilihan)
        self.refresh_session_ui()

    def _style_menu_filter_periode(self):
        ukuran = max(10, get_global_font_sizes(0)["sz_input"] - 1)
        return konversi_font_qss_ke_point(get_buku_gudang_menu_style(ukuran))

    def _buat_checkbox_menu_bulan(self, label):
        checkbox = QCheckBox(label)
        checkbox.setMinimumWidth(BUKU_GUDANG_MONTH_CHECKBOX_MIN_WIDTH)
        checkbox.setStyleSheet("QCheckBox { padding: 4px 8px; }")
        action = QWidgetAction(self.menu_bulan)
        action.setDefaultWidget(checkbox)
        self.menu_bulan.addAction(action)
        return checkbox

    def setup_menu_bulan(self):
        self.menu_bulan.clear()
        self.menu_bulan.setStyleSheet(self._style_menu_filter_periode())
        self._checkbox_bulan = {}

        self._checkbox_semua_bulan = self._buat_checkbox_menu_bulan("Semua Bulan")
        self._checkbox_semua_bulan.toggled.connect(
            self._on_checkbox_semua_bulan_changed
        )
        self.menu_bulan.addSeparator()

        for nomor, nama in enumerate(NAMA_BULAN, start=1):
            checkbox = self._buat_checkbox_menu_bulan(nama)
            checkbox.toggled.connect(
                lambda checked, n=nomor: self._on_checkbox_bulan_changed(n, checked)
            )
            self._checkbox_bulan[nomor] = checkbox

        self.menu_bulan.aboutToHide.connect(self._terapkan_perubahan_filter_bulan)
        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()

    def _sinkronkan_checkbox_bulan(self):
        if not self._checkbox_bulan:
            return
        pilihan = set(self._bulan_terpilih or ())
        self._sinkronisasi_checkbox_bulan = True
        try:
            if self._checkbox_semua_bulan is not None:
                self._checkbox_semua_bulan.setChecked(len(pilihan) == 12)
            for nomor, checkbox in self._checkbox_bulan.items():
                checkbox.setChecked(nomor in pilihan)
        finally:
            self._sinkronisasi_checkbox_bulan = False

    def _perbarui_label_bulan(self):
        pilihan = sorted(set(self._bulan_terpilih or ()))
        if len(pilihan) == 12:
            label = "Semua Bulan"
        elif len(pilihan) == 1:
            label = NAMA_BULAN[pilihan[0] - 1]
        else:
            label = f"{len(pilihan)} Bulan"

        if hasattr(self, "btn_bulan"):
            self.btn_bulan.setText(label)
            daftar = ", ".join(NAMA_BULAN[nomor - 1] for nomor in pilihan)
            self.btn_bulan.setToolTip(
                f"Bulan terpilih: {daftar}" if daftar else "Tidak ada bulan terpilih"
            )

    def _on_checkbox_semua_bulan_changed(self, checked):
        if self._sinkronisasi_checkbox_bulan:
            return
        self._bulan_terpilih = (
            set(range(1, 13))
            if checked
            else {datetime.now().month}
        )
        self._filter_bulan_kotor = True
        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()

    def _on_checkbox_bulan_changed(self, nomor, checked):
        if self._sinkronisasi_checkbox_bulan:
            return

        pilihan = set(self._bulan_terpilih or ())
        if checked:
            pilihan.add(int(nomor))
        else:
            pilihan.discard(int(nomor))

        # Buku Gudang tidak memiliki kondisi "tanpa bulan". Jika pengguna
        # menghapus pilihan terakhir, pertahankan bulan tersebut.
        if not pilihan:
            pilihan.add(int(nomor))

        self._bulan_terpilih = pilihan
        self._filter_bulan_kotor = True
        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()

    def _terapkan_perubahan_filter_bulan(self):
        if not self._filter_bulan_kotor:
            return
        self._filter_bulan_kotor = False
        self.refresh_session_ui()

    def ubah_bulan(self, bulan):
        if bulan is None:
            pilihan = set(range(1, 13))
        elif isinstance(bulan, (list, tuple, set, frozenset)):
            pilihan = {
                int(nilai)
                for nilai in bulan
                if str(nilai).strip().isdigit() and 1 <= int(nilai) <= 12
            }
        else:
            try:
                nomor = int(bulan)
            except (TypeError, ValueError):
                nomor = 0
            pilihan = {nomor} if 1 <= nomor <= 12 else set()

        if not pilihan:
            pilihan = {datetime.now().month}

        self._bulan_terpilih = pilihan
        self._filter_bulan_kotor = False
        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()
        self.refresh_session_ui()

    def setup_menu_status_penagihan(self):
        self.menu_status_penagihan.clear()
        self.menu_status_penagihan.setStyleSheet(self._style_menu_filter_periode())
        pilihan = (
            ("Semua Tagihan", "SEMUA"),
            ("Belum Invoice", "BELUM INVOICE"),
            ("Belum Lunas", "BELUM LUNAS"),
            ("Lunas", "LUNAS"),
            ("Macet", "MACET"),
        )
        for label, nilai in pilihan:
            self.menu_status_penagihan.addAction(label).triggered.connect(
                lambda _checked=False, l=label, n=nilai: self.ubah_status_penagihan(l, n)
            )

    def ubah_status_penagihan(self, label, nilai):
        self._status_penagihan_terpilih = str(nilai or "SEMUA").strip().upper()
        self.btn_status_penagihan.setText(str(label or "Semua Tagihan"))
        self.refresh_session_ui()

    def reset_semua_filter(self):
        sekarang = datetime.now()
        self.btn_tahun.setText(str(sekarang.year))
        self._bulan_terpilih = {sekarang.month}
        self._status_penagihan_terpilih = "SEMUA"
        self._filter_bulan_kotor = False
        self.btn_status_penagihan.setText("Semua Tagihan")
        self._sinkronkan_checkbox_bulan()
        self._perbarui_label_bulan()

        # Filter kolom dapat berbeda per wilayah; reset seluruh tab agar tombol
        # Reset Filter benar-benar mengembalikan Buku Gudang ke kondisi awal.
        for tab_widget in self.tabs_list:
            if hasattr(tab_widget, "filter_data"):
                tab_widget.filter_data.clear()

        if self.txt_cari.text():
            status_signal = self.txt_cari.blockSignals(True)
            try:
                self.txt_cari.clear()
            finally:
                self.txt_cari.blockSignals(status_signal)

        self.refresh_session_ui()

    @staticmethod
    def _kode_cabang_aktif():
        return CURRENT_SESSION.get("kode_cabang", "PUSAT")


    def _buat_menu_buku_gudang(self):
        menu = QMenu()
        ukuran = get_global_font_sizes(0)["sz_input"]
        menu.setStyleSheet(
            konversi_font_qss_ke_point(get_buku_gudang_menu_style(ukuran))
        )
        return menu

    def get_editor_type(self, col_index):
        if col_index in (self.KOL_MASUK, self.KOL_KELUAR):
            return "date"
        if col_index == self.KOL_STATUS:
            return "status"
        if col_index == self.KOL_STATUS_PENAGIHAN:
            return "billing_status"
        if col_index == self.KOL_PAYMENT:
            return "payment"
        return "text"

    def filter_pencarian_tabel(self):
        current_tab = self.tabs_wilayah.currentWidget()
        if not current_tab or not hasattr(current_tab, "tabel"):
            return
        self._terapkan_pencarian_ke_tabel(current_tab.tabel)

    def _buat_editor_filter(self, editor_type):
        if editor_type == "date":
            editor = QDateEdit()
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
            editor.setDate(QDate.currentDate())
            return editor
        if editor_type == "status":
            editor = QComboBox()
            editor.addItems(["", "DI GUDANG", "PERJALANAN", "SELESAI"])
            return editor
        if editor_type == "billing_status":
            editor = QComboBox()
            editor.addItems(["", "BELUM INVOICE", "BELUM LUNAS", "LUNAS", "MACET"])
            return editor
        if editor_type == "payment":
            editor = QComboBox()
            editor.addItems(["TF / INVOICE", "CASH"])
            return editor
        return QLineEdit()

    def show_header_menu(self, pos, tabel):
        col = tabel.horizontalHeader().logicalIndexAt(pos)
        if col == self.KOL_NO:
            return

        menu = self._buat_menu_buku_gudang()
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel(f"Filter {tabel.horizontalHeaderItem(col).text()}:"))
        editor = self._buat_editor_filter(self.get_editor_type(col))
        layout.addWidget(editor)

        action = QWidgetAction(menu)
        action.setDefaultWidget(container)
        menu.addAction(action)
        menu.addSeparator()
        menu.addAction(
            "Pasang Filter",
            lambda: self.apply_filter(tabel, col, editor, menu),
        )
        menu.addAction("Hapus Filter", lambda: self.reset_filter(tabel, col, menu))
        menu.exec(tabel.viewport().mapToGlobal(pos))

    def apply_filter(self, tabel, col, editor, menu):
        tab_widget = self._ambil_tab_widget_dari_tabel(tabel)
        if tab_widget is None:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Container tab Buku Gudang tidak ditemukan.",
            )
            menu.close()
            return

        val = editor.date().toString("yyyy-MM-dd") if isinstance(
            editor,
            QDateEdit,
        ) else editor.currentText() if isinstance(
            editor,
            QComboBox,
        ) else editor.text().strip()

        if val:
            tab_widget.filter_data[col] = val
        else:
            tab_widget.filter_data.pop(col, None)

        self.load_data(tab_widget)
        self._terapkan_pencarian_ke_tabel(tabel)
        menu.close()

    def reset_filter(self, tabel, col, menu):
        tab_widget = self._ambil_tab_widget_dari_tabel(tabel)
        if tab_widget is not None:
            tab_widget.filter_data.pop(col, None)
            self.load_data(tab_widget)
            self._terapkan_pencarian_ke_tabel(tabel)
        menu.close()

    def _jumlah_resi_context(self, tabel, row):
        baris_awal = {item.row() for item in tabel.selectedItems()}
        if row not in baris_awal:
            tabel.selectRow(row)

        resi = {
            self._no_resi_dari_baris(tabel, baris)
            for baris in {item.row() for item in tabel.selectedItems()}
            if self._no_resi_dari_baris(tabel, baris)
        }
        return len(resi)

    def _buat_action_context(self, menu, item, row, jumlah_resi):
        mode_normal = self.row_sedang_diedit == -1
        if jumlah_resi > 1:
            return (
                menu.addAction(f"🧾 Buat Invoice Gabungan ({jumlah_resi} Resi)")
                if mode_normal else None,
                None,
                None,
                None,
                menu.addAction("✅ Tandai 'SELESAI' Massal") if mode_normal else None,
            )

        return (
            menu.addAction("🧾 Buat Invoice dari Resi Ini") if mode_normal else None,
            menu.addAction("✏️ Edit Baris Ini") if mode_normal else None,
            menu.addAction("💾 Simpan Perubahan") if self.row_sedang_diedit == row else None,
            menu.addAction("❌ Batalkan Edit") if self.row_sedang_diedit == row else None,
            menu.addAction("✅ Tandai 'SELESAI'")
            if item.column() == self.KOL_STATUS and mode_normal else None,
        )


    def _actions_status_penagihan(self, menu, item):
        if item is None or item.column() != self.KOL_STATUS_PENAGIHAN:
            return {}
        no_invoice = str(item.data(self.ROLE_INVOICE_NO) or "").strip().upper()
        if not no_invoice:
            return {}

        status = str(item.data(self.ROLE_INVOICE_STATUS) or "").strip().upper()
        menu.addSeparator()
        action_lunas = menu.addAction("✓ Tandai LUNAS")
        action_macet = menu.addAction("⚠ Tandai MACET")
        action_reset = menu.addAction("↺ Kembalikan ke Belum Lunas")
        action_lunas.setEnabled(status != "LUNAS")
        action_macet.setEnabled(status != "MACET")
        action_reset.setEnabled(status in {"LUNAS", "MACET"})
        return {
            action_lunas: (no_invoice, "LUNAS"),
            action_macet: (no_invoice, "MACET"),
            action_reset: (no_invoice, "BELUM LUNAS"),
        }

    def _konfirmasi_status_penagihan(self, no_invoice, status_baru):
        if status_baru == "LUNAS":
            pesan = (
                f"Tandai Invoice {no_invoice} sebagai LUNAS?\n\n"
                "Seluruh Resi aktif dalam Invoice ini akan otomatis ditandai SELESAI."
            )
        elif status_baru == "MACET":
            pesan = (
                f"Tandai Invoice {no_invoice} sebagai MACET?\n\n"
                "Status Resi tidak akan diubah dan highlight merah akan menjadi prioritas."
            )
        else:
            pesan = (
                f"Kembalikan Invoice {no_invoice} ke BELUM LUNAS?\n\n"
                "Status Resi yang sudah SELESAI tidak akan dibatalkan otomatis."
            )
        jawaban = QMessageBox.question(
            self,
            "Konfirmasi Status Penagihan",
            pesan,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return jawaban == QMessageBox.StandardButton.Yes

    def ubah_status_penagihan_invoice(self, no_invoice, status_baru):
        invoice = str(no_invoice or "").strip().upper()
        status = str(status_baru or "").strip().upper()
        if not invoice or not self._konfirmasi_status_penagihan(invoice, status):
            return False
        try:
            sukses, pesan = db_service.ubah_status_penagihan_invoice(
                invoice, status, self._kode_cabang_aktif()
            )
            if not sukses:
                QMessageBox.warning(
                    self, "Status Penagihan", pesan or "Status penagihan gagal diperbarui."
                )
                return False
            self.refresh_session_ui()
            QMessageBox.information(
                self, "Status Penagihan", pesan or f"Invoice {invoice} diperbarui."
            )
            return True
        except Exception as error:
            QMessageBox.critical(
                self, "Error", f"Gagal mengubah status penagihan:\n{error}"
            )
            self.refresh_session_ui()
            return False

    def show_cell_context_menu(self, pos, tabel):
        item = tabel.itemAt(pos)
        if not item:
            return

        row = item.row()
        menu = self._buat_menu_buku_gudang()
        actions_penagihan = self._actions_status_penagihan(menu, item)
        actions = self._buat_action_context(
            menu, item, row, self._jumlah_resi_context(tabel, row)
        )
        action = menu.exec(tabel.viewport().mapToGlobal(pos))
        if action in actions_penagihan:
            no_invoice, status_baru = actions_penagihan[action]
            self.ubah_status_penagihan_invoice(no_invoice, status_baru)
            return

        buat_invoice, edit, simpan, batal, selesai = actions
        if action == edit:
            self.aktifkan_mode_edit_baris(tabel, row)
        elif action == simpan:
            self.eksekusi_simpan_baris_ke_db(tabel, row)
        elif action == batal:
            self.refresh_session_ui()
        elif action == selesai:
            self.tandai_selesai_massal(tabel)
        elif action == buat_invoice:
            self.proses_simpan_ke_invoice()

    def _pasang_validator_editor_inline(self, editor, col):
        if col == self.KOL_KOLI:
            editor.setValidator(
                get_integer_validator(parent=editor, minimum=0, maximum=999_999)
            )
        elif col == self.KOL_ONGKIR:
            editor.setValidator(
                get_integer_validator(parent=editor, minimum=0, maximum=2_147_483_647)
            )
        elif col in self.KOLOM_DESIMAL:
            editor.setValidator(
                get_decimal_validator(
                    parent=editor,
                    decimals=2,
                    minimum=0.0,
                    maximum=999_999_999.99,
                )
            )
        else:
            editor.textChanged.connect(
                lambda _, le=editor: paksa_kapital_lineedit(le)
            )

    def _ambil_autocomplete_nama_buku_gudang(self):
        """Mengambil suggestion nama master tanpa mengubah field Resi lainnya."""
        try:
            pengirim, penerima = db_service.ambil_data_autocomplete(
                self._kode_cabang_aktif()
            )
        except Exception:
            return [], []

        def normalisasi(data):
            return sorted({
                str(item).strip().upper()
                for item in (data or [])
                if str(item).strip()
            })

        return normalisasi(pengirim), normalisasi(penerima)

    @staticmethod
    def _pasang_autocomplete_nama(editor, daftar_nama):
        """Autocomplete hanya memilih nama; tidak menjalankan autofill profil."""
        if not isinstance(editor, QLineEdit) or not daftar_nama:
            return

        completer = QCompleter(daftar_nama, editor)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(BUKU_GUDANG_AUTOCOMPLETE_MAX_VISIBLE_ITEMS)
        editor.setCompleter(completer)
        editor.textEdited.connect(
            lambda text, c=completer: c.complete() if str(text).strip() else None
        )

    def _buat_editor_inline(self, tabel, row, col, teks_asal):
        if col == self.KOL_PAYMENT:
            editor = QComboBox()
            editor.addItems(["", "TF / INVOICE", "CASH"])
            editor.setCurrentText(teks_asal)
            editor.activated.connect(lambda: self.eksekusi_simpan_baris_ke_db(tabel, row))
        else:
            editor = QLineEdit()
            editor.is_numeric_col = col in self.KOLOM_NUMERIK
            teks = teks_asal.strip()
            editor.setText("" if editor.is_numeric_col and teks == "-" else (
                teks.replace(".", "") if editor.is_numeric_col else teks
            ))
            editor.setStyleSheet(getattr(self, "inline_editor_style", ""))
            self._pasang_validator_editor_inline(editor, col)
            editor.returnPressed.connect(lambda: self.eksekusi_simpan_baris_ke_db(tabel, row))

        editor.installEventFilter(self)
        return editor

    def aktifkan_mode_edit_baris(self, tabel, row):
        self.row_sedang_diedit = row
        item_resi = tabel.item(row, self.KOL_RESI)
        is_parent = bool(item_resi.data(self.ROLE_IS_PARENT)) if item_resi else True
        pengirim_autocomplete, penerima_autocomplete = (
            self._ambil_autocomplete_nama_buku_gudang()
            if is_parent
            else ([], [])
        )
        kolom_edit = (
            range(self.KOL_PENGIRIM, self.KOL_KETERANGAN + 1)
            if is_parent
            else range(self.KOL_NAMA_BARANG, self.KOL_CBM + 1)
        )
        for col in kolom_edit:
            item = tabel.item(row, col)
            editor = self._buat_editor_inline(
                tabel, row, col, item.text() if item else ""
            )
            if col == self.KOL_PENGIRIM:
                self._pasang_autocomplete_nama(editor, pengirim_autocomplete)
            elif col == self.KOL_PENERIMA:
                self._pasang_autocomplete_nama(editor, penerima_autocomplete)
            tabel.setCellWidget(row, col, editor)

        kolom_fokus = self.KOL_PENGIRIM if is_parent else self.KOL_NAMA_BARANG
        editor_awal = tabel.cellWidget(row, kolom_fokus)
        if editor_awal:
            editor_awal.setFocus()

    @staticmethod
    def _format_tanggal_status_penagihan(value):
        teks = str(value or "").strip()
        if not teks:
            return ""
        tanggal = teks[:10]
        try:
            return format_tanggal_ke_ui(tanggal)
        except Exception:
            return tanggal

    def _teks_status_penagihan(self, no_invoice, status, tanggal):
        invoice = str(no_invoice or "").strip().upper()
        if not invoice:
            return "-"
        status_norm = str(status or "").strip().upper()
        prefix = f"{status_norm} • " if status_norm in {"LUNAS", "MACET"} else ""
        tanggal_ui = self._format_tanggal_status_penagihan(tanggal)
        suffix = f" • {tanggal_ui}" if tanggal_ui else ""
        return f"{prefix}{invoice}{suffix}"

    @staticmethod
    def _tooltip_qss(is_dark):
        if is_dark:
            return (
                "QToolTip { color: #F2F2F2; background-color: #252525; "
                "border: 1px solid #555555; padding: 5px; }"
            )
        return (
            "QToolTip { color: #202124; background-color: #FFFFFF; "
            "border: 1px solid #C9CDD2; padding: 5px; }"
        )

    def _render_label_status_penagihan(self, label, is_dark):
        invoice = str(label.property("billing_invoice") or "").strip().upper()
        status = str(label.property("billing_status") or "").strip().upper()
        tanggal = str(label.property("billing_date") or "").strip()
        full_text = self._teks_status_penagihan(invoice, status, tanggal)
        label.setProperty("billing_full_text", full_text)

        selected = bool(label.property("billing_selected"))

        # QLabel rich-text tidak otomatis mewarisi foreground dari delegate
        # tabel. Saat row terseleksi, seluruh teks dibuat putih agar mengikuti
        # selection appearance tabel. Link tetap dibedakan oleh underline.
        if selected:
            warna_teks = "#FFFFFF"
            warna_link = "#FFFFFF"
        else:
            highlight_state = str(
                label.property("billing_highlight_state") or ""
            ).strip().upper()
            row_index = int(label.property("billing_row_index") or 0)
            _background, foreground = _get_buku_gudang_v2_status_colors(
                is_dark=is_dark,
                status=highlight_state,
                is_alternate_row=bool(row_index % 2),
            )
            if hasattr(foreground, "name"):
                warna_teks = foreground.name()
            else:
                warna_teks = str(
                    foreground or ("#F2F2F2" if is_dark else "#202124")
                )

            warna_link = "#B7A9FF" if is_dark else "#5B4BEA"

        label.setStyleSheet(
            "QLabel { background: transparent; padding: 0 4px; }"
            + self._tooltip_qss(is_dark)
        )

        bagian = []
        if status in {"LUNAS", "MACET"}:
            bagian.append(
                f'<span style="color:{warna_teks}; font-weight:400;">'
                f'{html.escape(status)}</span>'
                f'<span style="color:{warna_teks};"> &nbsp;•&nbsp; </span>'
            )

        bagian.append(
            f'<a href="{html.escape(invoice, quote=True)}" '
            f'style="color:{warna_link}; text-decoration:underline;">'
            f'{html.escape(invoice)}</a>'
        )

        tanggal_ui = self._format_tanggal_status_penagihan(tanggal)
        if tanggal_ui:
            bagian.append(
                f'<span style="color:{warna_teks};"> &nbsp;•&nbsp; '
                f'{html.escape(tanggal_ui)}</span>'
            )
        label.setText("".join(bagian))

    def _buat_label_status_penagihan(self, tabel, no_invoice, status, tanggal):
        label = QLabel()
        label.setProperty("billing_status_label", True)
        label.setProperty("billing_invoice", str(no_invoice or "").strip().upper())
        label.setProperty("billing_status", str(status or "").strip().upper())
        label.setProperty("billing_date", str(tanggal or "").strip())
        label.setProperty("billing_selected", False)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(False)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.setOpenExternalLinks(False)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.linkActivated.connect(self.buka_invoice_dari_buku_gudang)
        label.installEventFilter(self)
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(
            lambda pos, w=label, t=tabel: self.show_cell_context_menu(
                w.mapTo(t.viewport(), pos), t
            )
        )

        # Cell widget memiliki font sendiri, jadi samakan dengan zoom tabel aktif
        # sejak label dibuat. Ini juga menjaga ukuran setelah reload/filter data.
        zoom = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        ukuran_font = get_global_font_sizes(zoom)["sz_base"]
        self._terapkan_font_point(label, ukuran_font)

        self._render_label_status_penagihan(label, self._tema_gelap_aktif())
        return label

    def _terapkan_tema_label_status_penagihan(
        self,
        tabel,
        is_dark,
        ukuran_font=None,
    ):
        selection_model = tabel.selectionModel()
        selected_rows = (
            {index.row() for index in selection_model.selectedRows()}
            if selection_model is not None
            else set()
        )

        for row in range(tabel.rowCount()):
            label = tabel.cellWidget(row, self.KOL_STATUS_PENAGIHAN)
            if not (
                isinstance(label, QLabel)
                and bool(label.property("billing_status_label"))
            ):
                continue

            if ukuran_font is not None:
                self._terapkan_font_point(label, ukuran_font)

            label.setProperty("billing_selected", row in selected_rows)
            self._render_label_status_penagihan(label, is_dark)

    def _sinkronkan_selection_label_status_penagihan(self, tabel):
        """Sinkronkan warna rich-text STATUS PENAGIHAN dengan selection row."""
        self._terapkan_tema_label_status_penagihan(
            tabel,
            self._tema_gelap_aktif(),
        )

    def buka_invoice_dari_buku_gudang(self, no_invoice):
        invoice = str(no_invoice or "").strip().upper()
        if not invoice:
            return False
        tab_invoice = self._cari_tab_invoice()
        if tab_invoice is None or not hasattr(tab_invoice, "load_invoice_by_no"):
            QMessageBox.critical(
                self,
                "Tab Invoice Tidak Ditemukan",
                "Tab Invoice tidak ditemukan atau tidak mendukung pembukaan invoice langsung.",
            )
            return False
        if not tab_invoice.load_invoice_by_no(invoice):
            return False
        if not self._pindah_ke_tab_invoice(tab_invoice):
            QMessageBox.information(
                self,
                "Invoice Dibuka",
                f"Invoice {invoice} sudah dimuat, tetapi tab utama tidak dapat dipindahkan otomatis.",
            )
        return True

    def _format_cell_buku_gudang(self, data, col, wilayah):
        display = str(data).upper() if data is not None else ""
        if col == self.KOL_KOTA_TUJUAN:
            return display.replace(f"{wilayah} - ".upper(), "").replace(
                wilayah.upper(), ""
            ).strip(" -")
        if col in self.KOLOM_TANGGAL and data and "-" in display:
            return format_tanggal_ke_ui(data)
        if col == self.KOL_KOLI:
            teks = str(data).strip() if data is not None else ""
            return teks.upper() if teks and teks != "0" else "-"
        if col == self.KOL_ONGKIR:
            teks = str(data).strip() if data is not None else ""
            return format_ke_rupiah(data) if teks not in {"", "0", "0.0", "None"} else "-"
        if col in self.KOLOM_DESIMAL:
            return format_angka_indonesia(data, kosong_jika_nol=True, nilai_kosong="-")
        return display

    def _alignment_cell_buku_gudang(self, col):
        if col in self.KOLOM_RATA_KANAN:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if col in self.KOLOM_TANGGAL:
            return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    def _isi_baris_tabel(self, tabel, wilayah, row, is_parent):
        pos = tabel.rowCount()
        tabel.insertRow(pos)

        no_resi = str(row[0] or "").strip() if len(row) > 0 else ""
        detail_id = row[16] if len(row) > 16 else None
        urutan = int(row[17] or 1) if len(row) > 17 else 1
        revision = int(row[18] or 0) if len(row) > 18 else 0
        no_invoice = str(row[19] or "").strip().upper() if len(row) > 19 else ""
        status_invoice = str(row[20] or "").strip().upper() if len(row) > 20 else ""
        tanggal_invoice = str(row[21] or "").strip() if len(row) > 21 else ""
        jumlah_invoice = int(row[22] or 0) if len(row) > 22 else 0
        status_resi = str(row[3] or "").strip().upper() if len(row) > 3 else ""
        status_penagihan = self._teks_status_penagihan(
            no_invoice, status_invoice, tanggal_invoice
        )

        values = [
            row[0] if len(row) > 0 else "",
            row[1] if len(row) > 1 else "",
            row[2] if len(row) > 2 else "",
            row[3] if len(row) > 3 else "",
            status_penagihan,
            row[4] if len(row) > 4 else "",
            row[5] if len(row) > 5 else "",
            row[6] if len(row) > 6 else "",
            row[7] if len(row) > 7 else "",
            row[8] if len(row) > 8 else "",
            row[9] if len(row) > 9 else "",
            row[10] if len(row) > 10 else "",
            row[11] if len(row) > 11 else "",
            row[12] if len(row) > 12 else "",
            row[13] if len(row) > 13 else "",
            row[14] if len(row) > 14 else "",
            row[15] if len(row) > 15 else "",
        ]

        nomor_resi = 1 + sum(
            1
            for indeks in range(pos)
            if tabel.item(indeks, self.KOL_RESI) is not None
            and bool(tabel.item(indeks, self.KOL_RESI).data(self.ROLE_IS_PARENT))
        )
        item_no = buat_tabel_item(
            text=str(nomor_resi) if is_parent else "",
            editable=False,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        tabel.setItem(pos, self.KOL_NO, item_no)

        status_highlight = (
            status_invoice if status_invoice in {"LUNAS", "MACET"} else ""
        )
        highlight_value = f"{status_highlight}|{status_resi}"

        for col, data in enumerate(values, start=1):
            tampil = data
            if not is_parent:
                if col == self.KOL_RESI:
                    tampil = f"↳ ITEM {urutan}"
                elif col not in (
                    self.KOL_NAMA_BARANG, self.KOL_KOLI, self.KOL_BERAT, self.KOL_CBM
                ):
                    tampil = ""

            item = buat_tabel_item(
                text=self._format_cell_buku_gudang(tampil, col, wilayah),
                editable=False,
                alignment=self._alignment_cell_buku_gudang(col),
            )
            item.setData(self.ROLE_NO_RESI, no_resi)
            item.setData(self.ROLE_DETAIL_ID, detail_id)
            item.setData(self.ROLE_IS_PARENT, is_parent)
            item.setData(self.ROLE_URUTAN_DETAIL, urutan)
            item.setData(self.ROLE_REVISION, revision)
            item.setData(self.ROLE_INVOICE_NO, no_invoice if is_parent else "")
            item.setData(self.ROLE_INVOICE_DATE, tanggal_invoice if is_parent else "")
            item.setData(self.ROLE_INVOICE_STATUS, status_invoice if is_parent else "")
            item.setData(self.ROLE_INVOICE_COUNT, jumlah_invoice if is_parent else 0)
            if col == self.KOL_STATUS_RESI:
                item.setData(self.ROLE_STATUS_HIGHLIGHT, highlight_value)
            tabel.setItem(pos, col, item)

        if is_parent and no_invoice:
            label_penagihan = self._buat_label_status_penagihan(
                tabel, no_invoice, status_invoice, tanggal_invoice
            )
            label_penagihan.setProperty("billing_highlight_state", highlight_value)
            label_penagihan.setProperty("billing_row_index", pos)
            # Render ulang setelah state row tersedia agar warna teks non-link
            # identik dengan foreground delegate pada row tersebut.
            self._render_label_status_penagihan(
                label_penagihan, self._tema_gelap_aktif()
            )
            tabel.setCellWidget(
                pos, self.KOL_STATUS_PENAGIHAN, label_penagihan
            )


    def load_data(self, tab_widget):
        tabel = tab_widget.tabel
        wilayah = tab_widget.wilayah
        filters = dict(getattr(tab_widget, "filter_data", {}) or {})
        if self._bulan_terpilih:
            filters["_bulan"] = tuple(sorted(self._bulan_terpilih))
        if self._status_penagihan_terpilih != "SEMUA":
            filters["_status_penagihan"] = self._status_penagihan_terpilih

        if not hasattr(tabel, "_zoom_base_column_widths"):
            tabel._zoom_base_column_widths = {
                i: tabel.columnWidth(i) for i in range(tabel.columnCount())
            }

        tabel.blockSignals(True)
        tabel.setUpdatesEnabled(False)
        tabel.setRowCount(0)
        try:
            rows = db_service.ambil_data_buku_gudang(
                self._kode_cabang_aktif(),
                wilayah,
                self.btn_tahun.text(),
                filters,
            )
            resi_terakhir = None
            for row in rows or []:
                no_resi = str(row[0] or "").strip()
                is_parent = no_resi != resi_terakhir
                self._isi_baris_tabel(tabel, wilayah, row, is_parent)
                resi_terakhir = no_resi

            if tabel.rowCount() > 0:
                tabel.scrollToBottom()
            self._terapkan_pencarian_ke_tabel(tabel)
        except Exception as error:
            QMessageBox.critical(
                self, "Error Database", f"Gagal memuat data buku gudang:\n{error}"
            )
        finally:
            tabel.setUpdatesEnabled(True)
            tabel.blockSignals(False)
            tabel.viewport().update()

    def _nilai_editor_baris(self, tabel, row, col):
        widget = tabel.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            return widget.currentText().strip().upper()
        return widget.text().strip().upper() if widget else ""

    def _normalisasi_update_baris(self, tabel, row, col, val):
        if col in (*self.KOLOM_DESIMAL, self.KOL_ONGKIR) and val in {"", "-"}:
            val = "0"
        elif col == self.KOL_KOLI and val == "-":
            val = ""

        if col == self.KOL_ONGKIR:
            return str(rupiah_to_int(val))
        if col in self.KOLOM_DESIMAL:
            return str(angka_indonesia_to_decimal(val))
        if col == self.KOL_KOTA_TUJUAN:
            tab_widget = self._ambil_tab_widget_dari_tabel(tabel)
            wilayah = str(getattr(tab_widget, "wilayah", "")).strip().upper()
            if wilayah and wilayah not in val:
                return f"{wilayah} - {val}" if val else wilayah
        return val

    def _kumpulkan_update_baris(self, tabel, row):
        return {
            field: self._normalisasi_update_baris(
                tabel, row, col, self._nilai_editor_baris(tabel, row, col)
            )
            for col, field in self.KOLOM_DB.items()
        }


    @staticmethod
    def _pesan_proteksi_invoice(no_resi, teks_invoice, perubahan_finansial):
        pembuka = f"Resi {no_resi} sudah digunakan pada Invoice:\n{teks_invoice}\n\n"
        if perubahan_finansial:
            return (
                pembuka
                + "Anda mengubah data finansial (ongkir atau payment). Perubahan "
                "di Buku Gudang TIDAK otomatis memperbarui Invoice yang sudah dibuat."
                "\n\nTetap simpan perubahan Resi?"
            )
        return (
            pembuka
            + "Invoice tersebut tetap menjadi snapshot lama dan tidak ikut berubah."
            "\n\nTetap simpan perubahan Resi?"
        )

    def _konfirmasi_edit_resi_terinvoice(self, no_resi, updates):
        """Konfirmasi sebelum mengubah Resi yang sudah tersimpan pada Invoice."""
        try:
            proteksi = db_service.cek_proteksi_invoice_resi(
                no_resi, updates, self._kode_cabang_aktif()
            )
        except Exception:
            return True

        if not proteksi.get("terkait"):
            return True

        daftar = []
        for info in proteksi.get("invoices", []):
            nomor = str(info.get("no_invoice") or "").strip()
            status = str(info.get("status") or "").strip()
            daftar.append(f"{nomor} ({status})" if status else nomor)
        teks_invoice = ", ".join(item for item in daftar if item) or "Invoice terkait"

        pesan = self._pesan_proteksi_invoice(
            no_resi,
            teks_invoice,
            proteksi.get("perubahan_finansial"),
        )
        jawaban = QMessageBox.warning(
            self,
            "Resi Sudah Masuk Invoice",
            pesan,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return jawaban == QMessageBox.StandardButton.Yes

    def _updates_editor_baris(self, tabel, row, is_parent):
        if is_parent:
            return self._kumpulkan_update_baris(tabel, row)

        return {
            self.KOLOM_DB[col]: self._normalisasi_update_baris(
                tabel, row, col, self._nilai_editor_baris(tabel, row, col)
            )
            for col in (
                self.KOL_NAMA_BARANG,
                self.KOL_KOLI,
                self.KOL_BERAT,
                self.KOL_CBM,
            )
        }



    def _tampilkan_gagal_simpan_baris(self, no_resi, revision_awal):
        revision_sekarang = None
        try:
            detail = db_service.ambil_detail_resi(no_resi)
            if detail and len(detail) > 20:
                revision_sekarang = int(detail[20] or 0)
        except Exception:
            revision_sekarang = None

        konflik = (
            revision_awal is not None
            and (revision_sekarang is None or revision_sekarang != revision_awal)
        )
        if konflik:
            QMessageBox.warning(
                self,
                "Data Resi Berubah",
                "Data Resi telah berubah dari modul lain. "
                "Data akan dimuat ulang sebelum Anda mengedit kembali.",
            )
        else:
            QMessageBox.critical(
                self,
                "Gagal Menyimpan",
                f"Perubahan data Resi {no_resi} tidak tersimpan. "
                "Data mungkin sudah tidak tersedia atau database menolak pembaruan.",
            )
        self.refresh_session_ui()

    def eksekusi_simpan_baris_ke_db(self, tabel, row):
        if self.row_sedang_diedit == -1:
            return

        no_resi = self._no_resi_dari_baris(tabel, row)
        if not no_resi:
            QMessageBox.warning(
                self, "Peringatan", "Nomor resi pada baris yang diedit tidak tersedia."
            )
            self.refresh_session_ui()
            return

        item_resi = tabel.item(row, self.KOL_RESI)
        is_parent = bool(item_resi.data(self.ROLE_IS_PARENT)) if item_resi else True
        detail_id = self._detail_id_dari_baris(tabel, row)

        try:
            updates = self._updates_editor_baris(tabel, row, is_parent)
            payload = {
                key: updates[key]
                for key in ("nama_barang", "koli", "berat", "cbm")
                if key in updates
            }
            if not self._konfirmasi_edit_resi_terinvoice(no_resi, updates):
                return

            revision_awal = self._revision_dari_baris(tabel, row)
            berhasil = db_service.update_baris_buku_gudang(
                no_resi,
                self._kode_cabang_aktif(),
                updates,
                payload,
                detail_id=detail_id,
                expected_revision=revision_awal,
            )
            if not berhasil:
                self._tampilkan_gagal_simpan_baris(no_resi, revision_awal)
                return

            self.refresh_session_ui()
            QMessageBox.information(self, "Sukses", f"Data Resi {no_resi} berhasil disimpan!")
        except Exception as error:
            QMessageBox.critical(self, "Error", f"Gagal: {error}")
            self.refresh_session_ui()

    def _resi_terpilih_terlihat(self, tabel):
        return sorted({
            no_resi
            for row in self._ambil_baris_terseleksi_invoice(tabel)
            if not tabel.isRowHidden(row)
            for no_resi in [self._no_resi_dari_baris(tabel, row)]
            if no_resi
        })

    def tandai_selesai_massal(self, tabel):
        resi_list = self._resi_terpilih_terlihat(tabel)
        if not resi_list:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Tidak ada resi valid yang dipilih "
                "(atau resi sedang disembunyikan oleh filter).",
            )
            return

        jawaban = QMessageBox.question(
            self,
            "Konfirmasi",
            f"Tandai {len(resi_list)} resi menjadi SELESAI?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if jawaban != QMessageBox.StandardButton.Yes:
            return

        try:
            berhasil = db_service.tandai_resi_selesai_massal(
                resi_list, self._kode_cabang_aktif()
            )
            if not berhasil:
                QMessageBox.critical(
                    self,
                    "Gagal Memperbarui Status",
                    "Status resi tidak berhasil diperbarui di database.",
                )
                self.refresh_session_ui()
                return

            self.refresh_session_ui()
            QMessageBox.information(
                self, "Sukses", f"{len(resi_list)} resi berhasil ditandai SELESAI."
            )
        except Exception as error:
            QMessageBox.critical(self, "Error", f"Gagal: {error}")

    def refresh_session_ui(self):
        self.row_sedang_diedit = -1
        if self.tabs_wilayah.currentWidget():
            self.load_data(self.tabs_wilayah.currentWidget())

        self.filter_pencarian_tabel()

    def jadwalkan_simpan_lebar_kolom(self, tabel):
        """Menunda penyimpanan sampai resize kolom selesai dilakukan."""
        if self._sedang_menerapkan_zoom or tabel is None:
            return

        self._tabel_lebar_pending = tabel
        self._timer_simpan_lebar.start()

    def _simpan_lebar_kolom_tertunda(self):
        tabel = self._tabel_lebar_pending
        self._tabel_lebar_pending = None

        if tabel is None or self._sedang_menerapkan_zoom:
            return

        try:
            self.simpan_lebar_kolom(tabel)
        except RuntimeError:
            # Tabel mungkin sudah dihancurkan ketika aplikasi ditutup.
            return

    def simpan_lebar_kolom(self, tabel):
        if self._sedang_menerapkan_zoom:
            return

        z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        faktor = zoom_helper.dapatkan_faktor_geometri(z)

        lebar_dasar = []
        for index in range(tabel.columnCount()):
            lebar_asli = int(round(tabel.columnWidth(index) / faktor))
            lebar_asli = min(max(BUKU_GUDANG_COLUMN_WIDTH_MIN, lebar_asli), BUKU_GUDANG_COLUMN_WIDTH_MAX)
            lebar_dasar.append(lebar_asli)

            if hasattr(tabel, "_zoom_base_column_widths"):
                tabel._zoom_base_column_widths[index] = lebar_asli

        settings = self._settings_kolom()
        settings.setValue(self.SETTINGS_KEY_LEBAR, lebar_dasar)
        settings.sync()

    def load_lebar_kolom(self, tabel):
        saved_widths = self._normalisasi_daftar_lebar(
            self._settings_kolom().value(self.SETTINGS_KEY_LEBAR),
            tabel.columnCount(),
        )
        widths = saved_widths or list(
            self.DEFAULT_LEBAR_KOLOM[:tabel.columnCount()]
        )

        while len(widths) < tabel.columnCount():
            widths.append(BUKU_GUDANG_FALLBACK_COLUMN_WIDTH)

        header = tabel.horizontalHeader()
        status_signal_sebelumnya = header.blockSignals(True)
        try:
            for index, width in enumerate(widths):
                if index < tabel.columnCount():
                    tabel.setColumnWidth(index, int(width))
        finally:
            header.blockSignals(status_signal_sebelumnya)

        tabel._zoom_base_column_widths = {
            index: int(widths[index])
            for index in range(tabel.columnCount())
        }