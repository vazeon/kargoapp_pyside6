# delegates/overflow_tooltip_delegate.py
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
)


class OverflowTooltipDelegate(QStyledItemDelegate):
    """Tooltip dinamis yang hanya muncul ketika teks cell benar-benar terpotong.

    Delegate ini sengaja tidak menyimpan tooltip pada ``QTableWidgetItem``.
    Lebar cell diperiksa saat event hover terjadi, sehingga resize kolom langsung
    memengaruhi keputusan tampil/tidaknya tooltip tanpa sinkronisasi tambahan.
    """

    def __init__(self, parent: Optional[QAbstractItemView] = None) -> None:
        super().__init__(parent)

    @staticmethod
    def _display_text(index) -> str:
        value = index.data(Qt.ItemDataRole.DisplayRole)
        return str(value if value is not None else "")

    def _text_is_elided(self, view, option, index, text: str) -> bool:
        if not text or text.strip() in {"", "-"}:
            return False

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget or view
        style = widget.style() if widget is not None else QApplication.style()
        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText,
            opt,
            widget,
        )
        available_width = max(0, int(text_rect.width()))
        if available_width <= 0:
            return True

        elide_mode = opt.textElideMode
        if elide_mode == Qt.TextElideMode.ElideNone:
            return opt.fontMetrics.horizontalAdvance(text) > available_width

        rendered = opt.fontMetrics.elidedText(text, elide_mode, available_width)
        return rendered != text

    def helpEvent(self, event, view, option, index) -> bool:
        if event is None or event.type() != QEvent.Type.ToolTip:
            return super().helpEvent(event, view, option, index)
        if index is None or not index.isValid():
            QToolTip.hideText()
            return False

        text = self._display_text(index)
        if self._text_is_elided(view, option, index, text):
            QToolTip.showText(event.globalPos(), text, view, option.rect)
            return True

        QToolTip.hideText()
        event.ignore()
        return False