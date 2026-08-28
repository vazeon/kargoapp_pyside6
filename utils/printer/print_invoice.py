# utils/printer/print_invoice.py
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QWidget

from .common import (
    JENIS_INVOICE,
    JendelaPreviewCustom,
    bersihkan_nama_file,
    buat_dokumen_html,
    konfigurasi_printer,
    pastikan_ekstensi,
    sinkronkan_ukuran_dokumen,
)


# Invoice operasional harian menggunakan NCR / dot matrix.
# A4 tetap tersedia secara eksplisit untuk rekap, PDF, inkjet, atau laser.
DEFAULT_TIPE_KERTAS_INVOICE = "NCR"

_PAGE_DECLARATION = {
    "A4": "@page { size: A4 portrait; margin: 8mm; }",
    "NCR": "@page { size: 9.5in 5.5in; margin: 4mm; }",
}
_PAGE_PATTERN = re.compile(r"@page\s*\{[^{}]*\}", flags=re.IGNORECASE)

# Override tipografi/layout per media. HTML utama tetap satu sumber,
# sedangkan karakter fisik kertas ditangani di layer printer ini.
_PAPER_STYLE = {
    "NCR": r"""
        html, body, .page { width: 100%; margin: 0; padding: 0; }
        body { font-size: 7.4pt; line-height: 1.08; }

        .company, .party, .items, .bottom, .totals {
            width: 100%;
            border-collapse: collapse;
        }
        .company td { padding: 2px 4px; }
        .brand, .brand * { font-size: 11pt !important; line-height: 1 !important; }
        .company-name { font-size: 7.2pt; }
        .address { font-size: 6.5pt; line-height: 1.08; }

        .invoice-title, .invoice-title-cell { padding: 1px 3px; }
        .invoice-title .title, .invoice-title-cell .title { font-size: 9pt; line-height: 1; }
        .invoice-title .number, .invoice-title-cell .number { font-size: 7pt; margin-top: 0; }

        .party th, .party td { padding: 2px 3px; }
        .party th { font-size: 7pt; }
        .party td { font-size: 7.2pt; }
        .party.single th { width: 9%; }
        .party.single td { font-size: 7.5pt; }

        .items th {
            padding: 1px 2px;
            font-size: 6.7pt;
            line-height: 1.02;
        }
        .items td {
            padding: 1px 2px;
            font-size: 7pt;
            line-height: 1.05;
        }
        .items .empty { padding: 6px; }

        .payment {
            width: 65%;
            padding: 2px 3px;
            font-size: 7pt;
            line-height: 1.1;
        }
        .total-container { width: 35%; padding: 0; }
        .totals td { padding: 2px 3px; font-size: 7.2pt; }
        .totals .grand { font-size: 9pt; line-height: 1; }

        .notes { margin-top: 2px; padding: 2px; font-size: 6.5pt; line-height: 1.05; }
        .signature, .signature-cell { margin-top: 4px; padding-right: 5px; font-size: 7pt; line-height: 1.05; }
        .signature .space, .signature-space { height: 24px; }
        .signature .name, .signature-name { font-size: 7.2pt; }
    """,
    "A4": r"""
        html, body, .page { width: 100%; margin: 0; padding: 0; }
        body { font-size: 8.5pt; line-height: 1.15; }

        .company, .party, .items, .bottom, .totals {
            width: 100%;
            border-collapse: collapse;
        }
        .company td { padding: 4px 6px; }
        .brand, .brand * { font-size: 14pt !important; line-height: 1 !important; }
        .company-name { font-size: 8.5pt; }
        .address { font-size: 7.5pt; line-height: 1.2; }

        .invoice-title, .invoice-title-cell { padding: 2px 4px; }
        .invoice-title .title, .invoice-title-cell .title { font-size: 10.5pt; line-height: 1.1; }
        .invoice-title .number, .invoice-title-cell .number { font-size: 8pt; }

        .party th, .party td { padding: 3px 5px; }
        .party th { font-size: 8pt; }
        .party td { font-size: 8.5pt; }
        .party.single td { font-size: 9pt; }

        .items th { padding: 2px 3px; font-size: 7.5pt; line-height: 1.1; }
        .items td { padding: 2px 3px; font-size: 8pt; line-height: 1.15; }

        .payment { width: 65%; padding: 4px; font-size: 8pt; line-height: 1.25; }
        .total-container { width: 35%; padding: 0; }
        .totals td { padding: 3px 5px; font-size: 8.5pt; }
        .totals .grand { font-size: 10.5pt; line-height: 1.1; }

        .notes { margin-top: 4px; padding: 3px; font-size: 7.5pt; line-height: 1.2; }
        .signature, .signature-cell { margin-top: 7px; padding-right: 8px; font-size: 8pt; line-height: 1.2; }
        .signature .space, .signature-space { height: 38px; }
        .signature .name, .signature-name { font-size: 8.5pt; }
    """,
}


def _normalisasi_tipe_kertas(tipe_kertas: str) -> str:
    tipe = str(tipe_kertas or DEFAULT_TIPE_KERTAS_INVOICE).strip().upper()
    return "A4" if tipe == "A4" else "NCR"


def _konfigurasi_printer_invoice(
    printer: QPrinter,
    tipe_kertas: str,
) -> str:
    """Konfigurasi printer khusus Invoice tanpa memengaruhi Resi/Manifest.

    Untuk NCR 9.5 x 5.5 inci, QPageSize disimpan sebagai 5.5 x 9.5 inci
    lalu orientasi printer diatur Landscape. Ini mengikuti cara kerja Qt dan
    memastikan QPrintPreviewWidget mengenali media sebagai landscape.
    """
    tipe = _normalisasi_tipe_kertas(tipe_kertas)

    if tipe == "NCR":
        ncr_size = QPageSize(
            QSizeF(5.5, 9.5),
            QPageSize.Unit.Inch,
            "NCR 9.5 x 5.5 in",
        )
        printer.setPageSize(ncr_size)
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        printer.setPageMargins(
            QMarginsF(4, 4, 4, 4),
            QPageLayout.Unit.Millimeter,
        )
    else:
        konfigurasi_printer(printer, JENIS_INVOICE, "A4")

    return tipe


def _paksa_struktur_qt_full_width(html_content: str) -> str:
    """Menambahkan atribut HTML klasik yang stabil pada QTextDocument Qt."""
    html_text = str(html_content or "")

    # QTextDocument lebih konsisten membaca atribut width tabel dibanding
    # hanya mengandalkan CSS web modern.
    pola_tabel = re.compile(
        r'<table\s+class="(company|party(?:\s+single)?|items|bottom|totals|invoice-title-table|signature-table)"\s*>',
        flags=re.IGNORECASE,
    )
    html_text = pola_tabel.sub(
        lambda m: (
            f'<table class="{m.group(1)}" width="100%" '
            'cellspacing="0" cellpadding="0">'
        ),
        html_text,
    )

    html_text = re.sub(
        r'<td\s+class="payment"\s*>',
        '<td class="payment" width="65%">',
        html_text,
        flags=re.IGNORECASE,
    )
    html_text = re.sub(
        r'<td\s+class="total-container"\s*>',
        '<td class="total-container" width="35%">',
        html_text,
        flags=re.IGNORECASE,
    )
    html_text = re.sub(
        r'<td\s+class="address"\s*>',
        '<td class="address" width="45%">',
        html_text,
        count=1,
        flags=re.IGNORECASE,
    )

    # Kolom pertama header perusahaan dibuat eksplisit 55%.
    html_text = re.sub(
        r'(<table\s+class="company"[^>]*>\s*<tr>\s*)<td\s*>',
        r'\1<td width="55%">',
        html_text,
        count=1,
        flags=re.IGNORECASE,
    )
    return html_text


def _sesuaikan_html_kertas(html_content: str, tipe_kertas: str) -> str:
    """Menyiapkan HTML Invoice sesuai media NCR/A4 tanpa mengubah datanya."""
    tipe = _normalisasi_tipe_kertas(tipe_kertas)
    html_text = _paksa_struktur_qt_full_width(html_content)
    deklarasi = _PAGE_DECLARATION[tipe]

    if _PAGE_PATTERN.search(html_text):
        html_text = _PAGE_PATTERN.sub(deklarasi, html_text, count=1)
    else:
        marker = "<style>"
        if marker in html_text:
            html_text = html_text.replace(marker, f"{marker}\n    {deklarasi}", 1)

    # Style media disisipkan paling akhir agar menjadi override resmi.
    style_media = _PAPER_STYLE[tipe]
    if "</style>" in html_text:
        html_text = html_text.replace(
            "</style>",
            f"\n/* Invoice media: {tipe} */\n{style_media}\n</style>",
            1,
        )

    return html_text


def _nama_invoice_aman(suggested_name: str) -> str:
    nama = str(suggested_name or "invoice_draft").strip()
    nama = re.sub(r"\.pdf$", "", nama, flags=re.IGNORECASE)
    return bersihkan_nama_file(nama, default="invoice_draft")


def _buat_printer_invoice_pdf(output_path: str, tipe_kertas: str) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(output_path)
    _konfigurasi_printer_invoice(printer, tipe_kertas)
    return printer


def _buat_dokumen_invoice(
    html_content: str,
    tipe_kertas: str,
    printer: QPrinter,
):
    tipe = _konfigurasi_printer_invoice(printer, tipe_kertas)
    html_siap = _sesuaikan_html_kertas(html_content, tipe)
    return buat_dokumen_html(html_siap, printer, margin=0)


def simpan_html_ke_pdf(
    html_content: str,
    output_path: str,
    tipe_kertas: str = DEFAULT_TIPE_KERTAS_INVOICE,
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
    tipe_kertas: str = DEFAULT_TIPE_KERTAS_INVOICE,
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


def cetak_invoice_langsung(
    html_content: str,
    parent: Optional[QWidget] = None,
    tipe_kertas: str = DEFAULT_TIPE_KERTAS_INVOICE,
) -> bool:
    """Mencetak Invoice ke printer fisik memakai engine yang sama dengan preview."""
    tipe = _normalisasi_tipe_kertas(tipe_kertas)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    _konfigurasi_printer_invoice(printer, tipe)

    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(
        "Pilih Printer - Invoice NCR"
        if tipe == "NCR"
        else "Pilih Printer - Invoice A4"
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False

    try:
        # Ukuran media tetap ditegakkan setelah dialog printer ditutup.
        _konfigurasi_printer_invoice(printer, tipe)
        document = _buat_dokumen_invoice(html_content, tipe, printer)
        document.print_(printer)
        QMessageBox.information(
            parent,
            "Sukses",
            f"Invoice sedang dikirim ke printer:\n{printer.printerName()}",
        )
        return True
    except Exception as exc:
        QMessageBox.critical(parent, "Gagal Mencetak", str(exc))
        return False


class InvoicePreviewDialog(JendelaPreviewCustom):
    """Preview Invoice berbasis ukuran fisik media yang sebenarnya."""

    def __init__(
        self,
        html_content: str,
        suggested_name: str,
        parent: Optional[QWidget] = None,
        tipe_kertas: str = DEFAULT_TIPE_KERTAS_INVOICE,
    ):
        self.html_content = str(html_content or "")
        self.suggested_name = _nama_invoice_aman(suggested_name)
        self.tipe_invoice = _normalisasi_tipe_kertas(tipe_kertas)

        printer = QPrinter()
        printer.setResolution(96)
        _konfigurasi_printer_invoice(printer, self.tipe_invoice)
        document = _buat_dokumen_invoice(
            self.html_content,
            self.tipe_invoice,
            printer,
        )
        super().__init__(
            printer=printer,
            doc=document,
            parent=parent,
            jenis_dokumen=JENIS_INVOICE,
            tipe_kertas=self.tipe_invoice,
            nomor_dokumen=self.suggested_name,
        )
        self.setWindowTitle(f"Preview Invoice - {self.suggested_name}")

    def _sinkronkan_printer(self, printer: QPrinter) -> None:
        """Override sync bersama agar geometri NCR Invoice tidak dirotasi ulang."""
        _konfigurasi_printer_invoice(printer, self.tipe_invoice)
        sinkronkan_ukuran_dokumen(self.doc_terikat, printer)

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
    tipe_kertas: str = DEFAULT_TIPE_KERTAS_INVOICE,
) -> None:
    """Menampilkan preview Invoice secara modal."""
    dialog = InvoicePreviewDialog(
        html_content=html_content,
        suggested_name=suggested_name,
        parent=parent,
        tipe_kertas=tipe_kertas,
    )
    dialog.exec()