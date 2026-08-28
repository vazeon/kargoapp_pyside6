# tabs/tab_armada/tab_armada.py
import traceback
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from tabs.tab_armada.subtab_truk import SubTabTruk
from tabs.tab_armada.subtab_kapal import SubTabKapal
class TabArmada(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sedang_menerapkan_tema = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)

        self.tabs_internal = QTabWidget(self)
        # Pakai QTabBar default. Geometry/style mengikuti themes.base
        # dari baseline global TAB_* di utils.ui_metrics.
        self.subtab_truk = SubTabTruk(self.tabs_internal)
        self.subtab_kapal = SubTabKapal(self.tabs_internal)
        self.tabs_internal.addTab(self.subtab_truk, "Truk")
        self.tabs_internal.addTab(self.subtab_kapal, "Kapal")

        self.tabs_internal.currentChanged.connect(self._tema_subtab_aktif)

        layout.addWidget(self.tabs_internal)
        self.sesuaikan_tema_lokal()

    def _tema_subtab_aktif(self, _index=None):
        """Terapkan tema ke subtab aktif tanpa re-entry."""
        if self._sedang_menerapkan_tema:
            return

        subtab = self.tabs_internal.currentWidget()
        fungsi_tema = getattr(subtab, "sesuaikan_tema_lokal", None) if subtab else None
        if not callable(fungsi_tema):
            return

        self._sedang_menerapkan_tema = True
        try:
            fungsi_tema()
            subtab.update()
        except Exception as exc:
            print(
                f"[Tema] Gagal menerapkan tema pada "
                f"{type(subtab).__name__}: {type(exc).__name__}: {exc}"
            )
            traceback.print_exc()
        finally:
            self._sedang_menerapkan_tema = False

    def sesuaikan_tema_lokal(self):
        self._tema_subtab_aktif()

    def refresh_session_ui(self):
        """Teruskan refresh session/cabang ke subtab Armada."""
        for subtab in (self.subtab_truk, self.subtab_kapal):
            refresh = getattr(subtab, "refresh_session_ui", None)
            if callable(refresh):
                refresh()

    def showEvent(self, event):
        super().showEvent(event)