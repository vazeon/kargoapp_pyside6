# utils/smooth_scroll_helper.py
from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEvent,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QComboBox,
    QTabBar,
    QWidget,
)


DEFAULT_DURATION_MS = 130
DEFAULT_WHEEL_LINES = 3
DEFAULT_HORIZONTAL_STEP_PX = 80
DEFAULT_VERTICAL_STEP_PX = 48


class SmoothScrollController(QObject):
    """Animate mouse-wheel scrolling for one scroll area.

    A controller owns one reusable animation per axis. Each instance maintains
    its own targets, so scrolling one widget cannot affect another widget.
    """

    def __init__(
        self,
        scroll_area,
        event_targets=None,
        duration_ms=DEFAULT_DURATION_MS,
        wheel_lines=DEFAULT_WHEEL_LINES,
        horizontal_step_px=DEFAULT_HORIZONTAL_STEP_PX,
        vertical_step_px=DEFAULT_VERTICAL_STEP_PX,
    ):
        super().__init__(scroll_area)
        self._scroll_area = scroll_area
        self._duration_ms = max(1, int(duration_ms))
        self._wheel_lines = max(1, int(wheel_lines))
        self._horizontal_step_px = max(1, int(horizontal_step_px))
        self._vertical_step_px = max(1, int(vertical_step_px))
        self._scrollbars = {
            "vertical": self._ambil_scrollbar("vertical"),
            "horizontal": self._ambil_scrollbar("horizontal"),
        }
        self._animations = {}
        self._targets = {}
        self._event_targets = self._normalisasi_event_targets(event_targets)

        # Mark the widget and event targets. The global installer uses these
        # markers to avoid installing/handling a second animation on special
        # tables that already have a local controller (e.g. frozen columns).
        try:
            setattr(scroll_area, "_kargo_smooth_scroll_controller", self)
        except (AttributeError, RuntimeError):
            pass
        for target in self._event_targets:
            try:
                setattr(target, "_kargo_smooth_scroll_controller", self)
            except (AttributeError, RuntimeError):
                pass

        viewport_getter = getattr(scroll_area, "viewport", None)
        self._primary_event_target = (
            viewport_getter() if callable(viewport_getter) else None
        )
        if self._primary_event_target is None and self._event_targets:
            self._primary_event_target = self._event_targets[0]

        if isinstance(scroll_area, QAbstractItemView):
            scroll_area.setVerticalScrollMode(
                QAbstractItemView.ScrollMode.ScrollPerPixel
            )
            scroll_area.setHorizontalScrollMode(
                QAbstractItemView.ScrollMode.ScrollPerPixel
            )

        for axis, scrollbar in self._scrollbars.items():
            if scrollbar is None:
                continue
            animation = QPropertyAnimation(scrollbar, b"value", self)
            animation.setDuration(self._duration_ms)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.finished.connect(
                lambda current_axis=axis: self._animasi_selesai(current_axis)
            )
            self._animations[axis] = animation
            self._targets[axis] = scrollbar.value()
            scrollbar.sliderPressed.connect(
                lambda current_axis=axis: self.hentikan(current_axis)
            )
            scrollbar.rangeChanged.connect(
                lambda _minimum, _maximum, current_axis=axis: self._rentang_berubah(current_axis)
            )
            scrollbar.valueChanged.connect(
                lambda value, current_axis=axis: self._nilai_berubah(current_axis, value)
            )

        for target in self._event_targets:
            target.installEventFilter(self)

    def _ambil_scrollbar(self, axis):
        nama_method = (
            "verticalScrollBar" if axis == "vertical" else "horizontalScrollBar"
        )
        getter = getattr(self._scroll_area, nama_method, None)
        return getter() if callable(getter) else None

    def _normalisasi_event_targets(self, event_targets):
        if event_targets is None:
            viewport_getter = getattr(self._scroll_area, "viewport", None)
            event_targets = (viewport_getter(),) if callable(viewport_getter) else ()
        elif not isinstance(event_targets, (tuple, list, set)):
            event_targets = (event_targets,)

        hasil = []
        for target in event_targets:
            if target is not None and not any(target is existing for existing in hasil):
                hasil.append(target)
        return tuple(hasil)

    def _target_dikenal(self, watched):
        return any(watched is target for target in self._event_targets)

    def _animasi_berjalan(self, axis):
        animation = self._animations.get(axis)
        return bool(
            animation is not None
            and animation.state() == QAbstractAnimation.State.Running
        )

    def _nilai_berubah(self, axis, value):
        # Jangan menggantikan target akhir dengan nilai antara animasi.
        if not self._animasi_berjalan(axis):
            self._targets[axis] = int(value)

    def _rentang_berubah(self, axis):
        scrollbar = self._scrollbars.get(axis)
        animation = self._animations.get(axis)
        if scrollbar is None:
            return
        if self._animasi_berjalan(axis):
            target = self._batasi_target(
                axis, self._targets.get(axis, scrollbar.value())
            )
            animation.stop()
            posisi_sekarang = scrollbar.value()
            self._targets[axis] = target
            if target != posisi_sekarang:
                animation.setStartValue(posisi_sekarang)
                animation.setEndValue(target)
                animation.setDuration(self._duration_ms)
                animation.start()
        else:
            self._targets[axis] = scrollbar.value()

    def _animasi_selesai(self, axis):
        scrollbar = self._scrollbars.get(axis)
        if scrollbar is not None:
            self._targets[axis] = scrollbar.value()

    def _batasi_target(self, axis, target):
        scrollbar = self._scrollbars.get(axis)
        if scrollbar is None:
            return int(round(target))
        return max(
            scrollbar.minimum(),
            min(scrollbar.maximum(), int(round(target))),
        )

    def hentikan(self, axis):
        """Stop an axis animation and sync the target to its current position."""
        animation = self._animations.get(axis)
        scrollbar = self._scrollbars.get(axis)
        if animation is not None and self._animasi_berjalan(axis):
            animation.stop()
        if scrollbar is not None:
            self._targets[axis] = scrollbar.value()

    def hentikan_semua(self):
        """Stop animations before rebuilding or replacing table contents."""
        for axis in tuple(self._animations):
            self.hentikan(axis)

    def sinkronkan_target(self, axis, value=None):
        """Rebase an idle target after overlay/layout synchronization."""
        if self._animasi_berjalan(axis):
            return
        scrollbar = self._scrollbars.get(axis)
        if scrollbar is None:
            return
        self._targets[axis] = (
            scrollbar.value()
            if value is None
            else self._batasi_target(axis, value)
        )

    def _langkah_vertikal(self):
        header_getter = getattr(self._scroll_area, "verticalHeader", None)
        if callable(header_getter):
            header = header_getter()
            section_getter = getattr(header, "defaultSectionSize", None)
            if callable(section_getter):
                return max(1, int(section_getter())) * self._wheel_lines
        return self._vertical_step_px * self._wheel_lines

    @staticmethod
    def _faktor_arah(event):
        # Qt keeps deltas unchanged for inverted devices and exposes inversion
        # separately; apply that flag only when interpreting the delta ourselves.
        try:
            return 1 if event.inverted() else -1
        except AttributeError:
            return -1

    def _scroll_halus_ke(self, axis, delta_pixels):
        scrollbar = self._scrollbars.get(axis)
        animation = self._animations.get(axis)
        if scrollbar is None or animation is None or not delta_pixels:
            return False

        sedang_berjalan = self._animasi_berjalan(axis)
        dasar = self._targets[axis] if sedang_berjalan else scrollbar.value()
        target = self._batasi_target(axis, dasar + delta_pixels)
        self._targets[axis] = target

        posisi_sekarang = scrollbar.value()
        if target == posisi_sekarang:
            if sedang_berjalan:
                animation.stop()
                self._targets[axis] = posisi_sekarang
                return True
            return False

        if sedang_berjalan:
            # Restart the same animation from the current value. This avoids a
            # value jump that can occur when changing an animation's end value
            # mid-flight, while still reusing the existing animation object.
            animation.stop()
        animation.setStartValue(posisi_sekarang)
        animation.setEndValue(target)
        animation.setDuration(self._duration_ms)
        animation.start()
        return True

    def _scroll_pixel_langsung(self, event, pixel, shift):
        """Route pixel-based input over overlays directly to the main scrollbars."""
        factor = self._faktor_arah(event)
        perubahan = {}
        if shift:
            raw_horizontal = pixel.x() or pixel.y()
            if raw_horizontal:
                perubahan["horizontal"] = raw_horizontal * factor
        else:
            if pixel.y():
                perubahan["vertical"] = pixel.y() * factor
            if pixel.x():
                perubahan["horizontal"] = pixel.x() * factor

        berubah = False
        for axis, delta in perubahan.items():
            scrollbar = self._scrollbars.get(axis)
            if scrollbar is None:
                continue
            self.hentikan(axis)
            nilai_lama = scrollbar.value()
            scrollbar.setValue(self._batasi_target(axis, nilai_lama + delta))
            berubah = berubah or scrollbar.value() != nilai_lama
        return berubah

    def proses_roda(self, watched, event, *, mode_global=False):
        """Process one wheel event; global mode leaves pixel gestures native."""
        if event.type() != QEvent.Type.Wheel:
            return False
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Preserve application-specific Ctrl+wheel behavior (for example zoom).
            return False

        pixel = event.pixelDelta()
        angle = event.angleDelta()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if pixel.x() or pixel.y():
            if mode_global:
                # Trackpads and high-resolution devices already emit smooth pixel
                # deltas. Let Qt handle them natively instead of animating twice.
                return False
            if watched is self._primary_event_target and not shift:
                # Native Qt scrolling handles trackpad/high-resolution pixel input.
                if pixel.y():
                    self.hentikan("vertical")
                if pixel.x():
                    self.hentikan("horizontal")
                return False

            # If the pointer is over an overlay, drive the main scrollbars directly
            # so horizontal gestures do not get lost on the narrow frozen table.
            handled = self._scroll_pixel_langsung(event, pixel, shift)
            if handled:
                event.accept()
                return True
            return False

        handled = False
        factor = self._faktor_arah(event)
        if shift:
            raw = angle.x() or angle.y()
            if raw:
                delta_horizontal = factor * (raw / 120.0) * self._horizontal_step_px
                handled = self._scroll_halus_ke("horizontal", delta_horizontal)
        else:
            if angle.y():
                delta_vertical = factor * (angle.y() / 120.0) * self._langkah_vertikal()
                handled = self._scroll_halus_ke("vertical", delta_vertical) or handled
            if angle.x():
                delta_horizontal = factor * (angle.x() / 120.0) * self._horizontal_step_px
                handled = self._scroll_halus_ke("horizontal", delta_horizontal) or handled

        if handled:
            event.accept()
            return True
        return False

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel or not self._target_dikenal(watched):
            return super().eventFilter(watched, event)
        return self.proses_roda(watched, event, mode_global=False)


def pasang_scroll_halus(
    scroll_area,
    event_targets=None,
    *,
    duration_ms=DEFAULT_DURATION_MS,
    wheel_lines=DEFAULT_WHEEL_LINES,
    horizontal_step_px=DEFAULT_HORIZONTAL_STEP_PX,
    vertical_step_px=DEFAULT_VERTICAL_STEP_PX,
):
    """Attach one reusable smooth-scroll controller to a scrollable widget.

    Call once per widget and keep the returned controller on its owner. If an
    overlay is involved, pass both viewports, e.g. ``(table.viewport(),
    overlay.viewport())``. Only mouse-wheel angle deltas are animated; pixel
    deltas retain native behavior for trackpads.
    """
    return SmoothScrollController(
        scroll_area,
        event_targets=event_targets,
        duration_ms=duration_ms,
        wheel_lines=wheel_lines,
        horizontal_step_px=horizontal_step_px,
        vertical_step_px=vertical_step_px,
    )


_controller_global_smooth: "GlobalSmoothScrollController | None" = None


class GlobalSmoothScrollController(QObject):
    """Lazily enable smooth wheel scrolling for every QAbstractScrollArea.

    The controller is installed once on QApplication. It creates one reusable
    animation controller only when a scrollable widget first receives a wheel
    event, including widgets that are loaded lazily after application startup.
    """

    def __init__(self, app: QApplication, **scroll_options):
        super().__init__(app)
        self._app = app
        self._scroll_options = dict(scroll_options)
        app.installEventFilter(self)

    @staticmethod
    def _dropdown_event(combo: QComboBox, widget: QWidget) -> bool:
        try:
            view = combo.view()
            return bool(
                view is not None
                and view.isVisible()
                and (widget is view or view.isAncestorOf(widget))
            )
        except RuntimeError:
            return False

    @staticmethod
    def _parent_widget(widget):
        try:
            return widget.parentWidget()
        except RuntimeError:
            return None

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QWidget):
            return False

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False

        current = watched
        scroll_area = None
        while current is not None:
            # Leave tab and closed-combobox decisions to wheel_event_policy.py.
            if isinstance(current, QTabBar):
                return False
            if isinstance(current, QComboBox) and not self._dropdown_event(current, watched):
                return False

            existing = getattr(current, "_kargo_smooth_scroll_controller", None)
            if isinstance(existing, SmoothScrollController):
                # When the event target is one of the explicitly registered
                # targets, let that controller's QObject event filter handle it.
                if existing._target_dikenal(watched):
                    return False
                return existing.proses_roda(watched, event, mode_global=True)

            if scroll_area is None and isinstance(current, QAbstractScrollArea):
                scroll_area = current
            current = self._parent_widget(current)

        if scroll_area is None:
            return False

        controller = getattr(scroll_area, "_kargo_smooth_scroll_controller", None)
        if not isinstance(controller, SmoothScrollController):
            controller = SmoothScrollController(
                scroll_area, event_targets=(), **self._scroll_options
            )
        return controller.proses_roda(watched, event, mode_global=True)


def pasang_scroll_halus_global(
    app: QApplication | None = None,
    *,
    duration_ms=DEFAULT_DURATION_MS,
    wheel_lines=DEFAULT_WHEEL_LINES,
    horizontal_step_px=DEFAULT_HORIZONTAL_STEP_PX,
    vertical_step_px=DEFAULT_VERTICAL_STEP_PX,
):
    """Install app-wide smooth scrolling once, for all QAbstractScrollArea widgets.

    The controller is lazy: tables, text editors, lists, trees, scroll areas and
    lazily created tabs receive animations on first wheel use. Pixel-based trackpad
    gestures stay native. Tab bars and closed ComboBoxes remain governed by the
    separate global wheel policy.
    """
    global _controller_global_smooth

    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError(
            "QApplication harus dibuat sebelum smooth scrolling global dipasang."
        )

    if _controller_global_smooth is not None:
        try:
            if _controller_global_smooth._app is app:
                return _controller_global_smooth
        except RuntimeError:
            _controller_global_smooth = None

    _controller_global_smooth = GlobalSmoothScrollController(
        app,
        duration_ms=duration_ms,
        wheel_lines=wheel_lines,
        horizontal_step_px=horizontal_step_px,
        vertical_step_px=vertical_step_px,
    )
    return _controller_global_smooth


