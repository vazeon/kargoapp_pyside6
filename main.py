# main.py
import os
import sys
import faulthandler
import threading
import traceback
from PySide6.QtCore import QLocale, QSettings, QTimer, Qt
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
        self._logout_login_window = None
        self._logout_signout_thread = None
        self._logout_signout_error = None
        self._logout_poll_timer = None

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

    def init_ui(self):
        self._bangun_shell_utama()
        self._bangun_kontrol_kanan()
        self._bangun_tab_utama()
        self._konfigurasi_scrolling()
        self.tabs.currentChanged.connect(self.refresh_tab_utama_diklik)
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
        self.tab_resi_widget = TabResi()
        self.tabs.addTab(self.tab_resi_widget, "Data Resi")

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

        self._terapkan_tema_lokal(tab_aktif)
        self._terapkan_mode_akses_widget(tab_aktif)

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

        # Modul yang memahami struktur editornya sendiri mendapat prioritas.
        targets = (widget, *widget.findChildren(QWidget))
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

        for child in widget.findChildren(QWidget):
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
            self._terapkan_mode_akses_widget(tab_aktif)
        for widget in self._iter_tab_utama():
            self._terapkan_mode_akses_widget(widget)

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

            scaler = getattr(self, "_ui_scaler", None)
            if scaler is not None:
                scaler.apply_now()

        finally:
            self._sedang_ganti_tema = False

    def apply_theme(self, force=False):
        is_dark = self.current_theme == self.THEME_DARK

        self._terapkan_tema_shell(is_dark)

        tab_aktif = self._konten_tab(self.tabs.currentWidget(), muat=True)
        if tab_aktif is not None:
            self._terapkan_tema_lokal(tab_aktif, force=force)

    def _terapkan_tema_shell(self, is_dark):
        app = QApplication.instance()

        try:
            scale = dapatkan_ui_scale()
        except Exception:
            scale = 1.0

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

        self.btn_theme.setText("Mode Terang" if is_dark else "Mode Gelap")

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

        # Hanya setelah worker sync benar-benar selesai kita boleh memutus Auth.
        thread = getattr(self, "_logout_signout_thread", None)
        if thread is None:
            thread = threading.Thread(
                target=self._logout_signout_worker,
                name="KargoLogoutWorker",
                daemon=True,
            )
            self._logout_signout_thread = thread
            thread.start()
            return

        if thread.is_alive():
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

        # Offline: sign-out server boleh gagal karena jaringan. Logout lokal
        # tetap dianggap sukses setelah credential/session lokal dibersihkan.

        # Auth sudah diputus. Baru sekarang state aplikasi dikosongkan.
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
        self._logout_sedang_berjalan = False
        self.deleteLater()

    def _logout_signout_worker(self):
        """Lakukan sign-out Supabase di thread background."""
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

    def buka_dashboard_kargo():
        nama_db_aktif = str(
            CURRENT_SESSION.get("db_name", db_path)
            or db_path
        ).strip()
        db_path_aktif = init_db(nama_db_aktif)
        CURRENT_SESSION["db_name"] = db_path_aktif

        DATA_CLIENT.update(muat_pengaturan_sistem())

        main_window = window_holder["main"]

        if main_window is None:
            main_window = MainWindow()
            window_holder["main"] = main_window

        main_window.update_session_ui()
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
    def _selesai_restore(restored):
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