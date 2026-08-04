# themes/scrollbar.py
"""Style dan pengelola scrollbar global aplikasi."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from tempfile import gettempdir
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QScrollBar, QWidget


@lru_cache(maxsize=2)
def _buat_icon_panah() -> Dict[str, str]:
    warna_panah = "#64748b"
    nama_tema = "neutral"

    folder_icon = (
        Path(gettempdir())
        / "global_scrollbar_icons"
        / nama_tema
    )
    folder_icon.mkdir(
        parents=True,
        exist_ok=True,
    )

    data_path = {
        "up": "M1.25 5.25 L4 2.5 L6.75 5.25",
        "down": "M1.25 2.75 L4 5.5 L6.75 2.75",
        "left": "M5.25 1.25 L2.5 4 L5.25 6.75",
        "right": "M2.75 1.25 L5.5 4 L2.75 6.75",
    }

    hasil: Dict[str, str] = {}

    for arah, path_data in data_path.items():
        file_path = folder_icon / f"arrow_{arah}.svg"

        isi_svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
            width="8"
            height="8"
            viewBox="0 0 8 8">
            <path
                d="{path_data}"
                fill="none"
                stroke="{warna_panah}"
                stroke-width="1.45"
                stroke-linecap="round"
                stroke-linejoin="round"
            />
        </svg>"""

        # Hindari menulis ulang file ikon jika isinya tidak berubah.
        if (
            not file_path.exists()
            or file_path.read_text(
                encoding="utf-8"
            ) != isi_svg
        ):
            file_path.write_text(
                isi_svg,
                encoding="utf-8",
            )

        # Qt Style Sheet lebih stabil menggunakan slash, termasuk di Windows.
        hasil[arah] = file_path.resolve().as_posix()

    return hasil


def get_scrollbar_style() -> str:
    warna_handle = "rgba(100, 116, 139, 150)"
    warna_hover = "rgba(100, 116, 139, 210)"
    warna_track_hover = "rgba(100, 116, 139, 28)"
    warna_pressed = "rgba(71, 85, 105, 235)"
    warna_tombol_hover = "rgba(100, 116, 139, 42)"
    warna_tombol_pressed = "rgba(71, 85, 105, 68)"

    icon_panah = _buat_icon_panah()

    # Ukuran 16px menyediakan ruang yang cukup untuk handle dan tombol panah.
    ukuran_scrollbar = 16
    ukuran_icon_panah = 8

    return f"""
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: {ukuran_scrollbar}px;
            margin: {ukuran_scrollbar}px 0px {ukuran_scrollbar}px 0px;
        }}
        QScrollBar:vertical:hover {{
            background: {warna_track_hover};
            border-radius: 7px;
        }}
        QScrollBar::handle:vertical {{
            background: {warna_handle};
            border: none;
            border-radius: 5px;
            min-height: 30px;
            margin: 2px 3px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {warna_hover};
        }}
        QScrollBar::handle:vertical:pressed {{
            background: {warna_pressed};
        }}
        QScrollBar::sub-line:vertical {{
            background: transparent;
            border: none;
            border-radius: 4px;
            height: {ukuran_scrollbar}px;
            subcontrol-origin: margin;
            subcontrol-position: top;
        }}
        QScrollBar::add-line:vertical {{
            background: transparent;
            border: none;
            border-radius: 4px;
            height: {ukuran_scrollbar}px;
            subcontrol-origin: margin;
            subcontrol-position: bottom;
        }}
        QScrollBar::sub-line:vertical:hover, QScrollBar::add-line:vertical:hover {{
            background: {warna_tombol_hover};
        }}
        QScrollBar::sub-line:vertical:pressed, QScrollBar::add-line:vertical:pressed {{
            background: {warna_tombol_pressed};
        }}
        QScrollBar::up-arrow:vertical {{
            image: url("{icon_panah['up']}");
            width: {ukuran_icon_panah}px;
            height: {ukuran_icon_panah}px;
        }}
        QScrollBar::down-arrow:vertical {{
            image: url("{icon_panah['down']}");
            width: {ukuran_icon_panah}px;
            height: {ukuran_icon_panah}px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
            border: none;
        }}
        QScrollBar:horizontal {{
            border: none;
            background: transparent;
            height: {ukuran_scrollbar}px;
            margin: 0px {ukuran_scrollbar}px 0px {ukuran_scrollbar}px;
        }}
        QScrollBar:horizontal:hover {{
            background: {warna_track_hover};
            border-radius: 7px;
        }}
        QScrollBar::handle:horizontal {{
            background: {warna_handle};
            border: none;
            border-radius: 5px;
            min-width: 30px;
            margin: 3px 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {warna_hover};
        }}
        QScrollBar::handle:horizontal:pressed {{
            background: {warna_pressed};
        }}
        QScrollBar::sub-line:horizontal {{
            background: transparent;
            border: none;
            border-radius: 4px;
            width: {ukuran_scrollbar}px;
            subcontrol-origin: margin;
            subcontrol-position: left;
        }}
        QScrollBar::add-line:horizontal {{
            background: transparent;
            border: none;
            border-radius: 4px;
            width: {ukuran_scrollbar}px;
            subcontrol-origin: margin;
            subcontrol-position: right;
        }}
        QScrollBar::sub-line:horizontal:hover, QScrollBar::add-line:horizontal:hover {{
            background: {warna_tombol_hover};
        }}
        QScrollBar::sub-line:horizontal:pressed, QScrollBar::add-line:horizontal:pressed {{
            background: {warna_tombol_pressed};
        }}
        QScrollBar::left-arrow:horizontal {{
            image: url("{icon_panah['left']}");
            width: {ukuran_icon_panah}px;
            height: {ukuran_icon_panah}px;
        }}
        QScrollBar::right-arrow:horizontal {{
            image: url("{icon_panah['right']}");
            width: {ukuran_icon_panah}px;
            height: {ukuran_icon_panah}px;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
            border: none;
        }}
    """


class GlobalScrollbarManager(QObject):
    """
    Memasang satu blok QSS scrollbar netral pada QApplication.

    Style dipasang sekali saat startup. Pergantian tema aplikasi tidak memicu
    setStyleSheet() ulang, sehingga tidak menyebabkan repolish global.
    """

    STYLE_START = "/* __GLOBAL_SCROLLBAR_STYLE_START__ */"
    STYLE_END = "/* __GLOBAL_SCROLLBAR_STYLE_END__ */"

    def __init__(
        self,
        root_widget: QWidget,
        is_dark_getter: Optional[Callable[[], bool]] = None,
    ):
        super().__init__(root_widget)

        self.root_widget = root_widget
        # Parameter dipertahankan agar main.py lama tetap kompatibel.
        self.is_dark_getter = is_dark_getter
        self._app: Optional[QApplication] = None
        self._installed = False
        self._sedang_refresh = False

    @classmethod
    def _hapus_blok_lama(cls, stylesheet: str) -> str:
        """
        Menghapus semua blok QSS scrollbar yang pernah ditambahkan manager.
        """
        hasil = str(stylesheet or "")

        while True:
            posisi_awal = hasil.find(cls.STYLE_START)
            if posisi_awal < 0:
                break

            posisi_akhir = hasil.find(
                cls.STYLE_END,
                posisi_awal + len(cls.STYLE_START),
            )

            if posisi_akhir < 0:
                hasil = hasil[:posisi_awal]
                break

            posisi_akhir += len(cls.STYLE_END)
            hasil = hasil[:posisi_awal] + hasil[posisi_akhir:]

        return hasil.strip()

    @classmethod
    def _stylesheet_gabungan(cls, stylesheet_dasar: str) -> str:
        dasar_bersih = cls._hapus_blok_lama(stylesheet_dasar)
        style_scrollbar = get_scrollbar_style().strip()

        bagian = [
            item
            for item in (
                dasar_bersih,
                cls.STYLE_START,
                style_scrollbar,
                cls.STYLE_END,
            )
            if item
        ]

        return "\n\n".join(bagian)

    def install(
        self,
        app: Optional[QApplication] = None,
    ) -> None:
        """
        Memasang style scrollbar global satu kali.
        """
        if self._installed or self._sedang_refresh:
            return

        app_aktif = app or QApplication.instance()

        if app_aktif is None:
            return

        self._sedang_refresh = True

        try:
            stylesheet_lama = app_aktif.styleSheet()
            stylesheet_baru = self._stylesheet_gabungan(
                stylesheet_lama
            )

            if stylesheet_baru != stylesheet_lama:
                app_aktif.setStyleSheet(stylesheet_baru)

            self._app = app_aktif
            self._installed = True
        except RuntimeError:
            return
        finally:
            self._sedang_refresh = False

    def uninstall(self) -> None:
        """
        Menghapus blok QSS scrollbar tanpa mengubah stylesheet lainnya.
        """
        app = self._app

        if app is not None:
            try:
                stylesheet_lama = app.styleSheet()
                stylesheet_bersih = self._hapus_blok_lama(
                    stylesheet_lama
                )

                if stylesheet_bersih != stylesheet_lama:
                    app.setStyleSheet(stylesheet_bersih)
            except RuntimeError:
                pass

        self._app = None
        self._installed = False
        self._sedang_refresh = False

    def terapkan_ke_scrollbar(
        self,
        scrollbar: QScrollBar,
        force: bool = False,
    ) -> None:
        """
        API kompatibilitas untuk pemanggil lama.

        Tidak menempelkan style per-widget dan tidak memicu restyle global.
        """
        if not isinstance(scrollbar, QScrollBar):
            return

        if not self._installed:
            self.install()

        try:
            scrollbar.update()
        except RuntimeError:
            pass

    def refresh_semua(
        self,
        force: bool = False,
    ) -> None:
        """
        API kompatibilitas.

        Style netral tidak berubah saat tema berganti, sehingga metode ini tidak
        memanggil QApplication.setStyleSheet() ulang.
        """
        if not self._installed:
            self.install()
