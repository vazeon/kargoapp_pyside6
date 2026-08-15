# utils/modules/resi_metrics.py
"""Baseline geometry/layout khusus modul Setting.

Semua ukuran piksel adalah logical-pixel baseline desain.
Responsive geometry tetap ditangani layer global ``utils.ui_scaler`` dan
``utils.widget_helpers``.

Font/theme, business logic, DB limit, jumlah row data, dan konfigurasi JSON
tidak dikelola dari file metrics ini.
"""

# ---------------------------------------------------------------------------
# Root + sidebar + content
# ---------------------------------------------------------------------------
SETTING_ROOT_MARGINS = (0, 0, 0, 0)
SETTING_ROOT_SPACING = 0

SETTING_SIDEBAR_WIDTH = 240
SETTING_SIDEBAR_MARGINS = (16, 24, 16, 24)
SETTING_SIDEBAR_SPACING = 8

SETTING_CONTENT_MARGINS = (32, 24, 40, 24)
SETTING_CONTENT_SPACING = 20

SETTING_SAVE_BUTTON_HEIGHT = 48

# ---------------------------------------------------------------------------
# Form umum
# ---------------------------------------------------------------------------
SETTING_FORM_MARGINS = (16, 22, 16, 16)
SETTING_FORM_VERTICAL_SPACING = 16
SETTING_FORM_HORIZONTAL_SPACING = 16

# ---------------------------------------------------------------------------
# Format & Resi
# ---------------------------------------------------------------------------
SETTING_SUFFIX_MAX_WIDTH = 160
SETTING_PREFIX_INVOICE_MAX_WIDTH = 180
SETTING_RESI_MODE_MAX_WIDTH = 180
SETTING_DESTINATION_LIST_HEIGHT = 70

# ---------------------------------------------------------------------------
# Rekening bank
# ---------------------------------------------------------------------------
SETTING_ACCOUNT_GROUP_MARGINS = (16, 22, 16, 16)
SETTING_ACCOUNT_GROUP_SPACING = 8
SETTING_ACCOUNT_INPUT_SPACING = 4

SETTING_BANK_FIELD_WIDTH = 100
SETTING_ACCOUNT_NUMBER_WIDTH = 160
SETTING_ACCOUNT_ACTION_WIDTH = 40
SETTING_ACCOUNT_TABLE_MIN_HEIGHT = 120

# ---------------------------------------------------------------------------
# Kantor cabang
# ---------------------------------------------------------------------------
SETTING_BRANCH_GROUP_MARGINS = (16, 22, 16, 16)
SETTING_BRANCH_GROUP_SPACING = 8

SETTING_BRANCH_TABLE_HEIGHT = 280
SETTING_BRANCH_CODE_WIDTH = 64
SETTING_BRANCH_PREFIX_WIDTH = 96
SETTING_BRANCH_JSON_WIDTH = 185