# tabs/tab_kontak/subtab_pengirim.py
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION
import services.database_service as db_service
from themes.modules.kontak_armada import get_kontak_riwayat_styles
from utils.typography import get_global_font_sizes_pt, get_master_font
from utils.widget_helpers import atur_tinggi_input, paksa_kapital_lineedit as helper_paksa_kapital_lineedit
import utils.zoom as zoom_helper
from utils.mixins import ZoomTableMixin
from utils.table_helper import buat_tabel_item
from utils.date_ind_format import format_tanggal_ke_ui
from utils.splitter_helper import buat_splitter, perbarui_semua_style_splitter
from utils.modules.kontak_metrics import (
    KONTAK_ADD_BUTTON_HEIGHT,
    KONTAK_ADD_DIALOG_MARGINS,
    KONTAK_ADD_DIALOG_MIN_WIDTH,
    KONTAK_ADD_DIALOG_SPACING,
    KONTAK_ADD_FIELD_MIN_WIDTH,
    KONTAK_ADD_FORM_HORIZONTAL_SPACING,
    KONTAK_ADD_FORM_VERTICAL_SPACING,
    KONTAK_HISTORY_COLUMN_WIDTHS,
    KONTAK_HISTORY_SEARCH_WIDTH,
    KONTAK_PANEL_MARGINS,
    KONTAK_PANEL_MAX_WIDTH,
    KONTAK_PANEL_MIN_WIDTH,
    KONTAK_PENGIRIM_COLUMN_WIDTHS,
    KONTAK_SEARCH_WIDTH,
    KONTAK_SPACING,
    KONTAK_SPLITTER_INITIAL_SIZES,
    KONTAK_SUBTAB_MARGINS,
)


def _buat_font_pt(ukuran_pt: float, *, tebal: bool = False) -> QFont:
    """Membuat QFont berbasis point agar konsisten lintas-DPI."""
    font = QFont(get_master_font())
    font.setPointSizeF(float(ukuran_pt))
    font.setBold(tebal)
    return font


class SubTabPengirim(QWidget, ZoomTableMixin):
    KOL_NO = 0
    KOL_ID = 1
    KOL_NAMA_PENGIRIM = 2
    KOL_TELEPON = 3
    KOL_ALAMAT = 4
    KOL_KOTA = 5

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "SubTabMasterPengirim"

    KOLOM_PENCARIAN = (KOL_NAMA_PENGIRIM, KOL_TELEPON, KOL_ALAMAT, KOL_KOTA)
    HEADER_PENGIRIM = ("NO.", "ID SHIPPER", "NAMA PENGIRIM", "NO. HP", "ALAMAT", "KOTA")
    HEADER_HISTORI = ("TANGGAL", "NO. RESI", "PENERIMA", "KOLI", "BERAT", "CBM", "ONGKIR")
    LEBAR_PENGIRIM = KONTAK_PENGIRIM_COLUMN_WIDTHS
    LEBAR_HISTORI = KONTAK_HISTORY_COLUMN_WIDTHS

    def __init__(self):
        super().__init__()
        self._sedang_menerapkan_zoom = False
        self.init_ui()

    def init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(*KONTAK_SUBTAB_MARGINS)
        layout_utama.setSpacing(KONTAK_SPACING)

        self.panel_kiri = self._bangun_panel_pengirim()
        self.panel_kanan = self._bangun_panel_histori()

        self.splitter = buat_splitter(
            self.panel_kiri,
            self.panel_kanan,
            ukuran_awal=KONTAK_SPLITTER_INITIAL_SIZES,
            parent=self,
        )
        self.splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout_utama.addWidget(self.splitter)

        self.refresh_session_ui()
        self.sesuaikan_tema_lokal()

    def _bangun_panel_pengirim(self):
        panel = QWidget()
        panel.setMinimumWidth(KONTAK_PANEL_MIN_WIDTH)
        panel.setMaximumWidth(KONTAK_PANEL_MAX_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(*KONTAK_PANEL_MARGINS)
        layout.setSpacing(KONTAK_SPACING)

        self.lbl_judul = QLabel("List Pengirim")
        self.lbl_judul.setFont(
            _buat_font_pt(get_global_font_sizes_pt(0)["sz_title"], tebal=True)
        )
        self.txt_cari = self._buat_input_cari(
            "Cari pengirim...", KONTAK_SEARCH_WIDTH, self.filter_pencarian_tabel
        )
        self.btn_tambah_pengirim = QPushButton("+ Tambah Pengirim")
        self.btn_tambah_pengirim.setFixedHeight(KONTAK_ADD_BUTTON_HEIGHT)
        self.btn_tambah_pengirim.clicked.connect(self.tampilkan_dialog_tambah_pengirim)

        header = self._buat_header(self.lbl_judul, self.txt_cari)
        header.insertWidget(2, self.btn_tambah_pengirim)
        layout.addLayout(header)

        self.tabel_pengirim = QTableWidget()
        self._konfigurasi_tabel(
            self.tabel_pengirim,
            self.HEADER_PENGIRIM,
            editable=True,
        )
        self.tabel_pengirim.setColumnHidden(self.KOL_ID, True)
        self.tabel_pengirim.itemChanged.connect(self.simpan_edit_pengirim_dari_tabel)
        self.tabel_pengirim.cellClicked.connect(self.pilih_pengirim_tampilkan_histori)
        self.load_lebar_kolom(self.tabel_pengirim)
        self.tabel_pengirim.horizontalHeader().sectionResized.connect(
            lambda _index, _old, _new: self.simpan_lebar_kolom(self.tabel_pengirim)
        )
        layout.addWidget(self.tabel_pengirim)
        return panel

    def _bangun_panel_histori(self):
        panel = QWidget()
        panel.setMinimumWidth(KONTAK_PANEL_MIN_WIDTH)
        panel.setMaximumWidth(KONTAK_PANEL_MAX_WIDTH)
        panel.setObjectName("panelHistori")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(*KONTAK_PANEL_MARGINS)
        layout.setSpacing(KONTAK_SPACING)

        self.lbl_judul_histori = QLabel("📦 Riwayat Pengiriman")
        self.lbl_judul_histori.setFont(
            _buat_font_pt(get_global_font_sizes_pt(0)["sz_total"], tebal=True)
        )
        self.txt_cari_histori = self._buat_input_cari(
            "Cari di histori ini...", KONTAK_HISTORY_SEARCH_WIDTH, self.filter_pencarian_histori
        )
        layout.addLayout(self._buat_header(self.lbl_judul_histori, self.txt_cari_histori))

        self.tabel_histori = QTableWidget()
        self._konfigurasi_tabel(self.tabel_histori, self.HEADER_HISTORI)
        self.load_lebar_kolom_histori(self.tabel_histori)
        self.tabel_histori.horizontalHeader().sectionResized.connect(
            lambda _index, _old, _new: self.simpan_lebar_kolom_histori(self.tabel_histori)
        )
        layout.addWidget(self.tabel_histori)
        return panel

    @staticmethod
    def _buat_header(label, input_cari):
        layout = QHBoxLayout()
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(input_cari)
        return layout

    def _buat_input_cari(self, placeholder, lebar, callback):
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        widget.setFixedWidth(lebar)
        atur_tinggi_input(widget)
        widget.textChanged.connect(
            lambda _text, w=widget: helper_paksa_kapital_lineedit(w)
        )
        widget.textChanged.connect(callback)
        return widget

    @staticmethod
    def _konfigurasi_tabel(tabel, headers, *, editable=False):
        tabel.setColumnCount(len(headers))
        tabel.setHorizontalHeaderLabels(list(headers))
        tabel.verticalHeader().setVisible(False)
        tabel.setAlternatingRowColors(True)
        tabel.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
            if editable
            else QAbstractItemView.EditTrigger.NoEditTriggers
        )
        if editable:
            tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = tabel.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)

    def refresh_session_ui(self):
        self.load_data_pengirim()
        self.filter_pencarian_tabel()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_session_ui()

    def _tema_gelap_aktif(self):
        win = self.window()
        return bool(win and hasattr(win, "current_theme") and win.current_theme == "dark")

    @staticmethod
    def _filter_tabel(tabel, keyword, columns):
        keyword = keyword.lower().strip()
        for row in range(tabel.rowCount()):
            match = any(
                (item := tabel.item(row, col))
                and keyword in item.text().lower()
                for col in columns
            )
            tabel.setRowHidden(row, not match)

    def filter_pencarian_tabel(self):
        self._filter_tabel(
            self.tabel_pengirim,
            self.txt_cari.text(),
            self.KOLOM_PENCARIAN,
        )

    def filter_pencarian_histori(self):
        self._filter_tabel(
            self.tabel_histori,
            self.txt_cari_histori.text(),
            range(self.tabel_histori.columnCount()),
        )

    def _isi_baris_pengirim(self, baris, data):
        nilai = (
            (self.KOL_NO, baris + 1, False, Qt.AlignmentFlag.AlignCenter),
            (self.KOL_ID, data[0], False, Qt.AlignmentFlag.AlignCenter),
            (
                self.KOL_NAMA_PENGIRIM,
                data[2],
                True,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ),
            (self.KOL_TELEPON, data[3], True, Qt.AlignmentFlag.AlignCenter),
            (
                self.KOL_ALAMAT,
                data[4],
                True,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ),
            (self.KOL_KOTA, data[5], True, Qt.AlignmentFlag.AlignLeft),
        )
        for kolom, teks, editable, alignment in nilai:
            self.tabel_pengirim.setItem(
                baris,
                kolom,
                buat_tabel_item(teks, editable=editable, alignment=alignment),
            )

    def _buat_form_tambah_pengirim(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Tambah Pengirim")
        dialog.setModal(True)
        dialog.setMinimumWidth(KONTAK_ADD_DIALOG_MIN_WIDTH)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(*KONTAK_ADD_DIALOG_MARGINS)
        layout.setSpacing(KONTAK_ADD_DIALOG_SPACING)

        form = QFormLayout()
        form.setHorizontalSpacing(KONTAK_ADD_FORM_HORIZONTAL_SPACING)
        form.setVerticalSpacing(KONTAK_ADD_FORM_VERTICAL_SPACING)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        fields = {key: QLineEdit() for key in ("nama", "no_hp", "alamat", "kota")}
        for key, placeholder in (
            ("nama", "Nama pengirim"), ("no_hp", "No. HP"),
            ("alamat", "Alamat"), ("kota", "Kota"),
        ):
            fields[key].setPlaceholderText(placeholder)
            fields[key].setMinimumWidth(KONTAK_ADD_FIELD_MIN_WIDTH)
        atur_tinggi_input(tuple(fields.values()))
        for key in ("nama", "alamat", "kota"):
            fields[key].textChanged.connect(
                lambda _text, w=fields[key]: helper_paksa_kapital_lineedit(w)
            )
        for label, key in (
            ("Nama Pengirim *", "nama"), ("No. HP", "no_hp"),
            ("Alamat", "alamat"), ("Kota", "kota"),
        ):
            form.addRow(label, fields[key])
        layout.addLayout(form)

        tombol = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        tombol.rejected.connect(dialog.reject)
        layout.addWidget(tombol)
        return dialog, fields, tombol

    def _simpan_pengirim_baru_dari_form(self, dialog, fields):
        nama = fields["nama"].text().strip().upper()
        no_hp = fields["no_hp"].text().strip()
        alamat = fields["alamat"].text().strip().upper()
        kota = fields["kota"].text().strip().upper()
        if not nama:
            QMessageBox.warning(dialog, "Data Belum Lengkap", "Nama pengirim wajib diisi.")
            fields["nama"].setFocus()
            return

        sukses, pesan = db_service.tambah_master_pengirim(
            CURRENT_SESSION.get("kode_cabang", "PUSAT"), nama, no_hp, kota, alamat,
        )
        if not sukses:
            QMessageBox.warning(
                dialog, "Gagal Menambah Pengirim",
                pesan or "Data pengirim tidak dapat disimpan.",
            )
            return
        dialog.accept()
        self.refresh_session_ui()

    def tampilkan_dialog_tambah_pengirim(self):
        dialog, fields, tombol = self._buat_form_tambah_pengirim()

        def simpan_pengirim_baru():
            self._simpan_pengirim_baru_dari_form(dialog, fields)

        tombol.accepted.connect(simpan_pengirim_baru)
        fields["nama"].setFocus()
        dialog.adjustSize()
        dialog.exec()

    def load_data_pengirim(self):
        self.tabel_pengirim.blockSignals(True)
        self.tabel_pengirim.setRowCount(0)
        self.tabel_histori.setRowCount(0)
        try:
            rows = db_service.ambil_semua_master_pengirim(
                CURRENT_SESSION.get("kode_cabang", "PUSAT")
            )
            for baris, data in enumerate(rows):
                self.tabel_pengirim.insertRow(baris)
                self._isi_baris_pengirim(baris, data)
        except Exception as e:
            print(f"Error Load Pengirim: {e}")
        finally:
            self.tabel_pengirim.blockSignals(False)

    def _ambil_data_edit_pengirim(self, row):
        tabel = self.tabel_pengirim
        return (
            tabel.item(row, self.KOL_ID).text().strip(),
            tabel.item(row, self.KOL_NAMA_PENGIRIM).text().strip().upper(),
            tabel.item(row, self.KOL_TELEPON).text().strip(),
            tabel.item(row, self.KOL_ALAMAT).text().strip().upper(),
            tabel.item(row, self.KOL_KOTA).text().strip().upper(),
        )

    def _terapkan_data_edit_pengirim(self, row, nama, alamat, kota):
        self.tabel_pengirim.blockSignals(True)
        try:
            for kolom, nilai in (
                (self.KOL_NAMA_PENGIRIM, nama),
                (self.KOL_ALAMAT, alamat),
                (self.KOL_KOTA, kota),
            ):
                self.tabel_pengirim.item(row, kolom).setText(nilai)
        finally:
            self.tabel_pengirim.blockSignals(False)

    def simpan_edit_pengirim_dari_tabel(self, item):
        if not item or item.column() in [self.KOL_NO, self.KOL_ID]:
            return
        row = item.row()
        try:
            id_pengirim, nama, no_hp, alamat, kota = self._ambil_data_edit_pengirim(row)
            sukses, _pesan = db_service.update_master_pengirim_dari_tabel(
                id_pengirim, CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                nama, no_hp, kota, alamat,
            )
            if not sukses:
                self.refresh_session_ui()
                return
            self._terapkan_data_edit_pengirim(row, nama, alamat, kota)
        except Exception as e:
            print(f"Error simpan edit pengirim: {e}")
            self.refresh_session_ui()

    def _isi_baris_histori(self, baris, h):
        ongkir = f"{int(h[6]):,}".replace(",", ".") if h[6] else "0"
        nilai = (
            (format_tanggal_ke_ui(h[0]), Qt.AlignmentFlag.AlignCenter),
            (h[1], Qt.AlignmentFlag.AlignCenter),
            (h[2], Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            (h[3] if h[3] else "-", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            (h[4] if h[4] else "-", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            (h[5] if h[5] else "-", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            (ongkir, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
        )
        for kolom, (teks, alignment) in enumerate(nilai):
            self.tabel_histori.setItem(
                baris,
                kolom,
                buat_tabel_item(teks, editable=False, alignment=alignment),
            )

    def pilih_pengirim_tampilkan_histori(self, row, column):
        self.tabel_histori.setRowCount(0)
        item_nama = self.tabel_pengirim.item(row, self.KOL_NAMA_PENGIRIM)
        if not item_nama:
            return

        nama_pengirim = item_nama.text()
        try:
            histori_rows = db_service.ambil_histori_transaksi_by_pengirim(
                nama_pengirim,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
            )
            self.lbl_judul_histori.setText(f"📦 Riwayat Nota: {nama_pengirim}")
            for baris, histori in enumerate(histori_rows):
                self.tabel_histori.insertRow(baris)
                self._isi_baris_histori(baris, histori)
            self.filter_pencarian_histori()
        except Exception as e:
            print(f"Error Load Histori Pengirim: {e}")

    def _settings_kolom(self):
        return QSettings(self.SETTINGS_ORGANIZATION, self.SETTINGS_APPLICATION)

    def _simpan_lebar(self, tabel, key):
        if self._sedang_menerapkan_zoom:
            return
        widths = self._lebar_dasar_tabel(tabel)
        self._perbarui_cache_lebar_zoom(tabel, widths)
        self._settings_kolom().setValue(key, widths)

    def _muat_lebar(self, tabel, key, defaults):
        widths = self._settings_kolom().value(key)
        if widths:
            for index, width in enumerate(widths):
                if index < tabel.columnCount():
                    tabel.setColumnWidth(index, int(width))
        else:
            for index, width in enumerate(defaults):
                if index < tabel.columnCount():
                    tabel.setColumnWidth(index, width)
        self._perbarui_cache_lebar_zoom(
            tabel,
            [tabel.columnWidth(i) for i in range(tabel.columnCount())],
        )

    def simpan_lebar_kolom(self, t):
        self._simpan_lebar(t, "lebar_kolom_pengirim")

    def load_lebar_kolom(self, t):
        self._muat_lebar(t, "lebar_kolom_pengirim", self.LEBAR_PENGIRIM)
        self._perbarui_cache_lebar_zoom(
            t,
            [t.columnWidth(i) for i in range(t.columnCount())],
        )

    def simpan_lebar_kolom_histori(self, t):
        self._simpan_lebar(t, "lebar_kolom_histori_pengirim")

    def load_lebar_kolom_histori(self, t):
        self._muat_lebar(t, "lebar_kolom_histori_pengirim", self.LEBAR_HISTORI)

    def _terapkan_font_dasar(self):
        ukuran = get_global_font_sizes_pt(0)
        for widget, token, tebal in (
            (self.lbl_judul, "sz_title", True),
            (self.lbl_judul_histori, "sz_total", True),
            (self.txt_cari, "sz_input", False),
            (self.txt_cari_histori, "sz_input", False),
            (self.btn_tambah_pengirim, "sz_input", False),
        ):
            widget.setFont(_buat_font_pt(ukuran[token], tebal=tebal))
        atur_tinggi_input((self.txt_cari, self.txt_cari_histori))

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()
        z = zoom_helper.dapatkan_zoom_level("TabKontak")
        style = get_kontak_riwayat_styles(is_dark)

        for widget, key in (
            (self.lbl_judul, "judul"),
            (self.lbl_judul_histori, "judul_histori"),
            (self.txt_cari, "input"),
            (self.txt_cari_histori, "input"),
            (self.panel_kanan, "panel"),
        ):
            widget.setStyleSheet(style[key])

        perbarui_semua_style_splitter(self, is_dark)
        self._terapkan_font_dasar()

        self._sedang_menerapkan_zoom = True
        try:
            for tabel in (self.tabel_pengirim, self.tabel_histori):
                zoom_helper.terapkan_zoom_tabel(tabel, is_dark=is_dark, z=z)
        finally:
            self._sedang_menerapkan_zoom = False