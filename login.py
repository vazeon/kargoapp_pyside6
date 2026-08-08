# login.py
from PySide6.QtCore import Qt
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

from config import DATA_CLIENT, CURRENT_SESSION
from database_manager import init_db
from utils.typography import get_global_font_sizes_pt


class LoginWindow(QWidget):
    def __init__(self, switch_to_main_callback):
        super().__init__()
        self.switch_to_main = switch_to_main_callback
        self._drag_pos = None
        self._sedang_login = False
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.init_ui()
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
        card_widget.setFixedSize(360, 370)
        card_layout = QVBoxLayout(card_widget)
        card_layout.setContentsMargins(25, 15, 25, 30)
        card_layout.setSpacing(14)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 45))
        shadow.setOffset(0, 6)
        card_widget.setGraphicsEffect(shadow)

        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.addStretch()
        btn_close = QPushButton("×", card_widget)
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
        font_sizes = get_global_font_sizes_pt(0)
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
        self._set_login_busy(False)
        self.txt_pwd.clear()
        self.txt_user.setFocus()

    def _set_login_busy(self, busy):
        """Mengunci input agar proses login tidak terpanggil berulang."""
        self._sedang_login = bool(busy)
        aktif = not self._sedang_login
        self.txt_user.setEnabled(aktif)
        self.txt_pwd.setEnabled(aktif)
        self.btn_login.setEnabled(aktif)
        self.btn_login.setText("MEMPROSES..." if self._sedang_login else "MASUK")

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

    def handle_login(self):
        if self._sedang_login:
            return

        user, pwd = self._input_login()
        if self._peringatkan_input_kosong(user, pwd):
            return

        login_berhasil = False
        self._set_login_busy(True)
        try:
            from config import verifikasi_login_sistem

            sukses, role_user, nama_lengkap = self._validasi_hasil_login(
                verifikasi_login_sistem(user, pwd)
            )
            if sukses:
                self._siapkan_session_login(role_user, nama_lengkap)
                self.switch_to_main()
                login_berhasil = True
                self.txt_pwd.clear()
                self.close()
                return

            self._tampilkan_login_gagal()
        except Exception as error:
            self._tampilkan_error_login(error)
        finally:
            if not login_berhasil:
                self._set_login_busy(False)
                if self.isVisible():
                    self.txt_pwd.setFocus()

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