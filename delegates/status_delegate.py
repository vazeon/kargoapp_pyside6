# delegates/status_delegates.py
# warna higlight baris
from __future__ import annotations

from typing import Callable, Optional, Tuple, Union

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPalette
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

        # Preserve the view's native/QSS selection appearance.
        if not (opt.state & QStyle.StateFlag.State_Selected):
            background, foreground = self._color_provider(
                is_dark=self._is_dark,
                status=self._status_for_index(index),
                is_alternate_row=bool(index.row() % 2),
            )

            background_color = _to_qcolor(background)
            foreground_color = _to_qcolor(foreground)

            if background_color is not None:
                opt.backgroundBrush = QBrush(background_color)

            if foreground_color is not None:
                text_brush = QBrush(foreground_color)
                opt.palette.setBrush(QPalette.ColorRole.Text, text_brush)
                opt.palette.setBrush(QPalette.ColorRole.WindowText, text_brush)

        # Jika cell memakai setCellWidget()/indexWidget (mis. STATUS PENAGIHAN
        # dengan QLabel hyperlink), widget tersebut menjadi renderer teks utama.
        # Delegate tetap menggambar background/selection/highlight, tetapi teks
        # QTableWidgetItem di bawahnya harus disembunyikan agar tidak dobel.
        view = self.parent()
        if isinstance(view, QAbstractItemView) and view.indexWidget(index) is not None:
            opt.text = ""

        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)


def attach_status_delegate(
    view: QAbstractItemView,
    *,
    status_column: int,
    color_provider: ColorProvider,
    is_dark: bool = False,
    normalize_status: bool = True,
    status_role: int = Qt.ItemDataRole.DisplayRole,
) -> StatusColorDelegate:
    if not isinstance(view, QAbstractItemView):
        raise TypeError("view harus turunan QAbstractItemView.")

    delegate = StatusColorDelegate(
        status_column=status_column,
        color_provider=color_provider,
        is_dark=is_dark,
        normalize_status=normalize_status,
        status_role=status_role,
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