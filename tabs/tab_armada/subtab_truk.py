# tabs/tab_armada/subtab_truk.py
import os
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

import services.database_service as db_service

from themes.modules.kontak_armada import get_armada_styles

from utils.typography import MASTER_FONT, get_global_font_sizes
from utils.mixins import ZoomTableMixin
from utils.table_helper import buat_tabel_item
import utils.zoom as zoom_helper
from utils.widget_helpers import (
    paksa_kapital_lineedit as helper_paksa_kapital_lineedit,
    terapkan_popup_combobox_bawah,
)
from utils.placeholder_helper import (
    terap_semua_placeholder_dinamis,
)


class SubTabTruk(QWidget, ZoomTableMixin):
    KOL_NO = 0
    KOL_JENIS = 1
    KOL_NO_POLISI = 2
    KOL_NAMA_SOPIR = 3
    KOL_NO_HP = 4
    KOL_KETERANGAN = 5
    KOL_FOTO = 6

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "SubTabTruk"
    SETTINGS_KEY_LEBAR = "lebar_kolom_truk"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.mode = 'IDLE'
        self.current_foto_path = ""
        self._sedang_menerapkan_zoom = False
        self._sedang_menerapkan_tema = False
        self._identitas_terpilih = ""
        self._lewati_refresh_show_pertama = False

        # Menunda penyimpanan sampai pengguna selesai menggeser header.
        # Ini mencegah QSettings ditulis berkali-kali selama proses drag.
        self._timer_simpan_lebar = QTimer(self)
        self._timer_simpan_lebar.setSingleShot(True)
        self._timer_simpan_lebar.setInterval(250)

        self.init_ui()

    def init_ui(self):
        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(10, 10, 10, 10)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout_utama.addWidget(self.splitter)

        # ========================================================
        # PANEL KIRI: Master Data (Pencarian & Tabel)
        # ========================================================
        self.panel_kiri = QWidget()
        self.panel_kiri.setMinimumWidth(600)
        self.panel_kiri.setMaximumWidth(1800)
        layout_kiri = QVBoxLayout(self.panel_kiri)
        layout_kiri.setContentsMargins(0, 0, 10, 0)

        layout_judul_search = QHBoxLayout()
        self.label_judul = QLabel("🚚 List Data Truk")
        self.label_judul.setFont(QFont(MASTER_FONT, 14, QFont.Weight.Bold))
        layout_judul_search.addWidget(self.label_judul)
        layout_judul_search.addStretch()

        self.input_cari = QLineEdit()
        self.input_cari.setPlaceholderText("Cari truk...")
        self.input_cari.setProperty("zoom_font_key", "sz_input")
        self.input_cari.setFixedWidth(230)
        self.input_cari.textChanged.connect(
            lambda _t: helper_paksa_kapital_lineedit(self.input_cari),
        )
        self.input_cari.textChanged.connect(self.filter_tabel_truk)
        layout_judul_search.addWidget(self.input_cari)
        layout_kiri.addLayout(layout_judul_search)

        self.tabel_truk = QTableWidget()
        self.tabel_truk.setColumnCount(7)
        self.tabel_truk.setHorizontalHeaderLabels([
            "NO", "JENIS", "NO. POL", "NAMA SOPIR", "NO. HP", "KETERANGAN", "FOTO"
        ])

        self.tabel_truk.setColumnHidden(6, True)
        self.tabel_truk.setAlternatingRowColors(True)
        self.tabel_truk.verticalHeader().setVisible(False)

        # Jangan mengunci tinggi header/baris. Zoom global akan menghitung
        # tinggi berdasarkan font dan padding aktual agar teks tidak terpotong.
        header_truk = self.tabel_truk.horizontalHeader()
        header_truk.setMinimumHeight(35)
        header_truk.setMaximumHeight(16_777_215)

        vertical_header_truk = self.tabel_truk.verticalHeader()
        vertical_header_truk.setMinimumSectionSize(32)
        vertical_header_truk.setDefaultSectionSize(32)

        # Data Armada satu baris; cegah word-wrap yang membuat tinggi tidak stabil.
        self.tabel_truk.setWordWrap(False)
        self.tabel_truk.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.tabel_truk.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.tabel_truk.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel_truk.cellClicked.connect(self.pilih_data_dari_tabel)
        layout_kiri.addWidget(self.tabel_truk)

        self.load_lebar_kolom(self.tabel_truk)
        self.tabel_truk.horizontalHeader().sectionResized.connect(
            self.jadwalkan_simpan_lebar_kolom
        )
        self._timer_simpan_lebar.timeout.connect(
            self._simpan_lebar_kolom_sekarang
        )

        # ========================================================
        # PANEL KANAN: Detail & Editor Area
        # ========================================================
        self.panel_kanan = QFrame()
        self.panel_kanan.setMinimumWidth(320)
        self.panel_kanan.setMaximumWidth(950)
        self.panel_kanan.setObjectName("panelEditor")
        layout_kanan = QVBoxLayout(self.panel_kanan)
        layout_kanan.setContentsMargins(15, 15, 15, 15)

        self.lbl_judul_kanan = QLabel("📋 Detail / Editor truk")
        self.lbl_judul_kanan.setFont(QFont(MASTER_FONT, 12, QFont.Weight.Bold))
        self.lbl_judul_kanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_kanan.addWidget(self.lbl_judul_kanan)

        self.lbl_jenis = QLabel("Jenis Truk:")
        self.combo_jenis = QComboBox()
        self.combo_jenis.addItem("- Pilih jenis -")
        self.combo_jenis.addItems(["TB", "Tronton", "CDD", "Pick-up", "Lainnya..."])
        self.combo_jenis.setEditable(False)
        self.combo_jenis.setProperty("zoom_font_key", None)
        self.combo_jenis.currentIndexChanged.connect(self.on_jenis_truk_changed)
        layout_kanan.addWidget(self.lbl_jenis)
        layout_kanan.addWidget(self.combo_jenis)

        self.lbl_jenis_lain = QLabel("Jenis Truk Lainnya:")
        self.input_jenis_lain = QLineEdit()
        self.input_jenis_lain.setPlaceholderText("Contoh: FUSO WINGBOX")
        self.input_jenis_lain.setProperty("zoom_font_key", "sz_input")
        self.input_jenis_lain.textChanged.connect(
            lambda _t: helper_paksa_kapital_lineedit(self.input_jenis_lain)
        )
        self.lbl_jenis_lain.hide()
        self.input_jenis_lain.hide()
        layout_kanan.addWidget(self.lbl_jenis_lain)
        layout_kanan.addWidget(self.input_jenis_lain)

        self.lbl_nopol = QLabel("No. Polisi:")
        self.input_nopol = QLineEdit()
        self.input_nopol.setPlaceholderText("Contoh: L 1234 AB")
        self.input_nopol.setProperty("zoom_font_key", "sz_input")
        self.input_nopol.textChanged.connect(
            lambda _t: helper_paksa_kapital_lineedit(self.input_nopol),
        )
        layout_kanan.addWidget(self.lbl_nopol)
        layout_kanan.addWidget(self.input_nopol)

        self.lbl_sopir = QLabel("Nama Sopir:")
        self.input_sopir = QLineEdit()
        self.input_sopir.setPlaceholderText("Masukkan Nama")
        self.input_sopir.setProperty("zoom_font_key", "sz_input")
        self.input_sopir.textChanged.connect(
            lambda _t: helper_paksa_kapital_lineedit(self.input_sopir),
        )
        layout_kanan.addWidget(self.lbl_sopir)
        layout_kanan.addWidget(self.input_sopir)

        self.lbl_hp = QLabel("No. HP / WA:")
        self.input_hp_sopir = QLineEdit()
        self.input_hp_sopir.setPlaceholderText("081xxx")
        self.input_hp_sopir.setProperty("zoom_font_key", "sz_input")
        layout_kanan.addWidget(self.lbl_hp)
        layout_kanan.addWidget(self.input_hp_sopir)

        self.lbl_ket = QLabel("Keterangan:")
        self.input_keterangan = QLineEdit()
        self.input_keterangan.setPlaceholderText("Milik Perusahaan / Sewa")
        self.input_keterangan.setProperty("zoom_font_key", "sz_input")
        self.input_keterangan.textChanged.connect(
            lambda _t: helper_paksa_kapital_lineedit(self.input_keterangan),
        )
        layout_kanan.addWidget(self.lbl_ket)
        layout_kanan.addWidget(self.input_keterangan)

        layout_kanan.addSpacing(10)
        self.lbl_foto_title = QLabel("📷 Foto truk:")
        layout_kanan.addWidget(self.lbl_foto_title)

        self.lbl_preview_foto = QLabel("Tidak Ada Foto")
        self.lbl_preview_foto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_foto.setFixedHeight(180)
        self.lbl_preview_foto.setStyleSheet(
            f"""
                border: 2px dashed #9ca3af;
                border-radius: 8px;
                color: #9ca3af;
                background-color: transparent;
            """
        )
        layout_kanan.addWidget(self.lbl_preview_foto)

        self.btn_pilih_foto = QPushButton("📂 Lampirkan Foto Baru")

        self.btn_pilih_foto.setProperty("zoom_font_key", None)
        self.btn_pilih_foto.clicked.connect(self.pilih_foto_truk)
        layout_kanan.addWidget(self.btn_pilih_foto)
        layout_kanan.addStretch()

        hbox_tombol = QHBoxLayout()
        self.btn_aksi = QPushButton("Aksi")
        self.btn_aksi.setFixedHeight(40)
        self.btn_aksi.clicked.connect(self.handle_tombol_aksi)

        self.btn_batal = QPushButton("❌ Batal")
        self.btn_batal.setFixedHeight(40)
        self.btn_batal.clicked.connect(lambda: self.atur_mode('IDLE'))

        hbox_tombol.addWidget(self.btn_batal)
        hbox_tombol.addWidget(self.btn_aksi)
        layout_kanan.addLayout(hbox_tombol)

        self.splitter.addWidget(self.panel_kiri)
        self.splitter.addWidget(self.panel_kanan)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([650, 350])

        self.atur_mode('IDLE')
        self.refresh_session_ui()
        self._lewati_refresh_show_pertama = True
        terapkan_popup_combobox_bawah(self)

    # ============================================================
    # LIFECYCLE & REFRESH
    # ============================================================

    def refresh_session_ui(self):
        """Memuat ulang tabel tanpa menghilangkan filter dan state editor aktif."""
        self.refresh_tabel()

        if self.mode == "PREVIEW" and self._identitas_terpilih:
            if not self._sinkronkan_preview_terpilih():
                self.atur_mode("IDLE")

        self._terapkan_placeholder_dinamis()

    def showEvent(self, event):
        super().showEvent(event)
        terapkan_popup_combobox_bawah(self)

        # init_ui sudah memuat data. Hindari query kedua pada show pertama.
        if self._lewati_refresh_show_pertama:
            self._lewati_refresh_show_pertama = False
            self._terapkan_placeholder_dinamis()
            return

        self.refresh_session_ui()

    # ============================================================
    # MODE STATE & FORM
    # ============================================================

    def atur_mode(self, mode):
        self.mode = mode
        if mode == 'IDLE':
            self.bersihkan_form()
            self.aktifkan_input(False)
            self.tabel_truk.clearSelection()
            self.btn_aksi.setText("➕ Tambah truk")
            self.btn_batal.hide()
            self.btn_pilih_foto.hide()
        elif mode == 'TAMBAH':
            self.bersihkan_form()
            self.aktifkan_input(True)
            self.input_nopol.setReadOnly(False)
            self.btn_aksi.setText("💾 Simpan truk")
            self.btn_batal.show()
            self.btn_pilih_foto.show()
        elif mode == 'PREVIEW':
            self.aktifkan_input(False)
            self.btn_aksi.setText("✏️ Edit")
            self.btn_batal.hide()
            self.btn_pilih_foto.hide()
        elif mode == 'EDIT':
            self.aktifkan_input(True)
            self.input_nopol.setReadOnly(True)
            self.btn_aksi.setText("💾 Simpan")
            self.btn_batal.show()
            self.btn_pilih_foto.show()
        self.sesuaikan_tema_lokal()

    def aktifkan_input(self, aktif):
        self.combo_jenis.setEnabled(aktif)
        self.input_jenis_lain.setReadOnly(not aktif)
        self.input_nopol.setReadOnly(not aktif)
        self.input_sopir.setReadOnly(not aktif)
        self.input_hp_sopir.setReadOnly(not aktif)
        self.input_keterangan.setReadOnly(not aktif)
        self.on_jenis_truk_changed(self.combo_jenis.currentIndex())

    def _atur_placeholder_combo_jenis(self):
        """
        Membuat pilihan awal ComboBox miring hanya saat sedang aktif.
        """
        if not hasattr(self, "combo_jenis"):
            return

        index_aktif = self.combo_jenis.currentIndex()

        font_utama = QFont(self.combo_jenis.font())
        font_utama.setItalic(index_aktif == 0)
        self.combo_jenis.setFont(font_utama)

        font_placeholder = QFont(font_utama)
        font_placeholder.setItalic(True)
        self.combo_jenis.setItemData(
            0,
            font_placeholder,
            Qt.ItemDataRole.FontRole,
        )

        font_normal = QFont(font_utama)
        font_normal.setItalic(False)

        for index in range(1, self.combo_jenis.count()):
            self.combo_jenis.setItemData(
                index,
                font_normal,
                Qt.ItemDataRole.FontRole,
            )

    def _terapkan_placeholder_dinamis(self):
        """Memperbarui placeholder sesuai isi input dan tema aktif."""
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
        self._atur_placeholder_combo_jenis()

    def on_jenis_truk_changed(self, _index=None):
        """Menampilkan input khusus hanya ketika pilihan Lainnya digunakan."""
        pilih_lainnya = self.combo_jenis.currentText().strip() == "Lainnya..."
        self.lbl_jenis_lain.setVisible(pilih_lainnya)
        self.input_jenis_lain.setVisible(pilih_lainnya)

        if not pilih_lainnya:
            self.input_jenis_lain.clear()

        self._atur_placeholder_combo_jenis()

    def ambil_jenis_truk_final(self):
        """Menghasilkan nama jenis truk yang siap disimpan ke database."""
        pilihan = self.combo_jenis.currentText().strip()
        if pilihan == "Lainnya...":
            return self.input_jenis_lain.text().strip().upper()
        if self.combo_jenis.currentIndex() <= 0:
            return ""
        return pilihan

    def set_jenis_truk_form(self, jenis):
        """Memilih jenis baku atau mengalihkan jenis tidak umum ke Lainnya."""
        jenis_bersih = str(jenis or "").strip()
        if not jenis_bersih:
            self.combo_jenis.setCurrentIndex(0)
            return

        for index in range(1, self.combo_jenis.count()):
            item_text = self.combo_jenis.itemText(index)
            if item_text == "Lainnya...":
                continue
            if item_text.casefold() == jenis_bersih.casefold():
                self.combo_jenis.setCurrentIndex(index)
                return

        idx_lainnya = self.combo_jenis.findText(
            "Lainnya...",
            Qt.MatchFlag.MatchFixedString,
        )
        self.combo_jenis.setCurrentIndex(idx_lainnya)
        self.input_jenis_lain.setText(jenis_bersih.upper())

    def bersihkan_form(self):
        self._identitas_terpilih = ""
        self.combo_jenis.setCurrentIndex(0)
        self.input_jenis_lain.clear()
        self.input_nopol.clear()
        self.input_sopir.clear()
        self.input_hp_sopir.clear()
        self.input_keterangan.clear()
        self.current_foto_path = ""
        self.lbl_preview_foto.clear()
        self.lbl_preview_foto.setText("Tidak Ada Foto")

    def handle_tombol_aksi(self):
        if self.mode == 'IDLE':
            self.atur_mode('TAMBAH')
        elif self.mode == 'TAMBAH':
            self.simpan_atau_update_truk()
        elif self.mode == 'PREVIEW':
            self.atur_mode('EDIT')
        elif self.mode == 'EDIT':
            self.simpan_atau_update_truk()

    # ============================================================
    # FOTO truk
    # ============================================================

    def pilih_foto_truk(self):
        options = QFileDialog.Option(0)
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Pilih Foto Unit truk", "",
            "Images (*.png *.jpeg *.jpg *.bmp)", options=options
        )
        if file_path:
            self.current_foto_path = file_path
            self.tampilkan_foto(file_path)

    def tampilkan_foto(self, path):
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            self.lbl_preview_foto.setPixmap(
                pixmap.scaled(
                    self.lbl_preview_foto.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
        else:
            self.lbl_preview_foto.clear()
            self.lbl_preview_foto.setText("Tidak Ada Foto")

    # ============================================================
    # LEBAR KOLOM MENGGUNAKAN MIXIN
    # ============================================================

    def _settings_kolom(self):
        return QSettings(
            self.SETTINGS_ORGANIZATION,
            self.SETTINGS_APPLICATION,
        )

    def jadwalkan_simpan_lebar_kolom(self, *_args):
        """
        Menyimpan lebar setelah proses drag selesai.

        Resize yang berasal dari proses zoom tidak boleh dianggap sebagai
        perubahan manual pengguna.
        """
        if self._sedang_menerapkan_zoom:
            return

        self._timer_simpan_lebar.start()

    def _simpan_lebar_kolom_sekarang(self):
        if not hasattr(self, "tabel_truk"):
            return

        self.simpan_lebar_kolom(self.tabel_truk)

    def simpan_lebar_kolom(self, tabel):
        if self._sedang_menerapkan_zoom:
            return

        # Penting: zoom SubTabTruk mengikuti key TabArmada.
        # Dengan key yang sama, lebar tampilan dikembalikan dahulu ke
        # ukuran dasar sebelum disimpan, sehingga tidak membesar/mengecil
        # berulang kali ketika tab dibuka kembali.
        widths = self._lebar_dasar_tabel(
            tabel,
            zoom_key="TabArmada",
        )

        self._perbarui_cache_lebar_zoom(
            tabel,
            widths,
        )

        settings = self._settings_kolom()
        settings.setValue(
            self.SETTINGS_KEY_LEBAR,
            [int(width) for width in widths],
        )
        settings.sync()

    @staticmethod
    def _normalisasi_daftar_lebar(value):
        if not isinstance(value, (list, tuple)):
            return None

        hasil = []
        try:
            for width in value:
                hasil.append(min(max(20, int(width)), 1500))
        except (TypeError, ValueError):
            return None

        return hasil

    def load_lebar_kolom(self, tabel):
        default_widths = [
            45,   # NO
            80,   # JENIS
            110,  # NO. POL
            140,  # NAMA SOPIR
            120,  # NO. HP
            250,  # KETERANGAN / dasar sebelum Stretch
            20,   # FOTO tersembunyi
        ]

        header = tabel.horizontalHeader()
        header.blockSignals(True)
        self._sedang_menerapkan_zoom = True

        try:
            saved_widths = self._normalisasi_daftar_lebar(
                self._settings_kolom().value(
                    self.SETTINGS_KEY_LEBAR
                )
            )

            if (
                saved_widths
                and len(saved_widths) == tabel.columnCount()
            ):
                base_widths = saved_widths
            else:
                base_widths = default_widths[:tabel.columnCount()]

                while len(base_widths) < tabel.columnCount():
                    base_widths.append(110)

            # Kolom 0–4 dapat diatur manual.
            for index in range(min(5, tabel.columnCount())):
                tabel.setColumnWidth(
                    index,
                    int(base_widths[index]),
                )

            # Keterangan tetap mengisi ruang yang tersisa.
            if tabel.columnCount() > 5:
                header.setSectionResizeMode(
                    5,
                    QHeaderView.ResizeMode.Stretch,
                )

            self._perbarui_cache_lebar_zoom(
                tabel,
                base_widths,
            )

        except Exception as exc:
            print(
                f"Error memuat lebar kolom Truk: {exc}"
            )

        finally:
            self._sedang_menerapkan_zoom = False
            header.blockSignals(False)

    # ============================================================
    # DATA & TABEL truk
    # ============================================================

    @staticmethod
    def _normalisasi_teks(value, kapital=False):
        hasil = str(value or "").strip()
        return hasil.upper() if kapital else hasil

    def _isi_form_dari_baris(self, row, ubah_mode=True):
        item_nopol = self.tabel_truk.item(row, self.KOL_NO_POLISI)
        if not item_nopol:
            return False

        if ubah_mode:
            self.atur_mode("PREVIEW")

        nopol = item_nopol.text().strip().upper()
        self._identitas_terpilih = nopol
        self.input_nopol.setText(nopol)

        item_sopir = self.tabel_truk.item(row, self.KOL_NAMA_SOPIR)
        self.input_sopir.setText(item_sopir.text() if item_sopir else "")

        item_hp = self.tabel_truk.item(row, self.KOL_NO_HP)
        hp_val = item_hp.text() if item_hp else ""
        self.input_hp_sopir.setText("" if hp_val in ("-", "None") else hp_val)

        item_keterangan = self.tabel_truk.item(row, self.KOL_KETERANGAN)
        self.input_keterangan.setText(
            item_keterangan.text() if item_keterangan else ""
        )

        item_jenis = self.tabel_truk.item(row, self.KOL_JENIS)
        self.set_jenis_truk_form(item_jenis.text() if item_jenis else "")

        item_foto = self.tabel_truk.item(row, self.KOL_FOTO)
        foto_val = item_foto.text() if item_foto else ""
        self.current_foto_path = (
            foto_val if foto_val and foto_val != "None" else ""
        )
        self.tampilkan_foto(self.current_foto_path)
        return True

    def _sinkronkan_preview_terpilih(self):
        for row in range(self.tabel_truk.rowCount()):
            item_nopol = self.tabel_truk.item(row, self.KOL_NO_POLISI)
            if (
                item_nopol
                and item_nopol.text().strip().upper() == self._identitas_terpilih
            ):
                return self._isi_form_dari_baris(row, ubah_mode=False)
        return False

    def refresh_tabel(self):
        self.tabel_truk.blockSignals(True)
        self.tabel_truk.setRowCount(0)
        try:
            rows = db_service.ambil_semua_truk_full()
            for i, row in enumerate(rows):
                baris = self.tabel_truk.rowCount()
                self.tabel_truk.insertRow(baris)

                # 💡 Mendeklarasikan variabel agar lebih deskriptif dan mudah dibaca
                no_urut = str(i + 1)
                nopol = self._normalisasi_teks(
                    row[0] if len(row) > 0 else "",
                    kapital=True,
                )
                jenis = self._normalisasi_teks(
                    row[1] if len(row) > 1 else "",
                )
                sopir = self._normalisasi_teks(
                    row[2] if len(row) > 2 else "",
                    kapital=True,
                )
                hp = self._normalisasi_teks(
                    row[3] if len(row) > 3 else "",
                )
                ket = self._normalisasi_teks(
                    row[4] if len(row) > 4 else "",
                    kapital=True,
                )
                foto = self._normalisasi_teks(
                    row[5] if len(row) > 5 else "",
                )

                # 💡 Menggunakan fungsi buat_tabel_item()
                self.tabel_truk.setItem(
                    baris,
                    self.KOL_NO,
                    buat_tabel_item(
                        no_urut,
                        editable=False,
                        alignment=Qt.AlignmentFlag.AlignCenter,
                    ),
                )
                self.tabel_truk.setItem(
                    baris,
                    self.KOL_JENIS,
                    buat_tabel_item(
                        jenis,
                        editable=False,
                        alignment=Qt.AlignmentFlag.AlignCenter,
                    ),
                )
                self.tabel_truk.setItem(baris, self.KOL_NO_POLISI, buat_tabel_item(
                    nopol,
                    editable=False,
                    alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ))
                self.tabel_truk.setItem(baris, self.KOL_NAMA_SOPIR, buat_tabel_item(
                    sopir,
                    editable=False,
                    alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ))
                self.tabel_truk.setItem(
                    baris,
                    self.KOL_NO_HP,
                    buat_tabel_item(
                        hp,
                        editable=False,
                        alignment=Qt.AlignmentFlag.AlignCenter,
                    ),
                )
                self.tabel_truk.setItem(baris, self.KOL_KETERANGAN, buat_tabel_item(
                    ket,
                    editable=False,
                    alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ))
                self.tabel_truk.setItem(baris, self.KOL_FOTO, buat_tabel_item(foto, editable=False))

            self.filter_tabel_truk(self.input_cari.text())
        except Exception as e:
            print(f"Error Load Tabel truk: {e}")
        finally:
            self.tabel_truk.blockSignals(False)

    def filter_tabel_truk(self, text):
        kata_kunci = text.lower().strip()
        nomor_baru = 1

        for row in range(self.tabel_truk.rowCount()):
            harus_muncul = False
            for col in (
                self.KOL_JENIS,
                self.KOL_NO_POLISI,
                self.KOL_NAMA_SOPIR,
                self.KOL_NO_HP,
                self.KOL_KETERANGAN,
            ):
                item = self.tabel_truk.item(row, col)
                if item and kata_kunci in item.text().lower():
                    harus_muncul = True
                    break

            if harus_muncul:
                self.tabel_truk.setRowHidden(row, False)
                self.tabel_truk.item(row, self.KOL_NO).setText(str(nomor_baru))
                nomor_baru += 1
            else:
                self.tabel_truk.setRowHidden(row, True)

    def simpan_atau_update_truk(self):
        nopol = self.input_nopol.text().strip().upper()
        sopir = self.input_sopir.text().strip().upper()
        hp = self.input_hp_sopir.text().strip()
        jenis = self.ambil_jenis_truk_final()
        ket = self.input_keterangan.text().strip().upper()
        foto = self.current_foto_path

        if not nopol:
            QMessageBox.warning(self, "Peringatan", "No. Polisi wajib diisi!")
            self.input_nopol.setFocus()
            return

        if not jenis:
            if self.combo_jenis.currentText().strip() == "Lainnya...":
                QMessageBox.warning(
                    self,
                    "Peringatan",
                    "Jenis Truk Lainnya wajib diisi!",
                )
                self.input_jenis_lain.setFocus()
            else:
                QMessageBox.warning(self, "Peringatan", "Jenis Truk wajib dipilih!")
                self.combo_jenis.setFocus()
            return

        try:
            sukses, pesan = db_service.simpan_atau_update_truk_full(
                nopol, jenis, sopir, hp, ket, foto, mode=self.mode
            )

            if not sukses:
                QMessageBox.warning(self, "Data truk", pesan)
                return

            QMessageBox.information(
                self,
                "Sukses",
                f"Data truk {nopol} berhasil disimpan!",
            )
            self.atur_mode('IDLE')
            self.refresh_session_ui()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Database",
                f"Gagal menyimpan data:\n{str(e)}",
            )

    def pilih_data_dari_tabel(self, row, column):
        try:
            self._isi_form_dari_baris(row, ubah_mode=True)
        except Exception as e:
            print(f"Error Select Row: {e}")

    # ============================================================
    # TEMA DAN ZOOM
    # ============================================================

    def _kunci_tombol_foto_statis(self):
        """
        Menjaga tombol lampiran foto tetap konsisten seperti pada SubTabKapal.

        ComboBox Jenis Truk tidak lagi ditata ulang melalui callback terpisah,
        karena penataan ganda menyebabkan perubahan font/geometry tertunda dan
        membuat perpindahan zoom terlihat meloncat.
        """
        if not hasattr(self, "btn_pilih_foto"):
            return

        font_statis_base = zoom_helper.batasi_ukuran_font(
            get_global_font_sizes(0).get("sz_base", 10), default=10
        )

        style_btn_foto = getattr(
            self,
            "_style_btn_foto_truk",
            "QPushButton { background-color: #e2e8f0; color: #0f172a; "
            "border: 1px solid #cbd5e1; border-radius: 4px; } "
            "QPushButton:hover { background-color: #cbd5e1; }"
        )

        font_foto = QFont(MASTER_FONT, font_statis_base)
        self.btn_pilih_foto.setProperty("zoom_font_key", None)
        self.btn_pilih_foto.setFont(font_foto)
        self.btn_pilih_foto.setMinimumHeight(30)
        self.btn_pilih_foto.setMaximumHeight(30)
        self.btn_pilih_foto.setStyleSheet(
            style_btn_foto
            + f"""
            QPushButton {{
                font-family: '{MASTER_FONT}';
                font-size: {font_statis_base}pt;
                padding: 2px 6px;
            }}
            """
        )
        self.btn_pilih_foto.updateGeometry()

    def sesuaikan_tema_lokal(self):
        if self._sedang_menerapkan_tema:
            return

        self._sedang_menerapkan_tema = True
        try:
            win = self.window()
            is_dark = win.current_theme == "dark" if win and hasattr(
                win,
                "current_theme",
            ) else False
            z = zoom_helper.dapatkan_zoom_level("TabArmada")

            st = get_armada_styles(is_dark, self.mode)
            self._style_btn_foto_truk = st["btn_foto"]

            # --- 1. RESET MARGIN SEBELUM ZOOM ---
            self.layout().setContentsMargins(10, 10, 10, 10)
            self.panel_kiri.layout().setContentsMargins(0, 0, 10, 0)
            self.panel_kanan.layout().setContentsMargins(15, 15, 15, 15)

            # --- 3. BLOKIR SIGNAL & TERAPKAN ZOOM ---
            header = self.tabel_truk.horizontalHeader()
            header.blockSignals(True)
            self._sedang_menerapkan_zoom = True
            try:
                zoom_helper.terapkan_zoom_semua_elemen(
                    container_widget=self, z=z, is_dark=is_dark
                )
            finally:
                self._sedang_menerapkan_zoom = False
                header.blockSignals(False)

            # --- 4. TERAPKAN TEMA SETELAH ZOOM ---
            # Urutan ini mencegah cache stylesheet zoom mengembalikan warna
            # mode terang ketika aplikasi sedang menggunakan mode gelap.
            self.panel_kanan.setStyleSheet(st["panel_kanan"])
            self.label_judul.setStyleSheet(st["label_judul"])
            self.input_cari.setStyleSheet(st["input_normal"])
            self.lbl_judul_kanan.setStyleSheet(st["label_judul_kanan"])

            # --- 5. PAKSA SKALA KOLOM TABEL ---

            # --- 6. KUNCI PAKSA UKURAN INPUT & TOMBOL (ANTI-MELAR) ---
            ukuran_font = get_global_font_sizes(0)
            ukuran_statis = zoom_helper.batasi_ukuran_font(
                ukuran_font.get("sz_input", 10), default=10
            )
            font_base = zoom_helper.batasi_ukuran_font(
                ukuran_font.get("sz_base", 10), default=10
            )

            # Pencarian Kiri
            font_cari = self.input_cari.font()
            font_cari.setPointSize(ukuran_statis)
            self.input_cari.setFont(font_cari)
            self.input_cari.setFixedHeight(30)
            self.input_cari.setFixedWidth(230)

            # Judul Panel Kanan
            font_judul_kanan = QFont(MASTER_FONT, font_base + 1, QFont.Weight.Bold)
            self.lbl_judul_kanan.setFont(font_judul_kanan)

            # Label Kanan
            font_label = QFont(MASTER_FONT, font_base)
            for label in [
                self.lbl_jenis,
                self.lbl_jenis_lain,
                self.lbl_nopol,
                self.lbl_sopir,
                self.lbl_hp,
                self.lbl_ket,
                self.lbl_foto_title,
            ]:
                label.setFont(font_label)

            # Editor Form Input
            font_input = QFont(MASTER_FONT, ukuran_statis)
            line_edits = [
                self.input_jenis_lain,
                self.input_nopol,
                self.input_sopir,
                self.input_hp_sopir,
                self.input_keterangan,
            ]

            for widget in line_edits:
                widget.setFont(font_input)
                widget.setFixedHeight(30)  # Mengunci input agar tidak melar
                style_aktif = st["input_locked"] if widget.isReadOnly() or not widget.isEnabled() else st["input_normal"]
                widget.setStyleSheet(style_aktif)

            # Khusus ComboBox
            self.combo_jenis.setFont(font_input)
            self.combo_jenis.setFixedHeight(30)
            self.combo_jenis.setStyleSheet(
                st["input_locked"] if not self.combo_jenis.isEnabled() else st["input_normal"],
            )
            combo_view = self.combo_jenis.view()
            if combo_view is not None:
                combo_view.setFont(font_input)
                combo_view.setStyleSheet(
                    f"""
                        QAbstractItemView {{
                            font-family: '{MASTER_FONT}';
                            font-size: {ukuran_statis}pt;
                        }}
                        QAbstractItemView::item {{
                            min-height: 26px;
                            max-height: 26px;
                            padding: 2px 5px;
                        }}
                    """
                )

            # Tombol Aksi Kanan
            font_btn = QFont(MASTER_FONT, font_base, QFont.Weight.Bold)
            self.btn_batal.setFont(font_btn)
            self.btn_batal.setFixedHeight(38)
            self.btn_batal.setStyleSheet(st["btn_batal"])

            self.btn_aksi.setFont(font_btn)
            self.btn_aksi.setFixedHeight(38)
            self.btn_aksi.setStyleSheet(st["btn_aksi"])

            self.btn_pilih_foto.setFont(font_label)
            self.btn_pilih_foto.setStyleSheet(st["btn_foto"])
            self._kunci_tombol_foto_statis()

            # --- 7. KUNCI ULANG MARGIN SETELAH ZOOM (Kunci Mati Jarak) ---
            self.layout().setContentsMargins(10, 10, 10, 10)
            self.panel_kiri.layout().setContentsMargins(0, 0, 10, 0)
            self.panel_kanan.layout().setContentsMargins(15, 15, 15, 15)

            # Terapkan ulang setelah style dan zoom selesai agar
            # placeholder tidak ikut memakai font teks aktif.
            self._terapkan_placeholder_dinamis()

        finally:
            self._sedang_menerapkan_tema = False