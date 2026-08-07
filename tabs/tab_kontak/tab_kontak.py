# tabs/tab_kontak/tab_kontak.py
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from tabs.tab_kontak.subtab_pengirim import SubTabPengirim
from tabs.tab_kontak.subtab_penerima import SubTabPenerima


class TabKontak(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)

        self.tabs_internal = QTabWidget(self)
        self.subtab_pengirim = SubTabPengirim()
        self.subtab_penerima = SubTabPenerima()
        self.tabs_internal.addTab(self.subtab_pengirim, "Pengirim")
        self.tabs_internal.addTab(self.subtab_penerima, "Penerima")
        self.tabs_internal.currentChanged.connect(self._tema_subtab_aktif)

        layout.addWidget(self.tabs_internal)
        self.sesuaikan_tema_lokal()

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
        """Perbarui tema dan zoom tabel pada subtab yang sedang terlihat."""
        self._tema_subtab_aktif()

    def showEvent(self, event):
        super().showEvent(event)
        self.sesuaikan_tema_lokal()