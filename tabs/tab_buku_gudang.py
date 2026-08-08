# tabs/tab_buku_gudang.py
from datetime import datetime
from PySide6.QtCore import QDate, QEvent, QSettings, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    QFrame,
)

from config import CURRENT_SESSION, DATA_CLIENT

import services.database_service as db_service

from utils.frozen_table_helper import FrozenTableWidget
from utils import zoom as zoom_helper
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


class DialogPilihPenagih(QDialog):
    def __init__(self, nama_pengirim, nama_penerima, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pilih Pihak Tertagih")
        self.setMinimumWidth(350)
        self.nama_pengirim = str(nama_pengirim or "").strip()
        self.nama_penerima = str(nama_penerima or "").strip()
        dialog_styles = konversi_style_font_ke_point(
            get_dialog_pilih_penagih_styles()
        )
        self.setStyleSheet(dialog_styles["dialog"])

        layout = QVBoxLayout(self)

        lbl_info = QLabel("<b>Invoice ini akan ditagihkan kepada:</b>")
        layout.addWidget(lbl_info)

        self.rb_pengirim = QRadioButton(f"Pengirim ({self.nama_pengirim})")
        self.rb_penerima = QRadioButton(f"Penerima ({self.nama_penerima})")
        self.rb_ketiga = QRadioButton("Pihak Ketiga:")

        self.rb_pengirim.setChecked(True)

        self.txt_ketiga = QLineEdit()
        self.txt_ketiga.setPlaceholderText("Ketik nama pihak ketiga...")
        self.txt_ketiga.setEnabled(False)
        self.txt_ketiga.setStyleSheet(dialog_styles["input"])

        self.rb_ketiga.toggled.connect(
            lambda: self.txt_ketiga.setEnabled(self.rb_ketiga.isChecked()),
        )

        layout.addWidget(self.rb_pengirim)
        layout.addWidget(self.rb_penerima)
        layout.addWidget(self.rb_ketiga)
        layout.addWidget(self.txt_ketiga)

        layout.addSpacing(10)

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
    KOL_TRUK = 5
    KOL_PENGIRIM = 6
    KOL_KOTA_ASAL = 7
    KOL_PENERIMA = 8
    KOL_KOTA_TUJUAN = 9
    KOL_NAMA_BARANG = 10
    KOL_KOLI = 11
    KOL_BERAT = 12
    KOL_CBM = 13
    KOL_ONGKIR = 14
    KOL_PAYMENT = 15
    KOL_KETERANGAN = 16

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "BukuGudang"
    SETTINGS_KEY_LEBAR = "lebar_kolom_gudang_v2"

    KOLOM_PENCARIAN = tuple(range(KOL_RESI, KOL_KETERANGAN + 1))
    DEFAULT_LEBAR_KOLOM = (
        45,   # NO.
        115,  # RESI
        95,   # MASUK
        95,   # KELUAR
        110,  # STATUS
        165,  # TRUK
        180,  # PENGIRIM
        130,  # KOTA ASAL
        180,  # PENERIMA
        135,  # KOTA TUJUAN
        180,  # NAMA BARANG
        70,   # KOLI
        90,   # BERAT
        90,   # CBM
        125,  # ONGKIR
        120,  # PAYMENT
        220,  # KETERANGAN
    )

    HEADERS = (
        "NO.", "RESI", "MASUK", "KELUAR", "STATUS", "TRUK", "PENGIRIM",
        "KOTA ASAL", "PENERIMA", "KOTA TUJUAN", "NAMA BARANG", "KOLI",
        "BERAT (kg)", "KUBIK (m3)", "ONGKIR (Rp)", "PAYMENT", "KETERANGAN",
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

        # Simpan lebar kolom setelah pengguna selesai menyeret header.
        # Debounce mencegah QSettings.sync() dipanggil berkali-kali selama drag.
        self._timer_simpan_lebar = QTimer(self)
        self._timer_simpan_lebar.setSingleShot(True)
        self._timer_simpan_lebar.setInterval(250)
        self._timer_simpan_lebar.timeout.connect(
            self._simpan_lebar_kolom_tertunda,
        )

        self.init_ui()

    def init_ui(self):
        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(0, 8, 0, 0)
        layout_utama.setSpacing(8)

        hbox_header = QHBoxLayout()
        self.lbl_judul = QLabel("Buku Gudang")
        hbox_header.addWidget(self.lbl_judul)

        tahun_sekarang = datetime.now().year
        self.btn_tahun = QToolButton()
        self.btn_tahun.setText(str(tahun_sekarang))
        self.btn_tahun.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_tahun.setFixedWidth(120)

        self.menu_tahun = QMenu(self)
        self.setup_menu_tahun(tahun_sekarang)
        self.btn_tahun.setMenu(self.menu_tahun)

        hbox_header.addWidget(self.btn_tahun)
        hbox_header.addStretch()

        self.txt_cari = QLineEdit()
        self.txt_cari.setPlaceholderText("Ketik pencarian (Resi, Truk, Barang, dll)...")
        self.txt_cari.setFixedWidth(280)
        self.txt_cari.textChanged.connect(lambda: paksa_kapital_lineedit(self.txt_cari))
        self.txt_cari.textChanged.connect(self.filter_pencarian_tabel)
        hbox_header.addWidget(self.txt_cari)

        action_styles = konversi_style_font_ke_point(
            get_buku_gudang_action_styles()
        )

        self.btn_buat_invoice = QPushButton("🧾 Buat Invoice")
        self.btn_buat_invoice.setStyleSheet(action_styles["btn_buat_invoice"])

        self.btn_simpan_inv = QPushButton("Simpan")
        self.btn_simpan_inv.setStyleSheet(action_styles["btn_simpan_inv"])
        self.btn_simpan_inv.setVisible(False)

        self.btn_batal_inv = QPushButton("Batal")
        self.btn_batal_inv.setStyleSheet(action_styles["btn_batal_inv"])
        self.btn_batal_inv.setVisible(False)

        hbox_header.addWidget(self.btn_buat_invoice)
        hbox_header.addWidget(self.btn_simpan_inv)
        hbox_header.addWidget(self.btn_batal_inv)

        self.btn_buat_invoice.clicked.connect(self.aktifkan_mode_invoice)
        self.btn_batal_inv.clicked.connect(self.batalkan_mode_invoice)
        self.btn_simpan_inv.clicked.connect(self.proses_simpan_ke_invoice)

        layout_utama.addLayout(hbox_header)

        self.tabs_wilayah = QTabWidget()
        provinsi_tujuan = DATA_CLIENT.get(
            'provinsi_tujuan',
            ["PROVINSI A", "PROVINSI B", "PROVINSI C"],
        )

        for wilayah in provinsi_tujuan:
            widget_tabel = self.create_tabel_tab(wilayah)
            self.tabs_list.append(widget_tabel)
            self.tabs_wilayah.addTab(widget_tabel, f"{wilayah.title()}")

        layout_utama.addWidget(self.tabs_wilayah)
        self.tabs_wilayah.currentChanged.connect(
            lambda index: self.refresh_session_ui(),
        )

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

        for row in range(tabel.rowCount()):
            match = any(
                keyword in self._ambil_text_cell(tabel, row, col).casefold()
                for col in self.KOLOM_PENCARIAN
                if col < tabel.columnCount()
            )
            tabel.setRowHidden(row, not match)

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

    def _cari_tab_invoice(self):
        win = self.window()
        if not win:
            return None

        tab_invoice = getattr(win, 'tab_invoice', None)
        if tab_invoice and hasattr(tab_invoice, 'terima_data_baru'):
            return tab_invoice

        for widget in win.findChildren(QWidget):
            if widget.__class__.__name__ == 'TabInvoice' and hasattr(
                widget,
                'terima_data_baru',
            ):
                return widget

        for widget in win.findChildren(QWidget):
            if hasattr(widget, 'terima_data_baru') and hasattr(
                widget,
                'tabel_item_invoice',
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

    def _data_invoice_dari_baris(self, tabel, row):
        no_resi = self._ambil_text_item(tabel, row, self.KOL_RESI)
        if not no_resi:
            return None

        return {
            "no_resi": no_resi,
            "pengirim": self._ambil_text_item(tabel, row, self.KOL_PENGIRIM),
            "penerima": self._ambil_text_item(tabel, row, self.KOL_PENERIMA),
            "tujuan": self._ambil_text_item(tabel, row, self.KOL_KOTA_TUJUAN),
            "nama_barang": self._ambil_text_item(tabel, row, self.KOL_NAMA_BARANG),
            "koli": self._ambil_text_item(tabel, row, self.KOL_KOLI) or "0",
            "berat": self._ambil_text_item(tabel, row, self.KOL_BERAT) or "0",
            "kubik": self._ambil_text_item(tabel, row, self.KOL_CBM) or "0",
            "ongkir": self._ambil_text_item(tabel, row, self.KOL_ONGKIR) or "0",
        }

    def _kumpulkan_data_invoice(self, tabel, baris_terseleksi):
        hasil = []
        pengirim_pertama = penerima_pertama = None
        beda_pengirim_dikonfirmasi = False

        for row in baris_terseleksi:
            if tabel.isRowHidden(row):
                continue

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

    def proses_simpan_ke_invoice(self):
        current_tab = self.tabs_wilayah.currentWidget()
        if not current_tab or not hasattr(current_tab, "tabel"):
            QMessageBox.warning(self, "Peringatan", "Tabel Buku Gudang tidak ditemukan.")
            return

        tabel = current_tab.tabel
        baris_terseleksi = self._ambil_baris_terseleksi_invoice(tabel)
        if not baris_terseleksi:
            QMessageBox.warning(self, "Peringatan", "Anda belum memilih resi satupun!")
            return

        kumpulan = self._kumpulkan_data_invoice(tabel, baris_terseleksi)
        if kumpulan is None:
            return
        list_resi_data, nama_pengirim_pertama, nama_penerima_pertama = kumpulan

        if not list_resi_data:
            QMessageBox.warning(
                self, "Peringatan", "Data resi yang dipilih tidak valid atau kosong."
            )
            return

        dialog = DialogPilihPenagih(nama_pengirim_pertama, nama_penerima_pertama, self)
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
                    status_column=self.KOL_STATUS,
                    color_provider=get_buku_gudang_status_colors,
                    is_dark=is_dark,
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

        tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabel.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tabel.setAlternatingRowColors(True)
        tabel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tabel.customContextMenuRequested.connect(
            lambda pos, t=tabel: self.show_cell_context_menu(pos, t)
        )

    def create_tabel_tab(self, wilayah):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

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
            tabel.setStyleSheet(styles["tabel"])
            for target in (tabel, frozen):
                if target is None:
                    continue
                update_status_delegate_theme(target, is_dark)
                self._terapkan_font_point(target, ukuran_font)
                self._terapkan_font_point(target.horizontalHeader(), ukuran_font)
                self._terapkan_font_point(target.verticalHeader(), ukuran_font)
                target.verticalHeader().setDefaultSectionSize(tinggi_baris)

            self._sinkronkan_editor_inline(tabel)
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
        self.btn_tahun.setStyleSheet(styles_statis["btn_tahun"])
        self.txt_cari.setStyleSheet(styles_statis["txt_cari"])

        faktor = max(0.68, min(1.0 + (z * 0.08), 1.80))
        tinggi_baris = max(24, int(32 * faktor))
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
        ukuran_menu_tahun = get_global_font_sizes(0)["sz_input"] + 1
        self.menu_tahun.setStyleSheet(
            konversi_font_qss_ke_point(
                get_buku_gudang_menu_style(ukuran_menu_tahun)
            )
        )

        for i in range(3):
            thn = str(tahun_sekarang - i)
            self.menu_tahun.addAction(thn).triggered.connect(
                lambda checked, t=thn: self.ubah_tahun(t),
            )

        self.menu_tahun.addSeparator()

        submenu_lainnya = self.menu_tahun.addMenu("Lainnya...")
        submenu_lainnya.setStyleSheet(
            konversi_font_qss_ke_point(
                get_buku_gudang_menu_style(ukuran_menu_tahun)
            )
        )

        for i in range(3, 8):
            thn = str(tahun_sekarang - i)
            submenu_lainnya.addAction(thn).triggered.connect(
                lambda checked, t=thn: self.ubah_tahun(t),
            )

    def ubah_tahun(self, tahun_pilihan):
        self.btn_tahun.setText(tahun_pilihan)
        self.refresh_session_ui()

    def get_editor_type(self, col_index):
        if col_index in [self.KOL_MASUK, self.KOL_KELUAR]: return "date"
        if col_index == self.KOL_STATUS: return "status"
        if col_index == self.KOL_PAYMENT: return "payment"
        return "text"

    def filter_pencarian_tabel(self):
        current_tab = self.tabs_wilayah.currentWidget()
        if not current_tab or not hasattr(current_tab, "tabel"):
            return
        self._terapkan_pencarian_ke_tabel(current_tab.tabel)

    def show_header_menu(self, pos, tabel):
        col = tabel.horizontalHeader().logicalIndexAt(pos)
        if col == self.KOL_NO: return
        header_text = tabel.horizontalHeaderItem(col).text()
        editor_type = self.get_editor_type(col)

        menu = QMenu()
        menu.setStyleSheet(
            konversi_font_qss_ke_point(
                get_buku_gudang_menu_style(
                    get_global_font_sizes(0)["sz_input"]
                )
            )
        )
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.addWidget(QLabel(f"Filter {header_text}:"))

        if editor_type == "date":
            editor = QDateEdit()
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
            editor.setDate(QDate.currentDate())
        elif editor_type == "status":
            editor = QComboBox()
            editor.addItems(["", "DI GUDANG", "PERJALANAN", "SELESAI"])
        elif editor_type == "payment":
            editor = QComboBox()
            editor.addItems(["TF / INVOICE", "CASH"])
        else:
            editor = QLineEdit()

        vbox.addWidget(editor)
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

    def show_cell_context_menu(self, pos, tabel):
        item = tabel.itemAt(pos)
        if not item: return
        menu = QMenu()
        menu.setStyleSheet(
            konversi_font_qss_ke_point(
                get_buku_gudang_menu_style(
                    get_global_font_sizes(0)["sz_input"]
                )
            )
        )
        row = item.row()

        baris_awal = set(i.row() for i in tabel.selectedItems())
        if row not in baris_awal:
            tabel.selectRow(row)

        baris_terseleksi = set(i.row() for i in tabel.selectedItems())
        jumlah_resi = len(baris_terseleksi)

        if jumlah_resi > 1:
            buat_invoice_action = menu.addAction(
                f"🧾 Buat Invoice Gabungan ({jumlah_resi} Resi)",
            ) if self.row_sedang_diedit == -1 else None
            edit_action = None
            save_action = None
            cancel_action = None
            selesai_action = menu.addAction(
                "✅ Tandai 'SELESAI' Massal",
            ) if self.row_sedang_diedit == -1 else None
        else:
            buat_invoice_action = menu.addAction(
                "🧾 Buat Invoice dari Resi Ini",
            ) if self.row_sedang_diedit == -1 else None
            edit_action = menu.addAction(
                "✏️ Edit Baris Ini",
            ) if self.row_sedang_diedit == -1 else None
            save_action = menu.addAction(
                "💾 Simpan Perubahan",
            ) if self.row_sedang_diedit == row else None
            cancel_action = menu.addAction(
                "❌ Batalkan Edit",
            ) if self.row_sedang_diedit == row else None
            selesai_action = menu.addAction(
                "✅ Tandai 'SELESAI'",
            ) if item.column() == self.KOL_STATUS and self.row_sedang_diedit == -1 else None

        action = menu.exec(tabel.viewport().mapToGlobal(pos))
        if action == edit_action:
            self.aktifkan_mode_edit_baris(tabel, row)
        elif action == save_action:
            self.eksekusi_simpan_baris_ke_db(tabel, row)
        elif action == cancel_action:
            self.refresh_session_ui()
        elif action == selesai_action:
            self.tandai_selesai_massal(tabel)
        elif action == buat_invoice_action:
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
        for col in range(self.KOL_PENGIRIM, self.KOL_KETERANGAN + 1):
            item = tabel.item(row, col)
            tabel.setCellWidget(
                row,
                col,
                self._buat_editor_inline(tabel, row, col, item.text() if item else ""),
            )

        editor_awal = tabel.cellWidget(row, self.KOL_PENGIRIM)
        if editor_awal:
            editor_awal.setFocus()

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

    def _isi_baris_tabel(self, tabel, wilayah, row):
        pos = tabel.rowCount()
        tabel.insertRow(pos)
        tabel.setItem(
            pos,
            self.KOL_NO,
            buat_tabel_item(
                text=str(pos + 1),
                editable=False,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
        )

        for col_idx, data in enumerate(row):
            col = col_idx + 1
            if col >= tabel.columnCount():
                break
            tabel.setItem(
                pos,
                col,
                buat_tabel_item(
                    text=self._format_cell_buku_gudang(data, col, wilayah),
                    editable=False,
                    alignment=self._alignment_cell_buku_gudang(col),
                ),
            )

    def load_data(self, tab_widget):
        tabel = tab_widget.tabel
        wilayah = tab_widget.wilayah
        filters = getattr(tab_widget, "filter_data", {})

        if not hasattr(tabel, "_zoom_base_column_widths"):
            tabel._zoom_base_column_widths = {
                i: tabel.columnWidth(i) for i in range(tabel.columnCount())
            }

        tabel.blockSignals(True)
        tabel.setUpdatesEnabled(False)
        tabel.setRowCount(0)
        try:
            rows = db_service.ambil_data_buku_gudang(
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                wilayah,
                self.btn_tahun.text(),
                filters,
            )
            for row in rows or []:
                self._isi_baris_tabel(tabel, wilayah, row)

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

    def eksekusi_simpan_baris_ke_db(self, tabel, row):
        if self.row_sedang_diedit == -1:
            return

        item_resi = tabel.item(row, self.KOL_RESI)
        no_resi = item_resi.text().strip() if item_resi else ""
        if not no_resi:
            QMessageBox.warning(
                self, "Peringatan", "Nomor resi pada baris yang diedit tidak tersedia."
            )
            self.refresh_session_ui()
            return

        try:
            updates = self._kumpulkan_update_baris(tabel, row)
            payload = {key: updates[key] for key in ("nama_barang", "koli", "berat", "cbm")}
            berhasil = db_service.update_baris_buku_gudang(
                no_resi,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                updates,
                payload,
            )

            if not berhasil:
                QMessageBox.critical(
                    self,
                    "Gagal Menyimpan",
                    f"Perubahan data Resi {no_resi} tidak tersimpan. "
                    "Data mungkin sudah tidak tersedia atau database menolak pembaruan.",
                )
                self.refresh_session_ui()
                return

            self.refresh_session_ui()
            QMessageBox.information(self, "Sukses", f"Data Resi {no_resi} berhasil disimpan!")
        except Exception as error:
            QMessageBox.critical(self, "Error", f"Gagal: {error}")
            self.refresh_session_ui()

    def tandai_selesai_massal(self, tabel):
        rows = self._ambil_baris_terseleksi_invoice(tabel)
        resi_list = []
        for row in rows:
            if tabel.isRowHidden(row):
                continue
            item_resi = tabel.item(row, self.KOL_RESI)
            if item_resi and item_resi.text().strip():
                resi_list.append(item_resi.text().strip())

        resi_list = sorted(set(resi_list))
        if not resi_list:
            QMessageBox.warning(
                self,
                "Peringatan",
                (
                    "Tidak ada resi valid yang dipilih "
                    "(atau resi sedang disembunyikan oleh filter)."
                ),
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
                resi_list,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
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
                self,
                "Sukses",
                f"{len(resi_list)} resi berhasil ditandai SELESAI.",
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
        faktor = max(0.68, min(1.0 + (z * 0.08), 1.80))

        lebar_dasar = []
        for index in range(tabel.columnCount()):
            lebar_asli = int(round(tabel.columnWidth(index) / faktor))
            lebar_asli = min(max(20, lebar_asli), 1500)
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
            widths.append(110)

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