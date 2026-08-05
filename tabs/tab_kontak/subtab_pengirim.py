# tabs/tab_kontak/subtab_pengirim.py
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION

import services.database_service as db_service

from themes.modules.kontak_armada import get_kontak_riwayat_styles

from utils.typography import get_master_font, get_global_font_sizes
from utils.widget_helpers import paksa_kapital_lineedit as helper_paksa_kapital_lineedit
from utils.placeholder_helper import terap_semua_placeholder_dinamis
import utils.zoom as zoom_helper
from utils.mixins import ZoomTableMixin
from utils.table_helper import buat_tabel_item
from utils.date_ind_format import format_tanggal_ke_ui

# --- Import Helper Splitter ---
from utils.splitter_helper import buat_splitter

class SubTabPengirim(QWidget, ZoomTableMixin):
    KOL_NO = 0
    KOL_ID = 1
    KOL_NAMA_PENGIRIM = 2
    KOL_TELEPON = 3
    KOL_KOTA = 4
    KOL_ALAMAT = 5

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "SubTabMasterPengirim"

    KOLOM_PENCARIAN = (
        KOL_NAMA_PENGIRIM,
        KOL_TELEPON,
        KOL_KOTA,
        KOL_ALAMAT,
    )

    # ============================================================
    # INISIALISASI DAN UI
    # ============================================================

    def __init__(self):
        super().__init__()
        self._sedang_menerapkan_zoom = False
        self.init_ui()

    def init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(0, 0, 0, 0)
        layout_utama.setSpacing(8)

        # --- PANEL KIRI: DATA UTAMA (MASTER PANEL) ---
        self.panel_kiri = QWidget()
        self.panel_kiri.setMinimumWidth(400)
        self.panel_kiri.setMaximumWidth(1400)
        layout_kiri = QVBoxLayout(self.panel_kiri)
        layout_kiri.setContentsMargins(8, 8, 8, 8)
        layout_kiri.setSpacing(8)

        # Header Kiri (Utama): Horizontal Layout
        hbox_header_kiri = QHBoxLayout()
        self.lbl_judul = QLabel("👤 List Pengirim")
        self.lbl_judul.setFont(QFont(get_master_font(), 18, QFont.Weight.Bold))  # 14pt (Besar/Dominan)
        hbox_header_kiri.addWidget(self.lbl_judul)
        hbox_header_kiri.addStretch()

        self.txt_cari = QLineEdit()
        self.txt_cari.setPlaceholderText("Cari pengirim...")
        self.txt_cari.setProperty("zoom_font_key", "sz_input")
        self.txt_cari.setFixedWidth(230)  # Lebar utama 230px
        self.txt_cari.setFixedHeight(30)
        self.txt_cari.textChanged.connect(lambda _t: helper_paksa_kapital_lineedit(self.txt_cari))
        self.txt_cari.textChanged.connect(self.filter_pencarian_tabel)
        hbox_header_kiri.addWidget(self.txt_cari)
        layout_kiri.addLayout(hbox_header_kiri)

        self.tabel_pengirim = QTableWidget()
        self.tabel_pengirim.setColumnCount(6)
        self.tabel_pengirim.setHorizontalHeaderLabels([
            "NO.", "ID SHIPPER", "NAMA PENGIRIM", "NO. HP", "KOTA", "ALAMAT"
        ])
        self.tabel_pengirim.verticalHeader().setVisible(False)
        self.tabel_pengirim.setColumnHidden(self.KOL_ID, True)

        self.tabel_pengirim.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.tabel_pengirim.itemChanged.connect(self.simpan_edit_pengirim_dari_tabel)
        self.tabel_pengirim.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel_pengirim.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel_pengirim.setAlternatingRowColors(True)
        self.tabel_pengirim.cellClicked.connect(self.pilih_pengirim_tampilkan_histori)

        header_kiri = self.tabel_pengirim.horizontalHeader()
        header_kiri.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_kiri.setSectionsClickable(True)
        header_kiri.setSectionsMovable(False)

        self.load_lebar_kolom(self.tabel_pengirim)

        header_kiri.sectionResized.connect(
            lambda logicalIndex, oldSize, newSize: self.simpan_lebar_kolom(self.tabel_pengirim)
        )
        layout_kiri.addWidget(self.tabel_pengirim)

        # --- PANEL KANAN: HISTORI TRANSAKSI (DETAIL/PENDUKUNG PANEL) ---
        self.panel_kanan = QWidget()
        self.panel_kanan.setMinimumWidth(400)
        self.panel_kanan.setMaximumWidth(1400)
        self.panel_kanan.setObjectName("panelHistori")
        layout_kanan = QVBoxLayout(self.panel_kanan)
        layout_kanan.setContentsMargins(8, 8, 8, 8)
        layout_kanan.setSpacing(8)

        # Header Kanan (Pendukung): Horizontal Layout dengan hirarki visual lebih rendah
        hbox_header_kanan = QHBoxLayout()
        self.lbl_judul_histori = QLabel("📦 Riwayat Pengiriman")
        self.lbl_judul_histori.setFont(QFont(get_master_font(), 11, QFont.Weight.Bold))  # 11pt (Lebih kecil dari kiri)
        hbox_header_kanan.addWidget(self.lbl_judul_histori)
        hbox_header_kanan.addStretch()

        self.txt_cari_histori = QLineEdit()
        self.txt_cari_histori.setPlaceholderText("Cari di histori ini...")
        self.txt_cari_histori.setFixedHeight(30)
        self.txt_cari_histori.setFixedWidth(180)  # Lebih pendek (180px) agar terlihat sekunder
        self.txt_cari_histori.setProperty("zoom_font_key", "sz_input")
        self.txt_cari_histori.textChanged.connect(lambda _t: helper_paksa_kapital_lineedit(self.txt_cari_histori))
        self.txt_cari_histori.textChanged.connect(self.filter_pencarian_histori)
        hbox_header_kanan.addWidget(self.txt_cari_histori)
        layout_kanan.addLayout(hbox_header_kanan)

        self.tabel_histori = QTableWidget()
        self.tabel_histori.setColumnCount(7)
        self.tabel_histori.setHorizontalHeaderLabels(
            ["TANGGAL", "NO. RESI", "PENERIMA", "KOLI", "BERAT", "CBM", "ONGKIR"])
        self.tabel_histori.verticalHeader().setVisible(False)
        self.tabel_histori.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel_histori.setAlternatingRowColors(True)

        header_kanan = self.tabel_histori.horizontalHeader()
        header_kanan.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_kanan.setSectionsClickable(True)
        header_kanan.setSectionsMovable(False)

        self.load_lebar_kolom_histori(self.tabel_histori)

        header_kanan.sectionResized.connect(
            lambda logicalIndex, oldSize, newSize: self.simpan_lebar_kolom_histori(self.tabel_histori)
        )
        layout_kanan.addWidget(self.tabel_histori)

        # --- GABUNGKAN KE SPLITTER MENGGUNAKAN HELPER ---
        self.splitter = buat_splitter(
            self.panel_kiri,
            self.panel_kanan,
            ukuran_awal=(650, 450),
            parent=self,
        )
        self.splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout_utama.addWidget(self.splitter)

        self.refresh_session_ui()
        self.sesuaikan_tema_lokal()

    # ============================================================
    # REFRESH DAN EVENT
    # ============================================================

    def refresh_session_ui(self):
        self.load_data_pengirim()
        self.filter_pencarian_tabel()

    def showEvent(self, event):
        super().showEvent(event)

        self.refresh_session_ui()

        win = self.window()
        is_dark = bool(
            win
            and hasattr(win, "current_theme")
            and win.current_theme == "dark"
        )
        terap_semua_placeholder_dinamis(
            self,
            is_dark=is_dark,
        )

    # ============================================================
    # PENCARIAN
    # ============================================================

    def filter_pencarian_tabel(self):
        keyword = self.txt_cari.text().lower().strip()
        for row in range(self.tabel_pengirim.rowCount()):
            match = any(
                self.tabel_pengirim.item(row, col) and keyword in self.tabel_pengirim.item(row, col).text().lower()
                for col in self.KOLOM_PENCARIAN
            )
            self.tabel_pengirim.setRowHidden(row, not match)

    def filter_pencarian_histori(self):
        keyword = self.txt_cari_histori.text().lower().strip()
        for row in range(self.tabel_histori.rowCount()):
            match = any(
                self.tabel_histori.item(row, col) and keyword in self.tabel_histori.item(row, col).text().lower()
                for col in range(self.tabel_histori.columnCount())
            )
            self.tabel_histori.setRowHidden(row, not match)

    # ============================================================
    # DATA PENGIRIM
    # ============================================================

    def load_data_pengirim(self):
        self.tabel_pengirim.blockSignals(True)
        self.tabel_pengirim.setRowCount(0)
        self.tabel_histori.setRowCount(0)

        try:
            kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')
            rows = db_service.ambil_semua_master_pengirim(kode_cabang)

            for baris, data in enumerate(rows):
                self.tabel_pengirim.insertRow(baris)

                self.tabel_pengirim.setItem(baris, self.KOL_NO,
                                            buat_tabel_item(baris + 1, editable=False, alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_pengirim.setItem(baris, self.KOL_ID,
                                            buat_tabel_item(data[0], editable=False, alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_pengirim.setItem(baris, self.KOL_NAMA_PENGIRIM,
                                            buat_tabel_item(data[2], alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
                self.tabel_pengirim.setItem(baris, self.KOL_TELEPON,
                                            buat_tabel_item(data[3], alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_pengirim.setItem(baris, self.KOL_KOTA,
                                            buat_tabel_item(data[5], alignment=Qt.AlignmentFlag.AlignLeft))
                self.tabel_pengirim.setItem(baris, self.KOL_ALAMAT,
                                            buat_tabel_item(data[4], alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

        except Exception as e:
            print(f"Error Load Pengirim: {e}")
        finally:
            self.tabel_pengirim.blockSignals(False)

    def simpan_edit_pengirim_dari_tabel(self, item):
        if not item or item.column() in [self.KOL_NO, self.KOL_ID]: return
        row = item.row()
        kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')

        try:
            id_pengirim = self.tabel_pengirim.item(row, self.KOL_ID).text().strip()
            nama = self.tabel_pengirim.item(row, self.KOL_NAMA_PENGIRIM).text().strip().upper()
            no_hp = self.tabel_pengirim.item(row, self.KOL_TELEPON).text().strip()
            kota = self.tabel_pengirim.item(row, self.KOL_KOTA).text().strip().upper()
            alamat = self.tabel_pengirim.item(row, self.KOL_ALAMAT).text().strip().upper()

            sukses, pesan = db_service.update_master_pengirim_dari_tabel(id_pengirim, kode_cabang, nama, no_hp, kota,
                                                                         alamat)
            if not sukses:
                self.refresh_session_ui()
                return

            self.tabel_pengirim.blockSignals(True)
            try:
                self.tabel_pengirim.item(row, self.KOL_NAMA_PENGIRIM).setText(nama)
                self.tabel_pengirim.item(row, self.KOL_KOTA).setText(kota)
                self.tabel_pengirim.item(row, self.KOL_ALAMAT).setText(alamat)
            finally:
                self.tabel_pengirim.blockSignals(False)
        except Exception as e:
            print(f"Error simpan edit pengirim: {e}")
            self.refresh_session_ui()

    # ============================================================
    # HISTORI PENGIRIM
    # ============================================================

    def pilih_pengirim_tampilkan_histori(self, row, column):
        self.tabel_histori.setRowCount(0)
        item_nama = self.tabel_pengirim.item(row, self.KOL_NAMA_PENGIRIM)
        if not item_nama: return

        nama_pengirim = item_nama.text()
        kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')

        try:
            histori_rows = db_service.ambil_histori_transaksi_by_pengirim(nama_pengirim, kode_cabang)
            self.lbl_judul_histori.setText(f"📦 Riwayat Nota: {nama_pengirim}")

            for baris, h in enumerate(histori_rows):
                self.tabel_histori.insertRow(baris)
                ongkir_formatted = f"{int(h[6]):,}".replace(",", ".") if h[6] else "0"

                self.tabel_histori.setItem(baris, 0,
                                           buat_tabel_item(format_tanggal_ke_ui(h[0]), editable=False,
                                                           alignment=Qt.AlignmentFlag.AlignCenter)) #No.
                self.tabel_histori.setItem(baris, 1,
                                           buat_tabel_item(h[1], editable=False,
                                                           alignment=Qt.AlignmentFlag.AlignCenter)) #Resi
                self.tabel_histori.setItem(baris, 2,
                                           buat_tabel_item(h[2], editable=False,
                                                           alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)) #Penerima
                # Koli, Berat, CBM, Ongkir -> Rata Kanan
                for col in range(3, 7):
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    val = ongkir_formatted if col == 6 else (h[col] if h[col] else "-")
                    self.tabel_histori.setItem(baris, col, buat_tabel_item(val, editable=False, alignment=align))

            self.filter_pencarian_histori()
        except Exception as e:
            print(f"Error Load Histori Pengirim: {e}")

    # ============================================================
    # LEBAR KOLOM MENGGUNAKAN FUNGSI DARI MIXIN
    # ============================================================

    def _settings_kolom(self):
        return QSettings(self.SETTINGS_ORGANIZATION, self.SETTINGS_APPLICATION)

    def simpan_lebar_kolom(self, t):
        if self._sedang_menerapkan_zoom:
            return
        widths = self._lebar_dasar_tabel(t)
        self._perbarui_cache_lebar_zoom(t, widths)
        self._settings_kolom().setValue("lebar_kolom_pengirim", widths)

    def load_lebar_kolom(self, t):
        widths = self._settings_kolom().value("lebar_kolom_pengirim")
        if widths:
            for i, width in enumerate(widths):
                if i < t.columnCount(): t.setColumnWidth(i, int(width))
        else:
            t.setColumnWidth(self.KOL_NO, 50)
            t.setColumnWidth(self.KOL_ID, 90)
            t.setColumnWidth(self.KOL_NAMA_PENGIRIM, 180)
            t.setColumnWidth(self.KOL_TELEPON, 130)
            t.setColumnWidth(self.KOL_KOTA, 120)

        t.horizontalHeader().setSectionResizeMode(self.KOL_ALAMAT, QHeaderView.ResizeMode.Stretch)
        base_widths = [t.columnWidth(i) for i in range(t.columnCount())]
        self._perbarui_cache_lebar_zoom(t, base_widths)

    def simpan_lebar_kolom_histori(self, t):
        if self._sedang_menerapkan_zoom:
            return
        widths = self._lebar_dasar_tabel(t)
        self._perbarui_cache_lebar_zoom(t, widths)
        self._settings_kolom().setValue("lebar_kolom_histori_pengirim", widths)

    def load_lebar_kolom_histori(self, t):
        w = self._settings_kolom().value("lebar_kolom_histori_pengirim")
        if w:
            for i, width in enumerate(w):
                if i < t.columnCount(): t.setColumnWidth(i, int(width))
        else:
            defaults = [95, 100, 140, 50, 60, 60, 90]
            for idx, width in enumerate(defaults):
                if idx < t.columnCount(): t.setColumnWidth(idx, width)

        base_widths = [t.columnWidth(i) for i in range(t.columnCount())]
        self._perbarui_cache_lebar_zoom(t, base_widths)

    # ============================================================
    # TEMA DAN ZOOM SEMUA ELEMEN
    # ============================================================

    def sesuaikan_tema_lokal(self):
        win = self.window()
        is_dark = win.current_theme == "dark" if win and hasattr(win, 'current_theme') else False
        z = zoom_helper.dapatkan_zoom_level("TabKontak")

        st = get_kontak_riwayat_styles(is_dark)

        self._set_style_dasar_zoom(self.lbl_judul, st["judul"])
        self._set_style_dasar_zoom(self.lbl_judul_histori, st["judul_histori"])
        self._set_style_dasar_zoom(self.txt_cari, st["input"])
        self._set_style_dasar_zoom(self.txt_cari_histori, st["input"])

        # Blokir signal tabel sebelum zoom agar lebar tabel tidak "lompat"
        self.tabel_pengirim.horizontalHeader().blockSignals(True)
        self.tabel_histori.horizontalHeader().blockSignals(True)

        self._sedang_menerapkan_zoom = True
        try:
            # Terapkan style dan zoom hanya pada tabel panel kiri dan kanan.
            # Fungsi ini tetap dibutuhkan karena selain zoom, helper juga
            # menerapkan style dinamis pada tabel dan elemen turunannya.
            zoom_helper.terapkan_zoom_semua_elemen(
                container_widget=self.tabel_pengirim,
                z=z,
                is_dark=is_dark,
            )
            zoom_helper.terapkan_zoom_semua_elemen(
                container_widget=self.tabel_histori,
                z=z,
                is_dark=is_dark,
            )

            # Paksa skala lebar kolom seperti mekanisme pada kode asli.
            zoom_helper._skalakan_kolom_tableview(self.tabel_pengirim, z)
            zoom_helper._skalakan_kolom_tableview(self.tabel_histori, z)
        finally:
            self._sedang_menerapkan_zoom = False
            self.tabel_pengirim.horizontalHeader().blockSignals(False)
            self.tabel_histori.horizontalHeader().blockSignals(False)

        terap_semua_placeholder_dinamis(
            self,
            is_dark=is_dark,
        )