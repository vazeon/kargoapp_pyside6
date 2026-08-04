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


def _widget_dikecualikan(
    widget: QWidget,
    daftar_kecuali: Iterable[QWidget],
) -> bool:
    """
    Memeriksa apakah widget atau salah satu parent-nya dikecualikan.

    Widget/container juga dapat diberi:
        widget.setProperty("clear_form_ignore", True)
    """
    current: Optional[QWidget] = widget

    while current is not None:
        if bool(current.property("clear_form_ignore")):
            return True
        current = current.parentWidget()

    for widget_kecuali in daftar_kecuali:
        if widget is widget_kecuali:
            return True

        if widget_kecuali.isAncestorOf(widget):
            return True

    return False


def _lineedit_editor_internal(widget: QLineEdit) -> bool:
    """
    Menghindari pemrosesan QLineEdit internal milik QComboBox,
    QSpinBox, QDateEdit, dan turunan QAbstractSpinBox.
    """
    parent = widget.parentWidget()

    while parent is not None:
        if isinstance(parent, (QComboBox, QAbstractSpinBox)):
            return True
        parent = parent.parentWidget()

    return False


def _nilai_spinbox_aman(
    widget: Any,
    nilai_default: Optional[float],
) -> float:
    """Menjaga nilai reset tetap berada di antara minimum dan maksimum."""
    minimum = widget.minimum()
    maximum = widget.maximum()

    if nilai_default is None:
        nilai = 0 if minimum <= 0 <= maximum else minimum
    else:
        nilai = nilai_default

    return max(minimum, min(nilai, maximum))


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
    """
    Membersihkan seluruh input di dalam suatu container secara rekursif.

    Widget yang didukung:
    - QLineEdit
    - QTextEdit dan QPlainTextEdit
    - QComboBox
    - QSpinBox dan QDoubleSpinBox
    - QDateEdit, QTimeEdit, dan QDateTimeEdit
    - QCheckBox dan QRadioButton
    - QTableWidget, QListWidget, dan QTreeWidget secara opsional

    Pengamanan:
    - Input read-only dilewati secara default.
    - Signal diblokir secara default.
    - Widget tertentu dapat dimasukkan ke ``kecualikan``.
    - Widget/container dapat diberi property ``clear_form_ignore=True``.
    - QComboBox dapat diberi property ``clear_form_combo_index``.
    - Spinbox dapat diberi property ``clear_form_value``.

    Contoh:
        reset_form_input_global(
            self,
            kecualikan=[self.txt_no_resi, self.cb_provinsi],
            kosongkan_tabel=True,
            fokus_ke=self.txt_pengirim,
        )

    Return:
        Dictionary statistik jumlah widget yang berhasil direset.
    """
    hasil: Dict[str, int] = {
        "lineedit": 0,
        "textedit": 0,
        "combobox": 0,
        "spinbox": 0,
        "tanggal": 0,
        "centang": 0,
        "tabel": 0,
        "daftar": 0,
    }

    if container_widget is None or not isinstance(container_widget, QWidget):
        return hasil

    daftar_kecuali = tuple(
        widget
        for widget in (kecualikan or ())
        if isinstance(widget, QWidget)
    )

    daftar_widget = [container_widget]
    daftar_widget.extend(container_widget.findChildren(QWidget))

    sudah_diproses = set()

    for widget in daftar_widget:
        identitas = id(widget)

        if identitas in sudah_diproses:
            continue

        sudah_diproses.add(identitas)

        if _widget_dikecualikan(widget, daftar_kecuali):
            continue

        if isinstance(widget, QComboBox):
            with blokir_signal_opsional(widget, blokir_signal):
                property_index = widget.property("clear_form_combo_index")

                try:
                    index_target = (
                        int(property_index)
                        if property_index is not None
                        else int(indeks_combo_default)
                    )
                except (TypeError, ValueError):
                    index_target = 0

                if widget.count() <= 0:
                    widget.setCurrentIndex(-1)
                else:
                    index_target = max(
                        -1,
                        min(index_target, widget.count() - 1),
                    )
                    widget.setCurrentIndex(index_target)

                if widget.isEditable() and kosongkan_combo_editable:
                    widget.clearEditText()

            hasil["combobox"] += 1
            continue

        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            if reset_spinbox:
                with blokir_signal_opsional(widget, blokir_signal):
                    property_value = widget.property("clear_form_value")
                    nilai_target = (
                        property_value
                        if property_value is not None
                        else nilai_spinbox_default
                    )
                    nilai_aman = _nilai_spinbox_aman(
                        widget,
                        nilai_target,
                    )

                    if isinstance(widget, QSpinBox):
                        widget.setValue(int(round(nilai_aman)))
                    else:
                        widget.setValue(float(nilai_aman))

                hasil["spinbox"] += 1

            continue

        if isinstance(widget, (QDateEdit, QTimeEdit, QDateTimeEdit)):
            if lewati_readonly and widget.isReadOnly():
                continue

            if reset_tanggal:
                with blokir_signal_opsional(widget, blokir_signal):
                    if isinstance(widget, QDateEdit):
                        widget.setDate(QDate.currentDate())
                    elif isinstance(widget, QTimeEdit):
                        widget.setTime(QTime.currentTime())
                    else:
                        widget.setDateTime(QDateTime.currentDateTime())

                hasil["tanggal"] += 1

            continue

        if isinstance(widget, QLineEdit):
            if _lineedit_editor_internal(widget):
                continue

            if lewati_readonly and widget.isReadOnly():
                continue

            with blokir_signal_opsional(widget, blokir_signal):
                widget.clear()

            hasil["lineedit"] += 1
            continue

        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            if lewati_readonly and widget.isReadOnly():
                continue

            with blokir_signal_opsional(widget, blokir_signal):
                widget.clear()

            hasil["textedit"] += 1
            continue

        if isinstance(widget, (QCheckBox, QRadioButton)):
            if reset_centang:
                with blokir_signal_opsional(widget, blokir_signal):
                    auto_exclusive = (
                        widget.autoExclusive()
                        if isinstance(widget, QRadioButton)
                        else False
                    )

                    if auto_exclusive:
                        widget.setAutoExclusive(False)

                    widget.setChecked(False)

                    if auto_exclusive:
                        widget.setAutoExclusive(True)

                hasil["centang"] += 1

            continue

        if isinstance(widget, QTableWidget):
            if kosongkan_tabel:
                with blokir_signal_opsional(widget, blokir_signal):
                    widget.setRowCount(0)

                hasil["tabel"] += 1

            continue

        if isinstance(widget, (QListWidget, QTreeWidget)):
            if kosongkan_daftar:
                with blokir_signal_opsional(widget, blokir_signal):
                    widget.clear()

                hasil["daftar"] += 1

    if fokus_ke is not None and isinstance(fokus_ke, QWidget):
        QTimer.singleShot(
            0,
            lambda: fokus_ke.setFocus()
            if fokus_ke.isEnabled()
            else None,
        )

    return hasil
