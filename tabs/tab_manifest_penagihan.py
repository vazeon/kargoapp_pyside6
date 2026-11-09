"""Rekap Manifest Penagihan untuk administrasi penagihan per keberangkatan.

Data pengiriman dibaca dari Resi/Manifest gudang. Catatan penagihan disimpan
terpisah agar tidak mengubah proses manifest gudang atau data transaksi Resi.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from bisect import bisect_right
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION
import services.database_service as db_service
from utils.date_ind_format import format_tanggal_ke_ui
from utils.number_formatters import format_ke_rupiah
from utils.typography import (
    APPLICATION_NAME,
    ORGANIZATION_NAME,
    konversi_style_font_ke_point,
    get_fixed_font_sizes,
    get_font_weights,
)
from themes.modules.buku_gudang import (
    get_buku_gudang_styles,
    get_buku_gudang_menu_style,
)
from utils.smooth_scroll_helper import pasang_scroll_halus


KOLOM = (
    "KODE", "RESI", "PENGIRIM", "PENERIMA", "TUJUAN", "JENIS PAKET",
    "KOLI", "KG/M3", "TAGIHAN", "INVOICE", "PAYMENT MANDIRI", "PAYMENT BCA", "SJB",
)
KOLOM_DATA_PENAGIHAN = {
    7: "kg_m3_manual",
    9: "nomor_invoice_manual",
    10: "payment_mandiri",
    11: "payment_bca",
    12: "sjb",
}
NAMA_BULAN = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)
WARNA_HEADER = "#F4C7F3"
WARNA_GRUP = "#DDEBF7"
WARNA_BARIS = ("#FFFFFF", "#FAFBFC")
WARNA_TOTAL = "#FFF2CC"

_FONT_WEIGHTS = get_font_weights()


class _TabelManifestPenagihan(QTableWidget):
    """Tabel utama dengan sinkronisasi overlay resize yang terkoalesensi."""

    RESIZE_SYNC_INTERVAL_MS = 16

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._callback_resize = None
        self._resize_sync_timer = QTimer(self)
        self._resize_sync_timer.setSingleShot(True)
        self._resize_sync_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._resize_sync_timer.setInterval(self.RESIZE_SYNC_INTERVAL_MS)
        self._resize_sync_timer.timeout.connect(self._jalankan_callback_resize)

    def _jadwalkan_callback_resize(self):
        callback = self._callback_resize
        if callable(callback) and not self._resize_sync_timer.isActive():
            self._resize_sync_timer.start()

    def _jalankan_callback_resize(self):
        callback = self._callback_resize
        if callable(callback):
            callback()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._jadwalkan_callback_resize()


class TabManifestPenagihan(QWidget):
    """Tampilan tagihan kantor yang dikelompokkan vertikal per keberangkatan."""

    SETTINGS_ORGANIZATION = "EkspedisiApp"
    SETTINGS_APPLICATION = "TabManifestPenagihan"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row_resi_by_table_row: dict[int, str] = {}
        self._table_row_by_resi: dict[str, int] = {}
        self._groups: list[dict] = []
        self._group_title_by_table_row: dict[int, str] = {}
        # Cache indeks grup supaya pembaruan sticky header tidak memindai semua grup
        # setiap kali scrollbar bergerak.
        self._group_row_indices: list[int] = []
        self._scroll_halus = None
        self._sedang_memuat = False
        self._sedang_sinkron_pilihan = False
        self._branch_access_mode = "FULL"
        self._original_edit_triggers = None
        self._bangun_ui()
        self.refresh_session_ui()

    @staticmethod
    def _kode_cabang_aktif() -> str:
        return str(CURRENT_SESSION.get("kode_cabang") or "PUSAT").strip().upper()

    def _bangun_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        baris_filter = QHBoxLayout()
        baris_filter.setSpacing(8)
        self.lbl_judul = QLabel("Manifest Penagihan", self)
        baris_filter.addWidget(self.lbl_judul)

        # Gunakan tombol dropdown dan gaya yang sama dengan filter Buku Gudang.
        tahun_sekarang = datetime.now().year
        self.btn_tahun = QPushButton(str(tahun_sekarang), self)
        self.btn_tahun.setFixedSize(90, 30)
        self.btn_tahun.setToolTip("Pilih tahun keberangkatan")
        self.menu_tahun = QMenu(self)
        self.btn_tahun.setMenu(self.menu_tahun)
        self._bangun_menu_tahun()
        baris_filter.addWidget(self.btn_tahun)

        self.btn_bulan = QPushButton(NAMA_BULAN[datetime.now().month - 1], self)
        self.btn_bulan.setFixedSize(115, 30)
        self.btn_bulan.setToolTip("Pilih bulan keberangkatan")
        self.menu_bulan = QMenu(self)
        self.btn_bulan.setMenu(self.menu_bulan)
        self._bangun_menu_bulan()
        baris_filter.addWidget(self.btn_bulan)

        self.lbl_ringkasan = QLabel("Belum ada data")
        self.lbl_ringkasan.setWordWrap(True)
        baris_filter.addWidget(self.lbl_ringkasan, 1)

        self.btn_refresh = QPushButton("Perbarui")
        self.btn_refresh.setToolTip("Muat ulang data manifest dan tagihan")
        self.btn_refresh.clicked.connect(self.refresh_session_ui)
        baris_filter.addWidget(self.btn_refresh)

        self.btn_export = QPushButton("Ekspor Excel")
        self.btn_export.setToolTip("Ekspor rekap bulan yang sedang dipilih ke Excel")
        self.btn_export.clicked.connect(self.ekspor_excel)
        baris_filter.addWidget(self.btn_export)
        layout.addLayout(baris_filter)

        self.tabel = _TabelManifestPenagihan(0, len(KOLOM), self)
        self.tabel.setHorizontalHeaderLabels(KOLOM)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.tabel.setAlternatingRowColors(False)
        self.tabel.setWordWrap(False)
        # Scroll per pixel memungkinkan pergerakan halus dan menyamakan offset
        # vertikal antara tabel utama dan overlay kolom terpin.
        self.tabel.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabel.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setStretchLastSection(False)
        self.tabel.setSortingEnabled(False)
        self.tabel.itemChanged.connect(self._simpan_perubahan_sel)
        self._original_edit_triggers = self.tabel.editTriggers()

        lebar = (82, 115, 220, 220, 130, 240, 90, 120, 135, 145, 120, 120, 120)
        for index, width in enumerate(lebar):
            self.tabel.setColumnWidth(index, width)
        self.tabel.setMinimumHeight(240)

        # Sticky group header ditempatkan di viewport tabel, tepat setelah
        # kolom beku KODE/RESI. Header muncul ketika baris grup aktif melewati
        # bagian atas viewport dan terdorong keluar saat grup berikutnya tiba.
        self.lbl_grup_terpin = QLabel("", self.tabel.viewport())
        self.lbl_grup_terpin.setFixedHeight(27)
        self.lbl_grup_terpin.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.lbl_grup_terpin.setStyleSheet(
            f"QLabel {{ background-color: {WARNA_GRUP}; color: #202020; "
            f"font-weight: {_FONT_WEIGHTS['bold']}; "
            "padding: 4px 6px; border: 1px solid #9A9A9A; }"
        )
        self.lbl_grup_terpin.hide()

        # Overlay dua kolom pertama agar KODE dan RESI tetap terlihat saat
        # bagian tabel lainnya digulir ke arah horizontal.
        self._bangun_kolom_terpin()
        self._scroll_halus = pasang_scroll_halus(
            self.tabel,
            event_targets=(self.tabel.viewport(), self.tabel_terpin.viewport()),
        )
        self.tabel._callback_resize = self._posisikan_tabel_terpin
        self.sesuaikan_tema_lokal()
        layout.addWidget(self.tabel, 1)

    def sesuaikan_tema_lokal(self):
        """Menjaga gaya judul dan kontras tabel sesuai tema aplikasi."""
        window = self.window()
        tema_window = str(getattr(window, "current_theme", "") or "").strip().lower()
        if tema_window in {"light", "dark"}:
            is_dark = tema_window == "dark"
        else:
            settings_ui = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
            tema_tersimpan = str(settings_ui.value("theme", "light") or "light").strip().lower()
            is_dark = tema_tersimpan == "dark"

        styles = konversi_style_font_ke_point(get_buku_gudang_styles(is_dark=is_dark))
        self.lbl_judul.setStyleSheet(styles["lbl_judul"])
        # Kedua dropdown periode memakai style tombol Buku Gudang, sehingga
        # teksnya otomatis rata tengah dan ukuran kontrol konsisten.
        for tombol_filter in (self.btn_tahun, self.btn_bulan):
            tombol_filter.setStyleSheet(styles["btn_tahun"])
        self._style_menu_periode(is_dark)

        style_tabel = (
            "QHeaderView::section { background-color: #F4C7F3; color: #202020; "
            f"font-weight: {_FONT_WEIGHTS['bold']}; "
            "padding: 5px; border: 1px solid #777777; }"
            "QTableWidget { gridline-color: #9A9A9A; }"
        )
        self.tabel.setStyleSheet(style_tabel)
        if hasattr(self, "tabel_terpin"):
            self.tabel_terpin.setStyleSheet(style_tabel)
        self.tabel.horizontalHeader().setMinimumHeight(30)
        self.tabel.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )

    def _bangun_kolom_terpin(self):
        """Membangun overlay untuk kolom KODE dan RESI yang tidak ikut scroll horizontal."""
        self.tabel_terpin = QTableWidget(0, 2, self.tabel)
        self.tabel_terpin.setHorizontalHeaderLabels(KOLOM[:2])
        self.tabel_terpin.verticalHeader().setVisible(False)
        self.tabel_terpin.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tabel_terpin.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tabel_terpin.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tabel_terpin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabel_terpin.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tabel_terpin.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tabel_terpin.setAlternatingRowColors(False)
        self.tabel_terpin.setWordWrap(False)
        self.tabel_terpin.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabel_terpin.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabel_terpin.setSortingEnabled(False)
        self.tabel_terpin.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.tabel_terpin.horizontalHeader().setMinimumHeight(30)
        self.tabel_terpin.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.tabel_terpin.setFrameShape(self.tabel.frameShape())
        self.tabel_terpin.setLineWidth(self.tabel.lineWidth())
        self.tabel_terpin.setColumnWidth(0, self.tabel.columnWidth(0))
        self.tabel_terpin.setColumnWidth(1, self.tabel.columnWidth(1))

        self.tabel.verticalScrollBar().rangeChanged.connect(
            self._sinkronkan_scrollbar_terpin
        )
        self.tabel.verticalScrollBar().valueChanged.connect(
            self.tabel_terpin.verticalScrollBar().setValue
        )
        self.tabel.verticalScrollBar().valueChanged.connect(
            self._perbarui_label_grup_terpin
        )
        self.tabel.horizontalHeader().sectionResized.connect(
            self._sinkronkan_lebar_kolom_terpin
        )
        self.tabel.itemSelectionChanged.connect(
            lambda: self._sinkronkan_pilihan_tabel(self.tabel, self.tabel_terpin)
        )
        self.tabel_terpin.itemSelectionChanged.connect(
            lambda: self._sinkronkan_pilihan_tabel(self.tabel_terpin, self.tabel)
        )
        self.tabel_terpin.cellClicked.connect(self._pilih_baris_tabel_utama)
        self._posisikan_tabel_terpin()

    def _posisikan_tabel_terpin(self):
        """Menempatkan overlay di atas header dan dua kolom pertama."""
        if not hasattr(self, "tabel_terpin"):
            return
        frame = self.tabel.frameWidth()
        lebar = sum(self.tabel.columnWidth(index) for index in (0, 1))
        tinggi = (
            self.tabel.horizontalHeader().height()
            + self.tabel.viewport().height()
            + 2 * frame
        )
        target_geometry = (0, 0, lebar + 2 * frame, tinggi)
        current_geometry = self.tabel_terpin.geometry()
        geometry_changed = (
            current_geometry.x(),
            current_geometry.y(),
            current_geometry.width(),
            current_geometry.height(),
        ) != target_geometry
        if geometry_changed:
            self.tabel_terpin.setGeometry(*target_geometry)

        for column in (0, 1):
            target_width = self.tabel.columnWidth(column)
            if self.tabel_terpin.columnWidth(column) != target_width:
                self.tabel_terpin.setColumnWidth(column, target_width)

        self._sinkronkan_scrollbar_terpin()
        if geometry_changed:
            self.tabel_terpin.raise_()
        self._perbarui_label_grup_terpin()

    def _sinkronkan_scrollbar_terpin(self, *_args):
        if not hasattr(self, "tabel_terpin") or self._sedang_memuat:
            # Saat baris dibangun satu per satu, lewati pembaruan yang berulang;
            # posisi overlay disinkronkan sekali setelah pengisian selesai.
            return
        sumber = self.tabel.verticalScrollBar()
        tujuan = self.tabel_terpin.verticalScrollBar()
        tujuan.setRange(sumber.minimum(), sumber.maximum())
        tujuan.setPageStep(sumber.pageStep())
        tujuan.setSingleStep(sumber.singleStep())
        tujuan.setValue(sumber.value())
        # Rebase target scroll hanya saat animasi sedang idle.
        if self._scroll_halus is not None:
            self._scroll_halus.sinkronkan_target("vertical", sumber.value())
            self._scroll_halus.sinkronkan_target(
                "horizontal", self.tabel.horizontalScrollBar().value()
            )
        self._perbarui_label_grup_terpin()

    def _sinkronkan_lebar_kolom_terpin(self, logical_index, _old_size, new_size):
        if logical_index not in (0, 1) or not hasattr(self, "tabel_terpin"):
            return
        self.tabel_terpin.setColumnWidth(logical_index, new_size)
        self._posisikan_tabel_terpin()

    def _sinkronkan_pilihan_tabel(self, sumber, tujuan):
        if self._sedang_sinkron_pilihan:
            return
        self._sedang_sinkron_pilihan = True
        try:
            tujuan.clearSelection()
            for index in sumber.selectionModel().selectedRows():
                tujuan.selectRow(index.row())
        finally:
            self._sedang_sinkron_pilihan = False

    def _pilih_baris_tabel_utama(self, row, _column):
        self.tabel.selectRow(row)

    def _refresh_tabel_terpin(self):
        """Menyalin tampilan KODE/RESI agar baris dan span tetap sejajar."""
        frozen = self.tabel_terpin
        frozen.blockSignals(True)
        frozen.setUpdatesEnabled(False)
        try:
            frozen.clearSpans()
            frozen.clearContents()
            frozen.setRowCount(self.tabel.rowCount())
            frozen.setColumnWidth(0, self.tabel.columnWidth(0))
            frozen.setColumnWidth(1, self.tabel.columnWidth(1))
            for row in range(self.tabel.rowCount()):
                for column in (0, 1):
                    item = self.tabel.item(row, column)
                    if item is not None:
                        frozen.setItem(row, column, item.clone())
                frozen.setRowHeight(row, self.tabel.rowHeight(row))
                if row in self._group_title_by_table_row or row == self.tabel.rowCount() - 1:
                    frozen.setSpan(row, 0, 1, 2)
        finally:
            frozen.setUpdatesEnabled(True)
            frozen.blockSignals(False)
        frozen.verticalScrollBar().setValue(self.tabel.verticalScrollBar().value())
        self._posisikan_tabel_terpin()
        self._perbarui_label_grup_terpin()

    def _perbarui_label_grup_terpin(self, *_args):
        """Perbarui sticky header dalam O(log jumlah grup), dengan hanya dua rect aktif."""
        label = getattr(self, "lbl_grup_terpin", None)
        group_rows = self._group_row_indices
        if label is None:
            return
        if not group_rows or self.tabel.rowCount() == 0:
            label.hide()
            return

        # rowAt(0) memberi baris yang kini berada pada tepi atas viewport.
        # Bisect menemukan grup aktif tanpa memeriksa seluruh grup pada tiap
        # perubahan scrollbar.
        row_teratas = self.tabel.rowAt(0)
        if row_teratas < 0:
            label.hide()
            return
        group_index = bisect_right(group_rows, row_teratas) - 1
        if group_index < 0:
            label.hide()
            return

        grup_aktif = group_rows[group_index]
        y_grup = self.tabel.rowViewportPosition(grup_aktif)
        # Selama baris header aslinya masih di tepi atas atau di bawahnya,
        # label sticky belum perlu ditampilkan.
        if y_grup >= 0:
            label.hide()
            return

        tinggi_label = max(1, self.tabel.rowHeight(grup_aktif))
        row_total = self.tabel.rowCount() - 1
        row_pendorong = (
            group_rows[group_index + 1]
            if group_index + 1 < len(group_rows)
            else row_total
        )
        y_pendorong = self.tabel.rowViewportPosition(row_pendorong)

        # Label terdorong ke atas saat grup berikutnya (atau total) mendekat.
        y_label = min(0, y_pendorong - tinggi_label)
        lebar_kolom_beku = self.tabel.columnWidth(0) + self.tabel.columnWidth(1)
        lebar_label = max(0, self.tabel.viewport().width() - lebar_kolom_beku)
        judul = self._group_title_by_table_row.get(grup_aktif, "")
        if label.text() != judul:
            label.setText(judul)
        if label.height() != tinggi_label:
            label.setFixedHeight(tinggi_label)
        geo = label.geometry()
        if (geo.x(), geo.y(), geo.width(), geo.height()) != (
            lebar_kolom_beku, y_label, lebar_label, tinggi_label
        ):
            label.setGeometry(
                lebar_kolom_beku,
                y_label,
                lebar_label,
                tinggi_label,
            )

        # Qt mengklip bagian label yang terdorong melewati tepi viewport.
        harus_tampil = lebar_label > 0 and y_label + tinggi_label > 0
        if label.isVisible() != harus_tampil:
            label.setVisible(harus_tampil)
        if harus_tampil:
            label.raise_()

    def set_branch_access_mode(self, mode):
        """Menerima mode akses; MainWindow mengunci editor tabel terpusat."""
        self._branch_access_mode = str(mode or "FULL").strip().upper()

    def showEvent(self, event):
        super().showEvent(event)
        # Saat kembali dari tab Manifest gudang, muat ulang agar manifest baru
        # langsung tercermin pada jumlah manifest, tagihan, dan posisi total bulan.
        self.refresh_session_ui()

    def _style_menu_periode(self, is_dark=False):
        """Pakai tipografi menu yang sama dengan filter Buku Gudang."""
        ukuran = get_fixed_font_sizes()["body_small"]
        style_menu = konversi_style_font_ke_point(
            get_buku_gudang_menu_style(ukuran, is_dark)
        )
        for menu in (self.menu_tahun, self.menu_bulan):
            menu.setStyleSheet(style_menu)
            for action in menu.actions():
                submenu = action.menu()
                if submenu is not None:
                    submenu.setStyleSheet(style_menu)

    def _bangun_menu_tahun(self):
        self.menu_tahun.clear()
        tahun_sekarang = datetime.now().year
        daftar_tahun = list(range(tahun_sekarang, tahun_sekarang - 6, -1))

        # Tiga tahun terbaru tampil langsung, sisanya di submenu "Lainnya...",
        # mengikuti pola menu tahun di Buku Gudang.
        for tahun in daftar_tahun[:3]:
            action = self.menu_tahun.addAction(str(tahun))
            action.triggered.connect(
                lambda checked=False, nilai=tahun: self._ubah_tahun(nilai)
            )

        if len(daftar_tahun) > 3:
            self.menu_tahun.addSeparator()
            submenu = self.menu_tahun.addMenu("Lainnya...")
            # clear() pada refresh membuat submenu baru; wariskan style menu induk.
            submenu.setStyleSheet(self.menu_tahun.styleSheet())
            for tahun in daftar_tahun[3:]:
                action = submenu.addAction(str(tahun))
                action.triggered.connect(
                    lambda checked=False, nilai=tahun: self._ubah_tahun(nilai)
                )

    def _bangun_menu_bulan(self):
        self.menu_bulan.clear()
        for nomor_bulan, nama_bulan in enumerate(NAMA_BULAN, start=1):
            action = self.menu_bulan.addAction(nama_bulan)
            action.triggered.connect(
                lambda checked=False, nilai=nomor_bulan: self._ubah_bulan(nilai)
            )

    def _ubah_tahun(self, tahun):
        self.btn_tahun.setText(str(int(tahun)))
        self._muat_tabel_sesuai_filter()

    def _ubah_bulan(self, bulan):
        nomor_bulan = int(bulan)
        if 1 <= nomor_bulan <= 12:
            self.btn_bulan.setText(NAMA_BULAN[nomor_bulan - 1])
            self._muat_tabel_sesuai_filter()

    def refresh_session_ui(self):
        """Menyegarkan pilihan tahun/bulan dan data tabel."""
        tahun_sekarang = datetime.now().year
        try:
            pilihan_tahun = int(self.btn_tahun.text())
        except (TypeError, ValueError):
            pilihan_tahun = tahun_sekarang
        try:
            pilihan_bulan = NAMA_BULAN.index(self.btn_bulan.text()) + 1
        except ValueError:
            pilihan_bulan = datetime.now().month

        tahun_tersedia = range(tahun_sekarang, tahun_sekarang - 6, -1)
        if pilihan_tahun not in tahun_tersedia:
            pilihan_tahun = tahun_sekarang
        if not 1 <= pilihan_bulan <= 12:
            pilihan_bulan = datetime.now().month

        self._bangun_menu_tahun()
        self._bangun_menu_bulan()
        self.btn_tahun.setText(str(pilihan_tahun))
        self.btn_bulan.setText(NAMA_BULAN[pilihan_bulan - 1])
        self._muat_tabel_sesuai_filter()

    @staticmethod
    def _label_bulan(bulan_key):
        try:
            tahun, bulan = str(bulan_key).split("-", 1)
            return f"{NAMA_BULAN[int(bulan) - 1]} {tahun}"
        except (ValueError, IndexError):
            return str(bulan_key or "")

    @staticmethod
    def _tanggal_panjang(value):
        tanggal = str(value or "").strip()[:10]
        try:
            parsed = datetime.strptime(tanggal, "%Y-%m-%d")
            return f"{parsed.day:02d} {NAMA_BULAN[parsed.month - 1].upper()} {parsed.year}"
        except ValueError:
            return format_tanggal_ke_ui(tanggal) or tanggal

    def _ambil_data_bulan(self, bulan_key):
        if not bulan_key:
            return []
        conn = None
        try:
            conn = db_service.get_db_connection()
            rows = conn.execute(
                """
                SELECT
                    r.no_resi, r.kode_cabang, r.tanggal_keluar, r.truk,
                    COALESCE(r.no_manifest, ''), COALESCE(m.nama_kapal, ''),
                    COALESCE(m.note_manifest, ''), COALESCE(r.pengirim, ''),
                    COALESCE(r.penerima, ''), COALESCE(r.kota_tujuan, ''),
                    COALESCE(r.nama_barang, ''), COALESCE(r.koli, ''),
                    COALESCE(r.berat, 0), COALESCE(r.cbm, 0),
                    COALESCE(NULLIF(r.total_ongkir, 0), NULLIF(r.subtotal_ongkir, 0), 0),
                    COALESCE(k.kode_tagihan, ''), COALESCE(k.kg_m3_manual, ''),
                    COALESCE(k.nomor_invoice_manual, ''),
                    COALESCE(k.payment_mandiri, ''), COALESCE(k.payment_bca, ''),
                    COALESCE(k.sjb, ''),
                    COALESCE((
                        SELECT GROUP_CONCAT(invoice_list.no_invoice, ', ')
                        FROM (
                            SELECT DISTINCT h.no_invoice, h.updated_at, h.id
                            FROM invoice_resi ir
                            JOIN invoice_header h ON h.no_invoice = ir.no_invoice
                            WHERE UPPER(ir.no_resi) = UPPER(r.no_resi)
                            ORDER BY h.updated_at DESC, h.id DESC
                        ) AS invoice_list
                    ), '') AS invoice_terkait
                FROM data_resi r
                LEFT JOIN manifest m
                  ON m.id_manifest = r.no_manifest
                 AND m.kode_cabang = r.kode_cabang
                LEFT JOIN manifest_penagihan_detail k
                  ON k.no_resi = r.no_resi AND k.kode_cabang = r.kode_cabang
                WHERE r.kode_cabang = ?
                  AND substr(COALESCE(r.tanggal_keluar, ''), 1, 7) = ?
                  AND COALESCE(TRIM(r.deleted_at), '') = ''
                  AND COALESCE(TRIM(r.no_manifest), '') <> ''
                ORDER BY r.tanggal_keluar ASC, r.no_manifest ASC, r.no_resi ASC
                """,
                (self._kode_cabang_aktif(), str(bulan_key)),
            ).fetchall()
            hasil = []
            for row in rows:
                hasil.append({
                    "no_resi": str(row[0] or "").strip(),
                    "kode_cabang": str(row[1] or "").strip().upper(),
                    "tanggal_keluar": str(row[2] or "").strip(),
                    "truk": str(row[3] or "").strip(),
                    "no_manifest": str(row[4] or "").strip(),
                    "nama_kapal": str(row[5] or "").strip(),
                    "note_manifest": str(row[6] or "").strip(),
                    "pengirim": str(row[7] or "").strip(),
                    "penerima": str(row[8] or "").strip(),
                    "tujuan": str(row[9] or "").strip(),
                    "jenis_paket": str(row[10] or "").strip(),
                    "koli": str(row[11] or "").strip(),
                    "berat": row[12] or 0,
                    "cbm": row[13] or 0,
                    "tagihan": row[14] or 0,
                    "kode_tagihan": str(row[15] or "").strip(),
                    "kg_m3_manual": str(row[16] or "").strip(),
                    "nomor_invoice_manual": str(row[17] or "").strip(),
                    "payment_mandiri": str(row[18] or "").strip(),
                    "payment_bca": str(row[19] or "").strip(),
                    "sjb": str(row[20] or "").strip(),
                    "invoice_terkait": str(row[21] or "").strip(),
                })
            return hasil
        except sqlite3.Error as exc:
            self._tampilkan_error_db("Gagal memuat data rekap tagihan", exc)
            return []
        finally:
            if conn is not None:
                conn.close()

    def _bulan_key_terpilih(self):
        """Menggabungkan dropdown tahun dan bulan menjadi kunci YYYY-MM."""
        try:
            tahun = int(self.btn_tahun.text())
            bulan = NAMA_BULAN.index(self.btn_bulan.text()) + 1
            return f"{tahun:04d}-{bulan:02d}"
        except (TypeError, ValueError):
            return None

    def _muat_tabel_sesuai_filter(self, *_args):
        if not hasattr(self, "tabel"):
            return
        if self._scroll_halus is not None:
            self._scroll_halus.hentikan_semua()
        bulan_key = self._bulan_key_terpilih()
        data = self._ambil_data_bulan(bulan_key)
        self._groups = []
        for row in data:
            key = (row["tanggal_keluar"], row["no_manifest"])
            if not self._groups or self._groups[-1]["key"] != key:
                self._groups.append({
                    "key": key,
                    "tanggal_keluar": row["tanggal_keluar"],
                    "no_manifest": row["no_manifest"],
                    "truk": row["truk"],
                    "nama_kapal": row["nama_kapal"],
                    "note_manifest": row["note_manifest"],
                    "items": [],
                })
            self._groups[-1]["items"].append(row)

        self._sedang_memuat = True
        self.tabel.blockSignals(True)
        try:
            self.tabel.clearSpans()
            self.tabel.clearContents()
            self.tabel.setRowCount(0)
            self._row_resi_by_table_row.clear()
            self._table_row_by_resi.clear()
            self._group_title_by_table_row.clear()
            self._group_row_indices.clear()
            jumlah_resi = 0
            total_tagihan = Decimal(0)
            for group in self._groups:
                row_group = self.tabel.rowCount()
                self.tabel.insertRow(row_group)
                judul = self._judul_grup(group)
                self._group_title_by_table_row[row_group] = judul
                self._group_row_indices.append(row_group)
                # Dua kolom beku dibiarkan kosong; judul grup berada pada
                # area tabel yang dapat digulir dan versi lengkapnya tetap
                # tampil pada label grup terpin di atas tabel.
                for column in range(2):
                    spacer = QTableWidgetItem("")
                    spacer.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    spacer.setBackground(QColor(WARNA_GRUP))
                    self.tabel.setItem(row_group, column, spacer)
                self.tabel.setSpan(row_group, 0, 1, 2)

                item_judul = QTableWidgetItem(judul)
                item_judul.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item_judul.setBackground(QColor(WARNA_GRUP))
                item_judul.setForeground(QColor("#202020"))
                font = QFont(item_judul.font())
                font.setWeight(QFont.Weight(_FONT_WEIGHTS["bold"]))
                item_judul.setFont(font)
                item_judul.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.tabel.setItem(row_group, 2, item_judul)
                for column in range(3, len(KOLOM)):
                    spacer = QTableWidgetItem("")
                    spacer.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    spacer.setBackground(QColor(WARNA_GRUP))
                    self.tabel.setItem(row_group, column, spacer)
                self.tabel.setSpan(row_group, 2, 1, len(KOLOM) - 2)

                for item_data in group["items"]:
                    row_index = self.tabel.rowCount()
                    self.tabel.insertRow(row_index)
                    self._row_resi_by_table_row[row_index] = item_data["no_resi"]
                    self._table_row_by_resi[item_data["no_resi"]] = row_index
                    nilai_kg_m3 = self._kg_m3_tampilan(item_data)
                    nilai_invoice = item_data["nomor_invoice_manual"] or item_data["invoice_terkait"]
                    nominal = self._angka_tagihan(item_data["tagihan"])
                    values = (
                        item_data["no_manifest"],
                        item_data["no_resi"],
                        item_data["pengirim"],
                        item_data["penerima"],
                        item_data["tujuan"],
                        item_data["jenis_paket"],
                        item_data["koli"],
                        nilai_kg_m3,
                        f"Rp {format_ke_rupiah(int(nominal))}" if nominal else "Rp 0",
                        nilai_invoice,
                        item_data["payment_mandiri"],
                        item_data["payment_bca"],
                        item_data["sjb"],
                    )
                    for column, value in enumerate(values):
                        cell = QTableWidgetItem(str(value or ""))
                        cell.setBackground(QColor(WARNA_BARIS[(jumlah_resi % 2)]))
                        cell.setForeground(QColor("#202020"))
                        cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                        if column in KOLOM_DATA_PENAGIHAN:
                            cell.setFlags(cell.flags() | Qt.ItemFlag.ItemIsEditable)
                            cell.setToolTip("Klik dua kali untuk mengubah nilai ini.")
                        if column in (6, 7, 8):
                            cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        elif column in (0, 1) or column >= 9:
                            cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                        else:
                            cell.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                        if column == 8:
                            cell.setData(Qt.ItemDataRole.UserRole, int(nominal))
                        if column == 1:
                            cell.setData(Qt.ItemDataRole.UserRole, item_data["no_resi"])
                        self.tabel.setItem(row_index, column, cell)
                    jumlah_resi += 1
                    total_tagihan += nominal

            # Baris rekap selalu ditambahkan setelah kelompok manifest terakhir,
            # sehingga posisinya otomatis bergeser ketika ada manifest/resi baru.
            self._tambahkan_baris_total(jumlah_manifest=len(self._groups),
                                        jumlah_resi=jumlah_resi,
                                        total_tagihan=total_tagihan)
        finally:
            self.tabel.blockSignals(False)
            self._sedang_memuat = False

        jumlah_manifest = len(self._groups)
        jumlah_resi_label = format(jumlah_resi, ",").replace(",", ".")
        # Nama bulan sudah ditampilkan pada combobox, jadi tidak perlu diulang.
        self.lbl_ringkasan.setText(
            f"{jumlah_manifest} manifest · {jumlah_resi_label} resi · "
            f"Total tagihan: Rp {format_ke_rupiah(int(total_tagihan))}"
        )
        self.tabel.verticalHeader().setDefaultSectionSize(27)
        self._refresh_tabel_terpin()

    def _tambahkan_baris_total(self, jumlah_manifest, jumlah_resi, total_tagihan):
        """Menambahkan total transaksi setelah seluruh baris manifest pada bulan aktif."""
        row_total = self.tabel.rowCount()
        self.tabel.insertRow(row_total)

        jumlah_manifest_label = format(jumlah_manifest, ",").replace(",", ".")
        jumlah_resi_label = format(jumlah_resi, ",").replace(",", ".")
        label = f"TOTAL TRANSAKSI  |  {jumlah_manifest_label} MANIFEST  |  {jumlah_resi_label} RESI"

        # Sisakan KODE dan RESI sebagai area kolom beku; teks total dimulai
        # setelahnya supaya tidak terpotong oleh overlay kolom terpin.
        for column in range(2):
            item_kosong_kiri = QTableWidgetItem("")
            item_kosong_kiri.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_kosong_kiri.setBackground(QColor(WARNA_TOTAL))
            self.tabel.setItem(row_total, column, item_kosong_kiri)
        self.tabel.setSpan(row_total, 0, 1, 2)

        item_label = QTableWidgetItem(label)
        item_label.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item_label.setBackground(QColor(WARNA_TOTAL))
        item_label.setForeground(QColor("#202020"))
        font = QFont(item_label.font())
        font.setWeight(QFont.Weight(_FONT_WEIGHTS["bold"]))
        item_label.setFont(font)
        item_label.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.tabel.setItem(row_total, 2, item_label)
        self.tabel.setSpan(row_total, 2, 1, 6)

        nilai_total = self._angka_tagihan(total_tagihan)
        item_nominal = QTableWidgetItem(f"Rp {format_ke_rupiah(int(nilai_total))}")
        item_nominal.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item_nominal.setBackground(QColor(WARNA_TOTAL))
        item_nominal.setForeground(QColor("#202020"))
        font_nominal = QFont(item_nominal.font())
        font_nominal.setWeight(QFont.Weight(_FONT_WEIGHTS["bold"]))
        item_nominal.setFont(font_nominal)
        item_nominal.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item_nominal.setData(Qt.ItemDataRole.UserRole, int(nilai_total))
        self.tabel.setItem(row_total, 8, item_nominal)

        item_kosong = QTableWidgetItem("")
        item_kosong.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item_kosong.setBackground(QColor(WARNA_TOTAL))
        self.tabel.setItem(row_total, 9, item_kosong)
        for column in range(10, len(KOLOM)):
            item_kosong_lain = QTableWidgetItem("")
            item_kosong_lain.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_kosong_lain.setBackground(QColor(WARNA_TOTAL))
            self.tabel.setItem(row_total, column, item_kosong_lain)
        self.tabel.setSpan(row_total, 9, 1, len(KOLOM) - 9)

    def _judul_grup(self, group):
        """Judul satu keberangkatan, termasuk kapal, armada, tanggal, nomor, dan jumlah resi."""
        bagian = []
        nama_kapal = str(group.get("nama_kapal") or "").strip()
        truk = str(group.get("truk") or "").strip()
        note = str(group.get("note_manifest") or "").strip()

        # Sesuaikan urutan dengan lembar kerja admin penagihan: kapal lebih dahulu,
        # dilanjutkan detail truk (jenis, nopol, sopir, dan keterangan).
        if nama_kapal:
            bagian.append(nama_kapal)
        if truk and (not note or truk.upper() != note.upper()):
            bagian.append(truk)
        elif note:
            bagian.append(note)
        if not bagian:
            bagian.append("KEBERANGKATAN")

        tanggal = self._tanggal_panjang(group.get("tanggal_keluar"))
        if tanggal:
            bagian.append(tanggal)
        no_manifest = str(group.get("no_manifest") or "").strip()
        if no_manifest:
            bagian.append(no_manifest)
        jumlah_resi = len(group.get("items") or [])
        judul = " - ".join(bagian)
        return f"{judul} ({format(jumlah_resi, ',').replace(',', '.')} resi)"

    @staticmethod
    def _angka_tagihan(value):
        try:
            return Decimal(str(value or 0))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal(0)

    @staticmethod
    def _format_angka(value, maksimum_desimal=3):
        try:
            number = Decimal(str(value or 0))
        except (InvalidOperation, ValueError, TypeError):
            return str(value or "")
        formatted = f"{number:,.{maksimum_desimal}f}".rstrip("0").rstrip(".")
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")

    def _kg_m3_tampilan(self, row):
        manual = str(row.get("kg_m3_manual") or "").strip()
        if manual:
            return manual
        try:
            berat = Decimal(str(row.get("berat") or 0))
        except (InvalidOperation, ValueError, TypeError):
            berat = Decimal(0)
        try:
            cbm = Decimal(str(row.get("cbm") or 0))
        except (InvalidOperation, ValueError, TypeError):
            cbm = Decimal(0)
        parts = []
        if berat > 0:
            parts.append(f"{self._format_angka(berat)} KG")
        if cbm > 0:
            parts.append(f"{self._format_angka(cbm)} M3")
        return " / ".join(parts)

    def _simpan_perubahan_sel(self, item):
        if self._sedang_memuat or item is None:
            return
        row_index = item.row()
        no_resi = self._row_resi_by_table_row.get(row_index)
        column = item.column()
        field = KOLOM_DATA_PENAGIHAN.get(column)
        if not no_resi or not field:
            return
        if self._branch_access_mode in {"VIEW", "VIEW ONLY", "VIEW_ONLY"}:
            self._muat_tabel_sesuai_filter()
            return

        nilai = item.text().strip()
        try:
            self._upsert_detail_penagihan(no_resi, field, nilai)
            item.setBackground(QColor("#C6E0B4"))
            item.setToolTip("Tersimpan pada rekap penagihan.")
        except (sqlite3.Error, PermissionError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Gagal menyimpan rekap penagihan",
                f"Perubahan untuk resi {no_resi} tidak tersimpan.\n\n{exc}",
            )
            self._muat_tabel_sesuai_filter()

    def _upsert_detail_penagihan(self, no_resi, field, value):
        if field not in set(KOLOM_DATA_PENAGIHAN.values()):
            raise ValueError("Kolom rekap penagihan tidak dikenal.")
        kode_cabang = self._kode_cabang_aktif()
        conn = None
        try:
            conn = db_service.get_db_connection()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                f"""
                INSERT INTO manifest_penagihan_detail (
                    kode_cabang, no_resi, {field}, updated_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(kode_cabang, no_resi) DO UPDATE SET
                    {field} = excluded.{field}, updated_at = CURRENT_TIMESTAMP
                """,
                (kode_cabang, no_resi, value),
            )
            conn.commit()
        except Exception:
            if conn is not None and conn.in_transaction:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def ekspor_excel(self):
        bulan_key = self._bulan_key_terpilih()
        if not bulan_key or not self._groups:
            QMessageBox.information(self, "Ekspor Excel", "Tidak ada data untuk diekspor.")
            return
        label_bulan = self._label_bulan(bulan_key)
        nama_default = f"Manifest Penagihan - {label_bulan}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan Rekap Manifest Penagihan",
            nama_default,
            "Excel Workbook (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
            from openpyxl.utils import get_column_letter

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = re.sub(r"[\\/*?:\[\]]", "-", label_bulan)[:31] or "Rekap"
            fill_header = PatternFill("solid", fgColor="F4C7F3")
            fill_group = PatternFill("solid", fgColor="DDEBF7")
            fill_even = PatternFill("solid", fgColor="D9EAD3")
            fill_odd = PatternFill("solid", fgColor="E2F0D9")
            fill_total = PatternFill("solid", fgColor="FFF2CC")
            thin_grey = Side(style="thin", color="9A9A9A")
            border = Border(left=thin_grey, right=thin_grey, top=thin_grey, bottom=thin_grey)

            # Ringkasan bulan pada bagian atas ekspor, lalu header tabel.
            total_bulan_hint = sum(
                self._angka_tagihan(item.get("tagihan"))
                for group in self._groups for item in group["items"]
            )
            sheet.append([
                f"{label_bulan}: {len(self._groups)} manifest · "
                f"Total tagihan: Rp {format_ke_rupiah(int(total_bulan_hint))}"
            ])
            sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(KOLOM))
            summary_cell = sheet.cell(1, 1)
            summary_cell.fill = fill_group
            summary_cell.font = Font(bold=True, color="202020")
            summary_cell.alignment = Alignment(horizontal="left", vertical="center")
            for col in range(1, len(KOLOM) + 1):
                sheet.cell(1, col).fill = fill_group
                sheet.cell(1, col).border = border
            sheet.row_dimensions[1].height = 24

            sheet.append(list(KOLOM))
            for cell in sheet[2]:
                cell.fill = fill_header
                cell.font = Font(bold=True, color="202020")
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = border
            sheet.row_dimensions[2].height = 24

            jumlah_resi = 0
            total_tagihan = Decimal(0)
            for group in self._groups:
                start_row = sheet.max_row + 1
                sheet.append([self._judul_grup(group)] + [None] * (len(KOLOM) - 1))
                sheet.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=len(KOLOM))
                group_cell = sheet.cell(start_row, 1)
                group_cell.fill = fill_group
                group_cell.font = Font(bold=True, color="202020")
                group_cell.alignment = Alignment(horizontal="left", vertical="center")
                for col in range(1, len(KOLOM) + 1):
                    sheet.cell(start_row, col).fill = fill_group
                    sheet.cell(start_row, col).border = border

                for row_data in group["items"]:
                    jumlah_resi += 1
                    row_values = []
                    for col in range(len(KOLOM)):
                        item = self._cari_item_tabel(row_data["no_resi"], col)
                        text_value = item.text() if item is not None else ""
                        if col == 8:
                            raw_amount = item.data(Qt.ItemDataRole.UserRole) if item is not None else 0
                            try:
                                amount = Decimal(str(raw_amount or 0))
                            except (InvalidOperation, ValueError, TypeError):
                                amount = Decimal(0)
                            row_values.append(int(amount) if amount == amount.to_integral_value() else float(amount))
                            total_tagihan += amount
                        else:
                            row_values.append(text_value)
                    sheet.append(row_values)
                    sheet_row = sheet.max_row
                    fill = fill_even if jumlah_resi % 2 else fill_odd
                    for cell in sheet[sheet_row]:
                        cell.fill = fill
                        cell.border = border
                        cell.font = Font(color="202020")
                        cell.alignment = Alignment(vertical="center", wrap_text=False)
                    sheet.cell(sheet_row, 8).number_format = '@'
                    sheet.cell(sheet_row, 9).number_format = '"Rp" #,##0'

            sheet.append([
                f"TOTAL TRANSAKSI | {len(self._groups)} MANIFEST | {jumlah_resi} RESI",
                "", "", "", "", "", "", "", int(total_tagihan), "", "", "", "",
            ])
            total_row = sheet.max_row
            sheet.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=8)
            sheet.merge_cells(start_row=total_row, start_column=10, end_row=total_row, end_column=len(KOLOM))
            for cell in sheet[total_row]:
                cell.fill = fill_total
                cell.font = Font(bold=True, color="202020")
                cell.border = border
                cell.alignment = Alignment(vertical="center")
            sheet.cell(total_row, 9).number_format = '"Rp" #,##0'

            widths = (12, 18, 32, 32, 22, 32, 12, 18, 20, 26, 18, 18, 18)
            for index, width in enumerate(widths, start=1):
                sheet.column_dimensions[get_column_letter(index)].width = width
            sheet.freeze_panes = "A3"
            sheet.sheet_view.showGridLines = False
            workbook.save(path)
            QMessageBox.information(self, "Ekspor Excel", f"Rekap berhasil diekspor ke:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ekspor Excel gagal", str(exc))

    def _cari_item_tabel(self, no_resi, column):
        row = self._table_row_by_resi.get(no_resi)
        return self.tabel.item(row, column) if row is not None else None

    def _tampilkan_error_db(self, judul, exc):
        QMessageBox.warning(self, judul, str(exc))
