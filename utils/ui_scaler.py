# utils/ui_scaler.py
"""Penerapan responsive geometry ke tree QWidget secara aman.

Layer ini menangani geometry umum (constraint widget, layout, spacer, icon,
stylesheet geometry) berdasarkan faktor dari ``utils.ui_metrics``.

Yang sengaja tidak ditangani di sini:
- font: tetap point/DPI based melalui ``utils.typography``;
- row/header/column internal tabel: ditangani ``utils.zoom``;
- logika bisnis widget.

Semua scaling selalu dihitung dari baseline yang disimpan pertama kali sehingga
pemanggilan berulang tidak menumpuk (non-cumulative scaling).
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QObject, QPointF, QSize, QTimer
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHeaderView,
    QLayout,
    QSplitter,
    QTabBar,
    QToolBar,
    QWidget,
)

from utils.ui_metrics import (
    BASELINE_HEIGHT,
    BASELINE_WIDTH,
    dapatkan_ui_metrics,
    hitung_ui_scale,
    skalakan_px,
    tetapkan_ui_scale_aktif,
)


QT_GEOMETRY_MAX = 16_777_215

_BASE_MIN_W = "_ui_base_min_width"
_BASE_MIN_H = "_ui_base_min_height"
_BASE_MAX_W = "_ui_base_max_width"
_BASE_MAX_H = "_ui_base_max_height"
_BASE_ICON_W = "_ui_base_icon_width"
_BASE_ICON_H = "_ui_base_icon_height"
_BASE_SPLITTER_HANDLE = "_ui_base_splitter_handle"
_BASE_QSS = "_ui_base_stylesheet"
_LAST_SCALED_QSS = "_ui_last_scaled_stylesheet"
_EXPLICIT_GEOMETRY = "_ui_scaler_explicit_geometry"
_SCREEN_CONNECTED = "_ui_scaler_screen_connected"
_MIN_RENDER_W = "_ui_scaler_min_width"
_MIN_RENDER_H = "_ui_scaler_min_height"

_GEOMETRY_QSS_PROPERTIES = {
    "padding",
    "padding-left",
    "padding-right",
    "padding-top",
    "padding-bottom",
    "margin",
    "margin-left",
    "margin-right",
    "margin-top",
    "margin-bottom",
    "min-width",
    "max-width",
    "min-height",
    "max-height",
    "width",
    "height",
    "border-radius",
    "border-top-left-radius",
    "border-top-right-radius",
    "border-bottom-left-radius",
    "border-bottom-right-radius",
    "qproperty-iconsize",
    "outline-offset",
}

_DECLARATION_RE = re.compile(
    r"(?P<property>[A-Za-z][A-Za-z0-9_-]*)\s*:\s*(?P<value>[^;{}]+)(?P<semi>;)",
    flags=re.MULTILINE,
)
_PX_VALUE_RE = re.compile(r"(?P<number>-?\d+(?:\.\d+)?)px\b", flags=re.IGNORECASE)


def _scaled_px_token(match: re.Match[str], scale: float) -> str:
    try:
        raw = float(match.group("number"))
    except (TypeError, ValueError):
        return match.group(0)
    if raw == 0:
        return "0px"
    scaled = round(raw * scale)
    if raw > 0:
        scaled = max(1, scaled)
    else:
        scaled = min(-1, scaled)
    return f"{scaled}px"


def skalakan_qss_geometri(qss: str, scale: float) -> str:
    """Skalakan hanya properti geometry QSS; font-size dan border tetap utuh."""
    if not isinstance(qss, str) or not qss.strip():
        return qss

    def replace_declaration(match: re.Match[str]) -> str:
        prop = match.group("property")
        value = match.group("value")
        if prop.lower() not in _GEOMETRY_QSS_PROPERTIES:
            return match.group(0)
        scaled_value = _PX_VALUE_RE.sub(
            lambda token: _scaled_px_token(token, scale),
            value,
        )
        return f"{prop}: {scaled_value}{match.group('semi')}"

    return _DECLARATION_RE.sub(replace_declaration, qss)


def _property_int(obj: QObject, name: str, current: int) -> int:
    try:
        existing = obj.property(name)
    except RuntimeError:
        return int(current)
    if existing is None:
        try:
            obj.setProperty(name, int(current))
        except RuntimeError:
            return int(current)
        return int(current)
    try:
        return int(existing)
    except (TypeError, ValueError, OverflowError):
        return int(current)


def _property_text(obj: QObject, name: str) -> Optional[str]:
    try:
        value = obj.property(name)
    except RuntimeError:
        return None
    return None if value is None else str(value)


def _optional_positive_int_property(obj: QObject, name: str) -> Optional[int]:
    """Baca floor geometry opsional tanpa membuat baseline/property baru."""
    try:
        value = obj.property(name)
    except RuntimeError:
        return None
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _set_property(obj: QObject, name: str, value) -> None:
    try:
        obj.setProperty(name, value)
    except RuntimeError:
        pass


def _ancestor_item_view(widget: QWidget) -> bool:
    """True untuk child internal tabel/list, bukan item-view root itu sendiri."""
    try:
        parent = widget.parentWidget()
    except RuntimeError:
        return False
    while parent is not None:
        if isinstance(parent, QAbstractItemView):
            return True
        try:
            parent = parent.parentWidget()
        except RuntimeError:
            return False
    return False


class ResponsiveUIScaler(QObject):
    """Manager responsive untuk satu top-level/root QWidget."""

    def __init__(
        self,
        root: QWidget,
        *,
        on_scale_changed: Optional[Callable[[float], None]] = None,
    ) -> None:
        super().__init__(root)
        self._root = root
        self._on_scale_changed = on_scale_changed
        self._scale: Optional[float] = None
        self._apply_pending = False
        self._applying = False
        self._spacer_bases = {}
        self._install_filters()

    @property
    def scale(self) -> float:
        return float(self._scale if self._scale is not None else 1.0)

    def _root_available_size(self) -> tuple[int, int]:
        root = self._root
        if root is None:
            return BASELINE_WIDTH, BASELINE_HEIGHT

        try:
            handle = root.windowHandle()
        except RuntimeError:
            handle = None

        if handle is not None:
            try:
                screen = handle.screen()
                if screen is not None:
                    geometry = screen.availableGeometry()
                    return max(1, int(geometry.width())), max(1, int(geometry.height()))
            except RuntimeError:
                pass

        metrics = dapatkan_ui_metrics()
        return metrics.available_width, metrics.available_height

    def _ensure_screen_connection(self) -> None:
        root = self._root
        if root is None:
            return
        try:
            handle = root.windowHandle()
        except RuntimeError:
            return
        if handle is None:
            return
        try:
            if bool(handle.property(_SCREEN_CONNECTED)):
                return
            handle.screenChanged.connect(self._on_screen_changed)
            handle.setProperty(_SCREEN_CONNECTED, True)
        except RuntimeError:
            return

    def _on_screen_changed(self, *_args) -> None:
        # Jangan simpan atau gunakan QScreen dari argumen signal.
        self.schedule_apply()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if self._applying:
            return False

        event_type = event.type()
        if event_type in {
            QEvent.Type.ChildAdded,
            QEvent.Type.StyleChange,
            QEvent.Type.Show,
            QEvent.Type.ParentChange,
        }:
            if watched is self._root and event_type == QEvent.Type.Show:
                self._ensure_screen_connection()
            self.schedule_apply()
        return False

    def schedule_apply(self) -> None:
        if self._apply_pending:
            return
        self._apply_pending = True
        QTimer.singleShot(0, self.apply_now)

    def _install_filters(self) -> None:
        root = self._root
        if root is None:
            return
        widgets = [root]
        try:
            widgets.extend(root.findChildren(QWidget))
        except RuntimeError:
            return
        for widget in widgets:
            try:
                if not bool(widget.property("_ui_scaler_filter_installed")):
                    widget.installEventFilter(self)
                    widget.setProperty("_ui_scaler_filter_installed", True)
            except RuntimeError:
                continue
        self._ensure_screen_connection()

    def _scale_widget_constraints(self, widget: QWidget, scale: float) -> None:
        # Internal children QAbstractItemView ditangani tabel/Qt, kecuali widget
        # yang secara eksplisit diberi baseline oleh helper (mis. cell editor).
        if _ancestor_item_view(widget) and not bool(widget.property(_EXPLICIT_GEOMETRY)):
            return
        if isinstance(widget, QHeaderView):
            return

        try:
            min_w = _property_int(widget, _BASE_MIN_W, widget.minimumWidth())
            min_h = _property_int(widget, _BASE_MIN_H, widget.minimumHeight())
            max_w = _property_int(widget, _BASE_MAX_W, widget.maximumWidth())
            max_h = _property_int(widget, _BASE_MAX_H, widget.maximumHeight())

            target_min_w = skalakan_px(min_w, scale=scale) if min_w > 0 else 0
            target_min_h = skalakan_px(min_h, scale=scale) if min_h > 0 else 0

            # Komponen kecil tertentu (mis. icon-only QToolButton) dapat
            # menetapkan floor ukuran render agar glyph tetap utuh pada scale
            # compact. Floor tidak mengubah baseline dan tidak memengaruhi
            # widget lain yang tidak memasang property ini.
            render_floor_w = _optional_positive_int_property(widget, _MIN_RENDER_W)
            render_floor_h = _optional_positive_int_property(widget, _MIN_RENDER_H)
            if render_floor_w is not None:
                target_min_w = max(target_min_w, render_floor_w)
            if render_floor_h is not None:
                target_min_h = max(target_min_h, render_floor_h)

            target_max_w = (
                QT_GEOMETRY_MAX
                if max_w >= QT_GEOMETRY_MAX
                else skalakan_px(max_w, scale=scale, minimum=max(1, target_min_w))
            )
            target_max_h = (
                QT_GEOMETRY_MAX
                if max_h >= QT_GEOMETRY_MAX
                else skalakan_px(max_h, scale=scale, minimum=max(1, target_min_h))
            )

            widget.setMinimumSize(target_min_w, target_min_h)
            widget.setMaximumSize(target_max_w, target_max_h)
        except RuntimeError:
            return

        if isinstance(widget, QSplitter):
            try:
                base = _property_int(widget, _BASE_SPLITTER_HANDLE, widget.handleWidth())
                widget.setHandleWidth(max(1, skalakan_px(base, scale=scale)))
            except RuntimeError:
                pass

        if isinstance(widget, (QAbstractButton, QTabBar, QToolBar)):
            try:
                icon_size = widget.iconSize()
                base_w = _property_int(widget, _BASE_ICON_W, icon_size.width())
                base_h = _property_int(widget, _BASE_ICON_H, icon_size.height())
                if base_w > 0 and base_h > 0:
                    widget.setIconSize(QSize(
                        skalakan_px(base_w, scale=scale, minimum=1),
                        skalakan_px(base_h, scale=scale, minimum=1),
                    ))
            except (AttributeError, RuntimeError):
                pass

        try:
            effect = widget.graphicsEffect()
        except RuntimeError:
            effect = None
        if isinstance(effect, QGraphicsDropShadowEffect):
            try:
                base_blur = getattr(effect, "_ui_base_blur_radius", effect.blurRadius())
                base_offset = getattr(effect, "_ui_base_offset", effect.offset())
                if not hasattr(effect, "_ui_base_blur_radius"):
                    effect._ui_base_blur_radius = float(base_blur)
                    effect._ui_base_offset = QPointF(base_offset)
                effect.setBlurRadius(max(1.0, float(base_blur) * scale))
                effect.setOffset(
                    float(base_offset.x()) * scale,
                    float(base_offset.y()) * scale,
                )
            except (AttributeError, RuntimeError, TypeError):
                pass

    def _scale_widget_stylesheet(self, widget: QWidget, scale: float) -> None:
        # Style item-view/tabel dikelola layer tabel/tema tersendiri. Melewatkan
        # item-view juga mencegah akumulasi QSS pada subclass yang override
        # setStyleSheet (mis. frozen table).
        if isinstance(widget, QAbstractItemView) or _ancestor_item_view(widget):
            return

        try:
            current = widget.styleSheet()
        except RuntimeError:
            return
        if not current:
            return

        base = _property_text(widget, _BASE_QSS)
        last_scaled = _property_text(widget, _LAST_SCALED_QSS)

        # Bila style diubah oleh theme/module setelah apply terakhir, jadikan
        # style baru itu sebagai baseline, bukan hasil scale sebelumnya.
        if base is None or current != last_scaled:
            base = current
            _set_property(widget, _BASE_QSS, base)

        scaled = skalakan_qss_geometri(base, scale)
        if current != scaled:
            try:
                widget.setStyleSheet(scaled)
            except RuntimeError:
                return
        _set_property(widget, _LAST_SCALED_QSS, scaled)

    def _iter_layouts(self):
        root = self._root
        if root is None:
            return []
        layouts = []
        seen = set()
        try:
            root_layout = root.layout()
        except RuntimeError:
            root_layout = None
        if root_layout is not None:
            layouts.append(root_layout)
        try:
            layouts.extend(root.findChildren(QLayout))
        except RuntimeError:
            pass

        result = []
        for layout in layouts:
            ident = id(layout)
            if ident in seen:
                continue
            seen.add(ident)
            result.append(layout)
        return result

    def _scale_layout(self, layout: QLayout, scale: float) -> None:
        try:
            margins = layout.contentsMargins()
            base_left = _property_int(layout, "_ui_base_margin_left", margins.left())
            base_top = _property_int(layout, "_ui_base_margin_top", margins.top())
            base_right = _property_int(layout, "_ui_base_margin_right", margins.right())
            base_bottom = _property_int(layout, "_ui_base_margin_bottom", margins.bottom())
            layout.setContentsMargins(
                skalakan_px(base_left, scale=scale),
                skalakan_px(base_top, scale=scale),
                skalakan_px(base_right, scale=scale),
                skalakan_px(base_bottom, scale=scale),
            )

            spacing = layout.spacing()
            base_spacing = _property_int(layout, "_ui_base_spacing", spacing)
            if base_spacing >= 0:
                layout.setSpacing(skalakan_px(base_spacing, scale=scale))

            if isinstance(layout, QGridLayout):
                h_spacing = layout.horizontalSpacing()
                v_spacing = layout.verticalSpacing()
                base_h = _property_int(layout, "_ui_base_h_spacing", h_spacing)
                base_v = _property_int(layout, "_ui_base_v_spacing", v_spacing)
                if base_h >= 0:
                    layout.setHorizontalSpacing(skalakan_px(base_h, scale=scale))
                if base_v >= 0:
                    layout.setVerticalSpacing(skalakan_px(base_v, scale=scale))
        except RuntimeError:
            return

        self._scale_spacers(layout, scale)
        try:
            layout.invalidate()
        except RuntimeError:
            pass

    def _scale_spacers(self, layout: QLayout, scale: float) -> None:
        try:
            count = layout.count()
        except RuntimeError:
            return

        for index in range(count):
            try:
                item = layout.itemAt(index)
            except RuntimeError:
                continue
            if item is None:
                continue
            spacer = item.spacerItem()
            if spacer is None:
                continue

            ident = id(spacer)
            cached = self._spacer_bases.get(ident)
            if cached is None or cached[0] is not spacer:
                try:
                    hint = spacer.sizeHint()
                    policy = spacer.sizePolicy()
                    cached = (
                        spacer,
                        int(hint.width()),
                        int(hint.height()),
                        policy.horizontalPolicy(),
                        policy.verticalPolicy(),
                    )
                    self._spacer_bases[ident] = cached
                except RuntimeError:
                    continue

            _, base_w, base_h, h_policy, v_policy = cached
            try:
                spacer.changeSize(
                    skalakan_px(base_w, scale=scale),
                    skalakan_px(base_h, scale=scale),
                    h_policy,
                    v_policy,
                )
            except RuntimeError:
                continue


    def apply_now(self) -> None:
        self._apply_pending = False
        if self._applying:
            return

        root = self._root
        if root is None:
            return

        width, height = self._root_available_size()
        scale = hitung_ui_scale(width, height)
        scale_changed = self._scale is None or abs(scale - self._scale) > 0.0001

        self._applying = True
        try:
            self._scale = tetapkan_ui_scale_aktif(scale)
            self._install_filters()

            if scale_changed and callable(self._on_scale_changed):
                self._on_scale_changed(self._scale)

            widgets = [root]
            try:
                widgets.extend(root.findChildren(QWidget))
            except RuntimeError:
                pass

            for widget in widgets:
                self._scale_widget_constraints(widget, self._scale)
                self._scale_widget_stylesheet(widget, self._scale)

            for layout in self._iter_layouts():
                self._scale_layout(layout, self._scale)

            try:
                root.updateGeometry()
                root.update()
            except RuntimeError:
                pass
        finally:
            self._applying = False


__all__ = [
    "ResponsiveUIScaler",
    "skalakan_qss_geometri",
]