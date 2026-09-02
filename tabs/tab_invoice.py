# tabs/tab_invoice.py
import html
import json
import re

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from PySide6.QtCore import (
    QDate,
    QMarginsF,
    QSettings,
    QSize,
    QSizeF,
    Qt,
    Signal,
)
from PySide6.QtGui import QKeySequence, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION, muat_pengaturan_sistem
import services.database_service as db_service

from themes.modules.invoice import get_invoice_dialog_styles, get_invoice_styles
from themes.components.calendar import terapkan_style_kalender

from utils.splitter_helper import buat_splitter
from utils.typography import (
    get_global_font_sizes,
    konversi_style_font_ke_point,
)
from utils.printer.print_invoice import tampilkan_preview_invoice, simpan_invoice_pdf
from utils import zoom as zoom_helper
from utils.ui_metrics import skalakan_px
from utils.number_formatters import (
    rupiah_to_int,
    format_ke_rupiah,
    ambil_angka_dari_teks
)
from utils.table_helper import buat_tabel_item
from utils.reset_form_helper import reset_form_input_global
from utils.validators import UppercaseValidator
from utils.mixins import ZoomTableMixin
from utils.widget_helpers import atur_tinggi_input, blokir_signal_sementara

# KONFIGURASI TEMPLATE
INVOICE_TEMPLATES = {
    "Standar": {
        "version": 3,
        "layout": "standard",
        "amount_key": "amount",
        "columns": [
            {
                "key": "no",
                "title": "NO",
                "type": "integer",
                "width": 45,
            },
            {
                "key": "resi",
                "title": "RESI",
                "type": "text",
                "width": 105,
            },
            {
                "key": "destination",
                "title": "TUJUAN",
                "type": "text",
                "width": 135,
            },
            {
                "key": "description",
                "title": "NAMA BARANG",
                "type": "text",
                "width": 210,
                "stretch": True,
            },
            {
                "key": "package",
                "title": "KOLI",
                "type": "decimal",
                "width": 65,
            },
            {
                "key": "weight",
                "title": "BERAT (KG)",
                "type": "decimal",
                "width": 85,
            },
            {
                "key": "volume",
                "title": "KUBIK (M³)",
                "type": "decimal",
                "width": 90,
            },
            {
                "key": "amount",
                "title": "ONGKIR (Rp)",
                "type": "currency",
                "width": 125,
            },
        ],
    },
    "Logistik Berat": {
        "version": 2,
        "layout": "logistics",
        "amount_key": "amount",
        "columns": [
            {"key": "no", "title": "NO", "type": "integer", "width": 48},
            {"key": "resi", "title": "RESI", "type": "text", "width": 95},
            {"key": "destination", "title": "TUJUAN", "type": "text", "width": 145},
            {"key": "po_number", "title": "NO. PO", "type": "text", "width": 95},
            {
                "key": "description",
                "title": "JENIS BARANG",
                "type": "text",
                "width": 210,
                "stretch": True,
            },
            {"key": "package", "title": "KOLI", "type": "decimal", "width": 70},
            {"key": "weight", "title": "BERAT", "type": "text", "width": 90},
            {"key": "tariff", "title": "TARIF (Rp)", "type": "currency", "width": 105},
            {"key": "amount", "title": "RUPIAH", "type": "currency", "width": 130},
        ],
    },
    "Ritel Samarinda": {
        "version": 2,
        "layout": "bill_ship",
        "amount_key": "amount",
        "formula": {
            "operation": "multiply",
            "sources": ["package", "price"],
            "target": "amount",
        },
        "columns": [
            {"key": "resi", "title": "RESI", "type": "text", "width": 85},
            {
                "key": "description",
                "title": "DESCRIPTION",
                "type": "text",
                "width": 310,
                "stretch": True,
            },
            {"key": "package", "title": "KOLI", "type": "decimal", "width": 72},
            {"key": "ship_date", "title": "TGL KAPAL", "type": "date", "width": 105},
            {"key": "price", "title": "PRICE", "type": "currency", "width": 110},
            {"key": "amount", "title": "AMOUNT", "type": "currency", "width": 135},
        ],
    },
    "Proyek Batangan": {
        "version": 2,
        "layout": "bill_ship",
        "amount_key": "amount",
        "columns": [
            {"key": "resi", "title": "RESI", "type": "text", "width": 105},
            {
                "key": "description",
                "title": "DESCRIPTION",
                "type": "text",
                "width": 430,
                "stretch": True,
            },
            {"key": "quantity", "title": "QTY", "type": "text", "width": 85},
            {"key": "destination", "title": "TUJUAN", "type": "text", "width": 170},
            {"key": "amount", "title": "AMOUNT", "type": "currency", "width": 145},
        ],
    },
    "Custom / Bebas": {
        "version": 2,
        "layout": "bill_ship",
        "amount_key": "amount",
        "columns": [
            {"key": "resi", "title": "RESI", "type": "text", "width": 110},
            {
                "key": "description",
                "title": "DESCRIPTION",
                "type": "text",
                "width": 360,
                "stretch": True,
            },
            {"key": "quantity", "title": "QTY", "type": "text", "width": 80},
            {"key": "weight", "title": "BERAT", "type": "text", "width": 90},
            {"key": "tariff", "title": "TARIF", "type": "currency", "width": 110},
            {"key": "amount", "title": "AMOUNT", "type": "currency", "width": 140},
        ],
    },
}

# SPREADSHEET EDITOR

class InvoiceSheet(QTableWidget):
    sheetEdited = Signal()

    def setItem(self, row, column, item):
        """Pastikan item baru mengikuti font tabel yang sedang aktif."""
        if item is not None:
            item.setFont(self.font())
        super().setItem(row, column, item)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.verticalHeader().setDefaultSectionSize(28)
        self.verticalHeader().setMinimumSectionSize(24)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_selection()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            self.copy_selection()
            self.clear_selected_cells()
            return
        if event.matches(QKeySequence.StandardKey.Delete):
            self.clear_selected_cells()
            return
        if event.key() == Qt.Key.Key_Insert:
            self.insert_row_below()
            return
        super().keyPressEvent(event)

    def copy_selection(self):
        ranges = self.selectedRanges()
        if not ranges:
            return

        selected_range = ranges[0]
        lines = []
        for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
            values = []
            for column in range(
                selected_range.leftColumn(),
                selected_range.rightColumn() + 1,
            ):
                item = self.item(row, column)
                values.append(item.text() if item else "")
            lines.append("\t".join(values))
        QApplication.clipboard().setText("\n".join(lines))

    def paste_selection(self):
        text = QApplication.clipboard().text()
        if not text:
            return

        start_row = max(self.currentRow(), 0)
        start_column = max(self.currentColumn(), 0)
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if lines and lines[-1] == "":
            lines.pop()

        with blokir_signal_sementara(self):
            for row_offset, line in enumerate(lines):
                target_row = start_row + row_offset
                while target_row >= self.rowCount():
                    self.insertRow(self.rowCount())

                values = line.split("\t")
                for column_offset, value in enumerate(values):
                    target_column = start_column + column_offset
                    if target_column >= self.columnCount():
                        break
                    self.setItem(
                        target_row,
                        target_column,
                        buat_tabel_item(value.strip()),
                    )

        self.sheetEdited.emit()

    def clear_selected_cells(self):
        selected = self.selectedItems()
        if not selected:
            return
        with blokir_signal_sementara(self):
            for item in selected:
                item.setText("")
        self.sheetEdited.emit()

    def insert_blank_row(self, row=None):
        if row is None:
            row = self.rowCount()
        row = max(0, min(row, self.rowCount()))
        self.insertRow(row)
        self.setCurrentCell(row, 0)
        self.sheetEdited.emit()

    def insert_row_above(self):
        row = self.currentRow()
        self.insert_blank_row(0 if row < 0 else row)

    def insert_row_below(self):
        row = self.currentRow()
        self.insert_blank_row(self.rowCount() if row < 0 else row + 1)

    def delete_selected_rows(self):
        rows = sorted({index.row() for index in self.selectedIndexes()}, reverse=True)
        if not rows and self.currentRow() >= 0:
            rows = [self.currentRow()]
        if not rows:
            return

        with blokir_signal_sementara(self):
            for row in rows:
                self.removeRow(row)

        if self.rowCount() == 0:
            self.insertRow(0)
        self.sheetEdited.emit()

    def _row_values(self, row, missing_alignment=0):
        values = []
        for column in range(self.columnCount()):
            item = self.item(row, column)
            values.append((
                item.text() if item else "",
                item.textAlignment() if item else missing_alignment,
            ))
        return values

    def _set_row_values(self, row, values):
        for column, (value, alignment) in enumerate(values):
            self.setItem(row, column, buat_tabel_item(value, alignment=alignment))

    def duplicate_current_row(self):
        source_row = self.currentRow()
        if source_row < 0:
            return
        target_row = source_row + 1
        with blokir_signal_sementara(self):
            values = self._row_values(source_row, Qt.AlignmentFlag.AlignLeft)
            self.insertRow(target_row)
            self._set_row_values(target_row, values)
        self.setCurrentCell(target_row, 0)
        self.sheetEdited.emit()

    def move_current_row(self, offset):
        source_row = self.currentRow()
        if source_row < 0:
            return
        target_row = source_row + offset
        if target_row < 0 or target_row >= self.rowCount():
            return

        with blokir_signal_sementara(self):
            source_values = self._row_values(source_row)
            target_values = self._row_values(target_row)
            self._set_row_values(source_row, target_values)
            self._set_row_values(target_row, source_values)

        self.setCurrentCell(target_row, max(self.currentColumn(), 0))
        self.sheetEdited.emit()

    def clear_all_rows(self):
        with blokir_signal_sementara(self):
            self.setRowCount(1)
            for column in range(self.columnCount()):
                self.setItem(0, column, buat_tabel_item(""))
        self.setCurrentCell(0, 0)
        self.sheetEdited.emit()

    def _show_context_menu(self, position):
        menu = QMenu(self)
        act_insert_above = menu.addAction("Tambah Baris di Atas")
        act_insert_below = menu.addAction("Tambah Baris di Bawah")
        act_duplicate = menu.addAction("Duplikat Baris")
        menu.addSeparator()
        act_copy = menu.addAction("Salin")
        act_paste = menu.addAction("Tempel")
        act_clear = menu.addAction("Kosongkan Sel")
        menu.addSeparator()
        act_delete = menu.addAction("Hapus Baris")

        selected = menu.exec(self.viewport().mapToGlobal(position))
        if selected == act_insert_above:
            self.insert_row_above()
        elif selected == act_insert_below:
            self.insert_row_below()
        elif selected == act_duplicate:
            self.duplicate_current_row()
        elif selected == act_copy:
            self.copy_selection()
        elif selected == act_paste:
            self.paste_selection()
        elif selected == act_clear:
            self.clear_selected_cells()
        elif selected == act_delete:
            self.delete_selected_rows()

# DIALOG PENGATURAN KOLOM

class ColumnDesignerDialog(QDialog):
    """Pengaturan kolom Invoice versi ramah pengguna."""

    FORMAT_LABEL_TO_TYPE = {
        "Teks": "text",
        "Angka Bulat": "integer",
        "Angka Desimal": "decimal",
        "Rupiah": "currency",
        "Tanggal": "date",
    }
    TYPE_TO_FORMAT_LABEL = {
        value: key for key, value in FORMAT_LABEL_TO_TYPE.items()
    }

    SIZE_LABEL_TO_WIDTH = {
        "Kecil": 70,
        "Sedang": 110,
        "Lebar": 200,
        "Sangat Lebar": 360,
    }

    COLUMN_PRESETS = [
        ("NOMOR", "no", "integer", 70),
        ("RESI", "resi", "text", 110),
        ("TUJUAN", "destination", "text", 200),
        ("NAMA BARANG", "description", "text", 360),
        ("KOLI", "package", "decimal", 70),
        ("QTY", "quantity", "decimal", 70),
        ("BERAT", "weight", "decimal", 110),
        ("KUBIK", "volume", "decimal", 110),
        ("TARIF", "tariff", "currency", 110),
        ("ONGKIR", "amount", "currency", 140),
        ("KETERANGAN", "notes", "text", 360),
        ("TANGGAL KAPAL", "ship_date", "date", 110),
        ("NOMOR PO", "po_number", "text", 110),
    ]

    def __init__(self, columns, amount_key, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Atur Tampilan Kolom Invoice")
        self.resize(760, 480)
        self.result_columns = None
        self.result_amount_key = None
        self.initial_columns = deepcopy(columns or [])
        self.initial_amount_key = str(amount_key or "").strip()

        layout = QVBoxLayout(self)
        ukuran_dialog = get_global_font_sizes(0)
        style_dialog = konversi_style_font_ke_point(
            get_invoice_dialog_styles(ukuran_dialog["sz_total"])
        )
        title = QLabel("Susun Kolom yang Ditampilkan pada Invoice")
        title.setStyleSheet(style_dialog["title"])
        layout.addWidget(title)

        info = QLabel(
            "Ubah nama kolom bila diperlukan, lalu pilih format isi dan "
            "ukurannya. Pilih <b>Ya</b> pada satu kolom Rupiah yang akan "
            "dijumlahkan sebagai subtotal."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["NAMA KOLOM", "FORMAT ISI", "UKURAN KOLOM", "MASUK TOTAL"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table)
        self._load_columns(self.initial_columns, self.initial_amount_key)

        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("+ Tambah Kolom")
        self.btn_remove = QPushButton("Hapus")
        self.btn_up = QPushButton("Naik")
        self.btn_down = QPushButton("Turun")
        self.btn_restore = QPushButton("Pulihkan Susunan Awal")
        for button in (self.btn_add, self.btn_remove, self.btn_up, self.btn_down):
            toolbar.addWidget(button)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_restore)
        layout.addLayout(toolbar)

        actions = QHBoxLayout()
        actions.addStretch()
        btn_cancel = QPushButton("Batal")
        btn_ok = QPushButton("Terapkan")
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_ok)
        layout.addLayout(actions)

        self._setup_add_menu()
        self.btn_remove.clicked.connect(self._remove_current_row)
        self.btn_up.clicked.connect(lambda: self._move_row(-1))
        self.btn_down.clicked.connect(lambda: self._move_row(1))
        self.btn_restore.clicked.connect(self._restore_initial_columns)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._validate_and_accept)

    def _setup_add_menu(self):
        menu = QMenu(self)
        for title, key, data_type, width in self.COLUMN_PRESETS:
            action = menu.addAction(title)
            action.triggered.connect(
                lambda _checked=False, preset=(title, key, data_type, width):
                self._add_preset(preset)
            )
        menu.addSeparator()
        custom_action = menu.addAction("KOLOM LAINNYA...")
        custom_action.triggered.connect(self._add_custom_column)
        self.btn_add.setMenu(menu)

    @staticmethod
    def _slug_key(value):
        value = str(value or "").strip().lower()
        value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
        return value or "kolom"

    @classmethod
    def _size_label_from_width(cls, width):
        try:
            width = int(width)
        except (TypeError, ValueError):
            width = 110
        return min(
            cls.SIZE_LABEL_TO_WIDTH,
            key=lambda label: abs(cls.SIZE_LABEL_TO_WIDTH[label] - width),
        )

    def _load_columns(self, columns, amount_key):
        self.table.setRowCount(0)
        for column in columns or []:
            self._append_row(
                title=column.get("title", ""),
                key=column.get("key", ""),
                data_type=column.get("type", "text"),
                width=column.get("width", 110),
                is_amount=column.get("key") == amount_key,
            )
        if self.table.rowCount() == 0:
            self._append_row("KETERANGAN", "description", "text", 360, False)
            self._append_row("JUMLAH", "amount", "currency", 140, True)

    @staticmethod
    def _buat_combo_dialog(items, current):
        combo = QComboBox()
        combo.addItems(list(items))
        combo.setCurrentText(current)
        atur_tinggi_input(combo)
        return combo

    def _pasang_row(self, row, title, key, data_type, width, is_amount):
        title_item = buat_tabel_item(str(title or "KOLOM BARU").strip().upper())
        title_item.setData(Qt.ItemDataRole.UserRole, str(key or "").strip())
        self.table.setItem(row, 0, title_item)

        format_combo = self._buat_combo_dialog(
            self.FORMAT_LABEL_TO_TYPE.keys(),
            self.TYPE_TO_FORMAT_LABEL.get(data_type, "Teks"),
        )
        size_combo = self._buat_combo_dialog(
            self.SIZE_LABEL_TO_WIDTH.keys(),
            self._size_label_from_width(width),
        )
        total_combo = self._buat_combo_dialog(
            ("Tidak", "Ya"),
            "Ya" if is_amount else "Tidak",
        )
        total_combo.currentTextChanged.connect(
            lambda value, combo=total_combo: self._handle_total_changed(combo, value)
        )

        self.table.setCellWidget(row, 1, format_combo)
        self.table.setCellWidget(row, 2, size_combo)
        self.table.setCellWidget(row, 3, total_combo)

    def _append_row(self, title, key, data_type, width, is_amount):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._pasang_row(row, title, key, data_type, width, is_amount)
        self.table.setCurrentCell(row, 0)

    def _find_widget_row(self, widget, column):
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, column) is widget:
                return row
        return -1

    def _handle_total_changed(self, source_combo, value):
        if str(value).strip().lower() != "ya":
            return
        source_row = self._find_widget_row(source_combo, 3)
        if source_row < 0:
            return
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 3)
            if combo is None or combo is source_combo:
                continue
            with blokir_signal_sementara(combo):
                combo.setCurrentText("Tidak")
        format_combo = self.table.cellWidget(source_row, 1)
        if format_combo:
            format_combo.setCurrentText("Rupiah")

    def _existing_key_row(self, key):
        normalized_key = str(key or "").strip()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            row_key = str(item.data(
                Qt.ItemDataRole.UserRole,
            ) or "").strip() if item else ""
            if row_key == normalized_key:
                return row
        return -1

    def _add_preset(self, preset):
        title, key, data_type, width = preset
        existing_row = self._existing_key_row(key)
        if existing_row >= 0:
            self.table.setCurrentCell(existing_row, 0)
            QMessageBox.information(
                self,
                "Kolom Sudah Ada",
                f"Kolom {title} sudah terdapat pada susunan invoice.",
            )
            return
        self._append_row(title, key, data_type, width, key == "amount")

    def _add_custom_column(self):
        nomor = 1
        while self._existing_key_row(f"kolom_baru_{nomor}") >= 0:
            nomor += 1
        self._append_row(
            "KOLOM BARU",
            f"kolom_baru_{nomor}",
            "text",
            110,
            False,
        )
        item = self.table.item(self.table.rowCount() - 1, 0)
        if item:
            self.table.editItem(item)

    def _remove_current_row(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Pilih Kolom",
                "Pilih kolom yang ingin dihapus.",
            )
            return
        if self.table.rowCount() <= 1:
            QMessageBox.warning(
                self,
                "Kolom Tidak Bisa Dihapus",
                "Invoice harus memiliki minimal satu kolom.",
            )
            return
        self.table.removeRow(row)
        if self.table.rowCount() > 0:
            self.table.setCurrentCell(min(row, self.table.rowCount() - 1), 0)

    def _move_row(self, offset):
        source = self.table.currentRow()
        target = source + offset
        if source < 0 or target < 0 or target >= self.table.rowCount():
            return
        source_data = self._read_row(source)
        target_data = self._read_row(target)
        self._write_row(source, target_data)
        self._write_row(target, source_data)
        self.table.setCurrentCell(target, 0)

    def _read_row(self, row):
        title_item = self.table.item(row, 0)
        format_combo = self.table.cellWidget(row, 1)
        size_combo = self.table.cellWidget(row, 2)
        total_combo = self.table.cellWidget(row, 3)
        return {
            "title": title_item.text() if title_item else "",
            "key": str(
                title_item.data(Qt.ItemDataRole.UserRole) or "",
            ) if title_item else "",
            "type": self.FORMAT_LABEL_TO_TYPE.get(
                format_combo.currentText() if format_combo else "Teks",
                "text",
            ),
            "width": self.SIZE_LABEL_TO_WIDTH.get(
                size_combo.currentText() if size_combo else "Sedang",
                110,
            ),
            "amount": total_combo.currentText() == "Ya" if total_combo else False,
        }

    def _write_row(self, row, data):
        self._pasang_row(
            row,
            data.get("title", ""),
            data.get("key", ""),
            data.get("type", "text"),
            data.get("width", 110),
            data.get("amount", False),
        )

    def _restore_initial_columns(self):
        answer = QMessageBox.question(
            self,
            "Pulihkan Susunan Awal",
            "Kembalikan susunan kolom seperti saat dialog ini dibuka?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._load_columns(self.initial_columns, self.initial_amount_key)

    def _peringatan_desainer(self, judul, pesan, row=None):
        QMessageBox.warning(self, judul, pesan)
        if row is not None:
            self.table.setCurrentCell(row, 0)

    def _validate_and_accept(self):
        columns = []
        used_keys = set()
        amount_key = None

        for row in range(self.table.rowCount()):
            raw = self._read_row(row)
            title = str(raw["title"]).strip().upper()
            if not title:
                self._peringatan_desainer(
                    "Nama Kolom Belum Diisi",
                    f"Nama kolom pada baris {row + 1} masih kosong.",
                    row,
                )
                return

            key = str(raw["key"] or "").strip()
            if not key or key.startswith("kolom_baru_"):
                key = self._slug_key(title)
            if key in used_keys:
                self._peringatan_desainer(
                    "Kolom Sama",
                    f"Kolom {title} memiliki penyimpanan yang sama dengan kolom lain.",
                    row,
                )
                return
            used_keys.add(key)

            data_type = raw["type"]
            width = int(raw["width"])
            if raw["amount"]:
                if amount_key is not None:
                    self._peringatan_desainer(
                        "Kolom Total Ganda",
                        "Pilih hanya satu kolom yang masuk ke perhitungan subtotal.",
                    )
                    return
                amount_key, data_type = key, "currency"

            column = {"key": key, "title": title, "type": data_type, "width": width}
            if data_type == "text" and width >= 200:
                column["stretch"] = True
            columns.append(column)

        if not columns:
            self._peringatan_desainer(
                "Kolom Kosong",
                "Invoice harus memiliki minimal satu kolom.",
            )
            return

        if amount_key is None:
            rupiah_rows = [
                index for index, column in enumerate(columns)
                if column.get("type") == "currency"
            ]
            if len(rupiah_rows) == 1:
                amount_key = columns[rupiah_rows[0]]["key"]
            else:
                pesan = (
                    "Ubah satu kolom menjadi format Rupiah, lalu pilih Ya pada Masuk Total."
                    if not rupiah_rows
                    else "Pilih Ya pada satu kolom Rupiah yang akan dijumlahkan sebagai subtotal."
                )
                self._peringatan_desainer("Kolom Total Belum Dipilih", pesan)
                return

        self.result_columns = columns
        self.result_amount_key = amount_key
        self.accept()

# TAB INVOICE

class DialogPilihClientBilling(QDialog):
    """Memilih pihak tertagih setelah Resi dipilih dari Billing Queue."""

    def __init__(self, list_resi, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pilih Pihak Tertagih")
        self.setMinimumWidth(520)
        self._list_resi = [item for item in (list_resi or []) if isinstance(item, dict)]

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Invoice akan ditagihkan kepada:</b>"))

        self.cmb_client = QComboBox()
        kandidat = []
        sudah = set()
        for label, key in (("PENGIRIM", "pengirim"), ("PENERIMA", "penerima")):
            for data in self._list_resi:
                nama = str(data.get(key, "") or "").strip().upper()
                identitas = (label, nama)
                if nama and identitas not in sudah:
                    sudah.add(identitas)
                    kandidat.append((label, nama))

        for label, nama in kandidat:
            self.cmb_client.addItem(f"{label} — {nama}", nama)
        self.cmb_client.addItem("PIHAK KETIGA / INPUT MANUAL...", None)
        layout.addWidget(self.cmb_client)

        self.txt_manual = QLineEdit()
        self.txt_manual.setPlaceholderText("Nama pihak tertagih...")
        self.txt_manual.setEnabled(self.cmb_client.currentData() is None)
        layout.addWidget(self.txt_manual)

        info = QLabel(
            "Nama ini menjadi Bill To. Resi yang dipilih tetap mempertahankan "
            "asal cabang dan snapshot transaksinya masing-masing."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        tombol = QHBoxLayout()
        tombol.addStretch()
        self.btn_batal = QPushButton("Batal")
        self.btn_lanjut = QPushButton("Lanjutkan ke Draft Invoice")
        tombol.addWidget(self.btn_batal)
        tombol.addWidget(self.btn_lanjut)
        layout.addLayout(tombol)

        self.cmb_client.currentIndexChanged.connect(self._sinkronkan_input_manual)
        self.btn_batal.clicked.connect(self.reject)
        self.btn_lanjut.clicked.connect(self._validasi)

    def _sinkronkan_input_manual(self, *_):
        manual = self.cmb_client.currentData() is None
        self.txt_manual.setEnabled(manual)
        if manual:
            self.txt_manual.setFocus()

    def _validasi(self):
        if not self.get_nama_client():
            QMessageBox.warning(self, "Peringatan", "Nama pihak tertagih tidak boleh kosong.")
            return
        self.accept()

    def get_nama_client(self):
        data = self.cmb_client.currentData()
        if data is not None:
            return str(data or "").strip().upper()
        return self.txt_manual.text().strip().upper()


class BillingQueueDialog(QDialog):
    """Daftar Resi belum ditagihkan yang dapat dipilih langsung dari Tab Invoice."""

    COL_CHECK = 0
    COL_RESI = 1
    COL_CABANG = 2
    COL_TANGGAL = 3
    COL_PENGIRIM = 4
    COL_PENERIMA = 5
    COL_TUJUAN = 6
    COL_KOLI = 7
    COL_BERAT = 8
    COL_CBM = 9
    COL_ONGKIR = 10
    COL_STATUS = 11

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Billing Queue — Resi Belum Ditagihkan")
        self.resize(1240, 680)
        self._selected_data = []

        layout = QVBoxLayout(self)
        self._bangun_filter(layout)
        self._bangun_tabel(layout)
        self._bangun_footer(layout)
        self.muat_data()

    def _bangun_filter(self, layout):
        group = QGroupBox("Filter Resi Belum Ditagihkan")
        grid = QGridLayout(group)

        self.cmb_cabang = QComboBox()
        current_branch = str(CURRENT_SESSION.get("kode_cabang", "PUSAT") or "PUSAT").strip().upper()
        allowed_branches = CURRENT_SESSION.get("allowed_branches") or []
        allowed_codes = [
            str(item.get("kode_cabang") or "").strip().upper()
            for item in allowed_branches
            if isinstance(item, dict) and str(item.get("kode_cabang") or "").strip()
        ]
        allowed_codes = list(dict.fromkeys(allowed_codes)) or [current_branch]
        cabang_rows = db_service.ambil_daftar_cabang_billing() or []
        cabang_rows = [
            (kode, nama) for kode, nama in cabang_rows
            if str(kode or "").strip().upper() in set(allowed_codes)
        ]

        if len(allowed_codes) > 1:
            self.cmb_cabang.addItem("SEMUA CABANG", "__ALL__")
        for kode, nama in cabang_rows:
            kode_bersih = str(kode or "").strip().upper()
            self.cmb_cabang.addItem(f"{nama} ({kode_bersih})", kode_bersih)

        if self.cmb_cabang.count() == 0:
            self.cmb_cabang.addItem(current_branch, current_branch)

        self.txt_cari = QLineEdit()
        self.txt_cari.setPlaceholderText("Cari No. Resi / pengirim / penerima / tujuan / barang...")

        self.chk_periode = QCheckBox("Batasi periode")
        self.date_awal = QDateEdit(QDate.currentDate().addMonths(-1))
        self.date_akhir = QDateEdit(QDate.currentDate())
        for widget in (self.date_awal, self.date_akhir):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd/MM/yyyy")
            widget.setEnabled(False)

        self.btn_cari = QPushButton("🔎 Muat / Cari")
        grid.addWidget(QLabel("Cabang"), 0, 0)
        grid.addWidget(self.cmb_cabang, 0, 1)
        grid.addWidget(QLabel("Pencarian"), 0, 2)
        grid.addWidget(self.txt_cari, 0, 3, 1, 3)
        grid.addWidget(self.chk_periode, 1, 0)
        grid.addWidget(self.date_awal, 1, 1)
        grid.addWidget(QLabel("s.d."), 1, 2)
        grid.addWidget(self.date_akhir, 1, 3)
        grid.addWidget(self.btn_cari, 1, 5)
        grid.setColumnStretch(4, 1)
        layout.addWidget(group)

        self.chk_periode.toggled.connect(self._toggle_periode)
        self.btn_cari.clicked.connect(self.muat_data)
        self.txt_cari.returnPressed.connect(self.muat_data)
        self.cmb_cabang.currentIndexChanged.connect(self.muat_data)

    def _bangun_tabel(self, layout):
        self.tabel = QTableWidget()
        self.tabel.setColumnCount(12)
        self.tabel.setHorizontalHeaderLabels((
            "✓", "NO. RESI", "CABANG", "TANGGAL", "PENGIRIM", "PENERIMA",
            "TUJUAN", "KOLI", "BERAT", "CBM", "ONGKIR", "STATUS",
        ))
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.tabel.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        for col in (self.COL_PENGIRIM, self.COL_PENERIMA, self.COL_TUJUAN):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(self.COL_CHECK, 38)
        self.tabel.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tabel, 1)

    def _bangun_footer(self, layout):
        bar = QHBoxLayout()
        self.btn_pilih_semua = QPushButton("Pilih Semua")
        self.btn_kosongkan = QPushButton("Kosongkan Pilihan")
        self.lbl_ringkasan = QLabel("Dipilih: 0 Resi | Total: Rp 0")
        self.btn_batal = QPushButton("Batal")
        self.btn_masukkan = QPushButton("Masukkan ke Invoice")

        bar.addWidget(self.btn_pilih_semua)
        bar.addWidget(self.btn_kosongkan)
        bar.addWidget(self.lbl_ringkasan)
        bar.addStretch()
        bar.addWidget(self.btn_batal)
        bar.addWidget(self.btn_masukkan)
        layout.addLayout(bar)

        self.btn_pilih_semua.clicked.connect(lambda: self._set_semua_check(True))
        self.btn_kosongkan.clicked.connect(lambda: self._set_semua_check(False))
        self.btn_batal.clicked.connect(self.reject)
        self.btn_masukkan.clicked.connect(self._terima_pilihan)

    def _toggle_periode(self, aktif):
        self.date_awal.setEnabled(bool(aktif))
        self.date_akhir.setEnabled(bool(aktif))

    def _scope_cabang(self):
        data = self.cmb_cabang.currentData()
        if data == "__ALL__":
            return None, True
        return str(data or CURRENT_SESSION.get("kode_cabang", "PUSAT")).strip().upper(), False

    def muat_data(self, *_):
        kode_cabang, semua_cabang = self._scope_cabang()
        gunakan_periode = self.chk_periode.isChecked()
        rows = db_service.ambil_resi_belum_ditagihkan(
            kode_cabang,
            semua_cabang=semua_cabang,
            kode_cabang_list=[
                str(item.get("kode_cabang") or "").strip().upper()
                for item in (CURRENT_SESSION.get("allowed_branches") or [])
                if isinstance(item, dict) and str(item.get("kode_cabang") or "").strip()
            ],
            keyword=self.txt_cari.text(),
            tanggal_awal=(self.date_awal.date().toString("yyyy-MM-dd") if gunakan_periode else None),
            tanggal_akhir=(self.date_akhir.date().toString("yyyy-MM-dd") if gunakan_periode else None),
            limit=2000,
        ) or []

        with blokir_signal_sementara(self.tabel):
            self.tabel.setRowCount(0)
            for data in rows:
                row = self.tabel.rowCount()
                self.tabel.insertRow(row)

                check = QTableWidgetItem("")
                check.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                check.setCheckState(Qt.CheckState.Unchecked)
                check.setData(Qt.ItemDataRole.UserRole, dict(data))
                self.tabel.setItem(row, self.COL_CHECK, check)

                values = (
                    data.get("no_resi", ""),
                    data.get("kode_cabang", ""),
                    data.get("tanggal", ""),
                    data.get("pengirim", ""),
                    data.get("penerima", ""),
                    data.get("tujuan", ""),
                    data.get("koli", "0"),
                    data.get("berat", "0"),
                    data.get("kubik", "0"),
                    f"Rp {format_ke_rupiah(data.get('ongkir', 0))}",
                    data.get("status_resi", ""),
                )
                for offset, value in enumerate(values, start=1):
                    item = buat_tabel_item(value, editable=False)
                    self.tabel.setItem(row, offset, item)
        self._perbarui_ringkasan()

    def _set_semua_check(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        with blokir_signal_sementara(self.tabel):
            for row in range(self.tabel.rowCount()):
                item = self.tabel.item(row, self.COL_CHECK)
                if item is not None:
                    item.setCheckState(state)
        self._perbarui_ringkasan()

    def _on_item_changed(self, item):
        if item is not None and item.column() == self.COL_CHECK:
            self._perbarui_ringkasan()

    def _data_terpilih(self):
        hasil = []
        for row in range(self.tabel.rowCount()):
            item = self.tabel.item(row, self.COL_CHECK)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                hasil.append(dict(data))
        return hasil

    def _perbarui_ringkasan(self):
        data = self._data_terpilih()
        total = sum(rupiah_to_int(item.get("ongkir", 0)) for item in data)
        self.lbl_ringkasan.setText(
            f"Dipilih: {len(data)} Resi | Total: Rp {format_ke_rupiah(total)}"
        )

    def _terima_pilihan(self):
        self._selected_data = self._data_terpilih()
        if not self._selected_data:
            QMessageBox.warning(self, "Peringatan", "Pilih minimal satu Resi terlebih dahulu.")
            return
        self.accept()

    def selected_data(self):
        return [dict(item) for item in self._selected_data]


class TabInvoice(ZoomTableMixin, QWidget):
    KOL_HISTORI_NO_INV = 0
    KOL_HISTORI_TANGGAL = 1
    KOL_HISTORI_CLIENT = 2
    KOL_HISTORI_STATUS = 3

    SETTINGS_ORGANIZATION = "AplikasiEkspedisi"
    SETTINGS_APPLICATION_HISTORI = "TabInvoiceHistori"
    SETTINGS_KEY_LEBAR_HISTORI = "lebar_kolom"
    MIN_LEBAR_KOLOM = 20
    MAX_LEBAR_KOLOM = 1500

    def __init__(self):
        super().__init__()
        self.no_invoice_aktif = None
        self.total_invoice_aktif = 0
        self.status_invoice_aktif = "DRAFT"

        self._sedang_memuat_item = False
        self._sedang_menghitung = False
        self._sedang_menerapkan_zoom = False
        self._sedang_menyimpan_invoice = False
        self._dirty = False
        self._loading_invoice = False
        self._show_event_pertama = True

        self.template_configs = deepcopy(INVOICE_TEMPLATES)
        self.current_template_override = None
        self.active_template = deepcopy(self.template_configs["Standar"])
        self.active_columns = deepcopy(self.active_template["columns"])
        self.headers_aktif = [column["title"] for column in self.active_columns]

        self.init_ui()

    # UI & PENERAPAN HELPER INITIAL

    def init_ui(self):
        layout_utama = QHBoxLayout(self)
        layout_utama.setContentsMargins(8, 8, 8, 8)

        self._bangun_panel_histori_invoice()
        self._bangun_panel_editor_invoice()

        self.splitter = buat_splitter(
            self.panel_kiri,
            self.panel_kanan,
            orientation=Qt.Orientation.Horizontal,
            ukuran_awal=(340, 1000),
            bisa_diciutkan=False,
            parent=self,
        )
        layout_utama.addWidget(self.splitter)

        self._hubungkan_signal_invoice()
        self._inisialisasi_invoice_ui()

    @staticmethod
    def _buat_lineedit_invoice(placeholder, validator=None):
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        if validator is not None:
            widget.setValidator(validator)
        atur_tinggi_input(widget)
        return widget

    def _bangun_panel_histori_invoice(self):
        self.panel_kiri = QWidget()
        self.panel_kiri.setMinimumWidth(260)
        self.panel_kiri.setMaximumWidth(520)
        layout = QVBoxLayout(self.panel_kiri)
        layout.setContentsMargins(0, 0, 8, 0)

        self.lbl_title_histori = QLabel("Histori Invoice")
        self.txt_cari_invoice = self._buat_lineedit_invoice("Cari invoice...")

        self.tabel_histori_invoice = QTableWidget()
        self.tabel_histori_invoice.setColumnCount(4)
        self.tabel_histori_invoice.setHorizontalHeaderLabels(
            ["NO. INV", "TANGGAL", "CLIENT", "STATUS"],
        )
        self.tabel_histori_invoice.verticalHeader().setVisible(False)
        self.tabel_histori_invoice.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.tabel_histori_invoice.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        self.tabel_histori_invoice.setAlternatingRowColors(True)
        header = self.tabel_histori_invoice.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        btn_baru_kiri = QPushButton("＋ Invoice Baru")
        btn_baru_kiri.clicked.connect(self.buat_invoice_baru)

        for widget in (
            self.lbl_title_histori,
            self.txt_cari_invoice,
            self.tabel_histori_invoice,
            btn_baru_kiri,
        ):
            layout.addWidget(widget)

    def _bangun_panel_editor_invoice(self):
        self.panel_kanan = QWidget()
        self.panel_kanan.setMinimumWidth(700)
        self.panel_kanan.setMaximumWidth(1800)
        layout = QVBoxLayout(self.panel_kanan)
        layout.setContentsMargins(8, 0, 0, 0)

        self.lbl_title_editor = QLabel("DRAFT INVOICE BARU")
        layout.addWidget(self.lbl_title_editor)
        self._bangun_header_invoice(layout)
        self._bangun_toolbar_invoice(layout)

        self.tabel_item_invoice = InvoiceSheet(self)
        self.tabel_item_invoice.verticalHeader().setVisible(True)
        self.tabel_item_invoice.setAlternatingRowColors(True)
        layout.addWidget(self.tabel_item_invoice, 1)

        self._bangun_total_invoice(layout)
        self._bangun_aksi_invoice(layout)

    def _bangun_header_invoice(self, layout):
        group_header = QGroupBox("Informasi Invoice")
        grid = QGridLayout(group_header)
        validator_kapital = UppercaseValidator(self)

        self.txt_client = self._buat_lineedit_invoice(
            "Nama client / Bill To", validator_kapital,
        )
        self.txt_ship_to = self._buat_lineedit_invoice(
            "Ship To / tujuan penerima", validator_kapital,
        )
        self.txt_no_invoice = self._buat_lineedit_invoice(
            "Kosongkan untuk nomor otomatis", validator_kapital,
        )
        self.date_invoice = QDateEdit(QDate.currentDate())
        self.date_invoice.setCalendarPopup(True)
        self.date_invoice.setDisplayFormat("dd/MM/yyyy")

        self.cmb_tipe_invoice = QComboBox()
        self.cmb_tipe_invoice.addItems(list(self.template_configs.keys()))
        self.cmb_pajak = QComboBox()
        self.cmb_pajak.addItems(["NONPAJAK", "PPN 1,1%"])

        self.txt_payment_info = self._buat_lineedit_invoice(
            "Contoh: BCA 8292572980 a.n PT Ekspedisi kargo",
        )
        self.txt_catatan = self._buat_lineedit_invoice(
            "Catatan invoice, minimum charge, biaya bongkar, dll.",
        )
        self.txt_penanda_tangan = self._buat_lineedit_invoice("Nama penanda tangan")

        inputs = (
            self.txt_client,
            self.txt_ship_to,
            self.txt_no_invoice,
            self.date_invoice,
            self.cmb_tipe_invoice,
            self.cmb_pajak,
            self.txt_payment_info,
            self.txt_catatan,
            self.txt_penanda_tangan,
        )
        atur_tinggi_input(inputs)

        fields = (
            ("Bill To", self.txt_client, 0, 0, 1, 1),
            ("Ship To", self.txt_ship_to, 0, 2, 1, 1),
            ("No. Invoice", self.txt_no_invoice, 1, 0, 1, 1),
            ("Tanggal", self.date_invoice, 1, 2, 1, 1),
            ("Template", self.cmb_tipe_invoice, 2, 0, 1, 1),
            ("Pajak", self.cmb_pajak, 2, 2, 1, 1),
            ("Payment Info", self.txt_payment_info, 3, 0, 1, 3),
            ("Catatan", self.txt_catatan, 4, 0, 1, 3),
            ("Penanda Tangan", self.txt_penanda_tangan, 5, 0, 1, 3),
        )
        for label, widget, row, col, row_span, value_span in fields:
            grid.addWidget(QLabel(label), row, col)
            value_col = col + 1
            grid.addWidget(widget, row, value_col, row_span, value_span)

        layout.addWidget(group_header)

    def _bangun_toolbar_invoice(self, layout):
        toolbar = QHBoxLayout()
        self.btn_ambil_resi = QPushButton("Ambil Resi")
        self.btn_tambah_baris = QPushButton("＋ Baris")
        self.btn_hapus_baris = QPushButton("Hapus Baris")
        self.btn_duplikat_baris = QPushButton("Duplikat")
        self.btn_naik = QPushButton("↑")
        self.btn_turun = QPushButton("↓")
        self.btn_paste = QPushButton("Tempel Excel")
        self.btn_atur_kolom = QPushButton("⚙ Atur Kolom")
        self.btn_bersihkan = QPushButton("Bersihkan")
        for button in (
            self.btn_ambil_resi,
            self.btn_tambah_baris,
            self.btn_hapus_baris,
            self.btn_duplikat_baris,
            self.btn_naik,
            self.btn_turun,
            self.btn_paste,
            self.btn_atur_kolom,
            self.btn_bersihkan,
        ):
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

    def _bangun_total_invoice(self, layout):
        vbox = QVBoxLayout()
        alignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        self.lbl_subtotal = QLabel("SUB TOTAL: Rp 0")
        self.lbl_pajak_nominal = QLabel("PAJAK: Rp 0")
        self.lbl_total_tagihan = QLabel("TOTAL TAGIHAN: Rp 0")
        for label in (
            self.lbl_subtotal,
            self.lbl_pajak_nominal,
            self.lbl_total_tagihan,
        ):
            label.setAlignment(alignment)
            vbox.addWidget(label)
        layout.addLayout(vbox)

    def _bangun_aksi_invoice(self, layout):
        hbox = QHBoxLayout()
        self.btn_preview = QPushButton("Preview")
        self.btn_simpan_db = QPushButton("💾 Simpan Invoice")
        self.btn_cetak = QPushButton("🖨️ Cetak Invoice")
        self.menu_cetak = QMenu(self)
        self.action_cetak_pdf = self.menu_cetak.addAction("📄 Ekspor ke PDF (A4)")
        self.action_cetak_a4 = self.menu_cetak.addAction(
            "🖨️ Print Langsung (A4 - Inkjet/Laser)",
        )
        self.action_cetak_dotmatrix = self.menu_cetak.addAction(
            "🖨️ Print Langsung (NCR 9.5 x 5.5 - Dot Matrix)",
        )
        self.btn_cetak.setMenu(self.menu_cetak)
        self.btn_cetak.setEnabled(False)
        self.btn_share = QPushButton("📱 Share WA")

        hbox.addStretch()
        for button in (
            self.btn_preview,
            self.btn_simpan_db,
            self.btn_cetak,
            self.btn_share,
        ):
            hbox.addWidget(button)
        layout.addLayout(hbox)

    def _hubungkan_signal_invoice(self):
        self.txt_cari_invoice.textChanged.connect(self.filter_histori_invoice)
        self.tabel_histori_invoice.itemDoubleClicked.connect(
            self.buka_invoice_dari_histori,
        )
        self.tabel_item_invoice.itemChanged.connect(self._on_table_item_changed)
        self.tabel_item_invoice.sheetEdited.connect(self._on_sheet_bulk_edited)
        self.cmb_tipe_invoice.currentIndexChanged.connect(self._on_template_changed)
        self.cmb_pajak.currentIndexChanged.connect(self.ubah_rekening_otomatis)

        for field in (
            self.txt_client,
            self.txt_ship_to,
            self.txt_no_invoice,
            self.txt_payment_info,
            self.txt_catatan,
            self.txt_penanda_tangan,
        ):
            field.textChanged.connect(self._on_metadata_changed)
        self.date_invoice.dateChanged.connect(self._on_metadata_changed)

        self.btn_ambil_resi.clicked.connect(self.buka_billing_queue)
        self.btn_tambah_baris.clicked.connect(self.tabel_item_invoice.insert_row_below)
        self.btn_hapus_baris.clicked.connect(self.tabel_item_invoice.delete_selected_rows)
        self.btn_duplikat_baris.clicked.connect(
            self.tabel_item_invoice.duplicate_current_row,
        )
        self.btn_naik.clicked.connect(lambda: self.tabel_item_invoice.move_current_row(-1))
        self.btn_turun.clicked.connect(lambda: self.tabel_item_invoice.move_current_row(1))
        self.btn_paste.clicked.connect(self.tabel_item_invoice.paste_selection)
        self.btn_atur_kolom.clicked.connect(self.atur_kolom_invoice)
        self.btn_bersihkan.clicked.connect(self._confirm_clear_table)
        self.btn_preview.clicked.connect(self.tampilkan_preview)
        self.btn_simpan_db.clicked.connect(self.simpan_invoice_ke_db)
        self.action_cetak_pdf.triggered.connect(self.cetak_pdf)
        self.action_cetak_a4.triggered.connect(lambda: self.cetak_langsung("A4"))
        self.action_cetak_dotmatrix.triggered.connect(lambda: self.cetak_langsung("NCR"))
        self.btn_share.clicked.connect(self.info_fitur_share)

    def _inisialisasi_invoice_ui(self):
        self.load_lebar_kolom_histori(self.tabel_histori_invoice)
        self._perbarui_cache_lebar_zoom(
            self.tabel_histori_invoice,
            [
                self.tabel_histori_invoice.columnWidth(index)
                for index in range(self.tabel_histori_invoice.columnCount())
            ],
        )
        self.tabel_histori_invoice.horizontalHeader().sectionResized.connect(
            lambda *_: self.simpan_lebar_kolom_histori(self.tabel_histori_invoice)
        )
        self.apply_template(preserve_rows=False)
        self.sesuaikan_tema_lokal()
        self.load_histori_invoice()

    # FUNGSI PENDUKUNG HISTORI KOLOM

    def _settings_histori(self):
        return QSettings(
            self.SETTINGS_ORGANIZATION,
            self.SETTINGS_APPLICATION_HISTORI,
        )

    @classmethod
    def _normalisasi_lebar_kolom(cls, value, jumlah_kolom):
        if not isinstance(value, (list, tuple)):
            return None
        if len(value) != jumlah_kolom:
            return None

        hasil = []
        try:
            for width in value:
                hasil.append(
                    min(
                        max(cls.MIN_LEBAR_KOLOM, int(width)),
                        cls.MAX_LEBAR_KOLOM,
                    )
                )
        except (TypeError, ValueError):
            return None
        return hasil

    def simpan_lebar_kolom_histori(self, tabel):
        if self._sedang_menerapkan_zoom:
            return

        try:
            lebar_kolom = self._lebar_dasar_tabel(
                tabel,
                zoom_key=self.__class__.__name__,
            )
            lebar_kolom = [
                min(
                    max(self.MIN_LEBAR_KOLOM, int(width)),
                    self.MAX_LEBAR_KOLOM,
                )
                for width in lebar_kolom
            ]
            self._perbarui_cache_lebar_zoom(tabel, lebar_kolom)

            settings = self._settings_histori()
            settings.setValue(self.SETTINGS_KEY_LEBAR_HISTORI, lebar_kolom)
            settings.sync()
        except (TypeError, ValueError, RuntimeError) as exc:
            print(f"Gagal menyimpan lebar kolom histori: {exc}")

    def load_lebar_kolom_histori(self, tabel):
        header = tabel.horizontalHeader()
        lebar_default = [
            tabel.columnWidth(index)
            for index in range(tabel.columnCount())
        ]
        lebar_tersimpan = self._normalisasi_lebar_kolom(
            self._settings_histori().value(self.SETTINGS_KEY_LEBAR_HISTORI),
            tabel.columnCount(),
        )
        lebar_dasar = lebar_tersimpan or lebar_default

        self._sedang_menerapkan_zoom = True
        try:
            with blokir_signal_sementara(header):
                for index, width in enumerate(lebar_dasar):
                    tabel.setColumnWidth(index, int(width))
            self._perbarui_cache_lebar_zoom(tabel, lebar_dasar)
        except (TypeError, ValueError, RuntimeError) as exc:
            print(f"Gagal memuat lebar kolom histori: {exc}")
        finally:
            self._sedang_menerapkan_zoom = False

    # TEMPLATE DAN KOLOM

    @staticmethod
    def _alignment_tipe_invoice(data_type):
        if data_type in {"currency", "integer", "decimal"}:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if data_type == "date":
            return Qt.AlignmentFlag.AlignCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    @staticmethod
    def _buat_item_tabel(value, column):
        """Membuat item tabel dengan alignment sesuai tipe kolom."""
        return buat_tabel_item(
            text=value,
            alignment=TabInvoice._alignment_tipe_invoice(column.get("type", "text")),
        )

    def _current_template_config(self):
        if self.current_template_override:
            return deepcopy(self.current_template_override)
        name = self.cmb_tipe_invoice.currentText() or "Standar"
        return deepcopy(
            self.template_configs.get(name, self.template_configs["Standar"]),
        )

    def _capture_rows_by_key(self):
        rows = []
        if not self.active_columns:
            return rows
        for row in range(self.tabel_item_invoice.rowCount()):
            row_data = {}
            for column_index, column in enumerate(self.active_columns):
                item = self.tabel_item_invoice.item(row, column_index)
                row_data[column["key"]] = item.text() if item else ""
            if any(str(value).strip() for value in row_data.values()):
                rows.append(row_data)
        return rows

    def _tambahkan_row_invoice(self, row_data):
        row = self.tabel_item_invoice.rowCount()
        self.tabel_item_invoice.insertRow(row)
        for column_index, column in enumerate(self.active_columns):
            value = row_data.get(column["key"], row_data.get(column.get("title", ""), ""))
            self.tabel_item_invoice.setItem(
                row,
                column_index,
                self._buat_item_tabel(value, column),
            )
        return row

    def _pastikan_baris_invoice(self):
        if self.tabel_item_invoice.rowCount() == 0:
            self.tabel_item_invoice.insertRow(0)

    def _pasang_struktur_template_invoice(self, old_rows):
        with blokir_signal_sementara(self.tabel_item_invoice):
            self.tabel_item_invoice.clear()
            self.tabel_item_invoice.setColumnCount(len(self.active_columns))
            self.tabel_item_invoice.setHorizontalHeaderLabels(self.headers_aktif)
            self.tabel_item_invoice.setRowCount(0)

            header = self.tabel_item_invoice.horizontalHeader()
            has_stretch = False
            for index, column in enumerate(self.active_columns):
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
                if column.get("stretch") and not has_stretch:
                    has_stretch = True
                else:
                    self.tabel_item_invoice.setColumnWidth(
                        index,
                        int(column.get("width", 110)),
                    )

            lebar_dasar = [
                int(column.get("width", 110))
                for column in self.active_columns
            ]
            self._perbarui_cache_lebar_zoom(
                self.tabel_item_invoice,
                lebar_dasar,
            )
            for row_data in old_rows:
                self._tambahkan_row_invoice(row_data)
            self._pastikan_baris_invoice()

    def apply_template(self, preserve_rows=True, rows_override=None):
        old_rows = rows_override if rows_override is not None else (
            self._capture_rows_by_key() if preserve_rows else []
        )
        template = self._current_template_config()
        self.active_template = template
        self.active_columns = deepcopy(template.get("columns", []))
        self.headers_aktif = [
            column.get("title", column.get("key", ""))
            for column in self.active_columns
        ]

        self._sedang_memuat_item = True
        try:
            self._pasang_struktur_template_invoice(old_rows)
        finally:
            self._sedang_memuat_item = False

        self.hitung_ulang_total_tagihan()
        self._terapkan_zoom_tabel_invoice(
            is_dark=self._tema_gelap_aktif(),
            z=zoom_helper.dapatkan_zoom_level(self.__class__.__name__),
            tabel_sasaran=(self.tabel_item_invoice,),
        )

    def _on_template_changed(self, *_):
        if self._loading_invoice:
            return
        old_rows = self._capture_rows_by_key()
        self.current_template_override = None
        self.apply_template(preserve_rows=False, rows_override=old_rows)
        self._mark_dirty()

    def atur_kolom_invoice(self):
        dialog = ColumnDesignerDialog(
            self.active_columns,
            self.active_template.get("amount_key", "amount"),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        old_rows = self._capture_rows_by_key()
        override = deepcopy(self.active_template)
        override["columns"] = dialog.result_columns
        override["amount_key"] = dialog.result_amount_key
        override.pop("formula", None)
        override["customized"] = True
        self.current_template_override = override
        self.apply_template(preserve_rows=False, rows_override=old_rows)
        self._mark_dirty()

    def _column_index_by_key(self, key):
        for index, column in enumerate(self.active_columns):
            if column.get("key") == key:
                return index
        return -1

    # EVENT EDITOR DAN TOTAL

    def _on_table_item_changed(self, item):
        if self._sedang_memuat_item or self._sedang_menghitung:
            return

        if 0 <= item.column() < len(self.active_columns):
            data_type = self.active_columns[item.column()].get("type", "text")
            item.setTextAlignment(self._alignment_tipe_invoice(data_type))

        self._apply_formula_for_row(item.row(), edited_column=item.column())
        self.hitung_ulang_total_tagihan()
        self._mark_dirty()

    def _normalisasi_format_item_tabel(self):
        for row in range(self.tabel_item_invoice.rowCount()):
            for column_index, column in enumerate(self.active_columns):
                item = self.tabel_item_invoice.item(row, column_index)
                if item is None:
                    continue

                data_type = column.get("type", "text")
                item.setTextAlignment(self._alignment_tipe_invoice(data_type))
                if data_type == "currency":
                    teks = item.text().strip()
                    if teks and any(karakter.isdigit() for karakter in teks):
                        item.setText(format_ke_rupiah(rupiah_to_int(teks)))

    def _on_sheet_bulk_edited(self):
        if self._sedang_memuat_item:
            return

        with blokir_signal_sementara(self.tabel_item_invoice):
            self._normalisasi_format_item_tabel()
            self._recalculate_all_formulas()

        self.hitung_ulang_total_tagihan()
        self._mark_dirty()

    def _on_metadata_changed(self, *_):
        if self._loading_invoice:
            return
        self.hitung_ulang_total_tagihan()
        self._mark_dirty()

    def _mark_dirty(self):
        if self._loading_invoice:
            return
        self._dirty = True
        self.btn_simpan_db.setEnabled(True)
        self.btn_cetak.setEnabled(False)
        if self.no_invoice_aktif:
            self.lbl_title_editor.setText(f"EDIT INVOICE: {self.no_invoice_aktif} *")
        else:
            self.lbl_title_editor.setText("DRAFT INVOICE BARU *")

    def _apply_formula_for_row(self, row, edited_column=None):
        formula = self.active_template.get("formula")
        if not formula or formula.get("operation") != "multiply":
            return

        source_keys = formula.get("sources", [])
        target_key = formula.get("target")
        source_indexes = [self._column_index_by_key(key) for key in source_keys]
        target_index = self._column_index_by_key(target_key)
        if target_index < 0 or any(index < 0 for index in source_indexes):
            return
        if edited_column is not None and edited_column not in source_indexes:
            return

        values = []
        for index in source_indexes:
            item = self.tabel_item_invoice.item(row, index)

            value = ambil_angka_dari_teks(item.text() if item else "")
            values.append(value)

        result = Decimal("1")
        for value in values:
            result *= value

        self._sedang_menghitung = True
        try:
            item = self.tabel_item_invoice.item(row, target_index)
            nilai_akhir = int(result.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

            teks_akhir = format_ke_rupiah(nilai_akhir)

            if item is None:
                item = self._buat_item_tabel(
                    teks_akhir,
                    self.active_columns[target_index],
                )
                self.tabel_item_invoice.setItem(row, target_index, item)
            else:
                item.setText(teks_akhir)
        finally:
            self._sedang_menghitung = False

    def _recalculate_all_formulas(self):
        for row in range(self.tabel_item_invoice.rowCount()):
            self._apply_formula_for_row(row)

    def hitung_ulang_total_tagihan(self, *_):
        if self._sedang_memuat_item:
            return

        amount_column = self._column_index_by_key(
            self.active_template.get("amount_key", "amount")
        )
        subtotal = sum(
            rupiah_to_int(
                self.tabel_item_invoice.item(row, amount_column).text()
                if self.tabel_item_invoice.item(row, amount_column) else "0"
            )
            for row in range(self.tabel_item_invoice.rowCount())
        ) if amount_column >= 0 else 0

        tax_name = self.cmb_pajak.currentText()
        tax_rate = {
            "NONPAJAK": Decimal("0"),
            "PPN 1,1%": Decimal("0.011"),
        }.get(tax_name, Decimal("0"))
        tax_value = int(
            (Decimal(subtotal) * tax_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        self.total_invoice_aktif = subtotal + tax_value
        self.lbl_subtotal.setText(f"SUB TOTAL: Rp {format_ke_rupiah(subtotal)}")
        self.lbl_pajak_nominal.setText(f"{tax_name}: Rp {format_ke_rupiah(tax_value)}")
        self.lbl_total_tagihan.setText(
            f"TOTAL TAGIHAN: Rp {format_ke_rupiah(self.total_invoice_aktif)}"
        )

    @staticmethod
    def _muat_data_perusahaan():
        """
        Mengambil konfigurasi perusahaan dari database aktif.

        muat_pengaturan_sistem() sudah menggabungkan nilai database dengan
        default white-label, sehingga tidak perlu melakukan merge ulang.
        """
        try:
            data = muat_pengaturan_sistem()
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            print(f"Gagal memuat data perusahaan untuk invoice: {exc}")
            return {}

    def _set_rekening_otomatis(self, tandai_perubahan=True):
        """Mengisi payment info berdasarkan jenis pajak yang dipilih."""
        pengaturan = self._muat_data_perusahaan()
        pajak_dipilih = self.cmb_pajak.currentText().strip().upper()

        key_rekening = (
            "rekening_nonpajak"
            if pajak_dipilih == "NONPAJAK"
            else "rekening_pajak"
        )
        list_rekening = pengaturan.get(key_rekening, [])

        if isinstance(list_rekening, list):
            teks_rekening = " | ".join(
                str(item).strip()
                for item in list_rekening
                if str(item).strip()
            )
        elif isinstance(list_rekening, str):
            teks_rekening = list_rekening.strip()
        else:
            teks_rekening = ""

        with blokir_signal_sementara(self.txt_payment_info):
            self.txt_payment_info.setText(teks_rekening)

        self.hitung_ulang_total_tagihan()

        if tandai_perubahan:
            self._mark_dirty()

    def ubah_rekening_otomatis(self, *_):
        if self._loading_invoice:
            return

        self._set_rekening_otomatis(
            tandai_perubahan=True,
        )

    def _konfirmasi_buang_perubahan(self, tindakan):
        if not self._dirty:
            return True

        answer = QMessageBox.question(
            self,
            "Invoice Belum Disimpan",
            (
                "Perubahan invoice belum disimpan. "
                f"Tetap {str(tindakan or 'melanjutkan')}?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def buka_billing_queue(self):
        """Pilih Resi belum ditagihkan tanpa harus masuk ke Buku Gudang."""
        dialog = BillingQueueDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        list_resi_data = dialog.selected_data()
        if not list_resi_data:
            return False

        dialog_client = DialogPilihClientBilling(list_resi_data, self)
        if dialog_client.exec() != QDialog.DialogCode.Accepted:
            return False

        return self.terima_data_baru(
            dialog_client.get_nama_client(),
            list_resi_data,
        )

    @staticmethod
    def _row_invoice_dari_resi(nomor, data):
        return {
            "no": str(nomor),
            "resi": str(data.get("no_resi", "")).strip().upper(),
            "destination": str(data.get("tujuan", "")).strip().upper(),
            "description": str(data.get("nama_barang", "")).strip().upper(),
            "package": str(data.get("koli", "0")).strip(),
            "weight": str(data.get("berat", "0")).strip(),
            "volume": str(data.get("kubik", "0")).strip(),
            "amount": str(data.get("ongkir", "0")).strip(),
        }

    def terima_data_baru(self, nama_client, list_resi_data):
        if not self.buat_invoice_baru():
            return False

        self._loading_invoice = True
        try:
            self.txt_client.setText(str(nama_client or "").strip().upper())
            self.cmb_tipe_invoice.setCurrentText("Standar")
            self.current_template_override = None
            self.apply_template(preserve_rows=False)
            self._sedang_memuat_item = True

            with blokir_signal_sementara(self.tabel_item_invoice):
                self.tabel_item_invoice.setRowCount(0)
                for nomor, data in enumerate(list_resi_data or [], start=1):
                    if isinstance(data, dict):
                        self._tambahkan_row_invoice(
                            self._row_invoice_dari_resi(nomor, data)
                        )
                self._pastikan_baris_invoice()
        finally:
            self._sedang_memuat_item = False
            self._loading_invoice = False

        self.hitung_ulang_total_tagihan()
        self._mark_dirty()
        return True

    def _generate_no_invoice(self):
        try:
            pengaturan = self._muat_data_perusahaan()
            prefix_inv = str(
                pengaturan.get("prefix_invoice", "INV")
            ).strip().upper() or "INV"
            branch_code = str(
                CURRENT_SESSION.get("kode_cabang", "PUSAT")
            ).strip().upper() or "PUSAT"
        except Exception as exc:
            print(f"Gagal membaca konfigurasi nomor invoice: {exc}")
            prefix_inv, branch_code = "INV", "PUSAT"

        prefix = f"{prefix_inv}-{branch_code}-{datetime.now().strftime('%Y%m%d')}"
        sequence = db_service.dapatkan_sequence_invoice_baru(prefix)
        try:
            sequence_number = int(sequence)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Sequence invoice dari database tidak valid.") from exc
        return f"{prefix}-{sequence_number:04d}"

    def _metadata_dict(self):
        metadata = {
            "ship_to": self.txt_ship_to.text().strip(),
            "payment_info": self.txt_payment_info.text().strip(),
            "notes": self.txt_catatan.text().strip(),
            "signer": self.txt_penanda_tangan.text().strip(),
        }
        if self.current_template_override:
            metadata["template_config"] = self.current_template_override
        return metadata

    def ambil_data_item_invoice(self):
        items = []
        amount_key = self.active_template.get("amount_key", "amount")
        amount_column = self._column_index_by_key(amount_key)

        for row in range(self.tabel_item_invoice.rowCount()):
            row_data = {}
            for column_index, column in enumerate(self.active_columns):
                item = self.tabel_item_invoice.item(row, column_index)
                row_data[column["key"]] = item.text().strip() if item else ""

            if not any(row_data.values()):
                continue

            amount_item = self.tabel_item_invoice.item(
                row,
                amount_column,
            ) if amount_column >= 0 else None

            nominal = rupiah_to_int(amount_item.text() if amount_item else "0")
            items.append(
                {
                    "nomor_urut": row + 1,
                    "data_kolom": json.dumps(row_data, ensure_ascii=False),
                    "nominal": nominal,
                }
            )
        return items

    def _siapkan_header_simpan_invoice(self, client, items):
        manual_number = self.txt_no_invoice.text().strip().upper()
        no_invoice = self.no_invoice_aktif or manual_number or self._generate_no_invoice()
        no_invoice = str(no_invoice or "").strip().upper()
        if not no_invoice:
            raise ValueError("Nomor invoice tidak berhasil dibuat.")

        return no_invoice, {
            "no_invoice": no_invoice,
            "tanggal": self.date_invoice.date().toString("yyyy-MM-dd"),
            "client": client,
            "tipe_invoice": self.cmb_tipe_invoice.currentText(),
            "jenis_pajak": self.cmb_pajak.currentText(),
            "subtotal": sum(item["nominal"] for item in items),
            "total_akhir": self.total_invoice_aktif,
            "status": self.status_invoice_aktif,
            "metadata_json": json.dumps(self._metadata_dict(), ensure_ascii=False),
            "template_version": int(self.active_template.get("version", 1)),
        }

    def _tampilkan_gagal_simpan_invoice(self, pesan):
        pesan_teks = str(pesan or "Invoice gagal disimpan.")
        if "sudah digunakan" in pesan_teks.lower():
            QMessageBox.warning(
                self,
                "Nomor Invoice Sudah Ada",
                "Nomor invoice tersebut sudah tersimpan. Buka dari histori untuk mengeditnya.",
            )
        else:
            QMessageBox.warning(self, "Peringatan", pesan_teks)

    def _tandai_invoice_tersimpan(self, no_invoice):
        self.no_invoice_aktif = no_invoice
        self.txt_no_invoice.setText(str(no_invoice))
        self._dirty = False
        self.btn_simpan_db.setEnabled(False)
        self.btn_cetak.setEnabled(True)
        self.lbl_title_editor.setText(
            f"{self.status_invoice_aktif} INVOICE: {no_invoice}",
        )
        self.load_histori_invoice()
        QMessageBox.information(
            self,
            "Sukses",
            f"Invoice {no_invoice} berhasil disimpan.",
        )

    def _siapkan_simpan_invoice(self):
        client = self.txt_client.text().strip().upper()
        items = self.ambil_data_item_invoice()
        if not client:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Nama client / Bill To tidak boleh kosong.",
            )
            return None
        if not items:
            QMessageBox.warning(
                self,
                "Peringatan",
                "Belum ada item tagihan yang akan disimpan.",
            )
            return None

        self.hitung_ulang_total_tagihan()
        try:
            no_invoice, header_data = self._siapkan_header_simpan_invoice(client, items)
        except (TypeError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(
                self,
                "Nomor Invoice Tidak Valid",
                f"Invoice belum dapat disimpan:\n{exc}",
            )
            return None
        return no_invoice, header_data, items

    def simpan_invoice_ke_db(self):
        if self._sedang_menyimpan_invoice:
            return

        prepared = self._siapkan_simpan_invoice()
        if prepared is None:
            return
        no_invoice, header_data, items = prepared

        self._sedang_menyimpan_invoice = True
        self.btn_simpan_db.setEnabled(False)
        try:
            sukses, pesan = db_service.simpan_atau_update_invoice(
                header_data,
                items,
                self.no_invoice_aktif is not None,
            )
            if not sukses:
                self._tampilkan_gagal_simpan_invoice(pesan)
                return
            self._tandai_invoice_tersimpan(no_invoice)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Gagal menyimpan invoice:\n{exc}")
        finally:
            self._sedang_menyimpan_invoice = False
            self.btn_simpan_db.setEnabled(self._dirty)

    def _tambahkan_baris_histori_invoice(self, tabel, data):
        row = tabel.rowCount()
        tabel.insertRow(row)
        for column in range(min(len(data), tabel.columnCount())):
            value = data[column]
            item = buat_tabel_item(
                text=str(value if value is not None else ""),
                editable=False,
            )
            item.setFont(tabel.font())
            item.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled,
            )
            tabel.setItem(row, column, item)

    def load_histori_invoice(self):
        tabel = self.tabel_histori_invoice
        tabel.setUpdatesEnabled(False)
        tabel.blockSignals(True)
        try:
            tabel.setRowCount(0)
            for data in db_service.ambil_histori_invoice(limit=300) or []:
                if isinstance(data, (list, tuple)):
                    self._tambahkan_baris_histori_invoice(tabel, data)
            return True
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error Histori Invoice",
                f"Gagal memuat histori invoice:\n{exc}",
            )
            return False
        finally:
            tabel.blockSignals(False)
            tabel.setUpdatesEnabled(True)
            self.filter_histori_invoice()

    def filter_histori_invoice(self, *_):
        keyword = self.txt_cari_invoice.text().strip().lower()
        for row in range(self.tabel_histori_invoice.rowCount()):
            match = any(
                self.tabel_histori_invoice.item(row, column)
                and keyword in self.tabel_histori_invoice.item(row, column).text().lower()
                for column in range(self.tabel_histori_invoice.columnCount())
            )
            self.tabel_histori_invoice.setRowHidden(row, not match)

    def buka_invoice_dari_histori(self, *_):
        selection_model = self.tabel_histori_invoice.selectionModel()
        selected = selection_model.selectedRows() if selection_model else []
        if not selected:
            return False

        item = self.tabel_histori_invoice.item(
            selected[0].row(),
            self.KOL_HISTORI_NO_INV,
        )
        no_invoice = item.text().strip() if item else ""
        if not no_invoice:
            return False
        return self.load_invoice_by_no(no_invoice)

    def _terapkan_header_invoice_loaded(self, no_invoice, header):
        client, template_name, tax_name, status, date_text, metadata_text = header
        metadata = self._parse_json_object(metadata_text)
        template_name = str(template_name or "Standar")
        tax_name = str(tax_name or "NONPAJAK")
        status = str(status or "DRAFT")

        self.no_invoice_aktif = no_invoice
        self.status_invoice_aktif = status or "DRAFT"
        self.txt_no_invoice.setText(str(no_invoice or ""))
        self.txt_client.setText(str(client or ""))
        self.txt_ship_to.setText(str(metadata.get("ship_to", "") or ""))
        self.txt_payment_info.setText(str(metadata.get("payment_info", "") or ""))
        self.txt_catatan.setText(str(metadata.get("notes", "") or ""))
        self.txt_penanda_tangan.setText(str(metadata.get("signer", "") or ""))

        parsed_date = QDate.fromString(date_text or "", "yyyy-MM-dd")
        self.date_invoice.setDate(
            parsed_date if parsed_date.isValid() else QDate.currentDate(),
        )
        if template_name not in self.template_configs:
            self.cmb_tipe_invoice.addItem(template_name)
            self.template_configs[template_name] = deepcopy(
                self.template_configs["Custom / Bebas"],
            )
        self.cmb_tipe_invoice.setCurrentText(template_name)
        self.cmb_pajak.setCurrentText(tax_name or "NONPAJAK")
        override = metadata.get("template_config")
        self.current_template_override = override if isinstance(override, dict) else None
        self.apply_template(preserve_rows=False)

    def _muat_detail_invoice(self, details):
        with blokir_signal_sementara(self.tabel_item_invoice):
            self.tabel_item_invoice.setRowCount(0)
            for detail in details or []:
                self._tambahkan_row_invoice(
                    self._parse_json_object(detail[0] if detail else None)
                )
            self._pastikan_baris_invoice()

    def _terapkan_invoice_loaded(self, no_invoice, header, details):
        self._loading_invoice = True
        self._sedang_memuat_item = True
        try:
            self._terapkan_header_invoice_loaded(no_invoice, header)
            self._muat_detail_invoice(details)
            self.lbl_title_editor.setText(
                f"{self.status_invoice_aktif} INVOICE: {no_invoice}",
            )
            self._dirty = False
            self.btn_simpan_db.setEnabled(False)
            self.btn_cetak.setEnabled(True)
        finally:
            self._sedang_memuat_item = False
            self._loading_invoice = False

    def load_invoice_by_no(self, no_invoice):
        no_invoice = str(no_invoice or "").strip().upper()
        if not no_invoice or not self._konfirmasi_buang_perubahan("membuka invoice lain"):
            return False

        try:
            header, details = db_service.ambil_invoice_by_no(no_invoice)
            if not header:
                QMessageBox.warning(
                    self,
                    "Invoice Tidak Ditemukan",
                    f"Invoice {no_invoice} tidak ditemukan.",
                )
                return False
            if len(header) < 6:
                raise ValueError("Format header invoice dari database tidak lengkap.")

            self._terapkan_invoice_loaded(no_invoice, header, details)
            self.hitung_ulang_total_tagihan()
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Gagal membuka invoice:\n{exc}")
            return False

    def buat_invoice_baru(self):
        if not self._konfirmasi_buang_perubahan("membuat invoice baru"):
            return False

        self._loading_invoice = True
        try:
            self.no_invoice_aktif = None
            self.status_invoice_aktif = "DRAFT"
            self.current_template_override = None
            reset_form_input_global(
                self.panel_kanan,
                reset_tanggal=True,
                fokus_ke=self.txt_client,
            )
            self.cmb_tipe_invoice.setCurrentText("Standar")
            self.cmb_pajak.setCurrentText("NONPAJAK")
            self.apply_template(preserve_rows=False)
        finally:
            self._loading_invoice = False

        self._set_rekening_otomatis(tandai_perubahan=False)
        self.hitung_ulang_total_tagihan()
        self._dirty = False
        self.btn_simpan_db.setEnabled(True)
        self.btn_cetak.setEnabled(False)
        self.lbl_title_editor.setText("DRAFT INVOICE BARU")
        return True

    def _confirm_clear_table(self):
        answer = QMessageBox.question(
            self,
            "Bersihkan Tabel",
            "Kosongkan seluruh item pada invoice?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.tabel_item_invoice.clear_all_rows()

    # PREVIEW DAN PDF

    @staticmethod
    def _parse_json_object(value):
        """Mengubah teks JSON menjadi dictionary tanpa menghentikan UI."""
        if isinstance(value, dict):
            return deepcopy(value)

        if value is None or str(value).strip() == "":
            return {}

        try:
            parsed = json.loads(str(value))
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    @staticmethod
    def _esc(value):
        return html.escape(
            str(value if value is not None else ""),
            quote=True,
        )

    @staticmethod
    def _font_family_aplikasi() -> str:
        """Nama font aktual yang sudah diterapkan ke QApplication."""
        app = QApplication.instance()
        if app is None:
            return "sans-serif"

        nama_font = str(app.font().family() or "").strip()
        return nama_font or "sans-serif"

    @classmethod
    def _font_family_css(cls) -> str:
        """Nama font aktif yang aman disisipkan ke CSS bertanda kutip."""
        return (
            cls._font_family_aplikasi()
            .replace("\\", "\\\\")
            .replace('"', '\\"')
        )

    def _visible_rows(self):
        rows = []
        for row in range(self.tabel_item_invoice.rowCount()):
            data = {}
            for column_index, column in enumerate(self.active_columns):
                item = self.tabel_item_invoice.item(row, column_index)
                data[column["key"]] = item.text().strip() if item else ""
            if any(data.values()):
                rows.append(data)
        return rows

    def _konteks_header_html_invoice(self):
        invoice_number = self.no_invoice_aktif or self.txt_no_invoice.text().strip() or "DRAFT"
        client = self.txt_client.text().strip().upper() or "-"
        ship_to = self.txt_ship_to.text().strip().upper() or "-"
        date_text = self.date_invoice.date().toString("dd MMMM yyyy")
        payment = self.txt_payment_info.text().strip()
        notes = self.txt_catatan.text().strip()
        data_perusahaan = self._muat_data_perusahaan()

        nama_perusahaan = (
            str(data_perusahaan.get("nama_perusahaan", "")).strip()
            or "PT KARGO EKSPEDISI"
        )
        alamat = str(data_perusahaan.get("alamat_perusahaan", "")).strip()
        telp = str(data_perusahaan.get("telp_perusahaan", "")).strip()
        logo_html = (
            str(data_perusahaan.get("logo_text_html", "")).strip()
            or self._esc(nama_perusahaan)
        )
        default_signer = str(CURRENT_SESSION.get("username", "")).strip() or "ADMIN"

        bagian_alamat = []
        if alamat:
            bagian_alamat.append(self._esc(alamat).replace("\n", "<br>"))
        if telp:
            bagian_alamat.append(f"Telp. {self._esc(telp)}")

        kota_tanda_tangan = str(
            data_perusahaan.get("kota_tanda_tangan", "")
        ).strip()
        tempat_tanggal = (
            f"{self._esc(kota_tanda_tangan)}, {self._esc(date_text)}"
            if kota_tanda_tangan
            else self._esc(date_text)
        )
        signer = self.txt_penanda_tangan.text().strip() or default_signer
        return {
            "invoice_number": invoice_number,
            "client": client,
            "ship_to": ship_to,
            "date_text": date_text,
            "payment": payment,
            "notes": notes,
            "layout_type": self.active_template.get("layout", "standard"),
            "nama_perusahaan": nama_perusahaan,
            "logo_html": logo_html,
            "alamat_lengkap": "<br>".join(bagian_alamat) or "-",
            "tempat_tanggal": tempat_tanggal,
            "signer": signer,
        }

    def _headers_html_invoice(self):
        total_width = sum(
            max(int(column.get("width", 100)), 1)
            for column in self.active_columns
        ) or 1
        return "".join(
            f'<th style="width:{(max(int(column.get("width", 100)), 1) / total_width) * 100:.2f}%">'
            f'{self._esc(column.get("title", ""))}</th>'
            for column in self.active_columns
        )

    def _body_html_invoice(self, rows):
        body_lines = []
        center_keys = {
            "no",
            "package",
            "quantity",
            "weight",
            "volume",
            "ship_date",
        }
        for row_data in rows:
            cells = []
            for column in self.active_columns:
                key = column["key"]
                value = row_data.get(key, "")
                data_type = column.get("type", "text")
                if data_type == "currency":
                    cls = "num"
                elif data_type in {"integer", "decimal"} or key in center_keys:
                    cls = "center"
                else:
                    cls = ""
                if data_type == "currency" and value:
                    parsed = rupiah_to_int(value)
                    value = format_ke_rupiah(parsed) if parsed else value
                cells.append(f'<td class="{cls}">{self._esc(value)}</td>')
            body_lines.append("<tr>" + "".join(cells) + "</tr>")

        if not body_lines:
            body_lines.append(
                f'<tr><td colspan="{max(len(self.active_columns), 1)}" class="empty">Belum ada item</td></tr>',
            )
        return "".join(body_lines)

    def _party_header_html_invoice(self, layout_type, client, ship_to):
        if layout_type == "logistics":
            return f"""
                    <table class="party single">
                        <tr><th>TO :</th><td>{self._esc(client)}</td></tr>
                    </table>
                """
        return f"""
                    <table class="party">
                        <tr>
                            <th>BILL TO</th>
                            <th>SHIP TO</th>
                        </tr>
                        <tr>
                            <td>{self._esc(client)}</td>
                            <td>{self._esc(ship_to)}</td>
                        </tr>
                    </table>
                """

    @staticmethod
    def _style_html_invoice(font_family_css):
        return f"""
        @page {{ size: A4; margin: 8mm; }}
        * {{ box-sizing: border-box; }}
        html, body {{ margin: 0; padding: 0; width: 100%; }}
        body {{ font-family: "{font_family_css}"; color: #000; font-size: 8.5pt; font-weight: normal; line-height: 1.15; margin: 0; }}
        .page {{ width: 100%; margin: 0; padding: 0; }}

        .company {{ width: 100%; border: none; border-collapse: collapse; table-layout: fixed; margin-bottom: 2px; }}
        .company td {{ padding: 0 6px 4px 6px; vertical-align: top; border: none; }}
        .brand, .brand * {{ font-family: "{font_family_css}" !important; font-size: 14pt !important; line-height: 1 !important; font-weight: bold; }}
        .brand {{ color: #1747a6; }} .logo-kargo {{ color: #e00000; }}
        .company-name {{ font-size: 8.5pt; font-weight: bold; }}
        .address {{ text-align: right; font-size: 7.5pt; line-height: 1.2; }}

        .invoice-title {{ border: 1px solid #000; text-align: center; padding: 2px 4px; }}
        .invoice-title .title {{ font-size: 10.5pt; line-height: 1.1; font-weight: bold; }}
        .invoice-title .number {{ font-size: 8pt; margin-top: 1px; font-weight: normal; }}

        .party {{ width: 100%; border-collapse: collapse; margin: 0; table-layout: fixed; }}
        .party th, .party td {{ border: 1px solid #000; padding: 3px 5px; }}
        .party th {{ background: transparent; text-align: center; font-size: 8pt; font-weight: bold; }}
        .party td {{ text-align: center; font-size: 8.5pt; font-weight: normal; }}
        .party.single th {{ width: 45px; text-align: left; }}
        .party.single td {{ text-align: left; font-size: 9pt; font-weight: bold; }}

        .items {{ width: 100%; border-collapse: collapse; table-layout: fixed; margin: 0; }}
        .items th {{ border: 1px solid #000; background: transparent; padding: 2px 3px; text-align: center; vertical-align: middle; font-size: 7.5pt; line-height: 1.1; font-weight: bold; }}
        .items td {{ border: 1px solid #000; padding: 2px 3px; vertical-align: top; font-size: 8pt; line-height: 1.15; font-weight: normal; word-wrap: break-word; }}
        .items .num {{ text-align: right; white-space: nowrap; }}
        .items .center {{ text-align: center; white-space: nowrap; }}
        .items .empty {{ text-align: center; color: #777; padding: 10px; }}

        .bottom {{ width: 100%; border-collapse: collapse; margin: 0; table-layout: fixed; }}
        .bottom > tbody > tr > td {{ vertical-align: top; }}
        .payment {{ width: 65%; padding: 4px; font-size: 8pt; line-height: 1.25; font-weight: normal; }}
        .total-container {{ width: 35%; padding: 0; }}
        .totals {{ width: 100%; border-collapse: collapse; }}
        .totals td {{ border: 1px solid #000; padding: 3px 5px; font-size: 8.5pt; }}
        .totals .label {{ text-align: right; font-weight: bold; }}
        .totals .value {{ text-align: right; white-space: nowrap; font-weight: normal; }}
        .totals .grand {{ font-size: 10.5pt; line-height: 1.1; font-weight: bold; }}

        .notes {{ margin-top: 4px; padding: 3px; border: 1px solid #999; font-size: 7.5pt; line-height: 1.2; }}
        .signature {{ margin-top: 7px; text-align: right; padding-right: 8px; font-size: 8pt; line-height: 1.2; }}
        .signature .space {{ height: 38px; }}
        .signature .name {{ font-size: 8.5pt; font-weight: bold; text-decoration: underline; }}
    """

    def _render_invoice_html(
        self,
        context,
        headers_html,
        body_html,
        party_header,
        subtotal,
        tax_name,
        tax_value,
    ):
        notes = context["notes"]
        payment = context["payment"]
        notes_html = f'<div class="notes"><b>Catatan:</b> {self._esc(notes)}</div>' if notes else ""
        payment_html = self._esc(payment).replace("\n", "<br>") if payment else "-"
        style_html = self._style_html_invoice(self._font_family_css())
        return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><style>{style_html}</style></head>
    <body><div class="page">
    <table class="company"><tr>
    <td><span class="brand">{context["logo_html"]}</span><br><span class="company-name">{self._esc(context["nama_perusahaan"])}</span></td>
    <td class="address">{context["alamat_lengkap"]}</td>
    </tr></table>
    <div class="invoice-title"><div class="title">INVOICE</div><div class="number">No. {self._esc(context["invoice_number"])}</div></div>
    {party_header}
    <table class="items"><thead><tr>{headers_html}</tr></thead><tbody>{body_html}</tbody></table>
    <table class="bottom"><tr>
    <td class="payment"><b>PAYMENT INFO</b><br>{payment_html}{notes_html}</td>
    <td class="total-container"><table class="totals">
    <tr><td class="label">SUB TOTAL</td><td class="value">Rp {format_ke_rupiah(subtotal)}</td></tr>
    <tr><td class="label">{self._esc(tax_name)}</td><td class="value">Rp {format_ke_rupiah(tax_value)}</td></tr>
    <tr><td class="label grand">TOTAL</td><td class="value grand">Rp {format_ke_rupiah(self.total_invoice_aktif)}</td></tr>
    </table></td>
    </tr></table>
    <div class="signature">{context["tempat_tanggal"]}<div class="space"></div><div class="name">{self._esc(context["signer"])}</div></div>
    </div></body>
    </html>
            """

    def build_invoice_html(self):
        self.hitung_ulang_total_tagihan()
        context = self._konteks_header_html_invoice()
        rows = self._visible_rows()
        headers_html = self._headers_html_invoice()
        body_html = self._body_html_invoice(rows)
        subtotal = sum(item["nominal"] for item in self.ambil_data_item_invoice())
        tax_name = self.cmb_pajak.currentText()
        tax_value = self.total_invoice_aktif - subtotal
        party_header = self._party_header_html_invoice(
            context["layout_type"],
            context["client"],
            context["ship_to"],
        )
        return self._render_invoice_html(
            context,
            headers_html,
            body_html,
            party_header,
            subtotal,
            tax_name,
            tax_value,
        )

    def tampilkan_preview(self):
        html_content = self.build_invoice_html()
        default_name = self.no_invoice_aktif or self.txt_no_invoice.text().strip() or "invoice_draft"

        tampilkan_preview_invoice(
            html_content=html_content,
            suggested_name=default_name,
            parent=self,
        )

    def cetak_pdf(self):
        html_content = self.build_invoice_html()
        default_name = self.no_invoice_aktif or self.txt_no_invoice.text().strip() or "invoice_draft"

        simpan_invoice_pdf(
            html_content=html_content,
            suggested_name=default_name,
            parent=self,
        )

    def cetak_langsung(self, tipe_kertas):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)

        if tipe_kertas == "A4":
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            printer.setPageMargins(QMarginsF(8, 8, 8, 8), QPageLayout.Unit.Millimeter)

        elif tipe_kertas == "NCR":
            custom_size = QPageSize(QSizeF(9.5, 5.5), QPageSize.Unit.Inch)
            printer.setPageSize(custom_size)
            printer.setPageMargins(QMarginsF(4, 4, 4, 4), QPageLayout.Unit.Millimeter)

        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Pilih Printer")

        if dialog.exec() == QDialog.DialogCode.Accepted:
            html_content = self.build_invoice_html()

            if tipe_kertas == "NCR":
                html_content = html_content.replace(
                    "@page { size: A4; margin: 8mm; }",
                    "@page { size: 9.5in 5.5in; margin: 4mm; }",
                )
                font_family_css = self._font_family_css()
                html_content = html_content.replace(
                    f'body {{ font-family: "{font_family_css}"; color: #000; font-size: 8.5pt; font-weight: normal; line-height: 1.15; margin: 0; }}',
                    f'body {{ font-family: "{font_family_css}"; color: #000; font-size: 8pt; font-weight: normal; line-height: 1.1; margin: 0; }}',
                )

            document = QTextDocument()
            document.setHtml(html_content)

            try:
                document.print_(printer)
                QMessageBox.information(
                    self,
                    "Sukses",
                    f"Invoice sedang dikirim ke printer:\n{printer.printerName()}"
                )
            except Exception as exc:
                QMessageBox.critical(self, "Gagal Mencetak", str(exc))

    def info_fitur_cetak(self):
        self.cetak_pdf()

    def info_fitur_share(self):
        QMessageBox.information(
            self,
            "Share WhatsApp",
            "PDF invoice sudah dapat dibuat. Pengiriman WhatsApp dapat disambungkan setelah metode API/WhatsApp Desktop ditentukan.",
        )

    # TEMA

    def refresh_session_ui(self):
        self.load_histori_invoice()
        self.filter_histori_invoice()

    def showEvent(self, event):
        super().showEvent(event)
        if self._show_event_pertama:
            self._show_event_pertama = False
            self.filter_histori_invoice()
            return
        self.refresh_session_ui()

    @staticmethod
    def _style_tanpa_font_size(style):
        """Hapus deklarasi font-size agar ukuran tabel hanya berasal dari QFont."""
        return re.sub(
            r"font-size\s*:\s*[^;}]+;?",
            "",
            style or "",
            flags=re.IGNORECASE,
        )

    def _tema_gelap_aktif(self):
        window = self.window()
        return bool(
            window
            and hasattr(window, "current_theme")
            and window.current_theme == "dark"
        )

    @staticmethod
    def _dapatkan_style_invoice_statis(is_dark):
        """Bangun QSS tema pada ukuran dasar; tidak bergantung level zoom."""
        ukuran = get_global_font_sizes(0)
        return konversi_style_font_ke_point(get_invoice_styles(
            is_dark,
            ukuran["sz_title"],
            ukuran["sz_base"],
            ukuran["sz_input"],
            ukuran["sz_total"],
        ))

    def _terapkan_tema_statis_invoice(self, is_dark, styles):
        """Terapkan tema ke seluruh elemen non-tabel tanpa membaca level zoom."""
        self.lbl_title_histori.setStyleSheet(styles["lbl_title_histori"])
        self.lbl_title_editor.setStyleSheet(styles["lbl_title_editor"])
        self.lbl_subtotal.setStyleSheet(styles["lbl_subtotal"])
        self.lbl_pajak_nominal.setStyleSheet(styles["lbl_subtotal"])
        self.lbl_total_tagihan.setStyleSheet(styles["lbl_total_tagihan"])

        for widget in (
            self.txt_cari_invoice,
            self.txt_client,
            self.txt_ship_to,
            self.txt_no_invoice,
            self.txt_payment_info,
            self.txt_catatan,
            self.txt_penanda_tangan,
        ):
            widget.setStyleSheet(styles["input"])

        self.date_invoice.setStyleSheet("")
        terapkan_style_kalender(
            self.date_invoice,
            is_dark=is_dark,
        )

        for button in self.findChildren(QPushButton):
            button.setStyleSheet(styles["button_default"])

        self.btn_simpan_db.setStyleSheet(styles["button_simpan"])
        self.btn_preview.setStyleSheet(styles["button_preview"])
        self.btn_cetak.setStyleSheet(styles["button_cetak"])
        self.btn_share.setStyleSheet(styles["button_share"])

        if hasattr(self, "menu_cetak"):
            self.menu_cetak.setStyleSheet(styles["menu_cetak"])

    def _terapkan_combobox_statis_invoice(self):
        """Terapkan ukuran dasar ComboBox; zoom Invoice hanya untuk tabel."""
        comboboxes = (
            self.cmb_tipe_invoice,
            self.cmb_pajak,
        )

        atur_tinggi_input(comboboxes)

    @staticmethod
    def _sinkronkan_font_item_tabel(tabel):
        """Samakan font seluruh item/cell-widget dengan font tabel aktif.

        QTableWidgetItem dapat menyimpan QFont sendiri. Jika item dibuat oleh
        helper dengan font eksplisit, perubahan ``tabel.setFont()`` tidak
        otomatis mengubah teks sel yang sudah ada.
        """
        if tabel is None:
            return

        font_item = tabel.font()
        font_header = tabel.horizontalHeader().font()

        for column in range(tabel.columnCount()):
            header_item = tabel.horizontalHeaderItem(column)
            if header_item is not None:
                header_item.setFont(font_header)

        for row in range(tabel.rowCount()):
            for column in range(tabel.columnCount()):
                item = tabel.item(row, column)
                if item is not None:
                    item.setFont(font_item)

                cell_widget = tabel.cellWidget(row, column)
                if cell_widget is not None:
                    cell_widget.setFont(font_item)

    def _konfigurasi_zoom_tabel_invoice(self):
        konfigurasi = []
        tabel_histori = getattr(self, "tabel_histori_invoice", None)
        if tabel_histori is not None:
            konfigurasi.append((tabel_histori, "tabel_histori", 28))
        tabel_editor = getattr(self, "tabel_item_invoice", None)
        if tabel_editor is not None:
            konfigurasi.append((tabel_editor, "tabel_editor", 32))
        return konfigurasi

    def _terapkan_visual_zoom_tabel_invoice(self, tabel, style_key, styles, metrics):
        style_visual = self._style_tanpa_font_size(styles[style_key])
        style_font_zoom = zoom_helper.generate_font_zoom_tabel_qss(metrics.level)
        tabel.setStyleSheet(f"{style_visual}\n{style_font_zoom}")

        font_tabel = tabel.font()
        app = QApplication.instance()
        if app is not None:
            font_tabel.setFamily(app.font().family())
        font_tabel.setPointSizeF(metrics.font_base_pt)
        tabel.setFont(font_tabel)
        tabel.setIconSize(QSize(metrics.icon_size, metrics.icon_size))

        header = tabel.horizontalHeader()
        font_header = header.font()
        font_header.setPointSizeF(metrics.font_base_pt)
        font_header.setBold(True)
        header.setFont(font_header)
        tabel.verticalHeader().setFont(font_header)

        self._sinkronkan_font_item_tabel(tabel)
        style_engine = tabel.style()
        style_engine.unpolish(tabel)
        style_engine.polish(tabel)
        tabel.ensurePolished()
        return header

    @staticmethod
    def _hitung_geometri_zoom_invoice(tabel, header, tinggi_dasar, metrics):
        tinggi_teks = max(1, int(tabel.fontMetrics().height()))
        padding_item = skalakan_px(metrics.item_padding, minimum=1)
        ekstra_item = skalakan_px(8, minimum=4)
        tinggi_baris = max(
            skalakan_px(24, minimum=18),
            round(tinggi_dasar * metrics.factor),
            tinggi_teks + (padding_item * 2) + ekstra_item,
        )
        tabel.verticalHeader().setMinimumSectionSize(tinggi_baris)
        tabel.verticalHeader().setDefaultSectionSize(tinggi_baris)

        tinggi_teks_header = max(1, int(header.fontMetrics().height()))
        padding_header = skalakan_px(metrics.header_padding_v, minimum=1)
        ekstra_header = skalakan_px(8, minimum=4)
        tinggi_header = max(
            metrics.header_height,
            tinggi_teks_header + (padding_header * 2) + ekstra_header,
        )
        header.setMinimumHeight(tinggi_header)
        return tinggi_baris

    def _terapkan_zoom_satu_tabel_invoice(
        self,
        tabel,
        style_key,
        tinggi_dasar,
        styles,
        metrics,
    ):
        tabel.setUpdatesEnabled(False)
        try:
            header = self._terapkan_visual_zoom_tabel_invoice(
                tabel,
                style_key,
                styles,
                metrics,
            )
            tinggi_baris = self._hitung_geometri_zoom_invoice(
                tabel,
                header,
                tinggi_dasar,
                metrics,
            )
            with blokir_signal_sementara(header):
                zoom_helper.skalakan_kolom_tableview(tabel, metrics.level)

            model = tabel.model()
            if model is not None:
                for row in range(model.rowCount()):
                    tabel.setRowHeight(row, tinggi_baris)
        finally:
            tabel.setUpdatesEnabled(True)
            tabel.updateGeometries()
            tabel.viewport().update()
            tabel.viewport().repaint()
            tabel.update()

    def _terapkan_zoom_tabel_invoice(
        self,
        *,
        is_dark,
        z,
        tabel_sasaran=None,
    ):
        """Terapkan zoom hanya pada tabel histori dan tabel editor invoice."""
        styles = self._dapatkan_style_invoice_statis(is_dark)
        metrics = zoom_helper.dapatkan_metrik_zoom(z)
        target_ids = (
            {id(tabel) for tabel in tabel_sasaran if tabel is not None}
            if tabel_sasaran is not None
            else None
        )

        self._sedang_menerapkan_zoom = True
        try:
            for tabel, style_key, tinggi_dasar in self._konfigurasi_zoom_tabel_invoice():
                if target_ids is None or id(tabel) in target_ids:
                    self._terapkan_zoom_satu_tabel_invoice(
                        tabel,
                        style_key,
                        tinggi_dasar,
                        styles,
                        metrics,
                    )
        finally:
            self._sedang_menerapkan_zoom = False

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()

        styles = self._dapatkan_style_invoice_statis(is_dark)
        self._terapkan_tema_statis_invoice(is_dark, styles)

        self._terapkan_combobox_statis_invoice()

        z = zoom_helper.dapatkan_zoom_level(self.__class__.__name__)
        self._terapkan_zoom_tabel_invoice(
            is_dark=is_dark,
            z=z,
        )