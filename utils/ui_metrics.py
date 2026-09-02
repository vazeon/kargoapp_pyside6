# utils/ui_metrics.py
"""Perhitungan responsive UI berdasarkan ruang layar yang tersedia.

Modul ini hanya menyediakan angka/metrik. Ia tidak mengubah QWidget, layout,
stylesheet, atau tabel secara langsung. Penerapan ke object Qt dilakukan oleh
``utils.ui_scaler`` dan helper khusus seperti ``utils.widget_helpers``.

Prinsip:
- baseline desain: 1600x900 logical pixel;
- layar kecil dibuat lebih compact secara bertahap;
- layar besar hanya diperbesar sedikit agar UI tidak berlebihan;
- object QScreen tidak pernah disimpan sebagai state jangka panjang.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtGui import QGuiApplication


BASELINE_WIDTH = 1600
BASELINE_HEIGHT = 900
MIN_UI_SCALE = 0.84
MAX_UI_SCALE = 1.06

# ---------------------------------------------------------------------------
# Baseline geometry UI umum
# ---------------------------------------------------------------------------
# Semua nilai adalah logical-pixel baseline, BUKAN ukuran final.
# Scaling responsive dilakukan satu kali oleh ResponsiveUIScaler.
TAB_MIN_WIDTH = 88
TAB_PADDING_V = 10
TAB_PADDING_H = 16

# Tinggi baseline kontrol pada corner-widget kanan MainTabs.
# Nilai final tetap mengikuti ResponsiveUIScaler.
# Tinggi kontrol kanan dibuat sedikit lebih lega agar QComboBox tidak ter-clip
# setelah responsive scaling pada layar yang scale-nya < 1.0.
TOP_RIGHT_CONTROL_HEIGHT = 28

# Tinggi minimum bar tab utama. Memberi ruang vertikal yang cukup untuk
# corner-widget kanan tanpa memperbesar semua subtab.
MAIN_TAB_BAR_MIN_HEIGHT = 36

_APP_SCALE_PROPERTY = "_responsive_ui_scale"


@dataclass(frozen=True)
class UIMetrics:
    """Snapshot metrik responsive dalam nilai Python biasa."""

    available_width: int
    available_height: int
    scale: float
    input_padding_v: int
    input_padding_h: int
    combo_padding_right: int
    combo_padding_left: int


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(float(minimum), min(float(value), float(maximum)))


def hitung_ui_scale(width: int | float, height: int | float) -> float:
    """Hitung faktor density dari ukuran logical-pixel area kerja."""
    try:
        width = max(1.0, float(width))
        height = max(1.0, float(height))
    except (TypeError, ValueError, OverflowError):
        width = float(BASELINE_WIDTH)
        height = float(BASELINE_HEIGHT)

    scale_w = width / BASELINE_WIDTH
    scale_h = height / BASELINE_HEIGHT
    return _clamp(min(scale_w, scale_h), MIN_UI_SCALE, MAX_UI_SCALE)


def tetapkan_ui_scale_aktif(scale: float) -> float:
    """Simpan scale aktif sebagai nilai float pada QApplication.

    Yang disimpan hanya angka, bukan QScreen. Ini membuat helper yang dipanggil
    saat pembuatan widget dinamis memakai scale yang sama dengan MainWindow.
    """
    scale = _clamp(scale, MIN_UI_SCALE, MAX_UI_SCALE)
    app = QGuiApplication.instance()
    if app is not None:
        try:
            app.setProperty(_APP_SCALE_PROPERTY, float(scale))
        except RuntimeError:
            pass
    return scale


def _scale_tersimpan_aplikasi() -> Optional[float]:
    app = QGuiApplication.instance()
    if app is None:
        return None
    try:
        raw = app.property(_APP_SCALE_PROPERTY)
    except RuntimeError:
        return None
    if raw is None:
        return None
    try:
        return _clamp(float(raw), MIN_UI_SCALE, MAX_UI_SCALE)
    except (TypeError, ValueError, OverflowError):
        return None


def _baca_geometry_screen(screen) -> Optional[Tuple[int, int]]:
    """Baca availableGeometry segera dan jangan kembalikan wrapper QScreen."""
    if screen is None:
        return None
    try:
        geometry = screen.availableGeometry()
        return max(1, int(geometry.width())), max(1, int(geometry.height()))
    except RuntimeError:
        return None


def _dapatkan_ukuran_layar_aktif() -> Tuple[int, int]:
    app = QGuiApplication.instance()
    if app is None:
        return BASELINE_WIDTH, BASELINE_HEIGHT

    try:
        window = app.focusWindow()
    except RuntimeError:
        window = None

    if window is not None:
        try:
            ukuran = _baca_geometry_screen(window.screen())
        except RuntimeError:
            ukuran = None
        if ukuran is not None:
            return ukuran

    try:
        ukuran = _baca_geometry_screen(app.primaryScreen())
    except RuntimeError:
        ukuran = None

    return ukuran or (BASELINE_WIDTH, BASELINE_HEIGHT)


def dapatkan_ui_scale() -> float:
    """Ambil scale aktif tanpa mempertahankan object QScreen."""
    scale = _scale_tersimpan_aplikasi()
    if scale is not None:
        return scale
    width, height = _dapatkan_ukuran_layar_aktif()
    return hitung_ui_scale(width, height)


def dapatkan_ui_metrics(
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> UIMetrics:
    """Bangun snapshot metrics.

    ``width`` dan ``height`` dapat diberikan oleh ``ui_scaler`` agar scale
    dihitung dari screen milik window tertentu. Bila tidak diberikan, helper
    memakai screen aktif/fallback QApplication.
    """
    if width is None or height is None:
        width, height = _dapatkan_ukuran_layar_aktif()

    width = max(1, int(width))
    height = max(1, int(height))
    scale = hitung_ui_scale(width, height)

    return UIMetrics(
        available_width=width,
        available_height=height,
        scale=scale,
        input_padding_v=skalakan_px(4, scale=scale, minimum=3, maximum=5),
        input_padding_h=skalakan_px(10, scale=scale, minimum=8, maximum=11),
        combo_padding_right=skalakan_px(28, scale=scale, minimum=24, maximum=30),
        combo_padding_left=skalakan_px(12, scale=scale, minimum=10, maximum=16),
    )


def skalakan_px(
    value: int | float,
    *,
    scale: Optional[float] = None,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """Skalakan logical pixel desain dari baseline 1600x900."""
    if scale is None:
        scale = dapatkan_ui_scale()
    else:
        scale = _clamp(scale, MIN_UI_SCALE, MAX_UI_SCALE)

    try:
        angka = float(value)
    except (TypeError, ValueError, OverflowError):
        angka = 0.0

    if angka == 0:
        result = 0
    else:
        result = round(angka * scale)
        if angka > 0:
            result = max(1, result)
        else:
            result = min(-1, result)

    if minimum is not None:
        result = max(int(minimum), result)
    if maximum is not None:
        result = min(int(maximum), result)
    return int(result)