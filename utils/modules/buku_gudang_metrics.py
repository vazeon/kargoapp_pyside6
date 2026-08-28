# utils/modules/buku_gudang_metrics.py
"""Baseline geometry/layout khusus modul Buku Gudang.

Semua nilai piksel adalah logical-pixel baseline desain.
Responsive scaling tetap ditangani layer global ``utils.ui_scaler``.
Geometry internal tabel yang terkait user zoom tetap diterapkan melalui ``utils.zoom``.
"""

# ---------------------------------------------------------------------------
# Dialog pilih penagih
# ---------------------------------------------------------------------------
BUKU_GUDANG_DIALOG_PENAGIH_MIN_WIDTH = 350
BUKU_GUDANG_DIALOG_ACTION_GAP = 10

# ---------------------------------------------------------------------------
# Header utama
# ---------------------------------------------------------------------------
BUKU_GUDANG_HEADER_MARGINS = (8, 0, 8, 0)
BUKU_GUDANG_HEADER_SPACING = 6
BUKU_GUDANG_PRIMARY_ROW_SPACING = 8

BUKU_GUDANG_SEARCH_WIDTH = 340
BUKU_GUDANG_HEADER_CONTROL_HEIGHT = 32

# ---------------------------------------------------------------------------
# Filter operasional
# ---------------------------------------------------------------------------
BUKU_GUDANG_FILTER_ROW_SPACING = 6
BUKU_GUDANG_YEAR_BUTTON_SIZE = (90, 30)
BUKU_GUDANG_MONTH_BUTTON_SIZE = (115, 30)
BUKU_GUDANG_FILTER_SECTION_GAP = 10
BUKU_GUDANG_BILLING_STATUS_BUTTON_SIZE = (140, 30)
BUKU_GUDANG_RESET_FILTER_BUTTON_SIZE = (82, 30)
BUKU_GUDANG_MONTH_CHECKBOX_MIN_WIDTH = 170

# ---------------------------------------------------------------------------
# Layout utama + tab wilayah
# ---------------------------------------------------------------------------
BUKU_GUDANG_MAIN_MARGINS = (0, 6, 0, 0)
BUKU_GUDANG_MAIN_SPACING = 6
BUKU_GUDANG_TABLE_TAB_MARGINS = (6, 6, 6, 6)

# Ukuran QTabBar tidak disimpan per modul.
# Sumber tunggal: TAB_* di utils.ui_metrics, diterapkan oleh themes.base.

# ---------------------------------------------------------------------------
# Tabel
# ---------------------------------------------------------------------------
BUKU_GUDANG_DEFAULT_COLUMN_WIDTHS = (
    45,   # NO.
    115,  # RESI
    95,   # MASUK
    95,   # KELUAR
    115,  # STATUS RESI
    230,  # STATUS PENAGIHAN
    165,  # TRUK
    180,  # PENGIRIM
    130,  # KOTA ASAL
    180,  # PENERIMA
    135,  # KOTA TUJUAN
    180,  # NAMA BARANG
    70,   # KOLI
    90,   # BERAT
    90,   # CBM
    125,  # ONGKIR
    120,  # PAYMENT
    220,  # KETERANGAN
)

BUKU_GUDANG_COLUMN_WIDTH_MIN = 20
BUKU_GUDANG_COLUMN_WIDTH_MAX = 1500
BUKU_GUDANG_FALLBACK_COLUMN_WIDTH = 110

# Row/header tabel mengikuti USER TABLE ZOOM, bukan responsive geometry global.
BUKU_GUDANG_TABLE_ROW_BASE_HEIGHT = 28
BUKU_GUDANG_TABLE_ROW_MIN_HEIGHT = 20

# ---------------------------------------------------------------------------
# Autocomplete
# ---------------------------------------------------------------------------
BUKU_GUDANG_AUTOCOMPLETE_MAX_VISIBLE_ITEMS = 12