# tabs/tab_kontak/subtab_penerima.py
import json
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
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
from utils.input_style_helper import (
    atur_tinggi_input,
    paksa_kapital_lineedit as helper_paksa_kapital_lineedit,
    terapkan_style_input_global,
)
from utils.typography import get_fixed_font_sizes_pt, get_font_weights, get_master_font
from utils.mixins import ZoomTableMixin
from utils.table_helper import ModelTableView, terapkan_tema_tabel
from utils.date_ind_format import format_tanggal_ke_ui
import utils.zoom as zoom_helper

_FONT_WEIGHTS = get_font_weights()


KONTAK_SUBTAB_MARGINS = (0, 0, 0, 0)
KONTAK_SPACING = 8
KONTAK_SPLITTER_INITIAL_SIZES = (650, 450)
KONTAK_PANEL_MIN_WIDTH = 400
KONTAK_PANEL_MAX_WIDTH = 1400
KONTAK_PANEL_MARGINS = (8, 8, 8, 8)
KONTAK_SEARCH_WIDTH = 230
KONTAK_HISTORY_SEARCH_WIDTH = 180
KONTAK_ADD_BUTTON_HEIGHT = 30
KONTAK_ADD_DIALOG_MIN_WIDTH = 660
KONTAK_ADD_DIALOG_MARGINS = (24, 22, 24, 22)
KONTAK_ADD_DIALOG_SPACING = 18
KONTAK_ADD_FORM_HORIZONTAL_SPACING = 20
KONTAK_ADD_FORM_VERTICAL_SPACING = 14
KONTAK_ADD_FIELD_MIN_WIDTH = 400
KONTAK_HISTORY_COLUMN_WIDTHS = (95, 100, 140, 50, 60, 60, 90)
KONTAK_PENERIMA_COLUMN_WIDTHS = (50, 90, 190, 130, 260, 130, 140, 130, 130, 130)


def _buat_font_pt(ukuran_pt: float, *, weight: str = "regular") -> QFont:
    font = QFont(get_master_font())
    font.setPointSizeF(float(ukuran_pt))
    font.setWeight(QFont.Weight(_FONT_WEIGHTS[weight]))
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
    LEBAR_PENERIMA = KONTAK_PENERIMA_COLUMN_WIDTHS
    LEBAR_HISTORI = KONTAK_HISTORY_COLUMN_WIDTHS

    def __init__(self):
        super().__init__()
        self._sedang_menerapkan_zoom = False
        self._data_loaded = False

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.filter_pencarian_tabel)

        self._history_search_timer = QTimer(self)
        self._history_search_timer.setSingleShot(True)
        self._history_search_timer.setInterval(250)
        self._history_search_timer.timeout.connect(self.filter_pencarian_histori)

        self.init_ui()

    def init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(*KONTAK_SUBTAB_MARGINS)
        layout_utama.setSpacing(KONTAK_SPACING)

        self.panel_kiri = self._bangun_panel_penerima()
        self.panel_kanan = self._bangun_panel_histori()

        zoom_helper.pasang_ctrl_scroll_zoom(
            self.tabel_penerima,
            self._ubah_zoom_ctrl_scroll,
        )
        zoom_helper.pasang_ctrl_scroll_zoom(
            self.tabel_histori,
            self._ubah_zoom_ctrl_scroll,
        )

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(self.panel_kiri)
        self.splitter.addWidget(self.panel_kanan)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes(KONTAK_SPLITTER_INITIAL_SIZES)
        self.splitter.setHandleWidth(1)
        self.splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout_utama.addWidget(self.splitter)

        self.refresh_session_ui()
        self.sesuaikan_tema_lokal()

    def _bangun_panel_penerima(self):
        panel = QWidget()
        panel.setMinimumWidth(KONTAK_PANEL_MIN_WIDTH)
        panel.setMaximumWidth(KONTAK_PANEL_MAX_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(*KONTAK_PANEL_MARGINS)
        layout.setSpacing(KONTAK_SPACING)

        ukuran = get_fixed_font_sizes_pt()
        self.lbl_judul = QLabel("List Penerima")
        self.lbl_judul.setFont(_buat_font_pt(ukuran["subtitle"], weight="medium"))
        self.txt_cari = self._buat_input_cari(
            "Cari penerima...",
            KONTAK_SEARCH_WIDTH,
            self._search_timer,
            ukuran["body"],
        )
        self.btn_tambah_penerima = QPushButton("+ Tambah Penerima")
        self.btn_tambah_penerima.setFixedHeight(KONTAK_ADD_BUTTON_HEIGHT)
        self.btn_tambah_penerima.clicked.connect(self.tampilkan_dialog_tambah_penerima)

        header = self._buat_header(self.lbl_judul, self.txt_cari)
        header.insertWidget(2, self.btn_tambah_penerima)
        layout.addLayout(header)

        self.tabel_penerima = ModelTableView(parent=self)
        self._konfigurasi_tabel(
            self.tabel_penerima,
            self.HEADER_PENERIMA,
            editable=True,
        )
        self.tabel_penerima.setColumnHidden(self.KOL_ID, True)
        # Seluruh perubahan master penerima dilakukan melalui popup Edit.
        self.tabel_penerima.clicked.connect(
            lambda index: self.pilih_penerima_tampilkan_histori(
                index.row(), index.column()
            )
        )
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
        panel.setMinimumWidth(KONTAK_PANEL_MIN_WIDTH)
        panel.setMaximumWidth(KONTAK_PANEL_MAX_WIDTH)
        panel.setObjectName("panelHistori")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(*KONTAK_PANEL_MARGINS)
        layout.setSpacing(KONTAK_SPACING)

        ukuran = get_fixed_font_sizes_pt()
        self.lbl_judul_histori = QLabel("Histori Penerimaan")
        self.lbl_judul_histori.setFont(_buat_font_pt(ukuran["body"], weight="medium"))
        self.txt_cari_histori = self._buat_input_cari(
            "Cari di histori ini...",
            KONTAK_HISTORY_SEARCH_WIDTH,
            self._history_search_timer,
            ukuran["body"],
        )
        layout.addLayout(self._buat_header(self.lbl_judul_histori, self.txt_cari_histori))

        self.tabel_histori = ModelTableView(parent=self)
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

    def _buat_input_cari(self, placeholder, lebar, timer_obj, ukuran_font=None):
        widget = QLineEdit()
        if ukuran_font is not None:
            widget.setFont(_buat_font_pt(ukuran_font))
        widget.setPlaceholderText(placeholder)
        widget.setFixedWidth(lebar)
        atur_tinggi_input(widget)
        widget.textChanged.connect(
            lambda _text, w=widget: helper_paksa_kapital_lineedit(w)
        )
        widget.textChanged.connect(lambda: timer_obj.start())
        return widget

    @staticmethod
    def _konfigurasi_tabel(tabel, headers, *, editable=False):
        tabel.setColumnCount(len(headers))
        tabel.setHorizontalHeaderLabels(list(headers))
        tabel.verticalHeader().setVisible(False)
        tabel.setAlternatingRowColors(True)
        # Model/View master data tidak mengedit sel secara langsung.
        tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        if editable:
            tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = tabel.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)

    def refresh_session_ui(self):
        self.load_data()
        self.filter_pencarian_tabel()
        self._data_loaded = True

    def showEvent(self, event):
        super().showEvent(event)
        if not self._data_loaded:
            self.refresh_session_ui()

    def _tema_gelap_aktif(self):
        win = self.window()
        return bool(win and hasattr(win, "current_theme") and win.current_theme == "dark")

    @staticmethod
    def _nilai_setting_list(key, default=None):
        raw = db_service.get_setting(key)
        values = raw
        if isinstance(raw, str):
            try:
                values = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                values = None

        if not isinstance(values, (list, tuple)):
            values = default if default is not None else []

        hasil = []
        for value in values:
            text = str(value or "").strip().upper()
            if text and text not in hasil:
                hasil.append(text)
        return hasil

    def _daftar_provinsi_session(self):
        return self._nilai_setting_list(
            "provinsi_tujuan",
            ["PROVINSI A", "PROVINSI B", "PROVINSI C"],
        )

    @staticmethod
    def _daftar_pembayaran_session():
        return ["TF / INVOICE", "CASH"]

    @staticmethod
    def _filter_tabel(tabel, keyword, columns):
        keyword = keyword.lower().strip()
        for row in range(tabel.rowCount()):
            if hasattr(tabel, "searchText"):
                match = keyword in tabel.searchText(row, columns)
            else:
                match = any(
                    (item := tabel.item(row, col))
                    and keyword in item.text().casefold()
                    for col in columns
                )
            tabel.setRowHidden(row, not match)

    @db_service.profile_performance("KontakPenerima.search_filter", threshold=0.025)
    def filter_pencarian_tabel(self):
        self._filter_tabel(
            self.tabel_penerima,
            self.txt_cari.text(),
            self.KOLOM_PENCARIAN,
        )

    @db_service.profile_performance("KontakPenerima.search_history", threshold=0.025)
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

        self.tabel_penerima.selectRow(item.row())
        menu = QMenu(self)
        act_edit = menu.addAction("Edit Penerima...")
        menu.addSeparator()
        act_normal = menu.addAction("Set Status: NORMAL")
        act_blacklist = menu.addAction("Set Status: BLACKLIST (Macet)")
        action = menu.exec(self.tabel_penerima.viewport().mapToGlobal(pos))

        if action == act_edit:
            self.tampilkan_dialog_edit_penerima(item.row())
        elif action in (act_normal, act_blacklist):
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
        """Konversi satu record database menjadi tuple nilai model."""
        id_penerima = str(data[0]) if data[0] else ""
        nama = str(data[1]).upper() if data[1] else ""
        no_hp = str(data[2]) if data[2] else ""
        alamat = str(data[3]).upper() if data[3] else ""
        kota = str(data[4]).upper() if data[4] else ""
        provinsi = str(data[5]).upper() if data[5] else ""
        total_transaksi = str(data[6]) if data[6] else "0"
        pembayaran = str(data[7]).upper() if data[7] else "TF / INVOICE"
        status = str(data[8]).strip().upper() if data[8] else "NORMAL"
        return (
            str(baris + 1), id_penerima, nama, no_hp, alamat, kota,
            provinsi, total_transaksi, pembayaran, status,
        )

    def _warna_blacklist_model(self, is_dark):
        hex_bg, hex_fg = get_penerima_blacklist_colors(is_dark)
        return QBrush(QColor(hex_bg)), QBrush(QColor(hex_fg))

    def _buat_form_tambah_penerima(self, initial_data=None, title="Tambah Penerima"):
        dialog = QDialog(self)
        terapkan_style_input_global(dialog, self._tema_gelap_aktif())
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setMinimumWidth(KONTAK_ADD_DIALOG_MIN_WIDTH)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(*KONTAK_ADD_DIALOG_MARGINS)
        layout.setSpacing(KONTAK_ADD_DIALOG_SPACING)

        form = QFormLayout()
        form.setHorizontalSpacing(KONTAK_ADD_FORM_HORIZONTAL_SPACING)
        form.setVerticalSpacing(KONTAK_ADD_FORM_VERTICAL_SPACING)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        fields = {
            "nama": QLineEdit(),
            "no_hp": QLineEdit(),
            "alamat": QLineEdit(),
            "kota": QLineEdit(),
            "provinsi": QComboBox(),
            "pembayaran": QComboBox(),
        }
        for key, placeholder in (
            ("nama", "Nama penerima"), ("no_hp", "No. HP"),
            ("alamat", "Alamat"), ("kota", "Kota"),
        ):
            fields[key].setPlaceholderText(placeholder)
        fields["provinsi"].addItems(self._daftar_provinsi_session())
        fields["pembayaran"].addItems(self._daftar_pembayaran_session())
        fields["provinsi"].setToolTip(
            "Pilihan mengikuti pengaturan provinsi_tujuan pada database/session aktif."
        )
        if initial_data:
            fields["nama"].setText(str(initial_data.get("nama", "") or ""))
            fields["no_hp"].setText(str(initial_data.get("no_hp", "") or ""))
            fields["alamat"].setText(str(initial_data.get("alamat", "") or ""))
            fields["kota"].setText(str(initial_data.get("kota", "") or ""))
            for key in ("provinsi", "pembayaran"):
                value = str(initial_data.get(key, "") or "").strip().upper()
                combo = fields[key]
                idx = combo.findText(value, Qt.MatchFlag.MatchFixedString)
                if idx < 0 and value:
                    combo.addItem(value)
                    idx = combo.count() - 1
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        widgets = tuple(fields.values())
        for widget in widgets:
            widget.setMinimumWidth(KONTAK_ADD_FIELD_MIN_WIDTH)
        atur_tinggi_input(widgets)
        for key in ("nama", "alamat", "kota"):
            fields[key].textChanged.connect(
                lambda _text, w=fields[key]: helper_paksa_kapital_lineedit(w)
            )

        for label, key in (
            ("Nama Penerima *", "nama"), ("No. HP", "no_hp"),
            ("Alamat", "alamat"), ("Kota", "kota"),
            ("Provinsi", "provinsi"), ("Pembayaran", "pembayaran"),
        ):
            form.addRow(label, fields[key])
        layout.addLayout(form)

        tombol = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        tombol.rejected.connect(dialog.reject)
        layout.addWidget(tombol)
        return dialog, fields, tombol

    def _simpan_penerima_baru_dari_form(self, dialog, fields):
        nama = fields["nama"].text().strip().upper()
        no_hp = fields["no_hp"].text().strip()
        alamat = fields["alamat"].text().strip().upper()
        kota = fields["kota"].text().strip().upper()
        provinsi = fields["provinsi"].currentText().strip().upper()
        pembayaran = fields["pembayaran"].currentText().strip().upper() or "TF / INVOICE"
        if not nama:
            QMessageBox.warning(dialog, "Data Belum Lengkap", "Nama penerima wajib diisi.")
            fields["nama"].setFocus()
            return

        sukses, pesan = db_service.tambah_master_penerima(
            CURRENT_SESSION.get("kode_cabang", "PUSAT"),
            nama, no_hp, alamat, kota, provinsi, pembayaran,
        )
        if not sukses:
            QMessageBox.warning(
                dialog, "Gagal Menambah Penerima",
                pesan or "Data penerima tidak dapat disimpan.",
            )
            return
        dialog.accept()
        self.refresh_session_ui()

    def tampilkan_dialog_tambah_penerima(self):
        dialog, fields, tombol = self._buat_form_tambah_penerima()

        def simpan_penerima_baru():
            self._simpan_penerima_baru_dari_form(dialog, fields)

        tombol.accepted.connect(simpan_penerima_baru)
        fields["nama"].setFocus()
        dialog.adjustSize()
        dialog.exec()

    def tampilkan_dialog_edit_penerima(self, row):
        current = self.tabel_penerima.model().rowValues(row)
        if not current:
            return
        initial = {
            "nama": current[self.KOL_NAMA_PENERIMA],
            "no_hp": current[self.KOL_TELEPON],
            "alamat": current[self.KOL_ALAMAT],
            "kota": current[self.KOL_KOTA],
            "provinsi": current[self.KOL_PROVINSI],
            "pembayaran": current[self.KOL_PEMBAYARAN],
        }
        dialog, fields, tombol = self._buat_form_tambah_penerima(
            initial_data=initial,
            title="Edit Penerima",
        )
        tombol.accepted.connect(
            lambda: self._simpan_edit_penerima_popup(row, dialog, fields)
        )
        fields["nama"].setFocus()
        dialog.adjustSize()
        dialog.exec()

    def _simpan_edit_penerima_popup(self, row, dialog, fields):
        current = self.tabel_penerima.model().rowValues(row)
        if not current:
            return
        nama = fields["nama"].text().strip().upper()
        no_hp = fields["no_hp"].text().strip()
        alamat = fields["alamat"].text().strip().upper()
        kota = fields["kota"].text().strip().upper()
        provinsi = fields["provinsi"].currentText().strip().upper()
        pembayaran = fields["pembayaran"].currentText().strip().upper() or "TF / INVOICE"
        if not nama:
            QMessageBox.warning(dialog, "Data Belum Lengkap", "Nama penerima wajib diisi.")
            fields["nama"].setFocus()
            return

        try:
            sukses, pesan = db_service.update_master_penerima_dari_tabel(
                str(current[self.KOL_ID]).strip(),
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                nama, no_hp, alamat, kota, provinsi, pembayaran,
            )
            if not sukses:
                QMessageBox.warning(
                    dialog,
                    "Gagal Mengubah Penerima",
                    pesan or "Data penerima tidak dapat diperbarui.",
                )
                return

            updated = list(current)
            updated[self.KOL_NAMA_PENERIMA] = nama
            updated[self.KOL_TELEPON] = no_hp
            updated[self.KOL_ALAMAT] = alamat
            updated[self.KOL_KOTA] = kota
            updated[self.KOL_PROVINSI] = provinsi
            updated[self.KOL_PEMBAYARAN] = pembayaran
            is_dark = self._tema_gelap_aktif()
            background = foreground = None
            if str(updated[self.KOL_STATUS_TAGIHAN]).upper() == "BLACKLIST":
                background, foreground = self._warna_blacklist_model(is_dark)
            self.tabel_penerima.setRowValues(
                row, updated, background=background, foreground=foreground
            )
            self.filter_pencarian_tabel()
            dialog.accept()

            if self.tabel_penerima.currentRow() == row:
                self.pilih_penerima_tampilkan_histori(row, self.KOL_NAMA_PENERIMA)
        except Exception as error:
            QMessageBox.critical(dialog, "Error", f"Gagal memperbarui penerima: {error}")

    @db_service.profile_performance("KontakPenerima.load_data", threshold=0.05)
    def load_data(self):
        tabel = self.tabel_penerima
        tabel.setUpdatesEnabled(False)
        try:
            rows = db_service.ambil_semua_master_penerima_full(
                CURRENT_SESSION.get("kode_cabang", "PUSAT")
            ) or []
            is_dark = self._tema_gelap_aktif()
            display_rows = []
            backgrounds = {}
            foregrounds = {}
            blacklist_brushes = self._warna_blacklist_model(is_dark)
            for baris, data in enumerate(rows):
                values = self._isi_baris_penerima(baris, data, is_dark)
                display_rows.append(values)
                if values[self.KOL_STATUS_TAGIHAN] == "BLACKLIST":
                    backgrounds[baris], foregrounds[baris] = blacklist_brushes
            alignments = (
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
                Qt.AlignmentFlag.AlignCenter,
            )
            tabel.setRows(
                display_rows,
                alignments=alignments,
                row_backgrounds=backgrounds,
                row_foregrounds=foregrounds,
            )
            self.tabel_histori.setRows([])
            self.lbl_judul_histori.setText("Histori Penerimaan")
        except Exception as error:
            print(f"Error Load Penerima: {error}")
        finally:
            tabel.setUpdatesEnabled(True)

    def _isi_baris_histori(self, baris, h):
        return (
            format_tanggal_ke_ui(h[0]),
            str(h[1]),
            str(h[2]).upper(),
            str(h[3]),
            str(h[4]),
            str(h[5]),
            format_ke_rupiah(h[7]) if h[7] else "0",
        )

    def pilih_penerima_tampilkan_histori(self, row, column):
        if not hasattr(self, "tabel_histori"):
            return

        item_nama = self.tabel_penerima.item(row, self.KOL_NAMA_PENERIMA)
        if not item_nama:
            return

        nama_penerima = item_nama.text()
        tabel = self.tabel_histori
        tabel.setUpdatesEnabled(False)
        try:
            histori_rows = db_service.ambil_histori_transaksi_by_penerima(
                nama_penerima,
                CURRENT_SESSION.get("kode_cabang", "PUSAT"),
            ) or []
            self.lbl_judul_histori.setText(f"Histori Penerimaan: {nama_penerima}")
            display_rows = [
                self._isi_baris_histori(baris, histori)
                for baris, histori in enumerate(histori_rows)
            ]
            tabel.setRows(
                display_rows,
                alignments=(
                    Qt.AlignmentFlag.AlignCenter,
                    Qt.AlignmentFlag.AlignCenter,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    Qt.AlignmentFlag.AlignCenter,
                    Qt.AlignmentFlag.AlignCenter,
                    Qt.AlignmentFlag.AlignCenter,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ),
            )
            self.filter_pencarian_histori()
        except Exception as error:
            print(f"Error Load Histori Penerima: {error}")
        finally:
            tabel.setUpdatesEnabled(True)

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
        ukuran = get_fixed_font_sizes_pt()
        for widget, token, weight in (
            (self.lbl_judul, "subtitle", "medium"),
            (self.lbl_judul_histori, "body", "medium"),
            (self.txt_cari, "body", "regular"),
            (self.txt_cari_histori, "body", "regular"),
            (self.btn_tambah_penerima, "body", "regular"),
        ):
            widget.setFont(_buat_font_pt(ukuran[token], weight=weight))
        atur_tinggi_input((self.txt_cari, self.txt_cari_histori))

    def _ubah_zoom_ctrl_scroll(self, arah):
        nama_zoom = "TabKontak"
        z = zoom_helper.dapatkan_zoom_level(nama_zoom)
        z = zoom_helper.simpan_zoom_level(nama_zoom, z + int(arah))
        self.sesuaikan_tema_lokal()

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()
        z = zoom_helper.dapatkan_zoom_level("TabKontak")
        style = get_kontak_riwayat_styles(is_dark)

        for widget, key in (
            (self.lbl_judul, "judul"),
            (self.lbl_judul_histori, "judul_histori"),
            (self.panel_kanan, "panel"),
        ):
            widget.setStyleSheet(style[key])

        self._terapkan_font_dasar()
        terapkan_style_input_global(self, is_dark)
        self._sedang_menerapkan_zoom = True
        try:
            zoom_metrics = zoom_helper.dapatkan_metrik_zoom(z)
            for tabel in (self.tabel_penerima, self.tabel_histori):
                terapkan_tema_tabel(
                    tabel,
                    is_dark,
                    font_size_pt=zoom_metrics.font_base_pt,
                )
                zoom_helper.terapkan_zoom_tabel(tabel, z=z)
        finally:
            self._sedang_menerapkan_zoom = False