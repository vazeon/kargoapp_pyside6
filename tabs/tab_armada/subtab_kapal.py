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


class SubTabKapal(QWidget, ZoomTableMixin):
    KOL_NO = 0
    KOL_NAMA_KAPAL = 1
    KOL_TUJUAN = 2
    KOL_KETERANGAN = 3
    KOL_FOTO = 4

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "SubTabKapal"
    SETTINGS_KEY_LEBAR = "lebar_kolom_kapal"

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
        self.label_judul = QLabel("🚢 List Data Kapal")
        self.label_judul.setFont(QFont(MASTER_FONT, 14, QFont.Weight.Bold))
        layout_judul_search.addWidget(self.label_judul)
        layout_judul_search.addStretch()

        self.input_cari = QLineEdit()
        self.input_cari.setPlaceholderText("Cari Data Kapal...")
        self.input_cari.setProperty("zoom_font_key", "sz_input")
        self.input_cari.setFixedWidth(230)
        self.input_cari.textChanged.connect(
            lambda _t: helper_paksa_kapital_lineedit(self.input_cari),
        )
        self.input_cari.textChanged.connect(self.filter_tabel_kapal)
        layout_judul_search.addWidget(self.input_cari)
        layout_kiri.addLayout(layout_judul_search)

        self.tabel_kapal = QTableWidget()
        self.tabel_kapal.setColumnCount(5)
        self.tabel_kapal.setHorizontalHeaderLabels([
            "NO", "NAMA KAPAL", "TUJUAN", "KETERANGAN", "FOTO"
        ])

        self.tabel_kapal.setColumnHidden(4, True)  # Simpan path foto tersembunyi
        self.tabel_kapal.setAlternatingRowColors(True)
        self.tabel_kapal.verticalHeader().setVisible(False)

        # Jangan mengunci tinggi header/baris. Zoom global akan menghitung
        # tinggi berdasarkan font dan padding aktual agar teks tidak terpotong.
        header_kapal = self.tabel_kapal.horizontalHeader()
        header_kapal.setMinimumHeight(35)
        header_kapal.setMaximumHeight(16_777_215)

        vertical_header_kapal = self.tabel_kapal.verticalHeader()
        vertical_header_kapal.setMinimumSectionSize(32)
        vertical_header_kapal.setDefaultSectionSize(32)

        # Data Armada satu baris; cegah word-wrap yang membuat tinggi tidak stabil.
        self.tabel_kapal.setWordWrap(False)
        self.tabel_kapal.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.tabel_kapal.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.tabel_kapal.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel_kapal.cellClicked.connect(self.pilih_data_dari_tabel)
        layout_kiri.addWidget(self.tabel_kapal)

        self.load_lebar_kolom(self.tabel_kapal)
        self.tabel_kapal.horizontalHeader().sectionResized.connect(
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

        self.lbl_judul_kanan = QLabel("📋 Detail / Editor Kapal")
        self.lbl_judul_kanan.setFont(QFont(MASTER_FONT, 12, QFont.Weight.Bold))
        self.lbl_judul_kanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_kanan.addWidget(self.lbl_judul_kanan)

        self.lbl_nama_kapal = QLabel("Nama Kapal:")
        self.input_nama_kapal = QLineEdit()
        self.input_nama_kapal.setPlaceholderText("Contoh: KM. SPIL NIKEN")
        self.input_nama_kapal.textChanged.connect(
            lambda _t: helper_paksa_kapital_lineedit(self.input_nama_kapal),
        )
        self.input_nama_kapal.editingFinished.connect(
            self.autofill_kapal_dari_input
        )
        layout_kanan.addWidget(self.lbl_nama_kapal)
        layout_kanan.addWidget(self.input_nama_kapal)

        self.lbl_tujuan = QLabel("Tujuan:")
        self.input_tujuan = QLineEdit()
        self.input_tujuan.setPlaceholderText("Contoh: MAKASSAR / BANJARMASIN")
        self.input_tujuan.textChanged.connect(
            lambda _t: helper_paksa_kapital_lineedit(self.input_tujuan),
        )
        layout_kanan.addWidget(self.lbl_tujuan)
        layout_kanan.addWidget(self.input_tujuan)

        self.lbl_ket = QLabel("Keterangan:")
        self.input_keterangan = QLineEdit()
        self.input_keterangan.setPlaceholderText("Informasi Pelayaran / Dll")
        self.input_keterangan.textChanged.connect(
            lambda _t: helper_paksa_kapital_lineedit(self.input_keterangan),
        )
        layout_kanan.addWidget(self.lbl_ket)
        layout_kanan.addWidget(self.input_keterangan)

        layout_kanan.addSpacing(10)
        self.lbl_foto_title = QLabel("📷 Foto Kapal:")
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
        self.btn_pilih_foto.clicked.connect(self.pilih_foto_kapal)
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
            data = self._cari_master_kapal(self._identitas_terpilih)
            if data:
                self._isi_form_dari_master(data, ubah_mode=False)
            else:
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

    # ============================================================
    # FOTO KAPAL
    # ============================================================

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
                hasil.append(min(max(20, int(width)), 1500))
        except (TypeError, ValueError):
            return None

        return hasil

    def load_lebar_kolom(self, tabel):
        default_widths = [
            45,   # NO
            180,  # NAMA KAPAL
            150,  # TUJUAN
            280,  # KETERANGAN / dasar sebelum Stretch
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

            # Kolom 0-2 dapat diatur manual dan disimpan.
            for index in range(min(3, tabel.columnCount())):
                tabel.setColumnWidth(
                    index,
                    int(base_widths[index]),
                )

            # Keterangan tetap memakai ruang yang tersisa.
            if tabel.columnCount() > 3:
                header.setSectionResizeMode(
                    3,
                    QHeaderView.ResizeMode.Stretch,
                )

            self._perbarui_cache_lebar_zoom(
                tabel,
                base_widths,
            )

        except Exception as exc:
            print(
                f"Error memuat lebar kolom Kapal: {exc}"
            )

        finally:
            self._sedang_menerapkan_zoom = False
            header.blockSignals(False)

    # ============================================================
    # DATA & TABEL KAPAL
    # ============================================================

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
        self.tabel_kapal.blockSignals(True)
        self.tabel_kapal.setRowCount(0)
        self._kapal_master_by_key = {}

        try:
            rows = db_service.ambil_semua_kapal_full()

            for i, row in enumerate(rows):
                baris = self.tabel_kapal.rowCount()
                self.tabel_kapal.insertRow(baris)

                no_urut = str(i + 1)
                nama_kapal = self._normalisasi_teks(
                    row[0] if len(row) > 0 else "",
                    kapital=True,
                )
                tujuan = self._normalisasi_teks(
                    row[1] if len(row) > 1 else "",
                    kapital=True,
                )
                ket = self._normalisasi_teks(
                    row[2] if len(row) > 2 else "",
                    kapital=True,
                )
                foto = self._normalisasi_teks(
                    row[3] if len(row) > 3 else "",
                )

                key = self._normalisasi_kunci_kapal(
                    nama_kapal
                )
                if key and key not in self._kapal_master_by_key:
                    self._kapal_master_by_key[key] = {
                        "nama": nama_kapal,
                        "tujuan": tujuan,
                        "keterangan": ket,
                        "foto": foto,
                    }

                self.tabel_kapal.setItem(
                    baris, self.KOL_NO,
                    buat_tabel_item(
                        no_urut,
                        editable=False,
                        alignment=Qt.AlignmentFlag.AlignCenter,
                    ),
                )
                self.tabel_kapal.setItem(
                    baris, self.KOL_NAMA_KAPAL,
                    buat_tabel_item(
                        nama_kapal,
                        editable=False,
                        alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    ),
                )
                self.tabel_kapal.setItem(
                    baris, self.KOL_TUJUAN,
                    buat_tabel_item(
                        tujuan,
                        editable=False,
                        alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    ),
                )
                self.tabel_kapal.setItem(
                    baris, self.KOL_KETERANGAN,
                    buat_tabel_item(
                        ket,
                        editable=False,
                        alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    ),
                )
                self.tabel_kapal.setItem(
                    baris, self.KOL_FOTO,
                    buat_tabel_item(
                        foto,
                        editable=False,
                    ),
                )

            self.setup_autocomplete_kapal_editor()
            self.filter_tabel_kapal(
                self.input_cari.text()
            )

        except Exception as exc:
            print(
                f"Error Load Tabel Kapal: {exc}"
            )
        finally:
            self.tabel_kapal.blockSignals(False)

    def filter_tabel_kapal(self, text):
        kata_kunci = text.lower().strip()
        nomor_baru = 1

        for row in range(self.tabel_kapal.rowCount()):
            harus_muncul = False
            for col in (
                self.KOL_NAMA_KAPAL,
                self.KOL_TUJUAN,
                self.KOL_KETERANGAN,
            ):
                item = self.tabel_kapal.item(row, col)
                if item and kata_kunci in item.text().lower():
                    harus_muncul = True
                    break

            if harus_muncul:
                self.tabel_kapal.setRowHidden(row, False)
                self.tabel_kapal.item(row, self.KOL_NO).setText(str(nomor_baru))
                nomor_baru += 1
            else:
                self.tabel_kapal.setRowHidden(row, True)

    def simpan_atau_update_kapal(self):
        nama_kapal = self.input_nama_kapal.text().strip().upper()
        tujuan = self.input_tujuan.text().strip().upper()
        ket = self.input_keterangan.text().strip().upper()
        foto = self.current_foto_path

        if not nama_kapal:
            QMessageBox.warning(self, "Peringatan", "Nama Kapal wajib diisi!")
            self.input_nama_kapal.setFocus()
            return

        if self.mode == "TAMBAH":
            data_lama = self._cari_master_kapal(
                nama_kapal
            )
            if data_lama:
                self._isi_form_dari_master(
                    data_lama,
                    ubah_mode=True,
                )
                QMessageBox.information(
                    self,
                    "Data Kapal Sudah Ada",
                    (
                        f"Kapal {data_lama['nama']} sudah terdaftar. "
                        "Data yang lama ditampilkan agar tidak terjadi duplikasi."
                    ),
                )
                return

        try:
            sukses, pesan = db_service.simpan_atau_update_kapal_full(
                nama_kapal,
                tujuan,
                ket,
                foto,
                mode=self.mode,
            )
            if not sukses:
                QMessageBox.warning(self, "Data Kapal", pesan)
                return

            QMessageBox.information(
                self,
                "Sukses",
                f"Data kapal {nama_kapal} berhasil disimpan!",
            )
            self.atur_mode('IDLE')
            self.refresh_session_ui()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Database",
                f"Gagal menyimpan data: {str(e)}",
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

    # ============================================================
    # TEMA DAN ZOOM
    # ============================================================

    def _kunci_tombol_foto_statis(self):
        if not hasattr(self, "btn_pilih_foto"):
            return

        font_statis_base = zoom_helper.batasi_ukuran_font(
            get_global_font_sizes(0).get("sz_base", 10), default=10
        )

        style_btn_foto = getattr(
            self,
            "_style_btn_foto_kapal",
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
                'current_theme',
            ) else False
            z = zoom_helper.dapatkan_zoom_level("TabArmada")

            st = get_armada_styles(is_dark, self.mode)
            self._style_btn_foto_kapal = st["btn_foto"]

            # --- 1. RESET MARGIN SEBELUM ZOOM ---
            self.layout().setContentsMargins(10, 10, 10, 10)
            self.panel_kiri.layout().setContentsMargins(0, 0, 10, 0)
            self.panel_kanan.layout().setContentsMargins(15, 15, 15, 15)

            # --- 3. BLOKIR SIGNAL & TERAPKAN ZOOM ---
            header = self.tabel_kapal.horizontalHeader()
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
            for lbl in [
                self.lbl_nama_kapal,
                self.lbl_tujuan,
                self.lbl_ket,
                self.lbl_foto_title,
            ]:
                lbl.setFont(font_label)

            # Editor Form Input
            font_input = QFont(MASTER_FONT, ukuran_statis)
            for w_input in [
                self.input_nama_kapal,
                self.input_tujuan,
                self.input_keterangan,
            ]:
                w_input.setFont(font_input)
                w_input.setFixedHeight(30) # Mengunci input agar tidak melar
                style_aktif = st["input_locked"] if (hasattr(
                    w_input,
                    'isReadOnly',
                ) and w_input.isReadOnly()) or not w_input.isEnabled() else st["input_normal"]
                w_input.setStyleSheet(style_aktif)

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

            # Placeholder diterapkan paling akhir agar italic dan warnanya
            # tidak tertimpa oleh pengaturan font, tema, atau zoom.
            self._terapkan_placeholder_dinamis()
        finally:
            self._sedang_menerapkan_tema = False