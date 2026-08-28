
"""Manajemen theme berbasis scope widget.

QSS pyqtdarktheme sengaja TIDAK dipasang ulang ke QApplication saat toggle.
Global QApplication hanya menyimpan state theme/palette, sedangkan stylesheet
berat diterapkan pada widget yang sedang terlihat. Dengan begitu tab yang sudah
pernah dibuat tetapi sedang tersembunyi tidak ikut di-repolish oleh Qt.
"""

from __future__ import annotations

import re
from typing import Dict

import qdarktheme
from PySide6.QtWidgets import QApplication, QWidget

from themes.base import get_base_style, get_main_tabs_base_style
from themes.shell import get_main_shell_styles
from themes.components.inputs import get_global_focus_qss


_COMMENT_RE = re.compile(r"/\*.*?\*/", flags=re.DOTALL)


def _ringkas_qss(qss: str) -> str:
    """Buang komentar dan whitespace yang tidak dibutuhkan oleh parser QSS."""
    if not qss:
        return ""

    tanpa_komentar = _COMMENT_RE.sub("", str(qss))
    return "\n".join(
        baris.strip()
        for baris in tanpa_komentar.splitlines()
        if baris.strip()
    )


class ThemeManager:
    """Cache dan terapkan theme hanya pada scope yang memang perlu di-refresh."""

    _cache_qdark: Dict[str, str] = {}
    _cache_widget_qss: Dict[str, str] = {}
    _cache_shell_qss: Dict[str, str] = {}
    _cache_shell_container_qss: Dict[str, str] = {}

    _SCOPED_MODE_PROPERTY = "_theme_manager_scoped_mode"
    _WIDGET_KEY_PROPERTY = "_theme_manager_widget_key"
    _SHELL_KEY_PROPERTY = "_theme_manager_shell_key"
    _SHELL_CONTAINER_KEY_PROPERTY = "_theme_manager_shell_container_key"

    @classmethod
    def _qdark_stylesheet(cls, tema: str) -> str:
        qss = cls._cache_qdark.get(tema)
        if qss is None:
            qss = _ringkas_qss(qdarktheme.load_stylesheet(tema))
            cls._cache_qdark[tema] = qss
        return qss

    @classmethod
    def _widget_stylesheet(cls, tema: str, is_dark: bool) -> str:
        """Bangun QSS baseline; responsive geometry bukan tugas ThemeManager."""
        _ = is_dark
        cached = cls._cache_widget_qss.get(tema)
        if cached is not None:
            return cached

        qss = _ringkas_qss(
            "\n".join(
                (
                    cls._qdark_stylesheet(tema),
                    get_base_style(),
                    get_global_focus_qss(),
                )
            )
        )
        cls._cache_widget_qss[tema] = qss
        return qss

    @classmethod
    def _shell_stylesheet(cls, tema: str, is_dark: bool) -> str:
        cached = cls._cache_shell_qss.get(tema)
        if cached is not None:
            return cached

        qss = _ringkas_qss(get_main_shell_styles(is_dark))
        cls._cache_shell_qss[tema] = qss
        return qss

    @classmethod
    def _shell_container_stylesheet(
        cls,
        tema: str,
        is_dark: bool,
    ) -> str:
        """Bangun QSS shell baseline; scaling dilakukan ResponsiveUIScaler."""
        cached = cls._cache_shell_container_qss.get(tema)
        if cached is not None:
            return cached

        qss = _ringkas_qss(
            "\n".join(
                (
                    cls._qdark_stylesheet(tema),
                    get_base_style(),
                    cls._shell_stylesheet(tema, is_dark),
                    get_global_focus_qss(),
                )
            )
        )
        cls._cache_shell_container_qss[tema] = qss
        return qss

    @staticmethod
    def _property_text(widget: QWidget, name: str) -> str:
        try:
            value = widget.property(name)
        except RuntimeError:
            return ""
        return "" if value is None else str(value)

    @classmethod
    def _pasang_stylesheet_jika_berubah(
        cls,
        widget: QWidget,
        qss: str,
        *,
        property_name: str,
        target_key: str,
    ) -> bool:
        if widget is None:
            return False

        if cls._property_text(widget, property_name) == target_key:
            return False

        try:
            widget.setStyleSheet(qss)
            widget.setProperty(property_name, target_key)
            return True
        except RuntimeError:
            return False

    @classmethod
    def apply_theme(
        cls,
        app: QApplication,
        is_dark: bool,
        scale: float = 1.0,
    ) -> None:
        """Sinkronkan state theme aplikasi tanpa global ``setStyleSheet``.

        Nama method dipertahankan agar kompatibel dengan caller lama. Dalam mode
        scoped, QSS berat diterapkan lewat :meth:`apply_widget_theme` dan
        :meth:`apply_shell_theme`.
        """
        if app is None:
            return

        tema = "dark" if is_dark else "light"
        _ = scale  # kompatibilitas API; geometry ditangani ResponsiveUIScaler
        app.setProperty("theme", tema)

        if not bool(app.property(cls._SCOPED_MODE_PROPERTY)):
            if app.styleSheet():
                app.setStyleSheet("")
            app.setProperty(cls._SCOPED_MODE_PROPERTY, True)

        app.setProperty("_base_style_terpasang", True)

    @classmethod
    def apply_widget_theme(
        cls,
        widget: QWidget,
        is_dark: bool,
        scale: float = 1.0,
    ) -> bool:
        """Terapkan pyqtdarktheme hanya ke satu subtree widget yang aktif."""
        if widget is None:
            return False

        tema = "dark" if is_dark else "light"
        _ = scale  # kompatibilitas API; tidak menjadi bagian cache QSS
        target_key = tema
        qss = cls._widget_stylesheet(tema, is_dark)

        return cls._pasang_stylesheet_jika_berubah(
            widget,
            qss,
            property_name=cls._WIDGET_KEY_PROPERTY,
            target_key=target_key,
        )

    @classmethod
    def apply_shell_theme(
        cls,
        tabs: QWidget,
        tab_bar: QWidget,
        top_right: QWidget,
        is_dark: bool,
        scale: float = 1.0,
    ) -> None:
        """Refresh hanya widget shell utama, bukan seluruh isi tab tersembunyi."""
        tema = "dark" if is_dark else "light"
        _ = scale  # kompatibilitas API; geometry ditangani ResponsiveUIScaler

        # Visual tab qdarktheme + geometry baseline disusun oleh themes.base.
        tabs_qss = _ringkas_qss(
            get_main_tabs_base_style(
                is_dark,
                qdark_stylesheet=cls._qdark_stylesheet(tema),
            )
        )
        cls._pasang_stylesheet_jika_berubah(
            tabs,
            tabs_qss,
            property_name=cls._SHELL_KEY_PROPERTY,
            target_key=f"tabs:{tema}",
        )

        cls._pasang_stylesheet_jika_berubah(
            tab_bar,
            tabs_qss,
            property_name=cls._SHELL_KEY_PROPERTY,
            target_key=f"tabbar:{tema}",
        )

        container_key = tema
        container_qss = cls._shell_container_stylesheet(
            tema,
            is_dark,
        )
        cls._pasang_stylesheet_jika_berubah(
            top_right,
            container_qss,
            property_name=cls._SHELL_CONTAINER_KEY_PROPERTY,
            target_key=container_key,
        )

    @classmethod
    def bersihkan_cache(cls) -> None:
        cls._cache_qdark.clear()
        cls._cache_widget_qss.clear()
        cls._cache_shell_qss.clear()
        cls._cache_shell_container_qss.clear()