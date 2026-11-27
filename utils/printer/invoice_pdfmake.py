# utils/printer/invoice_pdfmake.py
"""Qt helpers for previewing, saving, and printing PDF bytes rendered by pdfmake."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from .invoice_page_setup import (
    InvoicePageSetupPanel,
    normalisasi_page_setup,
    simpan_page_setup,
)

from PySide6.QtCore import QEventLoop, QMarginsF, QRectF, QSize, QSizeF, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
except ImportError:  # Keep PDF export usable if the optional Qt PDF modules are absent.
    QPdfDocument = None
    QPdfView = None


def _nama_pdf_aman(value: str) -> str:
    nama = Path(str(value or "invoice")).name
    nama = "".join(char for char in nama if char not in '<>:"/\\|?*')
    nama = nama.strip().rstrip(".")
    return nama or "invoice"


def simpan_pdfmake_bytes(
    pdf_bytes: bytes,
    suggested_name: str,
    parent: Optional[QWidget] = None,
) -> Optional[str]:
    """Save an already-rendered pdfmake document with a Qt save dialog."""
    if not isinstance(pdf_bytes, (bytes, bytearray)) or not bytes(pdf_bytes).startswith(b"%PDF-"):
        QMessageBox.warning(parent, "Export PDF", "Data PDF tidak valid atau kosong.")
        return None

    filename = _nama_pdf_aman(suggested_name)
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    output_path, _ = QFileDialog.getSaveFileName(
        parent,
        "Simpan Invoice PDF",
        filename,
        "PDF Files (*.pdf)",
    )
    if not output_path:
        return None
    if not output_path.lower().endswith(".pdf"):
        output_path += ".pdf"

    try:
        Path(output_path).write_bytes(bytes(pdf_bytes))
    except OSError as exc:
        QMessageBox.critical(parent, "Gagal Menyimpan PDF", str(exc))
        return None
    return output_path


def _konfigurasi_printer_dari_setup(printer: QPrinter, page_setup: dict | None) -> None:
    setup = page_setup if isinstance(page_setup, dict) else {}
    paper = str(setup.get("paper_size", "NCR")).upper()
    orientation = str(setup.get("orientation", "landscape")).lower()
    if paper == "A3":
        page_size = QPageSize(QPageSize.PageSizeId.A3)
    elif paper == "A4":
        page_size = QPageSize(QPageSize.PageSizeId.A4)
    else:
        if paper == "NCR":
            width_mm, height_mm = 139.7, 241.3
            name = "NCR 9.5 x 5.5 in"
        else:
            width_mm = float(setup.get("width_mm", 210.0) or 210.0)
            height_mm = float(setup.get("height_mm", 297.0) or 297.0)
            name = "Custom Invoice"
        if orientation == "landscape" and width_mm < height_mm:
            width_mm, height_mm = height_mm, width_mm
        elif orientation != "landscape" and width_mm > height_mm:
            width_mm, height_mm = height_mm, width_mm
        page_size = QPageSize(
            QSizeF(width_mm, height_mm),
            QPageSize.Unit.Millimeter,
            name,
        )
    printer.setPageSize(page_size)
    printer.setPageOrientation(
        QPageLayout.Orientation.Landscape
        if orientation == "landscape"
        else QPageLayout.Orientation.Portrait
    )
    # Page margins are already part of the generated PDF. Printing the PDF page
    # as a whole avoids applying those margins a second time.
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    printer.setFullPage(True)


def _status_pdf(document: QPdfDocument) -> str:
    status = document.status()
    return str(getattr(status, "name", status)).split(".")[-1]


def _tunggu_pdf_siap(document: QPdfDocument, timeout_ms: int = 15000) -> None:
    """QPdfDocument.load() can be asynchronous; wait until pages are usable."""
    status = _status_pdf(document)
    if status == "Ready":
        return
    if status == "Error":
        raise RuntimeError(f"PDF gagal dibuka oleh Qt PDF: {document.error()}")

    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)

    def _on_status_changed(*_args):
        if _status_pdf(document) in {"Ready", "Error"}:
            loop.quit()

    document.statusChanged.connect(_on_status_changed)
    timeout.start(max(1000, int(timeout_ms)))
    # Re-check after the event loop starts to cover a Ready transition that
    # happens between the initial status check and signal connection.
    QTimer.singleShot(0, _on_status_changed)
    loop.exec()
    try:
        document.statusChanged.disconnect(_on_status_changed)
    except (RuntimeError, TypeError):
        pass
    timeout.stop()

    status = _status_pdf(document)
    if status != "Ready":
        if status == "Error":
            detail = str(document.error())
        else:
            detail = "waktu tunggu pemuatan PDF habis"
        raise RuntimeError(f"PDF belum siap dirender: {detail}")


def cetak_pdfmake_bytes(
    pdf_bytes: bytes,
    parent: Optional[QWidget] = None,
    page_setup: dict | None = None,
) -> bool:
    """Print pdfmake output through Qt by rasterizing each PDF page at 300 DPI."""
    if QPdfDocument is None:
        QMessageBox.warning(
            parent,
            "Modul PDF Qt Tidak Tersedia",
            "Cetak langsung PDF memerlukan PySide6.QtPdf dan PySide6.QtPdfWidgets.",
        )
        return False
    if not isinstance(pdf_bytes, (bytes, bytearray)) or not bytes(pdf_bytes).startswith(b"%PDF-"):
        QMessageBox.warning(parent, "Cetak Invoice", "Data PDF tidak valid atau kosong.")
        return False

    temp_path = None
    document = QPdfDocument()
    try:
        with tempfile.NamedTemporaryFile(prefix="kargo_invoice_", suffix=".pdf", delete=False) as handle:
            handle.write(bytes(pdf_bytes))
            temp_path = handle.name
        document.load(temp_path)
        _tunggu_pdf_siap(document)
        if document.pageCount() < 1:
            QMessageBox.warning(parent, "Cetak Invoice", "PDF tidak memiliki halaman yang dapat dicetak.")
            return False

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(300)
        _konfigurasi_printer_dari_setup(printer, page_setup)
        dialog = QPrintDialog(printer, parent)
        dialog.setWindowTitle("Cetak Invoice - PDF Univer")
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return False

        # Page Setup Kargo tetap menjadi sumber ukuran/orientasi dokumen;
        # dialog Windows hanya memilih printer dan opsi salinannya.
        _konfigurasi_printer_dari_setup(printer, page_setup)

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.critical(parent, "Gagal Mencetak", "Tidak dapat memulai proses pencetakan.")
            return False
        try:
            target = printer.pageRect(QPrinter.Unit.DevicePixel)
            for page_index in range(document.pageCount()):
                page_points = document.pagePointSize(page_index)
                page_width = max(1.0, float(page_points.width()))
                page_height = max(1.0, float(page_points.height()))
                fit_scale = min(
                    float(target.width()) / page_width,
                    float(target.height()) / page_height,
                )
                render_width = max(1, int(round(page_width * fit_scale)))
                render_height = max(1, int(round(page_height * fit_scale)))
                image = document.render(page_index, QSize(render_width, render_height))
                if image.isNull():
                    raise RuntimeError(f"Halaman PDF {page_index + 1} gagal dirender.")
                draw_rect = QRectF(
                    target.left() + (target.width() - render_width) / 2,
                    target.top() + (target.height() - render_height) / 2,
                    render_width,
                    render_height,
                )
                painter.drawImage(draw_rect, image)
                if page_index + 1 < document.pageCount() and not printer.newPage():
                    raise RuntimeError("Printer gagal menyiapkan halaman berikutnya.")
        finally:
            painter.end()
        return True
    except Exception as exc:
        QMessageBox.critical(parent, "Gagal Mencetak", str(exc))
        return False
    finally:
        document.close()
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


class InvoicePdfPreviewDialog(QDialog):
    """Print Preview Invoice dengan panel Page Setup di sisi kiri."""

    def __init__(
        self,
        pdf_bytes: bytes,
        suggested_name: str,
        page_setup: dict | None = None,
        parent: Optional[QWidget] = None,
        regenerate_callback=None,
        actions_enabled: bool = True,
        actions_disabled_reason: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Print Preview - {_nama_pdf_aman(suggested_name)}")
        self.resize(1280, 820)
        self.setMinimumSize(960, 620)
        self._pdf_bytes = bytes(pdf_bytes or b"")
        self._suggested_name = _nama_pdf_aman(suggested_name)
        self._page_setup = normalisasi_page_setup(page_setup)
        self._regenerate_callback = regenerate_callback
        self._actions_enabled = bool(actions_enabled)
        self._actions_disabled_reason = str(actions_disabled_reason or "")
        self._temp_path = None
        self._document = None
        self._busy = False
        # Keep the old preview document alive while QtPdf loads a replacement.
        # QPdfDocument.load() is asynchronous (Loading -> Ready/Error).
        self._pending_pdf_load = None
        self._requested_page_setup = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        content = QHBoxLayout()
        content.setSpacing(10)

        self.setup_panel = InvoicePageSetupPanel(self._page_setup, self)
        self.setup_panel.setFixedWidth(310)
        self.setup_panel.applyRequested.connect(self._apply_page_setup)

        setup_scroll = QScrollArea(self)
        setup_scroll.setWidgetResizable(True)
        setup_scroll.setFrameShape(QScrollArea.Shape.StyledPanel)
        setup_scroll.setFixedWidth(326)
        setup_scroll.setWidget(self.setup_panel)
        content.addWidget(setup_scroll, 0)

        preview_column = QVBoxLayout()
        preview_column.setSpacing(6)
        self.lbl_preview_meta = QLabel("Memuat dokumen PDF...")
        self.lbl_preview_meta.setStyleSheet("font-weight: 600; color: #475569; padding: 3px 2px;")
        preview_column.addWidget(self.lbl_preview_meta)

        if QPdfDocument is not None and QPdfView is not None:
            self.viewer = QPdfView(self)
            self.viewer.setPageMode(QPdfView.PageMode.MultiPage)
            self.viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            preview_column.addWidget(self.viewer, 1)
        else:
            self.viewer = None
            fallback = QLabel(
                "PDF berhasil dibuat, tetapi komponen Qt PDF Viewer tidak tersedia.\n"
                "Gunakan tombol Simpan PDF untuk membuka hasilnya dengan aplikasi PDF."
            )
            fallback.setWordWrap(True)
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet("background: palette(base); border: 1px solid palette(mid);")
            preview_column.addWidget(fallback, 1)

        content.addLayout(preview_column, 1)
        root.addLayout(content, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_print = QPushButton("Cetak...")
        self.btn_save = QPushButton("Simpan PDF...")
        self.btn_share = QPushButton("Share WA...")
        self.btn_close = QPushButton("Tutup")
        self.btn_save.clicked.connect(self._save_pdf)
        self.btn_print.clicked.connect(self._print_pdf)
        self.btn_share.clicked.connect(self._share_pdf)
        self.btn_close.clicked.connect(self.accept)
        buttons.addWidget(self.btn_print)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_share)
        buttons.addWidget(self.btn_close)
        root.addLayout(buttons)

        self.setup_panel.set_status("Ubah pengaturan di kiri, lalu klik Terapkan ke Preview.")
        self._set_action_buttons_enabled(bool(self._pdf_bytes))
        if self.viewer is not None and self._pdf_bytes.startswith(b"%PDF-"):
            try:
                self._load_pdf_bytes(self._pdf_bytes)
            except Exception as exc:
                self.lbl_preview_meta.setText("PDF tidak dapat ditampilkan")
                self.setup_panel.set_status(f"Gagal memuat PDF: {exc}")

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        active = bool(enabled) and self._actions_enabled and not self._busy
        for button in (self.btn_print, self.btn_save, self.btn_share):
            button.setEnabled(active)
            if not self._actions_enabled and self._actions_disabled_reason:
                button.setToolTip(self._actions_disabled_reason)
            elif active:
                button.setToolTip("")

    @staticmethod
    def _pdf_status(document) -> str:
        try:
            status = document.status()
            return str(getattr(status, "name", status)).split(".")[-1]
        except Exception:
            return "Unknown"

    def _cancel_pending_pdf_load(self) -> None:
        """Cancel a not-yet-ready replacement PDF and release its temporary file."""
        pending = self._pending_pdf_load
        if not pending:
            return
        self._pending_pdf_load = None

        timer = pending.get("timer")
        if timer is not None:
            timer.stop()
            timer.deleteLater()

        document = pending.get("document")
        handler = pending.get("handler")
        if document is not None and handler is not None:
            try:
                document.statusChanged.disconnect(handler)
            except (RuntimeError, TypeError):
                pass
        if document is not None:
            try:
                document.close()
                document.deleteLater()
            except RuntimeError:
                pass

        path = pending.get("path")
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    def _finish_pdf_load(self, pending: dict, success: bool, error: str = "") -> None:
        """Commit the new QPdfDocument only after Qt reports Status.Ready."""
        if self._pending_pdf_load is not pending:
            return
        self._pending_pdf_load = None

        timer = pending.get("timer")
        if timer is not None:
            timer.stop()
            timer.deleteLater()

        new_document = pending.get("document")
        handler = pending.get("handler")
        if new_document is not None and handler is not None:
            try:
                new_document.statusChanged.disconnect(handler)
            except (RuntimeError, TypeError):
                pass

        on_loaded = pending.get("on_loaded")
        if not success:
            if new_document is not None:
                try:
                    new_document.close()
                    new_document.deleteLater()
                except RuntimeError:
                    pass
            path = pending.get("path")
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
            detail = str(error or "Qt PDF Viewer gagal memuat PDF baru.")
            if callable(on_loaded):
                on_loaded(False, detail)
            else:
                self.lbl_preview_meta.setText("PDF tidak dapat ditampilkan")
                self.setup_panel.set_status(f"Gagal memuat PDF: {detail}")
            return

        # Keep the current document visible until the replacement has fully
        # loaded. Then detach/attach explicitly to force QPdfView to rebuild its
        # page geometry for the new physical paper size/orientation.
        old_document = self._document
        old_path = self._temp_path

        self._document = new_document
        self._temp_path = pending.get("path")
        self._pdf_bytes = pending.get("pdf_bytes", b"")

        if new_document is not None:
            new_document.statusChanged.connect(self._update_preview_meta)
            if self.viewer is not None:
                self.viewer.setDocument(None)
                self.viewer.setDocument(new_document)
                self.viewer.setPageMode(QPdfView.PageMode.MultiPage)
                self.viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)
                self.viewer.updateGeometry()
                self.viewer.update()
                QTimer.singleShot(0, self.viewer.update)
                QTimer.singleShot(80, self.viewer.update)

        if old_document is not None:
            try:
                old_document.close()
                old_document.deleteLater()
            except RuntimeError:
                pass
        if old_path:
            try:
                os.remove(old_path)
            except OSError:
                pass

        # Let the regeneration callback update the displayed paper metadata
        # before refreshing the status line for the newly loaded PDF.
        if callable(on_loaded):
            try:
                on_loaded(True, "")
            except Exception as exc:
                print(f"[INVOICE-PREVIEW] PDF loaded callback failed: {exc}")
        self._update_preview_meta()

    def _load_pdf_bytes(self, pdf_bytes: bytes, on_loaded=None) -> None:
        """Load PDF asynchronously and swap the visible document only when Ready."""
        if not isinstance(pdf_bytes, (bytes, bytearray)) or not bytes(pdf_bytes).startswith(b"%PDF-"):
            raise ValueError("Data PDF tidak valid atau kosong.")

        # Export and print remain usable when the optional Qt PDF viewer is not
        # installed; complete the callback so the panel never stays busy.
        if QPdfDocument is None or self.viewer is None:
            self._pdf_bytes = bytes(pdf_bytes)
            if callable(on_loaded):
                on_loaded(True, "")
            return

        # A new PDF supersedes an unfinished initial document load.
        self._cancel_pending_pdf_load()

        with tempfile.NamedTemporaryFile(
            prefix="kargo_invoice_preview_", suffix=".pdf", delete=False
        ) as handle:
            handle.write(bytes(pdf_bytes))
            new_path = handle.name

        new_document = QPdfDocument(self)
        pending = {
            "document": new_document,
            "path": new_path,
            "pdf_bytes": bytes(pdf_bytes),
            "on_loaded": on_loaded if callable(on_loaded) else None,
            "timer": QTimer(self),
            "handler": None,
        }

        def _status_changed(*_args):
            if self._pending_pdf_load is not pending:
                return
            status = self._pdf_status(new_document)
            if status == "Ready":
                self._finish_pdf_load(pending, True, "")
            elif status == "Error":
                try:
                    detail = str(new_document.error())
                except Exception:
                    detail = "Format PDF tidak dapat dibaca Qt."
                self._finish_pdf_load(pending, False, detail)

        pending["handler"] = _status_changed
        pending["timer"].setSingleShot(True)
        pending["timer"].timeout.connect(
            lambda: self._finish_pdf_load(
                pending,
                False,
                "Waktu tunggu Qt PDF Viewer habis saat memuat PDF baru.",
            )
        )
        new_document.statusChanged.connect(_status_changed)
        self._pending_pdf_load = pending

        try:
            new_document.load(new_path)
        except Exception as exc:
            self._finish_pdf_load(pending, False, str(exc))
            return

        # Small local PDFs can reach Ready synchronously; larger files signal it
        # asynchronously. Check now, then leave the Qt event loop unblocked.
        _status_changed()
        if self._pending_pdf_load is pending:
            self.lbl_preview_meta.setText("Memperbarui preview PDF...")
            self.setup_panel.set_status("PDF sedang dimuat ke Preview...")
            pending["timer"].start(20000)

    def _update_preview_meta(self, *_args) -> None:
        setup = self._page_setup
        paper = setup.get("paper_size", "NCR")
        orientation = str(setup.get("orientation", "landscape")).capitalize()
        if self._document is None:
            self.lbl_preview_meta.setText(f"{paper} · {orientation} · PDF Viewer tidak tersedia")
            return
        status = self._pdf_status(self._document)
        if status == "Ready":
            count = int(self._document.pageCount())
            self.lbl_preview_meta.setText(
                f"{paper} · {orientation} · {count} halaman"
            )
            status_text = f"Preview siap: {count} halaman · {paper} {orientation}."
            if not self._actions_enabled and self._actions_disabled_reason:
                status_text += " " + self._actions_disabled_reason
            self.setup_panel.set_status(status_text)
        elif status == "Error":
            self.lbl_preview_meta.setText("PDF gagal dimuat")
            self.setup_panel.set_status("Qt PDF Viewer gagal membaca PDF yang dihasilkan.")
        else:
            self.lbl_preview_meta.setText(f"{paper} · {orientation} · Memuat PDF...")

    def _apply_page_setup(self, requested_setup: dict) -> None:
        if self._busy:
            return
        setup = normalisasi_page_setup(requested_setup)
        if not callable(self._regenerate_callback):
            self._page_setup = setup
            self.setup_panel.set_status(
                "Pengaturan tersimpan untuk cetak, tetapi renderer preview tidak dapat dibuat ulang dari jendela ini."
            )
            simpan_page_setup(setup)
            return

        self._busy = True
        self._requested_page_setup = setup
        self.setup_panel.set_busy(True)
        self.setup_panel.set_status("Sedang membuat ulang PDF sesuai pengaturan halaman...")
        self._set_action_buttons_enabled(False)
        try:
            started = self._regenerate_callback(
                setup,
                self._on_regenerated_pdf,
                self._on_regeneration_progress,
            )
            if started is False:
                self._finish_regeneration_error(
                    "Renderer PDF tidak dapat memulai proses pembuatan ulang."
                )
        except Exception as exc:
            self._finish_regeneration_error(str(exc))

    def _on_regeneration_progress(self, message: str) -> None:
        """Show renderer stage updates in the Page Setup panel and preview header."""
        text = str(message or "").strip()
        if not text:
            return
        self.setup_panel.set_status(text)
        self.lbl_preview_meta.setText(text)

    def _finish_regeneration_error(self, message: str) -> None:
        self._requested_page_setup = None
        self._busy = False
        self.setup_panel.set_busy(False)
        self.setup_panel.set_status(f"Gagal memperbarui preview: {message}")
        self._set_action_buttons_enabled(bool(self._pdf_bytes))

    def _on_regenerated_pdf(self, pdf_bytes, error_message="") -> None:
        if error_message:
            self._finish_regeneration_error(str(error_message))
            return
        if not pdf_bytes:
            self._finish_regeneration_error("Renderer tidak menghasilkan PDF.")
            return

        requested_setup = normalisasi_page_setup(
            self._requested_page_setup or self.setup_panel.page_setup()
        )
        self.setup_panel.set_status("PDF selesai dibuat; memperbarui tampilan halaman...")

        def _after_pdf_loaded(success: bool, detail: str = "") -> None:
            if not success:
                self._finish_regeneration_error(
                    detail or "PDF baru gagal dimuat oleh Qt PDF Viewer."
                )
                return
            self._page_setup = requested_setup
            self._requested_page_setup = None
            simpan_page_setup(self._page_setup)
            self._busy = False
            self.setup_panel.set_busy(False)
            self.setup_panel.set_status("Pengaturan diterapkan. Preview PDF sudah diperbarui.")
            self._update_preview_meta()
            self._set_action_buttons_enabled(True)

        try:
            self._load_pdf_bytes(bytes(pdf_bytes), on_loaded=_after_pdf_loaded)
        except Exception as exc:
            self._finish_regeneration_error(str(exc))

    def _save_pdf(self) -> None:
        if not self._actions_enabled or self._busy:
            return
        simpan_pdfmake_bytes(self._pdf_bytes, self._suggested_name, self)

    def _print_pdf(self) -> None:
        if not self._actions_enabled or self._busy:
            return
        cetak_pdfmake_bytes(self._pdf_bytes, self, self._page_setup)

    def _share_pdf(self) -> None:
        """Save the current PDF, then open WhatsApp Web for a user-controlled attachment.

        Browser security does not allow Kargo to attach a local file to a WhatsApp
        chat automatically. The user chooses the recipient and attaches the file.
        """
        if not self._actions_enabled or self._busy:
            return
        output_path = simpan_pdfmake_bytes(self._pdf_bytes, self._suggested_name, self)
        if not output_path:
            return

        opened = QDesktopServices.openUrl(QUrl("https://web.whatsapp.com/"))
        if opened:
            message = (
                "PDF Invoice sudah disimpan dan WhatsApp Web sudah dibuka.\n\n"
                "Pilih chat tujuan, klik ikon lampiran (paperclip), pilih Dokumen, "
                "lalu pilih file berikut:\n" + output_path
            )
        else:
            message = (
                "PDF Invoice sudah disimpan. Buka https://web.whatsapp.com/ secara manual, "
                "lalu lampirkan file berikut sebagai Dokumen:\n" + output_path
            )
        QMessageBox.information(self, "Share Invoice", message)

    def closeEvent(self, event):
        self._cancel_pending_pdf_load()
        if self._document is not None:
            self._document.close()
            self._document.deleteLater()
            self._document = None
        if self._temp_path:
            try:
                os.remove(self._temp_path)
            except OSError:
                pass
            self._temp_path = None
        super().closeEvent(event)