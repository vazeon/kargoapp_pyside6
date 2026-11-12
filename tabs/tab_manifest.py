#tabs/tab_manifest.py
import re
from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QModelIndex,
    QSettings,
    QStringListModel,
    QTimer,
    Qt,
)
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION, DATA_CLIENT

from delegates.status_delegate import (
    StatusColorDelegate,
    update_status_delegate_theme,
)

import services.database_service as db_service
import services.numbering_service as numbering_service
from utils.input_style_helper import (
    atur_tinggi_input,
    paksa_kapital_lineedit,
    terapkan_style_input_global,
)
from themes.modules.manifest import (
    get_manifest_history_date_appearance,
    get_manifest_row_highlight,
    get_manifest_styles,
)

from utils.printer.print_manifest import cetak_manifest_ke_printer
from utils.frozen_table_helper import FrozenTableView
from utils.typography import (
    get_fixed_font_sizes,
    konversi_style_font_ke_point,
    ukuran_font_px_ke_pt,
)
from utils import zoom as zoom_helper
from utils.number_formatters import (
    format_angka_indonesia,
    format_ke_rupiah,
)
from utils.table_helper import atur_editor_sel
from utils.date_ind_format import format_tanggal_ke_ui


def _get_manifest_delegate_colors(
        is_dark,
        status,
        is_alternate_row=False,
):
    """Adapter warna highlight Manifest untuk StatusColorDelegate global."""
    del is_alternate_row
    belong = str(status or "").strip().upper() == "BELONG"
    return get_manifest_row_highlight(is_dark, belong), None


MANIFEST_TABLE_COLUMN_COUNT = 13
MANIFEST_KOL_CHECK = 0
MANIFEST_KOL_KET = 12


class _ManifestTableRow:
    """Record ringan satu baris Manifest untuk model tabel."""

    __slots__ = ("values", "checked", "status_tag")

    def __init__(self, values, checked=False, status_tag=""):
        self.values = tuple(values)
        self.checked = bool(checked)
        self.status_tag = str(status_tag or "")


class ManifestTableModel(QAbstractTableModel):
    """Model Manifest dengan penyimpanan data ringan tanpa widget permanen per sel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._headers = []
        self._rows = []
        self._column_count = 0
        self._alignments = ()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._column_count

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row_number = index.row()
        column = index.column()
        if not (0 <= row_number < len(self._rows)):
            return None
        if not (0 <= column < self._column_count):
            return None

        row = self._rows[row_number]

        if role == Qt.ItemDataRole.CheckStateRole and column == MANIFEST_KOL_CHECK:
            return Qt.CheckState.Checked if row.checked else Qt.CheckState.Unchecked

        if role == Qt.ItemDataRole.UserRole and column == MANIFEST_KOL_CHECK:
            return row.status_tag

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column < len(self._alignments):
                return self._alignments[column]
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        if role == Qt.ItemDataRole.ToolTipRole and column == MANIFEST_KOL_KET:
            return "Klik dua kali untuk mengisi atau mengubah keterangan resi."

        if role == Qt.ItemDataRole.DisplayRole:
            value = row.values[column]
            if column == MANIFEST_KOL_KET and not value:
                return "Ket..."
            return value

        if role == Qt.ItemDataRole.EditRole:
            return row.values[column]

        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False

        row_number = index.row()
        column = index.column()
        if not (0 <= row_number < len(self._rows)):
            return False
        if not (0 <= column < self._column_count):
            return False

        row = self._rows[row_number]

        if column == MANIFEST_KOL_CHECK and role == Qt.ItemDataRole.CheckStateRole:
            try:
                checked = int(value) == int(Qt.CheckState.Checked)
            except (TypeError, ValueError):
                checked = value == Qt.CheckState.Checked
            if row.checked == checked:
                return True
            row.checked = checked
            self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.CheckStateRole)])
            return True

        if column == MANIFEST_KOL_KET and role in (
            Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.DisplayRole,
        ):
            text = str(value or "").strip().upper()
            if row.values[column] == text:
                return True
            values = list(row.values)
            values[column] = text
            row.values = tuple(values)
            self.dataChanged.emit(
                index,
                index,
                [int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.EditRole)],
            )
            return True

        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == MANIFEST_KOL_CHECK:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        elif index.column() == MANIFEST_KOL_KET:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self._headers):
            return self._headers[section]
        return None

    def setColumnCount(self, count):
        count = max(0, int(count))
        self.beginResetModel()
        self._column_count = count
        self._headers = (
            self._headers[:count]
            + [""] * max(0, count - len(self._headers))
        )
        self._rows = []
        self.endResetModel()

    def setHeaders(self, labels):
        self._headers = list(labels or [])[:self._column_count]
        if self._headers:
            self.headerDataChanged.emit(
                Qt.Orientation.Horizontal, 0, len(self._headers) - 1
            )

    def setAlignments(self, alignments):
        self._alignments = tuple(alignments or ())

    def setRows(self, rows):
        prepared = list(rows or [])
        self.beginResetModel()
        self._rows = prepared
        self.endResetModel()


class ManifestTableView(FrozenTableView):
    """QTableView Manifest dengan tiga kolom kiri beku."""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            frozen_cols=3,
            fixed_cols=(MANIFEST_KOL_CHECK,),
            fixed_widths={MANIFEST_KOL_CHECK: 36},
        )
        self._manifest_model = ManifestTableModel(self)
        self.setModel(self._manifest_model)

    def setColumnCount(self, count):
        self._manifest_model.setColumnCount(count)
        self.sync_frozen_columns()

    def setHorizontalHeaderLabels(self, labels):
        self._manifest_model.setHeaders(labels)

    def rowCount(self):
        return self._manifest_model.rowCount()

    def columnCount(self):
        return self._manifest_model.columnCount()


class ManifestStatusDelegate(StatusColorDelegate):
    """Delegate highlight Manifest sekaligus editor on-demand untuk Keterangan."""

    def createEditor(self, parent, option, index):
        if index.column() != MANIFEST_KOL_KET:
            return None

        editor = QLineEdit(parent)
        editor.setObjectName("manifestKetCell")
        editor.setFrame(False)
        editor.setPlaceholderText("Ket...")
        editor.textChanged.connect(
            lambda _text, widget=editor: paksa_kapital_lineedit(widget)
        )
        atur_editor_sel(editor)
        return editor

    def setEditorData(self, editor, index):
        if not isinstance(editor, QLineEdit):
            return super().setEditorData(editor, index)
        editor.setText(str(index.data(Qt.ItemDataRole.EditRole) or ""))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        if not isinstance(editor, QLineEdit):
            return super().setModelData(editor, model, index)
        model.setData(
            index,
            editor.text().strip().upper(),
            Qt.ItemDataRole.EditRole,
        )

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class TabManifest(QWidget):
    KOL_CHECK = 0
    KOL_NO = 1
    KOL_RESI = 2
    KOL_TGL_MASUK = 3
    KOL_PENGIRIM = 4
    KOL_PENERIMA = 5
    KOL_TUJUAN = 6
    KOL_NAMA_BARANG = 7
    KOL_KOLI = 8
    KOL_BERAT = 9
    KOL_CBM = 10
    KOL_ONGKIR = 11
    KOL_KET = 12

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "TabManifest"
    SETTINGS_KEY_LEBAR_KOLOM = "lebar_kolom"

    NAMA_BULAN = {
        "01": "Januari",
        "02": "Februari",
        "03": "Maret",
        "04": "April",
        "05": "Mei",
        "06": "Juni",
        "07": "Juli",
        "08": "Agustus",
        "09": "September",
        "10": "Oktober",
        "11": "November",
        "12": "Desember",
    }

    def __init__(self):
        super().__init__()
        self.is_edit_mode = False
        self.edit_manifest_id = ""
        self._tanggal_edit_manifest = ""
        self._show_event_pertama = True
        self._sedang_menerapkan_zoom = False
        self._sedang_memuat_tabel = False
        self._sedang_memproses_manifest = False

        self._tinggi_input_manifest_sudah_diterapkan = False

        self._save_column_width_timer = QTimer(self)
        self._save_column_width_timer.setSingleShot(True)
        self._save_column_width_timer.setInterval(300)
        self._save_column_width_timer.timeout.connect(
            self._simpan_lebar_kolom_tertunda
        )

        self._kapal_master_by_key = {}

        self._ALIGNMENT_RESI_MANIFEST = tuple(
            (Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if col in (self.KOL_KOLI, self.KOL_BERAT, self.KOL_CBM)
            else (Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if col == self.KOL_TGL_MASUK
            else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            for col in range(self.KOL_KET + 1)
        )

        self.init_ui()

    @staticmethod
    def _kode_cabang_aktif():
        return CURRENT_SESSION.get("kode_cabang", "PUSAT")

    def init_ui(self):
        layout_utama = QHBoxLayout(self)
        layout_utama.setContentsMargins(0, 0, 0, 0)

        layout_kiri = self._buat_panel_kiri()
        self._bangun_header_manifest(layout_kiri)
        self._bangun_detail_manifest(layout_kiri)
        self._bangun_tabel_manifest(layout_kiri)
        self._bangun_panel_histori()

        self.scroll_kiri = QScrollArea(self)
        self.scroll_kiri.setMinimumWidth(360)
        self.scroll_kiri.setWidgetResizable(True)
        self.scroll_kiri.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_kiri.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self.scroll_kiri.setWidget(self.panel_kiri)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(self.scroll_kiri)
        self.splitter.addWidget(self.panel_kanan)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes((800, 200))
        self.splitter.setHandleWidth(1)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

        layout_utama.addWidget(self.splitter)

        self.btn_proses.clicked.connect(self.update_truk_ke_manifest)
        self.refresh_tahun_filter()
        self.load_data_resi_gudang()
        self.load_histori()
        self.generate_no_manifest()
        self.setup_autocomplete_truk()

    def _buat_panel_kiri(self):
        self.panel_kiri = QWidget()
        self.panel_kiri.setMinimumWidth(0)
        self.panel_kiri.setMaximumWidth(1800)

        layout = QVBoxLayout(self.panel_kiri)
        layout.setContentsMargins(8, 6, 6, 6)
        layout.setSpacing(8)
        return layout

    @staticmethod
    def _konfigurasi_wadah_tetap(widget, tinggi):
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        widget.setFixedHeight(tinggi)

    @staticmethod
    def _buat_grid_card(card, vertical_spacing):
        grid = QGridLayout(card)
        grid.setContentsMargins(10, 8, 8, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(vertical_spacing)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        return grid

    @staticmethod
    def _buat_label_input_manifest(teks):
        label = QLabel(teks)
        label.setMinimumWidth(70)
        return label

    @staticmethod
    def _konfigurasi_widget_expanding(widget, minimum_width=None):
        if minimum_width is not None:
            widget.setMinimumWidth(minimum_width)
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

    @staticmethod
    def _isi_grid_card_manifest(grid, rows):
        for row, (label, widget) in enumerate(rows):
            grid.addWidget(
                label,
                row,
                0,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            grid.addWidget(widget, row, 1)

    @staticmethod
    def _buat_wadah_header_field(label_text, ukuran, spacing):
        wadah = QWidget()
        layout = QHBoxLayout(wadah)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)

        label = QLabel(label_text)
        editor = QLabel()
        # editor.setReadOnly(True)
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setFixedWidth(ukuran[0])
        # atur_tinggi_input(editor)
        editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(label)
        layout.addWidget(editor)
        return wadah, label, editor

    def _bangun_header_manifest(self, layout_kiri):
        self.wadah_header_manifest = QWidget()
        self.wadah_header_manifest.setObjectName("wadahHeaderManifest")
        self._konfigurasi_wadah_tetap(self.wadah_header_manifest, 36)

        layout_header = QGridLayout(self.wadah_header_manifest)
        layout_header.setContentsMargins(0, 0, 0, 0)
        layout_header.setHorizontalSpacing(0)
        for column in range(3):
            layout_header.setColumnStretch(column, 1)

        self.lbl_title = QLabel("Manifest Pengiriman")
        layout_header.addWidget(
            self.lbl_title, 0, 0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        wadah_tanggal, self.lbl_tanggal_manifest, self.txt_tanggal_manifest = (
            self._buat_wadah_header_field("", (160, 32), 0)
        )
        layout_header.addWidget(
            wadah_tanggal, 0, 1,
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
        )

        wadah_nomor, self.lbl_no_manifest, self.txt_no_manifest = (
            self._buat_wadah_header_field("No. Manifest:", (160, 32), 8)
        )
        layout_header.addWidget(
            wadah_nomor, 0, 2,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        layout_kiri.addWidget(self.wadah_header_manifest, 0)
        self.perbarui_tanggal_header()

    @staticmethod
    def _konfigurasi_lineedit_kapital(widget, placeholder, minimum_width=None):
        widget.setPlaceholderText(placeholder)
        if minimum_width is not None:
            widget.setMinimumWidth(minimum_width)
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        widget.textChanged.connect(
            lambda _text="", editor=widget: paksa_kapital_lineedit(editor)
        )

    def _bangun_card_rute_manifest(self):
        self.card_rute_manifest = QFrame()
        self.card_rute_manifest.setObjectName("cardRuteManifest")
        self._konfigurasi_wadah_tetap(self.card_rute_manifest, 134)
        grid = self._buat_grid_card(self.card_rute_manifest, 8)

        self.lbl_input_tujuan = self._buat_label_input_manifest("Tujuan:")
        self.lbl_input_kapal = self._buat_label_input_manifest("Kapal:")
        self.lbl_input_note = self._buat_label_input_manifest("Note:")

        self.cb_filter_wilayah = QComboBox()
        self.cb_filter_wilayah.addItems(
            DATA_CLIENT.get(
                "provinsi_tujuan",
                ["PROVINSI A", "PROVINSI B", "PROVINSI C"],
            )
        )
        self._konfigurasi_widget_expanding(self.cb_filter_wilayah, 100)
        self.cb_filter_wilayah.currentTextChanged.connect(self.on_wilayah_changed)

        self.txt_nama_kapal = QLineEdit()
        self._konfigurasi_lineedit_kapital(
            self.txt_nama_kapal,
            "Nama Kapal (Opsional)",
            100,
        )
        self.txt_nama_kapal.editingFinished.connect(self.autofill_kapal_dari_input)

        self.txt_note_manifest = QLineEdit()
        self._konfigurasi_lineedit_kapital(
            self.txt_note_manifest,
            "Note (Wajib jika tanpa detail truk)",
            100,
        )
        self._isi_grid_card_manifest(grid, (
            (self.lbl_input_tujuan, self.cb_filter_wilayah),
            (self.lbl_input_kapal, self.txt_nama_kapal),
            (self.lbl_input_note, self.txt_note_manifest),
        ))

    def _bangun_card_armada_manifest(self):
        self.card_armada_manifest = QFrame()
        self.card_armada_manifest.setObjectName("cardArmadaManifest")
        self._konfigurasi_wadah_tetap(self.card_armada_manifest, 134)
        grid = self._buat_grid_card(self.card_armada_manifest, 8)

        self.lbl_input_truk = self._buat_label_input_manifest("Truk:")
        self.lbl_input_sopir = self._buat_label_input_manifest("Sopir:")
        self.lbl_input_keterangan = self._buat_label_input_manifest("Ket:")

        self.cb_jenis_truk = QComboBox()
        self._konfigurasi_widget_expanding(self.cb_jenis_truk, 65)
        self.cb_jenis_truk.currentIndexChanged.connect(
            self.on_jenis_truk_manifest_changed
        )

        self.txt_jenis_truk_lain = QLineEdit()
        self._konfigurasi_lineedit_kapital(
            self.txt_jenis_truk_lain,
            "Jenis lainnya",
            55,
        )
        self.txt_jenis_truk_lain.hide()
        self._muat_opsi_jenis_truk_manifest()

        self.txt_no_pol = QLineEdit()
        self._konfigurasi_lineedit_kapital(self.txt_no_pol, "No. Pol", 55)

        wadah_truk = QWidget()
        self._konfigurasi_widget_expanding(wadah_truk)
        layout_truk = QHBoxLayout(wadah_truk)
        layout_truk.setContentsMargins(0, 0, 0, 0)
        layout_truk.setSpacing(8)
        layout_truk.addWidget(self.cb_jenis_truk, 4)
        layout_truk.addWidget(self.txt_jenis_truk_lain, 4)
        layout_truk.addWidget(self.txt_no_pol, 4)

        self.txt_sopir = QLineEdit()
        self._konfigurasi_lineedit_kapital(self.txt_sopir, "Nama Sopir")
        self.txt_keterangan = QLineEdit()
        self._konfigurasi_lineedit_kapital(self.txt_keterangan, "Keterangan")
        self._isi_grid_card_manifest(grid, (
            (self.lbl_input_truk, wadah_truk),
            (self.lbl_input_sopir, self.txt_sopir),
            (self.lbl_input_keterangan, self.txt_keterangan),
        ))

    def _bangun_tombol_manifest(self):
        wadah = QWidget()
        wadah.setFixedSize(120, 80)
        wadah.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(wadah)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.btn_proses = QPushButton("Simpan")
        self.btn_proses.setMinimumWidth(100)
        self.btn_proses.setMinimumHeight(36)
        layout.addWidget(self.btn_proses, 0, Qt.AlignmentFlag.AlignHCenter)

        self.btn_batal_edit = QPushButton("Batal")
        self.btn_batal_edit.setMinimumWidth(98)
        self.btn_batal_edit.setMinimumHeight(32)
        self.btn_batal_edit.clicked.connect(self.batal_edit)
        self.btn_batal_edit.hide()
        layout.addWidget(self.btn_batal_edit, 0, Qt.AlignmentFlag.AlignHCenter)
        return wadah

    def _bangun_detail_manifest(self, layout_kiri):
        self.wadah_detail_manifest = QWidget()
        self.wadah_detail_manifest.setObjectName("wadahDetailManifest")
        self._konfigurasi_wadah_tetap(self.wadah_detail_manifest, 140)

        layout = QHBoxLayout(self.wadah_detail_manifest)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._bangun_card_rute_manifest()
        self._bangun_card_armada_manifest()
        wadah_tombol = self._bangun_tombol_manifest()

        layout.addWidget(self.card_rute_manifest, 5)
        layout.addWidget(self.card_armada_manifest, 6)
        layout.addWidget(wadah_tombol, 0, Qt.AlignmentFlag.AlignVCenter)
        layout_kiri.addWidget(
            self.wadah_detail_manifest,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

    def _tema_gelap_aktif(self):
        win = self.window()
        return bool(
            win
            and hasattr(win, "current_theme")
            and win.current_theme == "dark"
        )

    def _pasang_delegate_manifest(self, tabel, is_dark):
        delegate = ManifestStatusDelegate(
            status_column=self.KOL_CHECK,
            status_role=Qt.ItemDataRole.UserRole,
            color_provider=_get_manifest_delegate_colors,
            is_dark=is_dark,
            selected_checkbox_color="#ffffff",
            color_cache_size=16,
            parent=tabel,
        )
        tabel.setItemDelegate(delegate)
        setattr(tabel, "_status_color_delegate", delegate)

    def _bangun_tabel_manifest(self, layout_kiri):
        self.tabel_manifest = ManifestTableView(self)
        self.tabel_manifest.setColumnCount(MANIFEST_TABLE_COLUMN_COUNT)
        self.tabel_manifest.setHorizontalHeaderLabels([
            "✔", "NO.", "RESI", "TGL MASUK", "PENGIRIM", "PENERIMA",
            "TUJUAN", "NAMA BARANG", "KOLI", "BERAT (kg)", "KUBIK (m3)",
            "ONGKIR (Rp)", "KETERANGAN",
        ])
        self.tabel_manifest.model().setAlignments((
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
            *(
                self._alignment_cell_resi_manifest(column)
                for column in range(self.KOL_RESI, self.KOL_CBM + 1)
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        ))
        self.tabel_manifest.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked,
        )
        self.tabel_manifest.setWordWrap(False)
        self.tabel_manifest.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tabel_manifest.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel,
        )
        self.tabel_manifest.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel,
        )
        self.tabel_manifest.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.tabel_manifest.verticalHeader().setVisible(False)
        self.tabel_manifest.setAlternatingRowColors(True)

        # 1. Ambil status tema aktif terlebih dahulu
        is_dark = self._tema_gelap_aktif()

        # 2. Pasang delegate pada tabel utama
        self._pasang_delegate_manifest(self.tabel_manifest, is_dark)

        # 3. Hilangkan focus border & pasang delegate pada frozen_table
        frozen_table = getattr(self.tabel_manifest, "frozen_table", None)
        if frozen_table is not None:
            frozen_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._pasang_delegate_manifest(frozen_table, is_dark)

        self.load_lebar_kolom(self.tabel_manifest)
        zoom_helper.pasang_ctrl_scroll_zoom(
            self.tabel_manifest, self._ubah_zoom_tabel_manifest,
        )
        self.tabel_manifest.horizontalHeader().sectionResized.connect(
            self._jadwalkan_simpan_lebar_kolom
        )
        self.tabel_manifest.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout_kiri.addWidget(self.tabel_manifest, 1)
        layout_kiri.setStretch(0, 0)
        layout_kiri.setStretch(1, 0)
        layout_kiri.setStretch(2, 1)

    def _bangun_panel_histori(self):
        self.panel_kanan = QWidget()
        self.panel_kanan.setMinimumWidth(260)
        self.panel_kanan.setMaximumWidth(520)
        layout = QVBoxLayout(self.panel_kanan)
        layout.setContentsMargins(6, 8, 8, 8)
        layout.setSpacing(8)
        self.lbl_history_title = QLabel("Histori Manifest")
        layout.addWidget(self.lbl_history_title)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Tahun:"))
        self.cb_tahun_filter = QComboBox()
        self.cb_tahun_filter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cb_tahun_filter.currentTextChanged.connect(self.load_histori)
        filter_layout.addWidget(self.cb_tahun_filter)

        self.txt_cari_histori = QLineEdit()
        self._konfigurasi_lineedit_kapital(self.txt_cari_histori, "Cari manifest...")
        self._filter_histori_timer = QTimer(self)
        self._filter_histori_timer.setSingleShot(True)
        self._filter_histori_timer.setInterval(160)
        self._filter_histori_timer.timeout.connect(
            self._jalankan_filter_histori_tertunda
        )
        self.txt_cari_histori.textChanged.connect(
            self._jadwalkan_filter_histori
        )
        filter_layout.addWidget(self.txt_cari_histori)
        layout.addLayout(filter_layout)

        self.list_histori = QTreeWidget()
        self.list_histori.setColumnCount(2)
        self.list_histori.setHeaderHidden(True)
        self.list_histori.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents,
        )
        self.list_histori.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.list_histori.itemDoubleClicked.connect(self.preview_histori_manifest)
        self.list_histori.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_histori.customContextMenuRequested.connect(
            self.buka_menu_klik_kanan_histori
        )
        layout.addWidget(self.list_histori)


    def refresh_session_ui(self, refresh_autocomplete=True):
        """Menyegarkan data tab tanpa menghapus draft atau mode edit aktif."""
        self.perbarui_tanggal_header()

        if refresh_autocomplete:
            self.setup_autocomplete_truk()

        self.load_data_resi_gudang()
        self.generate_no_manifest()
        self.load_histori()

    def on_jenis_truk_manifest_changed(self, _index=None):
        """Menampilkan kolom jenis lainnya hanya saat diperlukan."""
        pilih_lainnya = self.cb_jenis_truk.currentText().strip() == "Lainnya..."
        self.txt_jenis_truk_lain.setVisible(pilih_lainnya)
        if not pilih_lainnya:
            self.txt_jenis_truk_lain.clear()

    def _muat_opsi_jenis_truk_manifest(self, jenis_terpilih=None):
        """Muat opsi jenis dari sumber data yang sama dengan Subtab Truk."""
        combo = getattr(self, "cb_jenis_truk", None)
        if combo is None:
            return

        if jenis_terpilih is None:
            sedang_lainnya = combo.currentText().strip() == "Lainnya..."
            if sedang_lainnya:
                pilihan = self.txt_jenis_truk_lain.text().strip()
            elif combo.currentIndex() > 0:
                pilihan = combo.currentText().strip()
            else:
                pilihan = ""
        else:
            pilihan = str(jenis_terpilih or "").strip()
            sedang_lainnya = False

        try:
            daftar = db_service.ambil_daftar_jenis_truk() or []
        except Exception as exc:
            print(f"[Manifest] Gagal memuat pilihan jenis truk: {exc}")
            daftar = list(getattr(db_service, "JENIS_TRUK_DEFAULT", ()))

        daftar = [str(jenis).strip() for jenis in daftar if str(jenis or "").strip()]
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("- Pilih jenis -")
            combo.addItems(daftar)
            combo.addItem("Lainnya...")

            idx_ditemukan = next(
                (idx + 1 for idx, nama in enumerate(daftar)
                 if nama.casefold() == pilihan.casefold()),
                -1,
            ) if pilihan else -1

            if idx_ditemukan >= 1:
                combo.setCurrentIndex(idx_ditemukan)
                self.txt_jenis_truk_lain.clear()
            elif pilihan:
                combo.setCurrentIndex(combo.count() - 1)
                self.txt_jenis_truk_lain.setText(pilihan.upper())
            elif sedang_lainnya:
                combo.setCurrentIndex(combo.count() - 1)
            else:
                combo.setCurrentIndex(0)
                self.txt_jenis_truk_lain.clear()
        finally:
            combo.blockSignals(False)

        self.on_jenis_truk_manifest_changed(combo.currentIndex())

    def ambil_jenis_truk_manifest(self):
        """Menghasilkan jenis truk baku untuk payload Manifest."""
        pilihan = self.cb_jenis_truk.currentText().strip()
        if pilihan == "Lainnya...":
            return self.txt_jenis_truk_lain.text().strip().upper()
        if self.cb_jenis_truk.currentIndex() <= 0:
            return ""
        return pilihan

    def set_jenis_truk_manifest(self, jenis):
        """Memilih jenis dari daftar bersama atau memakai input Lainnya."""
        self._muat_opsi_jenis_truk_manifest(str(jenis or "").strip())

    def _pastikan_completer_sopir(self):
        """Membuat completer sopir satu kali agar lifetime object Qt tetap stabil."""
        if hasattr(self, "model_autocomplete_sopir"):
            return

        self.model_autocomplete_sopir = QStringListModel(self)
        self.completer_sopir = QCompleter(self.model_autocomplete_sopir, self)
        self.completer_sopir.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.txt_sopir.setCompleter(self.completer_sopir)
        self.completer_sopir.activated.connect(self.on_sopir_selected)

    def setup_autocomplete_truk(self):
        self._muat_opsi_jenis_truk_manifest()
        try:
            rows = db_service.ambil_truk_list() or []
            sopirs = sorted(
                {
                    str(row[1]).strip().upper()
                    for row in rows
                    if len(row) > 1 and row[1]
                },
            )

            self._pastikan_completer_sopir()
            self.model_autocomplete_sopir.setStringList(sopirs)

            self.txt_no_pol.setCompleter(None)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Warning Database",
                f"Gagal memuat autocomplete truk: {e}",
            )
        finally:
            self.setup_autocomplete_kapal()

    @staticmethod
    def _normalisasi_kunci_kapal(nama):
        """Menyamakan huruf, spasi, titik, dan tanda baca untuk cek duplikat."""
        return re.sub(
            r"[^A-Z0-9]+",
            "",
            str(nama or "").strip().upper(),
        )

    def _bangun_cache_master_kapal(self, rows):
        master_by_key = {}
        for row in rows:
            if not row:
                continue
            nama = str(row[0] or "").strip().upper()
            if not nama:
                continue
            key = self._normalisasi_kunci_kapal(nama)
            if key and key not in master_by_key:
                master_by_key[key] = {
                    "nama": nama,
                    "tujuan": str(row[1] or "").strip().upper() if len(row) > 1 else "",
                    "keterangan": str(row[2] or "").strip().upper() if len(row) > 2 else "",
                    "foto": str(row[3] or "").strip() if len(row) > 3 else "",
                }
        return master_by_key

    def _pastikan_completer_kapal(self):
        if hasattr(self, "model_autocomplete_kapal"):
            return
        self.model_autocomplete_kapal = QStringListModel(self)
        self.completer_kapal = QCompleter(self.model_autocomplete_kapal, self)
        self.completer_kapal.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer_kapal.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer_kapal.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer_kapal.activated[str].connect(self.on_kapal_selected)
        self.txt_nama_kapal.setCompleter(self.completer_kapal)

    def setup_autocomplete_kapal(self):
        """Memuat master Kapal untuk autocomplete dan autofill Manifest."""
        try:
            master_by_key = self._bangun_cache_master_kapal(
                db_service.ambil_semua_kapal_full() or []
            )
            self._kapal_master_by_key = master_by_key
            self._pastikan_completer_kapal()
            self.model_autocomplete_kapal.setStringList(
                sorted(item["nama"] for item in master_by_key.values())
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Warning Database",
                f"Gagal memuat autocomplete kapal: {exc}",
            )

    def _cari_master_kapal(self, nama):
        key = self._normalisasi_kunci_kapal(nama)
        if not key:
            return None
        return self._kapal_master_by_key.get(key)

    def on_kapal_selected(self, nama):
        """Mengisi nama resmi dan tujuan Manifest dari master Kapal."""
        data = self._cari_master_kapal(nama)
        if not data:
            return

        nama_resmi = data["nama"]
        if self.txt_nama_kapal.text().strip().upper() != nama_resmi:
            self.txt_nama_kapal.setText(nama_resmi)

        tujuan = data.get("tujuan", "")
        if tujuan:
            index_tujuan = self.cb_filter_wilayah.findText(
                tujuan,
                Qt.MatchFlag.MatchFixedString,
            )
            if index_tujuan >= 0:
                self.cb_filter_wilayah.setCurrentIndex(
                    index_tujuan
                )

        detail_tooltip = []
        if tujuan:
            detail_tooltip.append(f"Tujuan: {tujuan}")
        if data.get("keterangan"):
            detail_tooltip.append(
                f"Keterangan: {data['keterangan']}"
            )
        self.txt_nama_kapal.setToolTip(
            "\n".join(detail_tooltip)
        )

    def autofill_kapal_dari_input(self):
        """Menangkap nama yang diketik manual tetapi sebenarnya sudah terdaftar."""
        nama = self.txt_nama_kapal.text().strip()
        if not nama:
            self.txt_nama_kapal.setToolTip("")
            return

        data = self._cari_master_kapal(nama)
        if data:
            self.on_kapal_selected(data["nama"])

    def _refresh_subtab_kapal(self):
        """Menyegarkan Subtab Kapal bila widget-nya sudah dibuat."""
        window = self.window()
        if not window:
            return

        for widget in window.findChildren(QWidget):
            if widget.__class__.__name__ != "SubTabKapal":
                continue

            refresh = getattr(widget, "refresh_tabel", None)
            if callable(refresh):
                try:
                    refresh()
                except RuntimeError:
                    pass
            break

    def pastikan_kapal_terdaftar(self, nama_kapal):
        nama_kapal = str(nama_kapal or "").strip().upper()
        if not nama_kapal:
            return True, ""

        self.setup_autocomplete_kapal()

        data_lama = self._cari_master_kapal(nama_kapal)
        if data_lama:
            self.on_kapal_selected(data_lama["nama"])
            return True, data_lama["nama"]

        tujuan = self.cb_filter_wilayah.currentText().strip().upper()
        sukses, pesan = db_service.simpan_atau_update_kapal_full(
            nama_kapal,
            tujuan,
            "",
            "",
            mode="TAMBAH",
        )

        if not sukses:
            self.setup_autocomplete_kapal()
            data_lama = self._cari_master_kapal(nama_kapal)
            if data_lama:
                self.on_kapal_selected(data_lama["nama"])
                return True, data_lama["nama"]

            return False, str(pesan or "Gagal menyimpan master Kapal.")

        self.setup_autocomplete_kapal()
        data_baru = self._cari_master_kapal(nama_kapal)
        nama_resmi = (
            data_baru["nama"]
            if data_baru
            else nama_kapal
        )

        self.txt_nama_kapal.setText(nama_resmi)
        self._refresh_subtab_kapal()
        return True, nama_resmi

    def on_sopir_selected(self, sopir):
        row = db_service.ambil_detail_truk_by_sopir(sopir)
        if row:
            no_polisi = row[0] if len(row) > 0 else ""
            jenis_truk = row[1] if len(row) > 1 else ""
            ket_truk = row[2] if len(row) > 2 else ""

            if no_polisi:
                self.txt_no_pol.setText(str(no_polisi))

            if jenis_truk:
                self.set_jenis_truk_manifest(jenis_truk)

            if ket_truk and str(ket_truk).strip() not in ('', '-'):
                self.txt_keterangan.setText(str(ket_truk))

    @staticmethod
    def _format_tanggal_header(tanggal):
        """Format tanggal header dalam bahasa Indonesia."""
        nama_hari = {
            1: "Senin",
            2: "Selasa",
            3: "Rabu",
            4: "Kamis",
            5: "Jumat",
            6: "Sabtu",
            7: "Minggu",
        }
        return (
            f"{nama_hari.get(tanggal.dayOfWeek(), '')}, "
            f"{tanggal.toString('dd/MM/yyyy')}"
        )

    def perbarui_tanggal_header(self):
        """Menampilkan tanggal transaksi hari ini pada header Manifest."""
        if hasattr(self, "txt_tanggal_manifest"):
            self.txt_tanggal_manifest.setText(
                self._format_tanggal_header(QDate.currentDate())
            )

    def generate_no_manifest(self):
        if self.is_edit_mode:
            self.txt_no_manifest.setText(self.edit_manifest_id)
            return

        wilayah = self.cb_filter_wilayah.currentText().strip().upper()
        try:
            result = numbering_service.peek_next_number(
                "MANIFEST",
                self._kode_cabang_aktif(),
                wilayah=wilayah,
                tanggal=QDate.currentDate().toString("yyyy-MM-dd"),
            )
            self.txt_no_manifest.setText(result.nomor)
        except Exception as exc:
            print(f"[Manifest] Gagal menghasilkan nomor manifest fixed: {exc}")
            self.txt_no_manifest.clear()

    def refresh_tahun_filter(self):
        pilihan_sebelumnya = self.cb_tahun_filter.currentText().strip()
        tahun_sekarang = str(QDate.currentDate().year())
        self.cb_tahun_filter.blockSignals(True)

        try:
            rows = db_service.ambil_daftar_tahun_manifest(
                self._kode_cabang_aktif()
            ) or []
            daftar_tahun = {
                str(row[0]).strip()
                for row in rows
                if row and str(row[0] or "").strip().isdigit()
            }
            daftar_tahun.add(tahun_sekarang)

            self.cb_tahun_filter.clear()
            self.cb_tahun_filter.addItem("Semua")
            self.cb_tahun_filter.addItems(
                sorted(daftar_tahun, reverse=True)
            )

            target = pilihan_sebelumnya or tahun_sekarang
            index_target = self.cb_tahun_filter.findText(
                target,
                Qt.MatchFlag.MatchFixedString,
            )
            self.cb_tahun_filter.setCurrentIndex(
                index_target if index_target >= 0 else 0
            )

        except Exception as exc:
            print(f"[Manifest] Gagal memuat daftar tahun: {exc}")
            self.cb_tahun_filter.clear()
            self.cb_tahun_filter.addItems(["Semua", tahun_sekarang])
            self.cb_tahun_filter.setCurrentIndex(1)

        finally:
            self.cb_tahun_filter.blockSignals(False)

    def _format_cell_resi_manifest(self, data, column):
        value = str(data) if data is not None else ""
        if column == self.KOL_TGL_MASUK and value:
            return format_tanggal_ke_ui(value)
        if column == self.KOL_TUJUAN and " - " in value:
            return value.split(" - ")[-1]
        if column in (self.KOL_KOLI, self.KOL_BERAT, self.KOL_CBM):
            return format_angka_indonesia(
                data,
                kosong_jika_nol=True,
                nilai_kosong="-",
            )
        return value

    def _alignment_cell_resi_manifest(self, column):
        try:
            return self._ALIGNMENT_RESI_MANIFEST[column]
        except IndexError:
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


    def _buat_data_baris_resi_manifest(self, row, pos):
        """Ubah satu hasil query menjadi record model tanpa objek per sel."""
        row = tuple(row or ())
        manifest_row = str(row[9] or "").strip() if len(row) > 9 else ""
        belong = bool(self.is_edit_mode and manifest_row == self.edit_manifest_id)

        values = [""] * self.KOL_KET + [""]
        values[self.KOL_NO] = str(pos + 1)

        for index in range(9):
            column = index + 2
            data = row[index] if index < len(row) else ""
            values[column] = self._format_cell_resi_manifest(data, column)

        ongkir = row[10] if len(row) > 10 else 0
        values[self.KOL_ONGKIR] = format_ke_rupiah(ongkir) if ongkir else "-"

        keterangan = row[11] if belong and len(row) > 11 and row[11] else ""
        values[self.KOL_KET] = str(keterangan or "").strip().upper()

        return _ManifestTableRow(
            values,
            checked=belong,
            status_tag="BELONG" if belong else "",
        )

    @db_service.profile_performance("Manifest.load_available_resi", threshold=0.05)
    def load_data_resi_gudang(self):
        if self._sedang_memuat_tabel:
            return

        self._sedang_memuat_tabel = True
        tabel = self.tabel_manifest

        if not hasattr(tabel, "_zoom_base_column_widths"):
            tabel._zoom_base_column_widths = {
                index: tabel.columnWidth(index)
                for index in range(tabel.columnCount())
            }

        tabel.blockSignals(True)
        tabel.setUpdatesEnabled(False)

        try:
            rows = db_service.ambil_resi_untuk_manifest(
                self._kode_cabang_aktif(),
                self.cb_filter_wilayah.currentText(),
                self.is_edit_mode,
                self.edit_manifest_id,
            ) or []
            prepared_rows = [
                self._buat_data_baris_resi_manifest(row, pos)
                for pos, row in enumerate(rows)
            ]
            tabel.model().setRows(prepared_rows)
        except Exception as exc:
            tabel.model().setRows([])
            QMessageBox.critical(
                self,
                "Error Load Data",
                f"Gagal memuat data resi manifest:\n{exc}",
            )
        finally:
            tabel.blockSignals(False)
            tabel.setUpdatesEnabled(True)
            tabel.viewport().update()
            self._sedang_memuat_tabel = False

    def _judul_grup_histori_manifest(self, tanggal_raw, tahun_terpilih):
        """Menentukan judul grup bulan histori tanpa mencampur antar tahun."""
        raw = str(tanggal_raw or "").strip()
        match = re.match(r"^(\d{4})-(\d{2})", raw)
        tahun = match.group(1) if match else ""
        bulan = match.group(2) if match else ""
        nama_bulan = self.NAMA_BULAN.get(bulan, "Tidak Diketahui")

        if str(tahun_terpilih or "").strip() == "Semua" and tahun:
            return f"{nama_bulan} {tahun}"
        return nama_bulan

    def _buat_item_histori_manifest(
        self, row, parents, font_tanggal, brush_tanggal, tahun_terpilih
    ):
        row = tuple(row or ())
        tanggal_raw = str(row[0] or "") if len(row) > 0 else ""
        manifest_id = str(row[1] or "") if len(row) > 1 else ""
        truk = str(row[2] or "") if len(row) > 2 else ""
        nama_kapal = str(row[3] or "") if len(row) > 3 else ""
        jumlah_resi = row[4] if len(row) > 4 else 0
        note_manifest = str(row[5] or "") if len(row) > 5 else ""

        tanggal_ui = format_tanggal_ke_ui(tanggal_raw)
        title = self._judul_grup_histori_manifest(tanggal_raw, tahun_terpilih)
        if title not in parents:
            parents[title] = QTreeWidgetItem(self.list_histori)
            parents[title].setText(0, title)

        child = QTreeWidgetItem(parents[title])
        child.setText(0, tanggal_ui)
        child.setFont(0, font_tanggal)
        child.setForeground(0, brush_tanggal)

        is_note_only = bool(
            note_manifest
            and truk.strip().upper() == note_manifest.strip().upper()
        )
        truk_display = (
            f" | NOTE: {note_manifest}"
            if is_note_only
            else (f" | {truk}" if truk and truk.strip() != "-" else "")
        )
        kapal_display = f" | 🚢 {nama_kapal}" if nama_kapal else ""
        child.setText(
            1,
            f"{manifest_id}{truk_display}{kapal_display} ({jumlah_resi} Resi)",
        )

        nilai_pencarian = (
            manifest_id,
            truk,
            nama_kapal,
            note_manifest,
            tanggal_raw,
            str(jumlah_resi or ""),
        )
        for role_offset, value in enumerate(nilai_pencarian):
            child.setData(
                0,
                Qt.ItemDataRole.UserRole + role_offset,
                value,
            )
        search_values = (
            tanggal_raw,
            tanggal_ui,
            child.text(1),
            *nilai_pencarian,
        )
        child.setData(
            0,
            Qt.ItemDataRole.UserRole + 10,
            " ".join(str(value or "") for value in search_values).casefold(),
        )

    @db_service.profile_performance("Manifest.load_history", threshold=0.05)
    def load_histori(self):
        self.list_histori.setUpdatesEnabled(False)
        self.list_histori.clear()
        is_dark = self._tema_gelap_aktif()
        self._filter_histori_timer.stop()
        try:
            rows = db_service.ambil_histori_manifest(
                self._kode_cabang_aktif(),
                self.cb_tahun_filter.currentText(),
            ) or []
            parents = {}
            tahun_terpilih = self.cb_tahun_filter.currentText()
            font_tanggal, warna_abu = get_manifest_history_date_appearance(is_dark)
            brush_tanggal = QBrush(warna_abu)
            for row in rows:
                self._buat_item_histori_manifest(
                    row,
                    parents,
                    font_tanggal,
                    brush_tanggal,
                    tahun_terpilih,
                )

            tahun_sekarang = str(QDate.currentDate().year())
            bulan_sekarang = f"{QDate.currentDate().month():02d}"
            if tahun_terpilih == "Semua":
                judul_bulan_berjalan = self._judul_grup_histori_manifest(
                    f"{tahun_sekarang}-{bulan_sekarang}-01",
                    tahun_terpilih,
                )
            else:
                judul_bulan_berjalan = self.NAMA_BULAN.get(
                    bulan_sekarang,
                    "Tidak Diketahui",
                )

            for parent in parents.values():
                parent.setExpanded(parent.text(0) == judul_bulan_berjalan)

            self.filter_histori(self.txt_cari_histori.text())
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error Histori",
                f"Gagal memuat histori manifest:\n{exc}",
            )
        finally:
            self.list_histori.setUpdatesEnabled(True)
            self.list_histori.viewport().update()

    def _sinkronkan_font_item_histori(self, is_dark):
        """Menyamakan font tanggal histori setelah tema atau zoom berubah."""
        font_tanggal, warna_abu = get_manifest_history_date_appearance(is_dark)

        for parent_index in range(self.list_histori.topLevelItemCount()):
            parent_item = self.list_histori.topLevelItem(parent_index)
            if parent_item is None:
                continue

            for child_index in range(parent_item.childCount()):
                child_item = parent_item.child(child_index)
                if child_item is None:
                    continue

                child_item.setFont(0, font_tanggal)
                child_item.setForeground(0, QBrush(warna_abu))

    def _ambil_resi_terpilih_manifest(self):
        resi = []
        tabel = self.tabel_manifest
        model = tabel.model()

        for row in range(model.rowCount()):
            if tabel.isRowHidden(row):
                continue

            index_check = model.index(row, self.KOL_CHECK)
            if model.data(index_check, Qt.ItemDataRole.CheckStateRole) != Qt.CheckState.Checked:
                continue

            nomor_resi = str(
                model.data(model.index(row, self.KOL_RESI), Qt.ItemDataRole.DisplayRole)
                or ""
            ).strip()
            if not nomor_resi:
                continue

            ket_text = str(
                model.data(model.index(row, self.KOL_KET), Qt.ItemDataRole.EditRole)
                or ""
            ).strip().upper()
            resi.append((nomor_resi, ket_text))

        return resi

    def _ambil_input_armada_manifest(self):
        return {
            "truk_idx": self.cb_jenis_truk.currentIndex(),
            "truk_text": self.ambil_jenis_truk_manifest(),
            "nopol": self.txt_no_pol.text().strip().upper(),
            "sopir": self.txt_sopir.text().strip().upper(),
            "keterangan": self.txt_keterangan.text().strip().upper(),
            "nama_kapal": self.txt_nama_kapal.text().strip().upper(),
            "note_manifest": self.txt_note_manifest.text().strip().upper(),
        }

    def _buat_payload_manifest_tanpa_truk(self, data):
        if data["nopol"] or data["sopir"] or data["keterangan"]:
            QMessageBox.warning(
                self,
                "Peringatan",
                "No. Polisi, Sopir, dan Keterangan hanya untuk detail truk. "
                "Pilih Jenis Truk, atau kosongkan detail truk lalu isi Note!",
            )
            self.cb_jenis_truk.setFocus()
            return None
        if not data["note_manifest"]:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Isi Note jika manifest tidak menggunakan detail truk!",
            )
            self.txt_note_manifest.setFocus()
            return None
        return {
            "no_polisi": "",
            "nama_sopir": "",
            "jenis_truk": "",
            "nama_truk": data["note_manifest"],
            "ket_truk": "",
            "nama_kapal": data["nama_kapal"],
            "note_manifest": data["note_manifest"],
        }

    def _buat_payload_manifest_dengan_truk(self, data):
        if self.cb_jenis_truk.currentText().strip() == "Lainnya..." and not data["truk_text"]:
            QMessageBox.warning(self, "Peringatan", "Jenis truk lainnya wajib diisi!")
            self.txt_jenis_truk_lain.setFocus()
            return None
        if not data["nopol"] and not data["sopir"]:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Isi minimal No. Polisi atau Nama Sopir jika jenis truk dipilih!",
            )
            self.txt_no_pol.setFocus()
            return None

        truk_full = (
            f"{data['truk_text']} - {data['nopol'] or 'BELUM DIKETAHUI'} "
            f"- {data['sopir'] or 'BELUM ADA SOPIR'}"
        )
        if data["keterangan"]:
            truk_full += f" ({data['keterangan']})"
        return {
            "no_polisi": data["nopol"],
            "nama_sopir": data["sopir"],
            "jenis_truk": data["truk_text"],
            "nama_truk": truk_full,
            "ket_truk": data["keterangan"],
            "nama_kapal": data["nama_kapal"],
            "note_manifest": data["note_manifest"],
        }

    def _buat_data_armada_manifest(self):
        data = self._ambil_input_armada_manifest()
        if data["truk_idx"] == 0:
            return self._buat_payload_manifest_tanpa_truk(data)
        return self._buat_payload_manifest_dengan_truk(data)

    def _kosongkan_input_manifest(self):
        self.cb_jenis_truk.setCurrentIndex(0)
        self.txt_jenis_truk_lain.clear()
        self.txt_no_pol.clear()
        self.txt_sopir.clear()
        self.txt_keterangan.clear()
        self.txt_nama_kapal.clear()
        self.txt_note_manifest.clear()

    def _tanggal_manifest_aktif(self):
        if self.is_edit_mode and self._tanggal_edit_manifest:
            return self._tanggal_edit_manifest
        return QDate.currentDate().toString("yyyy-MM-dd")

    def _siapkan_proses_manifest(self):
        manifest_id = (
            self.edit_manifest_id
            if self.is_edit_mode
            else self.txt_no_manifest.text().strip()
        )
        if not manifest_id:
            QMessageBox.warning(self, "Peringatan", "Nomor manifest belum tersedia.")
            return None

        resi = self._ambil_resi_terpilih_manifest()
        if not resi:
            QMessageBox.warning(self, "Warning", "Centang minimal 1 resi!")
            return None

        dict_update = self._buat_data_armada_manifest()
        if dict_update is None:
            return None
        dict_update["wilayah"] = self.cb_filter_wilayah.currentText().strip().upper()
        return manifest_id, resi, dict_update

    def _simpan_proses_manifest(self, manifest_id, resi, dict_update):
        kapal_ok, nama_kapal_resmi = self.pastikan_kapal_terdaftar(
            dict_update["nama_kapal"]
        )
        if not kapal_ok:
            QMessageBox.warning(self, "Data Kapal", nama_kapal_resmi)
            self.txt_nama_kapal.setFocus()
            return False

        dict_update["nama_kapal"] = nama_kapal_resmi
        sukses, hasil = db_service.simpan_atau_update_manifest_data(
            manifest_id,
            self._kode_cabang_aktif(),
            dict_update,
            resi,
            self.is_edit_mode,
            self._tanggal_manifest_aktif(),
        )
        if not sukses:
            QMessageBox.warning(
                self,
                "Manifest Tidak Disimpan",
                f"Manifest belum tersimpan:\n{hasil}",
            )
            return False
        if not self.is_edit_mode and hasil:
            self.txt_no_manifest.setText(str(hasil).strip().upper())
        return True

    def _selesaikan_proses_manifest(self):
        QMessageBox.information(self, "Sukses", "Manifest berhasil diproses!")
        self.setup_autocomplete_truk()
        if self.is_edit_mode:
            self.batal_edit()
            self.load_histori()
            return
        self._kosongkan_input_manifest()
        self.refresh_tahun_filter()
        self.load_data_resi_gudang()
        self.load_histori()
        self.generate_no_manifest()

    def update_truk_ke_manifest(self):
        if self._sedang_memproses_manifest:
            return

        proses = self._siapkan_proses_manifest()
        if proses is None:
            return

        self._sedang_memproses_manifest = True
        self.btn_proses.setEnabled(False)
        try:
            if self._simpan_proses_manifest(*proses):
                self._selesaikan_proses_manifest()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error",
                f"Gagal memproses manifest:\n{exc}",
            )
        finally:
            self._sedang_memproses_manifest = False
            self.btn_proses.setEnabled(True)

    @staticmethod
    def _format_tanggal_cetak(tanggal_manifest):
        tanggal = QDate.fromString(
            str(tanggal_manifest or "").strip(),
            "yyyy-MM-dd",
        )
        if tanggal.isValid():
            return tanggal.toString("dd/MM/yyyy")
        return QDate.currentDate().toString("dd/MM/yyyy")

    @staticmethod
    def _data_dari_item_histori(item):
        manifest_id = str(
            item.data(0, Qt.ItemDataRole.UserRole) or ""
        ).strip()
        truk = str(
            item.data(0, Qt.ItemDataRole.UserRole + 1) or ""
        ).strip()
        nama_kapal = str(
            item.data(0, Qt.ItemDataRole.UserRole + 2) or ""
        ).strip()
        note_manifest = str(
            item.data(0, Qt.ItemDataRole.UserRole + 3) or ""
        ).strip()
        tanggal_manifest = str(
            item.data(0, Qt.ItemDataRole.UserRole + 4) or ""
        ).strip()
        if not manifest_id:
            manifest_id = item.text(1).split(" | ")[0].strip()
        return manifest_id, truk, nama_kapal, note_manifest, tanggal_manifest

    def preview_histori_manifest(self, item):
        if not item.parent():
            return
        self.siapkan_dan_cetak_dari_id(*self._data_dari_item_histori(item))

    @staticmethod
    def _format_baris_cetak_manifest(row):
        ongkir_val = format_ke_rupiah(row[8]) if len(row) > 8 and row[8] else "-"
        ket_val = str(row[9] or "-").strip() if len(row) > 9 else "-"
        tujuan = str(row[3] or "")
        if " - " in tujuan:
            tujuan = tujuan.split(" - ")[-1]

        return (
            row[0],
            row[1],
            row[2],
            tujuan,
            row[4],
            format_angka_indonesia(row[5], kosong_jika_nol=True, nilai_kosong="-"),
            format_angka_indonesia(row[6], kosong_jika_nol=True, nilai_kosong="-"),
            format_angka_indonesia(row[7], kosong_jika_nol=True, nilai_kosong="-"),
            ongkir_val,
            ket_val,
        )

    def _buat_payload_cetak_manifest(
        self,
        m_id,
        truk,
        nama_kapal,
        note_manifest,
        tanggal_manifest,
        data,
        kode_cabang,
    ):
        if not nama_kapal:
            nama_kapal = db_service.ambil_nama_kapal_manifest(m_id, kode_cabang)
        if not note_manifest:
            note_manifest = db_service.ambil_note_manifest(m_id, kode_cabang)

        truk_cetak = str(truk or "").strip()
        note_manifest = str(note_manifest or "").strip()
        if note_manifest and truk_cetak.upper() == note_manifest.upper():
            truk_cetak = ""
        return {
            "no_manifest": m_id,
            "armada": truk_cetak,
            "note_manifest": note_manifest,
            "nama_kapal": nama_kapal,
            "tanggal": self._format_tanggal_cetak(tanggal_manifest),
            "items": [self._format_baris_cetak_manifest(row) for row in data],
        }

    def siapkan_dan_cetak_dari_id(
        self,
        m_id,
        truk,
        nama_kapal="",
        note_manifest="",
        tanggal_manifest="",
    ):
        try:
            kode_cabang = self._kode_cabang_aktif()
            daftar_resi = db_service.ambil_resi_list_by_manifest(
                m_id,
                kode_cabang,
            ) or []
            data = db_service.ambil_resi_detail_untuk_cetak(
                kode_cabang,
                daftar_resi,
            ) or []
            if not data:
                QMessageBox.warning(
                    self,
                    "Data Manifest",
                    f"Tidak ada data resi untuk manifest {m_id}.",
                )
                return

            payload = self._buat_payload_cetak_manifest(
                m_id,
                truk,
                nama_kapal,
                note_manifest,
                tanggal_manifest,
                data,
                kode_cabang,
            )
            cetak_manifest_ke_printer(payload, self)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Gagal cetak: {exc}")

    def showEvent(self, event):
        super().showEvent(event)


        if self._show_event_pertama:
            self._show_event_pertama = False
            self.perbarui_tanggal_header()
        else:
            self.refresh_session_ui()

        zoom_helper.sinkronkan_frozen_table(self.tabel_manifest, tertunda=True)

    def _terapkan_style_form_manifest(self, styles_statis):
        """Hanya menerapkan style form, card, dan input (Tabel dikelola oleh table.py)."""
        style_panel_kiri = styles_statis["panel_kiri"]
        style_panel_kiri = re.sub(
            r"(?i)\bborder(?:-[a-z_-]+)?\s*:\s*[^;]+;?",
            "",
            style_panel_kiri,
        )
        self.panel_kiri.setStyleSheet(style_panel_kiri)
        self.panel_kanan.setStyleSheet(styles_statis["panel_kanan"])
        self.lbl_title.setStyleSheet(styles_statis["lbl_title"])
        self.lbl_history_title.setStyleSheet(styles_statis["lbl_history_title"])
        self.btn_proses.setStyleSheet(styles_statis["btn_proses"])

        if not self._tinggi_input_manifest_sudah_diterapkan:
            with db_service.performance_timer(
                "UI.theme.Manifest.input_geometry_init", threshold=0.001
            ):
                atur_tinggi_input((
                    self.cb_filter_wilayah, self.txt_nama_kapal, self.txt_note_manifest,
                    self.cb_jenis_truk, self.txt_jenis_truk_lain, self.txt_no_pol,
                    self.txt_sopir, self.txt_keterangan, self.cb_tahun_filter,
                    self.txt_cari_histori,
                ))
            self._tinggi_input_manifest_sudah_diterapkan = True

        for card in (self.card_rute_manifest, self.card_armada_manifest):
            card.setStyleSheet(styles_statis["card_manifest"])
        for label in (
            self.lbl_input_tujuan, self.lbl_input_kapal, self.lbl_input_note,
            self.lbl_input_truk, self.lbl_input_sopir, self.lbl_input_keterangan,
        ):
            label.setStyleSheet(styles_statis["label_input"])

        self.lbl_tanggal_manifest.setStyleSheet(styles_statis["label_header"])
        self.lbl_no_manifest.setStyleSheet(styles_statis["lbl_no_manifest"])
        # Kedua display ini QLabel, bukan input form.
        self.txt_tanggal_manifest.setStyleSheet(styles_statis["txt_tanggal_manifest"])
        self.txt_no_manifest.setStyleSheet(styles_statis["txt_no_manifest"])

    def _terapkan_zoom_tabel_manifest(
        self,
        is_dark,
        z,
        *,
        update_geometry=True,
    ):
        """Terapkan tema tabel; hitung ulang geometri hanya saat zoom berubah."""
        tabel = self.tabel_manifest
        zoom_sebelumnya = self._sedang_menerapkan_zoom
        self._sedang_menerapkan_zoom = True
        try:
            for target in (tabel, getattr(tabel, "frozen_table", None)):
                if target is not None:
                    update_status_delegate_theme(target, is_dark)
            zoom_helper.terapkan_zoom_tabel(
                tabel,
                is_dark=is_dark,
                z=z,
                update_geometry=update_geometry,
            )
        finally:
            self._sedang_menerapkan_zoom = zoom_sebelumnya

    def _ubah_zoom_tabel_manifest(self, arah):
        z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        z = zoom_helper.simpan_zoom_level(self.__class__.__name__, z + int(arah))
        self._terapkan_zoom_tabel_manifest(self._tema_gelap_aktif(), z)

    def _terapkan_style_histori_manifest(self, styles_statis, is_dark):
        with db_service.performance_timer(
            "UI.theme.Manifest.history_stylesheet", threshold=0.001
        ):
            self.list_histori.setStyleSheet(styles_statis["list_histori"])
            font_histori = self.list_histori.font()
            font_histori.setPointSizeF(
                ukuran_font_px_ke_pt(get_fixed_font_sizes()["body_small"])
            )
            self.list_histori.setFont(font_histori)

        with db_service.performance_timer(
            "UI.theme.Manifest.history_items_sync", threshold=0.001
        ):
            self._sinkronkan_font_item_histori(is_dark)

    def sesuaikan_tema_lokal(self):
        with db_service.performance_timer(
            "UI.theme.Manifest.prepare_styles", threshold=0.001
        ):
            is_dark = self._tema_gelap_aktif()
            z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
            styles_statis = konversi_style_font_ke_point(
                get_manifest_styles(is_dark, self.is_edit_mode)
            )

        with db_service.performance_timer(
            "UI.theme.Manifest.form_styles", threshold=0.001
        ):
            self._terapkan_style_form_manifest(styles_statis)

        with db_service.performance_timer(
            "UI.theme.Manifest.table_theme", threshold=0.001
        ):
            self._terapkan_zoom_tabel_manifest(
                is_dark,
                z,
                update_geometry=False,
            )

        with db_service.performance_timer(
            "UI.theme.Manifest.history_theme", threshold=0.001
        ):
            self._terapkan_style_histori_manifest(styles_statis, is_dark)

        with db_service.performance_timer(
            "UI.theme.Manifest.global_input_styles", threshold=0.001
        ):
            terapkan_style_input_global(self, is_dark)

    def _settings_kolom(self):
        return QSettings(
            self.SETTINGS_ORGANIZATION,
            self.SETTINGS_APPLICATION,
        )

    @staticmethod
    def _normalisasi_daftar_lebar(value, jumlah_kolom):
        if not isinstance(value, (list, tuple)):
            return None
        if len(value) != jumlah_kolom:
            return None

        hasil = []
        try:
            for width in value:
                hasil.append(min(max(20, int(width)), 1500))
        except (TypeError, ValueError):
            return None
        return hasil

    def _jadwalkan_simpan_lebar_kolom(self, *_args):
        if self._sedang_menerapkan_zoom:
            return
        self._save_column_width_timer.start()

    def _simpan_lebar_kolom_tertunda(self):
        tabel = getattr(self, "tabel_manifest", None)
        if tabel is not None and not self._sedang_menerapkan_zoom:
            self.simpan_lebar_kolom(tabel)

    def simpan_lebar_kolom(self, tabel):
        if self._sedang_menerapkan_zoom:
            return

        z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        faktor = zoom_helper.dapatkan_faktor_geometri(z)

        lebar_dasar = []
        for index in range(tabel.columnCount()):
            lebar_asli = min(
                max(20, int(tabel.columnWidth(index) / faktor)),
                1500,
            )
            if index == self.KOL_CHECK:
                lebar_asli = 36
            lebar_dasar.append(lebar_asli)

            if hasattr(tabel, "_zoom_base_column_widths"):
                tabel._zoom_base_column_widths[index] = lebar_asli

        settings = self._settings_kolom()
        settings.setValue(
            self.SETTINGS_KEY_LEBAR_KOLOM,
            lebar_dasar,
        )
        settings.sync()

    def load_lebar_kolom(self, tabel):
        saved_widths = self._normalisasi_daftar_lebar(
            self._settings_kolom().value(
                self.SETTINGS_KEY_LEBAR_KOLOM
            ),
            tabel.columnCount(),
        )
        base_widths = list(
            saved_widths or [
                36, 45, 125, 105, 150, 150, 125, 180, 70, 85, 85, 110, 180,
            ]
        )

        while len(base_widths) < tabel.columnCount():
            base_widths.append(110)

        header = tabel.horizontalHeader()
        header.blockSignals(True)
        self._sedang_menerapkan_zoom = True

        try:
            for index in range(tabel.columnCount()):
                width = (
                    36
                    if index == self.KOL_CHECK
                    else base_widths[index]
                )
                tabel.setColumnWidth(index, int(width))

            tabel._zoom_base_column_widths = {
                index: int(
                    36
                    if index == self.KOL_CHECK
                    else base_widths[index]
                )
                for index in range(tabel.columnCount())
            }

        finally:
            self._sedang_menerapkan_zoom = False
            header.blockSignals(False)

    def on_wilayah_changed(self):
        if self.is_edit_mode:
            self.batal_edit()
            return

        self.generate_no_manifest()
        self.load_data_resi_gudang()

    def _jadwalkan_filter_histori(self, _text=None):
        """Gabungkan ketikan cepat menjadi satu pemindaian histori."""
        self._filter_histori_timer.start()

    def _jalankan_filter_histori_tertunda(self):
        self.filter_histori(self.txt_cari_histori.text())

    @db_service.profile_performance("Manifest.search_history", threshold=0.025)
    def filter_histori(self, text):
        keyword = str(text or "").strip().casefold()

        for index_parent in range(self.list_histori.topLevelItemCount()):
            parent = self.list_histori.topLevelItem(index_parent)
            parent_visible = False

            for index_child in range(parent.childCount()):
                child = parent.child(index_child)
                haystack = child.data(0, Qt.ItemDataRole.UserRole + 10)
                if haystack is None:
                    haystack = f"{child.text(0)} {child.text(1)}".casefold()
                match = not keyword or keyword in haystack
                child.setHidden(not match)
                parent_visible = parent_visible or match

            parent.setHidden(not parent_visible)
            if keyword and parent_visible:
                parent.setExpanded(True)

    def buka_menu_klik_kanan_histori(self, pos):
        item = self.list_histori.itemAt(pos)
        if not item or not item.parent():
            return

        # Samakan pola popup dengan Buku Gudang: QMenu top-level tanpa parent.
        menu = QMenu()
        styles = konversi_style_font_ke_point(
            get_manifest_styles(
                self._tema_gelap_aktif(),
                self.is_edit_mode,
            )
        )
        menu.setStyleSheet(styles["menu_histori"])
        act_print = menu.addAction("Preview")
        act_edit = menu.addAction("Edit")
        action = menu.exec(self.list_histori.viewport().mapToGlobal(pos))
        data = self._data_dari_item_histori(item)

        if action == act_print:
            self.siapkan_dan_cetak_dari_id(*data)
        elif action == act_edit:
            self.aktifkan_mode_edit(*data)

    def _isi_detail_truk_edit(self, truk_str, note_manifest):
        truk_bersih = str(truk_str or "").strip()
        is_note_only = bool(
            note_manifest
            and truk_bersih.upper() == note_manifest.upper()
        )
        if not truk_bersih or truk_bersih == "-" or is_note_only:
            return

        parts = truk_bersih.split(" - ", 2)
        if len(parts) < 3:
            if not note_manifest:
                self.txt_note_manifest.setText(truk_bersih.upper())
            return

        jenis_text, nopol_text, sopir_ket = parts
        self.set_jenis_truk_manifest(jenis_text.strip())

        nopol_text = nopol_text.strip()
        if nopol_text not in ("-", "BELUM DIKETAHUI"):
            self.txt_no_pol.setText(nopol_text)

        sopir_text = sopir_ket.strip()
        keterangan_text = ""
        if " (" in sopir_text and sopir_text.endswith(")"):
            sopir_text, keterangan_text = sopir_text.rsplit(" (", 1)
            keterangan_text = keterangan_text[:-1]

        if sopir_text.strip() not in ("", "-", "BELUM ADA SOPIR"):
            self.txt_sopir.setText(sopir_text.strip())
        if keterangan_text:
            self.txt_keterangan.setText(keterangan_text.strip())

    def _muat_metadata_edit_manifest(self, m_id, nama_kapal, note_manifest):
        kode_cabang = self._kode_cabang_aktif()
        nama_kapal = str(nama_kapal or "").strip().upper()
        if not nama_kapal:
            nama_kapal = db_service.ambil_nama_kapal_manifest(m_id, kode_cabang)

        if not note_manifest:
            note_manifest = db_service.ambil_note_manifest(m_id, kode_cabang)
        return nama_kapal, str(note_manifest or "").strip().upper()

    def _terapkan_tampilan_mode_edit(self, m_id):
        self.lbl_title.setText(f"Edit Manifest: {m_id}")
        self.txt_no_manifest.setText(m_id)
        self.btn_proses.setText("Simpan")
        self.btn_batal_edit.show()
        self.sesuaikan_tema_lokal()
        self.load_data_resi_gudang()

    def aktifkan_mode_edit(
        self,
        m_id,
        truk_str,
        nama_kapal="",
        note_manifest="",
        tanggal_manifest="",
    ):
        m_id = str(m_id or "").strip().upper()
        if not m_id:
            QMessageBox.warning(self, "Peringatan", "Nomor manifest tidak valid.")
            return

        self.is_edit_mode = True
        self.edit_manifest_id = m_id
        self._tanggal_edit_manifest = str(tanggal_manifest or "").strip()
        self._kosongkan_input_manifest()

        nama_kapal, note_manifest = self._muat_metadata_edit_manifest(
            m_id,
            nama_kapal,
            note_manifest,
        )
        self.txt_nama_kapal.setText(nama_kapal)
        self.txt_note_manifest.setText(note_manifest)
        self._isi_detail_truk_edit(truk_str, note_manifest)
        self._terapkan_tampilan_mode_edit(m_id)

    def batal_edit(self):
        self.is_edit_mode = False
        self.edit_manifest_id = ""
        self._tanggal_edit_manifest = ""
        self.lbl_title.setText("Manifest Pengiriman")
        self.btn_proses.setText("Simpan")
        self.btn_batal_edit.hide()
        self._kosongkan_input_manifest()

        self.sesuaikan_tema_lokal()
        self.generate_no_manifest()
        self.load_data_resi_gudang()