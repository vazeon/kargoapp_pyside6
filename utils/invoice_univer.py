# utils/invoice_univer.py
"""Univer spreadsheet frontend wrapper for the existing Kargo Invoice model.

The hidden InvoiceSheetModel remains authoritative for business data, validation,
subtotal/tax calculations, database persistence and printing. Univer is the
interactive spreadsheet surface hosted by Qt WebEngine.
"""
from __future__ import annotations

import base64
import binascii
import json
import sys
import uuid
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Slot
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from utils.typography import dapatkan_font_aplikasi_aktif

try:
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:  # Keep the legacy Qt table usable without Qt WebEngine.
    QWebChannel = None
    QWebEngineSettings = None
    QWebEngineView = None


if QWebEngineView is not None:
    class _InvoiceUniverWebView(QWebEngineView):
        """WebView yang meneruskan Ctrl+Scroll ke zoom kanvas Univer saja."""

        def __init__(self, parent=None, zoom_callback=None):
            super().__init__(parent)
            self._zoom_callback = zoom_callback

        def wheelEvent(self, event):
            modifiers = event.modifiers()
            delta_y = event.angleDelta().y()
            if modifiers & Qt.KeyboardModifier.ControlModifier and delta_y:
                if callable(self._zoom_callback):
                    self._zoom_callback(1 if delta_y > 0 else -1)
                    event.accept()
                    return
            super().wheelEvent(event)
else:
    _InvoiceUniverWebView = None


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class _InvoiceUniverBridge(QObject):
    def __init__(self, owner: "InvoiceSheetContainer"):
        super().__init__(owner)
        self.owner = owner

    @Slot()
    def webReady(self):
        self.owner._on_web_ready()

    @Slot()
    def gridReady(self):
        self.owner._on_grid_ready()

    @Slot()
    def openPageSetup(self):
        """Open Kargo's existing Page Setup dialog from the Univer ribbon."""
        self.owner._on_page_setup_requested()

    @Slot(str)
    def snapshotAvailable(self, payload: str):
        self.owner._on_snapshot_available(payload)

    @Slot(str)
    def sheetSnapshotChanged(self, payload: str):
        self.owner._on_web_sheet_snapshot_changed(payload)

    @Slot(str)
    def selectionChanged(self, payload: str):
        self.owner._on_web_selection_changed(payload)

    @Slot(str)
    def webError(self, message: str):
        self.owner._on_web_error(message)

    @Slot(str)
    def pdfReady(self, payload: str):
        self.owner._on_pdf_ready(payload)

    @Slot(str)
    def pdfError(self, message: str):
        self.owner._on_pdf_error(message)

    @Slot(str)
    def pdfProgress(self, payload: str):
        self.owner._on_pdf_progress(payload)


class InvoiceSheetContainer(QWidget):
    """QWidget wrapper preserving the QTableWidget API used by tab_invoice.py."""

    def __init__(self, model_class, parent=None):
        super().__init__(parent)
        self._owner = parent
        self._model = model_class(self)
        self._model.hide()

        self._view = None
        self._channel = None
        self._bridge = None
        self._using_univer = False
        self._web_ready = False
        self._grid_ready = False
        self._updates_suppressed = False
        self._suppress_model_refresh = False
        self._structure_dirty = True
        self._refresh_scheduled = False
        self._applying_web_snapshot = False
        self._handling_web_selection = False
        self._pending_theme = None
        self._pending_snapshot = None
        self._last_snapshot = None
        self._row_tokens: list[str] = []
        self._snapshot_timer = QTimer(self)
        self._snapshot_timer.setSingleShot(True)
        self._snapshot_timer.setInterval(120)
        self._snapshot_timer.timeout.connect(self._emit_model_to_web)
        self._last_error = ""
        self._fallback_label = None
        self._pending_pdf_callback = None
        self._page_setup_dialog_open = False
        self._pending_pdf_progress_callback = None
        self._last_pdf_progress_message = ""
        self._pending_pdf_request_id = None
        self._pdf_request_timeout_ms = 90_000
        self._pdf_request_timer = QTimer(self)
        self._pdf_request_timer.setSingleShot(True)
        self._pdf_request_timer.timeout.connect(self._on_pdf_request_timeout)
        self._pending_page_setup = None
        self._pending_page_setup_invoice_data = {"layout_type": "standard"}

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        root = _project_root()
        html_path = root / "tabs" / "invoice_univer" / "index.html"
        js_bundle = root / "tabs" / "invoice_univer" / "vendor" / "invoice_univer.js"
        css_bundle = root / "tabs" / "invoice_univer" / "vendor" / "invoice_univer.css"

        if (
            QWebEngineView is not None
            and QWebChannel is not None
            and html_path.is_file()
            and js_bundle.is_file()
            and css_bundle.is_file()
        ):
            self._view = _InvoiceUniverWebView(self, self._change_univer_zoom)
            settings = self._view.settings()
            if QWebEngineSettings is not None:
                attrs = QWebEngineSettings.WebAttribute
                for name, enabled in (
                    ("JavascriptEnabled", True),
                    ("LocalContentCanAccessFileUrls", True),
                    ("LocalContentCanAccessRemoteUrls", False),
                    ("JavascriptCanAccessClipboard", True),
                    ("JavascriptCanPaste", True),
                ):
                    attribute = getattr(attrs, name, None)
                    if attribute is not None:
                        settings.setAttribute(attribute, enabled)
            self._channel = QWebChannel(self._view.page())
            self._bridge = _InvoiceUniverBridge(self)
            self._channel.registerObject("kargoBridge", self._bridge)
            self._view.page().setWebChannel(self._channel)
            self._view.loadFinished.connect(self._on_page_loaded)
            self._view.load(QUrl.fromLocalFile(str(html_path)))
            self._layout.addWidget(self._view, 1)
            self._using_univer = True
        else:
            self._fallback_label = QLabel(
                "Editor Univer belum dibangun. Jalankan `npm install` lalu "
                "`npm run build:invoice-univer` dari folder utama proyek. "
                "Tabel Qt lama tetap tersedia sementara."
            )
            self._fallback_label.setWordWrap(True)
            self._fallback_label.setStyleSheet(
                "QLabel { color: #8a6d3b; padding: 6px 8px; }"
            )
            self._layout.addWidget(self._fallback_label)
            self._layout.addWidget(self._model, 1)
            self._model.show()

        self._model.itemChanged.connect(self._on_model_item_changed)
        self._model.currentCellChanged.connect(self._on_model_current_cell_changed)
        qt_model = self._model.model()
        for signal in (
            qt_model.rowsInserted,
            qt_model.rowsRemoved,
            qt_model.columnsInserted,
            qt_model.columnsRemoved,
            qt_model.modelReset,
        ):
            signal.connect(self._on_model_structure_changed)

    def __getattr__(self, name):
        model = self.__dict__.get("_model")
        if model is not None and hasattr(model, name):
            return getattr(model, name)
        raise AttributeError(name)

    @property
    def itemChanged(self):
        return self._model.itemChanged

    @property
    def sheetEdited(self):
        return self._model.sheetEdited

    @property
    def invoice_columns(self):
        return self._model.invoice_columns

    @invoice_columns.setter
    def invoice_columns(self, columns):
        self._model.invoice_columns = deepcopy(list(columns or []))
        self._structure_dirty = True
        self.refresh_univer()

    @property
    def mutation_locked(self) -> bool:
        return bool(getattr(self._model, "mutation_locked", False))

    @mutation_locked.setter
    def mutation_locked(self, locked):
        self.set_mutation_locked(locked)

    @property
    def using_univer(self) -> bool:
        return self._using_univer and self._grid_ready

    def blockSignals(self, block):
        previous_model = self._model.blockSignals(bool(block))
        super().blockSignals(bool(block))
        return previous_model

    def setUpdatesEnabled(self, enabled):
        enabled = bool(enabled)
        self._updates_suppressed = not enabled
        super().setUpdatesEnabled(enabled)
        self._model.setUpdatesEnabled(enabled)
        if enabled:
            self.refresh_univer()

    def updatesEnabled(self):
        return not self._updates_suppressed and super().updatesEnabled()

    def viewport(self):
        return self._view if self._view is not None else self._model.viewport()

    def setFocus(self, *args, **kwargs):
        if self._view is not None:
            self._view.setFocus(*args, **kwargs)
        else:
            self._model.setFocus(*args, **kwargs)

    def _change_univer_zoom(self, direction):
        """Ubah zoom sheet aktif tanpa mengubah zoom halaman Qt WebEngine."""
        if not self._grid_ready or self._view is None:
            return
        step = 1 if int(direction) > 0 else -1
        self._run_js(f"window.kargoAdjustZoom({step});")

    def set_mutation_locked(self, locked):
        self._model.set_mutation_locked(locked)
        if self._grid_ready:
            self._run_js(f"window.kargoSetLocked({str(bool(locked)).lower()});")

    def setAlternatingRowColors(self, enabled):
        self._model.setAlternatingRowColors(bool(enabled))

    def _on_model_structure_changed(self, *_):
        if self._suppress_model_refresh or self._applying_web_snapshot:
            return
        self._structure_dirty = True
        self.refresh_univer()

    def refresh_univer(self, *_):
        if (
            not self._using_univer
            or not self._web_ready
            or self._updates_suppressed
            or self._suppress_model_refresh
            or self._applying_web_snapshot
        ):
            return
        if self._refresh_scheduled:
            return
        self._refresh_scheduled = True
        QTimer.singleShot(0, self._emit_model_to_web)

    def _run_js(self, source, callback=None):
        if self._view is not None and self._web_ready:
            if callback is None:
                self._view.page().runJavaScript(str(source))
            else:
                self._view.page().runJavaScript(str(source), callback)

    def capture_live_model(self, callback):
        """Ambil snapshot langsung dari workbook aktif sebelum template diganti."""
        if (
            not callable(callback)
            or self._view is None
            or not self._web_ready
            or not self._grid_ready
        ):
            return False

        source = (
            "(() => {"
            " try {"
            "  const capture = window.kargoCaptureCurrentModel;"
            "  return typeof capture === 'function' ? capture() : null;"
            " } catch (error) {"
            "  console.error('[Kargo] Template snapshot capture failed', error);"
            "  return null;"
            " }"
            "})()"
        )

        def _dispatch_capture():
            if self._view is None or not self._web_ready or not self._grid_ready:
                callback(None)
                return
            try:
                self._view.page().runJavaScript(source, callback)
            except Exception as exc:
                print(f"[INVOICE-UNIVER] Template snapshot dispatch failed: {exc}")
                callback(None)

        # Beri Qt satu putaran event agar editor aktif Univer selesai commit
        # setelah fokus berpindah ke ComboBox Template.
        QTimer.singleShot(0, _dispatch_capture)
        return True

    def capture_workbook(self, callback):
        """Ambil snapshot semua sheet + model setiap invoice dari Univer."""
        if (
            not callable(callback)
            or self._view is None
            or not self._web_ready
            or not self._grid_ready
        ):
            return False

        source = (
            "(() => {"
            " try {"
            "  const capture = window.kargoCaptureWorkbook;"
            "  return typeof capture === 'function' ? capture() : null;"
            " } catch (error) {"
            "  console.error('[Kargo] Workbook capture failed', error);"
            "  return null;"
            " }"
            "})()"
        )

        def _dispatch_capture():
            if self._view is None or not self._web_ready or not self._grid_ready:
                callback(None)
                return
            try:
                self._view.page().runJavaScript(source, callback)
            except Exception as exc:
                print(f"[INVOICE-UNIVER] Workbook capture dispatch failed: {exc}")
                callback(None)

        QTimer.singleShot(0, _dispatch_capture)
        return True

    def add_invoice_sheet(self, payload, callback=None):
        if not self._web_ready or not self._grid_ready:
            return False
        source = f"window.kargoAddInvoiceSheet({_json_dumps(payload)});"
        self._run_js(source, callback)
        return True

    def set_invoice_sheet_meta(self, sheet_id, metadata):
        if not self._web_ready or not self._grid_ready:
            return False
        self._run_js(
            "window.kargoSetInvoiceSheetMeta(%s,%s);" % (
                _json_dumps(str(sheet_id or "")), _json_dumps(metadata or {})
            )
        )
        return True

    def activate_invoice_sheet(self, sheet_id):
        if not self._web_ready or not self._grid_ready:
            return False
        self._run_js(f"window.kargoActivateInvoiceSheet({_json_dumps(str(sheet_id or ''))});")
        return True

    def apply_live_snapshot(self, payload):
        """Salin snapshot aktif ke model Python sebelum struktur sheet dibangun ulang."""
        if not isinstance(payload, str) or not payload.strip():
            return False
        try:
            data = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(data, dict):
            return False
        columns = data.get("columns")
        rows = data.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            return False
        amount_key = str(
            getattr(self._owner, "active_template", {}).get("amount_key", "amount")
        )
        column_keys = {
            str(column.get("key"))
            for column in columns
            if isinstance(column, dict)
        }
        if amount_key and amount_key not in column_keys:
            return False
        previous_error = self._last_error
        self._on_web_sheet_snapshot_changed(payload)
        return self._last_error == previous_error

    def _on_page_loaded(self, ok):
        if not ok:
            self._on_web_error("Halaman Univer gagal dimuat dari folder lokal.")

    def _on_web_ready(self):
        self._web_ready = True
        if self._pending_theme:
            self._run_js(f"window.kargoApplyTheme({_json_dumps(self._pending_theme)});")
        if self._pending_snapshot:
            snapshot = self._pending_snapshot
            sheet_metadata = getattr(self, "_pending_workbook_sheet_metadata", []) or []
            self._pending_snapshot = None
            self._pending_workbook_sheet_metadata = []
            self._run_js(
                "window.kargoRestoreSnapshot(%s,%s);" % (
                    _json_dumps(snapshot), _json_dumps(sheet_metadata)
                )
            )
        else:
            self._structure_dirty = True
            self._emit_model_to_web()

    def _on_grid_ready(self):
        self._grid_ready = True
        self._run_js(f"window.kargoSetLocked({str(self.mutation_locked).lower()});")
        if self._pending_theme:
            self._run_js(f"window.kargoApplyTheme({_json_dumps(self._pending_theme)});")
        if self._pending_page_setup is None:
            try:
                from utils.printer.invoice_page_setup import muat_page_setup
                self._pending_page_setup = muat_page_setup()
            except Exception:
                self._pending_page_setup = {
                    "paper_size": "NCR", "orientation": "landscape",
                    "width_mm": 139.7, "height_mm": 241.3,
                    "margins": {"top": 4, "bottom": 4, "left": 4, "right": 4},
                    "scaling": "actual", "repeat_header_rows": 1,
                    "page_order": "down_then_over", "show_page_breaks": True,
                }
        invoice_data = self._pending_page_setup_invoice_data or {"layout_type": "standard"}
        owner_context = getattr(self._owner, "_invoice_pdfmake_context", None)
        if callable(owner_context):
            try:
                invoice_data = owner_context()
            except Exception:
                pass
        self.set_page_setup(self._pending_page_setup, invoice_data)

    def _on_snapshot_available(self, payload):
        try:
            data = json.loads(payload or "{}")
            snapshot = data.get("workbook") if isinstance(data, dict) else None
            if isinstance(snapshot, dict):
                self._last_snapshot = snapshot
                row_tokens = data.get("rowTokens") or []
                if isinstance(row_tokens, list):
                    self._row_tokens = [str(value) for value in row_tokens]
                    if len(self._row_tokens) == self._model.rowCount():
                        for index, token in enumerate(self._row_tokens):
                            self._model.set_row_token(index, token)
        except (TypeError, ValueError, json.JSONDecodeError):
            return

    def _on_web_error(self, message):
        self._last_error = str(message or "Error tidak diketahui")[:2000]
        print(f"[INVOICE-UNIVER] {self._last_error}")
        if self._fallback_label is None:
            self._fallback_label = QLabel(self)
            self._fallback_label.setWordWrap(True)
            self._fallback_label.setStyleSheet(
                "QLabel { color: #b45309; background: #fff7ed; padding: 6px 8px; }"
            )
            self._layout.insertWidget(0, self._fallback_label)
        self._fallback_label.setText(
            "Editor Univer mengalami masalah. Detail: " + self._last_error
        )

    def _new_row_token(self):
        return uuid.uuid4().hex

    def _columns_payload(self):
        columns = list(getattr(self._model, "invoice_columns", []) or [])
        result = []
        for index in range(self._model.columnCount()):
            config = dict(columns[index]) if index < len(columns) else {}
            header_item = self._model.horizontalHeaderItem(index)
            key = str(config.get("key") or f"column_{index}")
            title = str(
                config.get("title")
                or (header_item.text() if header_item else key)
            )
            try:
                width = int(self._model.columnWidth(index))
            except (TypeError, ValueError, RuntimeError):
                width = int(config.get("width", 110) or 110)
            result.append({
                "key": key,
                "title": title,
                "type": str(config.get("type", "text")),
                "width": max(45, width or int(config.get("width", 110) or 110)),
                "stretch": bool(config.get("stretch")),
            })
        return result

    def _model_payload(self):
        columns = self._columns_payload()
        while len(self._row_tokens) < self._model.rowCount():
            self._row_tokens.append(self._new_row_token())
        self._row_tokens = self._row_tokens[:self._model.rowCount()]

        rows = []
        seen_tokens = set()
        for row_index in range(self._model.rowCount()):
            cells = {}
            hidden = self._model.row_template_values(row_index)
            formulas = hidden.get("__formula_cells__", {})
            formulas = formulas if isinstance(formulas, dict) else {}
            for column_index, column in enumerate(columns):
                item = self._model.item(row_index, column_index)
                value = item.text() if item is not None else ""
                cells[column["key"]] = {
                    "value": value,
                    "formula": str(formulas.get(column["key"]) or ""),
                }
            token = self._model.row_token(row_index)
            if not token or token in seen_tokens:
                token = self._new_row_token()
                self._model.set_row_token(row_index, token)
            seen_tokens.add(token)
            self._row_tokens[row_index] = token
            rows.append({
                "id": token,
                "cells": cells,
                "hidden": deepcopy(hidden),
                "source": self._model.row_source_metadata(row_index),
            })
        sheet_meta = {}
        owner_meta_builder = getattr(self._owner, "_meta_sheet_aktif_dari_form", None)
        if callable(owner_meta_builder):
            try:
                active_id = str(getattr(self._owner, "_active_workbook_sheet_id", "") or "")
                base_meta = getattr(self._owner, "_workbook_sheet_meta", {}).get(active_id, {})
                sheet_meta = owner_meta_builder(base_meta)
            except Exception as exc:
                print(f"[INVOICE-UNIVER] Sheet metadata payload skipped: {exc}")
        return {
            "columns": columns,
            "rows": rows,
            "locked": self.mutation_locked,
            "locale": "id",
            "amountKey": str(
                getattr(self._owner, "active_template", {}).get("amount_key", "amount")
            ),
            "sheetMeta": sheet_meta if isinstance(sheet_meta, dict) else {},
        }

    def _emit_model_to_web(self):
        self._refresh_scheduled = False
        if not self._web_ready or self._updates_suppressed:
            return
        payload = self._model_payload()
        if self._grid_ready and bool(getattr(self._owner, "_workbook_mode_active", False)):
            self._structure_dirty = False
            self._run_js(f"window.kargoSyncActiveSheetModel({_json_dumps(payload)});")
        elif not self._grid_ready or self._structure_dirty:
            self._structure_dirty = False
            self._run_js(f"window.kargoLoadModel({_json_dumps(payload)});")
        else:
            self._run_js(f"window.kargoSyncModel({_json_dumps(payload)});")

    def _column_key(self, index):
        if 0 <= index < len(self._model.invoice_columns):
            return str(self._model.invoice_columns[index].get("key") or "")
        return ""

    def _on_model_item_changed(self, item):
        if self._applying_web_snapshot or not self._grid_ready or item is None:
            return
        row, column = item.row(), item.column()
        key = self._column_key(column)
        if row < 0 or not key:
            return
        hidden = self._model.row_template_values(row)
        formula_map = hidden.get("__formula_cells__", {})
        formula = str(formula_map.get(key) or "") if isinstance(formula_map, dict) else ""
        self._run_js(
            "window.kargoSetModelCell(%s,%s,%s,%s);" % (
                row,
                _json_dumps(key),
                _json_dumps(item.text()),
                _json_dumps(formula),
            )
        )

    def _on_model_current_cell_changed(self, row, column, _previous_row, _previous_column):
        if self._handling_web_selection or not self._grid_ready:
            return
        key = self._column_key(column)
        if row >= 0 and key:
            self._run_js(
                "window.kargoSetModelSelection(%s,%s);" % (row, _json_dumps(key))
            )

    def _on_web_selection_changed(self, payload):
        try:
            selections = json.loads(payload or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(selections, list):
            return
        self._handling_web_selection = True
        try:
            self._model.clearSelection()
            for selection in selections:
                if not isinstance(selection, dict):
                    continue
                top = int(selection.get("top", 1)) - 1
                bottom = int(selection.get("bottom", top + 1)) - 1
                left = int(selection.get("left", 0))
                right = int(selection.get("right", left))
                if self._model.rowCount() and self._model.columnCount():
                    top = max(0, min(top, self._model.rowCount() - 1))
                    bottom = max(top, min(bottom, self._model.rowCount() - 1))
                    left = max(0, min(left, self._model.columnCount() - 1))
                    right = max(left, min(right, self._model.columnCount() - 1))
                    from PySide6.QtWidgets import QTableWidgetSelectionRange
                    self._model.setRangeSelected(
                        QTableWidgetSelectionRange(top, left, bottom, right), True
                    )
            if selections and self._model.rowCount() and self._model.columnCount():
                first = selections[0]
                row = max(0, min(int(first.get("top", 1)) - 1, self._model.rowCount() - 1))
                column = max(0, min(int(first.get("left", 0)), self._model.columnCount() - 1))
                self._model.setCurrentCell(row, column)
        except (TypeError, ValueError, RuntimeError):
            self._model.clearSelection()
        finally:
            self._handling_web_selection = False

    def _on_web_sheet_snapshot_changed(self, payload):
        try:
            data = json.loads(payload or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return

        active_sheet_changed = bool(data.get("activeSheetChanged"))
        if active_sheet_changed:
            callback = getattr(self._owner, "_on_workbook_sheet_activated", None)
            if callable(callback):
                try:
                    callback(
                        str(data.get("sheetId") or ""),
                        str(data.get("sheetName") or "Sheet"),
                        data.get("sheetMeta") if isinstance(data.get("sheetMeta"), dict) else {},
                        data.get("columns") if isinstance(data.get("columns"), list) else [],
                    )
                except Exception as exc:
                    self._on_web_error(f"Gagal mengganti invoice sheet aktif: {exc}")
                    return
        if self.mutation_locked and not active_sheet_changed:
            self.refresh_univer()
            return

        columns = data.get("columns")
        rows = data.get("rows")
        workbook = data.get("workbook")
        row_tokens = data.get("rowTokens")
        if not isinstance(columns, list) or not isinstance(rows, list):
            return
        if not columns:
            self._reject_schema_change("Invoice harus memiliki minimal satu kolom.")
            return

        amount_key = str(
            getattr(self._owner, "active_template", {}).get("amount_key", "amount")
        )
        if amount_key and not any(str(col.get("key")) == amount_key for col in columns if isinstance(col, dict)):
            self._reject_schema_change(
                f"Kolom total '{amount_key}' tidak boleh dihapus. Ubah judul kolom bila diperlukan."
            )
            return

        old_columns = self._columns_payload()
        old_tokens = list(self._row_tokens)
        old_state = {}
        for index, token in enumerate(old_tokens):
            if index >= self._model.rowCount():
                continue
            old_state[token] = {
                "source": self._model.row_source_metadata(index),
                "hidden": self._model.row_template_values(index),
                "cells": {
                    col["key"]: (
                        self._model.item(index, col_index).text()
                        if self._model.item(index, col_index) is not None else ""
                    )
                    for col_index, col in enumerate(old_columns)
                },
            }

        normalized_columns = []
        seen_keys = set()
        for index, raw in enumerate(columns):
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key") or f"custom_{uuid.uuid4().hex[:10]}")
            if key in seen_keys:
                key = f"custom_{uuid.uuid4().hex[:10]}"
            seen_keys.add(key)
            title = str(raw.get("title") or f"KOLOM {index + 1}").strip() or f"KOLOM {index + 1}"
            data_type = str(raw.get("type") or "text")
            if data_type not in {"text", "integer", "decimal", "currency", "date"}:
                data_type = "text"
            width = raw.get("width", 110)
            try:
                width = max(45, min(1200, int(float(width))))
            except (TypeError, ValueError):
                width = 110
            normalized_columns.append({
                "key": key,
                "title": title,
                "type": data_type,
                "width": width,
                "stretch": bool(raw.get("stretch", False)),
            })
        if not normalized_columns:
            self._reject_schema_change("Tidak ditemukan kolom yang valid.")
            return

        normalized_rows = []
        incoming_tokens = []
        seen_row_tokens = set()
        inserted_blank_row = False
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            token = str(raw_row.get("id") or "")
            if not token or token in seen_row_tokens:
                token = self._new_row_token()
            seen_row_tokens.add(token)
            incoming_tokens.append(token)
            raw_cells = raw_row.get("cells") or {}
            state = old_state.get(token, {})
            raw_hidden = raw_row.get("hidden")
            hidden = dict(raw_hidden) if isinstance(raw_hidden, dict) else dict(state.get("hidden") or {})
            source = (
                deepcopy(raw_row.get("source"))
                if "source" in raw_row and isinstance(raw_row.get("source"), dict)
                else (None if "source" in raw_row else state.get("source"))
            )

            active_keys = {col["key"] for col in normalized_columns}
            for old_key, old_value in (state.get("cells") or {}).items():
                if old_key not in active_keys and old_value not in (None, ""):
                    hidden[old_key] = old_value

            values = {}
            formulas = dict(hidden.get("__formula_cells__") or {})
            for col in normalized_columns:
                cell = raw_cells.get(col["key"], {}) if isinstance(raw_cells, dict) else {}
                if not isinstance(cell, dict):
                    cell = {"value": cell}
                value = cell.get("value", "")
                formula = str(cell.get("formula") or "")
                if value is None:
                    value = ""
                values[col["key"]] = str(value)
                if formula:
                    formulas[col["key"]] = formula
                else:
                    formulas.pop(col["key"], None)

            if formulas:
                hidden["__formula_cells__"] = formulas
            else:
                hidden.pop("__formula_cells__", None)

            resi_index = next((i for i, col in enumerate(normalized_columns) if col["key"] == "resi"), -1)
            if source and resi_index >= 0:
                number = str(source.get("no_resi") or "").strip().upper()
                if values.get("resi", "").strip().upper() != number:
                    source = None
            normalized_rows.append({
                "token": token,
                "values": values,
                "hidden": hidden,
                "source": source,
            })

        if not normalized_rows:
            inserted_blank_row = True
            normalized_rows.append({
                "token": self._new_row_token(),
                "values": {col["key"]: "" for col in normalized_columns},
                "hidden": {},
                "source": None,
            })
            incoming_tokens = [normalized_rows[0]["token"]]

        owner = self._owner
        schema_changed = len(old_columns) != len(normalized_columns) or any(
            index >= len(old_columns)
            or any(
                str(old_columns[index].get(field, "")) != str(normalized_columns[index].get(field, ""))
                for field in ("key", "title", "type", "width")
            )
            for index in range(len(normalized_columns))
        )
        if schema_changed:
            template = deepcopy(getattr(owner, "active_template", {}) or {})
            template["columns"] = deepcopy(normalized_columns)
            formula_config = template.get("formula")
            if isinstance(formula_config, dict):
                required = list(formula_config.get("sources") or []) + [formula_config.get("target")]
                if any(key and key not in {col["key"] for col in normalized_columns} for key in required):
                    template.pop("formula", None)
            template["customized"] = True
            template["version"] = max(1, int(template.get("version", 1) or 1))
            owner.active_template = template
            owner.current_template_override = deepcopy(template)
        owner.active_columns = deepcopy(normalized_columns)
        owner.headers_aktif = [col["title"] for col in normalized_columns]

        self._applying_web_snapshot = True
        self._suppress_model_refresh = True
        previous_signals = self._model.blockSignals(True)
        try:
            self._model.clear()
            self._model.invoice_columns = deepcopy(normalized_columns)
            self._model.setColumnCount(len(normalized_columns))
            self._model.setHorizontalHeaderLabels([col["title"] for col in normalized_columns])
            self._model.setRowCount(len(normalized_rows))
            for row_index, row_data in enumerate(normalized_rows):
                for column_index, column in enumerate(normalized_columns):
                    value = row_data["values"].get(column["key"], "")
                    item = owner._buat_item_tabel(value, column)
                    self._model.setItem(row_index, column_index, item)
                self._model.set_row_template_values(row_index, row_data["hidden"])
                self._model.set_row_source_metadata(row_index, row_data["source"])
                self._model.set_row_token(row_index, row_data["token"])
            self._model.renumber_rows()
            self._row_tokens = incoming_tokens[:len(normalized_rows)]
            self._last_snapshot = workbook if isinstance(workbook, dict) else self._last_snapshot
            self._structure_dirty = inserted_blank_row
        except Exception as exc:
            self._on_web_error(f"Gagal menerapkan perubahan sheet ke model Python: {exc}")
        finally:
            self._model.blockSignals(previous_signals)
            self._suppress_model_refresh = False
            self._applying_web_snapshot = False

        if not active_sheet_changed:
            self._model.sheetEdited.emit()
        if inserted_blank_row:
            self.refresh_univer()

    def _reject_schema_change(self, message):
        QMessageBox.warning(self._owner or self, "Struktur Invoice", message)
        self._structure_dirty = True
        self.refresh_univer()

    def _on_page_setup_requested(self):
        """Open Page Setup safely after the WebChannel slot has returned."""
        if self._page_setup_dialog_open:
            return

        handler = getattr(self._owner, "atur_page_setup", None)
        if not callable(handler):
            QMessageBox.warning(
                self._owner or self,
                "Page Setup",
                "Dialog Page Setup Invoice belum tersedia pada tab aktif.",
            )
            return

        self._page_setup_dialog_open = True

        def _open_dialog():
            try:
                handler()
            except Exception as exc:
                QMessageBox.critical(
                    self._owner or self,
                    "Page Setup",
                    f"Gagal membuka pengaturan halaman Invoice:\n{exc}",
                )
            finally:
                self._page_setup_dialog_open = False

        # Jangan membuka dialog modal di dalam callback WebChannel.
        QTimer.singleShot(0, _open_dialog)

    def set_page_setup(self, page_setup: dict | None, invoice_data: dict | None = None):
        """Apply Page Setup to the live Univer page-break overlay."""
        try:
            from utils.printer.invoice_page_setup import normalisasi_page_setup
            self._pending_page_setup = normalisasi_page_setup(page_setup or {})
        except Exception:
            self._pending_page_setup = dict(page_setup or {})
        if isinstance(invoice_data, dict):
            self._pending_page_setup_invoice_data = dict(invoice_data)
        if self._grid_ready:
            self._run_js(
                "window.kargoSetPageSetup(%s,%s);" % (
                    _json_dumps(self._pending_page_setup or {}),
                    _json_dumps(self._pending_page_setup_invoice_data or {"layout_type": "standard"}),
                )
            )
        return self._pending_page_setup

    def generate_pdf(
        self,
        page_setup: dict | None,
        callback,
        invoice_data: dict | None = None,
        progress_callback=None,
    ):
        """Generate a PDF from the current Univer workbook using pdfmake.

        Each request has an ID and a watchdog timer. This prevents a lost
        WebChannel response from leaving the Invoice tab permanently busy.
        callback receives ``(pdf_bytes, error_message)`` on the GUI thread.
        """
        if not self._using_univer or not self._grid_ready:
            if callable(callback):
                callback(None, "Editor Univer belum siap; PDF spreadsheet tidak dapat dibuat.")
            return False
        if self._view is None or not self._web_ready:
            if callable(callback):
                callback(None, "Jembatan Qt-WebChannel Univer belum siap untuk membuat PDF.")
            return False

        if self._pending_pdf_callback is not None:
            # Recover defensively if a previous timer was stopped unexpectedly.
            if not self._pdf_request_timer.isActive():
                stale_id = self._pending_pdf_request_id
                self._complete_pdf_callback(
                    None,
                    "Permintaan PDF sebelumnya kedaluwarsa dan sudah dilepas. Silakan coba lagi.",
                    request_id=stale_id,
                )
            else:
                if callable(callback):
                    callback(None, "Proses PDF Invoice sebelumnya masih berjalan. Tunggu sampai selesai atau coba lagi setelah proses dibatalkan.")
                return True

        request_id = uuid.uuid4().hex
        self._pending_pdf_callback = callback
        self._pending_pdf_progress_callback = progress_callback
        self._last_pdf_progress_message = "Memulai permintaan PDF..."
        self._pending_pdf_request_id = request_id
        self._pdf_request_timer.start(self._pdf_request_timeout_ms)

        try:
            setup = page_setup or {}
            invoice = invoice_data or {}

            try:
                from utils.printer.invoice_page_setup import normalisasi_page_setup
                self._pending_page_setup = normalisasi_page_setup(setup)
            except Exception:
                self._pending_page_setup = deepcopy(setup)
            if isinstance(invoice, dict):
                self._pending_page_setup_invoice_data = deepcopy(invoice)

            diagnostic_source = (
                "(() => {"
                " const d = typeof window.kargoPdfBridgeDiagnostics === 'function' "
                "   ? window.kargoPdfBridgeDiagnostics() : {};"
                " return JSON.stringify({"
                "   protocol: Number(window.kargoPdfRequestProtocol) || 0,"
                "   generatePdf: typeof window.kargoGeneratePdf === 'function',"
                "   diagnosticsAvailable: typeof window.kargoPdfBridgeDiagnostics === 'function',"
                "   bridgeReady: Boolean(d.bridgeReady),"
                "   pdfProgressAvailable: Boolean(d.pdfProgressAvailable),"
                "   pdfReadyAvailable: Boolean(d.pdfReadyAvailable),"
                "   pdfErrorAvailable: Boolean(d.pdfErrorAvailable),"
                "   workbookReady: Boolean(d.workbookReady)"
                " });"
                "})()"
            )
            print(
                "[INVOICE-UNIVER] PDF preflight dispatch: "
                f"request={request_id!r}, view_visible={self._view.isVisible()}, "
                f"web_ready={self._web_ready}, grid_ready={self._grid_ready}"
            )
            self._view.page().runJavaScript(
                diagnostic_source,
                lambda result, current_id=request_id, current_setup=deepcopy(setup), current_invoice=deepcopy(invoice):
                    self._on_pdf_preflight_result(current_id, result, current_setup, current_invoice),
            )
        except Exception as exc:
            self._complete_pdf_callback(
                None,
                f"Gagal memulai proses PDF di Univer: {exc}",
                request_id=request_id,
            )
        return True

    def _on_pdf_preflight_result(self, request_id: str, result, setup: dict, invoice: dict):
        """Validate the live WebEngine/Qt bridge before starting pdfmake."""
        if request_id != self._pending_pdf_request_id:
            return
        try:
            if isinstance(result, str):
                diagnostic = json.loads(result) if result.strip() else {}
            elif isinstance(result, dict):
                diagnostic = result
            else:
                diagnostic = {}
        except (TypeError, ValueError, json.JSONDecodeError):
            diagnostic = {}

        keys = (
            "protocol", "generatePdf", "diagnosticsAvailable", "bridgeReady",
            "pdfProgressAvailable", "pdfReadyAvailable", "pdfErrorAvailable",
            "workbookReady",
        )
        summary = {key: diagnostic.get(key) for key in keys}
        print("[INVOICE-UNIVER] PDF live preflight: " + json.dumps(summary, ensure_ascii=False))

        missing = []
        if diagnostic.get("protocol") != 1:
            missing.append("protokol PDF bundle bukan versi 1")
        if diagnostic.get("generatePdf") is not True:
            missing.append("window.kargoGeneratePdf tidak tersedia")
        if diagnostic.get("diagnosticsAvailable") is not True:
            missing.append("fungsi diagnostik JS tidak tersedia")
        if diagnostic.get("bridgeReady") is not True:
            missing.append("Qt WebChannel belum siap")
        for key, label in (
            ("pdfProgressAvailable", "slot pdfProgress tidak tersedia"),
            ("pdfReadyAvailable", "slot pdfReady tidak tersedia"),
            ("pdfErrorAvailable", "slot pdfError tidak tersedia"),
        ):
            if diagnostic.get(key) is not True:
                missing.append(label)
        if diagnostic.get("workbookReady") is not True:
            missing.append("workbook/worksheet Univer belum siap")

        if missing:
            self._complete_pdf_callback(
                None,
                "Pemeriksaan awal Live Preview gagal: " + "; ".join(missing) + ". "
                "Detail runtime: " + json.dumps(summary, ensure_ascii=False),
                request_id=request_id,
            )
            return

        source = (
            "(() => {"
            " const fn = window.kargoGeneratePdf;"
            " if (typeof fn !== 'function') return false;"
            f" void fn({_json_dumps(setup)}, {_json_dumps(invoice)}, {_json_dumps(request_id)});"
            " return true;"
            "})()"
        )
        try:
            self._view.page().runJavaScript(
                source,
                lambda dispatch_result, current_id=request_id:
                    self._on_pdf_js_dispatch_result(current_id, dispatch_result),
            )
        except Exception as exc:
            self._complete_pdf_callback(
                None, f"Gagal memanggil renderer PDF Univer: {exc}", request_id=request_id
            )

    def _on_pdf_js_dispatch_result(self, request_id: str, result):
        if request_id != self._pending_pdf_request_id:
            return
        if result is False or result is None:
            self._complete_pdf_callback(
                None,
                "Fungsi PDF Univer tidak ditemukan atau bundle JavaScript belum diperbarui. Jalankan npm run build:invoice-univer lalu buka ulang Kargo.",
                request_id=request_id,
            )

    def _on_pdf_request_timeout(self):
        request_id = self._pending_pdf_request_id
        if request_id is None or self._pending_pdf_callback is None:
            return
        print(f"[INVOICE-UNIVER] PDF request timeout: {request_id}; last stage={self._last_pdf_progress_message}")
        detail = (
            "Pembuatan PDF tidak mendapat balasan dari Univer selama 90 detik. "
            f"Tahap terakhir: {self._last_pdf_progress_message or 'tidak ada progress yang diterima'}. "
            "Status proses sudah dilepas; periksa error JavaScript/Qt WebEngine, lalu coba Preview kembali."
        )
        self._complete_pdf_callback(
            None,
            detail,
            request_id=request_id,
        )

    def _complete_pdf_callback(self, pdf_bytes=None, error="", request_id=None):
        current_id = self._pending_pdf_request_id
        if request_id is not None and request_id != current_id:
            # Ignore late responses from a timed-out or superseded request.
            return False
        callback = self._pending_pdf_callback
        if callback is None:
            return False

        self._pdf_request_timer.stop()
        self._pending_pdf_callback = None
        self._pending_pdf_progress_callback = None
        self._pending_pdf_request_id = None

        byte_count = len(pdf_bytes) if isinstance(pdf_bytes, (bytes, bytearray)) else 0
        print(
            "[INVOICE-UNIVER] PDF request completed; callback queued: "
            f"request={current_id!r}, success={bool(pdf_bytes) and not error}, "
            f"bytes={byte_count}, has_error={bool(error)}"
        )

        def _invoke_callback(
            _callback=callback,
            _pdf_bytes=pdf_bytes,
            _error=str(error or ""),
        ):
            try:
                if callable(_callback):
                    _callback(_pdf_bytes, _error)
            except Exception as exc:
                print(f"[INVOICE-UNIVER] PDF callback failed: {exc}")

        QTimer.singleShot(0, _invoke_callback)
        return True

    @staticmethod
    def _decode_pdf_bridge_payload(payload: str, value_key: str):
        """Read request-tagged payloads, while accepting the previous bridge format."""
        raw = str(payload or "").strip()
        if not raw:
            return None, ""
        try:
            event = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            # Backward compatibility for a legacy bundle; request IDs are used
            # whenever the rebuilt bundle sends the new envelope format.
            return None, raw
        if isinstance(event, dict):
            request_id = str(event.get("request_id") or "") or None
            value = str(event.get(value_key) or "")
            return request_id, value
        return None, raw

    def _on_pdf_progress(self, payload: str):
        """Forward renderer stages to the open Preview without changing request state."""
        request_id, message = self._decode_pdf_bridge_payload(payload, "message")
        print(
            "[INVOICE-UNIVER] PDF progress slot received: "
            f"request={request_id!r}, active={self._pending_pdf_request_id!r}, "
            f"message={message!r}, callback={callable(self._pending_pdf_progress_callback)}"
        )
        if request_id is not None and request_id != self._pending_pdf_request_id:
            print("[INVOICE-UNIVER] Ignored progress for a different request ID.")
            return
        callback = self._pending_pdf_progress_callback
        if message:
            self._last_pdf_progress_message = message
        if callable(callback) and message:
            try:
                callback(message)
            except Exception as exc:
                print(f"[INVOICE-UNIVER] PDF progress callback failed: {exc}")
        if message:
            print(f"[INVOICE-UNIVER] {message}")

    def _on_pdf_ready(self, payload: str):
        request_id = None
        try:
            request_id, encoded = self._decode_pdf_bridge_payload(payload, "payload")
            if request_id is not None and request_id != self._pending_pdf_request_id:
                print(f"[INVOICE-UNIVER] Ignored stale PDF response: {request_id}")
                return
            if not encoded:
                raise ValueError("Renderer pdfmake mengembalikan PDF kosong.")
            pdf_bytes = base64.b64decode(encoded, validate=True)
            if not pdf_bytes.startswith(b"%PDF-"):
                raise ValueError("Data yang diterima bukan file PDF yang valid.")
            print(
                "[INVOICE-UNIVER] PDF ready received: "
                f"request={request_id!r}, bytes={len(pdf_bytes)}"
            )
            self._complete_pdf_callback(pdf_bytes, "", request_id=request_id)
        except (ValueError, binascii.Error) as exc:
            print(
                "[INVOICE-UNIVER] PDF ready decode failed: "
                f"request={request_id!r}, error={exc}"
            )
            self._complete_pdf_callback(None, str(exc), request_id=request_id)

    def _on_pdf_error(self, message: str):
        request_id, detail = self._decode_pdf_bridge_payload(message, "message")
        if request_id is not None and request_id != self._pending_pdf_request_id:
            print(f"[INVOICE-UNIVER] Ignored stale PDF error: {request_id}")
            return
        self._complete_pdf_callback(
            None,
            detail or "Gagal membuat PDF dengan pdfmake.",
            request_id=request_id,
        )

    def get_univer_snapshot(self):
        return deepcopy(self._last_snapshot) if isinstance(self._last_snapshot, dict) else None

    def restore_univer_snapshot(self, snapshot, sheets_metadata=None):
        if not isinstance(snapshot, dict):
            return
        self._pending_snapshot = deepcopy(snapshot)
        self._pending_workbook_sheet_metadata = deepcopy(list(sheets_metadata or []))
        if self._web_ready:
            pending = self._pending_snapshot
            sheet_metadata = self._pending_workbook_sheet_metadata
            self._pending_snapshot = None
            self._pending_workbook_sheet_metadata = []
            self._run_js(
                "window.kargoRestoreSnapshot(%s,%s);" % (
                    _json_dumps(pending), _json_dumps(sheet_metadata)
                )
            )

    def clear_univer_snapshot(self):
        self._pending_snapshot = None
        self._last_snapshot = None

    def apply_theme(self, is_dark, font_size_pt, row_height=28):
        palette = QApplication.palette()
        theme = {
            "dark": bool(is_dark),
            "bg": palette.color(QPalette.ColorRole.Base).name(),
            "text": palette.color(QPalette.ColorRole.Text).name(),
            "alt": palette.color(QPalette.ColorRole.AlternateBase).name(),
            "border": palette.color(QPalette.ColorRole.Mid).name(),
            "header": palette.color(QPalette.ColorRole.Button).name(),
            "fontSize": float(font_size_pt),
            "rowHeight": int(row_height),
            "fontFamily": str(
                dapatkan_font_aplikasi_aktif()
                or self._model.font().family()
                or "Roboto"
            ),
        }
        self._pending_theme = theme
        if self._grid_ready:
            self._run_js(f"window.kargoApplyTheme({_json_dumps(theme)});")

    def sync_cell(self, row, column):
        if not self._grid_ready:
            return
        if not (0 <= int(row) < self._model.rowCount() and 0 <= int(column) < self._model.columnCount()):
            return
        item = self._model.item(int(row), int(column))
        hidden = self._model.row_template_values(int(row))
        formulas = hidden.get("__formula_cells__", {})
        formula = str(formulas.get(self._column_key(int(column))) or "") if isinstance(formulas, dict) else ""
        value = item.text() if item is not None else ""
        self._run_js(
            "window.kargoSetModelCell(%s,%s,%s,%s);" % (
                int(row), _json_dumps(self._column_key(int(column))),
                _json_dumps(value), _json_dumps(formula),
            )
        )

    def setColumnWidth(self, column, width):
        self._model.setColumnWidth(column, width)
        if self._grid_ready and 0 <= int(column) < self._model.columnCount():
            self._run_js(f"window.kargoSetColumnWidth({int(column)},{int(width)});")

    def setCurrentCell(self, row, column, *args):
        self._model.setCurrentCell(row, column, *args)

    def scrollToItem(self, item, *args):
        if item is not None and self._grid_ready:
            self._run_js(f"window.kargoSetModelSelection({int(item.row())},{_json_dumps(self._column_key(item.column()))});")
        elif item is not None:
            self._model.scrollToItem(item, *args)

    def commitData(self, editor):
        # Univer commits cell input through its own editor and SheetValueChanged.
        return None

    def updateGeometries(self):
        self.update()

    def font(self):
        return self._view.font() if self._view is not None else self._model.font()

    def setFont(self, font):
        super().setFont(font)
        self._model.setFont(font)
        dark = (
            bool(self._pending_theme.get("dark"))
            if self._pending_theme is not None
            else str(getattr(self.window(), "current_theme", "light")).lower() == "dark"
        )
        self.apply_theme(dark, font.pointSizeF() or 9.5)


__all__ = ["InvoiceSheetContainer"]
