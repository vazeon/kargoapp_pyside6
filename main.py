# main.py
import os
import sys
import faulthandler
import threading
import time
import traceback
from PySide6.QtCore import QEvent, QLocale, QSettings, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QScroller,
    QTabBar,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from utils.typography import (
    APPLICATION_NAME,
    ORGANIZATION_NAME,
    konfigurasi_font_aplikasi,
)
from utils.ui_metrics import (
    TOP_RIGHT_CONTROL_HEIGHT,
    dapatkan_ui_scale,
)
from utils.ui_scaler import ResponsiveUIScaler

from config import (
    DATA_CLIENT,
    CURRENT_SESSION,
    BRANCH_ACCESS_FULL,
    BRANCH_ACCESS_VIEW,
    aktifkan_cabang_session,
    mode_akses_cabang,
    muat_pengaturan_sistem,
    refresh_akses_cabang_session,
)

from themes.theme_manager import ThemeManager
from themes.palette import get_theme_palette

from login import LoginWindow
from database_manager import init_db
from services.sync_service import AutoSyncController

from tabs.tab_resi import TabResi
from tabs.tab_setting import TabSettingSistem

import services.database_service as db_service
db_service.set_performance_report(
    os.environ.get("KARGO_PERF_LOG", "").strip() == "1"
)


class _LazyTabPage(QWidget):
    """Container ringan yang membuat isi tab hanya saat benar-benar diperlukan."""

    def __init__(self, factory, parent=None):
        super().__init__(parent)
        self._factory = factory
        self._content = None
        self._loading = False
        # Scroll behavior only needs to be configured once for the widgets
        # already created inside this lazy page.
        self._scrolling_configured = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._content_layout = layout

    @property
    def loaded_widget(self):
        return self._content

    @db_service.profile_performance(
        lambda self: f"Tab.open:{getattr(self._factory, '__name__', 'unknown')}"
    )
    def ensure_loaded(self):
        if self._content is not None:
            return self._content
        if self._loading:
            return None

        self._loading = True
        try:
            widget = self._factory()
            self._content = widget
            self._content_layout.addWidget(widget)
            window = self.window()
            register_show_profile = getattr(
                window, "_register_tab_first_show_profile", None
            )
            if callable(register_show_profile):
                register_show_profile(
                    widget,
                    getattr(self._factory, "__name__", "lazy_tab"),
                )
            return widget
        finally:
            self._loading = False

    def terima_data_baru(self, *args, **kwargs):
        widget = self.ensure_loaded()
        if widget is None:
            return None
        return widget.terima_data_baru(*args, **kwargs)

    def load_invoice_by_no(self, *args, **kwargs):
        widget = self.ensure_loaded()
        if widget is None:
            return False
        return widget.load_invoice_by_no(*args, **kwargs)


def _logout_error_is_network(exc: BaseException) -> bool:
    """True bila sign-out gagal hanya karena Supabase sedang tidak terjangkau."""
    seen = set()
    current = exc
    markers = (
        "connecterror", "getaddrinfo failed", "name or service not known",
        "network is unreachable", "connection reset", "connection refused",
        "connection aborted", "winerror 10054", "winerror 10060",
        "errno 11001", "errno 10054", "errno 10060", "timed out",
    )
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        name = type(current).__name__.lower()
        if any(marker in text or marker in name for marker in markers):
            return True
        current = current.__cause__ or current.__context__
    return False


class MainWindow(QMainWindow):
    SETTINGS_ORGANIZATION = ORGANIZATION_NAME
    SETTINGS_APPLICATION = APPLICATION_NAME
    THEME_LIGHT = "light"
    THEME_DARK = "dark"

    @db_service.profile_performance("MainWindow.__init__", threshold=0.05)
    def __init__(self):
        super().__init__()
        self.settings = QSettings(
            self.SETTINGS_ORGANIZATION,
            self.SETTINGS_APPLICATION,
        )
        self.current_theme = self._muat_tema_tersimpan()
        self._sedang_ganti_tema = False
        self._cache_tema_tab = {}
        self._tema_tab_sedang_diterapkan = set()
        self.dialog_setting = None
        self._sedang_sinkron_cabang = False
        self._logout_sedang_berjalan = False
        self._logout_was_developer = False
        self._logout_login_window = None
        self._logout_signout_thread = None
        self._logout_signout_error = None
        self._logout_poll_timer = None

        # Profiling first-visible work is opt-in and only active when requested.
        # It helps distinguish lazy construction from each tab's first showEvent.
        self._tab_first_show_profile_enabled = (
            os.environ.get("KARGO_PERF_LOG", "").strip() == "1"
        )
        self._tab_first_show_profile_labels = {}
        self._tab_first_show_profile_started = set()
        self._tab_first_show_profile_reported = set()

        app = QApplication.instance()
        self._siapkan_tema_aplikasi(app)
        self.init_ui()

        self._ui_scaler = ResponsiveUIScaler(
            self,
            on_scale_changed=self._saat_ui_scale_berubah,
        )
        self._ui_scaler.apply_now()

        self._session_signature_terakhir = self._buat_signature_session()
        self._auto_sync = AutoSyncController(self, interval_ms=15_000)

        # Warm up lazy tabs gradually while the user is idle. QWidget creation
        # must stay on the GUI thread, so this shifts first-open work away from
        # the first click without delaying the initial dashboard or changing
        # the existing lazy-tab architecture.
        self._siapkan_pemanasan_tab_tunda()

    def _muat_tema_tersimpan(self):
        tema = str(
            self.settings.value("theme", self.THEME_LIGHT)
            or self.THEME_LIGHT
        ).strip().lower()
        return tema if tema in {self.THEME_LIGHT, self.THEME_DARK} else self.THEME_LIGHT

    def _siapkan_tema_aplikasi(self, app):
        if app is None:
            return
        if not bool(app.property("_base_style_terpasang")):
            is_dark = self.current_theme == self.THEME_DARK
            try:
                scale = dapatkan_ui_scale()
            except Exception:
                scale = 1.0

            ThemeManager.apply_theme(app, is_dark, scale)

        app.setPalette(get_theme_palette(self.current_theme == self.THEME_DARK))

    def _saat_ui_scale_berubah(self, scale):
        """Sinkronkan stylesheet/theme saat window berpindah screen/density."""
        app = QApplication.instance()
        is_dark = self.current_theme == self.THEME_DARK
        ThemeManager.apply_theme(app, is_dark, scale)

        self._cache_tema_tab.clear()
        if hasattr(self, "tabs"):
            self.apply_theme(force=True)

    @db_service.profile_performance("MainWindow.init_ui", threshold=0.05)
    def init_ui(self):
        # Subfase ini hanya mengukur, tidak mengubah urutan atau perilaku UI.
        with db_service.performance_timer("MainWindow.init_ui.shell", threshold=0.02):
            self._bangun_shell_utama()
        with db_service.performance_timer("MainWindow.init_ui.top_controls", threshold=0.02):
            self._bangun_kontrol_kanan()
        with db_service.performance_timer("MainWindow.init_ui.tabs", threshold=0.02):
            self._bangun_tab_utama()
        with db_service.performance_timer("MainWindow.init_ui.scrolling", threshold=0.02):
            self._konfigurasi_scrolling()
        self.tabs.currentChanged.connect(self.refresh_tab_utama_diklik)
        with db_service.performance_timer("MainWindow.init_ui.theme", threshold=0.02):
            self.apply_theme()

    def _bangun_shell_utama(self):
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.tabs = QTabWidget(self)
        self.tabs_utama = self.tabs
        self.tabs.setObjectName("MainTabs")
        self.custom_tab_bar = QTabBar(self)
        self.custom_tab_bar.setObjectName("MainTabBar")
        self.tabs.setTabBar(self.custom_tab_bar)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.setUsesScrollButtons(True)
        self.main_layout.addWidget(self.tabs)

    def _buat_tombol_top_right(self, text, slot, *, size=None, width=None):
        button = QPushButton(text) if text else QPushButton(self)
        button.setProperty("class", "TopRightButton")

        if size is not None:
            button.setFixedSize(*size)
        if width is not None:
            button.setFixedWidth(width)
            button.setFixedHeight(TOP_RIGHT_CONTROL_HEIGHT)
        button.clicked.connect(slot)
        return button

    def _bangun_kontrol_kanan(self):
        self.container_top_right = QWidget(self)
        self.container_top_right.setObjectName("ContainerTopRight")

        layout = QHBoxLayout(self.container_top_right)
        layout.setContentsMargins(0, 0, 8, 5)
        layout.setSpacing(6)

        self.lbl_info_cabang = QLabel("")
        self.lbl_info_cabang.setObjectName("LabelCabang")
        self.lbl_info_cabang.hide()

        self.cmb_cabang_aktif = QComboBox(self)
        self.cmb_cabang_aktif.setMinimumWidth(100)
        self.cmb_cabang_aktif.setFixedHeight(TOP_RIGHT_CONTROL_HEIGHT)
        self.cmb_cabang_aktif.setToolTip("Ganti cabang operasional tanpa logout")
        self.cmb_cabang_aktif.currentIndexChanged.connect(self._ganti_cabang_aktif)

        self.btn_theme = self._buat_tombol_top_right(
            "",
            self.toggle_theme,
            width=120,
        )
        self.btn_setting = self._buat_tombol_top_right(
            "⛭",
            self.buka_dasbor_pengaturan,
            size=(40, TOP_RIGHT_CONTROL_HEIGHT),
        )
        self.btn_setting.setToolTip("Pengaturan")

        self.btn_refresh_data = self._buat_tombol_top_right(
            "🔄",
            self.refresh_semua_data,
            size=(40, TOP_RIGHT_CONTROL_HEIGHT),
        )
        self.btn_refresh_data.setToolTip("Perbarui data terbaru dari database")

        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        for widget in (
                self.lbl_info_cabang, self.cmb_cabang_aktif,
                self.btn_theme, self.btn_refresh_data, self.btn_setting,
        ):
            layout.addWidget(
                widget,
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )

        self.tabs.setCornerWidget(self.container_top_right, Qt.Corner.TopRightCorner)

    def _bangun_tab_utama(self):
        # Resi adalah tab yang dibangun langsung saat startup. Ukur terpisah
        # dari placeholder lazy tab agar biaya konstruksi terlihat jelas.
        with db_service.performance_timer("MainWindow.construct_tab_resi", threshold=0.02):
            self.tab_resi_widget = TabResi()
        self.tabs.addTab(self.tab_resi_widget, "Data Resi")

        with db_service.performance_timer("MainWindow.construct_lazy_tab_placeholders", threshold=0.02):
            self.tab_buku_gudang = _LazyTabPage(self._buat_tab_buku_gudang, self.tabs)
            self.tabs.addTab(self.tab_buku_gudang, "Buku Gudang")

            self.tab_manifest = _LazyTabPage(self._buat_tab_manifest, self.tabs)
            self.tabs.addTab(self.tab_manifest, "Manifest")

            self.tab_invoice = _LazyTabPage(self._buat_tab_invoice, self.tabs)
            self.tabs.addTab(self.tab_invoice, "Invoice")

            self.tab_kontak = _LazyTabPage(self._buat_tab_kontak, self.tabs)
            self.tabs.addTab(self.tab_kontak, "Kontak")

            self.tab_armada = _LazyTabPage(self._buat_tab_armada, self.tabs)
            self.tabs.addTab(self.tab_armada, "Armada")

    @staticmethod
    def _buat_tab_buku_gudang():
        from tabs.tab_buku_gudang import TabBukuGudang
        return TabBukuGudang()

    @staticmethod
    def _buat_tab_manifest():
        from tabs.tab_manifest import TabManifest
        return TabManifest()

    @staticmethod
    def _buat_tab_invoice():
        from tabs.tab_invoice import TabInvoice
        return TabInvoice()

    @staticmethod
    def _buat_tab_kontak():
        from tabs.tab_kontak.tab_kontak import TabKontak
        return TabKontak()

    @staticmethod
    def _buat_tab_armada():
        from tabs.tab_armada.tab_armada import TabArmada
        return TabArmada()

    _TAB_PREWARM_IDLE_MS = 200
    # Break warm-up into short GUI-thread phases so a single callback does not
    # combine construction, theming and access setup into one long UI pause.
    _TAB_PREWARM_PHASE_GAP_MS = 15
    _TAB_PREWARM_ACTIVITY_EVENTS = frozenset({
        QEvent.Type.MouseButtonPress,
        QEvent.Type.KeyPress,
        QEvent.Type.KeyRelease,
        QEvent.Type.Wheel,
        QEvent.Type.TouchBegin,
        QEvent.Type.TouchUpdate,
        QEvent.Type.TouchEnd,
        QEvent.Type.TabletPress,
        QEvent.Type.TabletMove,
        QEvent.Type.TabletRelease,
        QEvent.Type.DragEnter,
        QEvent.Type.DragMove,
        QEvent.Type.Drop,
        QEvent.Type.ContextMenu,
    })

    def _siapkan_pemanasan_tab_tunda(self):
        self._tab_prewarm_timer = QTimer(self)
        self._tab_prewarm_timer.setSingleShot(True)
        self._tab_prewarm_timer.timeout.connect(self._prewarm_next_lazy_tab)
        self._tab_prewarm_attempted = set()
        self._tab_prewarm_filter_installed = False
        self._tab_prewarm_current_page = None
        self._tab_prewarm_stage = None
        self._tab_prewarm_work_seconds = 0.0

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._tab_prewarm_filter_installed = True

        # Start after the main window construction. User activity continually
        # resets this timer, so warm-up yields to normal interaction.
        self._jadwalkan_pemanasan_tab_tunda()

    def _jadwalkan_pemanasan_tab_tunda(self, delay_ms=None):
        timer = getattr(self, "_tab_prewarm_timer", None)
        if timer is None or getattr(self, "_logout_sedang_berjalan", False):
            return
        if delay_ms is None:
            delay_ms = self._TAB_PREWARM_IDLE_MS
        timer.start(max(1, int(delay_ms)))

    def _register_tab_first_show_profile(self, root_widget, factory_name):
        """Profile the first visible event for custom tab widgets only.

        QTabWidget.currentChanged measures the handler, but it may not include
        work performed by a tab's first showEvent. This opt-in profiler records
        that missing portion without changing the event flow.
        """
        if not self._tab_first_show_profile_enabled or root_widget is None:
            return

        candidates = [root_widget]
        try:
            candidates.extend(root_widget.findChildren(QWidget))
        except RuntimeError:
            return

        seen_objects = set()
        for candidate in candidates:
            candidate_id = id(candidate)
            if candidate_id in seen_objects:
                continue
            seen_objects.add(candidate_id)

            candidate_type = type(candidate)
            module_name = getattr(candidate_type, "__module__", "")
            # Only track tab classes that define their own showEvent; this
            # avoids producing one PERF line for each ordinary input/control.
            if (
                not module_name.startswith("tabs.")
                or "showEvent" not in getattr(candidate_type, "__dict__", {})
            ):
                continue

            if candidate is root_widget:
                label = str(factory_name or type(candidate).__name__)
            else:
                label = f"{factory_name}.{type(candidate).__name__}"

            self._tab_first_show_profile_labels[candidate_id] = label
            try:
                candidate.installEventFilter(self)
            except RuntimeError:
                self._tab_first_show_profile_labels.pop(candidate_id, None)

    def _laporkan_tab_first_show_profile(self, object_id, label, started_at):
        if object_id in self._tab_first_show_profile_reported:
            return
        self._tab_first_show_profile_reported.add(object_id)
        elapsed = max(0.0, time.perf_counter() - started_at)
        print(
            f"[PERF] UI.tab_first_show.{label} | {elapsed:.4f} s",
            flush=True,
        )

    def eventFilter(self, watched, event):
        # Track only genuine user interaction. Do not consume the event or
        # alter normal QWidget event handling.
        timer = getattr(self, "_tab_prewarm_timer", None)
        if (
            timer is not None
            and timer.isActive()
            and event.type() in self._TAB_PREWARM_ACTIVITY_EVENTS
        ):
            timer.start(self._TAB_PREWARM_IDLE_MS)

        # QEvent.Show is observed before the widget's showEvent override runs.
        # A zero-delay callback reports after synchronous show handling returns.
        if (
            self._tab_first_show_profile_enabled
            and event.type() == QEvent.Type.Show
        ):
            object_id = id(watched)
            label = self._tab_first_show_profile_labels.get(object_id)
            if (
                label is not None
                and object_id not in self._tab_first_show_profile_started
            ):
                self._tab_first_show_profile_started.add(object_id)
                started_at = time.perf_counter()
                QTimer.singleShot(
                    0,
                    lambda oid=object_id, name=label, start=started_at: (
                        self._laporkan_tab_first_show_profile(oid, name, start)
                    ),
                )

        return super().eventFilter(watched, event)

    def _prewarm_next_lazy_tab(self):
        if getattr(self, "_logout_sedang_berjalan", False):
            self._hentikan_pemanasan_tab_tunda()
            return

        # Avoid doing hidden-tab work while this window is not the active UI.
        if not self.isVisible():
            self._jadwalkan_pemanasan_tab_tunda(750)
            return

        pages = (
            self.tab_buku_gudang,
            self.tab_manifest,
            self.tab_invoice,
            self.tab_kontak,
            self.tab_armada,
        )

        page = getattr(self, "_tab_prewarm_current_page", None)
        stage = getattr(self, "_tab_prewarm_stage", None)
        if page is None or stage is None:
            page = next(
                (
                    candidate for candidate in pages
                    if candidate.loaded_widget is None
                    and id(candidate) not in self._tab_prewarm_attempted
                ),
                None,
            )
            if page is None:
                self._hentikan_pemanasan_tab_tunda()
                return

            # Mark before construction so failures cannot create a timer loop.
            # A failed tab remains loadable on demand when the user selects it.
            self._tab_prewarm_attempted.add(id(page))
            self._tab_prewarm_current_page = page
            self._tab_prewarm_stage = "load"
            self._tab_prewarm_work_seconds = 0.0
            stage = "load"

        phase_started = time.perf_counter()
        next_stage = None
        completed_page = False
        try:
            if stage == "load":
                with db_service.performance_timer(
                    "UI.tab_prewarm.ensure_loaded", threshold=0.001
                ):
                    widget = page.ensure_loaded()

                if widget is not None and not page._scrolling_configured:
                    with db_service.performance_timer(
                        "UI.tab_prewarm.configure_scrolling", threshold=0.001
                    ):
                        self._konfigurasi_scrolling_widget(widget)
                    page._scrolling_configured = True

                next_stage = "theme"

            elif stage == "theme":
                widget = page.loaded_widget
                # If the user opened this tab between phases, the regular tab
                # activation path has already applied the current theme.
                if widget is not None and self.tabs.currentWidget() is not page:
                    with db_service.performance_timer(
                        "UI.tab_prewarm.apply_theme", threshold=0.001
                    ):
                        self._terapkan_tema_lokal(widget)
                next_stage = "access"

            elif stage == "access":
                widget = page.loaded_widget
                # Access is checked by normal activation when this page is
                # already visible; do not repeat the same work here.
                if widget is not None and self.tabs.currentWidget() is not page:
                    with db_service.performance_timer(
                        "UI.tab_prewarm.apply_access", threshold=0.001
                    ):
                        self._terapkan_mode_akses_widget(widget)
                completed_page = True

            else:
                # Recover safely if an unexpected stage value is present.
                completed_page = True

        except Exception as error:
            self._tab_prewarm_work_seconds += max(
                0.0, time.perf_counter() - phase_started
            )
            print(
                "[TabWarmup] Pemanasan tab ditunda/gagal untuk "
                f"{getattr(page._factory, '__name__', 'unknown')}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            traceback.print_exc()
            # Do not keep retrying a failed constructor indefinitely.
            self._tab_prewarm_current_page = None
            self._tab_prewarm_stage = None
            self._tab_prewarm_work_seconds = 0.0
            remaining = any(
                candidate.loaded_widget is None
                and id(candidate) not in self._tab_prewarm_attempted
                for candidate in pages
            )
            if remaining:
                self._jadwalkan_pemanasan_tab_tunda(self._TAB_PREWARM_IDLE_MS)
            else:
                self._hentikan_pemanasan_tab_tunda()
            return

        self._tab_prewarm_work_seconds += max(
            0.0, time.perf_counter() - phase_started
        )

        if completed_page:
            if self._tab_first_show_profile_enabled:
                print(
                    "[PERF] UI.tab_prewarm.total | "
                    f"{self._tab_prewarm_work_seconds:.4f} s",
                    flush=True,
                )
            self._tab_prewarm_current_page = None
            self._tab_prewarm_stage = None
            self._tab_prewarm_work_seconds = 0.0

            remaining = any(
                candidate.loaded_widget is None
                and id(candidate) not in self._tab_prewarm_attempted
                for candidate in pages
            )
            if remaining:
                # Pause between separate tabs; each tab's phases are split
                # so input events can be handled between construction/theme/access.
                self._jadwalkan_pemanasan_tab_tunda(self._TAB_PREWARM_IDLE_MS)
            else:
                self._hentikan_pemanasan_tab_tunda()
            return

        self._tab_prewarm_stage = next_stage
        # Yield the event loop between stages. If the user interacts during
        # this gap, eventFilter extends the timer to the normal idle interval.
        self._jadwalkan_pemanasan_tab_tunda(self._TAB_PREWARM_PHASE_GAP_MS)

    def _hentikan_pemanasan_tab_tunda(self):
        timer = getattr(self, "_tab_prewarm_timer", None)
        if timer is not None:
            timer.stop()
        self._tab_prewarm_current_page = None
        self._tab_prewarm_stage = None
        self._tab_prewarm_work_seconds = 0.0

        if getattr(self, "_tab_prewarm_filter_installed", False):
            app = QApplication.instance()
            if app is not None:
                try:
                    app.removeEventFilter(self)
                except RuntimeError:
                    pass
            self._tab_prewarm_filter_installed = False

    @staticmethod
    def _konten_tab(tab_widget, *, muat=False):
        if isinstance(tab_widget, _LazyTabPage):
            return tab_widget.ensure_loaded() if muat else tab_widget.loaded_widget
        return tab_widget

    def _konfigurasi_scrolling(self):
        self._touch_scroll_aktif = False
        self._viewport_scroller = []
        self._konfigurasi_scrolling_widget(self)

    def _konfigurasi_scrolling_widget(self, root):
        if root is None:
            return

        tables = root.findChildren(QTableWidget)
        for table in tables:
            table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        if not self._touch_scroll_aktif:
            return

        for widget in (*root.findChildren(QScrollArea), *tables):
            viewport = widget.viewport()
            QScroller.grabGesture(
                viewport,
                QScroller.ScrollerGestureType.LeftMouseButtonGesture,
            )
            self._viewport_scroller.append(viewport)

    def _signature_tema_tab(self, tab_widget):
        if tab_widget is None:
            return None

        return (
            self.current_theme,
            round(dapatkan_ui_scale(), 4),
        )

    def _terapkan_tema_lokal(
        self,
        tab_widget,
        force=False,
    ):
        if tab_widget is None:
            return

        fungsi_tema = getattr(
            tab_widget,
            "sesuaikan_tema_lokal",
            None,
        )

        if not callable(fungsi_tema):
            return

        signature = self._signature_tema_tab(
            tab_widget
        )
        cache_key = id(tab_widget)

        if (
            not force
            and self._cache_tema_tab.get(cache_key)
            == signature
        ):
            return

        if cache_key in self._tema_tab_sedang_diterapkan:
            return

        self._tema_tab_sedang_diterapkan.add(cache_key)

        try:
            tab_widget.setUpdatesEnabled(False)

            try:
                try:
                    scale = dapatkan_ui_scale()
                except Exception:
                    scale = 1.0

                with db_service.performance_timer(
                    f"UI.theme.local_apply_widget_theme.{type(tab_widget).__name__}",
                    threshold=0.01,
                ):
                    ThemeManager.apply_widget_theme(
                        tab_widget,
                        self.current_theme == self.THEME_DARK,
                        scale,
                    )

                with db_service.performance_timer(
                    f"UI.theme.local_tab_callback.{type(tab_widget).__name__}",
                    threshold=0.01,
                ):
                    fungsi_tema()

                self._cache_tema_tab[cache_key] = signature

            except Exception as error:
                print(
                    "[Tema] Gagal menerapkan tema pada "
                    f"{tab_widget.__class__.__name__}: "
                    f"{type(error).__name__}: {error}"
                )
                traceback.print_exc()

            finally:
                tab_widget.setUpdatesEnabled(True)
                tab_widget.update()

        except RuntimeError:
            self._cache_tema_tab.pop(cache_key, None)

        finally:
            self._tema_tab_sedang_diterapkan.discard(cache_key)

    @db_service.profile_performance("UI.tab_activation", threshold=0.001)
    def refresh_tab_utama_diklik(self, index):
        if index < 0 or index >= self.tabs.count():
            return

        page = self.tabs.widget(index)
        with db_service.performance_timer(
            "UI.tab_activation.ensure_loaded", threshold=0.01
        ):
            tab_aktif = self._konten_tab(page, muat=True)
        if tab_aktif is None:
            return

        if isinstance(page, _LazyTabPage) and not page._scrolling_configured:
            # Scroll mode setup was being repeated on every visit to every
            # lazy tab. Configure the widgets present at initial construction
            # once; normal data refresh and tab callbacks remain unchanged.
            with db_service.performance_timer(
                "UI.tab_activation.configure_scrolling", threshold=0.01
            ):
                self._konfigurasi_scrolling_widget(tab_aktif)
            page._scrolling_configured = True

        with db_service.performance_timer(
            f"UI.tab_activation.apply_theme.{type(tab_aktif).__name__}",
            threshold=0.01,
        ):
            self._terapkan_tema_lokal(tab_aktif)
        with db_service.performance_timer(
            "UI.tab_activation.apply_access", threshold=0.01
        ):
            self._terapkan_mode_akses_widget(tab_aktif)

        # Mulai hitung idle setelah aktivasi selesai, bukan sejak mouse press.
        # Pemanasan berikutnya hanya berjalan jika pengguna benar-benar berhenti
        # berinteraksi selama interval singkat ini.
        self._jadwalkan_pemanasan_tab_tunda()

    @db_service.profile_performance("UI.refresh_all_data", threshold=0.05)
    def refresh_semua_data(self):
        for widget in self._iter_tab_utama():
            try:
                fungsi_refresh = getattr(widget, "refresh_data", None)
                if callable(fungsi_refresh):
                    fungsi_refresh()
                else:
                    self._refresh_widget_session(widget)
            except Exception as error:
                print(
                    "[Refresh] Gagal memperbarui "
                    f"{widget.__class__.__name__}: "
                    f"{type(error).__name__}: {error}"
                )
                traceback.print_exc()

    @staticmethod
    def _panggil_opsional(widget, nama_method):
        fungsi = getattr(widget, nama_method, None)
        if callable(fungsi):
            fungsi()

    @staticmethod
    def _buat_signature_session():
        return (
            str(CURRENT_SESSION.get("db_name", "") or "").strip(),
            str(CURRENT_SESSION.get("kode_cabang", "") or "").strip().upper(),
            str(
                CURRENT_SESSION.get("id_user")
                or CURRENT_SESSION.get("username")
                or ""
            ).strip().upper(),
        )

    def _iter_tab_utama(self):
        hasil = []
        for index in range(self.tabs.count()):
            widget = self._konten_tab(self.tabs.widget(index), muat=False)
            if widget is not None:
                hasil.append(widget)
        return tuple(hasil)

    def _refresh_widget_session(self, widget):
        refresh_session = getattr(widget, "refresh_session_ui", None)
        if callable(refresh_session):
            refresh_session()
            return
        if widget is self.tab_resi_widget:
            self._panggil_opsional(widget, "auto_refresh_histori")
        elif widget.__class__.__name__ == "TabManifest":
            self._panggil_opsional(widget, "setup_autocomplete_truk")

    @staticmethod
    def _normalisasi_label_akses(mode: str) -> str:
        return "FULL" if str(mode or "").strip().upper() == BRANCH_ACCESS_FULL else "VIEW ONLY"

    @staticmethod
    def _button_write_related(widget) -> bool:
        # Aksi sesi seperti LOGOUT harus selalu aktif, termasuk pada mode VIEW ONLY.
        if bool(widget.property("access_safe_action")):
            return False
        text = " ".join(str(widget.text() or "").upper().split())
        if not text:
            return False
        read_markers = (
            "CARI", "SEARCH", "REFRESH", "MUAT", "DETAIL", "LIHAT",
            "CETAK", "PRINT", "PREVIEW", "EXPORT", "PDF", "CSV",
            "PILIH", "BUKA", "TUTUP", "KEMBALI", "CLEAR", "BERSIHKAN",
        )
        if any(marker in text for marker in read_markers) and not any(
            marker in text for marker in ("SIMPAN", "UPDATE", "UBAH", "EDIT", "HAPUS", "DELETE", "TAMBAH", "BUAT", "POSTING")
        ):
            return False
        write_markers = (
            "SIMPAN", "SAVE", "TAMBAH", "ADD", "EDIT", "UBAH", "UPDATE",
            "HAPUS", "DELETE", "BUAT", "CREATE", "POSTING", "PROSES",
            "SELESAI", "NONAKTIF", "AKTIFKAN", "RESET", "SUBMIT",
            "KIRIM", "TERIMA", "TAGIH", "LUNAS", "MANIFEST BARU",
        )
        return any(marker in text for marker in write_markers)

    def _terapkan_mode_akses_widget(self, widget):
        """Terapkan mode FULL/VIEW ONLY tanpa mematikan kontrol baca/filter."""
        if widget is None:
            return

        mode = str(
            CURRENT_SESSION.get("active_access_mode") or mode_akses_cabang()
        ).strip().upper()
        view_only = mode == BRANCH_ACCESS_VIEW

        # Cache the child list once. The old implementation traversed the
        # complete widget tree again before applying table/button restrictions.
        children = widget.findChildren(QWidget)

        # Modul yang memahami struktur editornya sendiri mendapat prioritas.
        targets = (widget, *children)
        for target in targets:
            handler = getattr(target, "set_branch_access_mode", None)
            if not callable(handler):
                continue
            try:
                handler(mode)
            except Exception as exc:
                print(
                    f"[BranchAccess] Gagal menerapkan mode pada "
                    f"{target.__class__.__name__}: {type(exc).__name__}: {exc}"
                )

        for child in children:
            try:
                if isinstance(child, QTableWidget):
                    if not hasattr(child, "_branch_access_original_edit_triggers"):
                        child._branch_access_original_edit_triggers = child.editTriggers()
                    if view_only:
                        child.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                    else:
                        child.setEditTriggers(child._branch_access_original_edit_triggers)
                    continue

                if isinstance(child, QPushButton) and self._button_write_related(child):
                    if not hasattr(child, "_branch_access_original_enabled"):
                        child._branch_access_original_enabled = child.isEnabled()
                    child.setEnabled(
                        False if view_only else bool(child._branch_access_original_enabled)
                    )
            except (RuntimeError, AttributeError):
                continue

    def _sinkronkan_pemilih_cabang(self):
        branches = CURRENT_SESSION.get("allowed_branches") or []
        current = str(CURRENT_SESSION.get("kode_cabang") or "PUSAT").strip().upper()

        self._sedang_sinkron_cabang = True
        self.cmb_cabang_aktif.blockSignals(True)
        try:
            self.cmb_cabang_aktif.clear()
            for item in branches:
                kode = str(item.get("kode_cabang") or "").strip().upper()
                if not kode:
                    continue
                # Label combobox dibuat sederhana: hanya nama kota/cabang.
                # Kode cabang dan status akses tetap disimpan pada data item
                # sehingga logika session tidak berubah.
                nama_cabang = {
                    "SBY": "SURABAYA",
                    "JKT": "JAKARTA",
                }.get(kode)
                if not nama_cabang:
                    nama_cabang = str(item.get("nama_cabang") or kode).strip()
                    for suffix in (" (PUSAT)", " (CABANG)", " PUSAT", " CABANG"):
                        if nama_cabang.upper().endswith(suffix):
                            nama_cabang = nama_cabang[:-len(suffix)].strip()
                            break
                self.cmb_cabang_aktif.addItem(nama_cabang, kode)

            index = self.cmb_cabang_aktif.findData(current)
            if index < 0 and self.cmb_cabang_aktif.count() > 0:
                index = 0
            if index >= 0:
                self.cmb_cabang_aktif.setCurrentIndex(index)
            self.cmb_cabang_aktif.setEnabled(self.cmb_cabang_aktif.count() > 1)
        finally:
            self.cmb_cabang_aktif.blockSignals(False)
            self._sedang_sinkron_cabang = False

    def _ganti_cabang_aktif(self, _index=None):
        if self._sedang_sinkron_cabang:
            return
        kode = str(self.cmb_cabang_aktif.currentData() or "").strip().upper()
        current = str(CURRENT_SESSION.get("kode_cabang") or "").strip().upper()
        if not kode or kode == current:
            self.update_session_ui()
            return

        if not aktifkan_cabang_session(kode):
            self._sinkronkan_pemilih_cabang()
            return

        # aktifkan_cabang_session sudah memvalidasi branch scope dari sumber
        # otoritatif. Jangan mengulang query yang sama saat menyegarkan UI.
        self.update_session_ui(refresh_branch_access=False)

    @db_service.profile_performance("UI.update_session", threshold=0.05)
    def update_session_ui(self, *, refresh_branch_access=True):
        if refresh_branch_access:
            with db_service.performance_timer(
                "SessionUI.refresh_branch_access", threshold=0.02
            ):
                refresh_akses_cabang_session()
        with db_service.performance_timer(
            "SessionUI.sync_branch_selector", threshold=0.02
        ):
            self._sinkronkan_pemilih_cabang()

        nama_perusahaan = DATA_CLIENT.get(
            'nama_perusahaan',
            'PT EKSPEDISI KARGO',
        )
        nama_cabang = CURRENT_SESSION.get('nama_cabang', 'PUSAT')
        self.setWindowTitle(
            f"{nama_perusahaan} - {nama_cabang} - PANEL ADMIN v1.0"
        )
        # Status akses tidak ditampilkan di header. Mode FULL/VIEW ONLY
        # tetap dipakai secara internal untuk mengunci/membuka operasi tulis.
        self.lbl_info_cabang.clear()
        self.lbl_info_cabang.setToolTip("")

        role_aktif = str(CURRENT_SESSION.get('role', '')).strip().upper()
        self.btn_setting.setToolTip(
            "Pengaturan Sistem (Super Admin / Owner)"
            if role_aktif in {"SUPER_ADMIN", "OWNER"}
            else "Pengaturan Sistem (View-Only)"
        )

        self._cache_tema_tab.clear()

        signature_baru = self._buat_signature_session()
        session_berubah = (
            signature_baru
            != getattr(self, "_session_signature_terakhir", None)
        )

        tab_aktif = self._konten_tab(self.tabs.currentWidget(), muat=True)
        widgets_refresh = (
            self._iter_tab_utama()
            if session_berubah
            else ((tab_aktif,) if tab_aktif is not None else ())
        )

        for widget in widgets_refresh:
            try:
                with db_service.performance_timer(
                    f"SessionUI.refresh_widget:{widget.__class__.__name__}",
                    threshold=0.02,
                ):
                    self._refresh_widget_session(widget)
            except Exception as error:
                print(
                    "[Sesi] Gagal menyegarkan "
                    f"{widget.__class__.__name__}: "
                    f"{type(error).__name__}: {error}"
                )
                traceback.print_exc()

        self._session_signature_terakhir = signature_baru

        if tab_aktif is not None:
            with db_service.performance_timer(
                "SessionUI.apply_active_tab_theme", threshold=0.02
            ):
                self._terapkan_tema_lokal(tab_aktif, force=True)
            with db_service.performance_timer(
                "SessionUI.apply_active_tab_access", threshold=0.02
            ):
                self._terapkan_mode_akses_widget(tab_aktif)
        with db_service.performance_timer(
            "SessionUI.apply_access_all_tabs", threshold=0.02
        ):
            for widget in self._iter_tab_utama():
                self._terapkan_mode_akses_widget(widget)

    def _terapkan_titlebar_native_windows(self):
        """Sinkronkan warna title bar Windows dengan tema aplikasi Qt."""
        if os.name != "nt":
            return

        try:
            import ctypes
            from ctypes import wintypes

            hwnd = wintypes.HWND(int(self.winId()))
            dark_mode = ctypes.c_int(
                1 if self.current_theme == self.THEME_DARK else 0
            )

            dwmapi = ctypes.WinDLL("dwmapi")
            set_window_attribute = dwmapi.DwmSetWindowAttribute
            set_window_attribute.argtypes = (
                wintypes.HWND,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
            )
            set_window_attribute.restype = ctypes.c_long

            # Attribute 20 digunakan pada Windows modern. Attribute 19 adalah
            # fallback untuk beberapa build Windows 10 yang lebih lama.
            for attribute in (20, 19):
                result = set_window_attribute(
                    hwnd,
                    attribute,
                    ctypes.byref(dark_mode),
                    ctypes.sizeof(dark_mode),
                )
                if result == 0:  # S_OK
                    return
        except (AttributeError, OSError, TypeError, ValueError):
            # Pengaturan title bar hanya kosmetik; jangan sampai mengganggu UI.
            return

    @db_service.profile_performance("UI.toggle_theme", threshold=0.05)
    def toggle_theme(self):
        if self._sedang_ganti_tema:
            return

        self._sedang_ganti_tema = True

        try:
            self.current_theme = (
                self.THEME_LIGHT
                if self.current_theme == self.THEME_DARK
                else self.THEME_DARK
            )

            with db_service.performance_timer(
                "UI.theme.persist_settings", threshold=0.01
            ):
                self.settings.setValue(
                    "theme",
                    self.current_theme,
                )
                self.settings.sync()

            with db_service.performance_timer(
                "UI.theme.apply_theme_call", threshold=0.01
            ):
                self.apply_theme(force=True)

            # Theme changes only affect colors/stylesheets. UI scaling is
            # independent and should run only when the scale/display settings
            # change; reapplying it here needlessly recalculates widget geometry.

        finally:
            self._sedang_ganti_tema = False

    @db_service.profile_performance("UI.apply_theme", threshold=0.05)
    def apply_theme(self, force=False):
        is_dark = self.current_theme == self.THEME_DARK

        with db_service.performance_timer(
            "UI.theme.apply_shell", threshold=0.01
        ):
            self._terapkan_tema_shell(is_dark)

        with db_service.performance_timer(
            "UI.theme.resolve_active_tab", threshold=0.01
        ):
            tab_aktif = self._konten_tab(self.tabs.currentWidget(), muat=True)

        if tab_aktif is not None:
            with db_service.performance_timer(
                f"UI.theme.active_tab_local.{type(tab_aktif).__name__}",
                threshold=0.01,
            ):
                self._terapkan_tema_lokal(tab_aktif, force=force)

    def _terapkan_tema_shell(self, is_dark):
        app = QApplication.instance()

        try:
            scale = dapatkan_ui_scale()
        except Exception:
            scale = 1.0

        with db_service.performance_timer(
            "UI.theme.manager_apply", threshold=0.01
        ):
            ThemeManager.apply_theme(app, is_dark, scale)

        if app is not None:
            with db_service.performance_timer(
                "UI.theme.application_palette", threshold=0.01
            ):
                app.setPalette(get_theme_palette(is_dark))

        with db_service.performance_timer(
            "UI.theme.shell_stylesheets", threshold=0.01
        ):
            ThemeManager.apply_shell_theme(
                self.tabs,
                self.custom_tab_bar,
                self.container_top_right,
                is_dark,
                scale,
            )

        self.btn_theme.setText("Mode Terang" if is_dark else "Mode Gelap")

        # Title bar adalah area native Windows, terpisah dari stylesheet Qt.
        # Terapkan setelah window handle siap; fungsi membaca tema terbaru.
        QTimer.singleShot(0, self._terapkan_titlebar_native_windows)

    def buka_dasbor_pengaturan(self):
        if self._aktifkan_dialog_setting_lama():
            return

        self.dialog_setting = QDialog(self)
        self.dialog_setting.setWindowTitle("PENGATURAN")
        self.dialog_setting.setMinimumSize(800, 600)
        layout = QVBoxLayout(self.dialog_setting)
        with db_service.performance_timer("UI.settings_dialog_construct", threshold=0.05):
            widget_setting = TabSettingSistem(self.dialog_setting)
        layout.addWidget(widget_setting)

        try:
            scale = dapatkan_ui_scale()
        except Exception:
            scale = 1.0
        ThemeManager.apply_widget_theme(
            self.dialog_setting,
            self.current_theme == self.THEME_DARK,
            scale,
        )

        # TabSettingSistem menangani mode read-only berdasarkan role melalui
        # validasi hak akses internal. Tidak ada overlay/warning yang menutupi
        # halaman Settings untuk user non-SUPER.
        try:
            self.dialog_setting.exec()
        finally:
            dialog = self.dialog_setting
            self.dialog_setting = None
            if dialog is not None:
                dialog.deleteLater()

    def _aktifkan_dialog_setting_lama(self):
        dialog = getattr(self, "dialog_setting", None)
        if dialog is None:
            return False
        try:
            if dialog.isVisible():
                dialog.raise_()
                dialog.activateWindow()
                return True
        except RuntimeError:
            self.dialog_setting = None
        return False

    def logout_session(self):
        """Logout eksplisit dengan urutan cleanup yang aman dan non-blocking."""
        if getattr(self, "_logout_sedang_berjalan", False):
            return

        # QMessageBox default mewarisi stylesheet global aplikasi.
        # Pada kombinasi theme/palette tertentu, teks tombol Yes/No bisa
        # menjadi putih di atas background terang sehingga terlihat disabled.
        # Gunakan style lokal hanya untuk dialog konfirmasi ini agar selalu terbaca.
        box = QMessageBox(self)
        box.setWindowTitle("Konfirmasi Logout")
        box.setText("Keluar dari akun saat ini?")
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)

        if self.current_theme == self.THEME_DARK:
            box.setStyleSheet("""
                QMessageBox {
                    background: #2b2b2b;
                }
                QMessageBox QLabel {
                    color: #f1f1f1;
                }
                QMessageBox QPushButton {
                    min-width: 72px;
                    min-height: 28px;
                    padding: 4px 14px;
                    color: #f1f1f1;
                    background: #3a3a3a;
                    border: 1px solid #666666;
                    border-radius: 4px;
                }
                QMessageBox QPushButton:hover {
                    background: #4a4a4a;
                }
            """)
        else:
            box.setStyleSheet("""
                QMessageBox {
                    background: #ffffff;
                }
                QMessageBox QLabel {
                    color: #1f2937;
                }
                QMessageBox QPushButton {
                    min-width: 72px;
                    min-height: 28px;
                    padding: 4px 14px;
                    color: #1f2937;
                    background: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 4px;
                }
                QMessageBox QPushButton:hover {
                    background: #f1f5f9;
                }
            """)

        konfirmasi = box.exec()
        if konfirmasi != QMessageBox.StandardButton.Yes:
            return

        self._logout_sedang_berjalan = True
        self._hentikan_pemanasan_tab_tunda()
        self._logout_was_developer = bool(CURRENT_SESSION.get("is_developer"))
        self._logout_signout_thread = None
        self._logout_signout_error = None
        self._logout_login_window = None

        try:
            from session_store import clear_last_login

            # Credential auto-login dihapus segera setelah user menekan Logout.
            clear_last_login()

            # Hentikan scheduling sync, tetapi JANGAN reset session atau sign-out
            # sebelum worker yang sedang aktif benar-benar selesai. Ini mencegah
            # worker lama memakai DB/session milik akun baru.
            auto_sync = getattr(self, "_auto_sync", None)
            if auto_sync is not None:
                auto_sync.stop(wait=False)

            dialog = getattr(self, "dialog_setting", None)
            if dialog is not None:
                try:
                    dialog.close()
                except RuntimeError:
                    pass
                self.dialog_setting = None

            self.hide()

            app = QApplication.instance()
            if app is None:
                self._logout_sedang_berjalan = False
                return

            show_login = getattr(app, "_show_login_window", None)
            if not callable(show_login):
                self._logout_sedang_berjalan = False
                return

            login_window = show_login(show=True)
            self._logout_login_window = login_window
            set_external_busy = getattr(login_window, "set_external_busy", None)
            if callable(set_external_busy):
                set_external_busy(True)

            self._logout_poll_timer = QTimer(self)
            self._logout_poll_timer.setInterval(50)
            self._logout_poll_timer.timeout.connect(self._proses_logout_async)
            self._logout_poll_timer.start()
            self._proses_logout_async()
        except Exception as exc:
            self._logout_sedang_berjalan = False
            print(
                f"[LOGOUT] Gagal memulai logout bersih: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

    def _proses_logout_async(self):
        """Jalankan cleanup logout tahap demi tahap lewat event loop GUI."""
        if not getattr(self, "_logout_sedang_berjalan", False):
            return

        auto_sync = getattr(self, "_auto_sync", None)
        if auto_sync is not None and auto_sync.is_running():
            return

        # DEV_SUPER tidak memiliki sesi Supabase. Jalur logout developer hanya
        # membersihkan state lokal dan tidak menjalankan worker sign-out online.
        thread = getattr(self, "_logout_signout_thread", None)
        if thread is None and not bool(getattr(self, "_logout_was_developer", False)):
            thread = threading.Thread(
                target=self._logout_signout_worker,
                name="KargoLogoutWorker",
                daemon=True,
            )
            self._logout_signout_thread = thread
            thread.start()
            return

        if thread is not None and thread.is_alive():
            return

        timer = getattr(self, "_logout_poll_timer", None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        self._logout_poll_timer = None

        error = getattr(self, "_logout_signout_error", None)
        if error is not None and not _logout_error_is_network(error):
            print(
                f"[LOGOUT] Supabase sign-out tidak sempurna: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

        # Logout online tetap menyelesaikan sign-out dahulu. Untuk DEV_SUPER,
        # tidak ada Auth Supabase yang disentuh; hanya state lokal dibersihkan.
        try:
            from config import reset_current_session
            reset_current_session()
        except Exception as exc:
            print(
                f"[LOGOUT] Gagal reset CURRENT_SESSION: {type(exc).__name__}: {exc}",
                flush=True,
            )

        app = QApplication.instance()
        window_holder = getattr(app, "_window_holder", None) if app is not None else None
        if isinstance(window_holder, dict):
            window_holder["main"] = None

        login_window = getattr(self, "_logout_login_window", None)
        if login_window is not None:
            try:
                set_external_busy = getattr(login_window, "set_external_busy", None)
                if callable(set_external_busy):
                    set_external_busy(False)
                login_window.txt_pwd.clear()
                login_window.txt_user.clear()
                login_window.txt_user.setFocus()
                login_window.raise_()
                login_window.activateWindow()
            except RuntimeError:
                pass

        scaler = getattr(self, "_ui_scaler", None)
        if scaler is not None:
            try:
                scaler.shutdown()
            except Exception:
                pass

        self._logout_login_window = None
        self._logout_signout_thread = None
        self._logout_signout_error = None
        self._logout_was_developer = False
        self._logout_sedang_berjalan = False
        self.deleteLater()

    def _logout_signout_worker(self):
        """Lakukan sign-out Supabase di thread background."""
        if bool(getattr(self, "_logout_was_developer", False)) or bool(
            CURRENT_SESSION.get("is_developer")
        ):
            return
        try:
            from supabase_client import supabase
            supabase.auth.sign_out()
        except Exception as exc:
            self._logout_signout_error = exc

    def closeEvent(self, event):
        try:
            self._lepas_resource_native()
            scaler = getattr(self, "_ui_scaler", None)
            if scaler is not None:
                try:
                    scaler.shutdown()
                except Exception:
                    pass
        finally:
            super().closeEvent(event)

    def _lepas_resource_native(self):
        self._hentikan_pemanasan_tab_tunda()
        auto_sync = getattr(self, "_auto_sync", None)
        if auto_sync is not None:
            auto_sync.stop(wait=False)
        for viewport in getattr(self, "_viewport_scroller", []):
            try:
                QScroller.ungrabGesture(viewport)
            except (RuntimeError, TypeError):
                pass
        self._viewport_scroller = []

        dialog = getattr(self, "dialog_setting", None)
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:
                pass

        self.dialog_setting = None
        self._setting_access_overlay = None
        self._sedang_sinkron_cabang = False
        self._cache_tema_tab.clear()
        self._tema_tab_sedang_diterapkan.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        dialog = getattr(self, 'dialog_setting', None)
        overlay = getattr(self, '_setting_access_overlay', None)
        if dialog is None or overlay is None:
            return

        try:
            if dialog.isVisible():
                overlay.resize(dialog.width(), dialog.height())
                overlay.raise_()
        except RuntimeError:
            self.dialog_setting = None
            self._setting_access_overlay = None

def penangkap_error_gaib(error_type, value, traceback_obj):
    traceback.print_exception(
        error_type,
        value,
        traceback_obj,
    )

sys.excepthook = penangkap_error_gaib


def jalankan_aplikasi():
    nama_db = CURRENT_SESSION.get(
        "db_name",
        "database_cargo.db",
    )

    with db_service.performance_timer("Startup.init_db", threshold=0.05):
        db_path = init_db(nama_db)
    CURRENT_SESSION["db_name"] = db_path

    with db_service.performance_timer("Startup.load_system_settings", threshold=0.05):
        DATA_CLIENT.update(muat_pengaturan_sistem())

    QLocale.setDefault(
        QLocale(
            QLocale.Language.Indonesian,
            QLocale.Country.Indonesia,
        )
    )

    with db_service.performance_timer("Startup.create_qapplication", threshold=0.05):
        app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("assets/logo/logo_mahkota_kargo.png"))

    if os.environ.get("DEBUG_FOCUS") == "1":
        def _debug_focus_changed(old, new):
            def _label(w):
                if w is None:
                    return "None"
                return f"{w.__class__.__name__}(objectName={w.objectName()!r})"

            print(
                f"\n[DEBUG_FOCUS] {_label(old)} -> {_label(new)}",
                flush=True,
            )
            for frame in traceback.format_stack()[:-1]:
                if "/site-packages/" not in frame and "\\site-packages\\" not in frame:
                    print(frame, end="", flush=True)

        app.focusChanged.connect(_debug_focus_changed)
        print("[DEBUG_FOCUS] Aktif - hover ke cell yang bermasalah lalu lihat console", flush=True)

    settings_awal = QSettings(
        MainWindow.SETTINGS_ORGANIZATION,
        MainWindow.SETTINGS_APPLICATION,
    )
    tema_awal = str(
        settings_awal.value(
            "theme",
            MainWindow.THEME_LIGHT,
        )
        or MainWindow.THEME_LIGHT
    ).strip().lower()

    if tema_awal not in {
        MainWindow.THEME_LIGHT,
        MainWindow.THEME_DARK,
    }:
        tema_awal = MainWindow.THEME_LIGHT

    app.setPalette(
        get_theme_palette(
            tema_awal == MainWindow.THEME_DARK
        )
    )

    print("[NATIVE] QApplication dibuat", flush=True)
    faulthandler.enable(all_threads=True)

    konfigurasi_font_aplikasi(app)

    window_holder = {
        "main": None,
    }

    @db_service.profile_performance("Startup.open_dashboard", threshold=0.05)
    def buka_dashboard_kargo():
        nama_db_aktif = str(
            CURRENT_SESSION.get("db_name", db_path)
            or db_path
        ).strip()
        with db_service.performance_timer("Dashboard.init_db", threshold=0.05):
            db_path_aktif = init_db(nama_db_aktif)
        CURRENT_SESSION["db_name"] = db_path_aktif

        with db_service.performance_timer("Dashboard.load_system_settings", threshold=0.05):
            DATA_CLIENT.update(muat_pengaturan_sistem())

        main_window = window_holder["main"]

        if main_window is None:
            main_window = MainWindow()
            window_holder["main"] = main_window

        # Seluruh jalur login yang sukses sudah menyiapkan allowed_branches:
        # online/developer/offline-cache. Gunakan snapshot sesi itu untuk
        # tampilan pertama, agar tidak mengulang request akses yang baru selesai.
        main_window.update_session_ui(refresh_branch_access=False)
        with db_service.performance_timer(
            "Dashboard.present_window", threshold=0.02
        ):
            main_window.showMaximized()
            main_window.raise_()
            main_window.activateWindow()

    def buat_login_window(show=True):
        """Buat login window baru untuk startup maupun setelah logout eksplisit."""
        login = LoginWindow(buka_dashboard_kargo)
        app._login_window = login
        if show:
            login.show()
        return login

    app._window_holder = window_holder
    app._show_login_window = buat_login_window

    login_window = buat_login_window(show=False)

    # Auto-login dijalankan asynchronous agar startup tidak freeze ketika
    # Supabase/database lambat. Form login hanya ditampilkan bila restore gagal.
    restore_started_at = time.perf_counter()

    def _selesai_restore(restored):
        db_service.log_performance_duration(
            "Startup.session_restore",
            time.perf_counter() - restore_started_at,
            threshold=0.05,
        )
        if not restored:
            login_window.show()

    login_window.restore_finished.connect(_selesai_restore)
    restore_started = login_window.try_restore_last_session()
    if not restore_started:
        login_window.show()

    print("[NATIVE] Memulai event loop", flush=True)
    exit_code = app.exec()
    print(f"[NATIVE] Event loop selesai: {exit_code}", flush=True)

    return exit_code

if __name__ == "__main__":
    sys.exit(jalankan_aplikasi())