# login.py
from PySide6.QtCore import Qt, QTimer, Signal

import os
import time
import threading
from contextlib import nullcontext
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import (
    DATA_CLIENT,
    CURRENT_SESSION,
    DEVELOPER_USERNAME,
    reset_current_session,
)
from session_store import (
    save_last_login,
    load_last_login,
    clear_last_login,
    save_offline_login_cache,
)
from database_manager import init_db
from utils.typography import get_fixed_font_sizes_pt
from utils.ui_scaler import ResponsiveUIScaler


class LoginWindow(QWidget):
    restore_finished = Signal(bool)
    auth_progress = Signal(str)

    def __init__(self, switch_to_main_callback):
        super().__init__()
        self.switch_to_main = switch_to_main_callback
        self._drag_pos = None
        self._sedang_login = False
        self._external_busy = False
        self._auth_thread = None
        self._auth_poll_timer = None
        self._auth_mode = None
        self._auth_result = None
        self._auth_error = None
        self._auth_identifier = None
        self._auth_password = None
        self._auth_password_backup = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.init_ui()
        self.auth_progress.connect(self._update_auth_progress_text)
        self._ui_scaler = ResponsiveUIScaler(self)
        self._ui_scaler.apply_now()
        self.center_window()

    @staticmethod
    def _style_login(font_sizes):
        placeholder_color = QApplication.palette().color(
            QPalette.ColorRole.PlaceholderText
        ).name()
        return f"""
                #LoginWidgetRoot {{
                    background: transparent;
                }}
                QWidget {{
                    color: #1e293b;
                    font-size: {font_sizes['sz_base']}pt;
                }}
                #LoginCard {{
                    background-color: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 12px;
                }}
                QLineEdit {{
                    background-color: #f8fafc;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 11px 15px;
                    color: #0f172a;
                    placeholder-text-color: {placeholder_color};
                    font-size: {font_sizes['sz_input']}pt;
                }}
                QLineEdit:focus {{
                    border: 1px solid #2563eb;
                    background-color: #ffffff;
                }}
                QPushButton#BtnEnter {{
                    background-color: #2563eb;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 12px;
                    font-weight: bold;
                    font-size: {font_sizes['sz_input']}pt;
                    letter-spacing: 1px;
                }}
                QPushButton#BtnEnter:hover {{
                    background-color: #1d4ed8;
                }}
                QPushButton#BtnCloseTop {{
                    background-color: transparent;
                    color: #94a3b8;
                    font-size: {font_sizes['sz_title']}pt;
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                }}
                QPushButton#BtnCloseTop:hover {{
                    background-color: #ef4444;
                    color: white;
                }}
            """

    def _buat_card_login(self):
        card_widget = QWidget()
        card_widget.setObjectName("LoginCard")
        card_widget.setFixedSize(360, 360)
        card_layout = QVBoxLayout(card_widget)
        card_layout.setContentsMargins(16, 16, 16, 24)
        card_layout.setSpacing(16)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 45))
        shadow.setOffset(0, 6)
        card_widget.setGraphicsEffect(shadow)

        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.addStretch()
        btn_close = QPushButton("🞩", card_widget)
        btn_close.setObjectName("BtnCloseTop")
        btn_close.setFixedSize(28, 28)
        btn_close.clicked.connect(QApplication.instance().quit)
        top_bar_layout.addWidget(btn_close)
        card_layout.addLayout(top_bar_layout)
        return card_widget, card_layout

    @staticmethod
    def _buat_label_identitas(text, style):
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(style)
        return label

    def _isi_card_login(self, card_layout, font_sizes):
        lbl_title = self._buat_label_identitas(
            DATA_CLIENT.get("nama_perusahaan", "SISTEM EKSPEDISI KARGO"),
            f"""
                font-size: {font_sizes['sz_total']}pt;
                font-weight: bold;
                color: #0f172a;
                letter-spacing: 1px;
                text-transform: uppercase;
                margin-top: -10px;
            """,
        )
        lbl_title.setWordWrap(True)
        card_layout.addWidget(lbl_title)

        card_layout.addWidget(self._buat_label_identitas(
            "PANEL ADMIN",
            f"""
                font-size: {font_sizes['sz_sm']}pt;
                letter-spacing: 3px;
                color: #2563eb;
                font-weight: bold;
                margin-bottom: 5px;
            """,
        ))

        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("Username")
        card_layout.addWidget(self.txt_user)

        self.txt_pwd = QLineEdit()
        self.txt_pwd.setPlaceholderText("Password")
        self.txt_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        card_layout.addWidget(self.txt_pwd)
        card_layout.addSpacing(5)

        self.btn_login = QPushButton("MASUK")
        self.btn_login.setObjectName("BtnEnter")
        card_layout.addWidget(self.btn_login)

    def _hubungkan_signal_login(self):
        self.btn_login.clicked.connect(self.handle_login)
        self.txt_user.returnPressed.connect(self.handle_login)
        self.txt_pwd.returnPressed.connect(self.handle_login)
        self.btn_login.setDefault(True)

    def init_ui(self):
        self.setObjectName("LoginWidgetRoot")
        font_sizes = get_fixed_font_sizes_pt()
        self.setStyleSheet(self._style_login(font_sizes))

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_widget, card_layout = self._buat_card_login()
        self._isi_card_login(card_layout, font_sizes)
        self._hubungkan_signal_login()
        main_layout.addWidget(card_widget)
        self.setLayout(main_layout)

    def showEvent(self, event):
        super().showEvent(event)
        auth_in_progress = self._auth_thread is not None and self._auth_thread.is_alive()
        if not self._external_busy and not auth_in_progress:
            self._set_login_busy(False)
            self.txt_pwd.clear()
            self.txt_user.setFocus()
        else:
            self._set_login_busy(auth_in_progress)

    def _set_login_busy(self, busy):
        """Mengunci input saat proses login atau transisi sesi sedang berjalan."""
        self._sedang_login = bool(busy)
        aktif = not self._sedang_login and not self._external_busy

        self.txt_user.setEnabled(aktif)
        self.txt_pwd.setEnabled(aktif)
        self.btn_login.setEnabled(aktif)

        if self._external_busy:
            self.btn_login.setText("MENUTUP SESI...")
        elif self._sedang_login:
            self.btn_login.setText("MEMPROSES...")
        else:
            self.btn_login.setText("MASUK")

    def _update_auth_progress_text(self, message):
        """Perbarui label tombol dari signal Qt, bukan langsung dari worker thread."""
        if not self._sedang_login or self._external_busy:
            return
        text = str(message or "").strip()
        if text:
            self.btn_login.setText(text)

    def set_external_busy(self, busy):
        """Kunci form dari proses eksternal, misalnya logout asinkron."""
        self._external_busy = bool(busy)
        if self._external_busy:
            self._sedang_login = False
        self._set_login_busy(self._sedang_login)

    def _input_login(self):
        return self.txt_user.text().strip(), self.txt_pwd.text().strip()

    def _peringatkan_input_kosong(self, user, pwd):
        if user and pwd:
            return False
        QMessageBox.warning(
            self,
            "Peringatan",
            "Username dan Password tidak boleh kosong!",
        )
        (self.txt_user if not user else self.txt_pwd).setFocus()
        return True

    @staticmethod
    def _validasi_hasil_login(hasil_login):
        if not isinstance(hasil_login, (tuple, list)) or len(hasil_login) < 3:
            raise RuntimeError("Hasil verifikasi login tidak memiliki format yang valid.")
        return hasil_login[:3]

    def _siapkan_session_login(self, role_user, nama_lengkap):
        db_name = str(
            CURRENT_SESSION.get("db_name", "database_cargo.db")
            or "database_cargo.db"
        ).strip()
        CURRENT_SESSION["db_name"] = init_db(db_name)
        if role_user and not CURRENT_SESSION.get("role"):
            CURRENT_SESSION["role"] = str(role_user).strip()
        if nama_lengkap and not CURRENT_SESSION.get("nama_lengkap"):
            CURRENT_SESSION["nama_lengkap"] = str(nama_lengkap).strip()
        if not callable(self.switch_to_main):
            raise RuntimeError("Callback untuk membuka dashboard tidak tersedia.")

    def _bootstrap_client_online(self):
        """Ambil konfigurasi white-label setelah login Supabase berhasil."""
        auth_email = str(CURRENT_SESSION.get("auth_email") or "").strip()
        if not auth_email:
            # DEV_SUPER adalah akun offline dan tidak pernah menjalankan bootstrap.
            return None

        from services.client_bootstrap_service import bootstrap_from_supabase

        db_name = str(
            CURRENT_SESSION.get("db_name", "database_cargo.db")
            or "database_cargo.db"
        ).strip()
        info = bootstrap_from_supabase(db_name)
        print(
            "[CLIENT_BOOTSTRAP] "
            f"client={info.get('client_code')} "
            f"config_version={info.get('config_version')} "
            f"changed={info.get('changed')}",
            flush=True,
        )
        return info

    def _simpan_sesi_worker(self, identifier, password, mode, phase_timer):
        """Simpan cache sesi dari worker agar hash dan I/O tidak memblokir UI."""
        if password and not bool(CURRENT_SESSION.get("is_developer")):
            self.auth_progress.emit("MENYIMPAN SESI...")
            snapshot = {
                "id_user": CURRENT_SESSION.get("id_user", ""),
                "username": CURRENT_SESSION.get("username", ""),
                "nama_lengkap": CURRENT_SESSION.get("nama_lengkap", ""),
                "auth_email": CURRENT_SESSION.get("auth_email", "") or identifier,
                "role": CURRENT_SESSION.get("role", ""),
                "kode_cabang": CURRENT_SESSION.get("kode_cabang", ""),
                "nama_cabang": CURRENT_SESSION.get("nama_cabang", ""),
                "home_kode_cabang": CURRENT_SESSION.get("home_kode_cabang", ""),
                "home_nama_cabang": CURRENT_SESSION.get("home_nama_cabang", ""),
                "resi_prefix": CURRENT_SESSION.get("resi_prefix", "INV"),
                "aturan_prefix": dict(CURRENT_SESSION.get("aturan_prefix") or {}),
                "allowed_branches": [
                    dict(item)
                    for item in (CURRENT_SESSION.get("allowed_branches") or [])
                    if isinstance(item, dict)
                ],
            }
            with phase_timer("Auth.persist_offline_cache"):
                save_offline_login_cache(identifier, password, snapshot)

        if mode == "login":
            with phase_timer("Auth.persist_last_login"):
                save_last_login(identifier, password)

    def _tampilkan_login_gagal(self):
        self.txt_pwd.clear()
        self.txt_pwd.setFocus()
        QMessageBox.critical(
            self,
            "Akses Ditolak",
            "Username atau Password salah!\nPastikan huruf besar/kecil sesuai.",
        )

    def _tampilkan_error_login(self, error):
        self.txt_pwd.clear()
        self.txt_pwd.setFocus()
        QMessageBox.critical(
            self,
            "Fatal Error",
            f"Terjadi kerusakan sistem saat memproses login:\n\n{str(error)}",
        )

    def _cleanup_failed_auth(self):
        """Kembalikan aplikasi ke keadaan unauthenticated yang konsisten."""
        # Kegagalan saat menyiapkan sesi developer harus tetap lokal. Jangan
        # mengirim request sign-out ke Supabase dari jalur DEV_SUPER.
        is_developer_attempt = (
            bool(CURRENT_SESSION.get("is_developer"))
            or str(self._auth_identifier or "").strip().upper()
            == DEVELOPER_USERNAME
        )
        if not is_developer_attempt:
            try:
                from supabase_client import supabase
                supabase.auth.sign_out()
            except Exception:
                pass
        try:
            reset_current_session()
        except Exception:
            pass

    def _stop_auth_poll_timer(self):
        timer = self._auth_poll_timer
        self._auth_poll_timer = None
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def _start_auth_worker(self, identifier, password, mode):
        if self._auth_thread is not None and self._auth_thread.is_alive():
            return False

        self._auth_mode = mode
        self._auth_result = None
        self._auth_error = None
        self._auth_identifier = str(identifier or "").strip()
        self._auth_password = str(password or "")
        self._auth_password_backup = self._auth_password

        worker = threading.Thread(
            target=self._auth_worker,
            args=(self._auth_identifier, self._auth_password, mode),
            name="KargoAuthWorker",
            daemon=True,
        )
        self._auth_thread = worker
        try:
            worker.start()
        except Exception:
            self._auth_thread = None
            self._auth_mode = None
            self._auth_result = None
            self._auth_error = RuntimeError("Worker autentikasi gagal dijalankan.")
            self._auth_password = None
            self._auth_password_backup = None
            return False

        self._stop_auth_poll_timer()
        self._auth_poll_timer = QTimer(self)
        self._auth_poll_timer.setInterval(40)
        self._auth_poll_timer.timeout.connect(self._poll_auth_worker)
        self._auth_poll_timer.start()
        return True

    @staticmethod
    def _is_network_error(error) -> bool:
        """Bedakan gangguan jaringan dari kredensial/akun yang benar-benar invalid."""
        if error is None:
            return False
        text = str(error).lower()
        network_terms = (
            "winerror 10054",
            "connectionreseterror",
            "connection reset",
            "forcibly closed",
            "remotedisconnected",
            "remote end closed",
            "timed out",
            "timeout",
            "urlerror",
            "name or service not known",
            "temporary failure in name resolution",
            "getaddrinfo failed",
            "network is unreachable",
            "connection aborted",
            "connection refused",
            "ssl",
        )
        return any(term in text for term in network_terms)

    def _try_offline_restore(self, identifier, error=None) -> bool:
        """Masuk memakai cache lokal bila restore Supabase gagal karena jaringan."""
        if not self._is_network_error(error):
            return False
        try:
            from config import _verifikasi_login_offline_cache
            hasil = _verifikasi_login_offline_cache(identifier)
            return bool(hasil and hasil[0])
        except Exception as exc:
            print(f"[SESSION] Offline restore gagal: {type(exc).__name__}: {exc}", flush=True)
            return False

    def _auth_worker(self, identifier, password, mode):
        # Profiling opsional untuk memisahkan waktu autentikasi, persiapan sesi,
        # dan bootstrap Supabase. Tidak mengubah jalur login saat fitur dimatikan.
        perf_db = None
        perf_enabled = os.environ.get("KARGO_PERF_LOG", "").strip() == "1"
        worker_started = time.perf_counter()
        if perf_enabled:
            try:
                from services import database_service as perf_db
            except Exception:
                # Kegagalan import alat ukur tidak boleh mengganggu autentikasi.
                perf_enabled = False
                perf_db = None

        def _phase_timer(label):
            if perf_enabled and perf_db is not None:
                return perf_db.performance_timer(label, threshold=0.02)
            return nullcontext()

        try:
            from config import verifikasi_login_sistem

            if mode == "restore":
                self.auth_progress.emit("MEMULIHKAN SESI...")
            else:
                self.auth_progress.emit("MEMVERIFIKASI AKUN...")

            with _phase_timer("Auth.verify_login"):
                hasil = self._validasi_hasil_login(
                    verifikasi_login_sistem(
                        identifier,
                        password,
                        progress_callback=self.auth_progress.emit,
                    )
                )
            sukses, role_user, nama_lengkap = hasil
            if not sukses:
                self._auth_result = {
                    "success": False,
                    "role": None,
                    "name": None,
                }
                return

            # Persiapan session + bootstrap dilakukan di worker agar GUI tidak
            # freeze ketika database/network lambat.
            self.auth_progress.emit("MENYIAPKAN DATABASE...")
            with _phase_timer("Auth.prepare_session"):
                self._siapkan_session_login(role_user, nama_lengkap)
            self.auth_progress.emit("MENYIAPKAN PROFIL CLIENT...")
            with _phase_timer("Auth.client_bootstrap"):
                self._bootstrap_client_online()
            self.auth_progress.emit("MEMBUKA DASHBOARD...")
            self._auth_result = {
                "success": True,
                "role": role_user,
                "name": nama_lengkap,
                "offline": bool(CURRENT_SESSION.get("is_offline_session")),
            }
            # Persist sesi setelah seluruh validasi dan bootstrap berhasil, tetapi
            # tetap di worker agar PBKDF2/QSettings tidak memblokir thread UI.
            self._simpan_sesi_worker(identifier, password, mode, _phase_timer)
        except Exception as exc:
            self._auth_error = exc
            offline_ok = False
            if mode == "restore":
                with _phase_timer("Auth.offline_restore_cache"):
                    offline_ok = self._try_offline_restore(identifier, exc)
            if offline_ok:
                self._auth_error = None
                self._auth_result = {
                    "success": True,
                    "role": CURRENT_SESSION.get("role"),
                    "name": CURRENT_SESSION.get("nama_lengkap"),
                    "offline": True,
                }
                try:
                    self._simpan_sesi_worker(identifier, password, mode, _phase_timer)
                except Exception as persist_exc:
                    self._auth_error = persist_exc
                    self._cleanup_failed_auth()
                    self._auth_result = {
                        "success": False,
                        "role": None,
                        "name": None,
                    }
            else:
                self._cleanup_failed_auth()
                self._auth_result = {
                    "success": False,
                    "role": None,
                    "name": None,
                }
        finally:
            self._auth_password = None
            if perf_enabled and perf_db is not None:
                perf_db.log_performance_duration(
                    "Auth.worker_total",
                    time.perf_counter() - worker_started,
                    threshold=0.02,
                )

    def _poll_auth_worker(self):
        thread = self._auth_thread
        if thread is not None and thread.is_alive():
            return

        self._stop_auth_poll_timer()
        self._auth_thread = None

        mode = self._auth_mode
        result = self._auth_result or {"success": False}
        error = self._auth_error
        identifier = self._auth_identifier or ""

        self._auth_mode = None
        self._auth_result = None
        self._auth_error = None
        self._auth_identifier = None
        self._auth_password_backup = None

        success = bool(result.get("success"))
        if success:
            try:
                # Penyimpanan cache sudah dilakukan oleh worker autentikasi.
                # Di sini hanya dilakukan perpindahan UI setelah worker selesai.
                self.switch_to_main()
                self._set_login_busy(False)
                self.txt_pwd.clear()
                self.close()
                if mode == "restore":
                    self.restore_finished.emit(True)
                return
            except Exception as exc:
                error = exc
                self._cleanup_failed_auth()
                if mode in {"login", "restore"}:
                    clear_last_login()

        if mode == "restore":
            # Jangan menghapus last-session hanya karena Supabase sedang offline.
            # Credential baru dihapus bila restore gagal karena alasan non-jaringan
            # (mis. password salah atau akun sudah tidak valid).
            if error is None or not self._is_network_error(error):
                clear_last_login()
            if error is not None:
                print(
                    "[SESSION] Restore sesi terakhir gagal: "
                    f"{type(error).__name__}: {error}",
                    flush=True,
                )
            self._set_login_busy(False)
            self.restore_finished.emit(False)
            return

        self._set_login_busy(False)
        if error is not None:
            self._tampilkan_error_login(error)
        else:
            self._tampilkan_login_gagal()
        if self.isVisible():
            self.txt_pwd.setFocus()

    def handle_login(self):
        if self._sedang_login or self._external_busy:
            return

        user, pwd = self._input_login()
        if self._peringatkan_input_kosong(user, pwd):
            return

        self._set_login_busy(True)
        self._start_auth_worker(user, pwd, "login")

    def try_restore_last_session(self):
        """Mulai restore sesi terakhir tanpa memblokir GUI.

        Return False berarti tidak ada credential tersimpan, sehingga caller
        boleh langsung menampilkan form login. Return True berarti proses restore
        sedang berjalan; hasil akhirnya dikirim melalui ``restore_finished``.
        """
        if self._external_busy or (self._auth_thread is not None and self._auth_thread.is_alive()):
            return False

        saved = load_last_login()
        if not saved:
            return False

        self._set_login_busy(True)
        return self._start_auth_worker(
            saved.get("identifier", ""),
            saved.get("password", ""),
            "restore",
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            self._drag_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def center_window(self):
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        qr = self.frameGeometry()
        qr.moveCenter(screen.availableGeometry().center())
        self.move(qr.topLeft())