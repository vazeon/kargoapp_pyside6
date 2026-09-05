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
    QStringListModel,
    Qt,
    QTimer,
)
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
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
from themes.components.calendar import terapkan_style_kalender
from themes.components.table import get_table_styles
from themes.modules.resi import (
    UKURAN_FONT_HISTORI_RESI,
    UKURAN_FONT_INPUT,
    get_btn_simpan_cetak_style,
    get_resi_detail_barang_theme,
    get_resi_rekening_styles,
    get_resi_static_styles,
    get_resi_styles,
    get_btn_clear_container_style,
)
from themes.modules.manifest import (
    get_manifest_history_date_appearance,
    get_manifest_styles,
)

from utils.splitter_helper import buat_splitter
from utils.printer.print_resi import cetak_resi_ke_printer
from utils.date_ind_format import format_tanggal_ke_db, format_tanggal_ke_ui
from utils.reset_form_helper import reset_form_input_global
from utils.number_formatters import (
    angka_indonesia_to_decimal,
    format_input_ribuan_gaya_indonesia,
    format_ke_rupiah,
    rupiah_to_int,
)
from utils.table_helper import buat_tabel_item
from utils.ui_metrics import dapatkan_ui_scale, skalakan_px
from utils.modules.resi_metrics import (
    RESI_ACCOUNT_CARD_MARGINS,
    RESI_ACCOUNT_CARD_SPACING,
    RESI_ACCOUNT_CONTENT_MARGINS,
    RESI_ACCOUNT_PANEL_MARGINS,
    RESI_ACTION_RIGHT_LEFT_MARGIN,
    RESI_ACTION_TOP_GAP,
    RESI_AUDIT_DIALOG_SIZE,
    RESI_AUDIT_HISTORY_SPACING,
    RESI_AUTOCOMPLETE_MAX_VISIBLE_ITEMS,
    RESI_CLEAR_BUTTON_SIZE,
    RESI_DATE_INPUT_WIDTH,
    RESI_DESTINATION_STRETCH,
    RESI_DETAIL_CONTAINER_MIN_HEIGHT,
    RESI_FINANCE_COLUMN_STRETCH,
    RESI_FORM_CONTAINER_MARGINS,
    RESI_HISTORY_DATE_WIDTH,
    RESI_HISTORY_MARGINS,
    RESI_HISTORY_MAX_WIDTH,
    RESI_HISTORY_MIN_WIDTH,
    RESI_HISTORY_RESET_WIDTH,
    RESI_IDENTITY_COLUMN_STRETCH,
    RESI_INPUT_HEIGHT,
    RESI_ITEMS_COLUMN_MIN_WIDTH,
    RESI_ITEMS_COLUMN_WIDTHS,
    RESI_ITEMS_TABLE_MIN_HEIGHT,
    RESI_NUMBER_DISPLAY_WIDTH,
    RESI_PAGE_MARGINS,
    RESI_PAYMENT_AREA_STRETCH,
    RESI_SCROLL_LEFT_MAX_WIDTH,
    RESI_SCROLL_LEFT_MIN_WIDTH,
    RESI_SPACING,
    RESI_SPLITTER_INITIAL_SIZES,
    RESI_TABLE_CONTAINER_MARGINS,
    RESI_TABLE_ROW_HEIGHT,
    RESI_TOTAL_ONGKIR_HEIGHT,
)
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
    atur_tinggi_input,
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
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

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



class TabResi(QWidget):
    NAMA_BULAN = {
        1: "Januari",
        2: "Februari",
        3: "Maret",
        4: "April",
        5: "Mei",
        6: "Juni",
        7: "Juli",
        8: "Agustus",
        9: "September",
        10: "Oktober",
        11: "November",
        12: "Desember",
    }
    KOL_NO = 0
    KOL_NAMA_BARANG = 1
    KOL_KOLI = 2
    KOL_BERAT = 3
    KOL_CBM = 4

    LEBAR_KOLOM_DASAR = dict(RESI_ITEMS_COLUMN_WIDTHS)
    KOLOM_INPUT_BARANG = (KOL_NAMA_BARANG, KOL_KOLI, KOL_BERAT, KOL_CBM)

    def __init__(self):
        super().__init__()
        self.kode_cabang = self._kode_cabang_aktif()
        self.settings = QSettings(
            ORGANIZATION_NAME,
            APPLICATION_NAME,
        )
        self.current_theme = self.settings.value("theme", "light")
        self.current_resi_data = None
        self._mode_edit = False
        self._resi_sedang_diedit = None
        self._revision_sedang_diedit = None

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
        self.scroll_kiri.setMinimumWidth(RESI_SCROLL_LEFT_MIN_WIDTH)
        self.scroll_kiri.setMaximumWidth(RESI_SCROLL_LEFT_MAX_WIDTH)
        self.scroll_kiri.setWidgetResizable(True)
        self.scroll_kiri.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_kiri.setStyleSheet(styles_awal["scroll_kiri"])

        self.widget_kiri = QWidget()
        layout_kiri = QVBoxLayout(self.widget_kiri)
        layout_kiri.setContentsMargins(*RESI_PAGE_MARGINS)
        layout_kiri.setSpacing(RESI_SPACING)

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
            ukuran_awal=RESI_SPLITTER_INITIAL_SIZES,
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

    @staticmethod
    def _lineedit(placeholder, pakai_tinggi_lokal=True):
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        if pakai_tinggi_lokal:
            atur_tinggi_input(widget, tinggi=RESI_INPUT_HEIGHT)
        else:
            # Khusus input seperti pencarian: ikuti default widget_helpers.py.
            atur_tinggi_input(widget)
        return widget

    @staticmethod
    def _tinggi_input_detail_barang():
        return RESI_INPUT_HEIGHT

    @staticmethod
    def _tinggi_input_total_ongkir():
        return RESI_TOTAL_ONGKIR_HEIGHT

    @staticmethod
    def _atur_grid_identitas(grid):
        grid.setVerticalSpacing(RESI_SPACING)
        grid.setHorizontalSpacing(RESI_SPACING)
        grid.setContentsMargins(*RESI_FORM_CONTAINER_MARGINS)
        for row in range(3):
            grid.setRowStretch(row, 1)
        grid.setColumnStretch(1, RESI_IDENTITY_COLUMN_STRETCH[0])
        grid.setColumnStretch(3, RESI_IDENTITY_COLUMN_STRETCH[1])

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
        area_tanggal.setSpacing(RESI_SPACING)
        self.date_input = QLabel(self)
        self.date_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_input.setFixedWidth(RESI_DATE_INPUT_WIDTH)
        self._tanggal_transaksi = QDate.currentDate()
        self.set_tanggal_resi(self._tanggal_transaksi)
        area_tanggal.addWidget(self.date_input)
        top_bar.addLayout(area_tanggal)
        top_bar.addStretch(1)

        area_resi = QHBoxLayout()
        area_resi.setSpacing(RESI_SPACING)
        self.lbl_edit_mode = QLabel("Edit")
        self.lbl_edit_mode.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        font_edit = self.lbl_edit_mode.font()
        font_edit.setBold(True)
        self.lbl_edit_mode.setFont(font_edit)
        self.lbl_edit_mode.hide()

        self.lbl_resi_tag = QLabel("No. Resi:")
        self.lbl_resi_tag.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.txt_resi_display = QLabel("GEN-RESI-CODE")
        self.txt_resi_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_resi_display.setFixedWidth(RESI_NUMBER_DISPLAY_WIDTH)
        self.txt_resi_display.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        area_resi.addWidget(self.lbl_edit_mode)
        area_resi.addWidget(self.lbl_resi_tag)
        area_resi.addWidget(self.txt_resi_display)
        top_bar.addLayout(area_resi)
        layout_kiri.addLayout(top_bar)

    def _bangun_form_pihak(self, layout_kiri):
        cards = QHBoxLayout()
        cards.setSpacing(RESI_SPACING)

        self.group_pengirim = QGroupBox("")
        grid = QGridLayout(self.group_pengirim)
        self._atur_grid_identitas(grid)

        self.txt_pengirim = self._lineedit("Nama pengirim/perusahaan/toko ...")
        self.txt_hp_pengirim = self._lineedit("08xx xxxx ...")
        self.txt_alamat_pengirim = self._lineedit("Masukkan alamat lengkap ...")
        self.txt_kota_pengirim = self._lineedit("Kota asal ...")
        self.btn_clear_pengirim = self._buat_tombol_clear_container(
            self.group_pengirim,
            "Reset pengirim",
            self.bersihkan_data_pengirim,
        )

        for label, widget, row, label_col, widget_col, span in (
            ("Pengirim:", self.txt_pengirim, 0, 0, 1, 1),
            ("No. HP:", self.txt_hp_pengirim, 0, 2, 3, 1),
            ("Alamat:", self.txt_alamat_pengirim, 1, 0, 1, 3),
            ("Asal:", self.txt_kota_pengirim, 2, 0, 1, 1),
        ):
            grid.addWidget(QLabel(label), row, label_col)
            grid.addWidget(widget, row, widget_col, 1, span)

        # Ruang kanan pada baris Kota Asal dipakai sebagai area reset.
        grid.addWidget(
            self.btn_clear_pengirim,
            2,
            3,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        self.group_penerima = QGroupBox("")
        grid = QGridLayout(self.group_penerima)
        self._atur_grid_identitas(grid)

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
        self.btn_clear_penerima = self._buat_tombol_clear_container(
            self.group_penerima,
            "Reset penerima",
            self.bersihkan_data_penerima,
        )

        tujuan = QHBoxLayout()
        tujuan.setSpacing(RESI_SPACING)
        tujuan.setContentsMargins(0, 0, 0, 0)
        tujuan.addWidget(self.txt_kota_penerima, stretch=RESI_DESTINATION_STRETCH[0])
        tujuan.addWidget(self.cb_provinsi, stretch=RESI_DESTINATION_STRETCH[1])
        tujuan.addStretch(RESI_DESTINATION_STRETCH[2])
        tujuan.addWidget(
            self.btn_clear_penerima,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        grid.addWidget(QLabel("Penerima:"), 0, 0)
        grid.addWidget(self.txt_penerima, 0, 1)
        grid.addWidget(QLabel("No. HP:"), 0, 2)
        grid.addWidget(self.txt_hp_penerima, 0, 3)
        grid.addWidget(QLabel("Alamat:"), 1, 0)
        grid.addWidget(self.txt_alamat_penerima, 1, 1, 1, 3)
        grid.addWidget(QLabel("Tujuan:"), 2, 0)
        grid.addLayout(tujuan, 2, 1, 1, 3)

        cards.addWidget(self.group_pengirim, stretch=1)
        cards.addWidget(self.group_penerima, stretch=1)
        layout_kiri.addLayout(cards)

    def _bangun_detail_barang(self, layout_kiri):
        self.group_tabel_container = QGroupBox("")
        self.group_tabel_container.setMinimumHeight(RESI_DETAIL_CONTAINER_MIN_HEIGHT)
        layout = QVBoxLayout(self.group_tabel_container)
        layout.setContentsMargins(*RESI_TABLE_CONTAINER_MARGINS)
        layout.setSpacing(RESI_SPACING)

        self.table_items = QTableWidget()
        self.table_items.setColumnCount(5)
        self.table_items.setHorizontalHeaderLabels(
            ["NO.", "NAMA BARANG", "KOLI", "BERAT (Kg)", "KUBIK (m³)"]
        )
        # Tabel sendiri tidak perlu ikut menangkap fokus (mis. saat mouse
        # hover/lewat di atasnya). Fokus tetap berpindah normal ke QLineEdit
        # di dalam sel lewat klik langsung atau navigasi Tab.
        self.table_items.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = self.table_items.horizontalHeader()

        header.setHighlightSections(False)

        font_header = header.font()
        font_header.setBold(True)
        header.setFont(font_header)

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
        self.table_items.setMinimumHeight(RESI_ITEMS_TABLE_MIN_HEIGHT)
        self.table_items.verticalHeader().setVisible(False)
        layout.addWidget(self.table_items)

        actions = QHBoxLayout()
        actions.setSpacing(RESI_SPACING)
        self.btn_tambah_baris = QPushButton("＋Tambah Baris")
        self.btn_tambah_baris.clicked.connect(self.tambah_baris_barang)
        self.btn_hapus_baris = QPushButton("－Hapus Baris")
        self.btn_hapus_baris.clicked.connect(self.hapus_baris_terpilih)
        self.btn_clear_barang = self._buat_tombol_clear_container(
            self.group_tabel_container,
            "Reset detail barang",
            self.bersihkan_detail_barang,
        )

        actions.addWidget(self.btn_tambah_baris)
        actions.addWidget(self.btn_hapus_baris)
        actions.addStretch(1)
        actions.addWidget(
            self.btn_clear_barang,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addLayout(actions)
        layout_kiri.addWidget(self.group_tabel_container)

    def _bangun_area_pembayaran(self, layout_kiri, styles_awal):
        area = QHBoxLayout()
        area.setSpacing(RESI_SPACING)
        self._bangun_form_finance(area)

        self.layout_pay_method = QHBoxLayout()
        self.layout_pay_method.setContentsMargins(0, 0, 0, 0)
        self.layout_pay_method.setSpacing(RESI_SPACING)
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
        area.addLayout(self.layout_pay_method, stretch=RESI_PAYMENT_AREA_STRETCH[1])
        layout_kiri.addLayout(area)

    def _bangun_form_finance(self, area):
        self.group_finance = QGroupBox("")
        grid = QGridLayout(self.group_finance)
        grid.setSpacing(RESI_SPACING)
        grid.setContentsMargins(*RESI_FORM_CONTAINER_MARGINS)

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
        self.btn_clear_finance = self._buat_tombol_clear_container(
            self.group_finance,
            "Reset detail ongkir",
            self.bersihkan_detail_pembayaran,
        )

        for widget in (self.txt_ongkir_kg, self.txt_ongkir_m3):
            widget.textChanged.connect(self.kalkulator_finansial_otomatis)
            widget.textChanged.connect(
                lambda _text=None, w=widget: format_input_ribuan_gaya_indonesia(w)
            )
        self.txt_total_ongkir.textChanged.connect(
            lambda _text=None: format_input_ribuan_gaya_indonesia(self.txt_total_ongkir)
        )

        fields = (
            ("Ongkir per kg (Rp):", self.txt_ongkir_kg),
            ("Ongkir per m³ (Rp):", self.txt_ongkir_m3),
            ("Total Ongkir (Rp):", self.txt_total_ongkir),
            ("Jenis Transaksi:", self.cb_pajak),
            ("Metode Payment:", self.cb_payment),
        )
        for row, (label, widget) in enumerate(fields):
            grid.addWidget(QLabel(label), row, 0)
            if widget in (self.cb_pajak, self.cb_payment):
                grid.addWidget(widget, row, 1)
            else:
                # Field numerik tetap memakai lebar penuh seperti desain lama.
                grid.addWidget(widget, row, 1, 1, 2)

        # Kolom kanan hanya dipakai untuk ruang napas + reset pada baris terakhir.
        grid.setColumnStretch(1, RESI_FINANCE_COLUMN_STRETCH[0])
        grid.setColumnStretch(2, RESI_FINANCE_COLUMN_STRETCH[1])
        grid.addWidget(
            self.btn_clear_finance,
            4,
            2,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        grid.setRowStretch(5, 1)
        area.addWidget(self.group_finance, stretch=RESI_PAYMENT_AREA_STRETCH[0])

    def _buat_panel_rekening(self, judul, setting_key, style_card):
        box = QGroupBox(judul)
        outer = QVBoxLayout(box)
        outer.setContentsMargins(*RESI_ACCOUNT_PANEL_MARGINS)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(*RESI_ACCOUNT_CONTENT_MARGINS)
        layout.setSpacing(RESI_SPACING)
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
        right.setContentsMargins(RESI_ACTION_RIGHT_LEFT_MARGIN, 0, 0, 0)
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
        layout_kiri.addSpacing(RESI_ACTION_TOP_GAP)
        layout_kiri.addLayout(actions)
        layout_kiri.addStretch(1)

    def _bangun_histori(self):
        self.widget_kanan = QWidget()
        self.widget_kanan.setMinimumWidth(RESI_HISTORY_MIN_WIDTH)
        self.widget_kanan.setMaximumWidth(RESI_HISTORY_MAX_WIDTH)
        layout = QVBoxLayout(self.widget_kanan)
        layout.setContentsMargins(*RESI_HISTORY_MARGINS)
        layout.setSpacing(RESI_SPACING)

        self.txt_search = self._lineedit(
            "Cari resi, pengirim, penerima...",
            pakai_tinggi_lokal=False,
        )
        self.txt_search.textChanged.connect(self.filter_data_resi)
        layout.addWidget(self.txt_search)

        header = QHBoxLayout()
        self.lbl_histori_title = QLabel("Histori Resi")
        self.date_histori = QDateEdit(self)
        self.date_histori.setCalendarPopup(True)
        self.date_histori.setDate(QDate.currentDate())
        self.date_histori.setFixedWidth(RESI_HISTORY_DATE_WIDTH)
        self.date_histori.setDisplayFormat("dd/MM/yyyy")
        self.date_histori.dateChanged.connect(self.load_data_resi)
        self.btn_reset_tgl = QPushButton("RESET")
        self.btn_reset_tgl.setFixedWidth(RESI_HISTORY_RESET_WIDTH)
        self.btn_reset_tgl.clicked.connect(self.reset_tanggal)
        header.addWidget(self.lbl_histori_title)
        header.addWidget(self.date_histori)
        header.addWidget(self.btn_reset_tgl)
        header.addStretch()

        # Tree histori mengikuti struktur visual Tab Manifest.
        # Parent = bulan, child = satu baris transaksi Resi.
        self.list_histori = QTreeWidget()
        self.list_histori.setColumnCount(2)
        self.list_histori.setHeaderHidden(True)
        self.list_histori.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents,
        )
        self.list_histori.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch,
        )
        self.list_histori.itemDoubleClicked.connect(self.munculkan_preview)
        self.list_histori.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_histori.customContextMenuRequested.connect(
            self._tampilkan_context_menu_histori
        )
        layout.addLayout(header)
        layout.addWidget(self.list_histori)

    def set_tanggal_resi(self, qdate):
        """Pure setter: Hanya update teks label dan variabel, tanpa side-effect."""
        self._tanggal_transaksi = qdate
        nama_hari = {
            1: "Senin", 2: "Selasa", 3: "Rabu", 4: "Kamis",
            5: "Jumat", 6: "Sabtu", 7: "Minggu"
        }
        teks = f"{nama_hari.get(qdate.dayOfWeek(), '')}, {qdate.toString('dd/MM/yyyy')}"
        self.date_input.setText(teks)

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

        self._keluar_mode_edit()
        self.set_tanggal_resi(QDate.currentDate())

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
        """Membuat tombol reset kecil yang ditempatkan oleh layout pemanggil."""
        tombol = QToolButton(parent)
        tombol.setText("⟳")
        tombol.setToolTip(tooltip)
        tombol.setFixedSize(RESI_CLEAR_BUTTON_SIZE, RESI_CLEAR_BUTTON_SIZE)
        # Glyph reset 16pt membutuhkan floor geometry agar tidak terpotong
        # ketika global responsive scale masuk mode compact (mis. 1366x768).
        tombol.setProperty("_ui_scaler_min_width", RESI_CLEAR_BUTTON_SIZE)
        tombol.setProperty("_ui_scaler_min_height", RESI_CLEAR_BUTTON_SIZE)
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

        if not hasattr(self, "_tombol_clear_list"):
            self._tombol_clear_list = []
        self._tombol_clear_list.append(tombol)
        return tombol

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
        """Bersihkan ongkir; jenis pajak resi lama tetap terkunci saat Edit."""
        indeks_pajak_edit = self.cb_pajak.currentIndex() if self._mode_edit else None
        self._reset_status_kalkulator_ongkir()
        reset_form_input_global(
            self.group_finance,
            indeks_combo_default=0,
            fokus_ke=self.txt_ongkir_kg,
        )
        if indeks_pajak_edit is not None and self.cb_pajak.count() > 0:
            with _blokir_signal_sementara(self.cb_pajak):
                self.cb_pajak.setCurrentIndex(
                    max(0, min(indeks_pajak_edit, self.cb_pajak.count() - 1))
                )
        self.kalkulator_finansial_otomatis()
        self.otomatisasi_nomor_resi()

    def showEvent(self, event):
        super().showEvent(event)
        self.kode_cabang = self._kode_cabang_aktif()
        self.load_data_resi()

    def _terapkan_tema_detail_barang(
        self,
        is_dark: bool,
        sz_base: int,
    ) -> None:
        """Terapkan style lokal Detail Barang tanpa mengubah perilaku widget."""

        table = getattr(self, "table_items", None)
        if table is None:
            return

        theme = get_resi_detail_barang_theme(
            is_dark=is_dark,
            sz_base=sz_base,
        )

        # Override lokal ini mencegah style global pyqtdarktheme membuat
        # QLineEdit di dalam cell tampak aktif hanya karena pointer melintas.
        # State focus tetap muncul hanya saat widget benar-benar menerima focus.
        qss = get_table_styles(is_dark) + f"""
            QTableWidget {{
                background-color: {theme["background"]};
                alternate-background-color: {theme["alternate_background"]};
                color: {theme["text"]};
                gridline-color: {theme["grid"]};
            }}

            QTableWidget QLineEdit {{
                background-color: transparent;
                color: {theme["text"]};
                border: none;
                padding: 0px 4px;
            }}

            QTableWidget QLineEdit:hover {{
                background-color: transparent;
                border: none;
            }}

            QTableWidget QLineEdit:focus {{
                background-color: {theme["background"]};
                border: 1px solid {theme["selection_background"]};
            }}
        """
        table.setStyleSheet(konversi_font_qss_ke_point(qss))
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.setMouseTracking(False)
        table.viewport().setMouseTracking(False)

        font_table = table.font()
        font_table.setPointSizeF(ukuran_font_px_ke_pt(sz_base))
        table.setFont(font_table)

        for row in range(table.rowCount()):
            for column in self.KOLOM_INPUT_BARANG:
                editor = table.cellWidget(row, column)
                if editor is not None:
                    atur_tinggi_input(
                        editor,
                        tinggi=self._tinggi_input_detail_barang(),
                    )

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()
        self.current_theme = "dark" if is_dark else "light"
        fs, styles = self._buat_resi_styles(is_dark)

        self._pasang_stylesheet_nama(
            (
                "lbl_main_title", "lbl_tgl_tag", "lbl_edit_mode", "lbl_resi_tag", "txt_resi_display",
                "date_input", "txt_search", "lbl_histori_title", "btn_reset_tgl",
                "list_histori", "btn_generate_simpan", "lbl_reset_form", "scroll_kiri",
                "group_pengirim", "group_penerima", "group_tabel_container",
                "group_finance", "btn_tambah_baris", "btn_hapus_baris",
                "box_np", "box_p",
            ),
            styles,
        )
        self._terapkan_tema_histori_statis(fs)
        self._terapkan_style_histori_seperti_manifest(is_dark)
        self._terapkan_tema_input(styles)
        self._terapkan_tema_detail_barang(
            is_dark=is_dark,
            sz_base=UKURAN_FONT_INPUT,
        )
        self._pulihkan_ukuran_tabel_resi()
        self._terapkan_style_rekening(is_dark)
        self.date_input.update()
        self.date_histori.update()
        terapkan_style_kalender(self.date_histori, is_dark=is_dark)
        self._perbarui_style_tombol_clear(is_dark)

    def _tema_gelap_aktif(self):
        win = self.window()
        if win and hasattr(win, "current_theme"):
            return win.current_theme == "dark"
        return self.settings.value("theme", "light") == "dark"

    @staticmethod
    def _buat_resi_styles(is_dark):
        fs = get_global_font_sizes(0)
        styles = get_resi_styles(
            is_dark,
            z=0,
        )
        return fs, konversi_style_font_ke_point(styles)

    def _pasang_stylesheet_nama(self, nama_widgets, styles):
        for nama in nama_widgets:
            widget = getattr(self, nama, None)
            qss = styles.get(nama)
            if widget is not None and qss is not None:
                widget.setStyleSheet(qss)

    def _terapkan_tema_histori_statis(self, fs_statis):
        self.date_histori.setStyleSheet("")
        font = self.date_histori.font()
        font.setPointSizeF(ukuran_font_px_ke_pt(UKURAN_FONT_HISTORI_RESI))
        self.date_histori.setFont(font)
        atur_tinggi_input(
            (self.date_input, self.date_histori),
            tinggi=RESI_INPUT_HEIGHT,
        )
        atur_tinggi_input(self.txt_search)

    def _terapkan_tema_input(self, styles):
        for widget in (
            self.txt_pengirim, self.txt_hp_pengirim, self.txt_alamat_pengirim,
            self.txt_kota_pengirim, self.txt_penerima, self.txt_hp_penerima,
            self.txt_alamat_penerima, self.txt_kota_penerima,
            self.txt_ongkir_kg, self.txt_ongkir_m3,
        ):
            if widget is not None:
                widget.setStyleSheet(styles["input_utama"])

        comboboxes = (self.cb_provinsi, self.cb_pajak, self.cb_payment)

        if self.txt_total_ongkir is not None:
            self.txt_total_ongkir.setStyleSheet(styles["txt_total_ongkir"])

        atur_tinggi_input(
            (
                self.txt_pengirim,
                self.txt_hp_pengirim,
                self.txt_alamat_pengirim,
                self.txt_kota_pengirim,
                self.txt_penerima,
                self.txt_hp_penerima,
                self.txt_alamat_penerima,
                self.txt_kota_penerima,
                self.txt_ongkir_kg,
                self.txt_ongkir_m3,
                *comboboxes,
            ),
            tinggi=RESI_INPUT_HEIGHT,
        )
        atur_tinggi_input(
            self.txt_total_ongkir,
            tinggi=self._tinggi_input_total_ongkir(),
        )

    def _pulihkan_ukuran_tabel_resi(self):
        self.table_items.verticalHeader().setDefaultSectionSize(
            skalakan_px(RESI_TABLE_ROW_HEIGHT)
        )
        header = self.table_items.horizontalHeader()
        status_signal = header.blockSignals(True)
        try:
            saved_state = self.settings.value("ukuran_tabel_resi")
            current_scale = dapatkan_ui_scale()
            if saved_state:
                header.restoreState(saved_state)
                try:
                    saved_scale = float(
                        self.settings.value("ukuran_tabel_resi_scale", 1.0)
                    )
                except (TypeError, ValueError, OverflowError):
                    saved_scale = 1.0
                saved_scale = max(0.01, saved_scale)
                ratio = current_scale / saved_scale
                for kolom in range(self.table_items.columnCount()):
                    lebar = max(RESI_ITEMS_COLUMN_MIN_WIDTH, round(self.table_items.columnWidth(kolom) * ratio))
                    self.table_items.setColumnWidth(kolom, lebar)
            else:
                for kolom, lebar in self.LEBAR_KOLOM_DASAR.items():
                    self.table_items.setColumnWidth(
                        kolom,
                        skalakan_px(lebar),
                    )
        except Exception:
            logger.exception("Gagal memulihkan ukuran kolom tabel resi")
        finally:
            header.blockSignals(status_signal)

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
            l_card.setContentsMargins(*RESI_ACCOUNT_CARD_MARGINS)
            l_card.setSpacing(RESI_ACCOUNT_CARD_SPACING)

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

    def _terapkan_style_rekening(self, is_dark):
        rekening_styles = konversi_style_font_ke_point(
            get_resi_rekening_styles(is_dark, 0)
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
        for widget in (
            self.txt_pengirim,
            self.txt_alamat_pengirim,
            self.txt_kota_pengirim,
            self.txt_penerima,
            self.txt_alamat_penerima,
            self.txt_kota_penerima,
            self.txt_search,
        ):
            widget.setValidator(self.upper_validator)

    def _pastikan_autocomplete(self):
        """Buat model dan completer Resi satu kali agar lifetime object Qt stabil."""
        if hasattr(self, "model_autocomplete_pengirim"):
            return

        self.model_autocomplete_pengirim = QStringListModel(self)
        self.model_autocomplete_penerima = QStringListModel(self)

        self.comp_pengirim = self._buat_completer(
            self.model_autocomplete_pengirim,
            self.txt_pengirim,
            self.pilih_autocomplete_pengirim,
        )
        self.comp_penerima = self._buat_completer(
            self.model_autocomplete_penerima,
            self.txt_penerima,
            self.pilih_autocomplete_penerima,
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

            self._pastikan_autocomplete()
            self.model_autocomplete_pengirim.setStringList(pengirim)
            self.model_autocomplete_penerima.setStringList(penerima)

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
    def _buat_completer(model, lineedit, callback):
        completer = QCompleter(model, lineedit)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(RESI_AUTOCOMPLETE_MAX_VISIBLE_ITEMS)
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

    def _pilih_autocomplete(self, nilai, lineedit, callback):
        nilai = str(nilai or "").strip().upper()
        if not nilai:
            return
        lineedit.setText(nilai)
        QTimer.singleShot(0, lambda: callback(nilai))

    def pilih_autocomplete_pengirim(self, nama_pengirim):
        self._pilih_autocomplete(
            nama_pengirim, self.txt_pengirim, self.eksekusi_autofill_pengirim
        )

    def pilih_autocomplete_penerima(self, nama_penerima):
        self._pilih_autocomplete(
            nama_penerima, self.txt_penerima, self.eksekusi_autofill_penerima
        )

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

    def _ukuran_point_histori_aktif(self):
        """Mengikuti perhitungan ukuran font Histori Manifest."""
        font_histori = self.list_histori.font()
        ukuran_point = font_histori.pointSizeF()
        if ukuran_point > 0:
            return ukuran_point

        ukuran_pixel = font_histori.pixelSize()
        if ukuran_pixel <= 0:
            return ukuran_font_px_ke_pt(get_global_font_sizes(0)["sz_base"])

        dpi_y = max(1, self.list_histori.logicalDpiY())
        return max(1.0, ukuran_pixel * 72.0 / dpi_y)

    def _sinkronkan_font_item_histori_resi(self, is_dark):
        """Samakan tampilan kolom tanggal dengan child pada Histori Manifest."""
        font_tanggal, warna_abu = get_manifest_history_date_appearance(
            is_dark,
            self._ukuran_point_histori_aktif(),
        )
        for parent_index in range(self.list_histori.topLevelItemCount()):
            parent = self.list_histori.topLevelItem(parent_index)
            if parent is None:
                continue
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                child.setFont(0, font_tanggal)
                child.setForeground(0, QBrush(warna_abu))

    def _terapkan_style_histori_seperti_manifest(self, is_dark):
        """Sumber QSS histori langsung dari theme Manifest agar selalu konsisten."""
        style_manifest = konversi_style_font_ke_point(
            get_manifest_styles(is_dark, False, 0)
        )
        self.list_histori.setStyleSheet(style_manifest["list_histori"])
        font_histori = self.list_histori.font()
        font_histori.setPointSizeF(
            ukuran_font_px_ke_pt(get_global_font_sizes(0)["sz_base"])
        )
        self.list_histori.setFont(font_histori)
        self._sinkronkan_font_item_histori_resi(is_dark)

    @staticmethod
    def _tanggal_histori_dari_row(row):
        """Pakai tanggal dari hasil query hanya jika memang tersedia."""
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            return ""
        kandidat = str(row[2] or "").strip()
        if not kandidat or ("/" not in kandidat and "-" not in kandidat):
            return ""
        return format_tanggal_ke_ui(kandidat)

    def _isi_tree_histori(
        self,
        rows,
        tanggal_default=None,
        parent_default="Hasil Pencarian",
    ):
        parents = {}
        is_dark = self._tema_gelap_aktif()
        font_tanggal, warna_abu = get_manifest_history_date_appearance(
            is_dark,
            self._ukuran_point_histori_aktif(),
        )

        tanggal_default_ui = (
            tanggal_default.toString("dd/MM/yyyy")
            if isinstance(tanggal_default, QDate)
            else ""
        )

        for raw_row in rows or []:
            row = tuple(raw_row or ())
            no_resi = str(row[0] or "").strip() if len(row) > 0 else ""
            detail = str(row[1] or "").strip() if len(row) > 1 else ""
            if not no_resi:
                continue

            tanggal_ui = self._tanggal_histori_dari_row(row) or tanggal_default_ui
            bulan_nama = ""
            if tanggal_ui:
                bagian = tanggal_ui.replace("-", "/").split("/")
                if len(bagian) >= 2:
                    try:
                        bulan_nama = self.NAMA_BULAN.get(int(bagian[1]), "")
                    except (TypeError, ValueError):
                        bulan_nama = ""

            parent_title = (
                f"{bulan_nama}"
                if bulan_nama
                else f"{parent_default}"
            )
            parent = parents.get(parent_title)
            if parent is None:
                parent = QTreeWidgetItem(self.list_histori)
                parent.setText(0, parent_title)
                parents[parent_title] = parent

            child = QTreeWidgetItem(parent)
            child.setText(0, tanggal_ui)
            child.setFont(0, font_tanggal)
            child.setForeground(0, QBrush(warna_abu))
            child.setText(1, f"{no_resi} | {detail}" if detail else no_resi)
            child.setData(0, Qt.ItemDataRole.UserRole, no_resi)

        self.list_histori.expandAll()

    def filter_data_resi(self):
        keyword = self.txt_search.text().strip().lower()
        if not keyword:
            self.load_data_resi()
            return

        self.list_histori.setUpdatesEnabled(False)
        self.list_histori.clear()
        kode_cabang = self._kode_cabang_aktif()
        try:
            rows = db_service.cari_histori_resi(keyword, kode_cabang) or []
            self._isi_tree_histori(
                rows,
                parent_default="Hasil Pencarian",
            )
        except Exception:
            logger.exception("Gagal memuat pencarian histori resi")
        finally:
            self.list_histori.setUpdatesEnabled(True)
            self.list_histori.viewport().update()

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
            # Gunakan Decimal selama perhitungan agar berat/CBM x tarif tidak
            # melewati floating-point sebelum pembulatan total rupiah.
            total_berat_kargo = Decimal("0")
            total_volume_kargo = Decimal("0")

            for row in range(self.table_items.rowCount()):
                w_b = self.table_items.cellWidget(row, self.KOL_BERAT)
                w_v = self.table_items.cellWidget(row, self.KOL_CBM)

                if w_b and w_b.text().strip() not in {"", "-"}:
                    total_berat_kargo += angka_indonesia_to_decimal(w_b.text())

                if w_v and w_v.text().strip() not in {"", "-"}:
                    total_volume_kargo += angka_indonesia_to_decimal(w_v.text())

            kg_rate = Decimal(rupiah_to_int(self.txt_ongkir_kg.text()))
            m3_rate = Decimal(rupiah_to_int(self.txt_ongkir_m3.text()))

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
        widget.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

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

        atur_tinggi_input(
            widget,
            tinggi=self._tinggi_input_detail_barang(),
        )
        widget.installEventFilter(self)
        return widget

    def hapus_baris_terpilih(self):
        current_row = self.table_items.currentRow()
        if current_row >= 0:
            self.table_items.removeRow(current_row)
        else:
            row_count = self.table_items.rowCount()
            if row_count > 0:
                self.table_items.removeRow(row_count - 1)

        for row in range(self.table_items.rowCount()):
            self.table_items.item(row, self.KOL_NO).setText(str(row + 1))
        self.kalkulator_finansial_otomatis()

    def auto_save_ukuran_kolom(self, logicalIndex, oldSize, newSize):
        state_sekarang = self.table_items.horizontalHeader().saveState()
        self.settings.setValue("ukuran_tabel_resi", state_sekarang)
        self.settings.setValue("ukuran_tabel_resi_scale", dapatkan_ui_scale())


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
        # Saat Edit, prefix/counter lama dipertahankan; hanya suffix pajak yang
        # mengikuti pilihan PAJAK/NONPAJAK.
        if self._mode_edit and self._resi_sedang_diedit:
            jenis_pajak = "PAJAK" if self._transaksi_kena_ppn() else "NONPAJAK"
            no_resi_edit = db_service.sesuaikan_nomor_resi_dengan_pajak(
                self._resi_sedang_diedit, jenis_pajak
            )
            self.txt_resi_display.setText(no_resi_edit or self._resi_sedang_diedit)
            return

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

    def _peringatkan_validasi(self, pesan, widget=None):
        """Tampilkan satu warning validasi dan arahkan fokus ke input terkait."""
        QMessageBox.warning(self, "Data Resi Belum Lengkap", pesan)
        if widget is not None:
            QTimer.singleShot(0, lambda w=widget: self._fokuskan_widget_input(w))
        return False

    def _validasi_form_sebelum_simpan(self):
        """Izinkan penyimpanan dengan kombinasi field apa pun.

        Nomor Resi dan tanggal transaksi tetap dikelola sistem. Seluruh input
        operasional lain bersifat opsional agar admin dapat menyimpan draft/
        data parsial tanpa dipaksa melengkapi field yang tidak tersedia saat itu.
        """
        return True

    def _cetak_setelah_database_tersimpan(self, ctx, *, perubahan=False):
        """Cetak setelah commit; kegagalan printer tidak mengubah status simpan DB."""
        no_resi = str(ctx.get("payload", {}).get("no_resi") or "").strip()
        try:
            cetak_resi_ke_printer(self._buat_data_cetak_dari_context(ctx), self)
            return True
        except Exception as exc:
            logger.exception("Resi %s tersimpan tetapi gagal membuka preview/cetak", no_resi)
            jenis = "Perubahan resi" if perubahan else "Resi"
            QMessageBox.warning(
                self,
                "Tersimpan - Cetak Gagal",
                f"{jenis} {no_resi or ''} sudah berhasil disimpan ke database, "
                "tetapi preview/cetak gagal dibuka.\n\n"
                f"Detail: {exc}\n\n"
                "Data tidak perlu disimpan ulang. Gunakan Histori Resi untuk mencetak kembali.",
            )
            return False

    def simpan_ke_database(self):
        if not self._validasi_form_sebelum_simpan():
            return

        if self._mode_edit and self._resi_sedang_diedit:
            self._simpan_perubahan_resi()
            return

        # Resi baru selalu memakai tanggal hari ini. Sumber tanggal yang sama
        # diteruskan ke database dan data cetak agar keduanya tidak berbeda.
        tanggal_transaksi = QDate.currentDate()
        self.set_tanggal_resi(tanggal_transaksi)

        self.otomatisasi_nomor_resi()
        ctx = self._siapkan_transaksi_form(
            self.txt_resi_display.text(),
            format_tanggal_ke_db(tanggal_transaksi),
        )
        try:
            sukses, pesan_error = db_service.simpan_transaksi_resi(ctx["payload"])
        except Exception as exc:
            logger.exception("Gagal menyimpan resi %s", self.txt_resi_display.text())
            QMessageBox.critical(self, "Error Database", f"Gagal menyimpan resi: {exc}")
            return

        if not sukses:
            self._tampilkan_error_simpan(pesan_error)
            return

        self._cetak_setelah_database_tersimpan(ctx)
        self._selesaikan_simpan_sukses()

    def _ambil_ringkasan_barang(self):
        """Ambil semua baris detail yang benar-benar diisi, termasuk parsial.

        Nama barang tidak lagi menjadi syarat. Baris seperti hanya KOLI, hanya
        BERAT, hanya KUBIK, atau kombinasi apa pun tetap masuk ke rincian. Baris
        default yang seluruh isinya kosong/"-" tetap diabaikan.
        """
        nama_barang = []
        rincian = []
        total_koli, total_berat, total_cbm = 0, 0.0, 0.0

        for row in range(self.table_items.rowCount()):
            widgets = [
                self.table_items.cellWidget(row, kolom)
                for kolom in self.KOLOM_INPUT_BARANG
            ]
            w_nama, w_qty, w_berat, w_cbm = widgets

            nama = w_nama.text().strip() if w_nama else ""
            qty_raw = w_qty.text().strip() if w_qty else ""
            berat_raw = w_berat.text().strip() if w_berat else ""
            cbm_raw = w_cbm.text().strip() if w_cbm else ""

            ada_input = bool(nama) or any(
                nilai not in {"", "-"}
                for nilai in (qty_raw, berat_raw, cbm_raw)
            )
            if not ada_input:
                continue

            koli = max(0, rupiah_to_int(qty_raw))
            berat = max(0.0, float(angka_indonesia_to_decimal(berat_raw or "0")))
            cbm = max(0.0, float(angka_indonesia_to_decimal(cbm_raw or "0")))

            total_koli += koli
            total_berat += berat
            total_cbm += cbm
            if nama:
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

    def _siapkan_transaksi_form(self, no_resi, tanggal):
        kode_cabang = self._kode_cabang_aktif()
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
        return {
            "payload": payload,
            "ringkasan": ringkasan,
            "kota_tujuan": kota_tujuan,
            "total_ongkir": total_ongkir,
            "ongkir_kg": ongkir_kg,
            "ongkir_m3": ongkir_m3,
        }

    def _buat_data_cetak_dari_context(self, ctx):
        data_cetak = self._buat_data_cetak(
            ctx["payload"]["no_resi"],
            ctx["kota_tujuan"],
            ctx["ringkasan"],
            ctx["total_ongkir"],
            ctx["ongkir_kg"],
            ctx["ongkir_m3"],
        )
        # Tanggal cetak mengikuti payload transaksi, bukan state widget yang
        # mungkin berubah setelah masuk/keluar mode Edit.
        data_cetak["tanggal"] = format_tanggal_ke_ui(
            ctx["payload"].get("tanggal_masuk")
        )
        return data_cetak

    def _subtotal_ongkir_untuk_simpan(self, total_ongkir):
        """Ambil subtotal dasar yang aman untuk PAJAK/NONPAJAK."""
        if self._mode_total_ongkir == "manual":
            return max(0, int(self._subtotal_manual_ongkir or 0))

        total_ongkir = max(0, int(total_ongkir or 0))
        if total_ongkir <= 0:
            return 0
        if self._transaksi_kena_ppn():
            return int(
                (Decimal(str(total_ongkir)) / Decimal("1.011")).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
        return total_ongkir

    def _buat_konteks_atomic_resi(self):
        """Konteks opsional agar database menentukan counter final saat write-lock."""
        provinsi = self.cb_provinsi.currentText().strip().upper()
        aturan_prefix = CURRENT_SESSION.get("aturan_prefix", {})
        prefix_default = (
            str(CURRENT_SESSION.get("resi_prefix", "SYS")).strip().upper()
            or "SYS"
        )
        prefix = aturan_prefix.get(
            provinsi,
            aturan_prefix.get("DEFAULT", prefix_default),
        )
        template = db_service.get_setting("template_no_resi") or "[PREFIX][COUNTER][SUFFIX]"
        suffix_setting = db_service.get_setting("kode_akhiran_pajak") or "-P"
        suffix = suffix_setting if self._transaksi_kena_ppn() else ""
        return {
            "prefix": str(prefix or prefix_default).strip().upper(),
            "template": str(template or "[PREFIX][COUNTER][SUFFIX]"),
            "suffix": str(suffix or "").strip().upper(),
        }

    def _buat_payload_transaksi(
        self, no_resi, kode_cabang, tanggal, provinsi, kota_tujuan, tujuan,
        kota_asal, data, total_ongkir, ongkir_kg, ongkir_m3,
    ):
        return {
            "no_resi": no_resi,
            "kode_cabang": kode_cabang,
            "tanggal_masuk": tanggal,
            "_atomic_resi": self._buat_konteks_atomic_resi(),
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
            "subtotal_ongkir": self._subtotal_ongkir_untuk_simpan(total_ongkir),
            "jenis_pajak": "PAJAK" if self._transaksi_kena_ppn() else "NONPAJAK",
            "total_ongkir": total_ongkir,
            "pembayaran": self.cb_payment.currentText(),
            "rincian": data["rincian"],
            "rincian_json": json.dumps(data["rincian"]),
        }

    def _buat_data_cetak(
        self, no_resi, kota_tujuan, data, total_ongkir, ongkir_kg, ongkir_m3
    ):
        fmt_kg = _format_ongkir_aman(ongkir_kg)
        fmt_m3 = _format_ongkir_aman(ongkir_m3)
        return {
            "tanggal": format_tanggal_ke_ui(self._tanggal_transaksi),
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
        elif kode == getattr(db_service, "KODE_RESI_KONFLIK", None):
            QMessageBox.warning(self, "Data Resi Berubah", str(error))
        elif kode == db_service.KODE_DB_ERROR:
            QMessageBox.critical(self, "Error Database", str(error))
        else:
            QMessageBox.critical(self, "Error SQL", f"Gagal simpan: {error}")

    def _tampilkan_context_menu_histori(self, pos):
        """Tampilkan aksi histori hanya ketika klik kanan tepat pada item."""
        item = self.list_histori.itemAt(pos)
        if item is None or item.parent() is None:
            return

        self.list_histori.setCurrentItem(item)
        menu = QMenu(self.list_histori)
        aksi_view = menu.addAction("View")
        aksi_edit = menu.addAction("Edit")
        menu.addSeparator()
        aksi_audit = menu.addAction("Riwayat Perubahan")
        aksi = menu.exec(self.list_histori.viewport().mapToGlobal(pos))

        if aksi is aksi_view:
            self.munculkan_preview(item)
        elif aksi is aksi_edit:
            self.mulai_edit_resi(item)
        elif aksi is aksi_audit:
            self.tampilkan_riwayat_perubahan(item)

    @staticmethod
    def _label_field_audit(field):
        label = {
            "tanggal_masuk": "Tanggal Masuk",
            "tanggal_keluar": "Tanggal Keluar",
            "status_resi": "Status Resi",
            "truk": "Truk",
            "pengirim": "Pengirim",
            "hp_pengirim": "HP Pengirim",
            "alamat_pengirim": "Alamat Pengirim",
            "kota_asal": "Kota Asal",
            "penerima": "Penerima",
            "hp_penerima": "HP Penerima",
            "alamat_penerima": "Alamat Penerima",
            "kota_tujuan": "Kota Tujuan",
            "ongkir_per_kg": "Ongkir / Kg",
            "ongkir_per_cbm": "Ongkir / CBM",
            "subtotal_ongkir": "Subtotal Ongkir",
            "jenis_pajak": "Jenis Pajak",
            "total_ongkir": "Total Ongkir",
            "pembayaran": "Pembayaran",
            "ket_buku_gudang": "Keterangan Buku Gudang",
            "no_manifest": "No. Manifest",
            "ket_manifest": "Keterangan Manifest",
        }
        return label.get(str(field), str(field).replace("_", " ").title())

    @staticmethod
    def _format_nilai_audit(field, nilai):
        if nilai is None or str(nilai).strip() == "":
            return "(kosong)"
        if field in {"ongkir_per_kg", "ongkir_per_cbm", "subtotal_ongkir", "total_ongkir"}:
            try:
                angka = int(float(nilai))
                return f"Rp {format_ke_rupiah(angka)}"
            except (TypeError, ValueError):
                pass
        return str(nilai)

    @classmethod
    def _format_barang_audit(cls, daftar):
        if not daftar:
            return "(kosong)"
        hasil = []
        for index, item in enumerate(daftar, start=1):
            if not isinstance(item, dict):
                hasil.append(f"{index}. {item}")
                continue
            urutan = item.get("urutan") or index
            nama = str(item.get("nama_barang") or "").strip() or "(tanpa nama)"
            koli = item.get("koli")
            berat = item.get("berat")
            cbm = item.get("cbm")
            hasil.append(
                f"{urutan}. {nama} | Koli: {koli or 0} | Berat: {berat or 0} | CBM: {cbm or 0}"
            )
        return "\n".join(hasil)

    @classmethod
    def _ringkasan_perubahan_audit(cls, no_resi_lama, no_resi_baru, perubahan_json):
        baris = []
        if str(no_resi_lama or "").strip() != str(no_resi_baru or "").strip():
            baris.append(f"No. Resi: {no_resi_lama} → {no_resi_baru}")

        try:
            perubahan = json.loads(perubahan_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            perubahan = {}

        header = perubahan.get("header", {}) if isinstance(perubahan, dict) else {}
        if isinstance(header, dict):
            for field, detail in header.items():
                if not isinstance(detail, dict):
                    continue
                sebelum = cls._format_nilai_audit(field, detail.get("sebelum"))
                sesudah = cls._format_nilai_audit(field, detail.get("sesudah"))
                baris.append(f"{cls._label_field_audit(field)}: {sebelum} → {sesudah}")

        barang = perubahan.get("barang") if isinstance(perubahan, dict) else None
        if isinstance(barang, dict):
            sebelum = cls._format_barang_audit(barang.get("sebelum", []))
            sesudah = cls._format_barang_audit(barang.get("sesudah", []))
            baris.append(f"Detail Barang - Sebelum:\n{sebelum}")
            baris.append(f"Detail Barang - Sesudah:\n{sesudah}")

        return "\n".join(baris) if baris else "Tidak ada rincian perubahan."

    @staticmethod
    def _format_waktu_audit(nilai):
        teks = str(nilai or "").strip()
        if not teks:
            return "-"
        try:
            tanggal, waktu = teks.split(" ", 1)
            tahun, bulan, hari = tanggal.split("-", 2)
            return f"{hari}-{bulan}-{tahun} {waktu}"
        except ValueError:
            return teks

    def _buat_card_audit(self, parent, row):
        if len(row) < 9:
            return None

        _, no_lama, no_baru, username, sumber, rev_lama, rev_baru, perubahan_json, created_at = row
        card = QFrame(parent)
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)

        sumber_tampil = str(sumber or "SYSTEM").replace("_", " ")
        info = QLabel(
            f"{self._format_waktu_audit(created_at)}  |  "
            f"{username or 'SYSTEM'}  |  {sumber_tampil}"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        rincian = QLabel(
            self._ringkasan_perubahan_audit(no_lama, no_baru, perubahan_json)
        )
        rincian.setWordWrap(True)
        rincian.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(rincian)

        if rev_lama is not None or rev_baru is not None:
            revision = QLabel(
                f"Revision: {rev_lama if rev_lama is not None else '-'} → "
                f"{rev_baru if rev_baru is not None else '-'}"
            )
            revision.setWordWrap(True)
            layout.addWidget(revision)
        return card

    def tampilkan_riwayat_perubahan(self, item):
        """Tampilkan audit Resi dari context menu histori tanpa mengubah data."""
        no_resi = self._ambil_no_resi_dari_item(item)
        if not no_resi:
            return

        try:
            histori = db_service.ambil_audit_resi(
                no_resi, self._kode_cabang_aktif(), limit=200
            )
        except Exception as error:
            logger.exception("Gagal mengambil audit Resi %s", no_resi)
            QMessageBox.critical(
                self, "Riwayat Perubahan", f"Gagal memuat riwayat perubahan: {error}"
            )
            return

        if not histori:
            QMessageBox.information(
                self,
                "Riwayat Perubahan",
                f"Belum ada riwayat perubahan untuk Resi {no_resi}.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Riwayat Perubahan - {no_resi}")
        dialog.setModal(True)
        dialog.resize(*RESI_AUDIT_DIALOG_SIZE)
        layout_dialog = QVBoxLayout(dialog)

        judul = QLabel(f"Riwayat Perubahan Resi {no_resi}")
        judul.setWordWrap(True)
        layout_dialog.addWidget(judul)

        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        isi_scroll = QWidget()
        layout_histori = QVBoxLayout(isi_scroll)
        layout_histori.setContentsMargins(0, 0, 0, 0)
        layout_histori.setSpacing(RESI_AUDIT_HISTORY_SPACING)
        for row in histori:
            card = self._buat_card_audit(isi_scroll, row)
            if card is not None:
                layout_histori.addWidget(card)

        layout_histori.addStretch(1)
        scroll.setWidget(isi_scroll)
        layout_dialog.addWidget(scroll, 1)

        tombol_tutup = QPushButton("Tutup", dialog)
        tombol_tutup.clicked.connect(dialog.accept)
        layout_tombol = QHBoxLayout()
        layout_tombol.addStretch(1)
        layout_tombol.addWidget(tombol_tutup)
        layout_dialog.addLayout(layout_tombol)
        dialog.exec()

    @staticmethod
    def _ambil_no_resi_dari_item(item):
        if item is None:
            return ""

        try:
            no_resi = str(
                item.data(0, Qt.ItemDataRole.UserRole) or ""
            ).strip()
            if no_resi:
                return no_resi
            if item.parent() is None:
                return ""
            return str(item.text(1) or "").split(" | ", 1)[0].strip()
        except (AttributeError, TypeError):
            try:
                return str(item.text() or "").split(" - ", 1)[0].strip()
            except (AttributeError, TypeError):
                return ""

    def _set_mode_edit(self, no_resi):
        no_resi = str(no_resi or "").strip()
        self._mode_edit = bool(no_resi)
        self._resi_sedang_diedit = no_resi or None
        self.lbl_edit_mode.setVisible(self._mode_edit)
        # Nomor resi tetap immutable, tetapi status PAJAK/NONPAJAK disimpan
        # sebagai data transaksi terpisah dan aman untuk diedit.
        if hasattr(self, "cb_pajak"):
            self.cb_pajak.setEnabled(True)
        if self._mode_edit:
            self.txt_resi_display.setText(no_resi)

    def _keluar_mode_edit(self):
        self._mode_edit = False
        self._resi_sedang_diedit = None
        self._revision_sedang_diedit = None
        self.current_resi_data = None
        if hasattr(self, "cb_pajak"):
            self.cb_pajak.setEnabled(True)
        if hasattr(self, "lbl_edit_mode"):
            self.lbl_edit_mode.hide()

    @staticmethod
    def _qdate_dari_nilai_db(nilai):
        if isinstance(nilai, QDate):
            return nilai

        # Mendukung datetime/date Python tanpa menambah dependency baru.
        if hasattr(nilai, "year") and hasattr(nilai, "month") and hasattr(nilai, "day"):
            try:
                return QDate(int(nilai.year), int(nilai.month), int(nilai.day))
            except (TypeError, ValueError):
                pass

        teks = str(nilai or "").strip()
        for fmt in ("yyyy-MM-dd", "dd/MM/yyyy", "yyyy-MM-dd HH:mm:ss"):
            qdate = QDate.fromString(teks, fmt)
            if qdate.isValid():
                return qdate
        return QDate.currentDate()

    def _pecah_tujuan_resi(self, tujuan):
        """Pisahkan string tujuan DB menjadi provinsi dan kota menggunakan isi combo."""
        teks = str(tujuan or "").strip().upper()
        if not teks:
            return "", ""

        daftar_provinsi = sorted(
            (self.cb_provinsi.itemText(i).strip().upper() for i in range(self.cb_provinsi.count())),
            key=len,
            reverse=True,
        )
        for provinsi in daftar_provinsi:
            if teks == provinsi:
                return provinsi, ""
            awalan = f"{provinsi} - "
            if teks.startswith(awalan):
                return provinsi, teks[len(awalan):].strip()

        if " - " in teks:
            provinsi, kota = teks.split(" - ", 1)
            return provinsi.strip(), kota.strip()
        return teks, ""

    def _pilih_combo_berdasarkan_teks(self, combo, teks):
        nilai = str(teks or "").strip()
        if not nilai:
            return
        indeks = combo.findText(nilai, Qt.MatchFlag.MatchFixedString)
        if indeks < 0:
            indeks = combo.findText(nilai, Qt.MatchFlag.MatchFixedString | Qt.MatchFlag.MatchCaseSensitive)
        if indeks < 0:
            combo.addItem(nilai)
            indeks = combo.count() - 1
        combo.setCurrentIndex(indeks)

    def _isi_tabel_barang_dari_resi(self, rincian):
        with _blokir_signal_sementara(self.table_items):
            self.table_items.setRowCount(0)

        rincian_valid = rincian if isinstance(rincian, list) else []
        if not rincian_valid:
            rincian_valid = [{"nama": "", "qty": "", "berat": "", "cbm": ""}]

        for data in rincian_valid:
            self.tambah_baris_barang()
            row = self.table_items.rowCount() - 1
            nilai_per_kolom = {
                self.KOL_NAMA_BARANG: data.get("nama", ""),
                self.KOL_KOLI: data.get("qty", data.get("koli", "")),
                self.KOL_BERAT: data.get("berat", ""),
                self.KOL_CBM: data.get("cbm", ""),
            }
            for kolom, nilai in nilai_per_kolom.items():
                editor = self.table_items.cellWidget(row, kolom)
                if editor is not None:
                    with _blokir_signal_sementara(editor):
                        editor.setText(str(nilai or ""))

    def _rincian_dari_row_resi(self, row, toleran_json=False, fallback_kosong=True):
        raw = row[14] if len(row) > 14 else None
        try:
            rincian = json.loads(raw) if raw else []
        except (TypeError, ValueError, json.JSONDecodeError):
            if not toleran_json:
                raise
            rincian = []
        if rincian or (raw and not fallback_kosong):
            return rincian
        return [{
            "nama": str(row[8] or ""),
            "qty": str(row[10] or ""),
            "berat": str(row[9] or ""),
            "cbm": str(row[11] or ""),
        }]

    def _isi_identitas_edit_dari_row(self, row):
        self.set_tanggal_resi(
            self._qdate_dari_nilai_db(row[0])
        )

        self.txt_pengirim.setText(str(row[1] or ""))
        self.txt_hp_pengirim.setText(str(row[2] or ""))
        self.txt_alamat_pengirim.setText(str(row[3] or ""))
        self.txt_kota_pengirim.setText(str(row[17] or "") if len(row) > 17 else "")
        self.txt_penerima.setText(str(row[4] or ""))
        self.txt_hp_penerima.setText(str(row[5] or ""))
        self.txt_alamat_penerima.setText(str(row[6] or ""))

        provinsi, kota = self._pecah_tujuan_resi(row[7])
        if provinsi:
            self._pilih_combo_berdasarkan_teks(self.cb_provinsi, provinsi)
        self.txt_kota_penerima.setText(kota)

        jenis_pajak = str(row[18] or "NONPAJAK").strip().upper() if len(row) > 18 else "NONPAJAK"
        is_pajak = jenis_pajak.startswith("PAJAK")
        with _blokir_signal_sementara(self.cb_pajak):
            self.cb_pajak.setCurrentIndex(1 if is_pajak and self.cb_pajak.count() > 1 else 0)
        if len(row) > 13 and row[13] is not None:
            self._pilih_combo_berdasarkan_teks(self.cb_payment, str(row[13]))
        return is_pajak

    def _isi_ongkir_edit_dari_row(self, row, is_pajak):
        ongkir_kg = str(row[15] or "") if len(row) > 15 else ""
        ongkir_m3 = str(row[16] or "") if len(row) > 16 else ""
        total_ongkir = int(row[12] or 0) if len(row) > 12 else 0

        self._reset_status_kalkulator_ongkir()
        self.txt_ongkir_kg.setText(_format_ongkir_aman(ongkir_kg))
        self.txt_ongkir_m3.setText(_format_ongkir_aman(ongkir_m3))
        self._set_total_ongkir_programatis(total_ongkir)

        subtotal_db = int(row[19] or 0) if len(row) > 19 else 0
        kg_rate = Decimal(rupiah_to_int(ongkir_kg))
        m3_rate = Decimal(rupiah_to_int(ongkir_m3))
        berat_db = angka_indonesia_to_decimal(row[9] if len(row) > 9 else 0)
        cbm_db = angka_indonesia_to_decimal(row[11] if len(row) > 11 else 0)

        subtotal_auto = None
        if kg_rate > 0 and berat_db > 0:
            subtotal_auto = berat_db * kg_rate
        elif m3_rate > 0 and cbm_db > 0:
            subtotal_auto = cbm_db * m3_rate

        total_auto = self._total_setelah_ppn(subtotal_auto) if subtotal_auto is not None else None
        if total_auto is not None and total_auto == total_ongkir:
            self._mode_total_ongkir = "auto"
        elif total_ongkir > 0:
            self._mode_total_ongkir = "manual"
            if subtotal_db > 0:
                self._subtotal_manual_ongkir = subtotal_db
            else:
                pembagi = Decimal("1.011") if is_pajak else Decimal("1")
                self._subtotal_manual_ongkir = int(
                    (Decimal(str(total_ongkir)) / pembagi).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )

    def mulai_edit_resi(self, item):
        """Muat resi histori ke form kiri dan aktifkan mode edit."""
        no_resi = self._ambil_no_resi_dari_item(item)
        if not no_resi:
            return

        try:
            row = db_service.ambil_detail_resi(no_resi)
            if not row:
                QMessageBox.warning(self, "Edit Resi", "Data resi tidak ditemukan.")
                return

            self.current_resi_data = row
            self._set_mode_edit(no_resi)
            self._revision_sedang_diedit = int(row[20] or 0) if len(row) > 20 else 0

            is_pajak = self._isi_identitas_edit_dari_row(row)
            self._isi_tabel_barang_dari_resi(
                self._rincian_dari_row_resi(row, toleran_json=True)
            )
            self._isi_ongkir_edit_dari_row(row, is_pajak)

            self.txt_resi_display.setText(no_resi)
            self.scroll_kiri.verticalScrollBar().setValue(0)
            QTimer.singleShot(0, self.txt_pengirim.setFocus)
        except Exception as exc:
            logger.exception("Gagal memuat resi %s ke mode edit", no_resi)
            self._keluar_mode_edit()
            QMessageBox.critical(self, "Edit Resi", f"Gagal memuat data resi: {exc}")

    def _konfirmasi_edit_resi_terinvoice(self, no_resi, payload):
        """Minta konfirmasi jika Resi sudah menjadi snapshot pada Invoice."""
        try:
            proteksi = db_service.cek_proteksi_invoice_resi(
                no_resi, payload, self._kode_cabang_aktif()
            )
        except Exception as exc:
            logger.exception("Gagal memeriksa Invoice terkait Resi %s", no_resi)
            QMessageBox.critical(
                self,
                "Status Invoice Tidak Dapat Diverifikasi",
                "Perubahan resi dibatalkan karena sistem gagal memeriksa keterkaitan "
                f"Invoice untuk resi {no_resi}.\n\nDetail: {exc}",
            )
            return False

        if not isinstance(proteksi, dict) or "terkait" not in proteksi:
            logger.error("Respons proteksi Invoice tidak valid untuk Resi %s: %r", no_resi, proteksi)
            QMessageBox.critical(
                self,
                "Status Invoice Tidak Dapat Diverifikasi",
                f"Perubahan resi {no_resi} dibatalkan karena hasil pemeriksaan Invoice tidak valid.",
            )
            return False

        if not proteksi.get("terkait"):
            return True

        daftar = []
        for info in proteksi.get("invoices", []):
            nomor = str(info.get("no_invoice") or "").strip()
            status = str(info.get("status") or "").strip()
            daftar.append(f"{nomor} ({status})" if status else nomor)
        teks_invoice = ", ".join(item for item in daftar if item) or "Invoice terkait"

        if proteksi.get("perubahan_finansial"):
            pesan = (
                f"Resi {no_resi} sudah digunakan pada Invoice:\n{teks_invoice}\n\n"
                "Anda mengubah data finansial (ongkir, PAJAK/NONPAJAK, subtotal, "
                "atau payment). Perubahan Resi TIDAK otomatis memperbarui Invoice "
                "yang sudah dibuat.\n\nTetap simpan perubahan Resi?"
            )
        else:
            pesan = (
                f"Resi {no_resi} sudah digunakan pada Invoice:\n{teks_invoice}\n\n"
                "Invoice tersebut tetap menjadi snapshot lama dan tidak ikut berubah.\n\n"
                "Tetap simpan perubahan Resi?"
            )

        jawaban = QMessageBox.warning(
            self,
            "Resi Sudah Masuk Invoice",
            pesan,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return jawaban == QMessageBox.StandardButton.Yes

    def _simpan_perubahan_resi(self):
        """Simpan perubahan Resi, termasuk perubahan suffix PAJAK/NONPAJAK."""
        no_resi_lama = str(self._resi_sedang_diedit or "").strip()
        if not no_resi_lama:
            return

        self.otomatisasi_nomor_resi()
        no_resi_baru = str(self.txt_resi_display.text() or no_resi_lama).strip()
        tanggal_edit = self._tanggal_transaksi
        ctx = self._siapkan_transaksi_form(
            no_resi_baru,
            format_tanggal_ke_db(tanggal_edit),
        )
        payload = ctx["payload"]
        payload["no_resi_lama"] = no_resi_lama
        payload["revision"] = self._revision_sedang_diedit

        if not self._konfirmasi_edit_resi_terinvoice(no_resi_lama, payload):
            return

        try:
            sukses, pesan_error = db_service.update_transaksi_resi(payload)
        except Exception as exc:
            logger.exception("Gagal memperbarui resi %s", no_resi_lama)
            QMessageBox.critical(self, "Edit Resi", f"Gagal menyimpan perubahan: {exc}")
            return

        if not sukses:
            self._tampilkan_error_simpan(pesan_error or "Update resi gagal.")
            return

        payload["no_resi"] = str(payload.get("no_resi") or no_resi_baru).strip()
        self._cetak_setelah_database_tersimpan(ctx, perubahan=True)

        self.notif_tengah = FadeNotification("💾 PERUBAHAN TERSIMPAN", self)
        self.notif_tengah.show()
        self.date_histori.setDate(tanggal_edit)
        self._keluar_mode_edit()
        self.clear_form()
        self.setup_autocomplete()
        self.load_data_resi()

    def load_data_resi(self):
        tgl_pilih = format_tanggal_ke_db(self.date_histori.date())
        kode_cabang = self._kode_cabang_aktif()
        self.list_histori.setUpdatesEnabled(False)
        self.list_histori.clear()
        try:
            rows = db_service.ambil_histori_resi_by_tanggal(
                tgl_pilih,
                kode_cabang,
            ) or []
            self._isi_tree_histori(
                rows,
                tanggal_default=self.date_histori.date(),
            )
        except Exception:
            logger.exception(
                "Gagal memuat histori resi untuk tanggal %s",
                tgl_pilih,
            )
        finally:
            self.list_histori.setUpdatesEnabled(True)
            self.list_histori.viewport().update()

    def munculkan_preview(self, item, _column=None):
        no_resi = self._ambil_no_resi_dari_item(item)
        if not no_resi:
            return
        try:
            row = db_service.ambil_detail_resi(no_resi)
            if not row:
                return

            jenis_pajak_db = (
                str(row[18] or "NONPAJAK").strip().upper()
                if len(row) > 18 else "NONPAJAK"
            )
            ongkir_kg_db = str(row[15]) if row[15] is not None else ""
            ongkir_m3_db = str(row[16]) if row[16] is not None else ""
            fmt_ongkir_kg = _format_ongkir_aman(ongkir_kg_db)
            fmt_ongkir_m3 = _format_ongkir_aman(ongkir_m3_db)
            val_ongkir = int(row[12]) if row[12] else 0

            formatted_data = {
                "tanggal": format_tanggal_ke_ui(row[0]),
                "no_resi": no_resi,
                "pengirim_nama": str(row[1]),
                "pengirim_telp": str(row[2]),
                "pengirim_alamat": str(row[3]),
                "penerima_nama": str(row[4]),
                "penerima_telp": str(row[5]),
                "penerima_alamat": str(row[6]),
                "penerima_kota": str(row[7]),
                "tipe_pajak": "PAJAK" if jenis_pajak_db.startswith("PAJAK") else "NONPAJAK",
                "list_barang": self._rincian_dari_row_resi(row, fallback_kosong=False),
                "total_qty": str(row[10]),
                "total_berat": str(row[9]),
                "total_cbm": str(row[11]),
                "total_jumlah_ongkir": (
                    f"Rp {format_ke_rupiah(val_ongkir)}" if val_ongkir > 0 else ""
                ),
                "ongkir_kg": fmt_ongkir_kg,
                "ongkir_m3": fmt_ongkir_m3,
                "ongkir_per_kg": fmt_ongkir_kg,
                "ongkir_per_cbm": fmt_ongkir_m3,
                "ongkir_kg_raw": ongkir_kg_db,
                "ongkir_m3_raw": ongkir_m3_db,
            }
            cetak_resi_ke_printer(formatted_data, self)
        except Exception as exc:
            QMessageBox.critical(self, "Error Preview", f"Gagal memuat preview: {exc}")

    def refresh_data(self):
        """Force reload data dari database (dipanggil tombol Perbarui di main)."""
        try:
            self.load_data_resi()
        except Exception:
            logger.exception("Gagal refresh data Resi")

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
        self._keluar_mode_edit()
        # date_input berada di top bar (di luar container reset). Resi baru harus
        # selalu kembali ke tanggal hari ini setelah keluar dari mode Edit.
        if hasattr(self, "date_input"):
            self.set_tanggal_resi(QDate.currentDate())

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