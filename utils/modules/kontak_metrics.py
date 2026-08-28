# utils/modules/kontak_metrics.py
"""Baseline geometry/layout khusus modul Kontak.

Dipakai bersama oleh TabKontak, SubTabPengirim, dan SubTabPenerima.
Semua nilai piksel adalah logical-pixel baseline desain.
Responsive scaling tetap ditangani layer global UI.
"""

# ---------------------------------------------------------------------------
# Wrapper Tab Kontak
# ---------------------------------------------------------------------------
KONTAK_TAB_MARGINS = (0, 8, 0, 0)
# Ukuran QTabBar tidak disimpan per modul.
# Sumber tunggal: TAB_* di utils.ui_metrics, diterapkan oleh themes.base.

# ---------------------------------------------------------------------------
# Layout subtab
# ---------------------------------------------------------------------------
KONTAK_SUBTAB_MARGINS = (0, 0, 0, 0)
KONTAK_SPACING = 8
KONTAK_SPLITTER_INITIAL_SIZES = (650, 450)

# ---------------------------------------------------------------------------
# Panel master + histori
# ---------------------------------------------------------------------------
KONTAK_PANEL_MIN_WIDTH = 400
KONTAK_PANEL_MAX_WIDTH = 1400
KONTAK_PANEL_MARGINS = (8, 8, 8, 8)

# ---------------------------------------------------------------------------
# Header / pencarian
# ---------------------------------------------------------------------------
KONTAK_SEARCH_WIDTH = 230
KONTAK_HISTORY_SEARCH_WIDTH = 180
KONTAK_ADD_BUTTON_HEIGHT = 30

# ---------------------------------------------------------------------------
# Dialog tambah data
# ---------------------------------------------------------------------------
KONTAK_ADD_DIALOG_MIN_WIDTH = 660
KONTAK_ADD_DIALOG_MARGINS = (24, 22, 24, 22)
KONTAK_ADD_DIALOG_SPACING = 18
KONTAK_ADD_FORM_HORIZONTAL_SPACING = 20
KONTAK_ADD_FORM_VERTICAL_SPACING = 14
KONTAK_ADD_FIELD_MIN_WIDTH = 400

# ---------------------------------------------------------------------------
# Baseline lebar kolom tabel
# ---------------------------------------------------------------------------
KONTAK_PENGIRIM_COLUMN_WIDTHS = (50, 90, 180, 130, 260, 120)
KONTAK_PENERIMA_COLUMN_WIDTHS = (50, 90, 190, 130, 260, 130, 140, 130, 130, 130)
KONTAK_HISTORY_COLUMN_WIDTHS = (95, 100, 140, 50, 60, 60, 90)