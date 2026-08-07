# tabs/tab_kontak/subtab_penerima.py
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION
import services.database_service as db_service
from themes.modules.kontak_armada import (
    get_kontak_riwayat_styles,
    get_penerima_blacklist_colors,
)
from utils.number_formatters import format_ke_rupiah
from utils.typography import get_global_font_sizes_pt, get_master_font
from utils.widget_helpers import paksa_kapital_lineedit as helper_paksa_kapital_lineedit
from utils.placeholder_helper import terap_semua_placeholder_dinamis
from utils.mixins import ZoomTableMixin
from utils.table_helper import buat_tabel_item
from utils.date_ind_format import format_tanggal_ke_ui
import utils.zoom as zoom_helper
from utils.splitter_helper import buat_splitter, perbarui_semua_style_splitter


def _buat_font_pt(ukuran_pt: float, *, tebal: bool = False) -> QFont:
    """Membuat QFont berbasis point agar konsisten lintas-DPI."""
    font = QFont(get_master_font())
    font.setPointSizeF(float(ukuran_pt))
    font.setBold(tebal)
    return font


class SubTabPenerima(QWidget, ZoomTableMixin):
    KOL_NO = 0
    KOL_ID = 1
    KOL_NAMA_PENERIMA = 2
    KOL_TELEPON = 3
    KOL_ALAMAT = 4
    KOL_KOTA = 5
    KOL_PROVINSI = 6
    KOL_TOTAL_TRANSAKSI = 7
    KOL_PEMBAYARAN = 8
    KOL_STATUS_TAGIHAN = 9

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "SubTabMasterPenerima"

    KOLOM_PENCARIAN = (
        KOL_NAMA_PENERIMA,
        KOL_TELEPON,
        KOL_ALAMAT,
        KOL_KOTA,
        KOL_PROVINSI,
        KOL_TOTAL_TRANSAKSI,
        KOL_PEMBAYARAN,
        KOL_STATUS_TAGIHAN,
    )
    HEADER_PENERIMA = (
        "NO.",
        "ID",
        "NAMA PENERIMA",
        "NO. HP",
        "ALAMAT",
        "KOTA",
        "PROVINSI",
        "TOTAL TRANSAKSI",
        "PEMBAYARAN",
        "STATUS TAGIHAN",
    )
    HEADER_HISTORI = ("TANGGAL", "NO. RESI", "PENGIRIM", "KOLI", "BERAT", "CBM", "ONGKIR")
    LEBAR_PENERIMA = (50, 90, 190, 130, 260, 130, 140, 130, 130, 130)
    LEBAR_HISTORI = (95, 100, 140, 50, 60, 60, 90)
    KOLOM_TIDAK_DIEDIT = (KOL_NO, KOL_ID, KOL_TOTAL_TRANSAKSI, KOL_STATUS_TAGIHAN)

    def __init__(self):
        super().__init__()
        self._sedang_menerapkan_zoom = False
        self.init_ui()

    def init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(8, 8, 8, 8)
        layout_utama.setSpacing(8)

        self.panel_kiri = self._bangun_panel_penerima()
        self.panel_kanan = self._bangun_panel_histori()

        self.splitter = buat_splitter(
            self.panel_kiri,
            self.panel_kanan,
            orientation=Qt.Orientation.Horizontal,
            ukuran_awal=[650, 450],
            bisa_diciutkan=False,
            parent=self,
        )
        self.splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout_utama.addWidget(self.splitter)

        self.refresh_session_ui()
        self.sesuaikan_tema_lokal()

    def _bangun_panel_penerima(self):
        panel = QWidget()
        panel.setMinimumWidth(400)
        panel.setMaximumWidth(1400)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        ukuran = get_global_font_sizes_pt(0)
        self.lbl_judul = QLabel("List Penerima")
        self.lbl_judul.setFont(_buat_font_pt(ukuran["sz_title"]))
        self.txt_cari = self._buat_input_cari(
            "Cari penerima...",
            230,
            self.filter_pencarian_tabel,
            ukuran["sz_input"],
        )
        layout.addLayout(self._buat_header(self.lbl_judul, self.txt_cari))

        self.tabel_penerima = QTableWidget()
        self._konfigurasi_tabel(
            self.tabel_penerima,
            self.HEADER_PENERIMA,
            editable=True,
        )
        self.tabel_penerima.setColumnHidden(self.KOL_ID, True)
        self.tabel_penerima.itemChanged.connect(self.simpan_edit_penerima_dari_tabel)
        self.tabel_penerima.cellClicked.connect(self.pilih_penerima_tampilkan_histori)
        self.tabel_penerima.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabel_penerima.customContextMenuRequested.connect(self.show_context_menu)
        self.load_lebar_kolom(self.tabel_penerima)
        self.tabel_penerima.horizontalHeader().sectionResized.connect(
            lambda _index, _old, _new: self.simpan_lebar_kolom(self.tabel_penerima)
        )
        layout.addWidget(self.tabel_penerima)
        return panel

    def _bangun_panel_histori(self):
        panel = QWidget()
        panel.setMinimumWidth(400)
        panel.setMaximumWidth(1400)
        panel.setObjectName("panelHistori")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        ukuran = get_global_font_sizes_pt(0)
        self.lbl_judul_histori = QLabel("📦 Riwayat Penerimaan")
        self.lbl_judul_histori.setFont(_buat_font_pt(ukuran["sz_total"]))
        self.txt_cari_histori = self._buat_input_cari(
            "Cari di histori ini...",
            180,
            self.filter_pencarian_histori,
            ukuran["sz_input"],
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

    def _buat_input_cari(self, placeholder, lebar, callback, ukuran_font=None):
        widget = QLineEdit()
        if ukuran_font is not None:
            widget.setFont(_buat_font_pt(ukuran_font))
        widget.setPlaceholderText(placeholder)
        widget.setFixedWidth(lebar)
        widget.setFixedHeight(30)
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
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)

    def refresh_session_ui(self):
        self.load_data()
        self.filter_pencarian_tabel()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_session_ui()
        terap_semua_placeholder_dinamis(self, is_dark=self._tema_gelap_aktif())

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
            self.tabel_penerima,
            self.txt_cari.text(),
            self.KOLOM_PENCARIAN,
        )

    def filter_pencarian_histori(self):
        self._filter_tabel(
            self.tabel_histori,
            self.txt_cari_histori.text(),
            range(self.tabel_histori.columnCount()),
        )

    def show_context_menu(self, pos):
        item = self.tabel_penerima.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        act_normal = menu.addAction("Set Status: NORMAL")
        act_blacklist = menu.addAction("Set Status: BLACKLIST (Macet)")
        action = menu.exec(self.tabel_penerima.viewport().mapToGlobal(pos))

        if action in (act_normal, act_blacklist):
            self.ubah_status_tagihan_penerima(
                item.row(),
                "NORMAL" if action == act_normal else "BLACKLIST",
            )

    def ubah_status_tagihan_penerima(self, row, status_baru):
        item_id = self.tabel_penerima.item(row, self.KOL_ID)
        if not item_id:
            return

        jawaban = QMessageBox.question(
            self,
            "Konfirmasi",
            f"Ubah status pembayaran menjadi {status_baru}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if jawaban != QMessageBox.StandardButton.Yes:
            return

        try:
            db_service.ubah_status_tagihan_penerima(
                item_id.text(),
                status_baru,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
            )
            self.refresh_session_ui()
        except Exception as error:
            QMessageBox.critical(self, "Error", f"Gagal: {error}")

    def _isi_baris_penerima(self, baris, data, is_dark):
        id_penerima = str(data[0]) if data[0] else ""
        nama = str(data[1]).upper() if data[1] else ""
        no_hp = str(data[2]) if data[2] else ""
        alamat = str(data[3]).upper() if data[3] else ""
        kota = str(data[4]).upper() if data[4] else ""
        provinsi = str(data[5]).upper() if data[5] else ""
        total_transaksi = str(data[6]) if data[6] else "0"
        pembayaran = str(data[7]).upper() if data[7] else "TF / INVOICE"
        status = str(data[8]).strip().upper() if data[8] else "NORMAL"

        nilai = (
            (self.KOL_NO, baris + 1, False, Qt.AlignmentFlag.AlignCenter),
            (self.KOL_ID, id_penerima, False, Qt.AlignmentFlag.AlignCenter),
            (
                self.KOL_NAMA_PENERIMA,
                nama,
                True,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ),
            (self.KOL_TELEPON, no_hp, True, Qt.AlignmentFlag.AlignCenter),
            (
                self.KOL_ALAMAT,
                alamat,
                True,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ),
            (self.KOL_KOTA, kota, True, Qt.AlignmentFlag.AlignCenter),
            (self.KOL_PROVINSI, provinsi, True, Qt.AlignmentFlag.AlignCenter),
            (self.KOL_TOTAL_TRANSAKSI, total_transaksi, False, Qt.AlignmentFlag.AlignCenter),
            (self.KOL_PEMBAYARAN, pembayaran, True, Qt.AlignmentFlag.AlignCenter),
            (self.KOL_STATUS_TAGIHAN, status, False, Qt.AlignmentFlag.AlignCenter),
        )
        for kolom, teks, editable, alignment in nilai:
            self.tabel_penerima.setItem(
                baris,
                kolom,
                buat_tabel_item(teks, editable=editable, alignment=alignment),
            )

        if status == "BLACKLIST":
            self._warnai_baris_blacklist(baris, is_dark)

    def _warnai_baris_blacklist(self, baris, is_dark):
        hex_bg, hex_fg = get_penerima_blacklist_colors(is_dark)
        warna_bg, warna_text = QColor(hex_bg), QColor(hex_fg)
        for kolom in range(self.tabel_penerima.columnCount()):
            item = self.tabel_penerima.item(baris, kolom)
            if item:
                item.setBackground(QBrush(warna_bg))
                item.setForeground(QBrush(warna_text))

    def load_data(self):
        self.tabel_penerima.blockSignals(True)
        self.tabel_penerima.setRowCount(0)
        if hasattr(self, "tabel_histori"):
            self.tabel_histori.setRowCount(0)

        try:
            rows = db_service.ambil_semua_master_penerima_full(
                CURRENT_SESSION.get("kode_cabang", "PUSAT")
            )
            is_dark = self._tema_gelap_aktif()
            for baris, data in enumerate(rows):
                self.tabel_penerima.insertRow(baris)
                self._isi_baris_penerima(baris, data, is_dark)
        except Exception as error:
            print(f"Error Load Penerima: {error}")
        finally:
            self.tabel_penerima.blockSignals(False)

    def simpan_edit_penerima_dari_tabel(self, item):
        if not item or item.column() in self.KOLOM_TIDAK_DIEDIT:
            return

        row = item.row()
        try:
            id_penerima = self.tabel_penerima.item(row, self.KOL_ID).text().strip()
            nama = self.tabel_penerima.item(row, self.KOL_NAMA_PENERIMA).text().strip().upper()
            no_hp = self.tabel_penerima.item(row, self.KOL_TELEPON).text().strip()
            alamat = self.tabel_penerima.item(row, self.KOL_ALAMAT).text().strip().upper()
            kota = self.tabel_penerima.item(row, self.KOL_KOTA).text().strip().upper()
            provinsi = self.tabel_penerima.item(row, self.KOL_PROVINSI).text().strip().upper()
            pembayaran = self.tabel_penerima.item(row, self.KOL_PEMBAYARAN).text().strip().upper()

            sukses, _pesan = db_service.update_master_penerima_dari_tabel(
                id_penerima,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                nama,
                no_hp,
                alamat,
                kota,
                provinsi,
                pembayaran,
            )
            if not sukses:
                self.refresh_session_ui()
                return

            self.tabel_penerima.blockSignals(True)
            try:
                for kolom, nilai in (
                    (self.KOL_NAMA_PENERIMA, nama),
                    (self.KOL_KOTA, kota),
                    (self.KOL_ALAMAT, alamat),
                    (self.KOL_PROVINSI, provinsi),
                    (self.KOL_PEMBAYARAN, pembayaran),
                ):
                    self.tabel_penerima.item(row, kolom).setText(nilai)
            finally:
                self.tabel_penerima.blockSignals(False)
        except Exception as error:
            QMessageBox.critical(self, "Error", f"Gagal simpan edit penerima: {error}")
            self.refresh_session_ui()

    def _isi_baris_histori(self, baris, h):
        nilai = (
            (format_tanggal_ke_ui(h[0]), Qt.AlignmentFlag.AlignCenter),
            (str(h[1]), Qt.AlignmentFlag.AlignCenter),
            (str(h[2]).upper(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            (str(h[3]), Qt.AlignmentFlag.AlignCenter),
            (str(h[4]), Qt.AlignmentFlag.AlignCenter),
            (str(h[5]), Qt.AlignmentFlag.AlignCenter),
            (
                format_ke_rupiah(h[7]) if h[7] else "0",
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            ),
        )
        for kolom, (teks, alignment) in enumerate(nilai):
            self.tabel_histori.setItem(
                baris,
                kolom,
                buat_tabel_item(teks, editable=False, alignment=alignment),
            )

    def pilih_penerima_tampilkan_histori(self, row, column):
        if not hasattr(self, "tabel_histori"):
            return
        self.tabel_histori.setRowCount(0)

        item_nama = self.tabel_penerima.item(row, self.KOL_NAMA_PENERIMA)
        if not item_nama:
            return

        nama_penerima = item_nama.text()
        try:
            histori_rows = db_service.ambil_histori_transaksi_by_penerima(
                nama_penerima,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
            )
            self.lbl_judul_histori.setText(f"📦 Riwayat Nota: {nama_penerima}")
            for baris, histori in enumerate(histori_rows):
                self.tabel_histori.insertRow(baris)
                self._isi_baris_histori(baris, histori)
            self.filter_pencarian_histori()
        except Exception as error:
            print(f"Error Load Histori Penerima: {error}")

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
        sumber = widths or defaults
        for index, width in enumerate(sumber):
            if index < tabel.columnCount():
                tabel.setColumnWidth(index, int(width))
        self._perbarui_cache_lebar_zoom(
            tabel,
            [tabel.columnWidth(i) for i in range(tabel.columnCount())],
        )

    def simpan_lebar_kolom(self, t):
        self._simpan_lebar(t, "lebar_kolom_penerima")

    def load_lebar_kolom(self, t):
        self._muat_lebar(t, "lebar_kolom_penerima", self.LEBAR_PENERIMA)

    def simpan_lebar_kolom_histori(self, t):
        self._simpan_lebar(t, "lebar_kolom_histori_penerima")

    def load_lebar_kolom_histori(self, t):
        self._muat_lebar(t, "lebar_kolom_histori_penerima", self.LEBAR_HISTORI)

    def _terapkan_font_dasar(self):
        ukuran = get_global_font_sizes_pt(0)
        for widget, token, tebal in (
            (self.lbl_judul, "sz_title", True),
            (self.lbl_judul_histori, "sz_total", True),
            (self.txt_cari, "sz_input", False),
            (self.txt_cari_histori, "sz_input", False),
        ):
            widget.setFont(_buat_font_pt(ukuran[token], tebal=tebal))
        self.txt_cari.setFixedHeight(30)
        self.txt_cari_histori.setFixedHeight(30)

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()
        z = zoom_helper.dapatkan_zoom_level("TabKontak")
        style = get_kontak_riwayat_styles(is_dark)

        perbarui_semua_style_splitter(self, is_dark)
        for widget, key in (
            (self.lbl_judul, "judul"),
            (self.lbl_judul_histori, "judul_histori"),
            (self.txt_cari, "input"),
            (self.txt_cari_histori, "input"),
            (self.panel_kanan, "panel"),
        ):
            widget.setStyleSheet(style[key])

        self._terapkan_font_dasar()
        self._sedang_menerapkan_zoom = True
        try:
            for tabel in (self.tabel_penerima, self.tabel_histori):
                zoom_helper.terapkan_zoom_tabel(tabel, is_dark=is_dark, z=z)
        finally:
            self._sedang_menerapkan_zoom = False

        terap_semua_placeholder_dinamis(self, is_dark=is_dark)