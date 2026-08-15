# utils/modules/resi_metrics.py
"""Baseline geometry/layout khusus modul Resi.

Semua ukuran piksel di file ini adalah logical-pixel baseline desain.
Jangan melakukan scaling responsive di sini. ``utils.ui_scaler`` dan helper
global akan menerapkan faktor responsive dari baseline yang sama.
"""

# ---------------------------------------------------------------------------
# Density umum
# ---------------------------------------------------------------------------
RESI_PAGE_MARGINS = (8, 8, 8, 8)
RESI_SPACING = 8

# ---------------------------------------------------------------------------
# Tinggi input / tabel
# ---------------------------------------------------------------------------
RESI_INPUT_HEIGHT = 32
RESI_TABLE_ROW_HEIGHT = 32
RESI_TOTAL_ONGKIR_HEIGHT = 40

# ---------------------------------------------------------------------------
# Area utama + splitter
# ---------------------------------------------------------------------------
RESI_SCROLL_LEFT_MIN_WIDTH = 700
RESI_SCROLL_LEFT_MAX_WIDTH = 1800
RESI_SPLITTER_INITIAL_SIZES = (856, 256)

# ---------------------------------------------------------------------------
# Top bar
# ---------------------------------------------------------------------------
RESI_DATE_INPUT_WIDTH = 160
RESI_NUMBER_DISPLAY_WIDTH = 200

# ---------------------------------------------------------------------------
# Container utama
# ---------------------------------------------------------------------------
# Urutan tuple: kiri, atas, kanan, bawah.
# Nilai ini menggantikan padding QGroupBox agar inset child dikontrol layout.
RESI_FORM_CONTAINER_MARGINS = (10, 8, 8, 8)
RESI_TABLE_CONTAINER_MARGINS = (8, 8, 8, 8)

# ---------------------------------------------------------------------------
# Pengirim / penerima
# ---------------------------------------------------------------------------
RESI_IDENTITY_COLUMN_STRETCH = (6, 4)
RESI_DESTINATION_STRETCH = (9, 9, 1)

# ---------------------------------------------------------------------------
# Detail barang
# ---------------------------------------------------------------------------
RESI_DETAIL_CONTAINER_MIN_HEIGHT = 320
RESI_ITEMS_TABLE_MIN_HEIGHT = 150
RESI_ITEMS_COLUMN_MIN_WIDTH = 20

# Urutan indeks mengikuti kolom tabel:
# NO., NAMA BARANG, KOLI, BERAT (Kg), KUBIK (m³)
RESI_ITEMS_COLUMN_WIDTHS = {
    0: 42,
    1: 400,
    2: 100,
    3: 100,
    4: 100,
}

# ---------------------------------------------------------------------------
# Pembayaran / rekening
# ---------------------------------------------------------------------------
# Urutan: finance, rekening
RESI_PAYMENT_AREA_STRETCH = (45, 55)

# Urutan: field combo, ruang/reset
RESI_FINANCE_COLUMN_STRETCH = (5, 1)

RESI_ACCOUNT_PANEL_MARGINS = (4, 10, 4, 4)
RESI_ACCOUNT_CONTENT_MARGINS = (8, 8, 8, 8)

# ---------------------------------------------------------------------------
# Action bar
# ---------------------------------------------------------------------------
RESI_ACTION_RIGHT_LEFT_MARGIN = 12
RESI_ACTION_TOP_GAP = 15

# ---------------------------------------------------------------------------
# Histori
# ---------------------------------------------------------------------------
RESI_HISTORY_MARGINS = (8, 8, 8, 8)
RESI_HISTORY_MIN_WIDTH = 256
RESI_HISTORY_MAX_WIDTH = 520
RESI_HISTORY_DATE_WIDTH = 112
RESI_HISTORY_RESET_WIDTH = 56

# ---------------------------------------------------------------------------
# Tombol reset kecil
# ---------------------------------------------------------------------------
RESI_CLEAR_BUTTON_SIZE = 20

# ---------------------------------------------------------------------------
# Kartu rekening
# ---------------------------------------------------------------------------
RESI_ACCOUNT_CARD_MARGINS = (10, 8, 10, 8)
RESI_ACCOUNT_CARD_SPACING = 2

# ---------------------------------------------------------------------------
# Autocomplete
# ---------------------------------------------------------------------------
RESI_AUTOCOMPLETE_MAX_VISIBLE_ITEMS = 12

# ---------------------------------------------------------------------------
# Dialog audit
# ---------------------------------------------------------------------------
RESI_AUDIT_DIALOG_SIZE = (760, 560)
RESI_AUDIT_HISTORY_SPACING = 10