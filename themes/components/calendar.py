# themes/components/calendar.py
from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import QCalendarWidget, QDateEdit


def terapkan_style_kalender(
        date_edit: QDateEdit,
        is_dark: bool = False,
) -> None:
    if date_edit is None or not hasattr(date_edit, "calendarWidget"):
        return

    date_edit.setCalendarPopup(True)

    locale_indonesia = QLocale("id_ID")
    date_edit.setLocale(locale_indonesia)

    calendar = date_edit.calendarWidget()
    if calendar is None:
        return

    calendar.setLocale(locale_indonesia)

    # Menetapkan hari Minggu sebagai hari pertama di kolom kalender
    calendar.setFirstDayOfWeek(Qt.DayOfWeek.Sunday)

    # Kosongkan QSS custom agar 100% menggunakan style native / pyqtdarktheme
    calendar.setStyleSheet("")

    # Ambil warna teks bawaan palette kalender saat ini (support light/dark mode)
    warna_biasa = calendar.palette().text().color()
    warna_minggu = QColor("#f87171") if is_dark else QColor("#ef4444")

    # Format hari biasa (Senin - Sabtu)
    fmt_biasa = QTextCharFormat()
    fmt_biasa.setForeground(warna_biasa)

    for hari in (
            Qt.DayOfWeek.Monday,
            Qt.DayOfWeek.Tuesday,
            Qt.DayOfWeek.Wednesday,
            Qt.DayOfWeek.Thursday,
            Qt.DayOfWeek.Friday,
            Qt.DayOfWeek.Saturday,
    ):
        calendar.setWeekdayTextFormat(hari, fmt_biasa)

    # Format khusus hari Minggu (merah)
    fmt_minggu = QTextCharFormat()
    fmt_minggu.setForeground(warna_minggu)
    calendar.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, fmt_minggu)

    calendar.updateCells()
    calendar.update()