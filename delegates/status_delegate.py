# delegates/status_delegates.py
# warna higlight baris
from __future__ import annotations

from typing import Callable, Optional, Tuple, Union

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPalette, QPen, QRegion
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyleOptionViewItem,
)

from delegates.overflow_tooltip_delegate import OverflowTooltipDelegate

ColorValue = Union[QColor, str]
ColorResult = Tuple[Optional[ColorValue], Optional[ColorValue]]
ColorProvider = Callable[..., ColorResult]

_DELEGATE_ATTRIBUTE = "_status_color_delegate"


def _to_qcolor(value: Optional[ColorValue]) -> Optional[QColor]:
    if value is None:
        return None

    color = value if isinstance(value, QColor) else QColor(str(value))
    return color if color.isValid() else None


class StatusColorDelegate(OverflowTooltipDelegate):

    def __init__(
        self,
        *,
        status_column: int,
        color_provider: ColorProvider,
        is_dark: bool = False,
        normalize_status: bool = True,
        status_role: int = Qt.ItemDataRole.DisplayRole,
        selected_checkbox_color: Optional[ColorValue] = None,
        parent: Optional[QAbstractItemView] = None,
    ) -> None:
        super().__init__(parent)

        if status_column < 0:
            raise ValueError("status_column tidak boleh bernilai negatif.")
        if not callable(color_provider):
            raise TypeError("color_provider harus berupa callable.")

        self._status_column = int(status_column)
        self._color_provider = color_provider
        self._is_dark = bool(is_dark)
        self._normalize_status = bool(normalize_status)
        self._status_role = int(status_role)
        # Opt-in per tabel. None mempertahankan tampilan delegate lama.
        self._selected_checkbox_color = _to_qcolor(selected_checkbox_color)

    @property
    def is_dark(self) -> bool:
        return self._is_dark

    def set_theme(self, is_dark: bool) -> None:
        new_value = bool(is_dark)
        if self._is_dark == new_value:
            return

        self._is_dark = new_value
        self.refresh()

    def refresh(self) -> None:
        view = self.parent()
        if isinstance(view, QAbstractItemView):
            view.viewport().update()

    def _status_for_index(self, index) -> str:
        status_index = index.sibling(index.row(), self._status_column)
        status = str(status_index.data(self._status_role) or "").strip()
        return status.upper() if self._normalize_status else status

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        background_color = None

        # 1. Evaluasi warna HANYA jika baris tidak sedang di-select
        if not (opt.state & QStyle.StateFlag.State_Selected):
            background, foreground = self._color_provider(
                is_dark=self._is_dark,
                status=self._status_for_index(index),
                is_alternate_row=bool(index.row() % 2),
            )

            background_color = _to_qcolor(background)
            foreground_color = _to_qcolor(foreground)

            if foreground_color is not None:
                text_brush = QBrush(foreground_color)
                opt.palette.setBrush(QPalette.ColorRole.Text, text_brush)
                opt.palette.setBrush(QPalette.ColorRole.WindowText, text_brush)

        view = self.parent()
        if isinstance(view, QAbstractItemView) and view.indexWidget(index) is not None:
            opt.text = ""

        if background_color is not None:
            painter.save()
            painter.setClipRect(opt.rect)
            painter.fillRect(opt.rect, background_color)
            painter.restore()
            opt.backgroundBrush = QBrush(Qt.BrushStyle.NoBrush)

        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        if (
            self._selected_checkbox_color is not None
            and opt.state & QStyle.StateFlag.State_Selected
            and opt.features & QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        ):
            self._paint_selected_checkbox(painter, opt, style, widget)
            return

        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

    def _paint_selected_checkbox(self, painter, opt, style, widget) -> None:
        check_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, widget
        )
        if check_rect.isEmpty():
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
            return

        # QSS dapat memberikan ukuran indicator berbeda untuk state selected.
        # Ambil ukuran state normal agar checkbox tidak terlihat membesar ketika
        # baris dipilih; posisi/area klik selected tetap milik Qt.
        normal_opt = QStyleOptionViewItem(opt)
        normal_opt.state &= ~QStyle.StateFlag.State_Selected
        normal_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemCheckIndicator,
            normal_opt,
            widget,
        )
        if normal_rect.isEmpty():
            normal_rect = check_rect

        # Beberapa theme (termasuk kombinasi QtDarkTheme + QSS aplikasi)
        # mengembalikan rect 18--20 px meskipun gambar checkbox normalnya hanya
        # sekitar 14 px. Batasi ukuran *visual* supaya state selected benar-benar
        # sama rampingnya dengan checkbox normal.
        standard_visual_size = 15
        target_width = min(check_rect.width(), normal_rect.width(), standard_visual_size)
        target_height = min(check_rect.height(), normal_rect.height(), standard_visual_size)
        target_rect = QRectF(
            check_rect.center().x() - target_width / 2.0,
            check_rect.center().y() - target_height / 2.0,
            target_width,
            target_height,
        )

        # Pertahankan background, posisi teks/icon, serta ukuran/hit area Qt.
        # Hanya gambar indikator bawaan yang dikecualikan dari area paint.
        painter.save()
        try:
            painter.setClipRect(opt.rect, Qt.ClipOperation.IntersectClip)
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget)
            painter.setClipRegion(
                QRegion(opt.rect).subtracted(QRegion(check_rect)),
                Qt.ClipOperation.IntersectClip,
            )
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        finally:
            painter.restore()

        painter.save()
        try:
            painter.setClipRect(check_rect.intersected(opt.rect), Qt.ClipOperation.IntersectClip)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # Invert warna indikator pada baris terpilih:
            # kotak memakai warna opsi (putih pada Manifest), sedangkan tanda
            # centang mengikuti warna highlight baris (biru).
            border_pen = QPen(self._selected_checkbox_color)
            border_pen.setWidthF(max(1.0, min(target_width, target_height) / 12.0))
            painter.setPen(border_pen)
            painter.setBrush(QBrush(self._selected_checkbox_color))
            inset = border_pen.widthF() / 2.0 + 0.5
            box = target_rect.adjusted(inset, inset, -inset, -inset)
            painter.drawRoundedRect(box, 1.5, 1.5)

            mark_pen = QPen(opt.palette.highlight().color())
            mark_pen.setWidthF(max(1.5, min(target_width, target_height) / 8.0))
            mark_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            mark_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(mark_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            mark = QPainterPath()
            x, y, w, h = box.x(), box.y(), box.width(), box.height()
            if opt.checkState == Qt.CheckState.Checked:
                mark.moveTo(x + w * 0.20, y + h * 0.52)
                mark.lineTo(x + w * 0.43, y + h * 0.75)
                mark.lineTo(x + w * 0.82, y + h * 0.25)
            elif opt.checkState == Qt.CheckState.PartiallyChecked:
                mark.moveTo(x + w * 0.23, y + h * 0.50)
                mark.lineTo(x + w * 0.77, y + h * 0.50)
            painter.drawPath(mark)
        finally:
            painter.restore()


def attach_status_delegate(
    view: QAbstractItemView,
    *,
    status_column: int,
    color_provider: ColorProvider,
    is_dark: bool = False,
    normalize_status: bool = True,
    status_role: int = Qt.ItemDataRole.DisplayRole,
    selected_checkbox_color: Optional[ColorValue] = None,
) -> StatusColorDelegate:
    if not isinstance(view, QAbstractItemView):
        raise TypeError("view harus turunan QAbstractItemView.")

    delegate = StatusColorDelegate(
        status_column=status_column,
        color_provider=color_provider,
        is_dark=is_dark,
        normalize_status=normalize_status,
        status_role=status_role,
        selected_checkbox_color=selected_checkbox_color,
        parent=view,
    )

    view.setItemDelegate(delegate)
    setattr(view, _DELEGATE_ATTRIBUTE, delegate)
    return delegate


def update_status_delegate_theme(
    view: QAbstractItemView,
    is_dark: bool,
) -> bool:
    delegate = getattr(view, _DELEGATE_ATTRIBUTE, None)
    if not isinstance(delegate, StatusColorDelegate):
        return False

    delegate.set_theme(is_dark)
    return True