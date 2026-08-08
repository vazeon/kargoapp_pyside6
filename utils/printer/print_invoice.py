# utils/printer/print_invoice.py
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from .common import (
    JENIS_INVOICE,
    JendelaPreviewCustom,
    bersihkan_nama_file,
    buat_dokumen_html,
    konfigurasi_printer,
    pastikan_ekstensi,
)


_PAGE_DECLARATION = {
    "A4": "@page { size: A4 portrait; margin: 8mm; }",
    "NCR": "@page { size: 9.5in 5.5in; margin: 4mm; }",
}
_PAGE_PATTERN = re.compile(r"@page\s*\{[^{}]*\}", flags=re.IGNORECASE)


def _normalisasi_tipe_kertas(tipe_kertas: str) -> str:
    tipe = str(tipe_kertas or "NCR").strip().upper()
    return "A4" if tipe == "A4" else "NCR"


def _sesuaikan_html_kertas(html_content: str, tipe_kertas: str) -> str:
    """Menyesuaikan deklarasi @page tanpa mengubah isi Invoice."""
    html_text = str(html_content or "")
    deklarasi = _PAGE_DECLARATION[_normalisasi_tipe_kertas(tipe_kertas)]
    if _PAGE_PATTERN.search(html_text):
        return _PAGE_PATTERN.sub(deklarasi, html_text, count=1)

    marker = "<style>"
    if marker in html_text:
        return html_text.replace(marker, f"{marker}\n    {deklarasi}", 1)
    return html_text


def _nama_invoice_aman(suggested_name: str) -> str:
    nama = str(suggested_name or "invoice_draft").strip()
    nama = re.sub(r"\.pdf$", "", nama, flags=re.IGNORECASE)
    return bersihkan_nama_file(nama, default="invoice_draft")


def _buat_printer_invoice_pdf(output_path: str, tipe_kertas: str) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(output_path)
    konfigurasi_printer(printer, JENIS_INVOICE, tipe_kertas)
    return printer


def _buat_dokumen_invoice(html_content: str, tipe_kertas: str, printer: QPrinter):
    html_siap = _sesuaikan_html_kertas(html_content, tipe_kertas)
    return buat_dokumen_html(html_siap, printer, margin=0)


def simpan_html_ke_pdf(
    html_content: str,
    output_path: str,
    tipe_kertas: str = "NCR",
) -> str:
    """Menyimpan HTML Invoice langsung ke file PDF."""
    output_path = pastikan_ekstensi(output_path, ".pdf")
    if not output_path:
        raise ValueError("Lokasi penyimpanan PDF tidak valid.")

    tipe = _normalisasi_tipe_kertas(tipe_kertas)
    printer = _buat_printer_invoice_pdf(output_path, tipe)
    document = _buat_dokumen_invoice(html_content, tipe, printer)
    document.print_(printer)
    return output_path


def simpan_invoice_pdf(
    html_content: str,
    suggested_name: str,
    parent: Optional[QWidget] = None,
    tipe_kertas: str = "NCR",
) -> Optional[str]:
    """Memilih lokasi penyimpanan lalu mengekspor Invoice ke PDF."""
    nama_file = pastikan_ekstensi(_nama_invoice_aman(suggested_name), ".pdf")
    output_path, _ = QFileDialog.getSaveFileName(
        parent,
        "Simpan Invoice PDF",
        nama_file,
        "PDF Files (*.pdf)",
    )
    if not output_path:
        return None

    try:
        hasil_path = simpan_html_ke_pdf(
            html_content,
            output_path,
            tipe_kertas=tipe_kertas,
        )
        QMessageBox.information(
            parent,
            "PDF Berhasil",
            "Invoice berhasil disimpan:\n" f"{hasil_path}",
        )
        return hasil_path
    except Exception as exc:
        QMessageBox.critical(parent, "Gagal Membuat PDF", str(exc))
        return None


class InvoicePreviewDialog(JendelaPreviewCustom):
    """Preview Invoice berbasis ukuran printer yang sebenarnya."""

    def __init__(
        self,
        html_content: str,
        suggested_name: str,
        parent: Optional[QWidget] = None,
        tipe_kertas: str = "NCR",
    ):
        self.html_content = str(html_content or "")
        self.suggested_name = _nama_invoice_aman(suggested_name)
        self.tipe_invoice = _normalisasi_tipe_kertas(tipe_kertas)

        printer = QPrinter()
        printer.setResolution(96)
        konfigurasi_printer(printer, JENIS_INVOICE, self.tipe_invoice)
        document = _buat_dokumen_invoice(self.html_content, self.tipe_invoice, printer)
        super().__init__(
            printer=printer,
            doc=document,
            parent=parent,
            jenis_dokumen=JENIS_INVOICE,
            tipe_kertas=self.tipe_invoice,
            nomor_dokumen=self.suggested_name,
        )
        self.setWindowTitle(f"Preview Invoice - {self.suggested_name}")

    def aksi_simpan_pdf(self) -> None:
        """Dipakai oleh menu PDF pada preview bersama."""
        simpan_invoice_pdf(
            html_content=self.html_content,
            suggested_name=self.suggested_name,
            parent=self,
            tipe_kertas=self.tipe_invoice,
        )

    def simpan_pdf(self) -> None:
        """Nama metode lama yang tetap dipertahankan."""
        self.aksi_simpan_pdf()


def tampilkan_preview_invoice(
    html_content: str,
    suggested_name: str,
    parent: Optional[QWidget] = None,
    tipe_kertas: str = "NCR",
) -> None:
    """Menampilkan preview Invoice secara modal."""
    dialog = InvoicePreviewDialog(
        html_content=html_content,
        suggested_name=suggested_name,
        parent=parent,
        tipe_kertas=tipe_kertas,
    )
    dialog.exec()