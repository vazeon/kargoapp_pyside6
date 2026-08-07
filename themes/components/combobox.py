# themes/components/combobox.py
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QTimer,
)

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
)


class _PopupBawahFilter(QObject):
    """
    Memastikan popup QComboBox selalu dibuka
    tepat di bawah sisi kiri QComboBox.
    """

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self._combo = combo

    def eventFilter(
        self,
        watched: QObject,
        event: QEvent,
    ) -> bool:
        if event.type() == QEvent.Type.Show:
            QTimer.singleShot(
                0,
                self._atur_posisi_popup,
            )

        return False

    def _atur_posisi_popup(self) -> None:
        combo = self._combo

        if combo is None or not combo.isVisible():
            return

        view = combo.view()

        if view is None:
            return

        popup = view.window()

        if popup is None:
            return

        posisi_bawah = combo.mapToGlobal(
            QPoint(
                0,
                combo.height(),
            )
        )

        titik_tengah = combo.mapToGlobal(
            combo.rect().center()
        )

        screen = QApplication.screenAt(
            titik_tengah
        )

        if screen is None:
            popup.move(posisi_bawah)
            return

        area_layar = screen.availableGeometry()

        batas_x_maksimum = (
            area_layar.right()
            - popup.width()
            + 1
        )

        posisi_x = max(
            area_layar.left(),
            min(
                posisi_bawah.x(),
                batas_x_maksimum,
            ),
        )

        popup.move(
            posisi_x,
            posisi_bawah.y(),
        )


def terapkan_popup_bawah_combobox(
    comboboxes: Iterable[QComboBox],
) -> None:
    """
    Memasang pengatur posisi popup pada beberapa QComboBox.

    Helper ini tidak mengubah style, ikon, palette,
    font, atau ukuran QComboBox.
    """

    for combo in comboboxes:
        if not isinstance(combo, QComboBox):
            continue

        if getattr(
            combo,
            "_popup_bawah_filter",
            None,
        ) is not None:
            continue

        view = combo.view()

        if view is None:
            continue

        popup = view.window()

        if popup is None:
            continue

        handler = _PopupBawahFilter(combo)

        popup.installEventFilter(handler)

        # Menjaga instance event filter agar tidak
        # dibersihkan oleh garbage collector.
        combo._popup_bawah_filter = handler