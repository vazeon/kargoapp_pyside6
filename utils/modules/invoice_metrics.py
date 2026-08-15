# utils/modules/invoice_metrics.py
"""Baseline geometry/layout khusus modul Invoice.

Semua nilai piksel adalah logical-pixel baseline desain.
Responsive geometry umum tetap ditangani ``utils.ui_scaler``.
Geometry tabel yang mengikuti user zoom tetap diterapkan melalui ``utils.zoom``.
Konfigurasi isi/template Invoice tidak dipindahkan ke sini.
"""

# ---------------------------------------------------------------------------
# Spreadsheet editor
# ---------------------------------------------------------------------------
INVOICE_SHEET_INITIAL_ROW_HEIGHT = 28
INVOICE_SHEET_INITIAL_MIN_ROW_HEIGHT = 24

# ---------------------------------------------------------------------------
# Dialog pengaturan kolom
# ---------------------------------------------------------------------------
INVOICE_COLUMN_DESIGNER_SIZE = (760, 480)

INVOICE_COLUMN_SIZE_LABEL_WIDTHS = {
    "Kecil": 70,
    "Sedang": 110,
    "Lebar": 200,
    "Sangat Lebar": 360,
}

INVOICE_DEFAULT_COLUMN_WIDTH = 110
INVOICE_COLUMN_WIDTH_MIN = 20
INVOICE_COLUMN_WIDTH_MAX = 1500

# ---------------------------------------------------------------------------
# Layout utama
# ---------------------------------------------------------------------------
INVOICE_PAGE_MARGINS = (8, 8, 8, 8)
INVOICE_SPLITTER_INITIAL_SIZES = (340, 1000)

# ---------------------------------------------------------------------------
# Panel histori
# ---------------------------------------------------------------------------
INVOICE_HISTORY_PANEL_MIN_WIDTH = 260
INVOICE_HISTORY_PANEL_MAX_WIDTH = 520
INVOICE_HISTORY_PANEL_MARGINS = (0, 0, 8, 0)

# ---------------------------------------------------------------------------
# Panel editor
# ---------------------------------------------------------------------------
INVOICE_EDITOR_PANEL_MIN_WIDTH = 700
INVOICE_EDITOR_PANEL_MAX_WIDTH = 1800
INVOICE_EDITOR_PANEL_MARGINS = (8, 0, 0, 0)

# ---------------------------------------------------------------------------
# Table-only zoom
# ---------------------------------------------------------------------------
INVOICE_HISTORY_ZOOM_ROW_BASE_HEIGHT = 28
INVOICE_EDITOR_ZOOM_ROW_BASE_HEIGHT = 32

INVOICE_ZOOM_ITEM_EXTRA_BASE = 8
INVOICE_ZOOM_ITEM_EXTRA_MIN = 4

INVOICE_ZOOM_ROW_FLOOR_BASE = 24
INVOICE_ZOOM_ROW_FLOOR_MIN = 18

INVOICE_ZOOM_HEADER_EXTRA_BASE = 8
INVOICE_ZOOM_HEADER_EXTRA_MIN = 4