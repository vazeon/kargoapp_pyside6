# main.py
import os
import sys
import faulthandler
import traceback
from PySide6.QtCore import QLocale, QSettings, Qt
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
    QSlider,
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
    konversi_font_qss_ke_point,
    konversi_style_font_ke_point,
)
from utils.splitter_helper import perbarui_semua_style_splitter
from utils.ui_metrics import (
    TOP_RIGHT_CONTROL_HEIGHT,
    TOP_RIGHT_ZOOM_SLIDER_WIDTH,
    dapatkan_ui_scale,
)
from utils.ui_scaler import ResponsiveUIScaler

from config import (
    DATA_CLIENT,
    CURRENT_SESSION,
    aktifkan_cabang_session,
    muat_pengaturan_sistem,
    refresh_akses_cabang_session,
)

from themes.theme_manager import ThemeManager
from themes.palette import get_theme_palette
from themes.scrollbar import GlobalScrollbarManager

from login import LoginWindow
from database_manager import init_db

from tabs.tab_resi import TabResi
from tabs.tab_setting import TabSettingSistem

ENABLE_GLOBAL_SCROLLBAR_STYLE = False


class _LazyTabPage(QWidget):
    """Container ringan yang membuat isi tab hanya saat benar-benar diperlukan."""

    def __init__(self, factory, parent=None):
        super().__init__(parent)
        self._factory = factory
        self._content = None
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._content_layout = layout

    @property
    def loaded_widget(self):
        return self._content

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
            return widget
        finally:
            self._loading = False

    # Kompatibilitas khusus alur Buku Gudang -> Invoice.
    # Method ini membuat Invoice on-demand tanpa mengubah kode TabBukuGudang.
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


class MainWindow(QMainWindow):
    SETTINGS_ORGANIZATION = ORGANIZATION_NAME
    SETTINGS_APPLICATION = APPLICATION_NAME
    THEME_LIGHT = "light"
    THEME_DARK = "dark"
    ZOOM_MIN = -4
    ZOOM_MAX = 10

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
        self._setting_access_overlay = None
        self._sedang_sinkron_cabang = False

        app = QApplication.instance()
        self._siapkan_tema_aplikasi(app)
        self._siapkan_scrollbar_global(app)
        self.init_ui()

        # Responsive geometry adalah layer otomatis berbasis screen. Zoom user
        # tetap terpisah dan hanya berlaku untuk tabel.
        self._ui_scaler = ResponsiveUIScaler(
            self,
            on_scale_changed=self._saat_ui_scale_berubah,
        )
        self._ui_scaler.apply_now()

        self._session_signature_terakhir = self._buat_signature_session()

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
            # Ambil scale saat ini
            try:
                scale = dapatkan_ui_scale()
            except Exception:
                scale = 1.0

            # Panggil Manager Global
            ThemeManager.apply_theme(app, is_dark, scale)

        app.setPalette(get_theme_palette(self.current_theme == self.THEME_DARK))

    def _siapkan_scrollbar_global(self, app):
        self.scrollbar_manager = None
        if ENABLE_GLOBAL_SCROLLBAR_STYLE and app is not None:
            self.scrollbar_manager = GlobalScrollbarManager(root_widget=self)
            self.scrollbar_manager.install(app)


    def _saat_ui_scale_berubah(self, scale):
        """Sinkronkan stylesheet/theme saat window berpindah screen/density."""
        app = QApplication.instance()
        is_dark = self.current_theme == self.THEME_DARK
        ThemeManager.apply_theme(app, is_dark, scale)

        self._cache_tema_tab.clear()
        if hasattr(self, "tabs"):
            self.apply_theme(force=True)


    def init_ui(self):
        self._bangun_shell_utama()
        self._bangun_kontrol_kanan()
        self._bangun_tab_utama()
        self._konfigurasi_scrolling()
        self.tabs.currentChanged.connect(self.refresh_tab_utama_diklik)
        self._sinkronkan_slider_zoom(self.tab_resi_widget)
        self.apply_theme()

    def _bangun_shell_utama(self):
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.tabs = QTabWidget(self)
        self.tabs_utama = self.tabs  # Alias kompatibilitas modul lama.
        self.tabs.setObjectName("MainTabs")
        self.custom_tab_bar = QTabBar(self)
        self.custom_tab_bar.setObjectName("MainTabBar")
        self.tabs.setTabBar(self.custom_tab_bar)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.setUsesScrollButtons(True)
        self.main_layout.addWidget(self.tabs)

    def _buat_tombol_top_right(self, text, slot, *, size=None, width=None):
        button = QPushButton(text) if text else QPushButton(self)

        # Tanda pengenal class untuk QSS Global
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
        self.container_top_right.setObjectName("ContainerTopRight")  # Pengenal CSS

        layout = QHBoxLayout(self.container_top_right)
        # Corner widget berbagi tinggi dengan MainTabBar. Margin vertikal 0
        # mencegah total tinggi kontrol melebihi tinggi bar tab.
        layout.setContentsMargins(0, 0, 15, 0)
        layout.setSpacing(6)

        self.lbl_info_cabang = QLabel("🏢:")
        self.lbl_info_cabang.setObjectName("LabelCabang")  # Pengenal CSS

        self.cmb_cabang_aktif = QComboBox(self)
        self.cmb_cabang_aktif.setMinimumWidth(180)
        self.cmb_cabang_aktif.setFixedHeight(TOP_RIGHT_CONTROL_HEIGHT)
        self.cmb_cabang_aktif.setToolTip("Ganti cabang operasional tanpa logout")
        self.cmb_cabang_aktif.currentIndexChanged.connect(self._ganti_cabang_aktif)

        self.lbl_zoom = QLabel("🔍")
        self.lbl_zoom.setObjectName("LabelZoom")
        self.lbl_zoom.setToolTip("Zoom tampilan tab aktif")

        self.slider_zoom = QSlider(Qt.Orientation.Horizontal, self)
        self.slider_zoom.setObjectName("ZoomSlider")
        self.slider_zoom.setRange(self.ZOOM_MIN, self.ZOOM_MAX)
        self.slider_zoom.setSingleStep(1)
        self.slider_zoom.setPageStep(1)
        self.slider_zoom.setTracking(False)
        self.slider_zoom.setFixedWidth(TOP_RIGHT_ZOOM_SLIDER_WIDTH)
        self.slider_zoom.setFixedHeight(TOP_RIGHT_CONTROL_HEIGHT)
        self.slider_zoom.setValue(0)
        self.slider_zoom.setToolTip("Zoom level: 0")
        self.slider_zoom.valueChanged.connect(self._ubah_zoom_dari_slider)

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
        self.btn_setting.setToolTip("Pengaturan Sistem (Super Admin)")

        # Posisikan seluruh kontrol top-right tepat di tengah secara vertikal
        # terhadap tinggi MainTabBar.
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        for widget in (
                self.lbl_info_cabang, self.cmb_cabang_aktif,
                self.lbl_zoom, self.slider_zoom,
                self.btn_theme, self.btn_setting,
        ):
            layout.addWidget(
                widget,
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )

        self.tabs.setCornerWidget(self.container_top_right, Qt.Corner.TopRightCorner)

    def _bangun_tab_utama(self):
        # Resi adalah landing page sehingga tetap dibuat langsung. Tab lain
        # dibuat on-demand agar pergantian theme global tidak perlu memproses
        # seluruh widget tree aplikasi sejak startup.
        self.tab_resi_widget = TabResi()
        self.tabs.addTab(self.tab_resi_widget, "📦 Data Resi")

        self.tab_buku_gudang = _LazyTabPage(self._buat_tab_buku_gudang, self.tabs)
        self.tabs.addTab(self.tab_buku_gudang, "🏭 Buku Gudang")

        self.tab_manifest = _LazyTabPage(self._buat_tab_manifest, self.tabs)
        self.tabs.addTab(self.tab_manifest, "📋 Manifest")

        self.tab_invoice = _LazyTabPage(self._buat_tab_invoice, self.tabs)
        self.tabs.addTab(self.tab_invoice, "🧾 Invoice")

        self.tab_kontak = _LazyTabPage(self._buat_tab_kontak, self.tabs)
        self.tabs.addTab(self.tab_kontak, "👥 Kontak")

        self.tab_armada = _LazyTabPage(self._buat_tab_armada, self.tabs)
        self.tabs.addTab(self.tab_armada, "🚛🚢 Armada")

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

        # QScroller desktop dinonaktifkan karena native event filter dapat
        # membuat penghancuran banyak viewport tidak stabil saat shutdown.
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

        nama_kelas = tab_widget.__class__.__name__

        try:
            zoom = int(
                self.settings.value(
                    f"zoom_{nama_kelas}",
                    0,
                )
            )
        except (TypeError, ValueError):
            zoom = 0

        return (
            self.current_theme,
            zoom,
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

                ThemeManager.apply_widget_theme(
                    tab_widget,
                    self.current_theme == self.THEME_DARK,
                    scale,
                )
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
            # Widget mungkin sudah dihancurkan saat aplikasi ditutup.
            self._cache_tema_tab.pop(cache_key, None)

        finally:
            self._tema_tab_sedang_diterapkan.discard(cache_key)

    def refresh_tab_utama_diklik(self, index):
        if index < 0 or index >= self.tabs.count():
            return

        page = self.tabs.widget(index)
        tab_aktif = self._konten_tab(page, muat=True)
        if tab_aktif is None:
            return

        if isinstance(page, _LazyTabPage):
            self._konfigurasi_scrolling_widget(tab_aktif)

        # Slider zoom selalu mengikuti zoom milik tab yang sedang aktif.
        self._sinkronkan_slider_zoom(tab_aktif)

        # Data tab disegarkan oleh showEvent masing-masing tab. MainWindow cukup
        # menangani tema agar satu perpindahan tab tidak memicu query/refresh ganda.
        self._terapkan_tema_lokal(tab_aktif)

    @staticmethod
    def _panggil_opsional(widget, nama_method):
        fungsi = getattr(widget, nama_method, None)
        if callable(fungsi):
            fungsi()


    @staticmethod
    def _buat_signature_session():
        """Identitas minimum untuk mendeteksi perpindahan akun/cabang."""
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
        """Menghasilkan hanya isi tab utama yang sudah benar-benar dibuat."""
        hasil = []
        for index in range(self.tabs.count()):
            widget = self._konten_tab(self.tabs.widget(index), muat=False)
            if widget is not None:
                hasil.append(widget)
        return tuple(hasil)

    def _refresh_widget_session(self, widget):
        """Menyegarkan widget saat cabang atau sesi aktif berubah."""
        refresh_session = getattr(widget, "refresh_session_ui", None)
        if callable(refresh_session):
            refresh_session()
            return
        if widget is self.tab_resi_widget:
            self._panggil_opsional(widget, "auto_refresh_histori")
        elif widget.__class__.__name__ == "TabManifest":
            self._panggil_opsional(widget, "setup_autocomplete_truk")


    def _sinkronkan_pemilih_cabang(self):
        """Isi pemilih cabang dari scope session tanpa memicu branch switch ulang."""
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
                nama = str(item.get("nama_cabang") or kode).strip()
                self.cmb_cabang_aktif.addItem(f"{nama} ({kode})", kode)

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
        """Ganti data scope cabang tanpa logout lalu refresh seluruh tab utama."""
        if self._sedang_sinkron_cabang:
            return
        kode = str(self.cmb_cabang_aktif.currentData() or "").strip().upper()
        current = str(CURRENT_SESSION.get("kode_cabang") or "").strip().upper()
        if not kode or kode == current:
            return

        if not aktifkan_cabang_session(kode):
            QMessageBox.warning(
                self,
                "Akses Cabang Ditolak",
                "Akun ini tidak memiliki akses ke cabang yang dipilih.",
            )
            self._sinkronkan_pemilih_cabang()
            return

        self.update_session_ui()

    def update_session_ui(self):
        refresh_akses_cabang_session()
        self._sinkronkan_pemilih_cabang()

        nama_perusahaan = DATA_CLIENT.get(
            'nama_perusahaan',
            'PT EKSPEDISI KARGO',
        )
        nama_cabang = CURRENT_SESSION.get('nama_cabang', 'PUSAT')
        self.setWindowTitle(
            f"{nama_perusahaan} - {nama_cabang} - PANEL ADMIN v1.0"
        )
        self.lbl_info_cabang.setText("🏢:")

        role_aktif = str(CURRENT_SESSION.get('role', '')).strip().upper()
        self.btn_setting.setToolTip(
            "Pengaturan Sistem (Super Admin / Owner)"
            if role_aktif in {"SUPER_ADMIN", "OWNER"}
            else "Pengaturan Sistem (akses terbatas)"
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
            self._terapkan_tema_lokal(tab_aktif, force=True)

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

            self.settings.setValue(
                "theme",
                self.current_theme,
            )
            self.settings.sync()

            self.apply_theme(force=True)

            # ThemeManager memasang QSS baseline theme baru.
            # ResponsiveUIScaler menerapkan geometry final satu kali.
            scaler = getattr(self, "_ui_scaler", None)
            if scaler is not None:
                scaler.apply_now()

        finally:
            self._sedang_ganti_tema = False

    def apply_theme(self, force=False):
        is_dark = self.current_theme == self.THEME_DARK

        # Shell dan tab aktif di-refresh secara terpisah. Jangan membekukan
        # MainWindow penuh karena itu mencakup seluruh tab yang sudah dibuat.
        self._terapkan_tema_shell(is_dark)

        tab_aktif = self._konten_tab(self.tabs.currentWidget(), muat=True)
        if tab_aktif is not None:
            self._terapkan_tema_lokal(tab_aktif, force=force)
            # Splitter hanya perlu mengikuti subtree yang sedang terlihat.
            perbarui_semua_style_splitter(tab_aktif, is_dark)

    def _terapkan_tema_shell(self, is_dark):
        app = QApplication.instance()

        try:
            scale = dapatkan_ui_scale()
        except Exception:
            scale = 1.0

        # QApplication hanya menyimpan state/palette. QSS pyqtdarktheme tidak
        # dipasang global agar tab tersembunyi tidak ikut di-repolish.
        ThemeManager.apply_theme(app, is_dark, scale)

        if app is not None:
            app.setPalette(get_theme_palette(is_dark))

        ThemeManager.apply_shell_theme(
            self.tabs,
            self.custom_tab_bar,
            self.container_top_right,
            is_dark,
            scale,
        )

        self.btn_theme.setText("☀️ Mode Terang" if is_dark else "🌙 Mode Gelap")


    def buka_dasbor_pengaturan(self):
        if self._aktifkan_dialog_setting_lama():
            return

        self.dialog_setting = QDialog(self)
        self.dialog_setting.setWindowTitle("PENGATURAN")
        self.dialog_setting.setMinimumSize(800, 600)
        layout = QVBoxLayout(self.dialog_setting)
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

        role_aktif = str(CURRENT_SESSION.get("role", "")).strip().upper()
        self._setting_access_overlay = None
        if role_aktif not in {"SUPER_ADMIN", "OWNER"}:
            self._pasang_overlay_akses_setting(widget_setting, role_aktif)

        try:
            self.dialog_setting.exec()
        finally:
            dialog = self.dialog_setting
            self._setting_access_overlay = None
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

    def _pasang_overlay_akses_setting(self, widget_setting, role_aktif):
        widget_setting.setEnabled(False)
        overlay = QWidget(self.dialog_setting)
        overlay.setObjectName("SettingAccessOverlay")
        overlay.setStyleSheet(
            "QWidget#SettingAccessOverlay {"
            "background-color: rgba(25, 25, 30, 0.9);"
            "border-radius: 6px;}"
        )
        overlay.resize(self.dialog_setting.width(), self.dialog_setting.height())

        label = QLabel(
            "🔒 AKSES TERBATAS\n\n"
            "Hanya akun SUPER ADMIN / OWNER yang memiliki otoritas\n"
            "untuk mengubah struktur data perusahaan.\n\n"
            f"(Role Anda Saat Ini: {role_aktif if role_aktif else 'TIDAK DIKETAHUI'})",
            overlay,
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "color: #ff4d4d; font-size: 12pt; font-weight: bold; line-height: 150%;"
        )
        QVBoxLayout(overlay).addWidget(label)
        overlay.raise_()
        self._setting_access_overlay = overlay

        if hasattr(widget_setting, "btn_simpan_all"):
            widget_setting.btn_simpan_all.setEnabled(False)
            widget_setting.btn_simpan_all.setText("❌ AKSES DITOLAK")


    def closeEvent(self, event):
        """Melepas resource native sebelum MainWindow dihancurkan."""
        try:
            self._lepas_resource_native()
        finally:
            super().closeEvent(event)

    def _lepas_resource_native(self):
        for viewport in getattr(self, "_viewport_scroller", []):
            try:
                QScroller.ungrabGesture(viewport)
            except (RuntimeError, TypeError):
                pass
        self._viewport_scroller = []

        manager = getattr(self, "scrollbar_manager", None)
        uninstall = getattr(manager, "uninstall", None)
        if callable(uninstall):
            try:
                uninstall()
            except (RuntimeError, TypeError):
                pass

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

    def _zoom_tab_aktif(self, active_tab=None):
        """Ambil zoom tersimpan untuk tab aktif tanpa mengubah UI."""
        if active_tab is None:
            active_tab = self._konten_tab(self.tabs.currentWidget(), muat=True)
        if active_tab is None:
            return 0

        key = f"zoom_{active_tab.__class__.__name__}"
        try:
            value = int(self.settings.value(key, 0))
        except (TypeError, ValueError):
            value = 0
        return max(self.ZOOM_MIN, min(value, self.ZOOM_MAX))

    def _sinkronkan_slider_zoom(self, active_tab=None):
        """Sinkronkan posisi slider dengan zoom milik tab yang sedang aktif."""
        slider = getattr(self, "slider_zoom", None)
        if slider is None:
            return

        value = self._zoom_tab_aktif(active_tab)
        blocked = slider.blockSignals(True)
        try:
            slider.setValue(value)
            slider.setToolTip(f"Zoom level: {value:+d}" if value else "Zoom level: 0")
        finally:
            slider.blockSignals(blocked)

    def _ubah_zoom_dari_slider(self, value):
        """Terapkan posisi slider sebagai zoom absolut tab aktif."""
        active_tab = self._konten_tab(self.tabs.currentWidget(), muat=True)
        if active_tab is None:
            return

        try:
            new_z = int(value)
        except (TypeError, ValueError):
            return

        new_z = max(self.ZOOM_MIN, min(new_z, self.ZOOM_MAX))
        current_z = self._zoom_tab_aktif(active_tab)

        slider = getattr(self, "slider_zoom", None)
        if slider is not None:
            slider.setToolTip(
                f"Zoom level: {new_z:+d}" if new_z else "Zoom level: 0"
            )

        if new_z == current_z:
            return

        key = f"zoom_{active_tab.__class__.__name__}"
        self.settings.setValue(key, new_z)
        self.settings.sync()
        self._terapkan_tema_lokal(active_tab, force=True)

    def ubah_zoom(self, step):
        active_tab = self._konten_tab(self.tabs.currentWidget(), muat=True)
        if active_tab is None:
            return
        try:
            step = int(step)
        except (TypeError, ValueError):
            return
        if step == 0:
            return

        current_z = self._zoom_tab_aktif(active_tab)
        new_z = max(self.ZOOM_MIN, min(current_z + step, self.ZOOM_MAX))
        if new_z == current_z:
            self._sinkronkan_slider_zoom(active_tab)
            return

        key = f"zoom_{active_tab.__class__.__name__}"
        self.settings.setValue(key, new_z)
        self.settings.sync()
        self._sinkronkan_slider_zoom(active_tab)
        self._terapkan_tema_lokal(active_tab, force=True)


    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.ubah_zoom(1)
            else:
                self.ubah_zoom(-1)
            event.accept()
        else:
            super().wheelEvent(event)


def penangkap_error_gaib(error_type, value, traceback_obj):
    traceback.print_exception(
        error_type,
        value,
        traceback_obj,
    )

sys.excepthook = penangkap_error_gaib


def jalankan_aplikasi():
    """Menyiapkan database, login, dan dashboard aplikasi."""
    nama_db = CURRENT_SESSION.get(
        "db_name",
        "database_cargo.db",
    )

    db_path = init_db(nama_db)
    CURRENT_SESSION["db_name"] = db_path

    DATA_CLIENT.update(muat_pengaturan_sistem())

    QLocale.setDefault(
        QLocale(
            QLocale.Language.Indonesian,
            QLocale.Country.Indonesia,
        )
    )

    app = QApplication(sys.argv)
    # app.setStyle("Fusion")

    # --- DEBUG SEMENTARA: lacak bug "input aktif sendiri saat hover" ---
    # Aktifkan dengan menjalankan: set DEBUG_FOCUS=1 (cmd) / $env:DEBUG_FOCUS=1 (PowerShell)
    # lalu jalankan app seperti biasa. Tidak berpengaruh apa pun bila env var
    # tidak diset (default off), aman ditinggal atau dihapus kapan saja.
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
            # Cetak hanya frame milik project ini (skip internal Qt/PySide/stdlib)
            for frame in traceback.format_stack()[:-1]:
                if "/site-packages/" not in frame and "\\site-packages\\" not in frame:
                    print(frame, end="", flush=True)

        app.focusChanged.connect(_debug_focus_changed)
        print("[DEBUG_FOCUS] Aktif - hover ke cell yang bermasalah lalu lihat console", flush=True)
    # --- AKHIR DEBUG SEMENTARA ---

    # Terapkan palette global sebelum widget apa pun dibuat, termasuk LoginWindow.
    # Dengan demikian QPalette.PlaceholderText dari themes/palette.py menjadi
    # sumber warna placeholder untuk seluruh aplikasi sejak awal.
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

    def buka_dashboard_kargo():
        # Jangan mengembalikan sesi ke database awal. Login dapat memilih
        # database/cabang lain dan path aktif tersebut harus dipertahankan.
        nama_db_aktif = str(
            CURRENT_SESSION.get("db_name", db_path)
            or db_path
        ).strip()
        db_path_aktif = init_db(nama_db_aktif)
        CURRENT_SESSION["db_name"] = db_path_aktif

        # Muat ulang identitas perusahaan dari database sesi yang aktif.
        DATA_CLIENT.update(muat_pengaturan_sistem())

        main_window = window_holder["main"]

        if main_window is None:
            main_window = MainWindow()
            window_holder["main"] = main_window

        main_window.update_session_ui()
        main_window.showMaximized()
        main_window.raise_()
        main_window.activateWindow()

    login_window = LoginWindow(
        buka_dashboard_kargo
    )

    app._login_window = login_window
    app._window_holder = window_holder
    login_window.show()

    print("[NATIVE] Memulai event loop", flush=True)
    exit_code = app.exec()
    print(f"[NATIVE] Event loop selesai: {exit_code}", flush=True)

    return exit_code

if __name__ == "__main__":
    sys.exit(jalankan_aplikasi())