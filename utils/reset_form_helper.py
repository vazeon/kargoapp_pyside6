# utils/reset_form_helper.py

from typing import Any, Dict, Iterable, Optional

from PySide6.QtCore import QDate, QDateTime, QTime, QTimer
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDoubleSpinBox,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTextEdit,
    QTimeEdit,
    QTreeWidget,
    QWidget,
)

from .widget_helpers import blokir_signal_opsional


_STATISTIK_AWAL = {
    "lineedit": 0,
    "textedit": 0,
    "combobox": 0,
    "spinbox": 0,
    "tanggal": 0,
    "centang": 0,
    "tabel": 0,
    "daftar": 0,
}

_TEXT_EDIT_WIDGETS = (QTextEdit, QPlainTextEdit)
_DATE_TIME_WIDGETS = (QDateEdit, QTimeEdit, QDateTimeEdit)
_SPINBOX_WIDGETS = (QSpinBox, QDoubleSpinBox)
_CHECK_WIDGETS = (QCheckBox, QRadioButton)
_LIST_WIDGETS = (QListWidget, QTreeWidget)
_INTERNAL_LINEEDIT_PARENTS = (QComboBox, QAbstractSpinBox)


def _widget_dikecualikan(
    widget: QWidget,
    daftar_kecuali: Iterable[QWidget],
) -> bool:
    """True jika widget/parent ditandai ignore atau berada dalam pengecualian."""
    current: Optional[QWidget] = widget
    while current is not None:
        if bool(current.property("clear_form_ignore")):
            return True
        current = current.parentWidget()

    return any(
        widget is widget_kecuali or widget_kecuali.isAncestorOf(widget)
        for widget_kecuali in daftar_kecuali
    )


def _lineedit_editor_internal(widget: QLineEdit) -> bool:
    """Mendeteksi QLineEdit editor internal milik combo/spinbox Qt."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, _INTERNAL_LINEEDIT_PARENTS):
            return True
        parent = parent.parentWidget()
    return False


def _nilai_spinbox_aman(
    widget: Any,
    nilai_default: Optional[float],
) -> float:
    """Menjaga nilai reset tetap di antara minimum dan maksimum widget."""
    minimum, maximum = widget.minimum(), widget.maximum()
    if nilai_default is None:
        nilai = 0 if minimum <= 0 <= maximum else minimum
    else:
        nilai = nilai_default
    return max(minimum, min(nilai, maximum))


def _reset_combobox(
    widget: QComboBox,
    indeks_default: int,
    kosongkan_editable: bool,
    blokir_signal: bool,
) -> None:
    with blokir_signal_opsional(widget, blokir_signal):
        property_index = widget.property("clear_form_combo_index")
        try:
            index_target = int(
                property_index if property_index is not None else indeks_default
            )
        except (TypeError, ValueError):
            index_target = 0

        if widget.count() <= 0:
            widget.setCurrentIndex(-1)
        else:
            widget.setCurrentIndex(max(-1, min(index_target, widget.count() - 1)))

        if widget.isEditable() and kosongkan_editable:
            widget.clearEditText()


def _reset_spinbox(
    widget: Any,
    nilai_default: Optional[float],
    blokir_signal: bool,
) -> None:
    with blokir_signal_opsional(widget, blokir_signal):
        property_value = widget.property("clear_form_value")
        nilai_target = property_value if property_value is not None else nilai_default
        nilai_aman = _nilai_spinbox_aman(widget, nilai_target)
        widget.setValue(
            int(round(nilai_aman)) if isinstance(widget, QSpinBox) else float(nilai_aman)
        )


def _reset_tanggal(widget: Any, blokir_signal: bool) -> None:
    with blokir_signal_opsional(widget, blokir_signal):
        if isinstance(widget, QDateEdit):
            widget.setDate(QDate.currentDate())
        elif isinstance(widget, QTimeEdit):
            widget.setTime(QTime.currentTime())
        else:
            widget.setDateTime(QDateTime.currentDateTime())


def _reset_centang(widget: Any, blokir_signal: bool) -> None:
    with blokir_signal_opsional(widget, blokir_signal):
        auto_exclusive = (
            widget.autoExclusive() if isinstance(widget, QRadioButton) else False
        )
        if auto_exclusive:
            widget.setAutoExclusive(False)
        widget.setChecked(False)
        if auto_exclusive:
            widget.setAutoExclusive(True)


def _readonly_dilewati(widget: Any, lewati_readonly: bool) -> bool:
    return lewati_readonly and widget.isReadOnly()


def reset_form_input_global(
    container_widget: QWidget,
    *,
    kecualikan: Optional[Iterable[QWidget]] = None,
    indeks_combo_default: int = 0,
    kosongkan_combo_editable: bool = True,
    reset_spinbox: bool = True,
    nilai_spinbox_default: Optional[float] = 0,
    reset_tanggal: bool = False,
    reset_centang: bool = True,
    kosongkan_tabel: bool = False,
    kosongkan_daftar: bool = False,
    lewati_readonly: bool = True,
    blokir_signal: bool = True,
    fokus_ke: Optional[QWidget] = None,
) -> Dict[str, int]:
    """Membersihkan input dalam container secara rekursif.

    Mendukung QLineEdit, text edit, combo box, spinbox, date/time edit,
    checkbox/radio button, serta table/list/tree secara opsional. Widget dapat
    dikecualikan melalui ``kecualikan`` atau property ``clear_form_ignore``.
    Property ``clear_form_combo_index`` dan ``clear_form_value`` dapat dipakai
    untuk menentukan nilai reset khusus per widget.
    """
    hasil: Dict[str, int] = _STATISTIK_AWAL.copy()
    if container_widget is None or not isinstance(container_widget, QWidget):
        return hasil

    daftar_kecuali = tuple(
        widget for widget in (kecualikan or ()) if isinstance(widget, QWidget)
    )
    daftar_widget = [container_widget, *container_widget.findChildren(QWidget)]
    sudah_diproses = set()

    for widget in daftar_widget:
        identitas = id(widget)
        if identitas in sudah_diproses:
            continue
        sudah_diproses.add(identitas)

        if _widget_dikecualikan(widget, daftar_kecuali):
            continue

        if isinstance(widget, QComboBox):
            _reset_combobox(
                widget,
                indeks_combo_default,
                kosongkan_combo_editable,
                blokir_signal,
            )
            hasil["combobox"] += 1

        elif isinstance(widget, _SPINBOX_WIDGETS):
            if reset_spinbox:
                _reset_spinbox(widget, nilai_spinbox_default, blokir_signal)
                hasil["spinbox"] += 1

        elif isinstance(widget, _DATE_TIME_WIDGETS):
            if not _readonly_dilewati(widget, lewati_readonly) and reset_tanggal:
                _reset_tanggal(widget, blokir_signal)
                hasil["tanggal"] += 1

        elif isinstance(widget, QLineEdit):
            if _lineedit_editor_internal(widget) or _readonly_dilewati(
                widget, lewati_readonly
            ):
                continue
            with blokir_signal_opsional(widget, blokir_signal):
                widget.clear()
            hasil["lineedit"] += 1

        elif isinstance(widget, _TEXT_EDIT_WIDGETS):
            if _readonly_dilewati(widget, lewati_readonly):
                continue
            with blokir_signal_opsional(widget, blokir_signal):
                widget.clear()
            hasil["textedit"] += 1

        elif isinstance(widget, _CHECK_WIDGETS):
            if reset_centang:
                _reset_centang(widget, blokir_signal)
                hasil["centang"] += 1

        elif isinstance(widget, QTableWidget):
            if kosongkan_tabel:
                with blokir_signal_opsional(widget, blokir_signal):
                    widget.setRowCount(0)
                hasil["tabel"] += 1

        elif isinstance(widget, _LIST_WIDGETS) and kosongkan_daftar:
            with blokir_signal_opsional(widget, blokir_signal):
                widget.clear()
            hasil["daftar"] += 1

    if fokus_ke is not None and isinstance(fokus_ke, QWidget):
        QTimer.singleShot(
            0,
            lambda: fokus_ke.setFocus() if fokus_ke.isEnabled() else None,
        )

    return hasil