# tabs/tab_armada/subtab_kapal.py
import re
import os
from PySide6.QtCore import QSettings, QStringListModel, Qt, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
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
    ARMADA_SPLITTER_INITIAL_SIZES,
    ARMADA_TABLE_HEADER_MIN_HEIGHT,
    ARMADA_TABLE_ROW_BASE_HEIGHT,
    ARMADA_KAPAL_COLUMN_WIDTHS,
)

def _buat_font_pt(ukuran_pt: float, *, tebal: bool = False) -> QFont:
    """Membuat QFont berbasis point untuk elemen UI statis."""
    font = QFont(get_master_font())
    font.setPointSizeF(float(ukuran_pt))
    font.setBold(bool(tebal))
    return font

class SubTabKapal(QWidget, ZoomTableMixin):
    KOL_NO = 0
    KOL_NAMA_KAPAL = 1
    KOL_TUJUAN = 2
    KOL_KETERANGAN = 3
    KOL_FOTO = 4

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "SubTabKapal"
    SETTINGS_KEY_LEBAR = "lebar_kolom_kapal"

    HEADERS = ("NO", "NAMA KAPAL", "TUJUAN", "KETERANGAN", "FOTO")
    DEFAULT_COLUMN_WIDTHS = ARMADA_KAPAL_COLUMN_WIDTHS
    FILTER_COLUMNS = (KOL_NAMA_KAPAL, KOL_TUJUAN, KOL_KETERANGAN)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.mode = 'IDLE'
        self.current_foto_path = ""
        self._sedang_menerapkan_zoom = False
        self._sedang_menerapkan_tema = False
        self._kapal_master_by_key = {}
        self._identitas_terpilih = ""
        self._lewati_refresh_show_pertama = False

        # Menunda penyimpanan sampai pengguna selesai menggeser header.
        self._timer_simpan_lebar = QTimer(self)
        self._timer_simpan_lebar.setSingleShot(True)
        self._timer_simpan_lebar.setInterval(250)

        self.init_ui()

    def init_ui(self):
        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(*ARMADA_PAGE_MARGINS)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout_utama.addWidget(self.splitter)

        self._bangun_panel_master_kapal()
        self._bangun_panel_editor_kapal()
        self._konfigurasi_splitter()

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

    def _buat_field_kapal(self, layout, label_text, placeholder):
        label = QLabel(label_text)
        editor = self._buat_input_kapital(placeholder)
        layout.addWidget(label)
        layout.addWidget(editor)
        return label, editor

    def _bangun_panel_master_kapal(self):
        self.panel_kiri = QWidget()
        self.panel_kiri.setMinimumWidth(ARMADA_MASTER_PANEL_MIN_WIDTH)
        self.panel_kiri.setMaximumWidth(ARMADA_MASTER_PANEL_MAX_WIDTH)
        layout = QVBoxLayout(self.panel_kiri)
        layout.setContentsMargins(*ARMADA_MASTER_PANEL_MARGINS)

        header_layout = QHBoxLayout()
        self.label_judul = QLabel("List Data Kapal")
        self.label_judul.setFont(
            _buat_font_pt(get_global_font_sizes_pt(0)["sz_title"], tebal=True)
        )
        header_layout.addWidget(self.label_judul)
        header_layout.addStretch()

        self.input_cari = self._buat_input_kapital("Cari Data Kapal...")
        self.input_cari.setFixedWidth(ARMADA_SEARCH_WIDTH)
        self.input_cari.textChanged.connect(self.filter_tabel_kapal)
        header_layout.addWidget(self.input_cari)
        layout.addLayout(header_layout)

        self.tabel_kapal = QTableWidget()
        tabel = self.tabel_kapal
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

    def _bangun_area_foto_kapal(self, layout):
        layout.addSpacing(ARMADA_EDITOR_SECTION_GAP)
        self.lbl_foto_title = QLabel("📷 Foto Kapal:")
        layout.addWidget(self.lbl_foto_title)
        self.lbl_preview_foto = QLabel("Tidak Ada Foto")
        self.lbl_preview_foto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_foto.setFixedHeight(ARMADA_PHOTO_PREVIEW_HEIGHT)
        layout.addWidget(self.lbl_preview_foto)
        self.btn_pilih_foto = QPushButton("📂 Lampirkan Foto Baru")
        self.btn_pilih_foto.clicked.connect(self.pilih_foto_kapal)
        layout.addWidget(self.btn_pilih_foto)
        layout.addStretch()

    def _bangun_tombol_editor_kapal(self, layout):
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

    def _bangun_panel_editor_kapal(self):
        self.panel_kanan = QFrame()
        self.panel_kanan.setMinimumWidth(ARMADA_EDITOR_PANEL_MIN_WIDTH)
        self.panel_kanan.setMaximumWidth(ARMADA_EDITOR_PANEL_MAX_WIDTH)
        self.panel_kanan.setObjectName("panelEditor")
        layout = QVBoxLayout(self.panel_kanan)
        layout.setContentsMargins(*ARMADA_EDITOR_PANEL_MARGINS)

        self.lbl_judul_kanan = QLabel("Detail / Editor Kapal")
        self.lbl_judul_kanan.setFont(
            _buat_font_pt(get_global_font_sizes_pt(0)["sz_total"], tebal=True)
        )
        self.lbl_judul_kanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_judul_kanan)

        self.lbl_nama_kapal, self.input_nama_kapal = self._buat_field_kapal(
            layout, "Nama Kapal:", "Contoh: KM. SPIL NIKEN"
        )
        self.lbl_tujuan, self.input_tujuan = self._buat_field_kapal(
            layout, "Tujuan:", "Contoh: MAKASSAR / BANJARMASIN"
        )
        self.lbl_ket, self.input_keterangan = self._buat_field_kapal(
            layout, "Keterangan:", "Informasi Pelayaran / Dll"
        )
        self.input_nama_kapal.editingFinished.connect(self.autofill_kapal_dari_input)
        self._bangun_area_foto_kapal(layout)
        self._bangun_tombol_editor_kapal(layout)

    def _konfigurasi_splitter(self):
        self.splitter.addWidget(self.panel_kiri)
        self.splitter.addWidget(self.panel_kanan)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes(list(ARMADA_SPLITTER_INITIAL_SIZES))

    # --- LIFECYCLE & REFRESH ---

    def refresh_session_ui(self):
        """Memuat ulang tabel tanpa menghilangkan filter dan state editor aktif."""
        self.refresh_tabel()

        if self.mode == "PREVIEW" and self._identitas_terpilih:
            data = self._cari_master_kapal(self._identitas_terpilih)
            if data:
                self._isi_form_dari_master(data, ubah_mode=False)
            else:
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
            self.tabel_kapal.clearSelection()
            self.btn_aksi.setText("➕ Tambah Kapal")
            self.btn_batal.hide()
            self.btn_pilih_foto.hide()
        elif mode == 'TAMBAH':
            self.bersihkan_form()
            self.aktifkan_input(True)
            self.input_nama_kapal.setReadOnly(False)
            self.btn_aksi.setText("💾 Simpan Kapal")
            self.btn_batal.show()
            self.btn_pilih_foto.show()
        elif mode == 'PREVIEW':
            self.aktifkan_input(False)
            self.btn_aksi.setText("✏️ Edit")
            self.btn_batal.hide()
            self.btn_pilih_foto.hide()
        elif mode == 'EDIT':
            self.aktifkan_input(True)
            self.input_nama_kapal.setReadOnly(
                True,
            )  # Primary key/identitas kapal dikunci
            self.btn_aksi.setText("💾 Simpan")
            self.btn_batal.show()
            self.btn_pilih_foto.show()
        self.sesuaikan_tema_lokal()

    def aktifkan_input(self, aktif):
        self.input_nama_kapal.setReadOnly(not aktif)
        self.input_tujuan.setReadOnly(not aktif)
        self.input_keterangan.setReadOnly(not aktif)

    def bersihkan_form(self):
        self._identitas_terpilih = ""
        self.input_nama_kapal.clear()
        self.input_tujuan.clear()
        self.input_keterangan.clear()
        self.current_foto_path = ""
        self.lbl_preview_foto.clear()
        self.lbl_preview_foto.setText("Tidak Ada Foto")

    def handle_tombol_aksi(self):
        if self.mode == 'IDLE':
            self.atur_mode('TAMBAH')
        elif self.mode == 'TAMBAH':
            self.simpan_atau_update_kapal()
        elif self.mode == 'PREVIEW':
            self.atur_mode('EDIT')
        elif self.mode == 'EDIT':
            self.simpan_atau_update_kapal()

    # --- FOTO KAPAL ---

    def pilih_foto_kapal(self):
        options = QFileDialog.Option(0)
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Pilih Foto Kapal", "",
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
        Menyimpan lebar kolom sesudah proses drag selesai.

        Perubahan ukuran yang berasal dari penerapan zoom tidak boleh
        dianggap sebagai perubahan manual pengguna.
        """
        if self._sedang_menerapkan_zoom:
            return

        self._timer_simpan_lebar.start()

    def _simpan_lebar_kolom_sekarang(self):
        if not hasattr(self, "tabel_kapal"):
            return

        self.simpan_lebar_kolom(self.tabel_kapal)

    def simpan_lebar_kolom(self, tabel):
        if self._sedang_menerapkan_zoom:
            return

        # Zoom SubTabKapal mengikuti TabArmada, jadi ukuran tampilan harus
        # dinormalisasi dengan key yang sama sebelum disimpan.
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

            for index, width in enumerate(base_widths[:min(3, tabel.columnCount())]):
                tabel.setColumnWidth(index, int(width))

            if tabel.columnCount() > self.KOL_KETERANGAN:
                header.setSectionResizeMode(
                    self.KOL_KETERANGAN,
                    QHeaderView.ResizeMode.Stretch,
                )

            self._perbarui_cache_lebar_zoom(tabel, base_widths)
        except Exception as exc:
            print(f"Error memuat lebar kolom Kapal: {exc}")
        finally:
            self._sedang_menerapkan_zoom = False
            header.blockSignals(False)

    # --- DATA & TABEL KAPAL ---

    @staticmethod
    def _normalisasi_teks(value, kapital=False):
        hasil = str(value or "").strip()
        return hasil.upper() if kapital else hasil

    @staticmethod
    def _normalisasi_kunci_kapal(nama):
        return re.sub(
            r"[^A-Z0-9]+",
            "",
            str(nama or "").strip().upper(),
        )

    def _cari_master_kapal(self, nama):
        key = self._normalisasi_kunci_kapal(nama)
        if not key:
            return None
        return self._kapal_master_by_key.get(key)

    def _isi_form_dari_master(self, data, ubah_mode=True):
        if not data:
            return

        if ubah_mode:
            self.atur_mode("PREVIEW")

        self._identitas_terpilih = data["nama"]
        self.input_nama_kapal.setText(data["nama"])
        self.input_tujuan.setText(data["tujuan"])
        self.input_keterangan.setText(data["keterangan"])
        self.current_foto_path = data["foto"]
        self.tampilkan_foto(self.current_foto_path)

    def setup_autocomplete_kapal_editor(self):
        daftar_nama = sorted(
            data["nama"]
            for data in self._kapal_master_by_key.values()
        )

        if not hasattr(self, "model_autocomplete_kapal_editor"):
            self.model_autocomplete_kapal_editor = QStringListModel(
                self
            )
            self.completer_kapal_editor = QCompleter(
                self.model_autocomplete_kapal_editor,
                self,
            )
            self.completer_kapal_editor.setCaseSensitivity(
                Qt.CaseSensitivity.CaseInsensitive
            )
            self.completer_kapal_editor.setFilterMode(
                Qt.MatchFlag.MatchContains
            )
            self.completer_kapal_editor.setCompletionMode(
                QCompleter.CompletionMode.PopupCompletion
            )
            self.completer_kapal_editor.activated[str].connect(
                self.on_kapal_autocomplete_selected
            )
            self.input_nama_kapal.setCompleter(
                self.completer_kapal_editor
            )

        self.model_autocomplete_kapal_editor.setStringList(
            daftar_nama
        )

    def on_kapal_autocomplete_selected(self, nama):
        data = self._cari_master_kapal(nama)
        if data:
            self._isi_form_dari_master(
                data,
                ubah_mode=True,
            )

    def autofill_kapal_dari_input(self):
        if self.mode != "TAMBAH":
            return

        data = self._cari_master_kapal(
            self.input_nama_kapal.text()
        )
        if data:
            self._isi_form_dari_master(
                data,
                ubah_mode=True,
            )

    def refresh_tabel(self):
        tabel = self.tabel_kapal
        tabel.blockSignals(True)
        tabel.setRowCount(0)
        self._kapal_master_by_key = {}
        try:
            for index, row in enumerate(db_service.ambil_semua_kapal_full()):
                self._tambahkan_baris_kapal(index, row)
            self.setup_autocomplete_kapal_editor()
            self.filter_tabel_kapal(self.input_cari.text())
        except Exception as exc:
            print(f"Error Load Tabel Kapal: {exc}")
        finally:
            tabel.blockSignals(False)

    def _data_baris_kapal(self, row):
        return {
            "nama": self._normalisasi_teks(row[0] if len(row) > 0 else "", kapital=True),
            "tujuan": self._normalisasi_teks(row[1] if len(row) > 1 else "", kapital=True),
            "keterangan": self._normalisasi_teks(row[2] if len(row) > 2 else "", kapital=True),
            "foto": self._normalisasi_teks(row[3] if len(row) > 3 else ""),
        }

    def _tambahkan_baris_kapal(self, index, row):
        tabel = self.tabel_kapal
        baris = tabel.rowCount()
        tabel.insertRow(baris)

        data = self._data_baris_kapal(row)
        key = self._normalisasi_kunci_kapal(data["nama"])
        if key and key not in self._kapal_master_by_key:
            self._kapal_master_by_key[key] = dict(data)

        values = (
            str(index + 1),
            data["nama"],
            data["tujuan"],
            data["keterangan"],
            data["foto"],
        )
        alignments = (
            Qt.AlignmentFlag.AlignCenter,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            None,
        )
        for column, (value, alignment) in enumerate(zip(values, alignments)):
            kwargs = {"editable": False}
            if alignment is not None:
                kwargs["alignment"] = alignment
            tabel.setItem(baris, column, buat_tabel_item(value, **kwargs))

    def filter_tabel_kapal(self, text):
        kata_kunci = text.lower().strip()
        nomor_baru = 1
        for row in range(self.tabel_kapal.rowCount()):
            muncul = any(
                (item := self.tabel_kapal.item(row, col))
                and kata_kunci in item.text().lower()
                for col in self.FILTER_COLUMNS
            )
            self.tabel_kapal.setRowHidden(row, not muncul)
            if muncul:
                self.tabel_kapal.item(row, self.KOL_NO).setText(str(nomor_baru))
                nomor_baru += 1

    def _ambil_input_simpan_kapal(self):
        return {
            "nama": self.input_nama_kapal.text().strip().upper(),
            "tujuan": self.input_tujuan.text().strip().upper(),
            "keterangan": self.input_keterangan.text().strip().upper(),
            "foto": self.current_foto_path,
        }

    def _tangani_duplikat_kapal_tambah(self, nama_kapal):
        if self.mode != "TAMBAH":
            return False
        data_lama = self._cari_master_kapal(nama_kapal)
        if not data_lama:
            return False
        self._isi_form_dari_master(data_lama, ubah_mode=True)
        QMessageBox.information(
            self,
            "Data Kapal Sudah Ada",
            f"Kapal {data_lama['nama']} sudah terdaftar. "
            "Data yang lama ditampilkan agar tidak terjadi duplikasi.",
        )
        return True

    def _simpan_data_kapal(self, data):
        return db_service.simpan_atau_update_kapal_full(
            data["nama"],
            data["tujuan"],
            data["keterangan"],
            data["foto"],
            mode=self.mode,
        )

    def simpan_atau_update_kapal(self):
        data = self._ambil_input_simpan_kapal()
        nama_kapal = data["nama"]
        if not nama_kapal:
            QMessageBox.warning(self, "Peringatan", "Nama Kapal wajib diisi!")
            self.input_nama_kapal.setFocus()
            return
        if self._tangani_duplikat_kapal_tambah(nama_kapal):
            return

        try:
            sukses, pesan = self._simpan_data_kapal(data)
            if not sukses:
                QMessageBox.warning(self, "Data Kapal", pesan)
                return
            QMessageBox.information(
                self, "Sukses", f"Data kapal {nama_kapal} berhasil disimpan!"
            )
            self.atur_mode("IDLE")
            self.refresh_session_ui()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error Database", f"Gagal menyimpan data: {str(exc)}"
            )

    def pilih_data_dari_tabel(self, row, column):
        try:
            item_nama = self.tabel_kapal.item(row, self.KOL_NAMA_KAPAL)
            if not item_nama:
                return

            data = self._cari_master_kapal(item_nama.text())
            if not data:
                return

            self._isi_form_dari_master(data, ubah_mode=True)

        except Exception as e:
            print(f"Error Select Row Kapal: {e}")

    # --- TEMA DAN ZOOM ---

    def _terapkan_font_form_kapal(self, st, ukuran):
        font_base = _buat_font_pt(ukuran["sz_base"])
        font_input = _buat_font_pt(ukuran["sz_input"])
        for label in (
            self.lbl_nama_kapal,
            self.lbl_tujuan,
            self.lbl_ket,
            self.lbl_foto_title,
            self.lbl_preview_foto,
        ):
            label.setFont(font_base)
        input_form = (self.input_nama_kapal, self.input_tujuan, self.input_keterangan)
        for widget in input_form:
            widget.setFont(font_input)
            key = "input_locked" if widget.isReadOnly() or not widget.isEnabled() else "input_normal"
            widget.setStyleSheet(st[key])
        self.input_cari.setFont(font_input)
        self.input_cari.setFixedWidth(ARMADA_SEARCH_WIDTH)
        atur_tinggi_input((self.input_cari, *input_form))
        return font_base

    def _terapkan_style_tombol_kapal(self, st, ukuran, font_base):
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
        font_base = self._terapkan_font_form_kapal(st, ukuran)
        self._terapkan_style_tombol_kapal(st, ukuran, font_base)

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

            # Tabel mengikuti level zoom TabArmada melalui helper tabel.
            self._sedang_menerapkan_zoom = True
            try:
                zoom_helper.terapkan_zoom_tabel(
                    self.tabel_kapal,
                    is_dark=is_dark,
                    z=z,
                )
            finally:
                self._sedang_menerapkan_zoom = False
        finally:
            self._sedang_menerapkan_tema = False