# main.py
import sys
import os
import faulthandler
import traceback
from PySide6.QtCore import QLocale, QSettings, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
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

from utils.typography import get_master_font

from config import DATA_CLIENT, CURRENT_SESSION, muat_pengaturan_sistem

from themes.base import BASE_STYLE
from themes.shell import get_main_shell_styles
from themes.top_right import get_top_right_styles
from themes.palette import get_theme_palette
from themes.scrollbar import GlobalScrollbarManager

from login import LoginWindow
from database_manager import init_db

from tabs.tab_resi import TabResi
from tabs.tab_buku_gudang import TabBukuGudang
from tabs.tab_manifest import TabManifest
from tabs.tab_invoice import TabInvoice
from tabs.tab_kontak.tab_kontak import TabKontak
from tabs.tab_armada.tab_armada import TabArmada

from tabs.tab_setting import TabSettingSistem

ENABLE_GLOBAL_SCROLLBAR_STYLE = False


class MainWindow(QMainWindow):
    SETTINGS_ORGANIZATION = "AplikasiEkspedisi"
    SETTINGS_APPLICATION = "PengaturanUI"
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
        tema_tersimpan = str(
            self.settings.value(
                "theme",
                self.THEME_LIGHT,
            )
            or self.THEME_LIGHT
        ).strip().lower()
        self.current_theme = (
            tema_tersimpan
            if tema_tersimpan in {self.THEME_LIGHT, self.THEME_DARK}
            else self.THEME_LIGHT
        )

        self._sedang_ganti_tema = False
        self._cache_tema_tab = {}
        self._tema_tab_sedang_diterapkan = set()
        self.dialog_setting = None
        self._setting_access_overlay = None

        app = QApplication.instance()
        if app is not None:
            if not bool(app.property("_base_style_terpasang")):
                app.setStyleSheet(BASE_STYLE)
                app.setProperty("_base_style_terpasang", True)

            app.setPalette(
                get_theme_palette(
                    self.current_theme == "dark"
                )
            )

        self.scrollbar_manager = None

        if ENABLE_GLOBAL_SCROLLBAR_STYLE and app is not None:
            self.scrollbar_manager = GlobalScrollbarManager(
                root_widget=self,
            )
            self.scrollbar_manager.install(app)

        self.init_ui()
        self._session_signature_terakhir = self._buat_signature_session()

    def init_ui(self):
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.tabs = QTabWidget(self)
        # Alias dipertahankan untuk modul yang mencari nama tabs_utama.
        self.tabs_utama = self.tabs
        self.tabs.setObjectName("MainTabs")
        self.custom_tab_bar = QTabBar(self)
        self.custom_tab_bar.setObjectName("MainTabBar")
        self.tabs.setTabBar(self.custom_tab_bar)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.setUsesScrollButtons(True)
        self.main_layout.addWidget(self.tabs)

        self.container_top_right = QWidget(self)
        hbox_top_right = QHBoxLayout(self.container_top_right)
        hbox_top_right.setContentsMargins(0, 4, 15, 4)
        hbox_top_right.setSpacing(6)

        self.lbl_info_cabang = QLabel("🏢 PUSAT")

        self.btn_zoom_out = QPushButton("🔍-")
        self.btn_zoom_out.setFixedSize(40, 32)
        self.btn_zoom_out.clicked.connect(lambda: self.ubah_zoom(-1))

        self.btn_zoom_in = QPushButton("🔍+")
        self.btn_zoom_in.setFixedSize(40, 32)
        self.btn_zoom_in.clicked.connect(lambda: self.ubah_zoom(1))

        self.btn_theme = QPushButton(self)
        self.btn_theme.setFixedWidth(120)
        self.btn_theme.setFixedHeight(32)
        self.btn_theme.clicked.connect(self.toggle_theme)

        self.btn_setting = QPushButton("⚙️")
        self.btn_setting.setFixedSize(40, 32)
        self.btn_setting.setToolTip("Pengaturan Sistem (Super Admin)")
        self.btn_setting.clicked.connect(self.buka_dasbor_pengaturan)

        hbox_top_right.addWidget(self.lbl_info_cabang)
        hbox_top_right.addWidget(self.btn_zoom_out)
        hbox_top_right.addWidget(self.btn_zoom_in)
        hbox_top_right.addWidget(self.btn_theme)
        hbox_top_right.addWidget(self.btn_setting)
        self.tabs.setCornerWidget(self.container_top_right, Qt.Corner.TopRightCorner)

        self.tab_resi_widget = TabResi()
        self.tabs.addTab(self.tab_resi_widget, "📦 Data Resi")

        self.tab_buku_gudang = TabBukuGudang()
        self.tabs.addTab(self.tab_buku_gudang, "🏭 Buku Gudang")

        self.tab_manifest = TabManifest()
        self.tabs.addTab(self.tab_manifest, "📋 Manifest")

        self.tab_invoice = TabInvoice()
        self.tabs.addTab(self.tab_invoice, "🧾 Invoice")

        self.tab_kontak = TabKontak()
        self.tabs.addTab(self.tab_kontak, "👥 Kontak")

        self.tab_armada = TabArmada()
        self.tabs.addTab(self.tab_armada, "🚛🚢 Armada")

        # Per-pixel scrolling tetap dipertahankan.
        for table in self.findChildren(QTableWidget):
            table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        # Gesture QScroller tidak dibutuhkan pada desktop mouse/keyboard.
        # Event filter native QScroller pada banyak viewport dapat membuat
        # penghancuran widget tidak stabil saat aplikasi ditutup.
        self._touch_scroll_aktif = False
        self._viewport_scroller = []

        if self._touch_scroll_aktif:
            for widget in self.findChildren(QScrollArea):
                viewport = widget.viewport()
                QScroller.grabGesture(
                    viewport,
                    QScroller.ScrollerGestureType.LeftMouseButtonGesture,
                )
                self._viewport_scroller.append(viewport)

            for table in self.findChildren(QTableWidget):
                viewport = table.viewport()
                QScroller.grabGesture(
                    viewport,
                    QScroller.ScrollerGestureType.LeftMouseButtonGesture,
                )
                self._viewport_scroller.append(viewport)

        self.tabs.currentChanged.connect(self.refresh_tab_utama_diklik)
        self.apply_theme()

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

        tab_aktif = self.tabs.widget(index)
        if tab_aktif is None:
            return

        self._terapkan_tema_lokal(tab_aktif)

        if tab_aktif is self.tab_resi_widget:
            fungsi_refresh = getattr(
                self.tab_resi_widget,
                "auto_refresh_histori",
                None,
            )

            if callable(fungsi_refresh):
                fungsi_refresh()

        elif tab_aktif is self.tab_manifest:
            fungsi_refresh_manifest = getattr(
                self.tab_manifest,
                "setup_autocomplete_truk",
                None,
            )

            if callable(fungsi_refresh_manifest):
                fungsi_refresh_manifest()

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
        """Menghasilkan seluruh widget tab utama yang masih tersedia."""
        return tuple(
            self.tabs.widget(index)
            for index in range(self.tabs.count())
            if self.tabs.widget(index) is not None
        )

    def _refresh_widget_session(self, widget):
        """Menyegarkan widget saat cabang atau sesi aktif berubah."""
        refresh_session = getattr(widget, "refresh_session_ui", None)
        if callable(refresh_session):
            refresh_session()
            return

        if widget is self.tab_resi_widget:
            refresh_resi = getattr(widget, "auto_refresh_histori", None)
            if callable(refresh_resi):
                refresh_resi()

        elif widget is self.tab_manifest:
            refresh_manifest = getattr(widget, "setup_autocomplete_truk", None)
            if callable(refresh_manifest):
                refresh_manifest()

    def update_session_ui(self):
        nama_perusahaan = DATA_CLIENT.get(
            'nama_perusahaan',
            'PT EKSPEDISI KARGO',
        )
        nama_cabang = CURRENT_SESSION.get('nama_cabang', 'PUSAT')
        self.setWindowTitle(
            f"{nama_perusahaan} - {nama_cabang} - PANEL ADMIN v1.0"
        )
        self.lbl_info_cabang.setText(f"🏢 {nama_cabang}")

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

        tab_aktif = self.tabs.currentWidget()
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

        finally:
            self._sedang_ganti_tema = False

    def apply_theme(self, force=False):
        is_dark = self.current_theme == self.THEME_DARK
        style_btn, style_label = get_top_right_styles(
            is_dark
        )

        app = QApplication.instance()

        self.setUpdatesEnabled(False)

        try:
            if app is not None:
                app.setPalette(
                    get_theme_palette(is_dark)
                )

            shell_styles = get_main_shell_styles(
                is_dark
            )
            self.central_widget.setStyleSheet(
                shell_styles["central"]
            )
            self.tabs.setStyleSheet(
                shell_styles["tabs"]
            )
            self.custom_tab_bar.setStyleSheet(
                shell_styles["tab_bar"]
            )
            self.container_top_right.setStyleSheet(
                shell_styles["corner"]
            )

            self.btn_theme.setText(
                "☀️ Mode Terang"
                if is_dark
                else "🌙 Mode Gelap"
            )

            self.lbl_info_cabang.setStyleSheet(
                style_label
            )

            for button in (
                self.btn_theme,
                self.btn_zoom_in,
                self.btn_zoom_out,
                self.btn_setting,
            ):
                button.setStyleSheet(style_btn)

        finally:
            self.setUpdatesEnabled(True)
            self.update()

        tab_aktif = self.tabs.currentWidget()

        if tab_aktif is not None:
            # Hindari callback lambda tertunda yang dapat tersisa ketika
            # widget atau QApplication sedang dihancurkan.
            self._terapkan_tema_lokal(
                tab_aktif,
                force=force,
            )

    def buka_dasbor_pengaturan(self):
        dialog_lama = getattr(self, "dialog_setting", None)
        if dialog_lama is not None:
            try:
                if dialog_lama.isVisible():
                    dialog_lama.raise_()
                    dialog_lama.activateWindow()
                    return
            except RuntimeError:
                self.dialog_setting = None

        self.dialog_setting = QDialog(self)
        self.dialog_setting.setWindowTitle("PENGATURAN")
        self.dialog_setting.setMinimumSize(800, 600)

        main_layout = QVBoxLayout(self.dialog_setting)
        widget_setting = TabSettingSistem(self.dialog_setting)
        main_layout.addWidget(widget_setting)

        role_aktif = str(CURRENT_SESSION.get('role', '')).strip().upper()
        boleh_mengubah = role_aktif in {"SUPER_ADMIN", "OWNER"}

        self._setting_access_overlay = None

        if not boleh_mengubah:
            widget_setting.setEnabled(False)

            overlay = QWidget(self.dialog_setting)
            overlay.setObjectName("SettingAccessOverlay")
            overlay.setStyleSheet(
                f"""
                    QWidget#SettingAccessOverlay {{
                        background-color: rgba(25, 25, 30, 0.9);
                        border-radius: 6px;
                    }}
                """
            )
            overlay.resize(
                self.dialog_setting.width(),
                self.dialog_setting.height(),
            )

            lbl_warning = QLabel(
                "🔒 AKSES TERBATAS\n\n"
                "Hanya akun SUPER ADMIN / OWNER yang memiliki otoritas\n"
                "untuk mengubah struktur data perusahaan.\n\n"
                f"(Role Anda Saat Ini: "
                f"{role_aktif if role_aktif else 'TIDAK DIKETAHUI'})",
                overlay,
            )
            lbl_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_warning.setStyleSheet(
                f"""
                    color: #ff4d4d;
                    font-size: 16px;
                    font-weight: bold;
                    line-height: 150%;
                """
            )

            overlay_layout = QVBoxLayout(overlay)
            overlay_layout.addWidget(lbl_warning)
            overlay.raise_()
            self._setting_access_overlay = overlay

            if hasattr(widget_setting, 'btn_simpan_all'):
                widget_setting.btn_simpan_all.setEnabled(False)
                widget_setting.btn_simpan_all.setText("❌ AKSES DITOLAK")

        try:
            self.dialog_setting.exec()
        finally:
            dialog = self.dialog_setting
            self._setting_access_overlay = None
            self.dialog_setting = None
            if dialog is not None:
                dialog.deleteLater()

    def closeEvent(self, event):
        """Melepas resource native sebelum MainWindow dihancurkan."""
        try:
            for viewport in getattr(self, "_viewport_scroller", []):
                try:
                    QScroller.ungrabGesture(viewport)
                except (RuntimeError, TypeError):
                    pass

            self._viewport_scroller = []

            scrollbar_manager = getattr(self, "scrollbar_manager", None)
            uninstall_scrollbar = getattr(scrollbar_manager, "uninstall", None)
            if callable(uninstall_scrollbar):
                try:
                    uninstall_scrollbar()
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
            self._cache_tema_tab.clear()
            self._tema_tab_sedang_diterapkan.clear()

        finally:
            super().closeEvent(event)

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

    def ubah_zoom(self, step):
        active_tab = self.tabs.currentWidget()

        if active_tab is None:
            return

        try:
            step = int(step)
        except (TypeError, ValueError):
            return

        if step == 0:
            return

        tab_name = active_tab.__class__.__name__

        try:
            current_z = int(
                self.settings.value(
                    f"zoom_{tab_name}",
                    0,
                )
            )
        except (TypeError, ValueError):
            current_z = 0

        new_z = max(
            self.ZOOM_MIN,
            min(current_z + step, self.ZOOM_MAX),
        )

        if new_z == current_z:
            return

        self.settings.setValue(
            f"zoom_{tab_name}",
            new_z,
        )
        self.settings.sync()

        self._terapkan_tema_lokal(
            active_tab,
            force=True,
        )

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.ubah_zoom(1)
            else:
                self.ubah_zoom(-1)
            event.accept()
        else:
            super().wheelEvent(event)


def load_fonts():
    font_folder = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "assets",
        "fonts",
    )

    if not os.path.exists(font_folder):
        print(
            f"❌ Folder font tidak ditemukan: {font_folder}"
        )
        return

    for filename in sorted(os.listdir(font_folder)):
        if not filename.lower().endswith((".ttf", ".otf")):
            continue

        font_path = os.path.join(
            font_folder,
            filename,
        )

        font_id = QFontDatabase.addApplicationFont(
            font_path
        )

        if font_id == -1:
            print(
                f"❌ Font gagal dimuat: {filename}"
            )
            continue

        families = QFontDatabase.applicationFontFamilies(
            font_id
        )

        print(
            f"✅ {filename} → "
            f"{', '.join(families)}"
        )


def penangkap_error_gaib(error_type, value, traceback_obj):
    import traceback

    traceback.print_exception(
        error_type,
        value,
        traceback_obj,
    )

sys.excepthook = penangkap_error_gaib


def konfigurasi_font_aplikasi(app):
    load_fonts()

    font_aktif = get_master_font()
    font_tersedia = set(QFontDatabase.families())

    if font_aktif not in font_tersedia:
        print(f"⚠️ Font '{font_aktif}' tidak tersedia.")

        if "Roboto" in font_tersedia:
            font_aktif = "Roboto"
        else:
            font_aktif = app.font().family()

    font_aplikasi = QFont(font_aktif)
    font_aplikasi.setPointSize(10)
    font_aplikasi.setWeight(QFont.Weight.Normal)
    font_aplikasi.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font_aplikasi)

    print("====================================")
    print("Font diterapkan:", app.font().family())
    print("====================================")


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
    app.setStyle("Fusion")
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