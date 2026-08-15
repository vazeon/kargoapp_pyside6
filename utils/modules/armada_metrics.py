# utils/modules/armada_metrics.py
"""Baseline geometry/layout khusus modul Armada.

Dipakai bersama oleh TabArmada, SubTabTruk, dan SubTabKapal.
Semua nilai piksel adalah logical-pixel baseline desain.
Table-only zoom tetap ditangani ``utils.zoom``.
"""

# ---------------------------------------------------------------------------
# Wrapper Tab Armada
# ---------------------------------------------------------------------------
ARMADA_TAB_MARGINS = (5, 5, 5, 5)

# ---------------------------------------------------------------------------
# Layout subtab
# ---------------------------------------------------------------------------
ARMADA_PAGE_MARGINS = (10, 10, 10, 10)
ARMADA_MASTER_PANEL_MARGINS = (0, 0, 10, 0)
ARMADA_EDITOR_PANEL_MARGINS = (15, 15, 15, 15)
ARMADA_SPLITTER_INITIAL_SIZES = (650, 350)

# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
ARMADA_MASTER_PANEL_MIN_WIDTH = 600
ARMADA_MASTER_PANEL_MAX_WIDTH = 1800
ARMADA_EDITOR_PANEL_MIN_WIDTH = 320
ARMADA_EDITOR_PANEL_MAX_WIDTH = 950

# ---------------------------------------------------------------------------
# Header / tabel
# ---------------------------------------------------------------------------
ARMADA_SEARCH_WIDTH = 230
ARMADA_TABLE_HEADER_MIN_HEIGHT = 35
ARMADA_TABLE_ROW_BASE_HEIGHT = 32

ARMADA_COLUMN_WIDTH_MIN = 20
ARMADA_COLUMN_WIDTH_MAX = 1500
ARMADA_COLUMN_FALLBACK_WIDTH = 110

ARMADA_TRUK_COLUMN_WIDTHS = (45, 80, 110, 140, 120, 250, 20)
ARMADA_KAPAL_COLUMN_WIDTHS = (45, 180, 150, 280, 20)

# ---------------------------------------------------------------------------
# Editor + foto
# ---------------------------------------------------------------------------
ARMADA_EDITOR_SECTION_GAP = 10
ARMADA_PHOTO_PREVIEW_HEIGHT = 180
ARMADA_ACTION_BUTTON_INITIAL_HEIGHT = 40
ARMADA_ACTION_BUTTON_MIN_HEIGHT = 38
ARMADA_PHOTO_BUTTON_MIN_HEIGHT = 30