# themes/calendar.py

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import QCalendarWidget, QDateEdit


def terapkan_style_kalender(
    date_edit: QDateEdit,
    is_dark: bool = False,
) -> None:
    """
    Menerapkan tampilan popup kalender standar aplikasi.

    Ketentuan:
    - Locale Indonesia.
    - Minggu tetap merah.
    - Sabtu mengikuti warna hari biasa.
    - Tampilan konsisten pada light dan dark mode.
    - Hanya memengaruhi popup kalender, bukan tampilan input QDateEdit.
    """

    if date_edit is None or not hasattr(date_edit, "calendarWidget"):
        return

    date_edit.setCalendarPopup(True)

    locale_indonesia = QLocale("id_ID")
    date_edit.setLocale(locale_indonesia)

    calendar = date_edit.calendarWidget()
    calendar.setLocale(locale_indonesia)
    calendar.setFirstDayOfWeek(Qt.DayOfWeek.Sunday)
    calendar.setHorizontalHeaderFormat(
        QCalendarWidget.HorizontalHeaderFormat.ShortDayNames
    )
    calendar.setVerticalHeaderFormat(
        QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
    )
    calendar.setNavigationBarVisible(True)
    calendar.setGridVisible(False)

    if is_dark:
        warna_background = "#111827"
        warna_teks = "#e5e7eb"
        warna_minggu = "#f87171"
        warna_border = "#374151"
        warna_hover = "#1f2937"
    else:
        warna_background = "#ffffff"
        warna_teks = "#111827"
        warna_minggu = "#ef4444"
        warna_border = "#cbd5e1"
        warna_hover = "#eff6ff"

    warna_navigasi = "#2563eb"
    warna_terpilih = "#2563eb"

    # Style popup kalender.
    calendar.setStyleSheet(
        f"""
            QCalendarWidget {{
                background-color: {warna_background};
                border: 1px solid {warna_border};
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background-color: {warna_navigasi};
                border: none;
            }}
            QCalendarWidget QToolButton#qt_calendar_prevmonth,
            QCalendarWidget QToolButton#qt_calendar_nextmonth {{
                background-color: transparent;
                border: none;
                padding: 3px;
            }}
            QCalendarWidget QToolButton#qt_calendar_prevmonth:hover,
            QCalendarWidget QToolButton#qt_calendar_nextmonth:hover {{
                background-color: rgba(255, 255, 255, 35);
                border-radius: 4px;
            }}
            QCalendarWidget QToolButton#qt_calendar_monthbutton,
            QCalendarWidget QToolButton#qt_calendar_yearbutton {{
                color: #ffffff;
                background-color: transparent;
                border: none;
                padding: 3px 5px;
                font-weight: 700;
            }}
            QCalendarWidget QToolButton#qt_calendar_monthbutton:hover,
            QCalendarWidget QToolButton#qt_calendar_yearbutton:hover {{
                background-color: rgba(255, 255, 255, 35);
                border-radius: 4px;
            }}
            QCalendarWidget QSpinBox#qt_calendar_yearedit {{
                color: #ffffff;
                background-color: {warna_navigasi};
                border: 1px solid rgba(255, 255, 255, 90);
                selection-background-color: #1d4ed8;
                selection-color: #ffffff;
                font-weight: 700;
            }}
            QCalendarWidget QTableView#qt_calendar_calendarview {{
                color: {warna_teks};
                background-color: {warna_background};
                alternate-background-color: {warna_background};
                border: none;
                outline: none;
                selection-background-color: {warna_terpilih};
                selection-color: #ffffff;
            }}
            QCalendarWidget QTableView#qt_calendar_calendarview::item {{
                border: none;
                padding: 2px;
            }}
            QCalendarWidget QTableView#qt_calendar_calendarview::item:hover {{
                background-color: {warna_hover};
            }}
            QCalendarWidget QTableView#qt_calendar_calendarview::item:selected {{
                color: #ffffff;
                background-color: {warna_terpilih};
            }}
        """
    )

    # Senin sampai Sabtu menggunakan warna normal.
    format_hari_normal = QTextCharFormat()
    format_hari_normal.setForeground(
        QColor(warna_teks)
    )

    for hari in (
        Qt.DayOfWeek.Monday,
        Qt.DayOfWeek.Tuesday,
        Qt.DayOfWeek.Wednesday,
        Qt.DayOfWeek.Thursday,
        Qt.DayOfWeek.Friday,
        Qt.DayOfWeek.Saturday,
    ):
        calendar.setWeekdayTextFormat(
            hari,
            format_hari_normal,
        )

    # Minggu tetap merah.
    format_minggu = QTextCharFormat()
    format_minggu.setForeground(
        QColor(warna_minggu)
    )

    calendar.setWeekdayTextFormat(
        Qt.DayOfWeek.Sunday,
        format_minggu,
    )

    calendar.updateCells()
    calendar.update()
