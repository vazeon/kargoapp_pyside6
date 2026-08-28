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
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

import services.database_service as db_service

from themes.modules.kontak_armada import get_armada_styles

from utils.typography import get_master_font, get_global_font_sizes_pt
from utils.mixins import ZoomTableMixin
from utils.table_helper import buat_tabel_item
import utils.zoom as zoom_helper
from utils.widget_helpers import atur_tinggi_input, paksa_kapital_lineedit as helper_paksa_kapital_lineedit
from utils.modules.armada_metrics import (
    ARMADA_ACTION_BUTTON_INITIAL_HEIGHT,
    ARMADA_ACTION_BUTTON_MIN_HEIGHT,
    ARMADA_COLUMN_FALLBACK_WIDTH,
    ARMADA_COLUMN_WIDTH_MAX,
    ARMADA_COLUMN_WIDTH_MIN,
    ARMADA_EDITOR_PANEL_MARGINS,
    ARMADA_EDITOR_PANEL_MAX_WIDTH,
    ARMADA_EDITOR_PANEL_MIN_WIDTH,
    ARMADA_EDITOR_SECTION_GAP,
    ARMADA_MASTER_PANEL_MARGINS,
    ARMADA_MASTER_PANEL_MAX_WIDTH,
    ARMADA_MASTER_PANEL_MIN_WIDTH,
    ARMADA_PAGE_MARGINS,
    ARMADA_PHOTO_BUTTON_MIN_HEIGHT,
    ARMADA_PHOTO_PREVIEW_HEIGHT,
    ARMADA_SEARCH_WIDTH,
    ARMADA_TABLE_HEADER_MIN_HEIGHT,
    ARMADA_TABLE_ROW_BASE_HEIGHT,
    ARMADA_TRUK_COLUMN_WIDTHS,
)

def _buat_font_pt(ukuran_pt: float, *, tebal: bool = False) -> QFont:
    """Membuat QFont berbasis point untuk elemen UI statis."""
    font = QFont(get_master_font())
    font.setPointSizeF(float(ukuran_pt))
    font.setBold(bool(tebal))
    return font

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

    HEADERS = ("NO", "JENIS", "NO. POL", "NAMA SOPIR", "NO. HP", "KETERANGAN", "FOTO")
    DEFAULT_COLUMN_WIDTHS = ARMADA_TRUK_COLUMN_WIDTHS
    FILTER_COLUMNS = (
        KOL_JENIS,
        KOL_NO_POLISI,
        KOL_NAMA_SOPIR,
        KOL_NO_HP,
        KOL_KETERANGAN,
    )

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
        layout_utama.setContentsMargins(*ARMADA_PAGE_MARGINS)

        self.layout_panel = QHBoxLayout()
        self.layout_panel.setSpacing(0)
        layout_utama.addLayout(self.layout_panel)

        self._bangun_panel_master_truk()
        self._bangun_panel_editor_truk()
        self._konfigurasi_panel()

        self.atur_mode("IDLE")
        self.refresh_session_ui()
        self._lewati_refresh_show_pertama = True

    def _buat_input_kapital(self, placeholder):
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        widget.textChanged.connect(
            lambda _text, target=widget: helper_paksa_kapital_lineedit(target),
        )
        atur_tinggi_input(widget)
        return widget

    def _buat_field_truk(self, layout, label_text, placeholder, kapital=True):
        label = QLabel(label_text)
        editor = self._buat_input_kapital(placeholder) if kapital else QLineEdit()
        if not kapital:
            editor.setPlaceholderText(placeholder)
            atur_tinggi_input(editor)
        layout.addWidget(label)
        layout.addWidget(editor)
        return label, editor

    def _bangun_panel_master_truk(self):
        self.panel_kiri = QWidget()
        self.panel_kiri.setMinimumWidth(ARMADA_MASTER_PANEL_MIN_WIDTH)
        self.panel_kiri.setMaximumWidth(ARMADA_MASTER_PANEL_MAX_WIDTH)
        layout = QVBoxLayout(self.panel_kiri)
        layout.setContentsMargins(*ARMADA_MASTER_PANEL_MARGINS)

        header_layout = QHBoxLayout()
        self.label_judul = QLabel("List Data Truk")
        self.label_judul.setFont(
            _buat_font_pt(get_global_font_sizes_pt(0)["sz_title"], tebal=True)
        )
        header_layout.addWidget(self.label_judul)
        header_layout.addStretch()

        self.input_cari = self._buat_input_kapital("Cari truk...")
        self.input_cari.setFixedWidth(ARMADA_SEARCH_WIDTH)
        self.input_cari.textChanged.connect(self.filter_tabel_truk)
        header_layout.addWidget(self.input_cari)
        layout.addLayout(header_layout)

        self.tabel_truk = QTableWidget()
        tabel = self.tabel_truk
        tabel.setColumnCount(len(self.HEADERS))
        tabel.setHorizontalHeaderLabels(self.HEADERS)
        tabel.setColumnHidden(self.KOL_FOTO, True)
        tabel.setAlternatingRowColors(True)
        tabel.verticalHeader().setVisible(False)
        tabel.setWordWrap(False)
        tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabel.cellClicked.connect(self.pilih_data_dari_tabel)

        header = tabel.horizontalHeader()
        header.setMinimumHeight(ARMADA_TABLE_HEADER_MIN_HEIGHT)
        header.setMaximumHeight(16_777_215)
        tabel.verticalHeader().setMinimumSectionSize(ARMADA_TABLE_ROW_BASE_HEIGHT)
        tabel.verticalHeader().setDefaultSectionSize(ARMADA_TABLE_ROW_BASE_HEIGHT)

        self.load_lebar_kolom(tabel)
        header.sectionResized.connect(self.jadwalkan_simpan_lebar_kolom)
        self._timer_simpan_lebar.timeout.connect(self._simpan_lebar_kolom_sekarang)
        layout.addWidget(tabel)

    def _bangun_field_armada_truk(self, layout):
        self.lbl_jenis = QLabel("Jenis Truk:")
        self.combo_jenis = QComboBox()
        self.combo_jenis.addItem("- Pilih jenis -")
        self.combo_jenis.addItems(["TB", "Tronton", "CDD", "Pick-up", "Lainnya..."])
        self.combo_jenis.setEditable(False)
        self.combo_jenis.currentIndexChanged.connect(self.on_jenis_truk_changed)
        layout.addWidget(self.lbl_jenis)
        layout.addWidget(self.combo_jenis)

        self.lbl_jenis_lain, self.input_jenis_lain = self._buat_field_truk(
            layout, "Jenis Truk Lainnya:", "Contoh: FUSO WINGBOX"
        )
        self.lbl_nopol, self.input_nopol = self._buat_field_truk(
            layout, "No. Polisi:", "Contoh: L 1234 AB"
        )
        self.lbl_sopir, self.input_sopir = self._buat_field_truk(
            layout, "Nama Sopir:", "Masukkan Nama"
        )
        self.lbl_hp, self.input_hp_sopir = self._buat_field_truk(
            layout, "No. HP / WA:", "081xxx", kapital=False
        )
        self.lbl_ket, self.input_keterangan = self._buat_field_truk(
            layout, "Keterangan:", "Milik Perusahaan / Sewa"
        )
        self.lbl_jenis_lain.hide()
        self.input_jenis_lain.hide()

    def _bangun_area_foto_truk(self, layout):
        layout.addSpacing(ARMADA_EDITOR_SECTION_GAP)
        self.lbl_foto_title = QLabel("📷 Foto truk:")
        layout.addWidget(self.lbl_foto_title)
        self.lbl_preview_foto = QLabel("Tidak Ada Foto")
        self.lbl_preview_foto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_foto.setFixedHeight(ARMADA_PHOTO_PREVIEW_HEIGHT)
        layout.addWidget(self.lbl_preview_foto)
        self.btn_pilih_foto = QPushButton("📂 Lampirkan Foto Baru")
        self.btn_pilih_foto.clicked.connect(self.pilih_foto_truk)
        layout.addWidget(self.btn_pilih_foto)
        layout.addStretch()

    def _bangun_tombol_editor_truk(self, layout):
        tombol_layout = QHBoxLayout()
        self.btn_aksi = QPushButton("Aksi")
        self.btn_aksi.setFixedHeight(ARMADA_ACTION_BUTTON_INITIAL_HEIGHT)
        self.btn_aksi.clicked.connect(self.handle_tombol_aksi)
        self.btn_batal = QPushButton("❌ Batal")
        self.btn_batal.setFixedHeight(ARMADA_ACTION_BUTTON_INITIAL_HEIGHT)
        self.btn_batal.clicked.connect(lambda: self.atur_mode("IDLE"))
        tombol_layout.addWidget(self.btn_batal)
        tombol_layout.addWidget(self.btn_aksi)
        layout.addLayout(tombol_layout)

    def _bangun_panel_editor_truk(self):
        self.panel_kanan = QFrame()
        self.panel_kanan.setMinimumWidth(ARMADA_EDITOR_PANEL_MIN_WIDTH)
        self.panel_kanan.setMaximumWidth(ARMADA_EDITOR_PANEL_MAX_WIDTH)
        self.panel_kanan.setObjectName("panelEditor")
        layout = QVBoxLayout(self.panel_kanan)
        layout.setContentsMargins(*ARMADA_EDITOR_PANEL_MARGINS)

        self.lbl_judul_kanan = QLabel("Detail / Editor truk")
        self.lbl_judul_kanan.setFont(
            _buat_font_pt(get_global_font_sizes_pt(0)["sz_total"], tebal=True)
        )
        self.lbl_judul_kanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_judul_kanan)
        self._bangun_field_armada_truk(layout)
        self._bangun_area_foto_truk(layout)
        self._bangun_tombol_editor_truk(layout)

    def _konfigurasi_panel(self):
        self.layout_panel.addWidget(self.panel_kiri)
        self.layout_panel.addWidget(self.panel_kanan)

    # --- LIFECYCLE & REFRESH ---

    def refresh_session_ui(self):
        """Memuat ulang tabel tanpa menghilangkan filter dan state editor aktif."""
        self.refresh_tabel()

        if self.mode == "PREVIEW" and self._identitas_terpilih:
            if not self._sinkronkan_preview_terpilih():
                self.atur_mode("IDLE")

    def showEvent(self, event):
        super().showEvent(event)

        # init_ui sudah memuat data. Hindari query kedua pada show pertama.
        if self._lewati_refresh_show_pertama:
            self._lewati_refresh_show_pertama = False
            return

        self.refresh_session_ui()

    # --- MODE STATE & FORM ---

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

    def on_jenis_truk_changed(self, _index=None):
        """Menampilkan input khusus hanya ketika pilihan Lainnya digunakan."""
        pilih_lainnya = self.combo_jenis.currentText().strip() == "Lainnya..."
        self.lbl_jenis_lain.setVisible(pilih_lainnya)
        self.input_jenis_lain.setVisible(pilih_lainnya)

        if not pilih_lainnya:
            self.input_jenis_lain.clear()

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

    # --- FOTO truk ---

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

    # --- LEBAR KOLOM MENGGUNAKAN MIXIN ---

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
                hasil.append(min(max(ARMADA_COLUMN_WIDTH_MIN, int(width)), ARMADA_COLUMN_WIDTH_MAX))
        except (TypeError, ValueError):
            return None

        return hasil

    def load_lebar_kolom(self, tabel):
        header = tabel.horizontalHeader()
        header.blockSignals(True)
        self._sedang_menerapkan_zoom = True
        try:
            saved = self._normalisasi_daftar_lebar(
                self._settings_kolom().value(self.SETTINGS_KEY_LEBAR)
            )
            if saved and len(saved) == tabel.columnCount():
                base_widths = saved
            else:
                base_widths = list(self.DEFAULT_COLUMN_WIDTHS[:tabel.columnCount()])
                base_widths.extend([ARMADA_COLUMN_FALLBACK_WIDTH] * (tabel.columnCount() - len(base_widths)))

            for index, width in enumerate(base_widths[:min(5, tabel.columnCount())]):
                tabel.setColumnWidth(index, int(width))

            if tabel.columnCount() > self.KOL_KETERANGAN:
                header.setSectionResizeMode(
                    self.KOL_KETERANGAN,
                    QHeaderView.ResizeMode.Stretch,
                )

            self._perbarui_cache_lebar_zoom(tabel, base_widths)
        except Exception as exc:
            print(f"Error memuat lebar kolom Truk: {exc}")
        finally:
            self._sedang_menerapkan_zoom = False
            header.blockSignals(False)

    # --- DATA & TABEL truk ---

    @staticmethod
    def _normalisasi_teks(value, kapital=False):
        hasil = str(value or "").strip()
        return hasil.upper() if kapital else hasil

    def _ambil_data_form_truk_dari_baris(self, row):
        item_nopol = self.tabel_truk.item(row, self.KOL_NO_POLISI)
        if not item_nopol:
            return None

        def teks(kolom):
            item = self.tabel_truk.item(row, kolom)
            return item.text() if item else ""

        hp = teks(self.KOL_NO_HP)
        foto = teks(self.KOL_FOTO)
        return {
            "nopol": item_nopol.text().strip().upper(),
            "sopir": teks(self.KOL_NAMA_SOPIR),
            "hp": "" if hp in ("-", "None") else hp,
            "keterangan": teks(self.KOL_KETERANGAN),
            "jenis": teks(self.KOL_JENIS),
            "foto": foto if foto and foto != "None" else "",
        }

    def _terapkan_data_form_truk(self, data, ubah_mode=True):
        if not data:
            return False
        if ubah_mode:
            self.atur_mode("PREVIEW")
        self._identitas_terpilih = data["nopol"]
        self.input_nopol.setText(data["nopol"])
        self.input_sopir.setText(data["sopir"])
        self.input_hp_sopir.setText(data["hp"])
        self.input_keterangan.setText(data["keterangan"])
        self.set_jenis_truk_form(data["jenis"])
        self.current_foto_path = data["foto"]
        self.tampilkan_foto(self.current_foto_path)
        return True

    def _isi_form_dari_baris(self, row, ubah_mode=True):
        return self._terapkan_data_form_truk(
            self._ambil_data_form_truk_dari_baris(row),
            ubah_mode=ubah_mode,
        )

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
        tabel = self.tabel_truk
        tabel.blockSignals(True)
        tabel.setRowCount(0)
        try:
            for index, row in enumerate(db_service.ambil_semua_truk_full()):
                self._tambahkan_baris_truk(index, row)
            self.filter_tabel_truk(self.input_cari.text())
        except Exception as exc:
            print(f"Error Load Tabel truk: {exc}")
        finally:
            tabel.blockSignals(False)

    def _data_baris_truk(self, row):
        return (
            self._normalisasi_teks(row[0] if len(row) > 0 else "", kapital=True),
            self._normalisasi_teks(row[1] if len(row) > 1 else ""),
            self._normalisasi_teks(row[2] if len(row) > 2 else "", kapital=True),
            self._normalisasi_teks(row[3] if len(row) > 3 else ""),
            self._normalisasi_teks(row[4] if len(row) > 4 else "", kapital=True),
            self._normalisasi_teks(row[5] if len(row) > 5 else ""),
        )

    def _tambahkan_baris_truk(self, index, row):
        baris = self.tabel_truk.rowCount()
        self.tabel_truk.insertRow(baris)

        nopol, jenis, sopir, hp, ket, foto = self._data_baris_truk(row)
        values = (str(index + 1), jenis, nopol, sopir, hp, ket, foto)
        alignments = (
            Qt.AlignmentFlag.AlignCenter,
            Qt.AlignmentFlag.AlignCenter,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            Qt.AlignmentFlag.AlignCenter,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            None,
        )
        for column, (value, alignment) in enumerate(zip(values, alignments)):
            kwargs = {"editable": False}
            if alignment is not None:
                kwargs["alignment"] = alignment
            self.tabel_truk.setItem(baris, column, buat_tabel_item(value, **kwargs))

    def filter_tabel_truk(self, text):
        kata_kunci = text.lower().strip()
        nomor_baru = 1
        for row in range(self.tabel_truk.rowCount()):
            muncul = any(
                (item := self.tabel_truk.item(row, col))
                and kata_kunci in item.text().lower()
                for col in self.FILTER_COLUMNS
            )
            self.tabel_truk.setRowHidden(row, not muncul)
            if muncul:
                self.tabel_truk.item(row, self.KOL_NO).setText(str(nomor_baru))
                nomor_baru += 1

    def _ambil_input_simpan_truk(self):
        return {
            "nopol": self.input_nopol.text().strip().upper(),
            "jenis": self.ambil_jenis_truk_final(),
            "sopir": self.input_sopir.text().strip().upper(),
            "hp": self.input_hp_sopir.text().strip(),
            "keterangan": self.input_keterangan.text().strip().upper(),
            "foto": self.current_foto_path,
        }

    def _validasi_input_simpan_truk(self, data):
        if not data["nopol"]:
            QMessageBox.warning(self, "Peringatan", "No. Polisi wajib diisi!")
            self.input_nopol.setFocus()
            return False
        if data["jenis"]:
            return True
        if self.combo_jenis.currentText().strip() == "Lainnya...":
            QMessageBox.warning(
                self, "Peringatan", "Jenis Truk Lainnya wajib diisi!"
            )
            self.input_jenis_lain.setFocus()
        else:
            QMessageBox.warning(self, "Peringatan", "Jenis Truk wajib dipilih!")
            self.combo_jenis.setFocus()
        return False

    def _simpan_data_truk(self, data):
        return db_service.simpan_atau_update_truk_full(
            data["nopol"],
            data["jenis"],
            data["sopir"],
            data["hp"],
            data["keterangan"],
            data["foto"],
            mode=self.mode,
        )

    def simpan_atau_update_truk(self):
        data = self._ambil_input_simpan_truk()
        if not self._validasi_input_simpan_truk(data):
            return

        try:
            sukses, pesan = self._simpan_data_truk(data)
            if not sukses:
                QMessageBox.warning(self, "Data truk", pesan)
                return
            QMessageBox.information(
                self, "Sukses", f"Data truk {data['nopol']} berhasil disimpan!"
            )
            self.atur_mode("IDLE")
            self.refresh_session_ui()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error Database", f"Gagal menyimpan data:\n{str(exc)}"
            )

    def pilih_data_dari_tabel(self, row, column):
        try:
            self._isi_form_dari_baris(row, ubah_mode=True)
        except Exception as e:
            print(f"Error Select Row: {e}")

    # --- TEMA DAN ZOOM ---

    def _terapkan_font_form_truk(self, st, ukuran):
        font_base = _buat_font_pt(ukuran["sz_base"])
        font_input = _buat_font_pt(ukuran["sz_input"])
        for label in (
            self.lbl_jenis,
            self.lbl_jenis_lain,
            self.lbl_nopol,
            self.lbl_sopir,
            self.lbl_hp,
            self.lbl_ket,
            self.lbl_foto_title,
            self.lbl_preview_foto,
        ):
            label.setFont(font_base)
        input_form = (
            self.input_jenis_lain,
            self.input_nopol,
            self.input_sopir,
            self.input_hp_sopir,
            self.input_keterangan,
        )
        for widget in input_form:
            widget.setFont(font_input)
            key = "input_locked" if widget.isReadOnly() or not widget.isEnabled() else "input_normal"
            widget.setStyleSheet(st[key])
        self.input_cari.setFont(font_input)
        self.input_cari.setFixedWidth(ARMADA_SEARCH_WIDTH)
        self.combo_jenis.setFont(font_input)
        combo_view = self.combo_jenis.view()
        if combo_view is not None:
            combo_view.setFont(font_input)
        atur_tinggi_input((self.input_cari, *input_form, self.combo_jenis))
        return font_base

    def _terapkan_style_tombol_truk(self, st, ukuran, font_base):
        font_tombol = _buat_font_pt(ukuran["sz_base"], tebal=True)
        for button, key in ((self.btn_batal, "btn_batal"), (self.btn_aksi, "btn_aksi")):
            button.setFont(font_tombol)
            button.setFixedHeight(max(ARMADA_ACTION_BUTTON_MIN_HEIGHT, button.sizeHint().height()))
            button.setStyleSheet(st[key])
        self.btn_pilih_foto.setFont(font_base)
        self.btn_pilih_foto.setFixedHeight(max(ARMADA_PHOTO_BUTTON_MIN_HEIGHT, self.btn_pilih_foto.sizeHint().height()))
        self.btn_pilih_foto.setStyleSheet(st["btn_foto"])

    def _terapkan_tema_statis_armada(self, st):
        """Terapkan tema statis form Armada; hanya tabel yang mengikuti zoom."""
        ukuran = get_global_font_sizes_pt(0)
        self.layout().setContentsMargins(*ARMADA_PAGE_MARGINS)
        self.panel_kiri.layout().setContentsMargins(*ARMADA_MASTER_PANEL_MARGINS)
        self.panel_kanan.layout().setContentsMargins(*ARMADA_EDITOR_PANEL_MARGINS)
        for widget, key in (
            (self.panel_kanan, "panel_kanan"),
            (self.label_judul, "label_judul"),
            (self.input_cari, "input_normal"),
            (self.lbl_judul_kanan, "label_judul_kanan"),
            (self.lbl_preview_foto, "preview_foto"),
        ):
            widget.setStyleSheet(st[key])
        self.label_judul.setFont(_buat_font_pt(ukuran["sz_title"], tebal=True))
        self.lbl_judul_kanan.setFont(_buat_font_pt(ukuran["sz_total"], tebal=True))
        font_base = self._terapkan_font_form_truk(st, ukuran)
        self._terapkan_style_tombol_truk(st, ukuran, font_base)

    def sesuaikan_tema_lokal(self):
        if self._sedang_menerapkan_tema:
            return

        self._sedang_menerapkan_tema = True
        try:
            win = self.window()
            is_dark = bool(
                win
                and hasattr(win, "current_theme")
                and win.current_theme == "dark"
            )
            z = zoom_helper.dapatkan_zoom_level("TabArmada")
            st = get_armada_styles(is_dark, self.mode)

            self._terapkan_tema_statis_armada(st)

            # Hanya tabel Truk yang mengikuti level zoom TabArmada.
            self._sedang_menerapkan_zoom = True
            try:
                zoom_helper.terapkan_zoom_tabel(
                    self.tabel_truk,
                    is_dark=is_dark,
                    z=z,
                )
            finally:
                self._sedang_menerapkan_zoom = False
        finally:
            self._sedang_menerapkan_tema = False