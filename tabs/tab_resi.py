# tabs/tab_resi.py
import json
import logging
from decimal import Decimal, ROUND_HALF_UP

from PySide6.QtCore import (
    QDate,
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    QSettings,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION
import services.database_service as db_service
from themes.components.notification import FADE_NOTIFICATION_STYLE
from themes.components.combobox import terapkan_popup_bawah_combobox
from themes.components.calendar import terapkan_style_kalender
from themes.modules.resi import (
    get_btn_simpan_cetak_style,
    get_resi_detail_barang_theme,
    get_resi_rekening_styles,
    get_resi_static_styles,
    get_resi_styles,
    get_btn_clear_container_style,
)

from utils.splitter_helper import buat_splitter
from utils.printer.print_resi import cetak_resi_ke_printer
from utils import zoom as zoom_helper
from utils.date_ind_format import format_tanggal_ke_db, format_tanggal_ke_ui
from utils.reset_form_helper import reset_form_input_global
from utils.mixins import ZoomTableMixin
from utils.number_formatters import (
    angka_indonesia_to_decimal,
    format_input_ribuan_gaya_indonesia,
    format_ke_rupiah,
    rupiah_to_int,
)
from utils.table_helper import buat_tabel_item
from utils.typography import (
    APPLICATION_NAME,
    ORGANIZATION_NAME,
    get_global_font_sizes,
    konversi_font_qss_ke_point,
    konversi_style_font_ke_point,
    ukuran_font_px_ke_pt,
)
from utils.validators import UppercaseValidator, get_decimal_validator
from utils.widget_helpers import (
    _blokir_signal_sementara,
    paksa_kapital_lineedit,
)

logger = logging.getLogger(__name__)


def _format_ongkir_aman(nilai_mentah):
    nilai_mentah = str(nilai_mentah or "")
    try:
        nilai = int(nilai_mentah) if nilai_mentah.isdigit() else 0
        return format_ke_rupiah(nilai) if nilai > 0 else ""
    except (ValueError, TypeError):
        return nilai_mentah


class FadeNotification(QWidget):
    def __init__(self, message, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(message, self)

        self.label.setStyleSheet(konversi_font_qss_ke_point(FADE_NOTIFICATION_STYLE))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        if parent:
            self.center_on_parent(parent)

        QTimer.singleShot(1000, self.start_fade_out)

    def center_on_parent(self, parent):
        self.adjustSize()
        main_window = parent.window().geometry()
        x = main_window.x() + (main_window.width() - self.width()) // 2
        y = main_window.y() + (main_window.height() - self.height()) // 2
        self.move(x, y)

    def start_fade_out(self):
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.finished.connect(self.close)
        self.anim.start()


class _ResetButtonResizeWatcher(QWidget):
    """Menjaga tombol reset tetap di kanan atas saat container berubah ukuran."""

    def __init__(self, container, tombol):
        super().__init__(container)
        self._container = container
        self._tombol = tombol
        self.hide()

    def eventFilter(self, watched, event):
        if watched is self._container and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self._perbarui_posisi()

        return False

    def _perbarui_posisi(self):
        if self._container is None or self._tombol is None:
            return

        self._tombol.move(
            max(2, self._container.width() - self._tombol.width() - 4),
            3,
        )
        self._tombol.raise_()


class TabResi(ZoomTableMixin, QWidget):
    KOL_NO = 0
    KOL_NAMA_BARANG = 1
    KOL_KOLI = 2
    KOL_BERAT = 3
    KOL_CBM = 4

    LEBAR_KOLOM_DASAR = {
        KOL_NO: 42,
        KOL_NAMA_BARANG: 400,
        KOL_KOLI: 100,
        KOL_BERAT: 100,
        KOL_CBM: 100,
    }
    KOLOM_INPUT_BARANG = (KOL_NAMA_BARANG, KOL_KOLI, KOL_BERAT, KOL_CBM)
    ZOOM_KOLOM = {
        KOL_NO: (30, 2),
        KOL_NAMA_BARANG: (150, 10),
        KOL_KOLI: (70, 4),
        KOL_BERAT: (70, 4),
        KOL_CBM: (70, 4),
    }

    def __init__(self):
        super().__init__()
        self.kode_cabang = self._kode_cabang_aktif()
        self.settings = QSettings(
            ORGANIZATION_NAME,
            APPLICATION_NAME,
        )
        self.current_theme = self.settings.value("theme", "light")
        self.current_resi_data = None

        # Menyimpan subtotal sebelum PPN agar pergantian PAJAK/NONPAJAK
        # tidak menyebabkan pajak dihitung berulang kali.
        self._mode_total_ongkir = None
        self._subtotal_manual_ongkir = 0
        self._sedang_set_total_ongkir = False

        self.init_ui()

    @staticmethod
    def _kode_cabang_aktif():
        return CURRENT_SESSION.get("kode_cabang", "PUSAT")

    def init_ui(self):
        layout_utama = QHBoxLayout(self)
        layout_utama.setContentsMargins(0, 0, 0, 0)
        styles_awal = konversi_style_font_ke_point(
            get_resi_static_styles(self.current_theme == "dark")
        )

        self.scroll_kiri = QScrollArea()
        self.scroll_kiri.setMinimumWidth(700)
        self.scroll_kiri.setMaximumWidth(1800)
        self.scroll_kiri.setWidgetResizable(True)
        self.scroll_kiri.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_kiri.setStyleSheet(styles_awal["scroll_kiri"])

        self.widget_kiri = QWidget()
        layout_kiri = QVBoxLayout(self.widget_kiri)
        layout_kiri.setContentsMargins(8, 8, 8, 8)
        layout_kiri.setSpacing(8)

        self._bangun_top_bar(layout_kiri)
        self._bangun_form_pihak(layout_kiri)
        self._bangun_detail_barang(layout_kiri)
        self._bangun_area_pembayaran(layout_kiri, styles_awal)
        self._bangun_action_bar(layout_kiri)
        self._bangun_histori()

        self.scroll_kiri.setWidget(self.widget_kiri)
        self.splitter = buat_splitter(
            self.scroll_kiri,
            self.widget_kanan,
            orientation=Qt.Orientation.Horizontal,
            ukuran_awal=(856, 256),
            bisa_diciutkan=False,
            parent=self,
        )
        layout_utama.addWidget(self.splitter)

        self.setup_uppercase_hooks()
        self.setup_autocomplete()
        self.tambah_baris_barang()
        self.otomatisasi_nomor_resi()
        self.sesuaikan_tema_lokal()
        self.load_data_resi()
        QTimer.singleShot(0, self._posisikan_tombol_clear_container)

    @staticmethod
    def _lineedit(placeholder):
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        return widget

    @staticmethod
    def _atur_grid_identitas(grid):
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(8)
        grid.setContentsMargins(12, 12, 12, 12)
        for row in range(3):
            grid.setRowStretch(row, 1)
        grid.setColumnStretch(1, 6)
        grid.setColumnStretch(3, 4)

    @staticmethod
    def _nilai_setting_list(key, default=None):
        raw = db_service.get_setting(key)
        if isinstance(raw, str):
            return json.loads(raw)
        return raw or (default if default is not None else [])

    def _bangun_top_bar(self, layout_kiri):
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)

        self.lbl_main_title = QLabel("Form Input Surat Jalan")
        top_bar.addWidget(self.lbl_main_title)
        top_bar.addStretch(1)

        area_tanggal = QHBoxLayout()
        area_tanggal.setSpacing(8)
        self.lbl_tgl_tag = QLabel("Tanggal:")
        self.date_input = QDateEdit(self)
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setReadOnly(True)
        self.date_input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.date_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.date_input.setFixedWidth(160)
        self.date_input.setDisplayFormat("dddd, dd/MM/yyyy")
        self.date_input.dateChanged.connect(self.otomatisasi_nomor_resi)
        area_tanggal.addWidget(self.lbl_tgl_tag)
        area_tanggal.addWidget(self.date_input)
        top_bar.addLayout(area_tanggal)
        top_bar.addStretch(1)

        area_resi = QHBoxLayout()
        area_resi.setSpacing(8)
        self.lbl_resi_tag = QLabel("No. Resi:")
        self.lbl_resi_tag.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.txt_resi_display = QLabel("GEN-RESI-CODE")
        self.txt_resi_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_resi_display.setFixedWidth(200)
        self.txt_resi_display.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        area_resi.addWidget(self.lbl_resi_tag)
        area_resi.addWidget(self.txt_resi_display)
        top_bar.addLayout(area_resi)
        layout_kiri.addLayout(top_bar)

    def _bangun_form_pihak(self, layout_kiri):
        cards = QHBoxLayout()
        cards.setSpacing(8)

        self.group_pengirim = QGroupBox("")
        grid = QGridLayout(self.group_pengirim)
        self._atur_grid_identitas(grid)
        self.btn_clear_pengirim = self._buat_tombol_clear_container(
            self.group_pengirim, "Reset pengirim", self.bersihkan_data_pengirim
        )
        self.txt_pengirim = self._lineedit("Nama pengirim/perusahaan/toko ...")
        self.txt_hp_pengirim = self._lineedit("08xx xxxx ...")
        self.txt_alamat_pengirim = self._lineedit("Masukkan alamat lengkap ...")
        self.txt_kota_pengirim = self._lineedit("Kota asal ...")
        for label, widget, row, label_col, widget_col, span in (
            ("Pengirim:", self.txt_pengirim, 0, 0, 1, 1),
            ("No. HP:", self.txt_hp_pengirim, 0, 2, 3, 1),
            ("Alamat:", self.txt_alamat_pengirim, 1, 0, 1, 3),
            ("Kota Asal:", self.txt_kota_pengirim, 2, 0, 1, 1),
        ):
            grid.addWidget(QLabel(label), row, label_col)
            grid.addWidget(widget, row, widget_col, 1, span)

        self.group_penerima = QGroupBox("")
        grid = QGridLayout(self.group_penerima)
        self._atur_grid_identitas(grid)
        self.btn_clear_penerima = self._buat_tombol_clear_container(
            self.group_penerima, "Reset penerima", self.bersihkan_data_penerima
        )
        self.txt_penerima = self._lineedit("Nama penerima/perusahaan/toko...")
        self.txt_hp_penerima = self._lineedit("08xx xxxx ...")
        self.txt_alamat_penerima = self._lineedit("Masukkan alamat lengkap ...")
        self.txt_kota_penerima = self._lineedit("Kota tujuan ...")
        self.cb_provinsi = QComboBox()
        self.cb_provinsi.installEventFilter(self)
        self.cb_provinsi.addItems(
            self._nilai_setting_list(
                "provinsi_tujuan",
                ["PROVINSI A", "PROVINSI B", "PROVINSI C"],
            )
        )
        self.cb_provinsi.currentTextChanged.connect(self.otomatisasi_nomor_resi)

        tujuan = QHBoxLayout()
        tujuan.setSpacing(8)
        tujuan.setContentsMargins(0, 0, 0, 0)
        tujuan.addWidget(self.txt_kota_penerima, stretch=6)
        tujuan.addWidget(self.cb_provinsi, stretch=4)

        grid.addWidget(QLabel("Penerima:"), 0, 0)
        grid.addWidget(self.txt_penerima, 0, 1)
        grid.addWidget(QLabel("No. HP:"), 0, 2)
        grid.addWidget(self.txt_hp_penerima, 0, 3)
        grid.addWidget(QLabel("Alamat:"), 1, 0)
        grid.addWidget(self.txt_alamat_penerima, 1, 1, 1, 3)
        grid.addWidget(QLabel("Kota:"), 2, 0)
        grid.addLayout(tujuan, 2, 1, 1, 3)

        cards.addWidget(self.group_pengirim, stretch=1)
        cards.addWidget(self.group_penerima, stretch=1)
        layout_kiri.addLayout(cards)

    def _bangun_detail_barang(self, layout_kiri):
        self.group_tabel_container = QGroupBox("")
        self.group_tabel_container.setMinimumHeight(250)
        layout = QVBoxLayout(self.group_tabel_container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        self.btn_clear_barang = self._buat_tombol_clear_container(
            self.group_tabel_container,
            "Reset detail barang",
            self.bersihkan_detail_barang,
        )

        self.table_items = QTableWidget()
        self.table_items.setColumnCount(5)
        self.table_items.setHorizontalHeaderLabels(
            ["NO.", "NAMA BARANG", "KOLI", "BERAT (Kg)", "KUBIK (m³)"]
        )
        header = self.table_items.horizontalHeader()
        for kolom in self.LEBAR_KOLOM_DASAR:
            mode = (
                QHeaderView.ResizeMode.Fixed
                if kolom == self.KOL_NO
                else QHeaderView.ResizeMode.Interactive
            )
            header.setSectionResizeMode(kolom, mode)
            self.table_items.setColumnWidth(kolom, self.LEBAR_KOLOM_DASAR[kolom])
        header.setStretchLastSection(True)
        header.sectionResized.connect(self.auto_save_ukuran_kolom)
        self.table_items.setMinimumHeight(150)
        self.table_items.verticalHeader().setVisible(False)
        layout.addWidget(self.table_items)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_tambah_baris = QPushButton("➕ Tambah Baris")
        self.btn_tambah_baris.clicked.connect(self.tambah_baris_barang)
        self.btn_hapus_baris = QPushButton("🗑️ Hapus Baris")
        self.btn_hapus_baris.clicked.connect(self.hapus_baris_terpilih)
        actions.addWidget(self.btn_tambah_baris)
        actions.addWidget(self.btn_hapus_baris)
        actions.addStretch()
        layout.addLayout(actions)
        layout_kiri.addWidget(self.group_tabel_container)

    def _bangun_area_pembayaran(self, layout_kiri, styles_awal):
        area = QHBoxLayout()
        area.setSpacing(8)
        self._bangun_form_finance(area)

        self.layout_pay_method = QHBoxLayout()
        self.layout_pay_method.setContentsMargins(0, 0, 0, 0)
        self.layout_pay_method.setSpacing(8)
        self.rek_cards_labels = []
        style_card = styles_awal["rekening_card"]
        self.box_np = self._buat_panel_rekening(
            "Rekening Nonpajak", "rekening_nonpajak", style_card
        )
        self.box_p = self._buat_panel_rekening(
            "Rekening Pajak (PT)", "rekening_pajak", style_card
        )
        self.layout_pay_method.addWidget(self.box_np, stretch=1)
        self.layout_pay_method.addWidget(self.box_p, stretch=1)
        area.addLayout(self.layout_pay_method, stretch=55)
        layout_kiri.addLayout(area)

    def _bangun_form_finance(self, area):
        self.group_finance = QGroupBox("")
        grid = QGridLayout(self.group_finance)
        grid.setSpacing(8)
        grid.setContentsMargins(12, 12, 12, 12)
        self.btn_clear_finance = self._buat_tombol_clear_container(
            self.group_finance,
            "Reset detail ongkir",
            self.bersihkan_detail_pembayaran,
        )

        self.txt_ongkir_kg = self._lineedit("Ongkir /kg")
        self.txt_ongkir_kg.installEventFilter(self)
        self.txt_ongkir_m3 = self._lineedit("Ongkir /m3")
        self.txt_total_ongkir = self._lineedit("Input Bisa Otomatis dan Manual")
        self.txt_total_ongkir.setToolTip(
            "Untuk transaksi PAJAK, angka manual dianggap subtotal sebelum PPN 1,1%."
        )
        self.txt_total_ongkir.textEdited.connect(self._catat_subtotal_ongkir_manual)
        self.txt_total_ongkir.editingFinished.connect(self._terapkan_ppn_ke_total_manual)

        self.cb_pajak = QComboBox()
        self.cb_pajak.addItems(["NONPAJAK", "PAJAK (PPN 1,1%)"])
        self.cb_pajak.setToolTip("PAJAK menambahkan PPN 1,1% ke subtotal ongkir.")
        self.cb_pajak.currentTextChanged.connect(self.otomatisasi_nomor_resi)
        self.cb_pajak.currentTextChanged.connect(
            self._perbarui_total_saat_jenis_transaksi_berubah
        )
        self.cb_payment = QComboBox()
        self.cb_payment.addItems(["TF / INVOICE", "CASH"])

        for widget in (self.txt_ongkir_kg, self.txt_ongkir_m3):
            widget.textChanged.connect(self.kalkulator_finansial_otomatis)
            widget.textChanged.connect(
                lambda _text=None, w=widget: format_input_ribuan_gaya_indonesia(w)
            )
        self.txt_total_ongkir.textChanged.connect(
            lambda _text=None: format_input_ribuan_gaya_indonesia(self.txt_total_ongkir)
        )

        for row, (label, widget) in enumerate((
            ("Ongkir per kg (Rp):", self.txt_ongkir_kg),
            ("Ongkir per m3 (Rp):", self.txt_ongkir_m3),
            ("Total Ongkir (Rp):", self.txt_total_ongkir),
            ("Jenis Transaksi:", self.cb_pajak),
            ("Metode Payment:", self.cb_payment),
        )):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(widget, row, 1)
        grid.setRowStretch(5, 1)
        area.addWidget(self.group_finance, stretch=45)

    def _buat_panel_rekening(self, judul, setting_key, style_card):
        box = QGroupBox(judul)
        outer = QVBoxLayout(box)
        outer.setContentsMargins(4, 10, 4, 4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self._bangun_kartu_rekening(
            self._nilai_setting_list(setting_key),
            layout,
            style_card,
        )
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return box

    def _bangun_action_bar(self, layout_kiri):
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(0)

        self.widget_action_kiri = QWidget()
        self.widget_action_kiri.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.btn_generate_simpan = QPushButton("SIMPAN DAN CETAK")
        self.btn_generate_simpan.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_generate_simpan.setStyleSheet(
            konversi_font_qss_ke_point(get_btn_simpan_cetak_style())
        )
        self.btn_generate_simpan.clicked.connect(self.simpan_ke_database)
        self.cb_payment.installEventFilter(self)
        self.btn_generate_simpan.installEventFilter(self)

        self.widget_action_kanan = QWidget()
        self.widget_action_kanan.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        right = QHBoxLayout(self.widget_action_kanan)
        right.setContentsMargins(12, 0, 0, 0)
        right.setSpacing(0)
        self.lbl_reset_form = QPushButton("Reset Form")
        self.lbl_reset_form.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.lbl_reset_form.clicked.connect(self.reset_form_input_manual)
        self.lbl_reset_form.installEventFilter(self)
        right.addWidget(
            self.lbl_reset_form,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        right.addStretch(1)

        actions.addWidget(self.widget_action_kiri, stretch=1)
        actions.addWidget(self.btn_generate_simpan, 0, Qt.AlignmentFlag.AlignCenter)
        actions.addWidget(self.widget_action_kanan, stretch=1)
        layout_kiri.addSpacing(15)
        layout_kiri.addLayout(actions)
        layout_kiri.addStretch(1)

    def _bangun_histori(self):
        self.widget_kanan = QWidget()
        self.widget_kanan.setMinimumWidth(256)
        self.widget_kanan.setMaximumWidth(520)
        layout = QVBoxLayout(self.widget_kanan)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.txt_search = self._lineedit("Cari resi, pengirim, penerima...")
        self.txt_search.textChanged.connect(self.filter_data_resi)
        layout.addWidget(self.txt_search)

        header = QHBoxLayout()
        self.lbl_histori_title = QLabel("🕒 Histori Resi")
        self.date_histori = QDateEdit(self)
        self.date_histori.setCalendarPopup(True)
        self.date_histori.setDate(QDate.currentDate())
        self.date_histori.setFixedWidth(112)
        self.date_histori.setDisplayFormat("dd/MM/yyyy")
        self.date_histori.dateChanged.connect(self.load_data_resi)
        self.btn_reset_tgl = QPushButton("RESET")
        self.btn_reset_tgl.setFixedWidth(56)
        self.btn_reset_tgl.clicked.connect(self.reset_tanggal)
        header.addWidget(self.lbl_histori_title)
        header.addWidget(self.date_histori)
        header.addWidget(self.btn_reset_tgl)
        header.addStretch()

        self.list_histori = QListWidget()
        self.list_histori.itemDoubleClicked.connect(self.munculkan_preview)
        layout.addLayout(header)
        layout.addWidget(self.list_histori)


    def reset_form_input_manual(self, _link=None):
        jawaban = QMessageBox.question(
            self,
            "Reset Form",
            "Bersihkan seluruh data input surat jalan?\n\n"
            "Data yang belum disimpan akan hilang.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if jawaban != QMessageBox.StandardButton.Yes:
            return

        reset_form_input_global(
            self.group_pengirim,
        )
        reset_form_input_global(
            self.group_penerima,
            indeks_combo_default=0,
        )
        reset_form_input_global(
            self.group_tabel_container,
            kosongkan_tabel=True,
        )
        self._reset_status_kalkulator_ongkir()
        reset_form_input_global(
            self.group_finance,
            indeks_combo_default=0,
        )

        # Detail barang selalu kembali memiliki satu baris kosong.
        self.tambah_baris_barang()

        self.kalkulator_finansial_otomatis()
        self.otomatisasi_nomor_resi()

        QTimer.singleShot(0, self.txt_pengirim.setFocus)

    def _buat_tombol_clear_container(self, parent, tooltip, callback):
        tombol = QToolButton(parent)
        tombol.setText("⟳")
        tombol.setToolTip(tooltip)
        tombol.setFixedSize(20, 20)
        tombol.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        win = self.window()
        if win and hasattr(win, "current_theme"):
            is_dark = win.current_theme == "dark"
        else:
            is_dark = getattr(self, "current_theme", "light") == "dark"
        tombol.setStyleSheet(
            konversi_font_qss_ke_point(get_btn_clear_container_style(is_dark))
        )
        tombol.clicked.connect(callback)
        tombol.raise_()

        if not hasattr(self, "_tombol_clear_list"):
            self._tombol_clear_list = []
        self._tombol_clear_list.append(tombol)
        tombol._resize_watcher = _ResetButtonResizeWatcher(parent, tombol)
        parent.installEventFilter(tombol._resize_watcher)
        return tombol


    def _posisikan_tombol_clear_container(self):
        """Menjaga seluruh tombol reset tetap di pojok kanan atas container."""
        for tombol in getattr(self, "_tombol_clear_list", ()):
            watcher = getattr(tombol, "_resize_watcher", None)
            if watcher is not None:
                watcher._perbarui_posisi()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._posisikan_tombol_clear_container()

    def bersihkan_data_pengirim(self):
        """Membersihkan hanya input di container Pengirim."""
        reset_form_input_global(
            self.group_pengirim,
            fokus_ke=self.txt_pengirim,
        )

    def bersihkan_data_penerima(self):
        """Membersihkan hanya input di container Penerima."""
        reset_form_input_global(
            self.group_penerima,
            indeks_combo_default=0,
            fokus_ke=self.txt_penerima,
        )
        self.otomatisasi_nomor_resi()

    def bersihkan_detail_barang(self):
        """Menghapus seluruh detail barang lalu menyiapkan satu baris baru."""
        reset_form_input_global(
            self.group_tabel_container,
            kosongkan_tabel=True,
        )
        self.tambah_baris_barang()
        self.kalkulator_finansial_otomatis()

        widget_nama = self.table_items.cellWidget(
            0,
            self.KOL_NAMA_BARANG,
        )
        if widget_nama is not None:
            QTimer.singleShot(0, widget_nama.setFocus)

    def bersihkan_detail_pembayaran(self):
        """Membersihkan ongkir dan mengembalikan ComboBox ke pilihan awal."""
        self._reset_status_kalkulator_ongkir()
        reset_form_input_global(
            self.group_finance,
            indeks_combo_default=0,
            fokus_ke=self.txt_ongkir_kg,
        )
        self.kalkulator_finansial_otomatis()
        self.otomatisasi_nomor_resi()

    def showEvent(self, event):
        super().showEvent(event)
        self.kode_cabang = self._kode_cabang_aktif()
        QTimer.singleShot(0, self._posisikan_tombol_clear_container)


    def _terapkan_tema_detail_barang(
        self,
        is_dark: bool,
        sz_base: int,
    ) -> None:
        """Terapkan tema tabel tanpa memberi stylesheet pada scrollbar."""

        table = getattr(self, "table_items", None)

        if table is None:
            return

        theme = konversi_style_font_ke_point(get_resi_detail_barang_theme(
            is_dark=is_dark,
            sz_base=sz_base,
        ))

        self._detail_barang_input_qss = theme["cell_input"]

        table.setAlternatingRowColors(True)
        table.setShowGrid(True)

        font_table = table.font()
        font_table.setPointSizeF(ukuran_font_px_ke_pt(sz_base))
        table.setFont(font_table)

        table.horizontalHeader().setStyleSheet(
            theme["header"]
        )

        for row in range(table.rowCount()):
            for column in self.KOLOM_INPUT_BARANG:
                editor = table.cellWidget(row, column)
                if editor is not None:
                    editor.setStyleSheet(theme["cell_input"])

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()
        self.current_theme = "dark" if is_dark else "light"
        z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)

        zoom_berubah = getattr(self, "_zoom_terakhir_tema", None) != z
        self._zoom_terakhir_tema = z
        fs_statis, styles_statis = self._buat_resi_styles(is_dark, 0)
        fs_zoom, styles_zoom = self._buat_resi_styles(is_dark, z)

        self._pasang_stylesheet_nama(
            (
                "lbl_main_title", "lbl_tgl_tag", "lbl_resi_tag", "txt_resi_display",
                "date_input", "txt_search", "lbl_histori_title", "btn_reset_tgl",
                "list_histori", "btn_generate_simpan", "lbl_reset_form", "scroll_kiri",
            ),
            styles_statis,
        )
        self._terapkan_tema_histori_statis(fs_statis)
        self._pasang_stylesheet_nama(
            (
                "group_pengirim", "group_penerima", "group_tabel_container",
                "group_finance", "btn_tambah_baris", "btn_hapus_baris",
                "box_np", "box_p",
            ),
            styles_zoom,
        )
        self._terapkan_tema_input_zoom(styles_zoom, z)
        self._terapkan_tema_detail_barang(is_dark=is_dark, sz_base=fs_zoom["sz_base"])

        if zoom_berubah:
            self._pulihkan_ukuran_tabel_resi(z)

        self.handle_rekening_zoom(z, is_dark)
        self.date_input.update()
        self.date_histori.update()
        terapkan_style_kalender(self.date_histori, is_dark=is_dark)
        self._perbarui_style_tombol_clear(is_dark)
        QTimer.singleShot(0, self._posisikan_tombol_clear_container)

    def _tema_gelap_aktif(self):
        win = self.window()
        if win and hasattr(win, "current_theme"):
            return win.current_theme == "dark"
        return self.settings.value("theme", "light") == "dark"

    @staticmethod
    def _buat_resi_styles(is_dark, z):
        fs = get_global_font_sizes(z)
        styles = get_resi_styles(
            is_dark,
            fs["sz_title"],
            fs["sz_tag"],
            fs["sz_sm"],
            fs["sz_base"],
            fs["sz_input"],
            fs["sz_total"],
            z=z,
        )
        return fs, konversi_style_font_ke_point(styles)

    def _pasang_stylesheet_nama(self, nama_widgets, styles):
        for nama in nama_widgets:
            widget = getattr(self, nama, None)
            qss = styles.get(nama)
            if widget is not None and qss is not None:
                widget.setStyleSheet(qss)

    def _terapkan_tema_histori_statis(self, fs_statis):
        # Date histori sengaja tetap native Fusion dan tidak mengikuti zoom tabel.
        self.date_histori.setStyleSheet("")
        font = self.date_histori.font()
        font.setPointSizeF(ukuran_font_px_ke_pt(fs_statis["sz_input"]))
        self.date_histori.setFont(font)
        self.date_histori.setFixedHeight(self.txt_search.sizeHint().height())

    def _terapkan_tema_input_zoom(self, styles_zoom, z):
        for widget in (
            self.txt_pengirim, self.txt_hp_pengirim, self.txt_alamat_pengirim,
            self.txt_kota_pengirim, self.txt_penerima, self.txt_hp_penerima,
            self.txt_alamat_penerima, self.txt_kota_penerima,
            self.txt_ongkir_kg, self.txt_ongkir_m3,
        ):
            if widget is not None:
                widget.setStyleSheet(styles_zoom["input_utama"])

        comboboxes = (self.cb_provinsi, self.cb_pajak, self.cb_payment)
        for combo in comboboxes:
            zoom_helper.terapkan_zoom_widget_standar(combo, z, "sz_input")
        tinggi_input = self.txt_kota_penerima.sizeHint().height()
        for combo in comboboxes:
            combo.setFixedHeight(tinggi_input)
        terapkan_popup_bawah_combobox(comboboxes)

        if self.txt_total_ongkir is not None:
            self.txt_total_ongkir.setStyleSheet(styles_zoom["txt_total_ongkir"])

    def _pulihkan_ukuran_tabel_resi(self, z):
        self.table_items.verticalHeader().setDefaultSectionSize(34 + z)
        try:
            saved_state = self.settings.value("ukuran_tabel_resi")
            if saved_state:
                self.table_items.horizontalHeader().restoreState(saved_state)
            else:
                for kolom, (minimum, langkah) in self.ZOOM_KOLOM.items():
                    self.table_items.setColumnWidth(
                        kolom,
                        max(minimum, self.LEBAR_KOLOM_DASAR[kolom] + z * langkah),
                    )
        except Exception:
            logger.exception("Gagal memulihkan ukuran kolom tabel resi")

        self._perbarui_cache_lebar_zoom(
            self.table_items,
            self._lebar_dasar_tabel(self.table_items),
        )

    def _perbarui_style_tombol_clear(self, is_dark):
        style = konversi_font_qss_ke_point(get_btn_clear_container_style(is_dark))
        for btn in getattr(self, "_tombol_clear_list", ()):
            btn.setStyleSheet(style)


    def _bangun_kartu_rekening(self, daftar_rekening, layout_target, style_card):
        """Bangun kartu rekening dari daftar string 'bank, no_rek, a.n' ke layout_target.
        Dipakai untuk panel rekening nonpajak maupun pajak.
        """
        for rek in daftar_rekening:
            if not rek:
                continue
            parts = [p.strip() for p in rek.split(",")]
            card = QWidget()
            card.setStyleSheet(style_card)
            l_card = QVBoxLayout(card)
            l_card.setContentsMargins(10, 8, 10, 8)
            l_card.setSpacing(2)

            if len(parts) >= 3:
                lbl_top = QLabel(f"{parts[0]}")
                lbl_bottom = QLabel(f"{parts[1]}<br>a.n. {parts[2]}")
            elif len(parts) == 2:
                lbl_top = QLabel(f"<b>{parts[0]}</b>")
                lbl_bottom = QLabel(f"a.n. {parts[1]}")
            else:
                lbl_top = QLabel(f"<b>{rek}</b>")
                lbl_bottom = QLabel("")

            lbl_top.setObjectName("rek_lbl_top")
            lbl_bottom.setObjectName("rek_lbl_bottom")
            self.rek_cards_labels.extend([lbl_top, lbl_bottom])
            l_card.addWidget(lbl_top)
            l_card.addWidget(lbl_bottom)
            layout_target.addWidget(card)

    def handle_rekening_zoom(self, z, is_dark):
        rekening_styles = konversi_style_font_ke_point(
            get_resi_rekening_styles(is_dark, z)
        )

        self.setUpdatesEnabled(False)
        try:
            for lbl in self.rek_cards_labels:
                if lbl.objectName() == "rek_lbl_top":
                    lbl.setStyleSheet(rekening_styles["label_top"])
                elif lbl.objectName() == "rek_lbl_bottom":
                    lbl.setStyleSheet(rekening_styles["label_bottom"])

            parent_cards_unik = set(
                (lbl.parentWidget() for lbl in self.rek_cards_labels if lbl.parentWidget()),
            )

            for card in parent_cards_unik:
                card.setStyleSheet(rekening_styles["card"])
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def setup_uppercase_hooks(self):
        self.upper_validator = UppercaseValidator(self)
        self.txt_pengirim.setValidator(self.upper_validator)
        self.txt_alamat_pengirim.setValidator(self.upper_validator)
        self.txt_kota_pengirim.setValidator(self.upper_validator)

        self.txt_penerima.setValidator(self.upper_validator)
        self.txt_alamat_penerima.setValidator(self.upper_validator)
        self.txt_kota_penerima.setValidator(self.upper_validator)

        self.txt_search.setValidator(self.upper_validator)

    def setup_autocomplete(self):
        try:
            self.kode_cabang = self._kode_cabang_aktif()
            pengirim, penerima = db_service.ambil_data_autocomplete(self.kode_cabang)
            pengirim = self._normalisasi_autocomplete(pengirim)
            penerima = self._normalisasi_autocomplete(penerima)
            logger.debug(
                "Autocomplete dimuat - Cabang: %s | Pengirim: %d | Penerima: %d",
                self.kode_cabang,
                len(pengirim),
                len(penerima),
            )

            self.txt_pengirim.setCompleter(None)
            self.txt_penerima.setCompleter(None)
            self.comp_pengirim = self._buat_completer(
                pengirim, self.txt_pengirim, self.pilih_autocomplete_pengirim
            )
            self.comp_penerima = self._buat_completer(
                penerima, self.txt_penerima, self.pilih_autocomplete_penerima
            )
            self._hubungkan_autocomplete_once(
                self.txt_pengirim,
                "comp_pengirim",
                lambda: self.eksekusi_autofill_pengirim(self.txt_pengirim.text()),
            )
            self._hubungkan_autocomplete_once(
                self.txt_penerima,
                "comp_penerima",
                lambda: self.eksekusi_autofill_penerima(self.txt_penerima.text()),
            )
            for widget in (
                self.txt_hp_pengirim, self.txt_alamat_pengirim, self.txt_kota_pengirim,
                self.txt_hp_penerima, self.txt_alamat_penerima, self.txt_kota_penerima,
            ):
                widget.setCompleter(None)
        except Exception:
            logger.exception("Gagal menyiapkan autocomplete resi")

    @staticmethod
    def _normalisasi_autocomplete(data):
        return sorted({str(item).strip().upper() for item in data if str(item).strip()})

    @staticmethod
    def _buat_completer(data, lineedit, callback):
        completer = QCompleter(data, lineedit)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(12)
        completer.activated[str].connect(callback)
        lineedit.setCompleter(completer)
        return completer

    def _hubungkan_autocomplete_once(self, lineedit, nama_completer, autofill):
        if lineedit.property("_autocomplete_connected") == "true":
            return
        lineedit.textEdited.connect(
            lambda text: getattr(self, nama_completer, None).complete()
            if getattr(self, nama_completer, None) and str(text).strip()
            else None
        )
        lineedit.editingFinished.connect(autofill)
        lineedit.setProperty("_autocomplete_connected", "true")


    def pilih_autocomplete_pengirim(self, nama_pengirim):
        nama_pengirim = str(nama_pengirim or "").strip().upper()
        if not nama_pengirim:
            return

        self.txt_pengirim.setText(nama_pengirim)
        QTimer.singleShot(0, lambda: self.eksekusi_autofill_pengirim(nama_pengirim))

    def pilih_autocomplete_penerima(self, nama_penerima):
        nama_penerima = str(nama_penerima or "").strip().upper()
        if not nama_penerima:
            return

        self.txt_penerima.setText(nama_penerima)
        QTimer.singleShot(0, lambda: self.eksekusi_autofill_penerima(nama_penerima))

    def eksekusi_autofill_penerima(self, nama_penerima):
        nama_penerima = str(nama_penerima or "").strip().upper()
        self.kode_cabang = self._kode_cabang_aktif()

        if not nama_penerima:
            return

        try:
            detail = db_service.ambil_detail_penerima(nama_penerima, self.kode_cabang)
            if detail:
                hp_master, alamat_master, kota_master, provinsi_master = detail

                self.txt_hp_penerima.setText(str(hp_master) if hp_master else "")
                self.txt_kota_penerima.setText(
                    str(kota_master).strip().upper() if kota_master else "",
                )
                self.txt_alamat_penerima.setText(
                    str(alamat_master).strip().upper() if alamat_master else "",
                )

                if provinsi_master and hasattr(self, 'cb_provinsi'):
                    provinsi_clean = str(provinsi_master).strip().upper()
                    index = self.cb_provinsi.findText(
                        provinsi_clean,
                        Qt.MatchFlag.MatchFixedString,
                    )

                    if index >= 0:
                        self.cb_provinsi.setCurrentIndex(index)
                    else:
                        self.cb_provinsi.addItem(provinsi_clean)
                        self.cb_provinsi.setCurrentIndex(self.cb_provinsi.count() - 1)

        except Exception:
            logger.exception("Gagal menjalankan autofill penerima")

    def reset_tanggal(self):
        self.txt_search.blockSignals(True)
        self.txt_search.clear()
        self.txt_search.blockSignals(False)
        self.date_histori.blockSignals(True)
        self.date_histori.setDate(QDate.currentDate())
        self.date_histori.blockSignals(False)
        self.load_data_resi()

    def filter_data_resi(self):
        keyword = self.txt_search.text().strip().lower()
        if not keyword:
            self.load_data_resi()
            return

        self.list_histori.clear()
        kode_cabang = self._kode_cabang_aktif()

        try:
            hasil = db_service.cari_histori_resi(keyword, kode_cabang)
            for row in hasil:
                self.list_histori.addItem(f"{row[0]} - {row[1]}")
        except Exception:
            logger.exception("Gagal memuat pencarian histori resi")

    def _transaksi_kena_ppn(self):
        """True bila Jenis Transaksi memakai PPN 1,1%."""
        return self.cb_pajak.currentText().strip().upper().startswith("PAJAK")

    def _total_setelah_ppn(self, subtotal):
        """Hitung total akhir dan bulatkan ke satuan rupiah terdekat."""
        subtotal_decimal = Decimal(str(subtotal or 0))
        pengali = Decimal("1.011") if self._transaksi_kena_ppn() else Decimal("1")
        return int(
            (subtotal_decimal * pengali).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )

    def _set_total_ongkir_programatis(self, nilai):
        """Tampilkan total tanpa mengubahnya menjadi subtotal manual baru."""
        self._sedang_set_total_ongkir = True
        try:
            with _blokir_signal_sementara(self.txt_total_ongkir):
                if nilai is None or int(nilai) <= 0:
                    self.txt_total_ongkir.clear()
                else:
                    self.txt_total_ongkir.setText(format_ke_rupiah(int(nilai)))
        finally:
            self._sedang_set_total_ongkir = False

    def _catat_subtotal_ongkir_manual(self, teks):
        """Catat angka yang benar-benar diketik admin sebagai subtotal."""
        if self._sedang_set_total_ongkir:
            return

        self._mode_total_ongkir = "manual"
        self._subtotal_manual_ongkir = max(0, rupiah_to_int(teks))

    def _terapkan_ppn_ke_total_manual(self):
        """Terapkan PPN setelah admin selesai mengisi Total Ongkir manual."""
        if self._mode_total_ongkir != "manual":
            return

        total_akhir = self._total_setelah_ppn(
            self._subtotal_manual_ongkir
        )
        self._set_total_ongkir_programatis(total_akhir)

    def _perbarui_total_saat_jenis_transaksi_berubah(self, _teks=None):
        """Hitung ulang total ketika pilihan PAJAK/NONPAJAK berubah."""
        if self._mode_total_ongkir == "manual":
            self._terapkan_ppn_ke_total_manual()
        else:
            self.kalkulator_finansial_otomatis()

    def _reset_status_kalkulator_ongkir(self):
        self._mode_total_ongkir = None
        self._subtotal_manual_ongkir = 0
        self._sedang_set_total_ongkir = False

    def kalkulator_finansial_otomatis(self):
        try:
            total_berat_kargo = 0.0
            total_volume_kargo = 0.0

            for row in range(self.table_items.rowCount()):
                w_b = self.table_items.cellWidget(row, self.KOL_BERAT)
                w_v = self.table_items.cellWidget(row, self.KOL_CBM)

                if w_b and w_b.text().strip() not in {"", "-"}:
                    total_berat_kargo += float(
                        angka_indonesia_to_decimal(w_b.text())
                    )

                if w_v and w_v.text().strip() not in {"", "-"}:
                    total_volume_kargo += float(
                        angka_indonesia_to_decimal(w_v.text())
                    )

            kg_rate = float(rupiah_to_int(self.txt_ongkir_kg.text()))
            m3_rate = float(rupiah_to_int(self.txt_ongkir_m3.text()))

            subtotal_ongkir = None
            if kg_rate > 0 and total_berat_kargo > 0:
                subtotal_ongkir = total_berat_kargo * kg_rate
            elif m3_rate > 0 and total_volume_kargo > 0:
                subtotal_ongkir = total_volume_kargo * m3_rate

            if subtotal_ongkir is not None:
                self._mode_total_ongkir = "auto"
                total_akhir = self._total_setelah_ppn(subtotal_ongkir)
                self._set_total_ongkir_programatis(total_akhir)
            elif self._mode_total_ongkir == "auto":
                # Mencegah total lama tertinggal setelah berat/rate dihapus.
                self._mode_total_ongkir = None
                self._set_total_ongkir_programatis(None)

        except Exception:
            logger.exception("Gagal menghitung kalkulator finansial otomatis")

    def _cari_posisi_widget_barang(self, widget):
        """Cari posisi baris dan kolom QLineEdit yang berada di tabel barang."""
        kolom_input = (
            self.KOL_NAMA_BARANG,
            self.KOL_KOLI,
            self.KOL_BERAT,
            self.KOL_CBM,
        )

        for row in range(self.table_items.rowCount()):
            for kolom in kolom_input:
                if self.table_items.cellWidget(row, kolom) is widget:
                    return row, kolom
        return None

    def _fokuskan_widget_input(self, widget):
        """Pindahkan fokus dengan alasan Tab dan pilih isi QLineEdit."""
        if widget is None:
            return

        posisi = self._cari_posisi_widget_barang(widget)
        if posisi is not None:
            row, kolom = posisi
            self.table_items.setCurrentCell(row, kolom)
            self.table_items.scrollToItem(
                self.table_items.item(row, self.KOL_NO)
            )

        widget.setFocus(Qt.FocusReason.TabFocusReason)
        if isinstance(widget, QLineEdit):
            widget.selectAll()

    def eventFilter(self, obj, event):
        """Atur Enter serta Tab/Shift+Tab tanpa membiarkan tabel menjebak fokus."""
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)

        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if obj is self.btn_generate_simpan:
                self.btn_generate_simpan.click()
                return True
            if obj is self.lbl_reset_form:
                self.lbl_reset_form.click()
                return True

        if key not in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            return super().eventFilter(obj, event)

        mundur = (
            key == Qt.Key.Key_Backtab
            or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        )
        if self._handle_tab_navigation(obj, mundur):
            return True
        return super().eventFilter(obj, event)

    def _handle_tab_navigation(self, obj, mundur):
        if obj is self.cb_provinsi and not mundur:
            if self.table_items.rowCount() > 0:
                return self._jadwalkan_fokus_input(
                    self.table_items.cellWidget(0, self.KOL_NAMA_BARANG)
                )
            return False

        if obj is self.cb_payment and not mundur:
            self._jadwalkan_fokus_widget(
                self.btn_generate_simpan,
                Qt.FocusReason.TabFocusReason,
            )
            return True

        if obj is self.btn_generate_simpan:
            target = self.cb_payment if mundur else self.lbl_reset_form
            reason = (
                Qt.FocusReason.BacktabFocusReason
                if mundur
                else Qt.FocusReason.TabFocusReason
            )
            self._jadwalkan_fokus_widget(target, reason)
            return True

        if obj is self.lbl_reset_form and mundur:
            self._jadwalkan_fokus_widget(
                self.btn_generate_simpan,
                Qt.FocusReason.BacktabFocusReason,
            )
            return True

        if obj is self.txt_ongkir_kg and mundur and self.table_items.rowCount() > 0:
            return self._jadwalkan_fokus_input(
                self.table_items.cellWidget(
                    self.table_items.rowCount() - 1,
                    self.KOL_CBM,
                )
            )

        posisi = self._cari_posisi_widget_barang(obj)
        if posisi is None:
            return False
        row, kolom = posisi
        target = self._target_tab_barang(row, kolom, mundur)
        return self._jadwalkan_fokus_input(target)

    def _target_tab_barang(self, row, kolom, mundur):
        kolom_input = self.KOLOM_INPUT_BARANG
        indeks = kolom_input.index(kolom)
        if mundur:
            if indeks > 0:
                return self.table_items.cellWidget(row, kolom_input[indeks - 1])
            if row > 0:
                return self.table_items.cellWidget(row - 1, self.KOL_CBM)
            return self.cb_provinsi

        if indeks < len(kolom_input) - 1:
            return self.table_items.cellWidget(row, kolom_input[indeks + 1])
        if row < self.table_items.rowCount() - 1:
            return self.table_items.cellWidget(row + 1, self.KOL_NAMA_BARANG)
        return self.txt_ongkir_kg

    def _jadwalkan_fokus_input(self, target):
        if target is None:
            return False
        QTimer.singleShot(0, lambda w=target: self._fokuskan_widget_input(w))
        return True

    @staticmethod
    def _jadwalkan_fokus_widget(target, reason):
        QTimer.singleShot(0, lambda w=target, r=reason: w.setFocus(r))


    def tambah_baris_barang(self):
        row = self.table_items.rowCount()
        self.table_items.insertRow(row)
        self.table_items.setItem(
            row,
            self.KOL_NO,
            buat_tabel_item(
                row + 1,
                editable=False,
                alignment=Qt.AlignmentFlag.AlignCenter,
            ),
        )

        widgets = (
            self._buat_input_barang("NAMA / JENIS BARANG...", "nama"),
            self._buat_input_barang("-", "koli"),
            self._buat_input_barang("-", "desimal"),
            self._buat_input_barang("-", "desimal"),
        )
        for kolom, widget in zip(self.KOLOM_INPUT_BARANG, widgets):
            self.table_items.setCellWidget(row, kolom, widget)

    def _buat_input_barang(self, placeholder, jenis):
        widget = self._lineedit(placeholder)
        if jenis == "nama":
            widget.textChanged.connect(lambda: paksa_kapital_lineedit(widget))
        else:
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if jenis == "koli":
                widget.textChanged.connect(
                    lambda _text=None, w=widget: format_input_ribuan_gaya_indonesia(w)
                )
            else:
                widget.setValidator(get_decimal_validator(widget))
                widget.textChanged.connect(self.kalkulator_finansial_otomatis)

        input_qss = getattr(self, "_detail_barang_input_qss", "")
        if input_qss:
            widget.setStyleSheet(input_qss)
        widget.installEventFilter(self)
        return widget


    def hapus_baris_terpilih(self):
        current_row = self.table_items.currentRow()
        if current_row >= 0:
            self.table_items.removeRow(current_row)
        else:
            row_count = self.table_items.rowCount()
            if row_count > 0: self.table_items.removeRow(row_count - 1)

        for row in range(self.table_items.rowCount()):
            self.table_items.item(row, self.KOL_NO).setText(str(row + 1))

        self.kalkulator_finansial_otomatis()

    def auto_save_ukuran_kolom(self, logicalIndex, oldSize, newSize):
        state_sekarang = self.table_items.horizontalHeader().saveState()
        self.settings.setValue("ukuran_tabel_resi", state_sekarang)

        self._perbarui_cache_lebar_zoom(
            self.table_items,
            self._lebar_dasar_tabel(self.table_items),
        )

    def eksekusi_autofill_pengirim(self, name_val):
        name_clean = str(name_val or "").strip().upper()
        self.kode_cabang = self._kode_cabang_aktif()

        if not name_clean:
            return

        try:
            row = db_service.ambil_detail_pengirim(name_clean, self.kode_cabang)
            if row:
                self.txt_hp_pengirim.setText(str(row[0]) if row[0] else "")
                self.txt_alamat_pengirim.setText(
                    str(row[1]).strip().upper() if row[1] else "",
                )
                self.txt_kota_pengirim.setText(
                    str(row[2]).strip().upper() if row[2] else "",
                )
        except Exception:
            logger.exception("Gagal autofill pengirim")

    def otomatisasi_nomor_resi(self):
        cp = self.cb_provinsi.currentText().upper()
        kode_cabang = self._kode_cabang_aktif()

        kamus_prefix = CURRENT_SESSION.get('aturan_prefix', {})

        prefix_default = (
                str(CURRENT_SESSION.get("resi_prefix", "SYS")).strip().upper()
                or "SYS"
        )

        pref = kamus_prefix.get(
            cp,
            kamus_prefix.get("DEFAULT", prefix_default),
        )

        setting_suf = db_service.get_setting('kode_akhiran_pajak') or '-P'
        suf = setting_suf if self._transaksi_kena_ppn() else ""

        try:
            base_number, max_num = db_service.ambil_sekuens_resi(kode_cabang, pref)
        except Exception:
            base_number, max_num = 0, 0

        template = db_service.get_setting(
            'template_no_resi',
        ) or '[PREFIX][COUNTER][SUFFIX]'
        counter_final = str(max(base_number, max_num) + 1)

        hasil_resi = template.replace('[PREFIX]', pref).replace('[COUNTER]', counter_final).replace(
            '[SUFFIX]',
            suf,
        )
        self.txt_resi_display.setText(hasil_resi)

    def simpan_ke_database(self):
        self.otomatisasi_nomor_resi()
        no_resi = self.txt_resi_display.text()
        kode_cabang = self._kode_cabang_aktif()
        tanggal = format_tanggal_ke_db(QDate.currentDate())
        provinsi = self.cb_provinsi.currentText()
        kota_tujuan = self.txt_kota_penerima.text().strip()
        tujuan = f"{provinsi} - {kota_tujuan}" if kota_tujuan else provinsi
        kota_asal = self.txt_kota_pengirim.text().strip().upper()

        ringkasan = self._ambil_ringkasan_barang()
        total_ongkir = rupiah_to_int(self.txt_total_ongkir.text())
        ongkir_kg = str(rupiah_to_int(self.txt_ongkir_kg.text()))
        ongkir_m3 = str(rupiah_to_int(self.txt_ongkir_m3.text()))
        payload = self._buat_payload_transaksi(
            no_resi, kode_cabang, tanggal, provinsi, kota_tujuan, tujuan, kota_asal,
            ringkasan, total_ongkir, ongkir_kg, ongkir_m3,
        )
        sukses, pesan_error = db_service.simpan_transaksi_resi(payload)
        if not sukses:
            self._tampilkan_error_simpan(pesan_error)
            return

        data_cetak = self._buat_data_cetak(
            no_resi, kota_tujuan, ringkasan, total_ongkir, ongkir_kg, ongkir_m3
        )
        cetak_resi_ke_printer(data_cetak, self)
        self._selesaikan_simpan_sukses()

    def _ambil_ringkasan_barang(self):
        nama_barang = []
        rincian = []
        total_koli, total_berat, total_cbm = 0, 0.0, 0.0
        for row in range(self.table_items.rowCount()):
            widgets = [
                self.table_items.cellWidget(row, kolom)
                for kolom in self.KOLOM_INPUT_BARANG
            ]
            w_nama, w_qty, w_berat, w_cbm = widgets
            if not (w_nama and w_qty):
                continue
            nama = w_nama.text().strip()
            if not nama:
                continue

            koli = max(0, rupiah_to_int(w_qty.text()))
            berat = float(
                angka_indonesia_to_decimal(w_berat.text() if w_berat else "0")
            )
            cbm = float(
                angka_indonesia_to_decimal(w_cbm.text() if w_cbm else "0")
            )
            total_koli += koli
            total_berat += berat
            total_cbm += cbm
            nama_barang.append(nama)
            rincian.append({
                "nama": nama,
                "qty": str(koli) if koli > 0 else "",
                "berat": str(berat) if berat > 0 else "",
                "cbm": str(cbm) if cbm > 0 else "",
            })
        return {
            "nama_barang": nama_barang,
            "rincian": rincian,
            "koli": total_koli,
            "berat": total_berat,
            "cbm": total_cbm,
        }

    def _buat_payload_transaksi(
        self, no_resi, kode_cabang, tanggal, provinsi, kota_tujuan, tujuan,
        kota_asal, data, total_ongkir, ongkir_kg, ongkir_m3,
    ):
        return {
            "no_resi": no_resi,
            "kode_cabang": kode_cabang,
            "tanggal_masuk": tanggal,
            "pengirim": self.txt_pengirim.text().strip(),
            "hp_pengirim": self.txt_hp_pengirim.text().strip(),
            "alamat_pengirim": self.txt_alamat_pengirim.text().strip(),
            "kota_asal": kota_asal,
            "penerima": self.txt_penerima.text().strip(),
            "hp_penerima": self.txt_hp_penerima.text().strip(),
            "alamat_penerima": self.txt_alamat_penerima.text().strip(),
            "kota_tujuan": tujuan,
            "provinsi_tujuan": provinsi.strip().upper(),
            "nama_barang": ", ".join(data["nama_barang"]),
            "berat": data["berat"],
            "koli": data["koli"],
            "cbm": data["cbm"],
            "ongkir_per_kg": ongkir_kg if int(ongkir_kg) > 0 else "",
            "ongkir_per_cbm": ongkir_m3 if int(ongkir_m3) > 0 else "",
            "total_ongkir": total_ongkir,
            "pembayaran": self.cb_payment.currentText(),
            "rincian_json": json.dumps(data["rincian"]),
        }

    def _buat_data_cetak(
        self, no_resi, kota_tujuan, data, total_ongkir, ongkir_kg, ongkir_m3
    ):
        fmt_kg = _format_ongkir_aman(ongkir_kg)
        fmt_m3 = _format_ongkir_aman(ongkir_m3)
        return {
            "tanggal": format_tanggal_ke_ui(QDate.currentDate()),
            "no_resi": no_resi,
            "pengirim_nama": self.txt_pengirim.text().strip(),
            "pengirim_telp": self.txt_hp_pengirim.text().strip(),
            "pengirim_alamat": self.txt_alamat_pengirim.text().strip(),
            "penerima_nama": self.txt_penerima.text().strip(),
            "penerima_telp": self.txt_hp_penerima.text().strip(),
            "penerima_alamat": self.txt_alamat_penerima.text().strip(),
            "tipe_pajak": "PAJAK" if self._transaksi_kena_ppn() else "NONPAJAK",
            "penerima_kota": kota_tujuan,
            "list_barang": data["rincian"],
            "total_qty": str(data["koli"]),
            "total_berat": f'{data["berat"]:.1f}',
            "total_cbm": f'{data["cbm"]:.1f}',
            "total_jumlah_ongkir": (
                f"Rp {format_ke_rupiah(total_ongkir)}" if total_ongkir > 0 else ""
            ),
            "ongkir_kg": fmt_kg,
            "ongkir_m3": fmt_m3,
            "ongkir_per_kg": fmt_kg,
            "ongkir_per_cbm": fmt_m3,
            "ongkir_kg_raw": ongkir_kg,
            "ongkir_m3_raw": ongkir_m3,
        }

    def _selesaikan_simpan_sukses(self):
        self.notif_tengah = FadeNotification("💾 TERSIMPAN", self)
        self.notif_tengah.show()
        self.date_histori.setDate(QDate.currentDate())
        self.clear_form()
        self.setup_autocomplete()
        self.load_data_resi()

    def _tampilkan_error_simpan(self, error):
        kode = getattr(error, "kode", None)
        if kode == db_service.KODE_RESI_DUPLIKAT:
            QMessageBox.critical(self, "Gagal", str(error))
        elif kode == db_service.KODE_DB_ERROR:
            QMessageBox.critical(self, "Error Database", str(error))
        else:
            QMessageBox.critical(self, "Error SQL", f"Gagal simpan: {error}")


    def load_data_resi(self):
        tgl_pilih = format_tanggal_ke_db(
            self.date_histori.date()
        )
        kode_cabang = self._kode_cabang_aktif()
        self.list_histori.clear()

        try:
            hasil = db_service.ambil_histori_resi_by_tanggal(tgl_pilih, kode_cabang)
            for row in hasil:
                self.list_histori.addItem(f"{row[0]} - {row[1]}")
        except Exception:
            logger.exception("Gagal memuat histori resi untuk tanggal %s", tgl_pilih)

    def munculkan_preview(self, item):
        teks_item = item.text()
        no_resi = teks_item.split(" - ")[0]
        try:
            row = db_service.ambil_detail_resi(no_resi)
            if not row: return

            tgl_indo = format_tanggal_ke_ui(row[0])

            suffix_pajak = db_service.get_setting('kode_akhiran_pajak') or '-P'
            tipe_pajak = "PAJAK" if suffix_pajak and no_resi.endswith(
                suffix_pajak,
            ) else "NON-PAJAK"

            list_barang_html = json.loads(row[14]) if row[14] else [
                {
                    'nama': str(row[8]),
                    'qty': str(row[10]),
                    'berat': str(row[9]),
                    'cbm': str(row[11]),
                }]

            val_ongkir = int(row[12]) if row[12] else 0
            formatted_ongkir = f"Rp {format_ke_rupiah(val_ongkir)}" if val_ongkir > 0 else ""

            ongkir_kg_db = str(row[15]) if row[15] is not None else ""
            ongkir_m3_db = str(row[16]) if row[16] is not None else ""

            fmt_ongkir_kg = _format_ongkir_aman(ongkir_kg_db)
            fmt_ongkir_m3 = _format_ongkir_aman(ongkir_m3_db)

            formatted_data = {
                'tanggal': tgl_indo,
                'no_resi': no_resi,
                'pengirim_nama': str(row[1]),
                'pengirim_telp': str(row[2]),
                'pengirim_alamat': str(row[3]),
                'penerima_nama': str(row[4]),
                'penerima_telp': str(row[5]),
                'penerima_alamat': str(row[6]),
                'penerima_kota': str(row[7]),
                'tipe_pajak': tipe_pajak,
                'list_barang': list_barang_html,
                'total_qty': str(row[10]),
                'total_berat': str(row[9]),
                'total_cbm': str(row[11]),
                'total_jumlah_ongkir': formatted_ongkir,
                'ongkir_kg': fmt_ongkir_kg,
                'ongkir_m3': fmt_ongkir_m3,
                'ongkir_per_kg': fmt_ongkir_kg,
                'ongkir_per_cbm': fmt_ongkir_m3,
                'ongkir_kg_raw': ongkir_kg_db,
                'ongkir_m3_raw': ongkir_m3_db,
            }
            cetak_resi_ke_printer(formatted_data, self)
        except Exception as e:
            QMessageBox.critical(self, "Error Preview", f"Gagal memuat preview: {e}")

    def refresh_session_ui(self):
        self.kode_cabang = self._kode_cabang_aktif()
        self.clear_form()
        self.setup_autocomplete()
        self.load_data_resi()

    def auto_refresh_histori(self):
        try:
            self.load_data_resi()
        except Exception:
            logger.exception("Gagal auto-refresh histori dari tab utama")

    def clear_form(self):
        # Pertahankan pilihan yang pada implementasi lama tidak ikut di-reset.
        status_combo = {
            self.cb_provinsi: self.cb_provinsi.currentIndex(),
            self.cb_pajak: self.cb_pajak.currentIndex(),
            self.cb_payment: self.cb_payment.currentIndex(),
        }

        reset_form_input_global(self.group_pengirim)
        reset_form_input_global(self.group_penerima)
        self._reset_status_kalkulator_ongkir()
        reset_form_input_global(self.group_finance)

        with _blokir_signal_sementara(self.table_items):
            self.table_items.setRowCount(0)

        for combo, index_sebelumnya in status_combo.items():
            with _blokir_signal_sementara(combo):
                if combo.count() > 0:
                    combo.setCurrentIndex(
                        max(0, min(index_sebelumnya, combo.count() - 1))
                    )
                else:
                    combo.setCurrentIndex(-1)

        self.tambah_baris_barang()


        self.otomatisasi_nomor_resi()