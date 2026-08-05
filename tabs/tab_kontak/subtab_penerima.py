# tabs/tab_kontak/subtab_penerima.py

import re

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION

import services.database_service as db_service

from themes.modules.kontak_armada import get_kontak_riwayat_styles, get_penerima_blacklist_colors

from utils.number_formatters import format_ke_rupiah
from utils.typography import get_master_font, get_global_font_sizes
from utils.widget_helpers import paksa_kapital_lineedit as helper_paksa_kapital_lineedit
from utils.placeholder_helper import terap_semua_placeholder_dinamis
from utils.mixins import ZoomTableMixin
from utils.table_helper import buat_tabel_item
from utils.date_ind_format import format_tanggal_ke_ui
import utils.zoom as zoom_helper

# --- Import Helper Splitter ---
from utils.splitter_helper import buat_splitter, perbarui_semua_style_splitter


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

    # ============================================================
    # INISIALISASI DAN UI
    # ============================================================

    def __init__(self):
        super().__init__()
        self._sedang_menerapkan_zoom = False
        self.init_ui()

    def init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        font_sizes = get_global_font_sizes(0)
        master_font = get_master_font()

        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(8, 8, 8, 8)
        layout_utama.setSpacing(8)

        # ========================================================
        # PANEL KIRI: DATA UTAMA (MASTER PANEL)
        # ========================================================
        self.panel_kiri = QWidget()
        self.panel_kiri.setMinimumWidth(400)
        self.panel_kiri.setMaximumWidth(1400)
        layout_kiri = QVBoxLayout(self.panel_kiri)
        layout_kiri.setContentsMargins(10, 10, 10, 10)  # Margin disamakan
        layout_kiri.setSpacing(10)

        # Header Kiri (Utama): Horizontal Layout
        hbox_header_kiri = QHBoxLayout()
        self.lbl_judul = QLabel("🏢 List Penerima")
        self.lbl_judul.setFont(QFont(master_font, font_sizes["sz_title"]))  # 14pt (Besar/Dominan)
        hbox_header_kiri.addWidget(self.lbl_judul)
        hbox_header_kiri.addStretch()

        self.txt_cari = QLineEdit()
        self.txt_cari.setFont(QFont(master_font, font_sizes["sz_input"]))
        self.txt_cari.setPlaceholderText("Cari penerima...")
        self.txt_cari.setFixedWidth(230)  # Lebar utama 230px
        self.txt_cari.setFixedHeight(30)
        self.txt_cari.textChanged.connect(lambda _text: helper_paksa_kapital_lineedit(self.txt_cari))
        self.txt_cari.textChanged.connect(self.filter_pencarian_tabel)
        hbox_header_kiri.addWidget(self.txt_cari)
        layout_kiri.addLayout(hbox_header_kiri)

        self.tabel_penerima = QTableWidget()
        self.tabel_penerima.setColumnCount(10)
        self.tabel_penerima.setHorizontalHeaderLabels([
            "NO.", "ID", "NAMA PENERIMA", "NO. HP", "ALAMAT",
            "KOTA", "PROVINSI", "TOTAL TRANSAKSI", "PEMBAYARAN", "STATUS TAGIHAN"
        ])

        self.tabel_penerima.verticalHeader().setVisible(False)
        self.tabel_penerima.setColumnHidden(self.KOL_ID, True)

        self.tabel_penerima.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.tabel_penerima.itemChanged.connect(self.simpan_edit_penerima_dari_tabel)
        self.tabel_penerima.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel_penerima.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel_penerima.setAlternatingRowColors(True)
        self.tabel_penerima.cellClicked.connect(self.pilih_penerima_tampilkan_histori)

        self.tabel_penerima.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabel_penerima.customContextMenuRequested.connect(self.show_context_menu)

        header = self.tabel_penerima.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)

        self.load_lebar_kolom(self.tabel_penerima)

        header.sectionResized.connect(
            lambda _index, _old, _new: self.simpan_lebar_kolom(self.tabel_penerima)
        )
        layout_kiri.addWidget(self.tabel_penerima)

        # ========================================================
        # PANEL KANAN: HISTORI TRANSAKSI (DETAIL/PENDUKUNG PANEL)
        # ========================================================
        self.panel_kanan = QWidget()  # Diubah menjadi QWidget biasa
        self.panel_kanan.setMinimumWidth(400)
        self.panel_kanan.setMaximumWidth(1400)
        self.panel_kanan.setObjectName("panelHistori")

        layout_kanan = QVBoxLayout(self.panel_kanan)
        layout_kanan.setContentsMargins(10, 10, 10, 10)
        layout_kanan.setSpacing(10)

        # Header Kanan (Pendukung): Horizontal Layout
        hbox_header_kanan = QHBoxLayout()
        self.lbl_judul_histori = QLabel("📦 Riwayat Penerimaan")
        self.lbl_judul_histori.setFont(QFont(master_font, font_sizes["sz_total"]))
        hbox_header_kanan.addWidget(self.lbl_judul_histori)
        hbox_header_kanan.addStretch()

        self.txt_cari_histori = QLineEdit()
        self.txt_cari_histori.setFont(QFont(master_font, font_sizes["sz_input"]))
        self.txt_cari_histori.setPlaceholderText("Cari di histori ini...")
        self.txt_cari_histori.setFixedHeight(30)
        self.txt_cari_histori.setFixedWidth(180)  # Lebih pendek 180px
        self.txt_cari_histori.textChanged.connect(lambda _t: helper_paksa_kapital_lineedit(self.txt_cari_histori))
        self.txt_cari_histori.textChanged.connect(self.filter_pencarian_histori)
        hbox_header_kanan.addWidget(self.txt_cari_histori)
        layout_kanan.addLayout(hbox_header_kanan)

        self.tabel_histori = QTableWidget()
        self.tabel_histori.setColumnCount(7)
        self.tabel_histori.setHorizontalHeaderLabels([
            "TANGGAL", "NO. RESI", "PENGIRIM", "KOLI", "BERAT", "CBM", "ONGKIR"
        ])
        self.tabel_histori.verticalHeader().setVisible(False)
        self.tabel_histori.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel_histori.setAlternatingRowColors(True)

        header_kanan = self.tabel_histori.horizontalHeader()
        header_kanan.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_kanan.setSectionsClickable(True)
        header_kanan.setSectionsMovable(False)

        self.load_lebar_kolom_histori(self.tabel_histori)

        header_kanan.sectionResized.connect(
            lambda _index, _old, _new: self.simpan_lebar_kolom_histori(self.tabel_histori)
        )
        layout_kanan.addWidget(self.tabel_histori)

        # --- GABUNGKAN KE SPLITTER MENGGUNAKAN HELPER ---
        self.splitter = buat_splitter(
            self.panel_kiri,
            self.panel_kanan,
            orientation=Qt.Orientation.Horizontal,
            ukuran_awal=[650, 450],
            bisa_diciutkan=False,
            parent=self
        )
        self.splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout_utama.addWidget(self.splitter)

        self.refresh_session_ui()
        self.sesuaikan_tema_lokal()

    # ============================================================
    # REFRESH DAN EVENT
    # ============================================================

    def refresh_session_ui(self):
        self.load_data()
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
        for row in range(self.tabel_penerima.rowCount()):
            match = any(
                self.tabel_penerima.item(row, col) and keyword in self.tabel_penerima.item(row, col).text().lower()
                for col in self.KOLOM_PENCARIAN
            )
            self.tabel_penerima.setRowHidden(row, not match)

    def filter_pencarian_histori(self):
        keyword = self.txt_cari_histori.text().lower().strip()
        for row in range(self.tabel_histori.rowCount()):
            match = any(
                self.tabel_histori.item(row, col) and keyword in self.tabel_histori.item(row, col).text().lower()
                for col in range(self.tabel_histori.columnCount())
            )
            self.tabel_histori.setRowHidden(row, not match)

    # ============================================================
    # CONTEXT MENU DAN STATUS TAGIHAN
    # ============================================================

    def show_context_menu(self, pos):
        item = self.tabel_penerima.itemAt(pos)
        if not item: return

        menu = QMenu(self)
        act_normal = menu.addAction("Set Status: NORMAL")
        act_blacklist = menu.addAction("Set Status: BLACKLIST (Macet)")

        action = menu.exec(self.tabel_penerima.viewport().mapToGlobal(pos))
        if action in (act_normal, act_blacklist):
            status_baru = "NORMAL" if action == act_normal else "BLACKLIST"
            self.ubah_status_tagihan_penerima(item.row(), status_baru)

    def ubah_status_tagihan_penerima(self, row, status_baru):
        item_id = self.tabel_penerima.item(row, self.KOL_ID)
        if not item_id: return

        id_penerima = item_id.text()
        jawaban = QMessageBox.question(
            self, "Konfirmasi",
            f"Ubah status pembayaran menjadi {status_baru}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if jawaban == QMessageBox.StandardButton.Yes:
            try:
                db_service.ubah_status_tagihan_penerima(
                    id_penerima, status_baru, CURRENT_SESSION.get("kode_cabang", "PUSAT")
                )
                self.refresh_session_ui()
            except Exception as error:
                QMessageBox.critical(self, "Error", f"Gagal: {error}")

    # ============================================================
    # DATA PENERIMA
    # ============================================================

    def load_data(self):
        self.tabel_penerima.blockSignals(True)
        self.tabel_penerima.setRowCount(0)

        if hasattr(self, "tabel_histori"):
            self.tabel_histori.setRowCount(0)

        window = self.window()
        is_dark = bool(window and hasattr(window, "current_theme") and window.current_theme == "dark")

        try:
            kode_cabang = CURRENT_SESSION.get("kode_cabang", "PUSAT")
            rows = db_service.ambil_semua_master_penerima_full(kode_cabang)

            for baris, data in enumerate(rows):
                self.tabel_penerima.insertRow(baris)

                id_penerima = str(data[0]) if data[0] else ""
                nama = str(data[1]).upper() if data[1] else ""
                no_hp = str(data[2]) if data[2] else ""
                alamat = str(data[3]).upper() if data[3] else ""
                kota = str(data[4]).upper() if data[4] else ""
                provinsi = str(data[5]).upper() if data[5] else ""
                total_transaksi = str(data[6]) if data[6] else "0"
                pembayaran = str(data[7]).upper() if data[7] else "TF / INVOICE"
                status = str(data[8]).strip().upper() if data[8] else "NORMAL"

                self.tabel_penerima.setItem(baris, self.KOL_NO,
                                            buat_tabel_item(baris + 1, editable=False,
                                                            alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_penerima.setItem(baris, self.KOL_ID,
                                            buat_tabel_item(id_penerima, editable=False,
                                                            alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_penerima.setItem(baris, self.KOL_NAMA_PENERIMA,
                                            buat_tabel_item(nama,
                                                            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
                self.tabel_penerima.setItem(baris, self.KOL_TELEPON,
                                            buat_tabel_item(no_hp, alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_penerima.setItem(baris, self.KOL_ALAMAT,
                                            buat_tabel_item(alamat,
                                                            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
                self.tabel_penerima.setItem(baris, self.KOL_KOTA,
                                            buat_tabel_item(kota, alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_penerima.setItem(baris, self.KOL_PROVINSI,
                                            buat_tabel_item(provinsi, alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_penerima.setItem(baris, self.KOL_TOTAL_TRANSAKSI,
                                            buat_tabel_item(total_transaksi, editable=False,
                                                            alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_penerima.setItem(baris, self.KOL_PEMBAYARAN,
                                            buat_tabel_item(pembayaran, alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_penerima.setItem(baris, self.KOL_STATUS_TAGIHAN,
                                            buat_tabel_item(status, editable=False,
                                                            alignment=Qt.AlignmentFlag.AlignCenter))

                # Pewarnaan untuk pelanggan Blacklist
                if status == "BLACKLIST":
                    hex_bg, hex_fg = get_penerima_blacklist_colors(is_dark)
                    warna_bg = QColor(hex_bg)
                    warna_text = QColor(hex_fg)

                    for col in range(self.tabel_penerima.columnCount()):
                        item_tabel = self.tabel_penerima.item(baris, col)
                        if item_tabel:
                            item_tabel.setBackground(QBrush(warna_bg))
                            item_tabel.setForeground(QBrush(warna_text))

        except Exception as error:
            print(f"Error Load Penerima: {error}")
        finally:
            self.tabel_penerima.blockSignals(False)

    def simpan_edit_penerima_dari_tabel(self, item):
        kolom_tidak_boleh_diedit = [self.KOL_NO, self.KOL_ID, self.KOL_TOTAL_TRANSAKSI, self.KOL_STATUS_TAGIHAN]
        if not item or item.column() in kolom_tidak_boleh_diedit: return

        row = item.row()
        kode_cabang = CURRENT_SESSION.get("kode_cabang", "PUSAT")

        try:
            id_penerima = self.tabel_penerima.item(row, self.KOL_ID).text().strip()
            nama = self.tabel_penerima.item(row, self.KOL_NAMA_PENERIMA).text().strip().upper()
            no_hp = self.tabel_penerima.item(row, self.KOL_TELEPON).text().strip()
            alamat = self.tabel_penerima.item(row, self.KOL_ALAMAT).text().strip().upper()
            kota = self.tabel_penerima.item(row, self.KOL_KOTA).text().strip().upper()
            provinsi = self.tabel_penerima.item(row, self.KOL_PROVINSI).text().strip().upper()
            pembayaran = self.tabel_penerima.item(row, self.KOL_PEMBAYARAN).text().strip().upper()

            sukses, pesan = db_service.update_master_penerima_dari_tabel(
                id_penerima, kode_cabang, nama, no_hp, alamat, kota, provinsi, pembayaran
            )

            if not sukses:
                self.refresh_session_ui()
                return

            self.tabel_penerima.blockSignals(True)
            try:
                self.tabel_penerima.item(row, self.KOL_NAMA_PENERIMA).setText(nama)
                self.tabel_penerima.item(row, self.KOL_KOTA).setText(kota)
                self.tabel_penerima.item(row, self.KOL_ALAMAT).setText(alamat)
                self.tabel_penerima.item(row, self.KOL_PROVINSI).setText(provinsi)
                self.tabel_penerima.item(row, self.KOL_PEMBAYARAN).setText(pembayaran)
            finally:
                self.tabel_penerima.blockSignals(False)

        except Exception as error:
            QMessageBox.critical(self, "Error", f"Gagal simpan edit penerima: {error}")
            self.refresh_session_ui()

    # ============================================================
    # HISTORI PENERIMA
    # ============================================================

    def pilih_penerima_tampilkan_histori(self, row, column):
        if not hasattr(self, "tabel_histori"): return
        self.tabel_histori.setRowCount(0)

        item_nama = self.tabel_penerima.item(row, self.KOL_NAMA_PENERIMA)
        if not item_nama: return

        nama_penerima = item_nama.text()
        kode_cabang = CURRENT_SESSION.get("kode_cabang", "PUSAT")

        try:
            histori_rows = db_service.ambil_histori_transaksi_by_penerima(nama_penerima, kode_cabang)
            self.lbl_judul_histori.setText(f"📦 Riwayat Nota: {nama_penerima}")

            for baris, h in enumerate(histori_rows):
                self.tabel_histori.insertRow(baris)
                ongkir_formatted = format_ke_rupiah(h[7]) if h[7] else "0"

                self.tabel_histori.setItem(baris, 0, buat_tabel_item(format_tanggal_ke_ui(h[0]), editable=False,
                                                                     alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_histori.setItem(baris, 1,
                                           buat_tabel_item(str(h[1]), editable=False,
                                                           alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_histori.setItem(baris, 2, buat_tabel_item(str(h[2]).upper(), editable=False,
                                                                     alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
                self.tabel_histori.setItem(baris, 3,
                                           buat_tabel_item(str(h[3]), editable=False,
                                                           alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_histori.setItem(baris, 4,
                                           buat_tabel_item(str(h[4]), editable=False,
                                                           alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_histori.setItem(baris, 5,
                                           buat_tabel_item(str(h[5]), editable=False,
                                                           alignment=Qt.AlignmentFlag.AlignCenter))
                self.tabel_histori.setItem(baris, 6, buat_tabel_item(ongkir_formatted, editable=False,
                                                                     alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))

            self.filter_pencarian_histori()

        except Exception as error:
            print(f"Error Load Histori Penerima: {error}")

    # ============================================================
    # LEBAR KOLOM MENGGUNAKAN FUNGSI DARI MIXIN
    # ============================================================

    def _settings_kolom(self):
        return QSettings(self.SETTINGS_ORGANIZATION, self.SETTINGS_APPLICATION)

    def simpan_lebar_kolom(self, t):
        if self._sedang_menerapkan_zoom: return
        widths = self._lebar_dasar_tabel(t)
        self._perbarui_cache_lebar_zoom(t, widths)
        self._settings_kolom().setValue("lebar_kolom_penerima", widths)

    def load_lebar_kolom(self, t):
        widths = self._settings_kolom().value("lebar_kolom_penerima")
        if widths:
            for index, width in enumerate(widths):
                if index < t.columnCount():
                    t.setColumnWidth(index, int(width))
        else:
            defaults = [50, 90, 190, 130, 260, 130, 140, 130, 130, 130]
            for index, width in enumerate(defaults):
                if index < t.columnCount():
                    t.setColumnWidth(index, width)

        base_widths = [t.columnWidth(i) for i in range(t.columnCount())]
        self._perbarui_cache_lebar_zoom(t, base_widths)

    def simpan_lebar_kolom_histori(self, t):
        if self._sedang_menerapkan_zoom: return
        widths = self._lebar_dasar_tabel(t)
        self._perbarui_cache_lebar_zoom(t, widths)
        self._settings_kolom().setValue("lebar_kolom_histori_penerima", widths)

    def load_lebar_kolom_histori(self, t):
        widths = self._settings_kolom().value("lebar_kolom_histori_penerima")
        if widths:
            for index, width in enumerate(widths):
                if index < t.columnCount():
                    t.setColumnWidth(index, int(width))
        else:
            defaults = [95, 100, 140, 50, 60, 60, 90]
            for index, width in enumerate(defaults):
                if index < t.columnCount():
                    t.setColumnWidth(index, width)

        base_widths = [t.columnWidth(i) for i in range(t.columnCount())]
        self._perbarui_cache_lebar_zoom(t, base_widths)

    # ============================================================
    # TEMA DAN ZOOM SEMUA ELEMEN
    # ============================================================

    @staticmethod
    def _style_tanpa_font_size(style):
        """Pertahankan seluruh QSS tema, tetapi jangan biarkan font-size menimpa konfigurasi global."""
        return re.sub(
            r"font-size\s*:\s*[^;}]+;?",
            "",
            style or "",
            flags=re.IGNORECASE,
        )

    def sesuaikan_tema_lokal(self):
        win = self.window()
        is_dark = win.current_theme == "dark" if win and hasattr(win, 'current_theme') else False
        z = zoom_helper.dapatkan_zoom_level("TabKontak")

        st = get_kontak_riwayat_styles(is_dark)

        # Perbarui style splitter menggunakan helper
        perbarui_semua_style_splitter(self, is_dark)

        self._set_style_dasar_zoom(
            self.lbl_judul,
            self._style_tanpa_font_size(st["judul"]),
        )
        self._set_style_dasar_zoom(
            self.lbl_judul_histori,
            self._style_tanpa_font_size(st["judul_histori"]),
        )
        self._set_style_dasar_zoom(
            self.txt_cari,
            self._style_tanpa_font_size(st["input"]),
        )
        self._set_style_dasar_zoom(
            self.txt_cari_histori,
            self._style_tanpa_font_size(st["input"]),
        )

        # Ukuran font elemen non-tabel mengikuti konfigurasi global.
        font_sizes = get_global_font_sizes(0)
        master_font = get_master_font()
        self.lbl_judul.setFont(QFont(master_font, font_sizes["sz_title"]))
        self.lbl_judul_histori.setFont(QFont(master_font, font_sizes["sz_total"]))
        self.txt_cari.setFont(QFont(master_font, font_sizes["sz_input"]))
        self.txt_cari_histori.setFont(QFont(master_font, font_sizes["sz_input"]))

        # Blokir signal tabel sebelum zoom agar lebar tabel tidak "lompat"
        self.tabel_penerima.horizontalHeader().blockSignals(True)
        self.tabel_histori.horizontalHeader().blockSignals(True)

        self._sedang_menerapkan_zoom = True
        try:
            # Terapkan style dan zoom hanya pada tabel kiri dan kanan.
            zoom_helper.terapkan_zoom_semua_elemen(
                container_widget=self.tabel_penerima,
                z=z,
                is_dark=is_dark,
            )
            zoom_helper.terapkan_zoom_semua_elemen(
                container_widget=self.tabel_histori,
                z=z,
                is_dark=is_dark,
            )
        finally:
            self._sedang_menerapkan_zoom = False
            self.tabel_penerima.horizontalHeader().blockSignals(False)
            self.tabel_histori.horizontalHeader().blockSignals(False)

        # Paksa skala kolom tabel
        zoom_helper._skalakan_kolom_tableview(self.tabel_penerima, z)
        zoom_helper._skalakan_kolom_tableview(self.tabel_histori, z)

        terap_semua_placeholder_dinamis(
            self,
            is_dark=is_dark,
        )