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
    QSplitter,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION
import services.database_service as db_service
from themes.components import (
    FADE_NOTIFICATION_STYLE,
    terapkan_style_combobox,
)
from themes.calendar import terapkan_style_kalender
from themes.modules.resi import (
    get_btn_simpan_cetak_style,
    get_resi_detail_barang_theme,
    get_resi_rekening_styles,
    get_resi_static_styles,
    get_resi_styles,
    get_btn_clear_container_style,
)
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
from utils.placeholder_helper import (
    setup_placeholder_dinamis,
    terap_semua_placeholder_dinamis,
)
from utils.table_helper import buat_tabel_item
from utils.typography import get_global_font_sizes
from utils.validators import UppercaseValidator, get_decimal_validator
from utils.widget_helpers import (
    _blokir_signal_sementara,
    paksa_kapital_lineedit,
    terapkan_popup_combobox_bawah,
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

        self.label.setStyleSheet(FADE_NOTIFICATION_STYLE)
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

    def __init__(self):
        super().__init__()
        self.kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')
        self.settings = QSettings("AplikasiEkspedisi", "PengaturanUI")
        self.current_theme = self.settings.value("theme", "light")
        self.current_resi_data = None

        # Menyimpan subtotal sebelum PPN agar pergantian PAJAK/NONPAJAK
        # tidak menyebabkan pajak dihitung berulang kali.
        self._mode_total_ongkir = None
        self._subtotal_manual_ongkir = 0
        self._sedang_set_total_ongkir = False

        self.init_ui()

    def init_ui(self):
        layout_utama_asli = QHBoxLayout(self)
        layout_utama_asli.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)
        layout_utama_asli.addWidget(self.splitter)

        initial_theme_styles = get_resi_static_styles(
            self.current_theme == "dark"
        )

        self.scroll_kiri = QScrollArea()
        self.scroll_kiri.setMinimumWidth(700)
        self.scroll_kiri.setMaximumWidth(1800)
        self.scroll_kiri.setWidgetResizable(True)
        self.scroll_kiri.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_kiri.setStyleSheet(
            initial_theme_styles["scroll_kiri"]
        )

        self.widget_kiri = QWidget()
        layout_kiri = QVBoxLayout(self.widget_kiri)
        layout_kiri.setContentsMargins(8, 8, 8, 8)
        layout_kiri.setSpacing(8)

        hbox_top_bar = QHBoxLayout()
        hbox_top_bar.setContentsMargins(0, 0, 0, 0)

        self.lbl_main_title = QLabel("📋 Form Input Surat Jalan")
        hbox_top_bar.addWidget(self.lbl_main_title)
        hbox_top_bar.addStretch(1)

        hbox_date = QHBoxLayout()
        hbox_date.setSpacing(8)
        self.lbl_tgl_tag = QLabel("Tanggal:")
        self.date_input = QDateEdit(self)
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setReadOnly(True)
        self.date_input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.date_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.date_input.setFixedWidth(160)
        self.date_input.setDisplayFormat("dddd, dd/MM/yyyy")
        self.date_input.dateChanged.connect(self.otomatisasi_nomor_resi)
        hbox_date.addWidget(self.lbl_tgl_tag)
        hbox_date.addWidget(self.date_input)
        hbox_top_bar.addLayout(hbox_date)
        hbox_top_bar.addStretch(1)

        hbox_resi_layout = QHBoxLayout()
        hbox_resi_layout.setSpacing(8)
        self.lbl_resi_tag = QLabel("No. Resi:")
        self.lbl_resi_tag.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.txt_resi_display = QLabel("GEN-RESI-CODE")
        self.txt_resi_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_resi_display.setFixedWidth(200)
        self.txt_resi_display.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        hbox_resi_layout.addWidget(self.lbl_resi_tag)
        hbox_resi_layout.addWidget(self.txt_resi_display)
        hbox_top_bar.addLayout(hbox_resi_layout)

        layout_kiri.addLayout(hbox_top_bar)

        hbox_cards_data = QHBoxLayout()
        hbox_cards_data.setSpacing(8)

        self.group_pengirim = QGroupBox("")
        grid_pengirim = QGridLayout(self.group_pengirim)
        grid_pengirim.setVerticalSpacing(8)
        grid_pengirim.setHorizontalSpacing(8)
        grid_pengirim.setContentsMargins(12, 12, 12, 12)

        self.btn_clear_pengirim = self._buat_tombol_clear_container(
            self.group_pengirim,
            "Reset pengirim",
            self.bersihkan_data_pengirim,
        )

        self.txt_pengirim = QLineEdit()
        self.txt_pengirim.setPlaceholderText("Nama pengirim/perusahaan/toko ...")

        self.txt_hp_pengirim = QLineEdit()
        self.txt_hp_pengirim.setPlaceholderText("08xx xxxx ...")

        self.txt_alamat_pengirim = QLineEdit()
        self.txt_alamat_pengirim.setPlaceholderText("Masukkan alamat lengkap ...")

        self.txt_kota_pengirim = QLineEdit()
        self.txt_kota_pengirim.setPlaceholderText("Kota asal ...")

        grid_pengirim.addWidget(QLabel("Pengirim:"), 0, 0)
        grid_pengirim.addWidget(self.txt_pengirim, 0, 1)
        grid_pengirim.addWidget(QLabel("No. HP:"), 0, 2)
        grid_pengirim.addWidget(self.txt_hp_pengirim, 0, 3)
        grid_pengirim.addWidget(QLabel("Alamat:"), 1, 0)
        grid_pengirim.addWidget(self.txt_alamat_pengirim, 1, 1, 1, 3)
        grid_pengirim.addWidget(QLabel("Kota Asal:"), 2, 0)
        grid_pengirim.addWidget(self.txt_kota_pengirim, 2, 1, 1, 3)

        grid_pengirim.setRowStretch(0, 1)
        grid_pengirim.setRowStretch(1, 1)
        grid_pengirim.setRowStretch(2, 1)

        grid_pengirim.setColumnStretch(1, 6)
        grid_pengirim.setColumnStretch(3, 4)
        hbox_cards_data.addWidget(self.group_pengirim, stretch=1)

        self.group_penerima = QGroupBox("")
        grid_penerima = QGridLayout(self.group_penerima)
        grid_penerima.setVerticalSpacing(8)
        grid_penerima.setHorizontalSpacing(8)
        grid_penerima.setContentsMargins(12, 12, 12, 12)

        self.btn_clear_penerima = self._buat_tombol_clear_container(
            self.group_penerima,
            "Reset penerima",
            self.bersihkan_data_penerima,
        )

        self.txt_penerima = QLineEdit()
        self.txt_penerima.setPlaceholderText("Nama penerima/perusahaan/toko...")

        self.txt_hp_penerima = QLineEdit()
        self.txt_hp_penerima.setPlaceholderText("08xx xxxx ...")

        self.txt_alamat_penerima = QLineEdit()
        self.txt_alamat_penerima.setPlaceholderText("Masukkan alamat lengkap ...")

        hbox_dest_widgets = QHBoxLayout()
        hbox_dest_widgets.setSpacing(8)
        hbox_dest_widgets.setContentsMargins(0, 0, 0, 0)

        self.txt_kota_penerima = QLineEdit()
        self.txt_kota_penerima.setPlaceholderText("Kota tujuan ...")

        self.cb_provinsi = QComboBox()
        self.cb_provinsi.installEventFilter(self)

        raw_provinsi = db_service.get_setting('provinsi_tujuan')
        provinsi_tujuan = json.loads(raw_provinsi) if isinstance(
            raw_provinsi,
            str,
        ) else (
                raw_provinsi or ["PROVINSI A", "PROVINSI B", "PROVINSI C"])

        self.cb_provinsi.addItems(provinsi_tujuan)
        self.cb_provinsi.currentTextChanged.connect(self.otomatisasi_nomor_resi)

        hbox_dest_widgets.addWidget(self.txt_kota_penerima, stretch=6)
        hbox_dest_widgets.addWidget(self.cb_provinsi, stretch=4)

        grid_penerima.addWidget(QLabel("Penerima:"), 0, 0)
        grid_penerima.addWidget(self.txt_penerima, 0, 1)
        grid_penerima.addWidget(QLabel("No. HP:"), 0, 2)
        grid_penerima.addWidget(self.txt_hp_penerima, 0, 3)
        grid_penerima.addWidget(QLabel("Alamat:"), 1, 0)
        grid_penerima.addWidget(self.txt_alamat_penerima, 1, 1, 1, 3)
        grid_penerima.addWidget(QLabel("Kota:"), 2, 0)
        grid_penerima.addLayout(hbox_dest_widgets, 2, 1, 1, 3)

        grid_penerima.setRowStretch(0, 1)
        grid_penerima.setRowStretch(1, 1)
        grid_penerima.setRowStretch(2, 1)

        grid_penerima.setColumnStretch(1, 6)
        grid_penerima.setColumnStretch(3, 4)
        hbox_cards_data.addWidget(self.group_penerima, stretch=1)

        layout_kiri.addLayout(hbox_cards_data)

        self.group_tabel_container = QGroupBox("")
        self.group_tabel_container.setMinimumHeight(250)

        vbox_tabel_inner = QVBoxLayout(self.group_tabel_container)
        vbox_tabel_inner.setContentsMargins(12, 12, 12, 12)
        vbox_tabel_inner.setSpacing(8)

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

        mode_resize_kolom = {
            self.KOL_NO: QHeaderView.ResizeMode.Fixed,
            self.KOL_NAMA_BARANG: QHeaderView.ResizeMode.Interactive,
            self.KOL_KOLI: QHeaderView.ResizeMode.Interactive,
            self.KOL_BERAT: QHeaderView.ResizeMode.Interactive,
            self.KOL_CBM: QHeaderView.ResizeMode.Interactive,
        }
        for kolom, mode in mode_resize_kolom.items():
            self.table_items.horizontalHeader().setSectionResizeMode(kolom, mode)
            self.table_items.setColumnWidth(kolom, self.LEBAR_KOLOM_DASAR[kolom])
        self.table_items.horizontalHeader().setStretchLastSection(True)

        self.table_items.horizontalHeader().sectionResized.connect(
            self.auto_save_ukuran_kolom,
        )
        self.table_items.setMinimumHeight(150)
        self.table_items.verticalHeader().setVisible(False)
        vbox_tabel_inner.addWidget(self.table_items)

        hbox_tbl_btn = QHBoxLayout()
        hbox_tbl_btn.setSpacing(8)
        self.btn_tambah_baris = QPushButton("➕ Tambah Baris")
        self.btn_tambah_baris.clicked.connect(self.tambah_baris_barang)

        self.btn_hapus_baris = QPushButton("🗑️ Hapus Baris")
        self.btn_hapus_baris.clicked.connect(self.hapus_baris_terpilih)

        hbox_tbl_btn.addWidget(self.btn_tambah_baris)
        hbox_tbl_btn.addWidget(self.btn_hapus_baris)
        hbox_tbl_btn.addStretch()
        vbox_tabel_inner.addLayout(hbox_tbl_btn)

        layout_kiri.addWidget(self.group_tabel_container)

        hbox_bottom_layout = QHBoxLayout()
        hbox_bottom_layout.setSpacing(8)

        self.group_finance = QGroupBox("")
        grid_finansial = QGridLayout(self.group_finance)
        grid_finansial.setSpacing(8)
        grid_finansial.setContentsMargins(12, 12, 12, 12)

        self.btn_clear_finance = self._buat_tombol_clear_container(
            self.group_finance,
            "Reset detail ongkir",
            self.bersihkan_detail_pembayaran,
        )

        self.txt_ongkir_kg = QLineEdit()
        self.txt_ongkir_kg.setPlaceholderText("Ongkir /kg")
        # Shift+Tab dari Detail Ongkir kembali ke sel terakhir Detail Barang.
        self.txt_ongkir_kg.installEventFilter(self)

        self.txt_ongkir_m3 = QLineEdit()
        self.txt_ongkir_m3.setPlaceholderText("Ongkir /m3")

        self.txt_total_ongkir = QLineEdit()
        self.txt_total_ongkir.setPlaceholderText("Input Bisa Otomatis dan Manual")
        self.txt_total_ongkir.setToolTip(
            "Untuk transaksi PAJAK, angka manual dianggap subtotal sebelum PPN 1,1%."
        )
        self.txt_total_ongkir.textEdited.connect(self._catat_subtotal_ongkir_manual)
        self.txt_total_ongkir.editingFinished.connect(
            self._terapkan_ppn_ke_total_manual
        )

        self.cb_pajak = QComboBox()
        self.cb_pajak.addItems(["NONPAJAK", "PAJAK (PPN 1,1%)"])
        self.cb_pajak.setToolTip(
            "PAJAK menambahkan PPN 1,1% ke subtotal ongkir."
        )
        self.cb_pajak.currentTextChanged.connect(self.otomatisasi_nomor_resi)
        self.cb_pajak.currentTextChanged.connect(
            self._perbarui_total_saat_jenis_transaksi_berubah
        )
        self.cb_payment = QComboBox()
        self.cb_payment.addItems(["TF / INVOICE", "CASH"])

        self.txt_ongkir_kg.textChanged.connect(self.kalkulator_finansial_otomatis)
        self.txt_ongkir_kg.textChanged.connect(
            lambda: format_input_ribuan_gaya_indonesia(self.txt_ongkir_kg),
        )

        self.txt_ongkir_m3.textChanged.connect(self.kalkulator_finansial_otomatis)
        self.txt_ongkir_m3.textChanged.connect(
            lambda: format_input_ribuan_gaya_indonesia(self.txt_ongkir_m3),
        )

        self.txt_total_ongkir.textChanged.connect(
            lambda: format_input_ribuan_gaya_indonesia(self.txt_total_ongkir),
        )

        grid_finansial.addWidget(QLabel("Ongkir per kg (Rp):"), 0, 0)
        grid_finansial.addWidget(self.txt_ongkir_kg, 0, 1)
        grid_finansial.addWidget(QLabel("Ongkir per m3 (Rp):"), 1, 0)
        grid_finansial.addWidget(self.txt_ongkir_m3, 1, 1)
        grid_finansial.addWidget(QLabel("Total Ongkir (Rp):"), 2, 0)
        grid_finansial.addWidget(self.txt_total_ongkir, 2, 1)
        grid_finansial.addWidget(QLabel("Jenis Transaksi:"), 3, 0)
        grid_finansial.addWidget(self.cb_pajak, 3, 1)
        grid_finansial.addWidget(QLabel("Metode Payment:"), 4, 0)
        grid_finansial.addWidget(self.cb_payment, 4, 1)

        grid_finansial.setRowStretch(5, 1)
        hbox_bottom_layout.addWidget(self.group_finance, stretch=45)

        self.layout_pay_method = QHBoxLayout()
        self.layout_pay_method.setContentsMargins(0, 0, 0, 0)
        self.layout_pay_method.setSpacing(8)

        self.rek_cards_labels = []

        self.box_np = QGroupBox("Rekening Nonpajak")
        vbox_np_outer = QVBoxLayout(self.box_np)
        vbox_np_outer.setContentsMargins(4, 10, 4, 4)

        scroll_np = QScrollArea()
        scroll_np.setWidgetResizable(True)
        scroll_np.setFrameShape(QFrame.Shape.NoFrame)
        scroll_np.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        widget_np_content = QWidget()
        vbox_np = QVBoxLayout(widget_np_content)
        vbox_np.setContentsMargins(8, 8, 8, 8)
        vbox_np.setSpacing(8)

        raw_np = db_service.get_setting('rekening_nonpajak')
        rek_np_list = json.loads(raw_np) if isinstance(raw_np, str) else (raw_np or [])
        self._bangun_kartu_rekening(
            rek_np_list,
            vbox_np,
            initial_theme_styles["rekening_card"],
        )

        vbox_np.addStretch()
        scroll_np.setWidget(widget_np_content)
        vbox_np_outer.addWidget(scroll_np)

        self.box_p = QGroupBox("Rekening Pajak (PT)")
        vbox_p_outer = QVBoxLayout(self.box_p)
        vbox_p_outer.setContentsMargins(4, 10, 4, 4)

        scroll_p = QScrollArea()
        scroll_p.setWidgetResizable(True)
        scroll_p.setFrameShape(QFrame.Shape.NoFrame)
        scroll_p.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        widget_p_content = QWidget()
        vbox_p = QVBoxLayout(widget_p_content)
        vbox_p.setContentsMargins(8, 8, 8, 8)
        vbox_p.setSpacing(8)

        raw_p = db_service.get_setting('rekening_pajak')
        rek_p_list = json.loads(raw_p) if isinstance(raw_p, str) else (raw_p or [])
        self._bangun_kartu_rekening(
            rek_p_list,
            vbox_p,
            initial_theme_styles["rekening_card"],
        )

        vbox_p.addStretch()
        scroll_p.setWidget(widget_p_content)
        vbox_p_outer.addWidget(scroll_p)

        self.layout_pay_method.addWidget(self.box_np, stretch=1)
        self.layout_pay_method.addWidget(self.box_p, stretch=1)

        hbox_bottom_layout.addLayout(self.layout_pay_method, stretch=55)
        layout_kiri.addLayout(hbox_bottom_layout)

        hbox_main_action = QHBoxLayout()
        hbox_main_action.setContentsMargins(0, 0, 0, 0)
        hbox_main_action.setSpacing(0)

        self.widget_action_kiri = QWidget()
        self.widget_action_kiri.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self.btn_generate_simpan = QPushButton("⚡ SIMPAN DAN CETAK")
        self.btn_generate_simpan.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_generate_simpan.setStyleSheet(get_btn_simpan_cetak_style())
        self.btn_generate_simpan.clicked.connect(self.simpan_ke_database)

        self.cb_payment.installEventFilter(self)
        self.btn_generate_simpan.installEventFilter(self)

        self.widget_action_kanan = QWidget()
        self.widget_action_kanan.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        layout_action_kanan = QHBoxLayout(self.widget_action_kanan)
        layout_action_kanan.setContentsMargins(12, 0, 0, 0)
        layout_action_kanan.setSpacing(0)

        self.lbl_reset_form = QPushButton("Reset Form")
        self.lbl_reset_form.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.lbl_reset_form.clicked.connect(self.reset_form_input_manual)
        self.lbl_reset_form.installEventFilter(self)

        layout_action_kanan.addWidget(
            self.lbl_reset_form,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        layout_action_kanan.addStretch(1)

        hbox_main_action.addWidget(self.widget_action_kiri, stretch=1)
        hbox_main_action.addWidget(
            self.btn_generate_simpan,
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        hbox_main_action.addWidget(self.widget_action_kanan, stretch=1)

        layout_kiri.addSpacing(15)
        layout_kiri.addLayout(hbox_main_action)
        layout_kiri.addStretch(1)

        self.widget_kanan = QWidget()
        self.widget_kanan.setMinimumWidth(256)
        self.widget_kanan.setMaximumWidth(520)
        layout_kanan = QVBoxLayout(self.widget_kanan)
        layout_kanan.setContentsMargins(8, 8, 8, 8)
        layout_kanan.setSpacing(8)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Cari resi, pengirim, penerima...")
        self.txt_search.textChanged.connect(self.filter_data_resi)
        layout_kanan.addWidget(self.txt_search)

        hbox_histori_header = QHBoxLayout()
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

        hbox_histori_header.addWidget(self.lbl_histori_title)
        hbox_histori_header.addWidget(self.date_histori)
        hbox_histori_header.addWidget(self.btn_reset_tgl)
        hbox_histori_header.addStretch()

        self.list_histori = QListWidget()
        self.list_histori.itemDoubleClicked.connect(self.munculkan_preview)

        layout_kanan.addLayout(hbox_histori_header)
        layout_kanan.addWidget(self.list_histori)

        self.scroll_kiri.setWidget(self.widget_kiri)
        self.splitter.addWidget(self.scroll_kiri)
        self.splitter.addWidget(self.widget_kanan)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([856, 256])

        self.setup_uppercase_hooks()
        self.setup_autocomplete()
        self.tambah_baris_barang()

        terap_semua_placeholder_dinamis(
            self,
            is_dark=self.current_theme == "dark",
        )

        self.otomatisasi_nomor_resi()
        self.sesuaikan_tema_lokal()
        self.load_data_resi()
        terapkan_popup_combobox_bawah(self)
        QTimer.singleShot(0, self._posisikan_tombol_clear_container)

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

        terap_semua_placeholder_dinamis(
            self.widget_kiri,
            is_dark=self.current_theme == "dark",
        )

        self.kalkulator_finansial_otomatis()
        self.otomatisasi_nomor_resi()

        QTimer.singleShot(0, self.txt_pengirim.setFocus)

    def _buat_tombol_clear_container(self, parent, tooltip, callback):
        tombol = QToolButton(parent)
        tombol.setText("⟳")
        tombol.setToolTip(tooltip)

        tombol.setFixedSize(20, 20)
        tombol.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # 1. Cek tema dengan fallback yang lebih aman
        win = self.window()
        is_dark = False
        if win and hasattr(win, "current_theme"):
            is_dark = (win.current_theme == "dark")
        elif hasattr(self, "current_theme"):
            is_dark = (self.current_theme == "dark")

        # 2. Terapkan stylesheet dinamis
        tombol.setStyleSheet(get_btn_clear_container_style(is_dark))

        tombol.clicked.connect(callback)
        tombol.raise_()

        # 3. Simpan ke list lokal jika ada penyesuaian tema ulang (opsional tapi bagus)
        if not hasattr(self, "_tombol_clear_list"):
            self._tombol_clear_list = []
        self._tombol_clear_list.append(tombol)

        # Watcher posisi
        tombol._resize_watcher = _ResetButtonResizeWatcher(parent, tombol)
        parent.installEventFilter(tombol._resize_watcher)

        return tombol

    def _posisikan_tombol_clear_container(self):
        """Menjaga seluruh tombol reset tetap di pojok kanan atas container."""
        pasangan = (
            (
                getattr(self, "group_pengirim", None),
                getattr(self, "btn_clear_pengirim", None),
            ),
            (
                getattr(self, "group_penerima", None),
                getattr(self, "btn_clear_penerima", None),
            ),
            (
                getattr(self, "group_tabel_container", None),
                getattr(self, "btn_clear_barang", None),
            ),
            (
                getattr(self, "group_finance", None),
                getattr(self, "btn_clear_finance", None),
            ),
        )

        for container, tombol in pasangan:
            if container is None or tombol is None:
                continue

            tombol.move(
                max(2, container.width() - tombol.width() - 4),
                3,
            )
            tombol.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._posisikan_tombol_clear_container()

    def bersihkan_data_pengirim(self):
        """Membersihkan hanya input di container Pengirim."""
        reset_form_input_global(
            self.group_pengirim,
            fokus_ke=self.txt_pengirim,
        )
        terap_semua_placeholder_dinamis(
            self.group_pengirim,
            is_dark=self.current_theme == "dark",
        )

    def bersihkan_data_penerima(self):
        """Membersihkan hanya input di container Penerima."""
        reset_form_input_global(
            self.group_penerima,
            indeks_combo_default=0,
            fokus_ke=self.txt_penerima,
        )
        terap_semua_placeholder_dinamis(
            self.group_penerima,
            is_dark=self.current_theme == "dark",
        )

        self.otomatisasi_nomor_resi()

    def bersihkan_detail_barang(self):
        """Menghapus seluruh detail barang lalu menyiapkan satu baris baru."""
        reset_form_input_global(
            self.group_tabel_container,
            kosongkan_tabel=True,
        )
        self.tambah_baris_barang()
        terap_semua_placeholder_dinamis(
            self.group_tabel_container,
            is_dark=self.current_theme == "dark",
        )
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
        terap_semua_placeholder_dinamis(
            self.group_finance,
            is_dark=self.current_theme == "dark",
        )
        self.kalkulator_finansial_otomatis()
        self.otomatisasi_nomor_resi()

    def showEvent(self, event):
        super().showEvent(event)

        # Autocomplete sudah dibuat saat init_ui().
        # Tema lokal dikelola MainWindow ketika tab diaktifkan.
        self.kode_cabang = CURRENT_SESSION.get(
            "kode_cabang",
            "PUSAT",
        )

        terapkan_popup_combobox_bawah(self)
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

        theme = get_resi_detail_barang_theme(
            is_dark=is_dark,
            sz_base=sz_base,
        )

        self._detail_barang_input_qss = theme["cell_input"]

        table.setAlternatingRowColors(True)
        table.setShowGrid(True)

        font_table = table.font()
        font_table.setPixelSize(sz_base)
        table.setFont(font_table)

        table.horizontalHeader().setStyleSheet(
            theme["header"]
        )

        for row in range(table.rowCount()):
            for column in (
                self.KOL_NAMA_BARANG,
                self.KOL_KOLI,
                self.KOL_BERAT,
                self.KOL_CBM,
            ):
                editor = table.cellWidget(row, column)

                if editor is not None:
                    editor.setStyleSheet(
                        theme["cell_input"]
                    )

    def sesuaikan_tema_lokal(self):
        win = self.window()

        is_dark = (
            win.current_theme == "dark"
            if win and hasattr(win, "current_theme")
            else self.settings.value("theme", "light") == "dark"
        )

        self.current_theme = "dark" if is_dark else "light"

        z = zoom_helper.dapatkan_zoom_level(
            self.__class__.__name__
        )

        terap_semua_placeholder_dinamis(
            self,
            is_dark=is_dark,
        )

        zoom_berubah = (
                getattr(self, "_zoom_terakhir_tema", None) != z
        )
        self._zoom_terakhir_tema = z

        fs_statis = get_global_font_sizes(0)

        styles_statis = get_resi_styles(
            is_dark,
            fs_statis["sz_title"],
            fs_statis["sz_tag"],
            fs_statis["sz_sm"],
            fs_statis["sz_base"],
            fs_statis["sz_input"],
            fs_statis["sz_total"],
            z=0,
        )

        fs_zoom = get_global_font_sizes(z)

        styles_zoom = get_resi_styles(
            is_dark,
            fs_zoom["sz_title"],
            fs_zoom["sz_tag"],
            fs_zoom["sz_sm"],
            fs_zoom["sz_base"],
            fs_zoom["sz_input"],
            fs_zoom["sz_total"],
            z=z,
        )

        def pasang_stylesheet(
                daftar_nama_widget,
                sumber_style,
        ):
            for nama_widget in daftar_nama_widget:
                widget = getattr(
                    self,
                    nama_widget,
                    None,
                )
                qss = sumber_style.get(nama_widget)

                if widget is not None and qss is not None:
                    widget.setStyleSheet(qss)

        pasang_stylesheet(
            (
                # Top bar sebelah kiri.
                "lbl_main_title",
                "lbl_tgl_tag",
                "lbl_resi_tag",
                "txt_resi_display",
                "date_input",

                # Histori sebelah kanan.
                "txt_search",
                "lbl_histori_title",
                "date_histori",
                "btn_reset_tgl",
                "list_histori",

                # Tombol bawah.
                "btn_generate_simpan",
                "lbl_reset_form",

                # Struktur utama.
                "scroll_kiri",
                "splitter",
            ),
            styles_statis,
        )

        pasang_stylesheet(
            (
                "group_pengirim",
                "group_penerima",
                "group_tabel_container",
                "group_finance",

                "btn_tambah_baris",
                "btn_hapus_baris",

                "box_np",
                "box_p",
            ),
            styles_zoom,
        )

        # Input yang semuanya berada di dalam kotak merah.
        input_area_zoom = (
            self.txt_pengirim,
            self.txt_hp_pengirim,
            self.txt_alamat_pengirim,
            self.txt_kota_pengirim,

            self.txt_penerima,
            self.txt_hp_penerima,
            self.txt_alamat_penerima,
            self.txt_kota_penerima,
            self.cb_provinsi,

            self.txt_ongkir_kg,
            self.txt_ongkir_m3,
            self.cb_pajak,
            self.cb_payment,
        )

        for widget in input_area_zoom:
            if widget is not None:
                widget.setStyleSheet(
                    styles_zoom["input_utama"]
                )

        terapkan_style_combobox(
            (
                self.cb_provinsi,
                self.cb_pajak,
                self.cb_payment,
            ),
            is_dark=is_dark,
        )

        # Total ongkir juga termasuk area kotak merah.
        if self.txt_total_ongkir is not None:
            self.txt_total_ongkir.setStyleSheet(
                styles_zoom["txt_total_ongkir"]
            )

        # Tabel Detail Barang memakai ukuran zoom aktif.
        self._terapkan_tema_detail_barang(
            is_dark=is_dark,
            sz_base=fs_zoom["sz_base"],
        )

        # ==================================================
        # UKURAN TABEL — TETAP MENGIKUTI ZOOM
        # ==================================================
        if zoom_berubah:
            self.table_items.verticalHeader().setDefaultSectionSize(
                34 + z
            )

            try:
                saved_state = self.settings.value(
                    "ukuran_tabel_resi"
                )

                if saved_state:
                    self.table_items.horizontalHeader().restoreState(
                        saved_state
                    )
                else:
                    self.table_items.setColumnWidth(
                        self.KOL_NO,
                        max(
                            30,
                            self.LEBAR_KOLOM_DASAR[self.KOL_NO]
                            + (z * 2),
                        ),
                    )

                    self.table_items.setColumnWidth(
                        self.KOL_NAMA_BARANG,
                        max(
                            150,
                            self.LEBAR_KOLOM_DASAR[
                                self.KOL_NAMA_BARANG
                            ] + (z * 10),
                        ),
                    )

                    self.table_items.setColumnWidth(
                        self.KOL_KOLI,
                        max(
                            70,
                            self.LEBAR_KOLOM_DASAR[
                                self.KOL_KOLI
                            ] + (z * 4),
                        ),
                    )

                    self.table_items.setColumnWidth(
                        self.KOL_BERAT,
                        max(
                            70,
                            self.LEBAR_KOLOM_DASAR[
                                self.KOL_BERAT
                            ] + (z * 4),
                        ),
                    )

                    self.table_items.setColumnWidth(
                        self.KOL_CBM,
                        max(
                            70,
                            self.LEBAR_KOLOM_DASAR[
                                self.KOL_CBM
                            ] + (z * 4),
                        ),
                    )

            except Exception:
                logger.exception(
                    "Gagal memulihkan ukuran kolom tabel resi"
                )

            self._perbarui_cache_lebar_zoom(
                self.table_items,
                self._lebar_dasar_tabel(
                    self.table_items
                ),
            )

        # Kartu rekening berada di dalam kotak merah.
        self.handle_rekening_zoom(
            z,
            is_dark,
        )

        self.date_input.update()
        self.date_histori.update()

        terapkan_style_kalender(
            self.date_histori,
            is_dark=is_dark,
        )

        # Pastikan tombol reset kecil tetap berada di ujung container.
        if hasattr(self, "_tombol_clear_list"):
            for btn in self._tombol_clear_list:
                btn.setStyleSheet(get_btn_clear_container_style(is_dark))

        QTimer.singleShot(
            0,
            self._posisikan_tombol_clear_container,
        )

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
                lbl_top = QLabel(f"<b>{parts[0]}</b>")
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
        rekening_styles = get_resi_rekening_styles(is_dark, z)

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
            self.kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')

            list_pengirim, list_penerima = db_service.ambil_data_autocomplete(
                self.kode_cabang,
            )

            list_pengirim = sorted(
                set([str(x).strip().upper() for x in list_pengirim if str(x).strip()]),
            )
            list_penerima = sorted(
                set([str(x).strip().upper() for x in list_penerima if str(x).strip()]),
            )

            logger.debug(
                "Autocomplete dimuat - Cabang: %s | Pengirim: %d | Penerima: %d",
                self.kode_cabang, len(list_pengirim), len(list_penerima),
            )

            self.txt_pengirim.setCompleter(None)
            self.txt_penerima.setCompleter(None)

            self.comp_pengirim = QCompleter(list_pengirim, self.txt_pengirim)
            self.comp_pengirim.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self.comp_pengirim.setFilterMode(Qt.MatchFlag.MatchStartsWith)
            self.comp_pengirim.setCompletionMode(
                QCompleter.CompletionMode.PopupCompletion,
            )
            self.comp_pengirim.setMaxVisibleItems(12)
            self.comp_pengirim.activated[str].connect(self.pilih_autocomplete_pengirim)
            self.txt_pengirim.setCompleter(self.comp_pengirim)

            self.comp_penerima = QCompleter(list_penerima, self.txt_penerima)
            self.comp_penerima.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self.comp_penerima.setFilterMode(Qt.MatchFlag.MatchStartsWith)
            self.comp_penerima.setCompletionMode(
                QCompleter.CompletionMode.PopupCompletion,
            )
            self.comp_penerima.setMaxVisibleItems(12)
            self.comp_penerima.activated[str].connect(self.pilih_autocomplete_penerima)
            self.txt_penerima.setCompleter(self.comp_penerima)

            if self.txt_pengirim.property("_autocomplete_connected") != "true":
                self.txt_pengirim.textEdited.connect(
                    lambda text: self.comp_pengirim.complete()
                    if getattr(self, 'comp_pengirim', None) and str(text).strip()
                    else None
                )
                self.txt_pengirim.editingFinished.connect(
                    lambda: self.eksekusi_autofill_pengirim(self.txt_pengirim.text())
                )
                self.txt_pengirim.setProperty("_autocomplete_connected", "true")

            if self.txt_penerima.property("_autocomplete_connected") != "true":
                self.txt_penerima.textEdited.connect(
                    lambda text: self.comp_penerima.complete()
                    if getattr(self, 'comp_penerima', None) and str(text).strip()
                    else None
                )
                self.txt_penerima.editingFinished.connect(
                    lambda: self.eksekusi_autofill_penerima(self.txt_penerima.text())
                )
                self.txt_penerima.setProperty("_autocomplete_connected", "true")

            for w in [
                self.txt_hp_pengirim,
                self.txt_alamat_pengirim,
                self.txt_kota_pengirim,
                self.txt_hp_penerima,
                self.txt_alamat_penerima,
                self.txt_kota_penerima
            ]:
                if w:
                    w.setCompleter(None)

        except Exception:
            logger.exception("Gagal menyiapkan autocomplete resi")

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
        self.kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')

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
        kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')

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
        """Atur Tab di Detail Barang agar tidak berputar di dalam tabel."""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

            # Enter/Return menjalankan tombol yang sedang memiliki fokus.
            # Event dikonsumsi agar aksi tidak terpanggil dua kali.
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if obj is self.btn_generate_simpan:
                    self.btn_generate_simpan.click()
                    return True

                if obj is self.lbl_reset_form:
                    self.lbl_reset_form.click()
                    return True

            tombol_tab = key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)

            if tombol_tab:
                mundur = (
                    key == Qt.Key.Key_Backtab
                    or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                )

                # Tab dari Provinsi langsung menuju Nama Barang baris pertama.
                if obj is self.cb_provinsi and not mundur:
                    if self.table_items.rowCount() > 0:
                        target = self.table_items.cellWidget(
                            0,
                            self.KOL_NAMA_BARANG,
                        )

                        if target is not None:
                            QTimer.singleShot(
                                0,
                                lambda w=target: self._fokuskan_widget_input(w),
                            )
                            return True

                # Tab dari Metode Payment langsung ke tombol utama.
                if obj is self.cb_payment and not mundur:
                    QTimer.singleShot(
                        0,
                        lambda: self.btn_generate_simpan.setFocus(
                            Qt.FocusReason.TabFocusReason,
                        ),
                    )
                    return True

                # Navigasi tombol utama dan Reset Form.
                if obj is self.btn_generate_simpan:
                    target = self.cb_payment if mundur else self.lbl_reset_form
                    alasan = Qt.FocusReason.BacktabFocusReason if mundur else Qt.FocusReason.TabFocusReason
                    QTimer.singleShot(
                        0,
                        lambda w=target, reason=alasan: w.setFocus(reason),
                    )
                    return True

                # Shift+Tab dari Reset Form kembali ke tombol utama.
                if obj is self.lbl_reset_form and mundur:
                    QTimer.singleShot(
                        0,
                        lambda: self.btn_generate_simpan.setFocus(
                            Qt.FocusReason.BacktabFocusReason,
                        ),
                    )
                    return True

                # Shift+Tab dari Ongkir/kg kembali ke volume baris terakhir.
                if obj is self.txt_ongkir_kg and mundur:
                    if self.table_items.rowCount() > 0:
                        target = self.table_items.cellWidget(
                            self.table_items.rowCount() - 1,
                            self.KOL_CBM,
                        )
                        QTimer.singleShot(
                            0,
                            lambda w=target: self._fokuskan_widget_input(w),
                        )
                        return True

                posisi = self._cari_posisi_widget_barang(obj)
                if posisi is not None:
                    row, kolom = posisi
                    urutan_kolom = [
                        self.KOL_NAMA_BARANG,
                        self.KOL_KOLI,
                        self.KOL_BERAT,
                        self.KOL_CBM,
                    ]
                    indeks = urutan_kolom.index(kolom)
                    target = None

                    if mundur:
                        if indeks > 0:
                            target = self.table_items.cellWidget(
                                row,
                                urutan_kolom[indeks - 1],
                            )
                        elif row > 0:
                            target = self.table_items.cellWidget(
                                row - 1,
                                self.KOL_CBM,
                            )
                        else:
                            # Dari sel pertama, kembali ke input terakhir penerima.
                            target = self.cb_provinsi
                    else:
                        if indeks < len(urutan_kolom) - 1:
                            target = self.table_items.cellWidget(
                                row,
                                urutan_kolom[indeks + 1],
                            )
                        elif row < self.table_items.rowCount() - 1:
                            target = self.table_items.cellWidget(
                                row + 1,
                                self.KOL_NAMA_BARANG,
                            )
                        else:
                            # Tab dari volume baris terakhir menuju Detail Ongkir.
                            target = self.txt_ongkir_kg

                    if target is not None:
                        QTimer.singleShot(
                            0,
                            lambda w=target: self._fokuskan_widget_input(w),
                        )
                        return True

        return super().eventFilter(obj, event)

    def tambah_baris_barang(self):
        row_count = self.table_items.rowCount()
        self.table_items.insertRow(row_count)

        item_no = buat_tabel_item(
            row_count + 1,
            editable=False,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        self.table_items.setItem(row_count, self.KOL_NO, item_no)

        txt_nama = QLineEdit()
        txt_nama.setPlaceholderText("NAMA / JENIS BARANG...")
        txt_nama.textChanged.connect(lambda: paksa_kapital_lineedit(txt_nama))

        txt_koli = QLineEdit()
        txt_koli.setPlaceholderText("-")
        txt_koli.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt_koli.textChanged.connect(
            lambda _, w=txt_koli: format_input_ribuan_gaya_indonesia(w),
        )

        txt_berat = QLineEdit()
        txt_berat.setPlaceholderText("-")
        txt_berat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt_berat.setValidator(get_decimal_validator(txt_berat))

        txt_volume = QLineEdit()
        txt_volume.setPlaceholderText("-")
        txt_volume.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt_volume.setValidator(get_decimal_validator(txt_volume))

        txt_berat.textChanged.connect(self.kalkulator_finansial_otomatis)
        txt_volume.textChanged.connect(self.kalkulator_finansial_otomatis)

        for w in [
            txt_nama,
            txt_koli,
            txt_berat,
            txt_volume,
        ]:
            setup_placeholder_dinamis(
                w,
                self.current_theme == "dark",
            )

            input_qss = getattr(
                self,
                "_detail_barang_input_qss",
                "",
            )

            if input_qss:
                w.setStyleSheet(input_qss)

            # Tangkap Tab/Shift+Tab sebelum diproses QTableWidget.
            w.installEventFilter(self)

        self.table_items.setCellWidget(row_count, self.KOL_NAMA_BARANG, txt_nama)
        self.table_items.setCellWidget(row_count, self.KOL_KOLI, txt_koli)
        self.table_items.setCellWidget(row_count, self.KOL_BERAT, txt_berat)
        self.table_items.setCellWidget(row_count, self.KOL_CBM, txt_volume)

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
        self.kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')

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
        kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')

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
        kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')
        tgl = format_tanggal_ke_db(QDate.currentDate())
        cp = self.cb_provinsi.currentText()
        ki = self.txt_kota_penerima.text().strip()
        tujuan_full = f"{cp} - {ki}" if ki else cp

        kt_asal = self.txt_kota_pengirim.text().strip().upper()

        items_list, list_barang_html = [], []
        tot_koli, tot_berat, tot_vol = 0, 0.0, 0.0

        for row in range(self.table_items.rowCount()):
            w_nama, w_qty, w_berat, w_vol = [self.table_items.cellWidget(
                row,
                i,
            ) for i in
                                             [
                                                 self.KOL_NAMA_BARANG,
                                                 self.KOL_KOLI,
                                                 self.KOL_BERAT,
                                                 self.KOL_CBM,
                                             ]]

            if w_nama and w_qty:
                nama = w_nama.text().strip()
                if nama:
                    qty_int = max(0, rupiah_to_int(w_qty.text()))
                    b_flt = float(
                        angka_indonesia_to_decimal(
                            w_berat.text() if w_berat else "0"
                        )
                    )
                    v_flt = float(
                        angka_indonesia_to_decimal(
                            w_vol.text() if w_vol else "0"
                        )
                    )

                    tot_koli += qty_int
                    tot_berat += b_flt
                    tot_vol += v_flt

                    items_list.append(nama)

                    list_barang_html.append({
                        'nama': nama,
                        'qty': str(qty_int) if qty_int > 0 else "",
                        'berat': str(b_flt) if b_flt > 0 else "",
                        'cbm': str(v_flt) if v_flt > 0 else "",
                    })

        total_ongkir_val = rupiah_to_int(self.txt_total_ongkir.text())
        ongkir_kg_clean = str(rupiah_to_int(self.txt_ongkir_kg.text()))
        ongkir_m3_clean = str(rupiah_to_int(self.txt_ongkir_m3.text()))

        payload = {
            'no_resi': no_resi,
            'kode_cabang': kode_cabang,
            'tanggal_masuk': tgl,
            'pengirim': self.txt_pengirim.text().strip(),
            'hp_pengirim': self.txt_hp_pengirim.text().strip(),
            'alamat_pengirim': self.txt_alamat_pengirim.text().strip(),
            'kota_asal': kt_asal,
            'penerima': self.txt_penerima.text().strip(),
            'hp_penerima': self.txt_hp_penerima.text().strip(),
            'alamat_penerima': self.txt_alamat_penerima.text().strip(),
            'kota_tujuan': tujuan_full,
            'provinsi_tujuan': self.cb_provinsi.currentText().strip().upper(),
            'nama_barang': ", ".join(items_list),
            'berat': tot_berat,
            'koli': tot_koli,
            'cbm': tot_vol,
            'ongkir_per_kg': ongkir_kg_clean if int(ongkir_kg_clean) > 0 else "",
            'ongkir_per_cbm': ongkir_m3_clean if int(ongkir_m3_clean) > 0 else "",
            'total_ongkir': total_ongkir_val,
            'pembayaran': self.cb_payment.currentText(),
            'rincian_json': json.dumps(list_barang_html),
        }

        sukses, pesan_error = db_service.simpan_transaksi_resi(payload)

        if sukses:
            formatted_ongkir = f"Rp {format_ke_rupiah(total_ongkir_val)}" if total_ongkir_val > 0 else ""

            fmt_ongkir_kg = _format_ongkir_aman(ongkir_kg_clean)
            fmt_ongkir_m3 = _format_ongkir_aman(ongkir_m3_clean)

            formatted_data = {
                'tanggal': format_tanggal_ke_ui(QDate.currentDate()),
                'no_resi': no_resi,
                'pengirim_nama': self.txt_pengirim.text().strip(),
                'pengirim_telp': self.txt_hp_pengirim.text().strip(),
                'pengirim_alamat': self.txt_alamat_pengirim.text().strip(),
                'penerima_nama': self.txt_penerima.text().strip(),
                'penerima_telp': self.txt_hp_penerima.text().strip(),
                'penerima_alamat': self.txt_alamat_penerima.text().strip(),
                'tipe_pajak': 'PAJAK' if self._transaksi_kena_ppn() else 'NONPAJAK',
                'penerima_kota': ki,
                'list_barang': list_barang_html,
                'total_qty': str(tot_koli),
                'total_berat': f"{tot_berat:.1f}",
                'total_cbm': f"{tot_vol:.1f}",
                'total_jumlah_ongkir': formatted_ongkir,
                'ongkir_kg': fmt_ongkir_kg,
                'ongkir_m3': fmt_ongkir_m3,
                'ongkir_per_kg': fmt_ongkir_kg,
                'ongkir_per_cbm': fmt_ongkir_m3,
                'ongkir_kg_raw': ongkir_kg_clean,
                'ongkir_m3_raw': ongkir_m3_clean,
            }

            cetak_resi_ke_printer(formatted_data, self)

            self.notif_tengah = FadeNotification("💾 TERSIMPAN", self)
            self.notif_tengah.show()

            self.date_histori.setDate(QDate.currentDate())
            self.clear_form()
            self.setup_autocomplete()
            self.load_data_resi()
        else:
            kode_error = getattr(pesan_error, "kode", None)

            if kode_error == db_service.KODE_RESI_DUPLIKAT:
                QMessageBox.critical(self, "Gagal", str(pesan_error))
            elif kode_error == db_service.KODE_DB_ERROR:
                QMessageBox.critical(self, "Error Database", str(pesan_error))
            else:
                QMessageBox.critical(self, "Error SQL", f"Gagal simpan: {pesan_error}")

    def load_data_resi(self):
        tgl_pilih = format_tanggal_ke_db(
            self.date_histori.date()
        )
        kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')
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
        self.kode_cabang = CURRENT_SESSION.get('kode_cabang', 'PUSAT')
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

        terap_semua_placeholder_dinamis(
            self,
            is_dark=self.current_theme == "dark",
        )

        self.otomatisasi_nomor_resi()