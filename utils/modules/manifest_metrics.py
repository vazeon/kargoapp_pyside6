# utils/modules/manifest_metrics.py
"""Baseline geometry/layout khusus modul Manifest.

Semua nilai piksel adalah logical-pixel baseline desain.
Responsive geometry umum tetap ditangani ``utils.ui_scaler``.
Geometry internal tabel yang mengikuti user zoom tetap diterapkan melalui
``utils.zoom`` dari baseline yang didefinisikan di sini.
"""

# ---------------------------------------------------------------------------
# Panel utama
# ---------------------------------------------------------------------------
MANIFEST_LEFT_PANEL_MIN_WIDTH = 700
MANIFEST_LEFT_PANEL_MAX_WIDTH = 1800
MANIFEST_LEFT_PANEL_MARGINS = (8, 8, 8, 8)
MANIFEST_SPACING = 8
MANIFEST_SPLITTER_INITIAL_SIZES = (800, 200)

# ---------------------------------------------------------------------------
# Header Manifest
# ---------------------------------------------------------------------------
MANIFEST_HEADER_HEIGHT = 36
MANIFEST_HEADER_FIELD_SIZE = (160, 32)
MANIFEST_HEADER_FIELD_SPACING = 8

# ---------------------------------------------------------------------------
# Card detail
# ---------------------------------------------------------------------------
MANIFEST_CARD_HEIGHT = 134
MANIFEST_CARD_GRID_MARGINS = (10, 8, 8, 8)
MANIFEST_CARD_HORIZONTAL_SPACING = 8
MANIFEST_INPUT_LABEL_MIN_WIDTH = 70

MANIFEST_ROUTE_FIELD_MIN_WIDTH = 230
MANIFEST_TRUCK_TYPE_MIN_WIDTH = 150
MANIFEST_TRUCK_DETAIL_MIN_WIDTH = 130
MANIFEST_TRUCK_ROW_STRETCH = (4, 4, 4)

# ---------------------------------------------------------------------------
# Tombol aksi
# ---------------------------------------------------------------------------
MANIFEST_ACTION_CONTAINER_SIZE = (210, 102)
MANIFEST_ACTION_BUTTON_MIN_WIDTH = 192
MANIFEST_ACTION_BUTTON_MIN_HEIGHT = 36

# ---------------------------------------------------------------------------
# Area detail Manifest
# ---------------------------------------------------------------------------
MANIFEST_DETAIL_CONTAINER_HEIGHT = 140
MANIFEST_DETAIL_STRETCH = (5, 6)

# ---------------------------------------------------------------------------
# Tabel Manifest
# ---------------------------------------------------------------------------
MANIFEST_CHECK_COLUMN_WIDTH = 22
MANIFEST_DEFAULT_COLUMN_WIDTHS = (
    22,   # CHECK
    45,   # NO.
    125,  # RESI
    105,  # TGL MASUK
    150,  # PENGIRIM
    150,  # PENERIMA
    125,  # TUJUAN
    180,  # NAMA BARANG
    70,   # KOLI
    85,   # BERAT
    85,   # CBM
    110,  # ONGKIR
    180,  # KETERANGAN
)
MANIFEST_COLUMN_WIDTH_MIN = 20
MANIFEST_COLUMN_WIDTH_MAX = 1500
MANIFEST_FALLBACK_COLUMN_WIDTH = 110

# Row tabel mengikuti USER TABLE ZOOM, bukan responsive geometry global.
MANIFEST_TABLE_ROW_BASE_HEIGHT = 32
MANIFEST_TABLE_ROW_MIN_HEIGHT = 20

# ---------------------------------------------------------------------------
# Histori
# ---------------------------------------------------------------------------
MANIFEST_HISTORY_MIN_WIDTH = 260
MANIFEST_HISTORY_MAX_WIDTH = 520
MANIFEST_HISTORY_YEAR_WIDTH = 80