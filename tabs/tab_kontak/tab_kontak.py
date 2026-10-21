# tabs/tab_kontak/tab_kontak.py
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from utils.ui_metrics import dapatkan_ui_scale
from tabs.tab_kontak.subtab_pengirim import SubTabPengirim
from tabs.tab_kontak.subtab_penerima import SubTabPenerima


class TabKontak(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tema_lokal_signature = None
        self.init_ui()

    def _signature_tema_lokal(self):
        """Identitas tema untuk menghindari penerapan tema berulang saat showEvent."""
        window = self.window()
        tema = getattr(window, "current_theme", "light")
        try:
            scale = round(float(dapatkan_ui_scale()), 4)
        except Exception:
            scale = 1.0
        return tema, scale

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)

        self.tabs_internal = QTabWidget(self)
        # Pakai QTabBar default. Geometry/style mengikuti themes.base
        # dari baseline global TAB_* di utils.ui_metrics.
        self.subtab_pengirim = SubTabPengirim()
        self.subtab_penerima = SubTabPenerima()
        self.tabs_internal.addTab(self.subtab_pengirim, "Pengirim")
        self.tabs_internal.addTab(self.subtab_penerima, "Penerima")

        self.tabs_internal.currentChanged.connect(self._tema_subtab_aktif)

        layout.addWidget(self.tabs_internal)

    def _tema_subtab_aktif(self, _index=None):
        subtab = self.tabs_internal.currentWidget()
        fungsi_tema = getattr(subtab, "sesuaikan_tema_lokal", None) if subtab else None
        if not callable(fungsi_tema):
            return

        subtab.setUpdatesEnabled(False)
        try:
            fungsi_tema()
        finally:
            subtab.setUpdatesEnabled(True)
            subtab.update()

    def sesuaikan_tema_lokal(self):
        """Perbarui tema hanya saat tema atau skala berubah."""
        signature = self._signature_tema_lokal()
        if signature == self._tema_lokal_signature:
            return

        self._tema_subtab_aktif()
        self._tema_lokal_signature = signature

    def refresh_session_ui(self):
        """Teruskan refresh session/cabang ke seluruh subtab terkait."""
        for subtab in (self.subtab_pengirim, self.subtab_penerima):
            refresh = getattr(subtab, "refresh_session_ui", None)
            if callable(refresh):
                refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.sesuaikan_tema_lokal()
