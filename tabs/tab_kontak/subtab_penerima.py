# tabs/tab_kontak/subtab_penerima.py
import json
from PySide6.QtCore import QSettings, Qt
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
    QStyledItemDelegate,
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
from utils.widget_helpers import atur_tinggi_input, paksa_kapital_lineedit as helper_paksa_kapital_lineedit
from utils.mixins import ZoomTableMixin
from utils.table_helper import buat_tabel_item
from utils.date_ind_format import format_tanggal_ke_ui
import utils.zoom as zoom_helper
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
    KONTAK_PENERIMA_COLUMN_WIDTHS,
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


class _ComboBoxDelegate(QStyledItemDelegate):
    """Editor combo untuk kolom tabel tanpa mengubah mekanisme itemChanged lama."""

    def __init__(self, options_getter, parent=None):
        super().__init__(parent)
        self._options_getter = options_getter

    def _options(self):
        try:
            values = self._options_getter() or []
        except Exception:
            values = []
        hasil = []
        for value in values:
            text = str(value or "").strip().upper()
            if text and text not in hasil:
                hasil.append(text)
        return hasil

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(self._options())
        atur_tinggi_input(combo)
        return combo

    def setEditorData(self, editor, index):
        value = str(index.data(Qt.ItemDataRole.EditRole) or "").strip().upper()
        idx = editor.findText(value, Qt.MatchFlag.MatchFixedString)
        if idx < 0 and value:
            editor.addItem(value)
            idx = editor.count() - 1
        if editor.count() > 0:
            editor.setCurrentIndex(max(0, idx))

    def setModelData(self, editor, model, index):
        model.setData(
            index,
            editor.currentText().strip().upper(),
            Qt.ItemDataRole.EditRole,
        )

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


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
    KOLOM_TIDAK_DIEDIT = (KOL_NO, KOL_ID, KOL_TOTAL_TRANSAKSI, KOL_STATUS_TAGIHAN)

    def __init__(self):
        super().__init__()
        self._sedang_menerapkan_zoom = False
        self.init_ui()

    def init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(*KONTAK_SUBTAB_MARGINS)
        layout_utama.setSpacing(KONTAK_SPACING)

        self.panel_kiri = self._bangun_panel_penerima()
        self.panel_kanan = self._bangun_panel_histori()

        self.splitter = buat_splitter(
            self.panel_kiri,
            self.panel_kanan,
            orientation=Qt.Orientation.Horizontal,
            ukuran_awal=KONTAK_SPLITTER_INITIAL_SIZES,
            bisa_diciutkan=False,
            parent=self,
        )
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

        ukuran = get_global_font_sizes_pt(0)
        self.lbl_judul = QLabel("List Penerima")
        self.lbl_judul.setFont(_buat_font_pt(ukuran["sz_title"]))
        self.txt_cari = self._buat_input_cari(
            "Cari penerima...",
            KONTAK_SEARCH_WIDTH,
            self.filter_pencarian_tabel,
            ukuran["sz_input"],
        )
        self.btn_tambah_penerima = QPushButton("+ Tambah Penerima")
        self.btn_tambah_penerima.setFixedHeight(KONTAK_ADD_BUTTON_HEIGHT)
        self.btn_tambah_penerima.clicked.connect(self.tampilkan_dialog_tambah_penerima)

        header = self._buat_header(self.lbl_judul, self.txt_cari)
        header.insertWidget(2, self.btn_tambah_penerima)
        layout.addLayout(header)

        self.tabel_penerima = QTableWidget()
        self._konfigurasi_tabel(
            self.tabel_penerima,
            self.HEADER_PENERIMA,
            editable=True,
        )
        self.tabel_penerima.setColumnHidden(self.KOL_ID, True)
        self._delegate_provinsi = _ComboBoxDelegate(
            self._daftar_provinsi_session,
            self.tabel_penerima,
        )
        self._delegate_pembayaran = _ComboBoxDelegate(
            self._daftar_pembayaran_session,
            self.tabel_penerima,
        )
        self.tabel_penerima.setItemDelegateForColumn(
            self.KOL_PROVINSI,
            self._delegate_provinsi,
        )
        self.tabel_penerima.setItemDelegateForColumn(
            self.KOL_PEMBAYARAN,
            self._delegate_pembayaran,
        )
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
        panel.setMinimumWidth(KONTAK_PANEL_MIN_WIDTH)
        panel.setMaximumWidth(KONTAK_PANEL_MAX_WIDTH)
        panel.setObjectName("panelHistori")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(*KONTAK_PANEL_MARGINS)
        layout.setSpacing(KONTAK_SPACING)

        ukuran = get_global_font_sizes_pt(0)
        self.lbl_judul_histori = QLabel("📦 Riwayat Penerimaan")
        self.lbl_judul_histori.setFont(_buat_font_pt(ukuran["sz_total"]))
        self.txt_cari_histori = self._buat_input_cari(
            "Cari di histori ini...",
            KONTAK_HISTORY_SEARCH_WIDTH,
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
        self.load_data()
        self.filter_pencarian_tabel()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_session_ui()

    def _tema_gelap_aktif(self):
        win = self.window()
        return bool(win and hasattr(win, "current_theme") and win.current_theme == "dark")

    @staticmethod
    def _nilai_setting_list(key, default=None):
        """Baca list setting dari database/session aktif, sama seperti Tab Resi."""
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
        # Sama dengan pilihan Metode Payment di Tab Resi.
        return ["TF / INVOICE", "CASH"]

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

    def _buat_form_tambah_penerima(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Tambah Penerima")
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

    def _ambil_data_edit_penerima(self, row):
        tabel = self.tabel_penerima
        return (
            tabel.item(row, self.KOL_ID).text().strip(),
            tabel.item(row, self.KOL_NAMA_PENERIMA).text().strip().upper(),
            tabel.item(row, self.KOL_TELEPON).text().strip(),
            tabel.item(row, self.KOL_ALAMAT).text().strip().upper(),
            tabel.item(row, self.KOL_KOTA).text().strip().upper(),
            tabel.item(row, self.KOL_PROVINSI).text().strip().upper(),
            tabel.item(row, self.KOL_PEMBAYARAN).text().strip().upper(),
        )

    def _terapkan_data_edit_penerima(self, row, nama, alamat, kota, provinsi, pembayaran):
        self.tabel_penerima.blockSignals(True)
        try:
            for kolom, nilai in (
                (self.KOL_NAMA_PENERIMA, nama), (self.KOL_KOTA, kota),
                (self.KOL_ALAMAT, alamat), (self.KOL_PROVINSI, provinsi),
                (self.KOL_PEMBAYARAN, pembayaran),
            ):
                self.tabel_penerima.item(row, kolom).setText(nilai)
        finally:
            self.tabel_penerima.blockSignals(False)

    def simpan_edit_penerima_dari_tabel(self, item):
        if not item or item.column() in self.KOLOM_TIDAK_DIEDIT:
            return
        row = item.row()
        try:
            id_penerima, nama, no_hp, alamat, kota, provinsi, pembayaran = (
                self._ambil_data_edit_penerima(row)
            )
            sukses, _pesan = db_service.update_master_penerima_dari_tabel(
                id_penerima, CURRENT_SESSION.get("kode_cabang", "PUSAT"),
                nama, no_hp, alamat, kota, provinsi, pembayaran,
            )
            if not sukses:
                self.refresh_session_ui()
                return
            self._terapkan_data_edit_penerima(row, nama, alamat, kota, provinsi, pembayaran)
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
            (self.btn_tambah_penerima, "sz_input", False),
        ):
            widget.setFont(_buat_font_pt(ukuran[token], tebal=tebal))
        atur_tinggi_input((self.txt_cari, self.txt_cari_histori))

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