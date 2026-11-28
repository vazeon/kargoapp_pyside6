# tabs/tab_invoice.py
import html
import csv
import io
import json
import re

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext

from PySide6.QtCore import QDate, QRectF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QPalette, QPen, QValidator
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
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import CURRENT_SESSION, muat_pengaturan_sistem
import services.database_service as db_service
import services.numbering_service as numbering_service

from themes.modules.invoice import get_invoice_dialog_styles, get_invoice_styles
from utils.input_style_helper import atur_tinggi_input, terapkan_style_input_global
from themes.components.calendar import terapkan_style_kalender

from utils.typography import (
    get_fixed_font_sizes,
    get_fixed_font_sizes_pt,
    konversi_style_font_ke_point,
)
from utils.printer.print_invoice import (
    cetak_invoice_langsung,
    tampilkan_preview_invoice,
    simpan_invoice_pdf,
)
from utils.printer.invoice_page_setup import (
    InvoicePageSetupDialog,
    muat_page_setup,
    page_setup_untuk_kertas,
    simpan_page_setup,
)
from utils.printer.invoice_pdfmake import (
    InvoicePdfPreviewDialog,
    cetak_pdfmake_bytes,
    simpan_pdfmake_bytes,
)
from utils.number_formatters import (
    rupiah_to_int,
    format_ke_rupiah,
)
from utils.table_helper import (
    buat_tabel_item,
    pasang_header_wrap,
    pasang_style_tabel,
    terapkan_tema_tabel,
)
from utils.reset_form_helper import reset_form_input_global
from utils.validators import UppercaseValidator
from utils.widget_helpers import blokir_signal_sementara
from utils.invoice_univer import InvoiceSheetContainer

# KONFIGURASI TEMPLATE
INVOICE_TEMPLATES = {
    "Standar": {
        "version": 3,
        "layout": "standard",
        "amount_key": "amount",
        "columns": [
            {"key": "no", "title": "NO", "type": "integer", "width": 45},
            {"key": "resi", "title": "RESI", "type": "text", "width": 105},
            {"key": "destination", "title": "TUJUAN", "type": "text", "width": 135},
            {"key": "description", "title": "NAMA BARANG", "type": "text", "width": 210, "stretch": True},
            {"key": "package", "title": "KOLI", "type": "decimal", "width": 65},
            {"key": "weight", "title": "BERAT (KG)", "type": "decimal", "width": 85},
            {"key": "volume", "title": "KUBIK (M³)", "type": "decimal", "width": 90},
            {"key": "amount", "title": "ONGKIR (Rp)", "type": "currency", "width": 125},
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
            {"key": "description", "title": "JENIS BARANG", "type": "text", "width": 210, "stretch": True},
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
            {"key": "description", "title": "DESCRIPTION", "type": "text", "width": 310, "stretch": True},
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
            {"key": "description", "title": "DESCRIPTION", "type": "text", "width": 430, "stretch": True},
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
            {"key": "description", "title": "DESCRIPTION", "type": "text", "width": 360, "stretch": True},
            {"key": "quantity", "title": "QTY", "type": "text", "width": 80},
            {"key": "weight", "title": "BERAT", "type": "text", "width": 90},
            {"key": "tariff", "title": "TARIF", "type": "currency", "width": 110},
            {"key": "amount", "title": "AMOUNT", "type": "currency", "width": 140},
        ],
    },
}

# SPREADSHEET EDITOR

def _parse_invoice_number(value, data_type):
    text = str(value or "").strip()
    if text in {"", "-"}:
        return Decimal(0)
    if data_type == "currency":
        text = re.sub(r"^Rp\s*", "", text, flags=re.IGNORECASE)
    if data_type in {"currency", "integer"}:
        pattern = r"(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+)(?:,0+)?"
        if not re.fullmatch(pattern, text):
            if re.fullmatch(r"[0-9]+\.0+", text):
                return Decimal(text)
            raise ValueError("Gunakan angka bulat nonnegatif, contoh 1500 atau 1.500.")
        text = text.split(",")[0].replace(".", "")
    elif "," in text:
        if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+),[0-9]+", text):
            raise ValueError("Gunakan angka desimal nonnegatif, contoh 1,5 atau 1.000,5.")
        text = text.replace(".", "").replace(",", ".")
    elif not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
        raise ValueError("Gunakan angka desimal nonnegatif, contoh 1,5 atau 1.5.")
    return Decimal(text)


def _subtotal_resi_untuk_invoice(data):
    """Ambil subtotal tersimpan; None berarti nominal akan diisi di Invoice."""
    if not isinstance(data, dict):
        raise TypeError("Data Resi untuk Invoice harus berupa dictionary.")

    raw_subtotal = data.get("subtotal_ongkir")
    if raw_subtotal in (None, ""):
        return None

    subtotal = rupiah_to_int(raw_subtotal)
    if subtotal < 0:
        nomor = str(data.get("no_resi") or "(nomor tidak diketahui)").strip()
        raise ValueError(f"Resi {nomor} memiliki subtotal_ongkir negatif.")
    return subtotal


def _normalisasi_nilai_invoice(value, column):
    text = str(value if value is not None else "").strip()
    data_type = column.get("type", "text")
    if data_type in {"integer", "decimal", "currency"}:
        number = _parse_invoice_number(text, data_type)
        if text in {"", "-"}:
            return text
        if data_type == "currency":
            return format_ke_rupiah(int(number))
        if data_type == "integer":
            return str(int(number))
        result = format(number, "f")
        if "." in result:
            result = result.rstrip("0").rstrip(".")
        return result.replace(".", ",")
    if data_type == "date" and text not in {"", "-"}:
        for date_format in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, date_format).strftime("%d/%m/%Y")
            except ValueError:
                continue
        raise ValueError("Tanggal tidak valid. Gunakan DD/MM/YYYY, contoh 12/09/2026.")
    return text.upper()


class InvoiceCellValidator(QValidator):
    def __init__(self, data_type, parent=None):
        super().__init__(parent)
        self.data_type = data_type

    def validate(self, text, pos):
        pattern = r"[0-9/\-]*" if self.data_type == "date" else r"[0-9.,\- ]*"
        if self.data_type == "currency":
            pattern = r"(?:[Rr](?:[Pp])?\s*)?[0-9.,\- ]*"
        state = self.State.Acceptable if re.fullmatch(pattern, text) else self.State.Invalid
        return state, text, pos


class InvoiceItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if not selected:
            super().paint(painter, option, index)
            return

        normal_option = QStyleOptionViewItem(option)
        normal_option.state &= ~(
            QStyle.StateFlag.State_Selected
            | QStyle.StateFlag.State_HasFocus
            | QStyle.StateFlag.State_MouseOver
        )
        super().paint(painter, normal_option, index)

        color = option.palette.color(
            QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight,
        )
        painter.save()
        try:
            painter.setClipRect(option.rect, Qt.ClipOperation.IntersectClip)
            painter.setPen(QPen(color, 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -0.5))
        finally:
            painter.restore()

    def createEditor(self, parent, option, index):
        view = self.parent()
        if bool(getattr(view, "mutation_locked", False)):
            return None
        editor = QLineEdit(parent)
        column = self.parent().invoice_column(index.column())
        data_type = column.get("type", "text")
        if data_type in {"integer", "decimal", "currency", "date"}:
            editor.setValidator(InvoiceCellValidator(data_type, editor))
            editor.setPlaceholderText(
                "DD/MM/YYYY" if data_type == "date" else
                "Desimal: 1,5 / 1.5" if data_type == "decimal" else "Angka bulat: 1.500"
            )
        else:
            editor.setValidator(UppercaseValidator(editor))
        return editor

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.EditRole)
        editor.setText(str(value if value is not None else ""))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        column = self.parent().invoice_column(index.column())
        try:
            value = _normalisasi_nilai_invoice(editor.text(), column)
        except ValueError:
            value = editor.text().strip().upper()
        model.setData(index, value, Qt.ItemDataRole.EditRole)


class InvoiceSheetModel(QTableWidget):
    sheetEdited = Signal()
    ROW_SOURCE_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    ROW_TEMPLATE_VALUES_ROLE = int(Qt.ItemDataRole.UserRole) + 2
    ROW_TOKEN_ROLE = int(Qt.ItemDataRole.UserRole) + 3

    def setItem(self, row, column, item):
        if item is not None:
            item.setFont(self.font())
        super().setItem(row, column, item)
        if self.signalsBlocked():
            parent = self.parent()
            refresh = getattr(parent, "refresh_univer", None)
            if (
                callable(refresh)
                and not getattr(parent, "_suppress_model_refresh", False)
                and not getattr(parent, "_applying_web_snapshot", False)
            ):
                QTimer.singleShot(0, refresh)

    def __init__(self, parent=None):
        super().__init__(parent)
        pasang_header_wrap(self)
        self.invoice_columns = []
        self.mutation_locked = False
        self.setItemDelegate(InvoiceItemDelegate(self))
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

    def invoice_column(self, index):
        if 0 <= index < len(self.invoice_columns):
            return self.invoice_columns[index]
        return {"type": "text"}

    def set_mutation_locked(self, locked):
        """Kunci seluruh jalur edit tabel tanpa menonaktifkan baca/salin/cetak."""
        self.mutation_locked = bool(locked)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
            if self.mutation_locked
            else (
                QAbstractItemView.EditTrigger.DoubleClicked
                | QAbstractItemView.EditTrigger.EditKeyPressed
                | QAbstractItemView.EditTrigger.SelectedClicked
                | QAbstractItemView.EditTrigger.AnyKeyPressed
            )
        )

    def _boleh_mutasi(self):
        return not self.mutation_locked

    def _header_item_for_row(self, row):
        if row < 0 or row >= self.rowCount():
            return None
        header_item = self.verticalHeaderItem(row)
        if header_item is None:
            header_item = QTableWidgetItem(str(row + 1))
            header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setVerticalHeaderItem(row, header_item)
        return header_item

    def set_row_source_metadata(self, row, metadata):
        header_item = self._header_item_for_row(row)
        if header_item is None:
            return
        header_item.setData(
            self.ROW_SOURCE_ROLE,
            dict(metadata) if isinstance(metadata, dict) and metadata else None,
        )

    def row_source_metadata(self, row):
        header_item = self._header_item_for_row(row)
        metadata = header_item.data(self.ROW_SOURCE_ROLE) if header_item else None
        return dict(metadata) if isinstance(metadata, dict) else None

    def set_row_template_values(self, row, values):
        """Simpan nilai kolom yang sedang tidak ditampilkan oleh template aktif."""
        header_item = self._header_item_for_row(row)
        if header_item is None:
            return
        header_item.setData(
            self.ROW_TEMPLATE_VALUES_ROLE,
            deepcopy(values) if isinstance(values, dict) and values else None,
        )

    def row_template_values(self, row):
        header_item = self._header_item_for_row(row)
        values = (
            header_item.data(self.ROW_TEMPLATE_VALUES_ROLE)
            if header_item else None
        )
        return deepcopy(values) if isinstance(values, dict) else {}

    def set_row_token(self, row, token):
        header_item = self._header_item_for_row(row)
        if header_item is not None:
            header_item.setData(self.ROW_TOKEN_ROLE, str(token) if token else None)

    def row_token(self, row):
        header_item = self._header_item_for_row(row)
        token = header_item.data(self.ROW_TOKEN_ROLE) if header_item else None
        return str(token) if token else None

    def renumber_rows(self):
        """Jaga nomor urut visual dan kolom NO setelah perubahan struktur tabel."""
        no_column = next(
            (
                index for index, column in enumerate(self.invoice_columns)
                if column.get("key") == "no"
            ),
            -1,
        )
        with blokir_signal_sementara(self):
            for row in range(self.rowCount()):
                header_item = self.verticalHeaderItem(row)
                if header_item is None:
                    header_item = QTableWidgetItem()
                    self.setVerticalHeaderItem(row, header_item)
                header_item.setText(str(row + 1))
                header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if no_column >= 0:
                    item = self.item(row, no_column)
                    if item is None:
                        item = buat_tabel_item(str(row + 1))
                        self.setItem(row, no_column, item)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        parent = self.parent()
        refresh = getattr(parent, "refresh_univer", None)
        if (
            callable(refresh)
            and not getattr(parent, "_suppress_model_refresh", False)
            and not getattr(parent, "_applying_web_snapshot", False)
        ):
            QTimer.singleShot(0, refresh)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_selection()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            self.copy_selection()
            if self._boleh_mutasi():
                self.clear_selected_cells()
            return
        if event.matches(QKeySequence.StandardKey.Delete):
            self.clear_selected_cells()
            return
        if event.key() == Qt.Key.Key_Insert:
            self.insert_row_below()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._boleh_mutasi():
            row = max(self.currentRow(), 0)
            column = max(self.currentColumn(), 0) + 1
            if column >= self.columnCount():
                column = 0
                row += 1
            if row >= self.rowCount():
                self.insert_blank_row(self.rowCount())
            if self.rowCount() > 0 and self.columnCount() > 0:
                self.setCurrentCell(min(row, self.rowCount() - 1), column)
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
        if not self._boleh_mutasi():
            return
        text = QApplication.clipboard().text()
        if not text:
            return

        start_row = max(self.currentRow(), 0)
        start_column = max(self.currentColumn(), 0)
        try:
            rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True))
        except csv.Error as exc:
            QMessageBox.warning(self, "Tempel Excel", f"Format clipboard tidak valid:\n{exc}")
            return

        pending = []
        for row_offset, values in enumerate(rows):
            if start_column + len(values) > self.columnCount():
                QMessageBox.warning(self, "Tempel Excel", "Kolom clipboard melebihi sisa kolom tabel. Tidak ada data yang ditempel.")
                return
            for column_offset, value in enumerate(values):
                target_row = start_row + row_offset
                target_column = start_column + column_offset
                column = self.invoice_column(target_column)
                try:
                    value = _normalisasi_nilai_invoice(value, column)
                except ValueError as exc:
                    QMessageBox.warning(
                        self, "Tempel Excel",
                        f"Baris {target_row + 1}, kolom {column.get('title', target_column + 1)}:\n"
                        f"{exc}\nTidak ada data yang ditempel.",
                    )
                    return
                pending.append((target_row, target_column, value))

        self.setUpdatesEnabled(False)
        try:
            with blokir_signal_sementara(self):
                for target_row, target_column, value in pending:
                    while target_row >= self.rowCount():
                        self.insertRow(self.rowCount())
                    item = self.item(target_row, target_column)
                    if item is None:
                        self.setItem(target_row, target_column, buat_tabel_item(value))
                    else:
                        item.setText(value)

                    column_config = self.invoice_column(target_column)
                    if column_config.get("key") == "resi":
                        metadata = self.row_source_metadata(target_row)
                        nomor_sumber = str((metadata or {}).get("no_resi") or "").strip().upper()
                        if metadata and str(value or "").strip().upper() != nomor_sumber:
                            self.set_row_source_metadata(target_row, None)
                self.renumber_rows()
        finally:
            self.setUpdatesEnabled(True)

        self.sheetEdited.emit()

    def clear_selected_cells(self):
        if not self._boleh_mutasi():
            return
        selected = self.selectedItems()
        if not selected:
            return
        with blokir_signal_sementara(self):
            resi_column = next(
                (index for index, column in enumerate(self.invoice_columns)
                 if column.get("key") == "resi"),
                -1,
            )
            for item in selected:
                item.setText("")
                if item.column() == resi_column:
                    self.set_row_source_metadata(item.row(), None)
            self.renumber_rows()
        self.sheetEdited.emit()

    def insert_blank_row(self, row=None):
        if not self._boleh_mutasi():
            return
        if row is None:
            row = self.rowCount()
        row = max(0, min(row, self.rowCount()))
        self.insertRow(row)
        self.renumber_rows()
        self.setCurrentCell(row, 0)
        self.sheetEdited.emit()

    def insert_row_above(self):
        row = self.currentRow()
        self.insert_blank_row(0 if row < 0 else row)

    def insert_row_below(self):
        row = self.currentRow()
        self.insert_blank_row(self.rowCount() if row < 0 else row + 1)

    def delete_selected_rows(self):
        if not self._boleh_mutasi():
            return
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
        self.renumber_rows()
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
        if not self._boleh_mutasi():
            return
        source_row = self.currentRow()
        if source_row < 0:
            return
        target_row = source_row + 1
        source_metadata = self.row_source_metadata(source_row)
        source_template_values = self.row_template_values(source_row)
        with blokir_signal_sementara(self):
            values = self._row_values(source_row, Qt.AlignmentFlag.AlignLeft)
            self.insertRow(target_row)
            self._set_row_values(target_row, values)
            self.set_row_source_metadata(target_row, source_metadata)
            self.set_row_template_values(target_row, source_template_values)
            self.set_row_token(target_row, None)
            self.renumber_rows()
        self.setCurrentCell(target_row, 0)
        self.sheetEdited.emit()

    def move_current_row(self, offset):
        if not self._boleh_mutasi():
            return
        source_row = self.currentRow()
        if source_row < 0:
            return
        target_row = source_row + offset
        if target_row < 0 or target_row >= self.rowCount():
            return

        source_metadata = self.row_source_metadata(source_row)
        target_metadata = self.row_source_metadata(target_row)
        source_template_values = self.row_template_values(source_row)
        target_template_values = self.row_template_values(target_row)
        with blokir_signal_sementara(self):
            source_values = self._row_values(source_row)
            target_values = self._row_values(target_row)
            self._set_row_values(source_row, target_values)
            self._set_row_values(target_row, source_values)
            self.set_row_source_metadata(source_row, target_metadata)
            self.set_row_source_metadata(target_row, source_metadata)
            self.set_row_template_values(source_row, target_template_values)
            self.set_row_template_values(target_row, source_template_values)
            source_token = self.row_token(source_row)
            target_token = self.row_token(target_row)
            self.set_row_token(source_row, target_token)
            self.set_row_token(target_row, source_token)
            self.renumber_rows()

        self.setCurrentCell(target_row, max(self.currentColumn(), 0))
        self.sheetEdited.emit()

    def clear_all_rows(self):
        if not self._boleh_mutasi():
            return
        with blokir_signal_sementara(self):
            self.setRowCount(1)
            for column in range(self.columnCount()):
                self.setItem(0, column, buat_tabel_item(""))
            self.renumber_rows()
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

        boleh_mutasi = self._boleh_mutasi()
        for action in (
            act_insert_above,
            act_insert_below,
            act_duplicate,
            act_paste,
            act_clear,
            act_delete,
        ):
            action.setEnabled(boleh_mutasi)

        context_widget = getattr(self, "_context_widget", None) or self.viewport()
        selected = menu.exec(context_widget.mapToGlobal(position))
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


class InvoiceSheet(InvoiceSheetContainer):
    """Tampilan Univer dengan InvoiceSheetModel sebagai sumber data Python."""

    def __init__(self, parent=None):
        super().__init__(InvoiceSheetModel, parent)

# DIALOG PENGATURAN KOLOM


# TAB INVOICE

class DialogPilihClientBilling(QDialog):
    def __init__(self, list_resi, parent=None):
        super().__init__(parent)
        terapkan_style_input_global(self)
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
        self.txt_manual.setValidator(UppercaseValidator(self))
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
        terapkan_style_input_global(self)
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
        self.txt_cari.setValidator(UppercaseValidator(self.txt_cari))

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
        pasang_header_wrap(self.tabel)
        parent = self.parentWidget()
        dialog_styles = get_invoice_dialog_styles(
            get_fixed_font_sizes()["subtitle"],
            is_dark=bool(parent and getattr(parent.window(), "current_theme", "light") == "dark"),
        )
        pasang_style_tabel(self.tabel, dialog_styles["table"])
        self.tabel.setColumnCount(12)
        self.tabel.setHorizontalHeaderLabels((
            "✓", "NO. RESI", "CABANG", "TANGGAL", "PENGIRIM", "PENERIMA",
            "TUJUAN", "KOLI", "BERAT", "CBM", "SUBTOTAL", "STATUS",
        ))
        header_item_subtotal = self.tabel.horizontalHeaderItem(self.COL_ONGKIR)
        if header_item_subtotal is not None:
            header_item_subtotal.setToolTip(
                "Dasar tagihan yang dimasukkan ke Invoice. PPN dihitung sekali "
                "dari subtotal gabungan Invoice."
            )
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
        self.lbl_ringkasan = QLabel("Dipilih: 0 Resi | Subtotal: Rp 0 | Estimasi Invoice: Rp 0")
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

    @db_service.profile_performance("Invoice.load_unbilled_resi", threshold=0.05)
    def muat_data(self, *_):
        kode_cabang, semua_cabang = self._scope_cabang()
        gunakan_periode = self.chk_periode.isChecked()
        try:
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
            )
            if not isinstance(rows, (list, tuple)):
                raise TypeError("Hasil Billing Queue harus berupa daftar Resi.")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Gagal Memuat Billing Queue",
                f"Data Resi belum dapat dimuat:\n{exc}",
            )
            return False

        self.tabel.setUpdatesEnabled(False)
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

                subtotal = _subtotal_resi_untuk_invoice(data)
                subtotal_display = (
                    f"Rp {format_ke_rupiah(subtotal)}"
                    if subtotal is not None else ""
                )
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
                    subtotal_display,
                    data.get("status_resi", ""),
                )
                for offset, value in enumerate(values, start=1):
                    item = buat_tabel_item(value, editable=False)
                    self.tabel.setItem(row, offset, item)
        self.tabel.setUpdatesEnabled(True)
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
        subtotal_per_resi = [_subtotal_resi_untuk_invoice(item) for item in data]
        subtotal = sum(nilai for nilai in subtotal_per_resi if nilai is not None)
        belum_diisi = sum(nilai is None for nilai in subtotal_per_resi)
        jenis_pajak = {
            str(item.get("jenis_pajak") or "NONPAJAK").strip().upper()
            for item in data
        }

        if len(jenis_pajak) > 1:
            self.lbl_ringkasan.setText(
                f"Dipilih: {len(data)} Resi | Subtotal tercatat: Rp {format_ke_rupiah(subtotal)}"
                " | Campuran PAJAK/NONPAJAK — pisahkan pilihan"
            )
            return

        tax_name = next(iter(jenis_pajak), "NONPAJAK")
        tax_rate = Decimal("0.011") if tax_name.startswith("PAJAK") else Decimal("0")
        with localcontext() as context:
            context.prec = max(28, len(str(subtotal)) + 8)
            tax_value = int(
                (Decimal(subtotal) * tax_rate).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
        total_invoice = subtotal + tax_value
        label_pajak = f"PPN: Rp {format_ke_rupiah(tax_value)}" if tax_rate else "NONPAJAK"
        status_estimasi = "Estimasi sementara" if belum_diisi else "Estimasi Invoice"
        self.lbl_ringkasan.setText(
            f"Dipilih: {len(data)} Resi | Subtotal tercatat: Rp {format_ke_rupiah(subtotal)}"
            f" | {label_pajak} | {status_estimasi}: "
            f"Rp {format_ke_rupiah(total_invoice)}"
        )

    def _terima_pilihan(self):
        self._selected_data = self._data_terpilih()
        if not self._selected_data:
            QMessageBox.warning(self, "Peringatan", "Pilih minimal satu Resi terlebih dahulu.")
            return
        self.accept()

    def selected_data(self):
        return [dict(item) for item in self._selected_data]


class TabInvoice(QWidget):
    KOL_HISTORI_NO_WORKBOOK = 0
    KOL_HISTORI_TANGGAL = 1
    KOL_HISTORI_CLIENT = 2
    KOL_HISTORI_JUMLAH_SHEET = 3
    KOL_HISTORI_TOTAL = 4
    KOL_HISTORI_SISA = 5
    KOL_HISTORI_STATUS = 6

    SETTINGS_ORGANIZATION = "AplikasiEkspedisi"
    SETTINGS_APPLICATION_HISTORI = "TabInvoiceHistori"
    SETTINGS_KEY_LEBAR_HISTORI = "lebar_kolom"
    MIN_LEBAR_KOLOM = 20
    MAX_LEBAR_KOLOM = 1500

    def __init__(self):
        super().__init__()
        self.no_invoice_aktif = None
        self.workbook_id_aktif = None
        self.no_workbook_aktif = None
        self._workbook_mode_active = False
        self._workbook_dirty = False
        self._active_workbook_sheet_id = ""
        self._workbook_sheet_meta = {}
        self._workbook_sheet_payment = {}
        self._pending_workbook_capture = False
        self.total_invoice_aktif = 0
        self.status_invoice_aktif = "DRAFT"

        self._sedang_memuat_item = False
        self._sedang_menghitung = False
        self._sedang_menyimpan_invoice = False
        self._dirty = False
        self._loading_invoice = False
        self._data_loaded = False
        self._invoice_dari_resi = False
        self._source_resi = []
        self._created_by_name = ""
        self._created_by_username = ""
        self._payment_info_snapshot = ""
        self._template_switch_pending = False
        self._last_applied_template_name = "Standar"

        # Debounce Timer untuk Pencarian Histori Invoice (250ms)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.load_histori_invoice)

        self.template_configs = deepcopy(INVOICE_TEMPLATES)
        self.current_template_override = None
        self.active_template = deepcopy(self.template_configs["Standar"])
        self.active_columns = deepcopy(self.active_template["columns"])
        self.headers_aktif = [column["title"] for column in self.active_columns]

        self.init_ui()

    def init_ui(self):
        layout_utama = QHBoxLayout(self)
        layout_utama.setContentsMargins(8, 8, 8, 8)

        self._bangun_panel_histori_invoice()
        self._bangun_panel_editor_invoice()

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(self.panel_kiri)
        self.splitter.addWidget(self.panel_kanan)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([340, 1000])
        self.splitter.setHandleWidth(1)

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

        self.lbl_title_histori = QLabel("Histori Workbook Invoice")
        self.txt_cari_invoice = self._buat_lineedit_invoice(
            "Cari invoice...", UppercaseValidator(self),
        )

        self.tabel_histori_invoice = QTableWidget()
        pasang_header_wrap(self.tabel_histori_invoice)
        self.tabel_histori_invoice.setColumnCount(7)
        self.tabel_histori_invoice.setHorizontalHeaderLabels(
            ["NO. WORKBOOK", "TANGGAL", "CLIENT", "INVOICE", "TOTAL", "SISA", "STATUS"],
        )
        self.tabel_histori_invoice.verticalHeader().setVisible(False)
        self.tabel_histori_invoice.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.tabel_histori_invoice.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        self.tabel_histori_invoice.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu,
        )
        self.tabel_histori_invoice.customContextMenuRequested.connect(
            self._tampilkan_context_menu_histori_invoice,
        )
        self.tabel_histori_invoice.setAlternatingRowColors(True)
        header = self.tabel_histori_invoice.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        btn_baru_kiri = QPushButton("＋ Workbook Baru")
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

        self._invoice_lunas_locked = False
        self._invoice_dibatalkan = False
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

        self.txt_catatan = self._buat_lineedit_invoice(
            "Catatan invoice, minimum charge, biaya bongkar, dll.",
            validator_kapital,
        )

        inputs = (
            self.txt_client,
            self.txt_ship_to,
            self.txt_no_invoice,
            self.date_invoice,
            self.cmb_tipe_invoice,
            self.cmb_pajak,
            self.txt_catatan,
        )
        atur_tinggi_input(inputs)

        fields = (
            ("Bill To", self.txt_client, 0, 0, 1, 1),
            ("Ship To", self.txt_ship_to, 0, 2, 1, 1),
            ("No. Invoice", self.txt_no_invoice, 1, 0, 1, 1),
            ("Tanggal", self.date_invoice, 1, 2, 1, 1),
            ("Template", self.cmb_tipe_invoice, 2, 0, 1, 1),
            ("Pajak", self.cmb_pajak, 2, 2, 1, 1),
            ("Catatan", self.txt_catatan, 3, 0, 1, 3),
        )
        for label, widget, row, col, row_span, value_span in fields:
            grid.addWidget(QLabel(label), row, col)
            value_col = col + 1
            grid.addWidget(widget, row, value_col, row_span, value_span)

        layout.addWidget(group_header)

    def _bangun_toolbar_invoice(self, layout):
        # Hanya aksi khusus Kargo yang berada di luar editor.
        # Perubahan struktur sheet native Univer disinkronkan oleh InvoiceSheetContainer
        # ke active_columns dan template_config; kolom subtotal tetap dilindungi.
        # Baris/kolom, paste, clear, dan format memakai UI native Univer.
        toolbar = QHBoxLayout()
        self.btn_ambil_resi = QPushButton("Ambil Resi")
        self.btn_catat_pembayaran = QPushButton("Catat Pembayaran")
        self.btn_riwayat_pembayaran = QPushButton("Riwayat Pembayaran")
        self.btn_catat_pembayaran.setEnabled(False)
        self.btn_riwayat_pembayaran.setEnabled(False)
        toolbar.addWidget(self.btn_ambil_resi)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_riwayat_pembayaran)
        toolbar.addWidget(self.btn_catat_pembayaran)
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
        """Aksi utama Invoice: simpan data atau buka satu alur Print Preview."""
        hbox = QHBoxLayout()
        self.btn_simpan_db = QPushButton("💾 Simpan Workbook")
        self.btn_cetak = QPushButton("🖨️ Cetak Invoice")
        # Page Setup dibuka dari tab tambahan di ribbon Univer. Tombol Cetak
        # tidak lagi memiliki dropdown dan selalu langsung membuka Preview.
        self.btn_cetak.setEnabled(not bool(getattr(self, "_invoice_dibatalkan", False)))
        self._update_print_menu_state()

        hbox.addStretch()
        hbox.addWidget(self.btn_simpan_db)
        hbox.addWidget(self.btn_cetak)
        layout.addLayout(hbox)

    def _hubungkan_signal_invoice(self):
        self.txt_cari_invoice.textChanged.connect(lambda: self._search_timer.start())
        self.tabel_histori_invoice.itemDoubleClicked.connect(
            self.buka_invoice_dari_histori,
        )
        self.tabel_item_invoice.itemChanged.connect(self._on_table_item_changed)
        self.tabel_item_invoice.sheetEdited.connect(self._on_sheet_bulk_edited)
        self.cmb_tipe_invoice.currentIndexChanged.connect(self._on_template_changed)
        self.cmb_pajak.currentIndexChanged.connect(self.ubah_rekening_otomatis)
        self.btn_catat_pembayaran.clicked.connect(self.buka_dialog_catat_pembayaran)
        self.btn_riwayat_pembayaran.clicked.connect(self.tampilkan_riwayat_pembayaran)

        for field in (
            self.txt_client,
            self.txt_ship_to,
            self.txt_no_invoice,
            self.txt_catatan,
        ):
            field.textChanged.connect(self._on_metadata_changed)
        self.date_invoice.dateChanged.connect(self._on_metadata_changed)

        self.btn_ambil_resi.clicked.connect(self.buka_billing_queue)
        self.btn_simpan_db.clicked.connect(self.simpan_invoice_ke_db)
        self.btn_cetak.clicked.connect(self.tampilkan_preview)

    def _inisialisasi_invoice_ui(self):
        # Zoom global Ctrl+Scroll sengaja tidak dipasang pada tab Invoice.
        # Area spreadsheet Univer mengelola zoom-nya sendiri.
        self.load_lebar_kolom_histori(self.tabel_histori_invoice)
        self.tabel_histori_invoice.horizontalHeader().sectionResized.connect(
            lambda *_: self.simpan_lebar_kolom_histori(self.tabel_histori_invoice)
        )
        self.apply_template(preserve_rows=False)
        self._set_rekening_otomatis(tandai_perubahan=False)
        self.sesuaikan_tema_lokal()
        self.refresh_session_ui()

    def refresh_session_ui(self):
        self._data_loaded = self.load_histori_invoice()
        return self._data_loaded

    def showEvent(self, event):
        super().showEvent(event)
        if not self._data_loaded:
            self.refresh_session_ui()

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
        # Lebar histori disimpan apa adanya; tidak ada konversi faktor zoom.
        try:
            lebar_kolom = [
                min(
                    max(self.MIN_LEBAR_KOLOM, int(tabel.columnWidth(index))),
                    self.MAX_LEBAR_KOLOM,
                )
                for index in range(tabel.columnCount())
            ]
            settings = self._settings_histori()
            settings.setValue(self.SETTINGS_KEY_LEBAR_HISTORI, lebar_kolom)
            settings.sync()
        except (TypeError, ValueError, RuntimeError) as exc:
            print(f"Gagal menyimpan lebar kolom histori: {exc}")

    def load_lebar_kolom_histori(self, tabel):
        lebar_default = [
            tabel.columnWidth(index)
            for index in range(tabel.columnCount())
        ]
        lebar_tersimpan = self._normalisasi_lebar_kolom(
            self._settings_histori().value(self.SETTINGS_KEY_LEBAR_HISTORI),
            tabel.columnCount(),
        )
        lebar_dasar = lebar_tersimpan or lebar_default

        try:
            header = tabel.horizontalHeader()
            with blokir_signal_sementara(header):
                for index, width in enumerate(lebar_dasar):
                    tabel.setColumnWidth(index, int(width))
        except (TypeError, ValueError, RuntimeError) as exc:
            print(f"Gagal memuat lebar kolom histori: {exc}")

    @staticmethod
    def _alignment_tipe_invoice(data_type):
        if data_type in {"currency", "integer", "decimal"}:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if data_type == "date":
            return Qt.AlignmentFlag.AlignCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    @staticmethod
    def _buat_item_tabel(value, column):
        data_type = column.get("type", "text")
        nilai = "" if value is None else str(value)
        if data_type == "text":
            nilai = nilai.upper()

        return buat_tabel_item(
            text=nilai,
            alignment=TabInvoice._alignment_tipe_invoice(data_type),
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
        active_keys = {column.get("key") for column in self.active_columns}
        for row in range(self.tabel_item_invoice.rowCount()):
            row_data = {}
            hidden_values = {
                key: value
                for key, value in self.tabel_item_invoice.row_template_values(row).items()
                if key not in active_keys
            }
            for column_index, column in enumerate(self.active_columns):
                item = self.tabel_item_invoice.item(row, column_index)
                row_data[column["key"]] = item.text() if item else ""

            # KOLI (package) dan QTY (quantity) adalah satu data yang sama:
            # sumbernya tetap kolom koli dari data_resi. Saat berpindah template,
            # salin nilai yang sedang terlihat ke alias template lainnya agar
            # edit manual di salah satu template tidak tertinggal oleh nilai lama.
            has_package = "package" in active_keys
            has_quantity = "quantity" in active_keys
            if has_package and not has_quantity:
                row_data["quantity"] = row_data.get("package", "")
            elif has_quantity and not has_package:
                row_data["package"] = row_data.get("quantity", "")

            if hidden_values:
                row_data["__template_values__"] = hidden_values
            source_metadata = self.tabel_item_invoice.row_source_metadata(row)
            if source_metadata:
                row_data["__source_resi__"] = source_metadata
            has_visible_values = any(
                str(value).strip()
                for key, value in row_data.items()
                if key not in {"__source_resi__", "__template_values__"}
            )
            has_hidden_values = any(str(value).strip() for value in hidden_values.values())
            if has_visible_values or has_hidden_values or source_metadata:
                rows.append(row_data)
        return rows

    def _tambahkan_row_invoice(self, row_data):
        row_data = dict(row_data or {})
        source_metadata = row_data.pop("__source_resi__", None)
        template_values = row_data.pop("__template_values__", {})
        template_values = dict(template_values) if isinstance(template_values, dict) else {}
        active_keys = {column.get("key") for column in self.active_columns}

        # Kompatibilitas dengan detail Invoice lama atau hasil template lain:
        # key yang tidak dikenal template aktif disimpan, bukan dibuang.
        for key, value in row_data.items():
            if key not in active_keys:
                template_values[key] = value

        row = self.tabel_item_invoice.rowCount()
        self.tabel_item_invoice.insertRow(row)
        for column_index, column in enumerate(self.active_columns):
            key = column["key"]
            value = row_data.get(
                key,
                template_values.get(key, row_data.get(column.get("title", ""), "")),
            )
            self.tabel_item_invoice.setItem(
                row,
                column_index,
                self._buat_item_tabel(value, column),
            )

        # Hanya simpan key yang belum punya kolom pada template aktif.
        template_values = {
            key: value for key, value in template_values.items()
            if key not in active_keys
        }
        self.tabel_item_invoice.set_row_template_values(row, template_values)
        if isinstance(source_metadata, dict):
            self.tabel_item_invoice.set_row_source_metadata(row, source_metadata)
        self.tabel_item_invoice.renumber_rows()
        return row

    def _pastikan_baris_invoice(self):
        if self.tabel_item_invoice.rowCount() == 0:
            self.tabel_item_invoice.insertRow(0)
        self.tabel_item_invoice.renumber_rows()

    def _pasang_struktur_template_invoice(self, old_rows):
        self.tabel_item_invoice.invoice_columns = deepcopy(self.active_columns)
        self.tabel_item_invoice.setUpdatesEnabled(False)
        try:
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
                    self.tabel_item_invoice.setColumnWidth(
                        index,
                        int(column.get("width", 110)),
                    )

                for row_data in old_rows:
                    self._tambahkan_row_invoice(row_data)
                self._pastikan_baris_invoice()
        finally:
            self.tabel_item_invoice.setUpdatesEnabled(True)

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
        self._last_applied_template_name = (
            self.cmb_tipe_invoice.currentText() or "Standar"
        )

    def _restore_template_selection(self, template_name):
        combo = self.cmb_tipe_invoice
        previous = combo.blockSignals(True)
        try:
            if template_name and combo.findText(template_name) >= 0:
                combo.setCurrentText(template_name)
        finally:
            combo.blockSignals(previous)

    def _on_template_changed(self, *_):
        if self._loading_invoice or self._invoice_lunas_locked:
            return
        if self._template_switch_pending:
            return

        container = self.tabel_item_invoice
        capture_live_model = getattr(container, "capture_live_model", None)
        if callable(capture_live_model) and bool(getattr(container, "using_univer", False)):
            previous_template = self._last_applied_template_name or "Standar"
            self._template_switch_pending = True
            self.cmb_tipe_invoice.setEnabled(False)

            def _finish_template_switch(payload):
                try:
                    if not payload:
                        self._restore_template_selection(previous_template)
                        QMessageBox.warning(
                            self,
                            "Ganti Template",
                            "Data terbaru dari editor Univer belum berhasil dibaca. "
                            "Template tidak diubah agar data tidak hilang. Silakan coba lagi.",
                        )
                        return

                    self._sedang_memuat_item = True
                    try:
                        apply_live_snapshot = getattr(container, "apply_live_snapshot", None)
                        if not callable(apply_live_snapshot) or not apply_live_snapshot(payload):
                            raise RuntimeError("Snapshot editor tidak dapat diterapkan ke model Invoice.")
                        old_rows = self._capture_rows_by_key()
                    finally:
                        self._sedang_memuat_item = False

                    self.current_template_override = None
                    self.apply_template(preserve_rows=False, rows_override=old_rows)
                    self._mark_dirty()
                except Exception as exc:
                    self._restore_template_selection(previous_template)
                    QMessageBox.warning(
                        self,
                        "Ganti Template",
                        f"Gagal mengambil data terbaru dari editor:\n{exc}\n\n"
                        "Template lama dipertahankan agar data tidak hilang.",
                    )
                finally:
                    self._template_switch_pending = False
                    self.cmb_tipe_invoice.setEnabled(not self._invoice_lunas_locked)

            if capture_live_model(_finish_template_switch):
                return

            # Fallback untuk mode tabel Qt lama / WebEngine yang belum siap.
            self._template_switch_pending = False
            self.cmb_tipe_invoice.setEnabled(not self._invoice_lunas_locked)

        old_rows = self._capture_rows_by_key()
        self.current_template_override = None
        self.apply_template(preserve_rows=False, rows_override=old_rows)
        self._mark_dirty()


    def _column_index_by_key(self, key):
        for index, column in enumerate(self.active_columns):
            if column.get("key") == key:
                return index
        return -1

    def _on_table_item_changed(self, item):
        if self._invoice_lunas_locked:
            return
        if self._sedang_memuat_item or self._sedang_menghitung:
            return

        if 0 <= item.column() < len(self.active_columns):
            column = self.active_columns[item.column()]
            with blokir_signal_sementara(self.tabel_item_invoice):
                self._normalisasi_item_invoice(item, column)
                if column.get("key") == "resi":
                    source_metadata = self.tabel_item_invoice.row_source_metadata(item.row())
                    nomor_sumber = str((source_metadata or {}).get("no_resi") or "").strip().upper()
                    if source_metadata and item.text().strip().upper() != nomor_sumber:
                        self.tabel_item_invoice.set_row_source_metadata(item.row(), None)

        self._apply_formula_for_row(item.row(), edited_column=item.column())
        sync_cell = getattr(self.tabel_item_invoice, "sync_cell", None)
        if callable(sync_cell):
            sync_cell(item.row(), item.column())
        self.hitung_ulang_total_tagihan()
        self._mark_dirty()

    def _normalisasi_item_invoice(self, item, column):
        item.setTextAlignment(self._alignment_tipe_invoice(column.get("type", "text")))
        try:
            value = _normalisasi_nilai_invoice(item.text(), column)
        except ValueError as exc:
            item.setToolTip(str(exc))
        else:
            if item.text() != value:
                item.setText(value)
            item.setToolTip("")

    def _normalisasi_format_item_tabel(self):
        for row in range(self.tabel_item_invoice.rowCount()):
            for column_index, column in enumerate(self.active_columns):
                item = self.tabel_item_invoice.item(row, column_index)
                if item is None:
                    continue
                self._normalisasi_item_invoice(item, column)

    def _on_sheet_bulk_edited(self):
        if self._invoice_lunas_locked:
            return
        if self._sedang_memuat_item:
            return

        with blokir_signal_sementara(self.tabel_item_invoice):
            self._normalisasi_format_item_tabel()
            self._recalculate_all_formulas()

        self.hitung_ulang_total_tagihan()
        self._mark_dirty()

    def _on_metadata_changed(self, *_):
        if self._loading_invoice or self._invoice_lunas_locked:
            return
        self.hitung_ulang_total_tagihan()
        self._mark_dirty()

    def _update_print_menu_state(self):
        """Tombol Cetak membuka Preview; aksi output diatur di dalam Preview."""
        button = getattr(self, "btn_cetak", None)
        if button is None:
            return
        cancelled = bool(getattr(self, "_invoice_dibatalkan", False))
        button.setEnabled(not cancelled)
        button.setToolTip(
            "Invoice BATAL tidak dapat dicetak."
            if cancelled
            else "Buka Print Preview untuk memeriksa, mencetak, menyimpan PDF, atau membagikan Invoice."
        )

    def _mark_dirty(self):
        if self._loading_invoice or self._invoice_lunas_locked:
            return
        self._dirty = True
        if self._workbook_mode_active:
            self._workbook_dirty = True
        self.btn_simpan_db.setEnabled(True)
        self._update_print_menu_state()
        if self._workbook_mode_active:
            self._simpan_meta_sheet_aktif_ke_univer()
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
        # A formula entered directly in Univer takes precedence over the
        # template's legacy Python multiply formula for this row.
        hidden_values = self.tabel_item_invoice.row_template_values(row)
        formula_cells = hidden_values.get("__formula_cells__", {})
        if isinstance(formula_cells, dict) and formula_cells.get(target_key):
            return
        source_indexes = [self._column_index_by_key(key) for key in source_keys]
        target_index = self._column_index_by_key(target_key)
        if target_index < 0 or any(index < 0 for index in source_indexes):
            return
        if edited_column is not None and edited_column not in source_indexes:
            return

        values = []
        for index in source_indexes:
            item = self.tabel_item_invoice.item(row, index)
            text = item.text().strip() if item else ""
            # Jangan menafsirkan operand kosong sebagai nol. Pada template
            # Ritel, nilai ONGKIR dari Resi/manual harus tetap dipertahankan
            # sampai semua sumber rumus (KOLI dan PRICE) benar-benar diisi.
            if not text:
                return
            try:
                values.append(_parse_invoice_number(text, self.active_columns[index].get("type", "decimal")))
            except ValueError:
                return

        with localcontext() as context:
            context.prec = max(28, sum(len(value.as_tuple().digits) for value in values) + 2)
            result = Decimal("1")
            for value in values:
                result *= value
            nilai_akhir = int(result.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        self._sedang_menghitung = True
        try:
            item = self.tabel_item_invoice.item(row, target_index)
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
        refresh = getattr(self.tabel_item_invoice, "refresh_univer", None)
        if callable(refresh):
            refresh()

    def hitung_ulang_total_tagihan(self, *_):
        if self._sedang_memuat_item:
            return

        amount_column = self._column_index_by_key(
            self.active_template.get("amount_key", "amount")
        )
        subtotal = 0
        invalid_amount = False
        formula = self.active_template.get("formula") or {}
        source_indexes = [
            self._column_index_by_key(key) for key in formula.get("sources", [])
        ] if formula.get("operation") == "multiply" else []
        if amount_column >= 0:
            for row in range(self.tabel_item_invoice.rowCount()):
                item = self.tabel_item_invoice.item(row, amount_column)
                try:
                    for index in source_indexes:
                        if index < 0:
                            continue
                        source = self.tabel_item_invoice.item(row, index)
                        _parse_invoice_number(
                            source.text() if source else "",
                            self.active_columns[index].get("type", "decimal"),
                        )
                    subtotal += int(_parse_invoice_number(item.text() if item else "", "currency"))
                except ValueError:
                    invalid_amount = True

        if invalid_amount:
            self.total_invoice_aktif = 0
            self.lbl_subtotal.setText("SUB TOTAL: PERIKSA INPUT ANGKA")
            self.lbl_pajak_nominal.setText("PAJAK: BELUM DIHITUNG")
            self.lbl_total_tagihan.setText("TOTAL TAGIHAN: INPUT BELUM VALID")
            return

        tax_name = self.cmb_pajak.currentText()
        tax_rate = {
            "NONPAJAK": Decimal("0"),
            "PPN 1,1%": Decimal("0.011"),
        }.get(tax_name, Decimal("0"))
        with localcontext() as context:
            context.prec = max(28, len(str(subtotal)) + 8)
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
        try:
            data = muat_pengaturan_sistem()
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            print(f"Gagal memuat data perusahaan untuk invoice: {exc}")
            return {}

    def _payment_info_otomatis(self, jenis_pajak=None):
        """Ambil informasi pembayaran dari data perusahaan yang tersimpan."""
        pengaturan = self._muat_data_perusahaan()
        pajak_dipilih = str(
            jenis_pajak if jenis_pajak is not None else self.cmb_pajak.currentText()
        ).strip().upper()
        key_rekening = (
            "rekening_nonpajak"
            if pajak_dipilih == "NONPAJAK"
            else "rekening_pajak"
        )
        data_rekening = pengaturan.get(key_rekening, [])

        if isinstance(data_rekening, list):
            return " | ".join(
                str(item).strip()
                for item in data_rekening
                if str(item).strip()
            ).upper()
        if isinstance(data_rekening, str):
            return data_rekening.strip().upper()
        return ""

    def _set_rekening_otomatis(self, tandai_perubahan=True):
        # Payment info tidak lagi diedit di form Invoice. Nilainya tetap
        # diambil otomatis dari pengaturan perusahaan dan disimpan sebagai
        # snapshot metadata agar invoice lama tetap konsisten saat dibuka.
        self._payment_info_snapshot = self._payment_info_otomatis()
        self.hitung_ulang_total_tagihan()

        if tandai_perubahan:
            self._mark_dirty()

    def ubah_rekening_otomatis(self, *_):
        if self._loading_invoice or self._invoice_lunas_locked:
            return
        self._set_rekening_otomatis(tandai_perubahan=True)

    def _konfirmasi_buang_perubahan(self, tindakan):
        if not self._dirty and not self._workbook_dirty:
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
        # In Workbook mode a paid/cancelled sheet stays locked, but the admin
        # may still open Billing Queue; imported Resi will go to a new sheet.
        if self._invoice_lunas_locked and not (
            self._workbook_mode_active and self.tabel_item_invoice.using_univer
        ):
            return False
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
    def _kota_tujuan_invoice(value):
        """Ambil nama kota dari format tujuan Resi, tanpa nama provinsi."""
        tujuan = " ".join(str(value or "").strip().upper().split())
        if not tujuan:
            return ""

        # Data Resi Kargo saat ini menyimpan tujuan sebagai "PROVINSI - KOTA".
        # Toleransi juga format "KOTA, PROVINSI" dari data historis.
        if " - " in tujuan:
            tujuan = tujuan.rsplit(" - ", 1)[-1]
        elif "," in tujuan:
            tujuan = tujuan.split(",", 1)[0]
        return tujuan.strip()

    @staticmethod
    def _row_invoice_dari_resi(nomor, data):
        subtotal = _subtotal_resi_untuk_invoice(data)
        koli = str(data.get("koli", "0")).strip()
        return {
            "no": str(nomor),
            "resi": str(data.get("no_resi", "")).strip().upper(),
            "destination": TabInvoice._kota_tujuan_invoice(data.get("tujuan", "")),
            "description": str(data.get("nama_barang", "")).strip().upper(),
            "package": koli,
            "quantity": koli,
            "weight": str(data.get("berat", "0")).strip(),
            "volume": str(data.get("kubik", "0")).strip(),
            # Nominal yang sudah tercatat dibawa ke Invoice; bila kosong, input dilakukan di Invoice.
            "amount": "" if subtotal is None else str(subtotal),
            "__source_resi__": {
                "no_resi": str(data.get("no_resi") or "").strip().upper(),
                "kode_cabang": str(data.get("kode_cabang") or "").strip().upper() or None,
                "revision": data.get("revision"),
            },
        }

    def terima_data_baru(self, nama_client, list_resi_data):
        if self._invoice_lunas_locked and not (
            self._workbook_mode_active and self.tabel_item_invoice.using_univer
        ):
            return False
        data_resi = [
            dict(item) for item in (list_resi_data or []) if isinstance(item, dict)
        ]
        if not data_resi:
            QMessageBox.warning(
                self,
                "Data Resi Tidak Valid",
                "Tidak ada data Resi yang dapat dimasukkan ke Invoice.",
            )
            return False

        jenis_pajak = {
            str(item.get("jenis_pajak") or "NONPAJAK").strip().upper()
            for item in data_resi
        }
        if len(jenis_pajak) > 1:
            QMessageBox.warning(
                self,
                "Invoice Tidak Dapat Diproses",
                "Resi yang dipilih mengandung campuran PAJAK dan NONPAJAK.\n\n"
                "Satu Invoice hanya boleh berisi satu jenis pajak.\n"
                "Silakan pilih Resi dengan jenis pajak yang sama.",
            )
            return False

        jenis_pajak_sumber = next(iter(jenis_pajak), "NONPAJAK")

        for item in data_resi:
            no_resi = str(item.get("no_resi") or "").strip().upper()
            expected_revision = item.get("revision")
            if not no_resi or expected_revision in (None, ""):
                continue
            ok_revision, revision_sekarang = db_service.cek_revision_resi(
                no_resi,
                expected_revision,
                item.get("kode_cabang"),
            )
            if not ok_revision:
                tampil_revision = (
                    "tidak ditemukan"
                    if revision_sekarang is None
                    else str(revision_sekarang)
                )
                QMessageBox.warning(
                    self,
                    "Data Resi Sudah Berubah",
                    f"Resi {no_resi} sudah berubah sejak dipilih.\n\n"
                    f"Revision saat dipilih: {expected_revision}\n"
                    f"Revision saat ini: {tampil_revision}\n\n"
                    "Invoice tidak dapat diproses dari data lama. Silakan refresh data Resi "
                    "lalu pilih kembali.",
                )
                return False

        nama_client_bersih = str(nama_client or "").strip().upper()
        in_workbook = bool(
            self._workbook_mode_active
            and self._active_workbook_sheet_id
            and self.tabel_item_invoice.using_univer
        )
        if in_workbook:
            client_workbook = str(self.txt_client.text() or "").strip().upper()
            if client_workbook and client_workbook != nama_client_bersih:
                QMessageBox.warning(
                    self,
                    "Customer Berbeda",
                    "Workbook ini sudah dimiliki customer "
                    f"{client_workbook}. Resi dari {nama_client_bersih} tidak dapat "
                    "dimasukkan ke Workbook yang sama.",
                )
                return False

            has_visible_data = any(
                (self.tabel_item_invoice.item(row, column) is not None
                 and bool(self.tabel_item_invoice.item(row, column).text().strip()))
                for row in range(self.tabel_item_invoice.rowCount())
                for column in range(self.tabel_item_invoice.columnCount())
            )
            needs_new_sheet = bool(
                self.no_invoice_aktif or has_visible_data or self._invoice_lunas_locked
            )
            if needs_new_sheet:
                # Do not replace a previous invoice sheet. Capture the complete
                # workbook, insert a new draft, then populate that new sheet.
                def _populate_new_sheet():
                    self._isi_sheet_aktif_dari_resi(
                        nama_client_bersih, data_resi, jenis_pajak_sumber
                    )

                if not self.tambah_invoice_sheet(on_added=_populate_new_sheet):
                    return False
                return True
            return self._isi_sheet_aktif_dari_resi(
                nama_client_bersih, data_resi, jenis_pajak_sumber
            )

        if not self.buat_invoice_baru():
            return False
        return self._isi_sheet_aktif_dari_resi(
            nama_client_bersih, data_resi, jenis_pajak_sumber
        )

    def _isi_sheet_aktif_dari_resi(self, nama_client, data_resi, jenis_pajak_sumber):
        """Isi satu sheet aktif dari Billing Queue tanpa mereset workbook induk."""
        self.no_invoice_aktif = None
        self.txt_no_invoice.clear()
        self.status_invoice_aktif = "DRAFT"
        self._dirty = False
        self._source_resi = [
            {
                "no_resi": str(item.get("no_resi") or "").strip().upper(),
                "kode_cabang": str(item.get("kode_cabang") or "").strip().upper() or None,
                "revision": item.get("revision"),
            }
            for item in data_resi
            if str(item.get("no_resi") or "").strip()
        ]
        self._loading_invoice = True
        try:
            self._invoice_dari_resi = True
            self.txt_client.setText(str(nama_client or "").strip().upper())
            self.cmb_tipe_invoice.setCurrentText("Standar")
            self.current_template_override = None
            self.apply_template(preserve_rows=False)
            self._sedang_memuat_item = True

            self.tabel_item_invoice.setUpdatesEnabled(False)
            with blokir_signal_sementara(self.tabel_item_invoice):
                self.tabel_item_invoice.setRowCount(0)
                for nomor, data in enumerate(data_resi, start=1):
                    self._tambahkan_row_invoice(
                        self._row_invoice_dari_resi(nomor, data)
                    )
                self._pastikan_baris_invoice()
        finally:
            self.tabel_item_invoice.setUpdatesEnabled(True)
            self._sedang_memuat_item = False
            self._loading_invoice = False

        self._source_resi = self._source_resi_dari_tabel()
        self.cmb_pajak.setCurrentText(
            "PPN 1,1%" if jenis_pajak_sumber == "PAJAK" else "NONPAJAK"
        )
        self.cmb_pajak.setEnabled(False)
        self._set_rekening_otomatis(tandai_perubahan=False)
        self.hitung_ulang_total_tagihan()
        self._mark_dirty()
        return True

    def _generate_no_invoice(self):
        try:
            result = numbering_service.peek_next_number(
                "INVOICE",
                numbering_service.CENTRAL_INVOICE_BRANCH,
                tanggal=self.date_invoice.date().toString("yyyy-MM-dd"),
            )
            return result.nomor
        except Exception as exc:
            print(f"Gagal membaca nomor invoice fixed: {exc}")
            return ""

    def _prefix_no_invoice_otomatis(self):
        # Kompatibilitas modul lama; bukan sumber aturan nomor.
        return "INV-MKT-SUB"

    def _source_resi_dari_tabel(self):
        """Ambil identitas Resi yang benar-benar masih terwakili oleh baris tabel."""
        hasil = []
        seen = set()
        tabel = self.tabel_item_invoice
        resi_column = self._column_index_by_key("resi")
        for row in range(tabel.rowCount()):
            metadata = tabel.row_source_metadata(row)
            if metadata:
                nomor = str(metadata.get("no_resi") or "").strip().upper()
                cabang = str(metadata.get("kode_cabang") or "").strip().upper() or None
                revision = metadata.get("revision")
            else:
                resi_item = tabel.item(row, resi_column) if resi_column >= 0 else None
                nomor = str(resi_item.text() if resi_item else "").strip().upper()
                cabang = None
                revision = None

            if not nomor:
                continue
            key = (nomor, cabang)
            if key in seen:
                continue
            seen.add(key)
            hasil.append({
                "no_resi": nomor,
                "kode_cabang": cabang,
                "revision": revision,
            })
        return hasil

    def _metadata_dict(self):
        metadata = {
            "ship_to": self.txt_ship_to.text().strip().upper(),
            "payment_info": str(self._payment_info_snapshot or "").strip().upper(),
            "notes": self.txt_catatan.text().strip().upper(),
        }
        if self.current_template_override:
            metadata["template_config"] = self.current_template_override
        get_snapshot = getattr(self.tabel_item_invoice, "get_univer_snapshot", None)
        if callable(get_snapshot):
            snapshot = get_snapshot()
            if isinstance(snapshot, dict):
                metadata["univer_snapshot"] = snapshot
        source_resi = self._source_resi_dari_tabel()
        if source_resi:
            metadata["source_resi"] = source_resi
        return metadata

    def ambil_data_item_invoice(self):
        items = []
        amount_key = self.active_template.get("amount_key", "amount")
        amount_column = self._column_index_by_key(amount_key)

        for row in range(self.tabel_item_invoice.rowCount()):
            row_data = {}
            for column_index, column in enumerate(self.active_columns):
                item = self.tabel_item_invoice.item(row, column_index)
                value = item.text().strip() if item else ""
                if column.get("type", "text") == "text":
                    value = value.upper()
                row_data[column["key"]] = value

            hidden_values = self.tabel_item_invoice.row_template_values(row)
            if not any(row_data.values()) and not any(hidden_values.values()):
                continue
            if hidden_values:
                row_data["__template_values__"] = hidden_values

            amount_item = self.tabel_item_invoice.item(
                row,
                amount_column,
            ) if amount_column >= 0 else None

            nominal = int(_parse_invoice_number(amount_item.text() if amount_item else "", "currency"))
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
        is_new = self.no_invoice_aktif is None
        no_invoice = "" if is_new else (self.no_invoice_aktif or manual_number)
        if not is_new and not no_invoice:
            raise ValueError("Nomor invoice tidak berhasil dibuat.")
        auto_prefix = ""

        return no_invoice, {
            "no_invoice": no_invoice,
            "auto_invoice_prefix": auto_prefix,
            "tanggal": self.date_invoice.date().toString("yyyy-MM-dd"),
            "client": client,
            "tipe_invoice": self.cmb_tipe_invoice.currentText(),
            "jenis_pajak": self.cmb_pajak.currentText(),
            "subtotal": sum(item["nominal"] for item in items),
            "total_akhir": self.total_invoice_aktif,
            "status": self.status_invoice_aktif,
            "metadata_json": json.dumps(self._metadata_dict(), ensure_ascii=False),
            "source_resi": self._source_resi_dari_tabel(),
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
        self._update_print_menu_state()
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
        if not self._validasi_data_invoice(untuk_simpan=True):
            return None
        client = self.txt_client.text().strip().upper()
        items = self.ambil_data_item_invoice()
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

    def _validasi_data_invoice(self, untuk_simpan=False):
        if self._invoice_lunas_locked and untuk_simpan:
            QMessageBox.warning(
                self,
                "Invoice Terkunci",
                "Invoice berstatus LUNAS tidak dapat diubah atau disimpan ulang.",
            )
            return False
        tabel = self.tabel_item_invoice
        editor = QApplication.focusWidget()
        if isinstance(editor, QLineEdit) and tabel.isAncestorOf(editor):
            tabel.commitData(editor)

        if untuk_simpan and not self.txt_client.text().strip():
            QMessageBox.warning(self, "Peringatan", "Nama client / Bill To tidak boleh kosong.")
            self.txt_client.setFocus()
            return False

        amount_key = self.active_template.get("amount_key", "amount")
        if self._column_index_by_key(amount_key) < 0:
            QMessageBox.warning(self, "Kolom Total", "Kolom subtotal dari template tidak ditemukan. Pastikan kolom ONGKIR/AMOUNT masih tersedia.")
            return False

        pending = []
        for row in range(tabel.rowCount()):
            for index, column in enumerate(self.active_columns):
                item = tabel.item(row, index)
                if item is None:
                    continue
                try:
                    value = _normalisasi_nilai_invoice(item.text(), column)
                    if column.get("key") == amount_key:
                        _parse_invoice_number(value, "currency")
                except ValueError as exc:
                    tabel.setCurrentCell(row, index)
                    tabel.scrollToItem(item)
                    QMessageBox.warning(
                        self, "Input Invoice Belum Valid",
                        f"Baris {row + 1}, kolom {column.get('title', index + 1)}:\n{exc}",
                    )
                    tabel.setFocus()
                    return False
                pending.append((item, value))

        changed = False
        with blokir_signal_sementara(tabel):
            for item, value in pending:
                if item.text() != value:
                    item.setText(value)
                    changed = True
        if changed:
            self._mark_dirty()
        self.hitung_ulang_total_tagihan()
        return True

    def simpan_invoice_ke_db(self):
        if self._sedang_menyimpan_invoice:
            return
        if self._invoice_lunas_locked and not (
            self._workbook_mode_active and self._workbook_dirty
        ):
            QMessageBox.information(
                self, "Invoice Terkunci",
                "Sheet ini sudah LUNAS/BATAL. Tambah sheet baru untuk membuat tagihan berikutnya.",
            )
            return
        if not self.txt_client.text().strip():
            QMessageBox.warning(self, "Data Belum Lengkap", "Nama customer / Bill To wajib diisi.")
            self.txt_client.setFocus()
            return
        if self.tabel_item_invoice.using_univer and callable(getattr(self.tabel_item_invoice, "capture_workbook", None)):
            self._sedang_menyimpan_invoice = True
            self._pending_workbook_capture = True
            self.btn_simpan_db.setEnabled(False)

            def _captured(raw_payload):
                try:
                    if not raw_payload:
                        raise ValueError("Univer tidak mengembalikan snapshot workbook.")
                    payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
                    if not isinstance(payload, dict):
                        raise ValueError("Format snapshot workbook tidak valid.")
                    self._simpan_payload_workbook(payload)
                except Exception as exc:
                    QMessageBox.critical(self, "Workbook Tidak Tersimpan", f"Gagal memproses workbook invoice:\n{exc}")
                finally:
                    self._pending_workbook_capture = False
                    self._sedang_menyimpan_invoice = False
                    self.btn_simpan_db.setEnabled(
                        (not self._invoice_lunas_locked) and (self._dirty or self._workbook_dirty)
                    )

            if not self.tabel_item_invoice.capture_workbook(_captured):
                self._pending_workbook_capture = False
                self._sedang_menyimpan_invoice = False
                self.btn_simpan_db.setEnabled(True)
                QMessageBox.warning(self, "Univer Belum Siap", "Editor Univer belum siap untuk mengambil snapshot workbook.")
            return

        # Fallback apabila Qt WebEngine/Univer tidak tersedia: simpan invoice
        # tunggal melalui jalur lama, tetapi tetap otomatis menjadi workbook 1 sheet.
        prepared = self._siapkan_simpan_invoice()
        if prepared is None:
            return
        no_invoice, header_data, items = prepared
        self._sedang_menyimpan_invoice = True
        self.btn_simpan_db.setEnabled(False)
        try:
            sukses, pesan = db_service.simpan_atau_update_invoice(
                header_data, items, self.no_invoice_aktif is not None,
            )
            if not sukses:
                self._tampilkan_gagal_simpan_invoice(pesan)
                return
            nomor_tersimpan = str(header_data.get("no_invoice") or no_invoice).strip().upper()
            self._tandai_invoice_tersimpan(nomor_tersimpan)
            self._workbook_dirty = False
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Gagal menyimpan invoice:\n{exc}")
        finally:
            self._sedang_menyimpan_invoice = False
            self.btn_simpan_db.setEnabled(
                (not self._invoice_lunas_locked) and (self._dirty or self._workbook_dirty)
            )

    @staticmethod
    def _parse_meta_json(value):
        try:
            parsed = json.loads(value or "{}") if isinstance(value, str) else value
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}

    def _meta_sheet_aktif_dari_form(self, base=None):
        meta = dict(base or {})
        meta.update({
            "no_invoice": str(self.no_invoice_aktif or ""),
            "status": str(self.status_invoice_aktif or "DRAFT").upper(),
            "template_name": self.cmb_tipe_invoice.currentText(),
            "template_config": deepcopy(self.active_template),
            "client": self.txt_client.text().strip().upper(),
            "tanggal": self.date_invoice.date().toString("yyyy-MM-dd"),
            "jenis_pajak": self.cmb_pajak.currentText().strip().upper(),
            "ship_to": self.txt_ship_to.text().strip().upper(),
            "payment_info": str(self._payment_info_snapshot or "").strip().upper(),
            "notes": self.txt_catatan.text().strip().upper(),
            "source_resi": self._source_resi_dari_tabel(),
            "paid_total": int(meta.get("paid_total") or 0),
            "sheet_name": str(meta.get("sheet_name") or "Sheet 1"),
        })
        return meta

    def _simpan_meta_sheet_aktif_ke_univer(self):
        sheet_id = str(self._active_workbook_sheet_id or "").strip()
        if not sheet_id:
            return
        meta = self._meta_sheet_aktif_dari_form(self._workbook_sheet_meta.get(sheet_id))
        self._workbook_sheet_meta[sheet_id] = meta
        setter = getattr(self.tabel_item_invoice, "set_invoice_sheet_meta", None)
        if callable(setter):
            setter(sheet_id, meta)

    def _on_workbook_sheet_activated(self, sheet_id, sheet_name, sheet_meta, columns):
        # Every Univer workbook (including a fresh one-sheet draft) uses this
        # state machine. Legacy invoice numbers are opened through their parent
        # workbook, so a sheet activation always establishes a stable sheet ID.
        self._workbook_mode_active = True
        sheet_id = str(sheet_id or "").strip()
        if not sheet_id:
            return
        old_id = str(self._active_workbook_sheet_id or "").strip()
        if old_id and old_id != sheet_id:
            old_meta = self._meta_sheet_aktif_dari_form(self._workbook_sheet_meta.get(old_id))
            self._workbook_sheet_meta[old_id] = old_meta
            # Keep the metadata inside the matching native Univer sheet in step
            # with the form. Workbook capture reads sheet metadata from JS, so
            # updating only the Python cache could otherwise persist stale data.
            setter = getattr(self.tabel_item_invoice, "set_invoice_sheet_meta", None)
            if callable(setter):
                setter(old_id, old_meta)

        meta = dict(sheet_meta or {})
        if not meta:
            meta = dict(self._workbook_sheet_meta.get(sheet_id) or {})
        meta.setdefault("sheet_name", str(sheet_name or "Sheet"))
        meta.setdefault("status", "DRAFT")
        meta.setdefault("template_name", self.cmb_tipe_invoice.currentText() or "Standar")
        if meta.get("is_new_sheet"):
            # Native Univer '+' creates an unsaved draft sheet. Carry the
            # currently selected template/config instead of defaulting to Standar.
            meta["template_name"] = str(self.cmb_tipe_invoice.currentText() or meta.get("template_name") or "Standar")
            meta["template_config"] = deepcopy(self.active_template)
            meta.setdefault("client", self.txt_client.text().strip().upper())
            meta.setdefault("tanggal", self.date_invoice.date().toString("yyyy-MM-dd"))
            meta.setdefault("jenis_pajak", self.cmb_pajak.currentText().strip().upper())
            meta.setdefault("ship_to", self.txt_ship_to.text().strip().upper())
            meta.setdefault("payment_info", str(self._payment_info_snapshot or "").strip().upper())
            meta.setdefault("notes", self.txt_catatan.text().strip().upper())
            self._workbook_dirty = True
        meta["sheet_name"] = str(sheet_name or meta.get("sheet_name") or "Sheet")
        template_name = str(meta.get("template_name") or "Standar")
        template_config = meta.get("template_config")
        if not isinstance(template_config, dict):
            template_config = deepcopy(
                self.template_configs.get(template_name, self.template_configs["Custom / Bebas"])
            )
        else:
            template_config = deepcopy(template_config)
        if isinstance(columns, list) and columns:
            template_config["columns"] = deepcopy(columns)
        self.active_template = template_config
        self.active_columns = deepcopy(template_config.get("columns") or [])
        self.headers_aktif = [str(col.get("title") or col.get("key") or "") for col in self.active_columns]
        self.current_template_override = deepcopy(template_config) if template_config.get("customized") else None

        self._active_workbook_sheet_id = sheet_id
        self._workbook_sheet_meta[sheet_id] = meta
        setter = getattr(self.tabel_item_invoice, "set_invoice_sheet_meta", None)
        if callable(setter):
            setter(sheet_id, meta)
        self.no_invoice_aktif = str(meta.get("no_invoice") or "").strip().upper() or None
        self.status_invoice_aktif = str(meta.get("status") or "DRAFT").strip().upper()
        self.total_invoice_aktif = int(meta.get("total_akhir") or 0)
        self._created_by_name = str(meta.get("created_by_name") or meta.get("created_by_username") or "").strip()
        self._created_by_username = str(meta.get("created_by_username") or "").strip().upper()

        self._loading_invoice = True
        try:
            client = str(meta.get("client") or self.txt_client.text()).strip().upper()
            self.txt_client.setText(client)
            self.txt_no_invoice.setText(self.no_invoice_aktif or "")
            self.txt_ship_to.setText(str(meta.get("ship_to") or "").strip().upper())
            self.txt_catatan.setText(str(meta.get("notes") or "").strip().upper())
            self._payment_info_snapshot = str(meta.get("payment_info") or self._payment_info_otomatis(meta.get("jenis_pajak"))).strip().upper()
            self.cmb_tipe_invoice.setCurrentText(template_name)
            self.cmb_pajak.setCurrentText(str(meta.get("jenis_pajak") or "NONPAJAK").strip().upper())
            self._source_resi = [dict(item) for item in (meta.get("source_resi") or []) if isinstance(item, dict)]
            self._invoice_dari_resi = bool(self._source_resi)
            self.cmb_pajak.setEnabled(not self._invoice_dari_resi and self.status_invoice_aktif not in {"LUNAS", "BATAL"})
            parsed_date = QDate.fromString(str(meta.get("tanggal") or ""), "yyyy-MM-dd")
            self.date_invoice.setDate(parsed_date if parsed_date.isValid() else QDate.currentDate())
            self._set_invoice_lunas_locked(
                self.status_invoice_aktif in {"LUNAS", "BATAL"},
                dibatalkan=self.status_invoice_aktif == "BATAL",
            )
            self._dirty = False
        finally:
            self._loading_invoice = False
        self.lbl_title_editor.setText(
            f"{self.status_invoice_aktif} INVOICE: {self.no_invoice_aktif or sheet_name}"
        )
        self.btn_catat_pembayaran.setEnabled(bool(self.no_invoice_aktif) and self.status_invoice_aktif not in {"LUNAS", "BATAL"})
        self.btn_riwayat_pembayaran.setEnabled(bool(self.no_invoice_aktif))
        self.btn_simpan_db.setEnabled(bool(self._workbook_dirty or self._dirty))
        self._update_print_menu_state()
        QTimer.singleShot(0, self.hitung_ulang_total_tagihan)

    def _simpan_payload_workbook(self, payload):
        sheets = payload.get("sheets")
        if not isinstance(sheets, list) or not sheets:
            raise ValueError("Workbook harus memiliki minimal satu sheet invoice.")
        workbook_snapshot = payload.get("workbookSnapshot")
        if not isinstance(workbook_snapshot, dict):
            raise ValueError("Snapshot Univer tidak berisi data workbook yang valid.")
        active_sheet_id = str(payload.get("activeSheetId") or self._active_workbook_sheet_id or "")
        sheet_entries = []
        workbook_client = self.txt_client.text().strip().upper()

        for order_index, raw_sheet in enumerate(sheets):
            if not isinstance(raw_sheet, dict):
                continue
            sheet_id = str(raw_sheet.get("sheetId") or "").strip()
            if not sheet_id:
                raise ValueError(f"Identitas sheet ke-{order_index + 1} tidak tersedia.")
            sheet_name = str(raw_sheet.get("sheetName") or f"Sheet {order_index + 1}")
            meta = dict(raw_sheet.get("sheetMeta") or self._workbook_sheet_meta.get(sheet_id) or {})
            if sheet_id == active_sheet_id:
                meta = self._meta_sheet_aktif_dari_form(meta)
            template_name = str(meta.get("template_name") or "Standar")
            template_config = meta.get("template_config")
            if not isinstance(template_config, dict):
                template_config = deepcopy(self.template_configs.get(template_name, self.template_configs["Custom / Bebas"]))
            else:
                template_config = deepcopy(template_config)
            columns = raw_sheet.get("columns") or template_config.get("columns") or []
            if not isinstance(columns, list) or not columns:
                raise ValueError(f"Kolom pada {sheet_name} tidak valid.")
            template_config["columns"] = deepcopy(columns)
            amount_key = str(template_config.get("amount_key") or "amount")
            amount_col = next((col for col in columns if str(col.get("key")) == amount_key), None)
            if amount_col is None:
                raise ValueError(f"Kolom nominal '{amount_key}' tidak ditemukan di {sheet_name}.")

            items = []
            subtotal = 0
            for row_index, raw_row in enumerate(raw_sheet.get("rows") or []):
                if not isinstance(raw_row, dict):
                    continue
                raw_cells = raw_row.get("cells") or {}
                data_row = {}
                row_has_data = False
                amount_value = ""
                for column in columns:
                    key = str(column.get("key") or "")
                    cell = raw_cells.get(key, {}) if isinstance(raw_cells, dict) else {}
                    if not isinstance(cell, dict):
                        cell = {"value": cell}
                    value = cell.get("value", "")
                    value = "" if value is None else str(value).strip()
                    data_row[key] = value
                    if value:
                        row_has_data = True
                    if key == amount_key:
                        amount_value = value
                row_id = str(raw_row.get("id") or "").strip()
                if row_id:
                    data_row["__row_id__"] = row_id
                hidden = raw_row.get("hidden")
                if isinstance(hidden, dict) and hidden:
                    data_row["__template_values__"] = deepcopy(hidden)
                source = raw_row.get("source")
                if isinstance(source, dict) and str(source.get("no_resi") or "").strip():
                    data_row["__source_resi__"] = deepcopy(source)
                    row_has_data = True
                if not row_has_data:
                    continue
                try:
                    nominal = int(_parse_invoice_number(amount_value, "currency"))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Nominal pada {sheet_name}, baris {row_index + 2}: {exc}") from exc
                subtotal += nominal
                items.append({
                    "nomor_urut": row_index + 1,
                    "data_kolom": json.dumps(data_row, ensure_ascii=False),
                    "nominal": nominal,
                })
            tax_name = str(meta.get("jenis_pajak") or "NONPAJAK").strip().upper()
            if not items and str(meta.get("no_invoice") or "").strip():
                raise ValueError(f"Rincian {meta.get('no_invoice')} tidak boleh dikosongkan.")
            tax_value = (
                int((Decimal(subtotal) * Decimal("0.011")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                if items and tax_name == "PPN 1,1%" else 0
            )
            total = subtotal + tax_value
            status = str(meta.get("status") or "DRAFT").strip().upper()
            if not items and not str(meta.get("no_invoice") or "").strip():
                status = "DRAFT"
            if status in {"DRAFT", "BELUM DITAGIH", ""}:
                status = "BELUM LUNAS"
            if status not in {"BELUM LUNAS", "CICILAN", "LUNAS", "BATAL", "MACET"}:
                status = "BELUM LUNAS"
            client = str(meta.get("client") or workbook_client).strip().upper()
            if not client:
                raise ValueError(f"Customer pada {sheet_name} belum diisi.")
            if workbook_client and client != workbook_client:
                raise ValueError("Semua sheet dalam satu Workbook harus memakai customer yang sama.")
            meta.update({
                "sheet_name": sheet_name,
                "template_name": template_name,
                "template_config": template_config,
                "client": client,
                "tanggal": str(meta.get("tanggal") or self.date_invoice.date().toString("yyyy-MM-dd")),
                "jenis_pajak": tax_name,
                "status": status,
                "subtotal": subtotal,
                "total_akhir": total,
            })
            # This sheet is now part of a persisted workbook, not a transient
            # native Univer sheet creation event.
            meta.pop("is_new_sheet", None)
            self._workbook_sheet_meta[sheet_id] = meta
            metadata = {
                "ship_to": str(meta.get("ship_to") or "").strip().upper(),
                "payment_info": str(meta.get("payment_info") or "").strip().upper(),
                "notes": str(meta.get("notes") or "").strip().upper(),
                "template_config": template_config,
                "source_resi": meta.get("source_resi") or [],
            }
            header = {
                "no_invoice": str(meta.get("no_invoice") or "").strip().upper(),
                "tanggal": meta["tanggal"],
                "client": client,
                "tipe_invoice": template_name,
                "jenis_pajak": tax_name,
                "subtotal": subtotal,
                "total_akhir": total,
                "status": status,
                "metadata_json": json.dumps(metadata, ensure_ascii=False),
                "template_version": int(template_config.get("version", 1) or 1),
                "source_resi": meta.get("source_resi") or [],
            }
            sheet_entries.append({
                "sheet_id": sheet_id,
                "sheet_name": sheet_name,
                "header": header,
                "items": items,
            })
        if not sheet_entries:
            raise ValueError("Tidak ada sheet invoice yang dapat disimpan.")

        # Persist business metadata for every sheet in the workbook snapshot,
        # including an empty first-sheet draft that has no invoice_header row yet.
        snapshot_custom = workbook_snapshot.get("custom")
        if not isinstance(snapshot_custom, dict):
            snapshot_custom = {}
            workbook_snapshot["custom"] = snapshot_custom
        snapshot_sheet_meta = snapshot_custom.get("kargoInvoiceSheets")
        if not isinstance(snapshot_sheet_meta, dict):
            snapshot_sheet_meta = {}
        for entry in sheet_entries:
            sheet_id = str(entry["sheet_id"])
            meta = self._workbook_sheet_meta.get(sheet_id)
            if isinstance(meta, dict):
                snapshot_sheet_meta[sheet_id] = deepcopy(meta)
        snapshot_custom["kargoInvoiceSheets"] = snapshot_sheet_meta
        snapshot_custom["kargoActiveSheetId"] = active_sheet_id

        active_meta = self._workbook_sheet_meta.get(active_sheet_id) or {}
        workbook_data = {
            "workbook_id": self.workbook_id_aktif or "",
            "no_workbook": self.no_workbook_aktif or "",
            "client": workbook_client or str(active_meta.get("client") or ""),
            "tanggal": str(active_meta.get("tanggal") or self.date_invoice.date().toString("yyyy-MM-dd")),
            "snapshot_json": json.dumps(workbook_snapshot, ensure_ascii=False),
            "sheet_order_json": json.dumps([entry["sheet_id"] for entry in sheet_entries], ensure_ascii=False),
            "metadata_json": "{}",
        }
        sukses, hasil = db_service.simpan_workbook_invoice(workbook_data, sheet_entries)
        if not sukses:
            self._tampilkan_gagal_simpan_invoice(hasil)
            return False

        self.workbook_id_aktif = hasil.get("workbook_id")
        self.no_workbook_aktif = hasil.get("no_workbook")
        for result_sheet in hasil.get("sheets", []):
            sheet_id = str(result_sheet.get("sheet_id") or "")
            meta = self._workbook_sheet_meta.get(sheet_id, {})
            meta["no_invoice"] = result_sheet.get("no_invoice") or meta.get("no_invoice") or ""
            meta["status"] = result_sheet.get("status") or meta.get("status") or "BELUM LUNAS"
            self._workbook_sheet_meta[sheet_id] = meta
            setter = getattr(self.tabel_item_invoice, "set_invoice_sheet_meta", None)
            if callable(setter):
                setter(sheet_id, meta)
            if sheet_id == active_sheet_id:
                self.no_invoice_aktif = str(meta.get("no_invoice") or "").strip().upper() or None
                self.status_invoice_aktif = str(meta.get("status") or "BELUM LUNAS").upper()
        self._workbook_mode_active = True
        self._workbook_dirty = False
        self._dirty = False
        self._set_invoice_lunas_locked(
            self.status_invoice_aktif in {"LUNAS", "BATAL"},
            dibatalkan=self.status_invoice_aktif == "BATAL",
        )
        self.txt_no_invoice.setText(self.no_invoice_aktif or "")
        self.lbl_title_editor.setText(
            f"{self.status_invoice_aktif} INVOICE: {self.no_invoice_aktif or self.no_workbook_aktif or 'WORKBOOK'}"
        )
        self.btn_simpan_db.setEnabled(False)
        self.btn_catat_pembayaran.setEnabled(bool(self.no_invoice_aktif) and self.status_invoice_aktif not in {"LUNAS", "BATAL"})
        self.btn_riwayat_pembayaran.setEnabled(bool(self.no_invoice_aktif))
        self.load_histori_invoice()
        QMessageBox.information(
            self, "Workbook Invoice Tersimpan",
            f"Workbook {self.no_workbook_aktif} berhasil disimpan.\n"
            f"Jumlah sheet: {len(sheet_entries)} (termasuk sheet DRAFT).",
        )
        return True

    def tambah_invoice_sheet(self, on_added=None):
        if not callable(on_added):
            on_added = None
        if not self.tabel_item_invoice.using_univer:
            QMessageBox.warning(self, "Univer Tidak Siap", "Tambah sheet memerlukan editor Univer aktif.")
            return False
        if not self.txt_client.text().strip():
            QMessageBox.warning(self, "Customer Belum Diisi", "Isi nama customer sebelum menambah invoice sheet.")
            self.txt_client.setFocus()
            return False
        capture = getattr(self.tabel_item_invoice, "capture_workbook", None)
        if not callable(capture):
            return False

        def _captured(raw_payload):
            try:
                if not raw_payload:
                    raise ValueError("Snapshot sheet aktif tidak tersedia.")
                data = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
                active_id = str(data.get("activeSheetId") or "")
                active_sheet = next((item for item in data.get("sheets", []) if str(item.get("sheetId")) == active_id), None)
                if not active_sheet:
                    raise ValueError("Sheet aktif tidak ditemukan di workbook.")
                active_meta = self._meta_sheet_aktif_dari_form(active_sheet.get("sheetMeta") or {})
                active_meta["no_invoice"] = str(self.no_invoice_aktif or "")
                self._workbook_sheet_meta[active_id] = active_meta
                self._workbook_mode_active = True
                self._workbook_dirty = True
                self.tabel_item_invoice.set_invoice_sheet_meta(active_id, active_meta)
                new_name = f"Invoice {len(data.get('sheets') or []) + 1}"
                new_meta = deepcopy(active_meta)
                new_meta.update({"no_invoice": "", "status": "DRAFT", "paid_total": 0, "total_akhir": 0, "subtotal": 0, "source_resi": [], "is_new_sheet": True})
                new_columns = deepcopy(active_sheet.get("columns") or self.active_columns)
                def _sheet_inserted(new_sheet_id=None):
                    if not new_sheet_id:
                        QMessageBox.warning(
                            self, "Gagal Menambah Sheet",
                            "Univer tidak berhasil membuat sheet invoice baru.",
                        )
                        return
                    self.btn_simpan_db.setEnabled(True)
                    if on_added is not None:
                        # Let the ActiveSheetChanged WebChannel callback finish
                        # applying the new blank sheet to the Python model first.
                        QTimer.singleShot(0, on_added)

                self.tabel_item_invoice.add_invoice_sheet(
                    {
                        "sheetName": new_name,
                        "columns": new_columns,
                        "sheetMeta": new_meta,
                    },
                    _sheet_inserted,
                )
            except Exception as exc:
                QMessageBox.warning(self, "Gagal Menambah Sheet", str(exc))

        return bool(capture(_captured))

    def buka_dialog_catat_pembayaran(self):
        no_invoice = str(self.no_invoice_aktif or "").strip().upper()
        if not no_invoice:
            QMessageBox.information(self, "Invoice Belum Tersimpan", "Simpan Workbook terlebih dahulu sebelum mencatat pembayaran.")
            return False
        if self._invoice_lunas_locked or self.status_invoice_aktif == "BATAL":
            return False
        if self._dirty or self._workbook_dirty:
            QMessageBox.information(
                self, "Simpan Perubahan Terlebih Dahulu",
                "Simpan perubahan Workbook terlebih dahulu sebelum mencatat pembayaran, "
                "agar nominal pembayaran sesuai dengan total invoice yang tersimpan.",
            )
            return False
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Catat Pembayaran — {no_invoice}")
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Invoice: {no_invoice}"))
        txt_nominal = QLineEdit()
        txt_nominal.setPlaceholderText("Nominal pembayaran, contoh 1.500.000")
        txt_nominal.setValidator(InvoiceCellValidator("currency", txt_nominal))
        atur_tinggi_input(txt_nominal)
        date_payment = QDateEdit(QDate.currentDate())
        date_payment.setCalendarPopup(True)
        date_payment.setDisplayFormat("dd/MM/yyyy")
        cmb_metode = QComboBox()
        cmb_metode.addItems(["TRANSFER", "TUNAI", "LAINNYA"])
        txt_referensi = QLineEdit()
        txt_referensi.setPlaceholderText("Nomor referensi / bukti (opsional)")
        txt_catatan = QLineEdit()
        txt_catatan.setPlaceholderText("Catatan pembayaran (opsional)")
        for label, widget in (
            ("Nominal", txt_nominal), ("Tanggal", date_payment), ("Metode", cmb_metode),
            ("Referensi", txt_referensi), ("Catatan", txt_catatan),
        ):
            layout.addWidget(QLabel(label))
            layout.addWidget(widget)
        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Batal")
        btn_save = QPushButton("Simpan Pembayaran")
        btn_cancel.clicked.connect(dialog.reject)
        btn_save.clicked.connect(dialog.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_save)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            nominal = int(_parse_invoice_number(txt_nominal.text(), "currency"))
        except ValueError as exc:
            QMessageBox.warning(self, "Nominal Tidak Valid", str(exc))
            return False
        if nominal <= 0:
            QMessageBox.warning(self, "Nominal Tidak Valid", "Nominal pembayaran harus lebih besar dari nol.")
            return False
        sukses, hasil = db_service.catat_pembayaran_invoice(
            no_invoice,
            nominal,
            date_payment.date().toString("yyyy-MM-dd"),
            cmb_metode.currentText(),
            txt_referensi.text().strip(),
            txt_catatan.text().strip(),
        )
        if not sukses:
            QMessageBox.warning(self, "Pembayaran Tidak Tersimpan", str(hasil))
            return False
        self.status_invoice_aktif = str(hasil.get("status") or "CICILAN").upper()
        meta = self._meta_sheet_aktif_dari_form(self._workbook_sheet_meta.get(self._active_workbook_sheet_id))
        meta.update({
            "status": self.status_invoice_aktif,
            "paid_total": int(hasil.get("paid_total") or 0),
            "total_akhir": int(self.total_invoice_aktif or meta.get("total_akhir") or 0),
        })
        self._workbook_sheet_meta[self._active_workbook_sheet_id] = meta
        self.tabel_item_invoice.set_invoice_sheet_meta(self._active_workbook_sheet_id, meta)
        self._set_invoice_lunas_locked(self.status_invoice_aktif == "LUNAS", dibatalkan=False)
        self.btn_catat_pembayaran.setEnabled(self.status_invoice_aktif != "LUNAS")
        self.btn_riwayat_pembayaran.setEnabled(True)
        self.lbl_title_editor.setText(f"{self.status_invoice_aktif} INVOICE: {no_invoice}")
        self.load_histori_invoice()
        QMessageBox.information(
            self, "Pembayaran Tersimpan",
            f"Pembayaran Rp {nominal:,} berhasil dicatat.\n"
            f"Total dibayar: Rp {int(hasil.get('paid_total') or 0):,}\n"
            f"Sisa tagihan: Rp {int(hasil.get('remaining') or 0):,}\n"
            f"Status: {self.status_invoice_aktif}.",
        )
        return True

    def tampilkan_riwayat_pembayaran(self):
        no_invoice = str(self.no_invoice_aktif or "").strip().upper()
        if not no_invoice:
            return False
        try:
            payments = db_service.ambil_pembayaran_invoice(no_invoice)
        except Exception as exc:
            QMessageBox.warning(self, "Riwayat Pembayaran", f"Gagal membaca riwayat pembayaran: {exc}")
            return False
        if not payments:
            message = "Belum ada catatan transaksi pembayaran untuk invoice ini.\n"
            if self.status_invoice_aktif == "LUNAS":
                message += "Status LUNAS berasal dari pencatatan invoice versi lama; rincian transaksinya belum tersedia."
        else:
            lines = []
            for payment in payments:
                _, tanggal, nominal, metode, referensi, catatan, created_at, *_ = payment
                lines.append(
                    f"{tanggal} | Rp {int(nominal or 0):,} | {metode or '-'}"
                    + (f" | Ref: {referensi}" if referensi else "")
                    + (f" | {catatan}" if catatan else "")
                )
            message = "\n".join(lines)
        QMessageBox.information(self, f"Riwayat Pembayaran — {no_invoice}", message)
        return True

    def _tambahkan_baris_histori_invoice(self, tabel, data):
        # Bentuk query: workbook_id, no_workbook, tanggal, client,
        # jumlah_sheet, total_tagihan, total_dibayar, sisa_tagihan, status.
        row = tabel.rowCount()
        tabel.insertRow(row)
        workbook_id = str(data[0] or "") if len(data) > 0 else ""
        no_workbook = str(data[1] or "") if len(data) > 1 else ""
        tanggal = str(data[2] or "") if len(data) > 2 else ""
        client = str(data[3] or "") if len(data) > 3 else ""
        jumlah_sheet = int(data[4] or 0) if len(data) > 4 else 0
        total = int(data[5] or 0) if len(data) > 5 else 0
        sisa = int(data[7] or 0) if len(data) > 7 else 0
        status = str(data[8] or "") if len(data) > 8 else ""
        values = (
            no_workbook,
            tanggal,
            client,
            f"{jumlah_sheet} sheet",
            f"Rp {total:,}",
            f"Rp {sisa:,}",
            status,
        )
        for column, value in enumerate(values):
            item = buat_tabel_item(text=str(value), editable=False)
            item.setFont(tabel.font())
            item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            if column == self.KOL_HISTORI_NO_WORKBOOK:
                item.setData(Qt.ItemDataRole.UserRole, workbook_id)
            tabel.setItem(row, column, item)

    @db_service.profile_performance("Invoice.load_history", threshold=0.05)
    def load_histori_invoice(self):
        tabel = self.tabel_histori_invoice
        keyword = self.txt_cari_invoice.text().strip()

        # Ambil dan validasi hasil lebih dahulu. Jika query gagal, histori
        # terakhir yang berhasil dimuat tetap terlihat di tabel.
        try:
            data_histori = db_service.ambil_histori_invoice(
                limit=300, keyword=keyword
            )
            if not isinstance(data_histori, (list, tuple)):
                raise TypeError(
                    "Hasil histori Invoice harus berupa daftar, bukan None/tipe lain."
                )
            if any(not isinstance(data, (list, tuple)) for data in data_histori):
                raise TypeError("Ada baris histori Invoice dengan format data yang tidak valid.")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error Histori Invoice",
                f"Gagal memuat histori invoice:\n{exc}",
            )
            return False

        status_signal = tabel.blockSignals(True)
        tabel.setUpdatesEnabled(False)
        try:
            tabel.setRowCount(0)
            for data in data_histori:
                self._tambahkan_baris_histori_invoice(tabel, data)
        finally:
            tabel.blockSignals(status_signal)
            tabel.setUpdatesEnabled(True)

        self.filter_histori_invoice()
        return True

    @db_service.profile_performance("Invoice.search_history", threshold=0.025)
    def filter_histori_invoice(self, *_):
        keyword = self.txt_cari_invoice.text().strip().lower()
        for row in range(self.tabel_histori_invoice.rowCount()):
            match = any(
                self.tabel_histori_invoice.item(row, column)
                and keyword in self.tabel_histori_invoice.item(row, column).text().lower()
                for column in range(self.tabel_histori_invoice.columnCount())
            )
            self.tabel_histori_invoice.setRowHidden(row, not match)

    def _tampilkan_context_menu_histori_invoice(self, position):
        tabel = self.tabel_histori_invoice
        row = tabel.rowAt(position.y())
        if row < 0:
            return
        tabel.selectRow(row)
        item = tabel.item(row, self.KOL_HISTORI_NO_WORKBOOK)
        workbook_id = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        if not workbook_id:
            return
        menu = QMenu(self)
        action_buka = menu.addAction("Buka Workbook Invoice")
        batal_menu = menu.addMenu("Batalkan Invoice Sheet")
        try:
            loaded = db_service.ambil_workbook_invoice(workbook_id) or {}
            sheets = loaded.get("sheets") or []
        except Exception as exc:
            sheets = []
            print(f"[INVOICE-WORKBOOK] Gagal membaca daftar sheet untuk pembatalan: {exc}")
        cancel_actions = {}
        for sheet in sheets:
            no_invoice = str(sheet.get("no_invoice") or "").strip().upper()
            status = str(sheet.get("status") or "").strip().upper()
            if not no_invoice or status in {"LUNAS", "BATAL"}:
                continue
            sheet_name = str(sheet.get("sheet_name") or no_invoice)
            paid_total = int(sheet.get("paid_total") or 0)
            if paid_total > 0:
                action = batal_menu.addAction(
                    f"{sheet_name} — {no_invoice} (ADA PEMBAYARAN; refund belum didukung)"
                )
                action.setEnabled(False)
                continue
            action = batal_menu.addAction(f"{sheet_name} — {no_invoice} ({status})")
            cancel_actions[action] = no_invoice
        if not batal_menu.actions():
            batal_menu.setEnabled(False)
        dipilih = menu.exec(tabel.viewport().mapToGlobal(position))
        if dipilih == action_buka:
            self.load_workbook_invoice(workbook_id)
        elif dipilih in cancel_actions:
            self._batalkan_invoice_dari_histori(cancel_actions[dipilih])

    def _batalkan_invoice_dari_histori(self, no_invoice):
        no_invoice = str(no_invoice or "").strip().upper()
        if not no_invoice:
            return False

        workbook_editing = bool(
            self._workbook_mode_active
            and self.workbook_id_aktif
            and (self._dirty or self._workbook_dirty)
        )
        if workbook_editing:
            QMessageBox.information(
                self,
                "Simpan Workbook Terlebih Dahulu",
                "Simpan atau buang perubahan Workbook terlebih dahulu sebelum membatalkan salah satu invoice sheet.",
            )
            return False
        if self.no_invoice_aktif == no_invoice and self._dirty:
            if not self._konfirmasi_buang_perubahan("membatalkan Invoice yang sedang diedit"):
                return False

        jawaban = QMessageBox.question(
            self,
            "Batalkan Invoice",
            f"Batalkan Invoice {no_invoice}?\n\n"
            "Invoice akan tetap tersimpan sebagai arsip berstatus BATAL. "
            "Relasi Resi aktif akan dilepas sehingga Resi dapat dipilih kembali "
            "di Billing Queue dan ditagihkan melalui Invoice baru.\n\n"
            "Invoice yang sudah LUNAS tidak dapat dibatalkan. Tindakan ini tidak dapat diurungkan.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if jawaban != QMessageBox.StandardButton.Yes:
            return False

        sukses, pesan = db_service.ubah_status_penagihan_invoice(
            no_invoice,
            "BATAL",
            numbering_service.CENTRAL_INVOICE_BRANCH,
        )
        if not sukses:
            QMessageBox.warning(self, "Invoice Tidak Dibatalkan", str(pesan))
            return False

        if self._workbook_mode_active and self.workbook_id_aktif:
            try:
                loaded_workbook = db_service.ambil_workbook_invoice(self.workbook_id_aktif) or {}
                for sheet in loaded_workbook.get("sheets") or []:
                    if str(sheet.get("no_invoice") or "").strip().upper() != no_invoice:
                        continue
                    sheet_id = str(sheet.get("sheet_id") or "")
                    meta = dict(self._workbook_sheet_meta.get(sheet_id) or {})
                    meta.update({"no_invoice": no_invoice, "status": "BATAL"})
                    self._workbook_sheet_meta[sheet_id] = meta
                    self.tabel_item_invoice.set_invoice_sheet_meta(sheet_id, meta)
                    break
            except Exception as exc:
                print(f"[INVOICE-WORKBOOK] Gagal memperbarui status sheet yang dibatalkan: {exc}")

        if self.no_invoice_aktif == no_invoice:
            self.status_invoice_aktif = "BATAL"
            self._dirty = False
            self._set_invoice_lunas_locked(True, dibatalkan=True)
            self.lbl_title_editor.setText(f"BATAL INVOICE: {no_invoice}")
            self.btn_simpan_db.setEnabled(False)
            self.btn_catat_pembayaran.setEnabled(False)

        self.load_histori_invoice()
        QMessageBox.information(
            self,
            "Invoice Dibatalkan",
            f"Invoice {no_invoice} berhasil dibatalkan. Resi terkait dapat dipilih kembali di Billing Queue.",
        )
        return True

    def buka_invoice_dari_histori(self, *_):
        selection_model = self.tabel_histori_invoice.selectionModel()
        selected = selection_model.selectedRows() if selection_model else []
        if not selected:
            return False
        item = self.tabel_histori_invoice.item(
            selected[0].row(), self.KOL_HISTORI_NO_WORKBOOK,
        )
        workbook_id = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        return self.load_workbook_invoice(workbook_id) if workbook_id else False

    def load_workbook_invoice(self, workbook_id):
        workbook_key = str(workbook_id or "").strip()
        if not workbook_key:
            return False
        if not self._konfirmasi_buang_perubahan("membuka Workbook Invoice lain"):
            return False

        try:
            loaded = db_service.ambil_workbook_invoice(workbook_key)
            if not loaded:
                QMessageBox.warning(self, "Workbook Tidak Ditemukan", f"Workbook {workbook_key} tidak ditemukan.")
                return False
            workbook = loaded.get("workbook") or {}
            db_sheets = list(loaded.get("sheets") or [])
            snapshot = self._parse_meta_json(workbook.get("snapshot_json"))
            if not snapshot:
                # Kompatibilitas untuk invoice lama yang masih menyimpan snapshot
                # Univer di metadata_json per invoice, bukan pada induk workbook.
                for sheet in db_sheets:
                    old_meta = self._parse_meta_json(sheet.get("metadata_json"))
                    candidate = old_meta.get("univer_snapshot")
                    if isinstance(candidate, dict) and candidate:
                        snapshot = candidate
                        break

            order_ids = []
            try:
                raw_order = json.loads(workbook.get("sheet_order_json") or "[]")
                if isinstance(raw_order, list):
                    order_ids = [str(value) for value in raw_order if str(value or "").strip()]
            except (TypeError, ValueError, json.JSONDecodeError):
                order_ids = []

            sheets_by_id = {
                str(sheet.get("sheet_id") or ""): sheet
                for sheet in db_sheets
                if str(sheet.get("sheet_id") or "").strip()
            }
            snapshot_custom = snapshot.get("custom") if isinstance(snapshot.get("custom"), dict) else {}
            snapshot_sheet_meta = snapshot_custom.get("kargoInvoiceSheets")
            if not isinstance(snapshot_sheet_meta, dict):
                snapshot_sheet_meta = {}
            snapshot_sheet_order = snapshot.get("sheetOrder")
            if not order_ids and isinstance(snapshot_sheet_order, list):
                order_ids = [str(value) for value in snapshot_sheet_order if str(value or "").strip()]
            if not order_ids:
                order_ids = [str(sheet.get("sheet_id") or "") for sheet in db_sheets if sheet.get("sheet_id")]

            sheets_metadata = []
            sheet_meta_map = {}
            for index, sheet_id in enumerate(order_ids):
                sheet = sheets_by_id.get(sheet_id)
                if sheet:
                    invoice_meta = self._parse_meta_json(sheet.get("metadata_json"))
                    template_name = str(sheet.get("tipe_invoice") or "Standar")
                    template_config = invoice_meta.get("template_config")
                    if not isinstance(template_config, dict):
                        template_config = deepcopy(
                            self.template_configs.get(template_name, self.template_configs["Custom / Bebas"])
                        )
                    source_resi = invoice_meta.get("source_resi")
                    if not isinstance(source_resi, list):
                        source_resi = []
                    meta = dict(snapshot_sheet_meta.get(sheet_id) or {})
                    meta.update({
                        "no_invoice": str(sheet.get("no_invoice") or "").strip().upper(),
                        "status": str(sheet.get("status") or "DRAFT").strip().upper(),
                        "template_name": template_name,
                        "template_config": template_config,
                        "client": str(sheet.get("client") or workbook.get("client") or "").strip().upper(),
                        "tanggal": str(sheet.get("tanggal") or workbook.get("tanggal") or ""),
                        "jenis_pajak": str(sheet.get("jenis_pajak") or "NONPAJAK").strip().upper(),
                        "ship_to": str(invoice_meta.get("ship_to") or "").strip().upper(),
                        "payment_info": str(invoice_meta.get("payment_info") or "").strip().upper(),
                        "notes": str(invoice_meta.get("notes") or "").strip().upper(),
                        "source_resi": source_resi,
                        "paid_total": int(sheet.get("paid_total") or 0),
                        "subtotal": int(sheet.get("subtotal") or 0),
                        "total_akhir": int(sheet.get("total_akhir") or 0),
                        "created_by_user_id": sheet.get("created_by_user_id"),
                        "created_by_username": sheet.get("created_by_username"),
                        "created_by_name": sheet.get("created_by_name"),
                    })
                    sheet_name = str(sheet.get("sheet_name") or meta.get("sheet_name") or f"Invoice {index + 1}")
                    meta["sheet_name"] = sheet_name
                    rows_metadata = []
                    for detail in sheet.get("details") or []:
                        data_row = self._parse_json_object(detail[0] if detail else None)
                        rows_metadata.append({
                            "id": str(data_row.get("__row_id__") or ""),
                            "hidden": data_row.get("__template_values__") if isinstance(data_row.get("__template_values__"), dict) else {},
                            "source": data_row.get("__source_resi__") if isinstance(data_row.get("__source_resi__"), dict) else None,
                        })
                else:
                    # Sheet DRAFT kosong disimpan di snapshot workbook, belum punya invoice_header.
                    meta = dict(snapshot_sheet_meta.get(sheet_id) or {})
                    template_name = str(meta.get("template_name") or "Standar")
                    template_config = meta.get("template_config")
                    if not isinstance(template_config, dict):
                        template_config = deepcopy(
                            self.template_configs.get(template_name, self.template_configs["Custom / Bebas"])
                        )
                    meta.update({
                        "no_invoice": "",
                        "status": "DRAFT",
                        "template_name": template_name,
                        "template_config": template_config,
                        "client": str(meta.get("client") or workbook.get("client") or "").strip().upper(),
                        "tanggal": str(meta.get("tanggal") or workbook.get("tanggal") or ""),
                        "jenis_pajak": str(meta.get("jenis_pajak") or "NONPAJAK").strip().upper(),
                        "paid_total": 0,
                        "subtotal": 0,
                        "total_akhir": 0,
                        "sheet_name": str(meta.get("sheet_name") or f"Invoice {index + 1}"),
                    })
                    rows_metadata = []
                sheet_meta_map[sheet_id] = meta
                sheets_metadata.append({
                    "sheetId": sheet_id,
                    "sheetMeta": meta,
                    "rows": rows_metadata,
                })

            if not order_ids and not db_sheets:
                raise ValueError("Workbook tidak memiliki sheet invoice.")
            if not snapshot:
                # Fallback hanya untuk workbook legacy tanpa snapshot. Bangun sheet
                # pertama dari detail invoice yang tersimpan, lalu kaitkan id baru Univer.
                if not db_sheets:
                    raise ValueError("Snapshot Workbook tidak tersedia untuk dipulihkan.")
                first = db_sheets[0]
                invoice_meta = self._parse_meta_json(first.get("metadata_json"))
                header = (
                    first.get("client"), first.get("tipe_invoice"), first.get("jenis_pajak"),
                    first.get("status"), first.get("tanggal"), first.get("metadata_json"),
                    first.get("created_by_user_id"), first.get("created_by_username"),
                    first.get("created_by_name"),
                )
                self._workbook_mode_active = False
                self._workbook_dirty = False
                self.workbook_id_aktif = str(workbook.get("workbook_id") or "")
                self.no_workbook_aktif = str(workbook.get("no_workbook") or "")
                self._workbook_sheet_meta = sheet_meta_map
                self._active_workbook_sheet_id = str(first.get("sheet_id") or "")
                self._loading_invoice = True
                self._sedang_memuat_item = True
                try:
                    self._terapkan_header_invoice_loaded(str(first.get("no_invoice") or ""), header)
                    self._muat_detail_invoice(first.get("details") or [])
                    self._set_invoice_lunas_locked(
                        str(first.get("status") or "").upper() in {"LUNAS", "BATAL"},
                        dibatalkan=str(first.get("status") or "").upper() == "BATAL",
                    )
                finally:
                    self._sedang_memuat_item = False
                    self._loading_invoice = False
                self._workbook_mode_active = True
                self._workbook_dirty = False
                self._dirty = False

                def _attach_legacy_sheet(_payload=None):
                    def _captured(raw_payload):
                        try:
                            data = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
                            active_id = str((data or {}).get("activeSheetId") or "")
                            if not active_id:
                                return
                            meta = dict(sheet_meta_map.get(str(first.get("sheet_id") or "")) or {})
                            meta["sheet_name"] = str((data.get("sheets") or [{}])[0].get("sheetName") or "Sheet 1")
                            self._active_workbook_sheet_id = active_id
                            self._workbook_sheet_meta = {active_id: meta}
                            self.tabel_item_invoice.set_invoice_sheet_meta(active_id, meta)
                        except Exception as exc:
                            print(f"[INVOICE-WORKBOOK] Legacy metadata attach failed: {exc}")

                    self.tabel_item_invoice.capture_workbook(_captured)

                QTimer.singleShot(100, _attach_legacy_sheet)
                self.lbl_title_editor.setText(f"{self.status_invoice_aktif} INVOICE: {self.no_invoice_aktif}")
                self.btn_catat_pembayaran.setEnabled(bool(self.no_invoice_aktif) and self.status_invoice_aktif not in {"LUNAS", "BATAL"})
                self.btn_riwayat_pembayaran.setEnabled(bool(self.no_invoice_aktif))
                self.btn_simpan_db.setEnabled(False)
                self.load_histori_invoice()
                return True

            active_id = str(snapshot_custom.get("kargoActiveSheetId") or "").strip()
            if active_id not in order_ids:
                active_id = order_ids[0]
            if not isinstance(snapshot.get("custom"), dict):
                snapshot["custom"] = {}
            snapshot["custom"]["kargoInvoiceSheets"] = sheet_meta_map
            snapshot["custom"]["kargoActiveSheetId"] = active_id

            self.workbook_id_aktif = str(workbook.get("workbook_id") or "")
            self.no_workbook_aktif = str(workbook.get("no_workbook") or "")
            self._workbook_mode_active = True
            self._workbook_dirty = False
            self._dirty = False
            self._active_workbook_sheet_id = active_id
            self._workbook_sheet_meta = sheet_meta_map
            self._workbook_sheet_payment = {
                str(sheet.get("no_invoice") or ""): list(sheet.get("payments") or [])
                for sheet in db_sheets if str(sheet.get("no_invoice") or "").strip()
            }
            self._loading_invoice = True
            try:
                self.txt_client.setText(str(workbook.get("client") or "").strip().upper())
                self.lbl_title_editor.setText(f"WORKBOOK INVOICE: {self.no_workbook_aktif}")
                self._set_invoice_lunas_locked(False, dibatalkan=False)
                self._dirty = False
            finally:
                self._loading_invoice = False
            self.tabel_item_invoice.restore_univer_snapshot(snapshot, sheets_metadata)
            self._workbook_dirty = False
            self.btn_simpan_db.setEnabled(False)
            self.load_histori_invoice()
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Gagal Membuka Workbook", f"Workbook Invoice tidak dapat dibuka:\n{exc}")
            return False

    def _source_resi_yang_berubah(self):
        """Kembalikan Resi sumber yang revision-nya tidak lagi sama."""
        berubah = []
        for item in self._source_resi_dari_tabel():
            nomor = str(item.get("no_resi") or "").strip().upper()
            revision = item.get("revision")
            if not nomor or revision in (None, ""):
                continue
            cocok, revision_sekarang = db_service.cek_revision_resi(
                nomor,
                revision,
                item.get("kode_cabang"),
            )
            if not cocok:
                berubah.append((nomor, revision, revision_sekarang))
        return berubah

    def _peringatkan_source_resi_berubah(self):
        berubah = self._source_resi_yang_berubah()
        if not berubah:
            return

        daftar = "\n".join(
            f"- {nomor}: revision {lama} -> "
            f"{baru if baru is not None else 'tidak ditemukan'}"
            for nomor, lama, baru in berubah
        )
        QMessageBox.warning(
            self,
            "Resi Sumber Sudah Berubah",
            "Invoice ini tetap dapat dilihat sebagai snapshot historis.\n\n"
            "Namun Invoice tidak dapat disimpan ulang sebelum data Resi "
            "direfresh dan dipilih kembali.\n\n"
            f"Resi yang berubah:\n{daftar}",
        )

    def _terapkan_header_invoice_loaded(self, no_invoice, header):
        client, template_name, tax_name, status, date_text, metadata_text = header[:6]
        created_by_user_id = header[6] if len(header) > 6 else None
        created_by_username = header[7] if len(header) > 7 else None
        created_by_name = header[8] if len(header) > 8 else None
        metadata = self._parse_json_object(metadata_text)
        snapshot = metadata.get("univer_snapshot")
        self._pending_univer_snapshot = snapshot if isinstance(snapshot, dict) else None
        template_name = str(template_name or "Standar")
        tax_name = str(tax_name or "NONPAJAK")
        status = str(status or "DRAFT")

        self.no_invoice_aktif = no_invoice
        self._created_by_name = str(created_by_name or created_by_username or "").strip()
        self._created_by_username = str(created_by_username or "").strip().upper()
        self.status_invoice_aktif = status or "DRAFT"
        self.txt_no_invoice.setText(str(no_invoice or "").upper())
        self.txt_client.setText(str(client or "").upper())
        self.txt_ship_to.setText(str(metadata.get("ship_to", "") or "").upper())
        # Pertahankan snapshot rekening pada invoice lama. Jika metadata lama
        # belum memiliki payment_info, isi dari pengaturan perusahaan saat ini.
        payment_info = str(metadata.get("payment_info", "") or "").strip().upper()
        self._payment_info_snapshot = (
            payment_info or self._payment_info_otomatis(tax_name)
        )
        self.txt_catatan.setText(str(metadata.get("notes", "") or "").upper())
        raw_source_resi = metadata.get("source_resi", [])
        self._source_resi = [
            {
                "no_resi": str(item.get("no_resi") or "").strip().upper(),
                "kode_cabang": str(item.get("kode_cabang") or "").strip().upper() or None,
                "revision": item.get("revision"),
            }
            for item in raw_source_resi
            if isinstance(item, dict) and str(item.get("no_resi") or "").strip()
        ]
        self._invoice_dari_resi = bool(self._source_resi)
        self.cmb_pajak.setEnabled(not self._invoice_dari_resi)

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
        details = list(details or [])
        source_resi = [dict(item) for item in (self._source_resi or []) if isinstance(item, dict)]
        source_by_no = {}
        for source in source_resi:
            nomor = str(source.get("no_resi") or "").strip().upper()
            if nomor:
                source_by_no.setdefault(nomor, source)

        self.tabel_item_invoice.setUpdatesEnabled(False)
        try:
            with blokir_signal_sementara(self.tabel_item_invoice):
                self.tabel_item_invoice.setRowCount(0)
                for index, detail in enumerate(details):
                    row_data = self._parse_json_object(detail[0] if detail else None)
                    nomor_resi = str(
                        row_data.get("resi") or row_data.get("no_resi") or ""
                    ).strip().upper()
                    source_metadata = source_by_no.get(nomor_resi)
                    if source_metadata is None and not nomor_resi and len(source_resi) == len(details):
                        source_metadata = source_resi[index]
                    if source_metadata:
                        row_data["__source_resi__"] = dict(source_metadata)
                    self._tambahkan_row_invoice(row_data)
                self._pastikan_baris_invoice()
        finally:
            self.tabel_item_invoice.setUpdatesEnabled(True)

    def _set_invoice_lunas_locked(self, locked, dibatalkan=False):
        self._invoice_lunas_locked = bool(locked)
        self._invoice_dibatalkan = bool(dibatalkan)
        fields = (
            self.txt_client,
            self.txt_ship_to,
            self.txt_no_invoice,
            self.date_invoice,
            self.cmb_tipe_invoice,
            self.cmb_pajak,
            self.txt_catatan,
        )
        for widget in fields:
            widget.setEnabled(not locked)

        edit_buttons = (self.btn_ambil_resi,)
        for widget in edit_buttons:
            widget.setEnabled(not locked)

        self.tabel_item_invoice.set_mutation_locked(locked)
        if bool(getattr(self, "_workbook_mode_active", False)):
            self.btn_simpan_db.setEnabled(bool(self._dirty or self._workbook_dirty))
        else:
            self.btn_simpan_db.setEnabled((not locked) and self._dirty)
        self._update_print_menu_state()

    def _terapkan_invoice_loaded(self, no_invoice, header, details):
        self._loading_invoice = True
        self._sedang_memuat_item = True
        try:
            self._terapkan_header_invoice_loaded(no_invoice, header)
            self._muat_detail_invoice(details)
            snapshot = getattr(self, "_pending_univer_snapshot", None)
            restore_snapshot = getattr(self.tabel_item_invoice, "restore_univer_snapshot", None)
            if snapshot and callable(restore_snapshot):
                restore_snapshot(snapshot)
            self._pending_univer_snapshot = None
            status_loaded = str(self.status_invoice_aktif or "").strip().upper()
            self._set_invoice_lunas_locked(
                status_loaded in {"LUNAS", "BATAL"},
                dibatalkan=status_loaded == "BATAL",
            )
            self.lbl_title_editor.setText(
                f"{self.status_invoice_aktif} INVOICE: {no_invoice}",
            )
            self._dirty = False
            self.btn_simpan_db.setEnabled(False)
            self._update_print_menu_state()
        finally:
            self._sedang_memuat_item = False
            self._loading_invoice = False

    def load_invoice_by_no(self, no_invoice):
        no_invoice = str(no_invoice or "").strip().upper()
        if not no_invoice:
            return False
        # Nomor invoice tetap dapat dipakai sebagai pintasan pembuka, tetapi
        # konten dibuka melalui parent workbook agar sheet lain tidak hilang.
        workbook_id = db_service.ambil_workbook_id_untuk_invoice(no_invoice)
        if workbook_id:
            return self.load_workbook_invoice(workbook_id)
        if not self._konfirmasi_buang_perubahan("membuka invoice lain"):
            return False

        try:
            self.workbook_id_aktif = None
            self.no_workbook_aktif = None
            self._workbook_mode_active = False
            self._workbook_dirty = False
            self._active_workbook_sheet_id = ""
            self._workbook_sheet_meta = {}
            self._workbook_sheet_payment = {}
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
            if str(self.status_invoice_aktif or "").strip().upper() != "BATAL":
                self._peringatkan_source_resi_berubah()
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Gagal membuka invoice:\n{exc}")
            return False

    def buat_invoice_baru(self):
        if not self._konfirmasi_buang_perubahan("membuat invoice baru"):
            return False

        self._loading_invoice = True
        try:
            self.workbook_id_aktif = None
            self.no_workbook_aktif = None
            self._workbook_mode_active = False
            self._workbook_dirty = False
            self._active_workbook_sheet_id = ""
            self._workbook_sheet_meta = {}
            self._workbook_sheet_payment = {}
            self.no_invoice_aktif = None
            self._created_by_name = str(
                CURRENT_SESSION.get("nama_lengkap")
                or CURRENT_SESSION.get("username")
                or "ADMIN"
            ).strip()
            self._created_by_username = str(CURRENT_SESSION.get("username") or "ADMIN").strip().upper()
            self.status_invoice_aktif = "DRAFT"
            self.current_template_override = None
            clear_snapshot = getattr(self.tabel_item_invoice, "clear_univer_snapshot", None)
            if callable(clear_snapshot):
                clear_snapshot()
            self._pending_univer_snapshot = None
            reset_form_input_global(
                self.panel_kanan,
                reset_tanggal=True,
                fokus_ke=self.txt_client,
            )
            self.cmb_tipe_invoice.setCurrentText("Standar")
            self._invoice_dari_resi = False
            self._source_resi = []
            self._set_invoice_lunas_locked(False, dibatalkan=False)
            self.cmb_pajak.setEnabled(True)
            self.cmb_pajak.setCurrentText("NONPAJAK")
            self.apply_template(preserve_rows=False)
        finally:
            self._loading_invoice = False

        self._set_rekening_otomatis(tandai_perubahan=False)
        preview_nomor = self._generate_no_invoice()
        if preview_nomor:
            self.txt_no_invoice.setText(preview_nomor)
        self.hitung_ulang_total_tagihan()
        self._dirty = False
        self.btn_simpan_db.setEnabled(True)
        self.btn_catat_pembayaran.setEnabled(False)
        self.btn_riwayat_pembayaran.setEnabled(False)
        self._update_print_menu_state()
        self.lbl_title_editor.setText("DRAFT WORKBOOK INVOICE")
        return True

    def _confirm_clear_table(self):
        if self._invoice_lunas_locked:
            return
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
        app = QApplication.instance()
        if app is None:
            return "sans-serif"
        nama_font = str(app.font().family() or "").strip()
        return nama_font or "sans-serif"

    @classmethod
    def _font_family_css(cls) -> str:
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
                value = item.text().strip() if item else ""
                if column.get("type", "text") == "text":
                    value = value.upper()
                data[column["key"]] = value
            if any(data.values()):
                rows.append(data)
        return rows

    def _konteks_header_html_invoice(self):
        invoice_number = self.no_invoice_aktif or self.txt_no_invoice.text().strip() or "DRAFT"
        client = self.txt_client.text().strip().upper() or "-"
        ship_to = self.txt_ship_to.text().strip().upper() or "-"
        date_text = self.date_invoice.date().toString("dd MMMM yyyy")
        payment = str(self._payment_info_snapshot or "").strip().upper()
        notes = self.txt_catatan.text().strip().upper()
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
        default_signer = str(
            self._created_by_name
            or self._created_by_username
            or CURRENT_SESSION.get("nama_lengkap")
            or CURRENT_SESSION.get("username", "")
            or "ADMIN"
        ).strip() or "ADMIN"

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

        signer = default_signer.upper()
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
                    parsed = int(_parse_invoice_number(value, "currency"))
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

    @staticmethod
    def _teks_pdfmake(value):
        """Ubah fragmen teks/HTML kecil dari konteks Invoice menjadi teks biasa."""
        text_value = str(value or "")
        text_value = re.sub(r"<br\s*/?>", "\n", text_value, flags=re.IGNORECASE)
        text_value = re.sub(r"</(div|p|tr|li)>\s*<", "\n<", text_value, flags=re.IGNORECASE)
        text_value = re.sub(r"<[^>]*>", "", text_value)
        return html.unescape(text_value).strip()

    def _invoice_pdfmake_context(self):
        """Bangun konteks non-grid agar PDF Univer tetap memuat identitas Invoice."""
        self.hitung_ulang_total_tagihan()
        context = self._konteks_header_html_invoice()
        company = self._muat_data_perusahaan()
        subtotal = sum(item["nominal"] for item in self.ambil_data_item_invoice())
        tax_value = int(self.total_invoice_aktif) - int(subtotal)
        company_name = str(company.get("nama_perusahaan", "")).strip() or context["nama_perusahaan"]

        return {
            "invoice_number": context["invoice_number"],
            "client": context["client"],
            "ship_to": context["ship_to"],
            "layout_type": context["layout_type"],
            "company_name": company_name,
            # Logo tersimpan sebagai fragmen HTML pada konfigurasi lama; PDFMake
            # menerima teks biasa agar markup tidak bocor ke isi PDF.
            "logo_text": self._teks_pdfmake(context["logo_html"]) or company_name,
            "company_address": str(company.get("alamat_perusahaan", "")).strip(),
            "company_phone": str(company.get("telp_perusahaan", "")).strip(),
            "payment": context["payment"],
            "notes": context["notes"],
            "date_text": context["date_text"],
            "place_date": self._teks_pdfmake(context["tempat_tanggal"]),
            "signer": context["signer"],
            "subtotal_text": f"Rp {format_ke_rupiah(subtotal)}",
            "tax_name": self.cmb_pajak.currentText(),
            "tax_text": f"Rp {format_ke_rupiah(tax_value)}",
            "total_text": f"Rp {format_ke_rupiah(self.total_invoice_aktif)}",
        }

    def _generate_pdfmake_invoice(self, action, page_setup=None, suggested_name=None):
        """Generate the active Univer worksheet as a PDF through pdfmake.

        Keep the Invoice on the Univer/pdfmake route whenever the wrapper
        exposes generate_pdf. If the WebView/grid is not ready, show diagnostics
        instead of silently opening the legacy HTML preview.
        """
        container = getattr(self, "tabel_item_invoice", None)
        generator = getattr(container, "generate_pdf", None)
        web_view = getattr(container, "_view", None)
        is_univer_hosted = bool(getattr(container, "_using_univer", False))
        grid_ready = bool(getattr(container, "_grid_ready", False))
        web_ready = bool(getattr(container, "_web_ready", False))

        # InvoiceSheetContainer exposes generate_pdf even while its WebView is
        # starting. Once this method exists, keep the Invoice on the Univer PDF
        # route; do not silently switch to the legacy QTextDocument preview.
        if not callable(generator):
            return False

        if not is_univer_hosted or not grid_ready or not web_ready:
            last_error = str(getattr(container, "_last_error", "") or "(tidak ada error JavaScript yang tercatat)")
            details = (
                "Preview PDF Univer belum dapat dijalankan karena editor belum siap.\n\n"
                f"WebView dibuat: {'Ya' if web_view is not None else 'Tidak'}\n"
                f"Univer aktif: {'Ya' if is_univer_hosted else 'Tidak'}\n"
                f"WebChannel siap: {'Ya' if web_ready else 'Tidak'}\n"
                f"Grid siap: {'Ya' if grid_ready else 'Tidak'}\n\n"
                f"Error terakhir: {last_error}\n\n"
                "Preview HTML lama tidak dibuka otomatis agar hasil cetak tidak berbeda dari worksheet Univer."
            )
            QMessageBox.warning(self, "Univer Belum Siap", details)
            return True

        setup = page_setup or muat_page_setup()
        safe_name = str(
            suggested_name
            or self.no_invoice_aktif
            or self.txt_no_invoice.text().strip()
            or "invoice_draft"
        )

        def _on_pdf_ready(pdf_bytes, error_message):
            if error_message:
                QMessageBox.critical(
                    self,
                    "PDF Invoice",
                    f"Gagal membuat PDF dari worksheet Univer:\n{error_message}",
                )
                return
            if not pdf_bytes:
                QMessageBox.warning(self, "PDF Invoice", "Renderer tidak menghasilkan file PDF.")
                return

            if action == "preview":
                def _regenerate_preview(new_setup, ready_callback, progress_callback=None):
                    """Buat ulang PDF dari workbook aktif setelah Page Setup diubah."""
                    try:
                        fresh_invoice_data = self._invoice_pdfmake_context()
                        # generate_pdf() passes the page setup and invoice data
                        # directly to kargoGeneratePdf; avoid running the separate
                        # page-break recalculation before its WebEngine preflight.
                        return generator(
                            new_setup,
                            ready_callback,
                            fresh_invoice_data,
                            progress_callback=progress_callback,
                        )
                    except Exception as exc:
                        ready_callback(None, str(exc))
                        return True

                can_output = bool(
                    getattr(self, "no_invoice_aktif", None)
                    and not bool(getattr(self, "_dirty", False))
                    and not bool(getattr(self, "_invoice_dibatalkan", False))
                )
                dialog = InvoicePdfPreviewDialog(
                    pdf_bytes,
                    safe_name,
                    page_setup=setup,
                    parent=self,
                    regenerate_callback=_regenerate_preview,
                    actions_enabled=can_output,
                    actions_disabled_reason=(
                        "Simpan Invoice terlebih dahulu dan pastikan tidak ada perubahan yang belum disimpan "
                        "untuk mengaktifkan Cetak, Simpan PDF, dan Share."
                        if not can_output else ""
                    ),
                )
                dialog.exec()
            elif action == "save":
                output_path = simpan_pdfmake_bytes(pdf_bytes, safe_name, self)
                if output_path:
                    QMessageBox.information(
                        self,
                        "Export PDF",
                        f"Invoice berhasil disimpan:\n{output_path}",
                    )
            elif action == "print":
                cetak_pdfmake_bytes(pdf_bytes, self, setup)

        try:
            invoice_data = self._invoice_pdfmake_context()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "PDF Invoice",
                f"Gagal menyiapkan informasi Invoice untuk PDF:\n{exc}",
            )
            return True

        try:
            started = generator(setup, _on_pdf_ready, invoice_data)
        except Exception as exc:
            QMessageBox.critical(self, "PDF Invoice", f"Gagal memulai renderer PDF Univer:\n{exc}")
            return True

        # Once the Univer generator was invoked, the request is handled even
        # when it reports a failure through the callback. Never fall through to
        # the legacy HTML preview after entering the Univer PDF route.
        return True

    def tampilkan_preview(self):
        if self._invoice_dibatalkan:
            QMessageBox.information(self, "Invoice BATAL", "Invoice BATAL hanya tersedia sebagai arsip dan tidak dapat dipreview sebagai tagihan aktif.")
            return
        if not self._validasi_data_invoice():
            return
        default_name = self.no_invoice_aktif or self.txt_no_invoice.text().strip() or "invoice_draft"
        if self._generate_pdfmake_invoice("preview", muat_page_setup(), default_name):
            return
        html_content = self.build_invoice_html()

        tampilkan_preview_invoice(
            html_content=html_content,
            suggested_name=default_name,
            parent=self,
            page_setup=muat_page_setup(),
        )

    def atur_page_setup(self):
        """Buka dialog Page Setup dan simpan preferensi cetak Invoice."""
        dialog = InvoicePageSetupDialog(muat_page_setup(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            setup = simpan_page_setup(dialog.page_setup())
            container = getattr(self, "tabel_item_invoice", None)
            setter = getattr(container, "set_page_setup", None)
            if callable(setter):
                try:
                    setter(setup, self._invoice_pdfmake_context())
                except Exception:
                    setter(setup, {"layout_type": "standard"})

    def cetak_pdf(self):
        if self._invoice_dibatalkan:
            QMessageBox.information(self, "Invoice BATAL", "Invoice BATAL hanya tersedia sebagai arsip dan tidak dapat diekspor sebagai tagihan aktif.")
            return
        if not self._validasi_data_invoice():
            return
        default_name = self.no_invoice_aktif or self.txt_no_invoice.text().strip() or "invoice_draft"
        if self._generate_pdfmake_invoice("save", muat_page_setup(), default_name):
            return
        html_content = self.build_invoice_html()

        simpan_invoice_pdf(
            html_content=html_content,
            suggested_name=default_name,
            parent=self,
            page_setup=muat_page_setup(),
        )

    def cetak_langsung(self, tipe_kertas):
        if self._invoice_dibatalkan:
            QMessageBox.information(self, "Invoice BATAL", "Invoice BATAL hanya tersedia sebagai arsip dan tidak dapat dicetak sebagai tagihan aktif.")
            return
        if not self._validasi_data_invoice():
            return

        setup = page_setup_untuk_kertas(tipe_kertas, muat_page_setup())
        if self._generate_pdfmake_invoice("print", setup):
            return
        html_content = self.build_invoice_html()
        cetak_invoice_langsung(
            html_content=html_content,
            parent=self,
            page_setup=setup,
        )

    def info_fitur_cetak(self):
        """Alias kompatibilitas untuk satu alur cetak berbasis Preview."""
        self.tampilkan_preview()

    # TEMA

    def _tema_gelap_aktif(self):
        window = self.window()
        return bool(
            window
            and hasattr(window, "current_theme")
            and window.current_theme == "dark"
        )

    @staticmethod
    def _dapatkan_style_invoice_statis(is_dark):
        ukuran = get_fixed_font_sizes()
        return konversi_style_font_ke_point(get_invoice_styles(
            is_dark,
            ukuran["body"],
            ukuran["body_small"],
            ukuran["body"],
            ukuran["display"],
        ))

    def _terapkan_tema_statis_invoice(self, is_dark, styles):
        self.lbl_title_histori.setStyleSheet(styles["lbl_title_histori"])
        self.lbl_title_editor.setStyleSheet(styles["lbl_title_editor"])
        self.lbl_subtotal.setStyleSheet(styles["lbl_subtotal"])
        self.lbl_pajak_nominal.setStyleSheet(styles["lbl_subtotal"])
        self.lbl_total_tagihan.setStyleSheet(styles["lbl_total_tagihan"])

        terapkan_style_kalender(
            self.date_invoice,
            is_dark=is_dark,
        )

        for button in self.findChildren(QPushButton):
            button.setStyleSheet(styles["button_default"])

        self.btn_simpan_db.setStyleSheet(styles["button_simpan"])
        self.btn_cetak.setStyleSheet(styles["button_cetak"])
        terapkan_style_input_global(self, is_dark)

    def _terapkan_combobox_statis_invoice(self):
        comboboxes = (
            self.cmb_tipe_invoice,
            self.cmb_pajak,
        )
        atur_tinggi_input(comboboxes)

    @staticmethod
    def _sinkronkan_font_item_tabel(tabel):
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

    def sesuaikan_tema_lokal(self):
        is_dark = self._tema_gelap_aktif()

        styles = self._dapatkan_style_invoice_statis(is_dark)
        self._terapkan_tema_statis_invoice(is_dark, styles)
        self._terapkan_combobox_statis_invoice()

        ukuran_font_pt = get_fixed_font_sizes_pt()["body_small"]
        terapkan_tema_tabel(
            self.tabel_histori_invoice,
            is_dark,
            font_size_pt=ukuran_font_pt,
        )
        self._sinkronkan_font_item_tabel(self.tabel_histori_invoice)

        # Zoom editor diatur sepenuhnya oleh kontrol zoom bawaan Univer.
        apply_theme = getattr(self.tabel_item_invoice, "apply_theme", None)
        if callable(apply_theme):
            apply_theme(is_dark, ukuran_font_pt, row_height=32)
