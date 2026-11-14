# utils/frozen_table_helper.py
from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QTableView,
    QTableWidget,
)

from utils.table_helper import pasang_header_wrap


_FROZEN_GEOMETRY_UPDATE_INTERVAL_MS = 16


def _buat_timer_geometri_frozen(owner):
    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.setInterval(_FROZEN_GEOMETRY_UPDATE_INTERVAL_MS)
    timer.timeout.connect(owner.update_frozen_geometry)
    owner._frozen_geometry_timer = timer


def _set_frozen_separator_color(owner):
    separator = getattr(owner, "frozen_separator", None)
    if separator is None:
        return

    # QFrame dengan Shadow.Plain menggambar garis memakai WindowText.
    # Gunakan warna lebih kontras agar batas frozen mudah dikenali.
    base = owner.palette().color(QPalette.ColorRole.Base)
    luminance = (base.red() * 299 + base.green() * 587 + base.blue() * 114) / 1000
    line_color = QColor("#A8B8CC" if luminance < 128 else "#64748B")
    palette = separator.palette()
    palette.setColor(QPalette.ColorRole.WindowText, line_color)
    palette.setColor(QPalette.ColorRole.Text, line_color)
    palette.setColor(QPalette.ColorRole.Mid, line_color)
    separator.setPalette(palette)


def _position_frozen_separator(owner):
    """Posisikan separator hanya saat geometri frozen view berubah."""
    separator = getattr(owner, "frozen_separator", None)
    frozen = getattr(owner, "frozen_table", None)
    if separator is None or frozen is None:
        return

    rect = frozen.geometry()
    if rect.width() <= 0 or rect.height() <= 0:
        if not separator.isHidden():
            separator.hide()
        return

    separator_width = 2
    target = (
        rect.x() + rect.width() - separator_width,
        rect.y(),
        separator_width,
        rect.height(),
    )
    current = separator.geometry()
    current_geometry = (
        current.x(), current.y(), current.width(), current.height()
    )
    if current_geometry != target:
        separator.setGeometry(*target)
    # Dipanggil hanya saat layout/ukuran berubah, bukan pada setiap pixel scroll.
    separator.raise_()


def _update_frozen_separator(owner):
    """Ubah visibilitas hanya ketika state berubah; scroll tidak perlu raise_()."""
    separator = getattr(owner, "frozen_separator", None)
    if separator is None:
        return

    visible = (
        owner.horizontalScrollBar().value() > 0
        and getattr(owner, "frozen_cols", 0) > 0
    )
    if visible:
        if separator.isHidden():
            separator.show()
            separator.raise_()
    elif not separator.isHidden():
        separator.hide()

class FrozenTableWidget(QTableWidget):
    """QTableWidget dengan view bayangan untuk membekukan kolom kiri."""

    def __init__(self, frozen_cols=2, fixed_cols=None, fixed_widths=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frozen_cols = frozen_cols
        self.fixed_cols = fixed_cols or []
        self.fixed_widths = fixed_widths or {}
        self._syncing_frozen_geometry = False
        _buat_timer_geometri_frozen(self)

        self.frozen_table = QTableView(self)
        self._konfigurasi_frozen_table()
        self._konfigurasi_separator()
        self._hubungkan_sinkronisasi()

    def _konfigurasi_frozen_table(self):
        frozen = self.frozen_table
        # Penanda agar lapisan tema mengenali view kolom beku.
        frozen.setProperty("tableFrozenView", True)
        frozen.setFrameShape(QFrame.Shape.NoFrame)
        frozen.setModel(self.model())
        frozen.setSelectionModel(self.selectionModel())
        frozen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        frozen.verticalHeader().hide()

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        frozen.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.viewport().stackUnder(frozen)

        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        frozen.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.setAlternatingRowColors(True)
        frozen.show()

        frozen.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        frozen.horizontalHeader().customContextMenuRequested.connect(
            self.horizontalHeader().customContextMenuRequested.emit
        )
        frozen.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        frozen.customContextMenuRequested.connect(self.customContextMenuRequested.emit)
        pasang_header_wrap(self)

    def _konfigurasi_separator(self):
        """Siapkan garis pemisah native 2 px tanpa graphics effect."""
        self.shadow_effect = None  # kompatibilitas API lama
        self.frozen_separator = QFrame(self)
        self.frozen_separator.setFrameShape(QFrame.Shape.VLine)
        self.frozen_separator.setFrameShadow(QFrame.Shadow.Plain)
        self.frozen_separator.setLineWidth(2)
        self.frozen_separator.setMidLineWidth(0)
        self.frozen_separator.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.frozen_separator.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _set_frozen_separator_color(self)
        self.frozen_separator.hide()

    def _perbarui_warna_separator(self):
        _set_frozen_separator_color(self)

    def _posisikan_separator(self):
        _position_frozen_separator(self)

    def _perbarui_separator(self, *_args):
        _update_frozen_separator(self)

    def _hubungkan_sinkronisasi(self):
        frozen = self.frozen_table
        main_header = self.horizontalHeader()
        frozen_header = frozen.horizontalHeader()
        main_vheader = self.verticalHeader()
        frozen_vheader = frozen.verticalHeader()
        main_scroll = self.verticalScrollBar()
        frozen_scroll = frozen.verticalScrollBar()

        main_header.geometriesChanged.connect(self._sinkronkan_tinggi_header)
        frozen_header.geometriesChanged.connect(self._sinkronkan_tinggi_header)
        main_header.sectionResized.connect(self.update_section_width)
        frozen_header.sectionResized.connect(self.update_main_section_width)
        wrap_signal = getattr(main_header, "wrapHeightChanged", None)
        if wrap_signal is not None:
            wrap_signal.connect(self._jadwalkan_update_frozen_geometry)

        main_vheader.sectionResized.connect(self._sinkronkan_tinggi_baris_ke_frozen)
        frozen_vheader.sectionResized.connect(self._sinkronkan_tinggi_baris_ke_main)
        main_scroll.valueChanged.connect(frozen_scroll.setValue)
        frozen_scroll.valueChanged.connect(main_scroll.setValue)
        main_scroll.rangeChanged.connect(frozen_scroll.setRange)
        self.horizontalScrollBar().valueChanged.connect(self._perbarui_separator)
        self.horizontalScrollBar().rangeChanged.connect(self._perbarui_separator)

    def _jadwalkan_update_frozen_geometry(self, *_args):
        if self._syncing_frozen_geometry:
            return
        timer = getattr(self, "_frozen_geometry_timer", None)
        if timer is not None and not timer.isActive():
            timer.start()

    def _sinkronkan_tinggi_header(self):
        self._jadwalkan_update_frozen_geometry()

    def _sinkronkan_tinggi_baris_ke_frozen(self, logical_index, _old_size, new_size):
        frozen_vheader = self.frozen_table.verticalHeader()
        blocker = QSignalBlocker(frozen_vheader)
        frozen_vheader.resizeSection(logical_index, new_size)
        del blocker

    def _sinkronkan_tinggi_baris_ke_main(self, logical_index, _old_size, new_size):
        main_vheader = self.verticalHeader()
        blocker = QSignalBlocker(main_vheader)
        main_vheader.resizeSection(logical_index, new_size)
        del blocker

    def update_shadow(self, _value):
        """Kompatibilitas API lama; indikator sekarang berupa garis 2 px."""
        self._perbarui_separator()

    def update_section_width(self, logicalIndex, oldSize, newSize):
        if logicalIndex >= self.frozen_cols:
            return

        # sectionResized dipancarkan oleh QHeaderView, bukan QTableView.
        # Blokir header tujuan agar sinkronisasi tidak memantul balik.
        frozen_header = self.frozen_table.horizontalHeader()
        blocker = QSignalBlocker(frozen_header)
        self.frozen_table.setColumnWidth(logicalIndex, newSize)
        del blocker
        self._jadwalkan_update_frozen_geometry()

    def update_main_section_width(self, logicalIndex, oldSize, newSize):
        if logicalIndex >= self.frozen_cols:
            return

        main_header = self.horizontalHeader()
        frozen_header = self.frozen_table.horizontalHeader()
        blocker_main = QSignalBlocker(main_header)
        blocker_frozen = QSignalBlocker(frozen_header)
        self.setColumnWidth(logicalIndex, newSize)
        del blocker_frozen
        del blocker_main
        self._jadwalkan_update_frozen_geometry()

    def update_frozen_geometry(self):
        """Sejajarkan viewport kedua view, termasuk inset nyata dari style Qt."""
        frozen = getattr(self, "frozen_table", None)
        if frozen is None or self._syncing_frozen_geometry:
            return

        self._syncing_frozen_geometry = True
        try:
            total_w = sum(
                self.columnWidth(col)
                for col in range(min(self.frozen_cols, self.columnCount()))
                if not self.isColumnHidden(col)
            )

            header = self.horizontalHeader()
            frozen_header = frozen.horizontalHeader()
            header_height = 0 if header.isHidden() else header.height()
            frozen_header.setVisible(not header.isHidden())
            frozen_header.setFixedHeight(header_height)
            frozen_header.setHighlightSections(header.highlightSections())
            frozen_header.setSectionsClickable(header.sectionsClickable())

            # QSS/tema dapat memberi inset di luar tinggi header. Ukur viewport
            # view beku sendiri; jangan menganggap offset-nya (0, header_height).
            # Ulangi terbatas karena perubahan ukuran dapat memicu layout Qt lagi.
            for _ in range(3):
                frozen.updateGeometries()
                main_rect = self.viewport().geometry()
                frozen_rect = frozen.viewport().geometry()
                left = frozen_rect.x()
                top = frozen_rect.y()
                right = max(0, frozen.width() - left - frozen_rect.width())
                bottom = max(0, frozen.height() - top - frozen_rect.height())
                target = (
                    main_rect.x() - left,
                    main_rect.y() - top,
                    total_w + left + right,
                    main_rect.height() + top + bottom,
                )
                current = (frozen.x(), frozen.y(), frozen.width(), frozen.height())
                if current == target:
                    break
                frozen.setGeometry(*target)

            frozen.raise_()
            self._posisikan_separator()
            self._perbarui_separator()
        finally:
            self._syncing_frozen_geometry = False

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.update_frozen_geometry)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._jadwalkan_update_frozen_geometry()

    def scrollTo(self, index, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        if index.column() >= self.frozen_cols:
            super().scrollTo(index, hint)

    def setColumnCount(self, count):
        super().setColumnCount(count)
        for col in range(self.frozen_cols, count):
            self.frozen_table.setColumnHidden(col, True)

        if count <= 0:
            self.update_frozen_geometry()
            return
        for col in self.fixed_cols:
            if col >= count:
                continue
            self.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.frozen_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Fixed
            )
            if col in self.fixed_widths:
                width = self.fixed_widths[col]
                self.setColumnWidth(col, width)
                self.frozen_table.setColumnWidth(col, width)

        self.update_frozen_geometry()

    def setColumnWidth(self, column, width):
        super().setColumnWidth(column, width)
        if column < self.frozen_cols:
            self.frozen_table.setColumnWidth(column, width)
            self.update_frozen_geometry()

    def setRowHidden(self, row, hide):
        super().setRowHidden(row, hide)
        self.frozen_table.setRowHidden(row, hide)

    def setColumnHidden(self, column, hide):
        super().setColumnHidden(column, hide)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setColumnHidden(column, hide or column >= self.frozen_cols)
            self.update_frozen_geometry()

    def setWordWrap(self, enabled):
        super().setWordWrap(enabled)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setWordWrap(enabled)

    def setEditTriggers(self, triggers):
        super().setEditTriggers(triggers)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setEditTriggers(triggers)

    def setStyleSheet(self, styleSheet):
        # Helper hanya menyinkronkan; isi QSS sepenuhnya milik lapisan tema.
        super().setStyleSheet(styleSheet)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setStyleSheet(styleSheet)
            frozen.setPalette(self.palette())
            frozen.setGridStyle(self.gridStyle())
            self._perbarui_warna_separator()
            self.update_frozen_geometry()

    def setSelectionMode(self, mode):
        super().setSelectionMode(mode)
        self.frozen_table.setSelectionMode(mode)

    def setSelectionBehavior(self, behavior):
        super().setSelectionBehavior(behavior)
        self.frozen_table.setSelectionBehavior(behavior)

class FrozenTableView(QTableView):
    """QTableView dengan overlay kolom kiri beku untuk model berbasis QAbstractItemModel.

    Kelas ini menjadi pasangan QTableView dari FrozenTableWidget. Model dan
    selection model dibagi dengan view utama; hanya kolom yang dibekukan yang
    dirender pada view overlay.
    """

    def __init__(
        self,
        *args,
        frozen_cols=1,
        fixed_cols=None,
        fixed_widths=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.frozen_cols = max(0, int(frozen_cols))
        self.fixed_cols = tuple(fixed_cols or ())
        self.fixed_widths = dict(fixed_widths or {})
        self._syncing_frozen_geometry = False
        _buat_timer_geometri_frozen(self)

        self.frozen_table = QTableView(self)
        self._konfigurasi_frozen_table()
        self._konfigurasi_separator()
        self._hubungkan_sinkronisasi()

        if self.model() is not None:
            self._pasang_model_ke_frozen(self.model())

    def _konfigurasi_frozen_table(self):
        frozen = self.frozen_table
        frozen.setProperty("tableFrozenView", True)
        frozen.setFrameShape(QFrame.Shape.NoFrame)
        frozen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        frozen.verticalHeader().hide()
        frozen.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        frozen.setAlternatingRowColors(self.alternatingRowColors())
        frozen.setShowGrid(self.showGrid())
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.viewport().stackUnder(frozen)
        frozen.show()

        # Kebijakan context menu dipasang di sini; handler aplikasi dapat
        # mengikat event view beku secara langsung agar kolom/logical row tepat.
        frozen.horizontalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        frozen.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        pasang_header_wrap(self)

    def _konfigurasi_separator(self):
        """Siapkan garis pemisah native 2 px tanpa graphics effect."""
        self.shadow_effect = None  # kompatibilitas API lama
        self.frozen_separator = QFrame(self)
        self.frozen_separator.setFrameShape(QFrame.Shape.VLine)
        self.frozen_separator.setFrameShadow(QFrame.Shadow.Plain)
        self.frozen_separator.setLineWidth(2)
        self.frozen_separator.setMidLineWidth(0)
        self.frozen_separator.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.frozen_separator.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _set_frozen_separator_color(self)
        self.frozen_separator.hide()

    def _perbarui_warna_separator(self):
        _set_frozen_separator_color(self)

    def _posisikan_separator(self):
        _position_frozen_separator(self)

    def _perbarui_separator(self, *_args):
        _update_frozen_separator(self)

    def _hubungkan_sinkronisasi(self):
        frozen = self.frozen_table
        main_header = self.horizontalHeader()
        frozen_header = frozen.horizontalHeader()
        main_vheader = self.verticalHeader()
        frozen_vheader = frozen.verticalHeader()
        main_scroll = self.verticalScrollBar()
        frozen_scroll = frozen.verticalScrollBar()

        main_header.geometriesChanged.connect(self._jadwalkan_update_frozen_geometry)
        frozen_header.geometriesChanged.connect(self._jadwalkan_update_frozen_geometry)
        main_header.sectionResized.connect(self.update_section_width)
        frozen_header.sectionResized.connect(self.update_main_section_width)
        wrap_signal = getattr(main_header, "wrapHeightChanged", None)
        if wrap_signal is not None:
            wrap_signal.connect(self._jadwalkan_update_frozen_geometry)
        main_vheader.sectionResized.connect(self._sinkronkan_tinggi_baris_ke_frozen)
        frozen_vheader.sectionResized.connect(self._sinkronkan_tinggi_baris_ke_main)
        main_scroll.valueChanged.connect(frozen_scroll.setValue)
        frozen_scroll.valueChanged.connect(main_scroll.setValue)
        main_scroll.rangeChanged.connect(frozen_scroll.setRange)
        self.horizontalScrollBar().valueChanged.connect(self._perbarui_separator)
        self.horizontalScrollBar().rangeChanged.connect(self._perbarui_separator)

    def _pasang_model_ke_frozen(self, model):
        frozen = self.frozen_table
        if model is None:
            return
        frozen.setModel(model)
        pasang_header_wrap(self)
        selection_model = self.selectionModel()
        if selection_model is not None:
            frozen.setSelectionModel(selection_model)
        frozen.verticalHeader().hide()
        frozen.verticalHeader().setDefaultSectionSize(
            self.verticalHeader().defaultSectionSize()
        )
        self._sync_frozen_columns()
        self._sync_frozen_view_options()
        QTimer.singleShot(0, self.update_frozen_geometry)

    def setModel(self, model):
        super().setModel(model)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None and model is not None:
            self._pasang_model_ke_frozen(model)

    def setSelectionModel(self, selection_model):
        super().setSelectionModel(selection_model)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None and selection_model is not None:
            if frozen.model() is self.model():
                frozen.setSelectionModel(selection_model)

    def _jadwalkan_update_frozen_geometry(self, *_args):
        if self._syncing_frozen_geometry:
            return
        timer = getattr(self, "_frozen_geometry_timer", None)
        if timer is not None and not timer.isActive():
            timer.start()

    def _jumlah_kolom_model(self):
        model = self.model()
        return model.columnCount() if model is not None else 0

    def sync_frozen_columns(self):
        """Sinkronkan visibilitas/ukuran kolom setelah model di-reset."""
        self._sync_frozen_columns()
        self.update_frozen_geometry()

    def _sync_frozen_columns(self):
        frozen = getattr(self, "frozen_table", None)
        if frozen is None:
            return
        count = self._jumlah_kolom_model()
        for column in range(count):
            is_frozen = column < self.frozen_cols and not self.isColumnHidden(column)
            frozen.setColumnHidden(column, not is_frozen)
            if is_frozen:
                frozen.setColumnWidth(column, self.columnWidth(column))

        for column in self.fixed_cols:
            if 0 <= column < count:
                self.horizontalHeader().setSectionResizeMode(
                    column, QHeaderView.ResizeMode.Fixed
                )
                frozen.horizontalHeader().setSectionResizeMode(
                    column, QHeaderView.ResizeMode.Fixed
                )
                if column in self.fixed_widths:
                    width = int(self.fixed_widths[column])
                    self.setColumnWidth(column, width)

    def _sync_frozen_view_options(self):
        frozen = getattr(self, "frozen_table", None)
        if frozen is None:
            return
        frozen.setWordWrap(self.wordWrap())
        frozen.setTextElideMode(self.textElideMode())
        frozen.setEditTriggers(self.editTriggers())
        frozen.setSelectionMode(self.selectionMode())
        frozen.setSelectionBehavior(self.selectionBehavior())
        frozen.setAlternatingRowColors(self.alternatingRowColors())
        frozen.setShowGrid(self.showGrid())
        frozen.setGridStyle(self.gridStyle())
        frozen.setMouseTracking(self.hasMouseTracking())
        frozen.setVerticalScrollMode(self.verticalScrollMode())
        frozen.setHorizontalScrollMode(self.horizontalScrollMode())
        frozen.setFont(self.font())
        frozen.setPalette(self.palette())
        frozen.setStyleSheet(self.styleSheet())
        self._perbarui_warna_separator()

    def _sinkronkan_tinggi_baris_ke_frozen(self, logical_index, _old_size, new_size):
        frozen_vheader = self.frozen_table.verticalHeader()
        blocker = QSignalBlocker(frozen_vheader)
        frozen_vheader.resizeSection(logical_index, new_size)
        del blocker

    def _sinkronkan_tinggi_baris_ke_main(self, logical_index, _old_size, new_size):
        main_vheader = self.verticalHeader()
        blocker = QSignalBlocker(main_vheader)
        main_vheader.resizeSection(logical_index, new_size)
        del blocker

    def update_shadow(self, _value):
        """Kompatibilitas API lama; indikator sekarang berupa garis 2 px."""
        self._perbarui_separator()

    def update_section_width(self, logical_index, _old_size, new_size):
        if logical_index >= self.frozen_cols:
            return
        frozen_header = self.frozen_table.horizontalHeader()
        blocker = QSignalBlocker(frozen_header)
        self.frozen_table.setColumnWidth(logical_index, new_size)
        del blocker
        self._jadwalkan_update_frozen_geometry()

    def update_main_section_width(self, logical_index, _old_size, new_size):
        if logical_index >= self.frozen_cols:
            return
        main_header = self.horizontalHeader()
        frozen_header = self.frozen_table.horizontalHeader()
        blocker_main = QSignalBlocker(main_header)
        blocker_frozen = QSignalBlocker(frozen_header)
        super().setColumnWidth(logical_index, new_size)
        del blocker_frozen
        del blocker_main
        self._jadwalkan_update_frozen_geometry()

    def update_frozen_geometry(self):
        frozen = getattr(self, "frozen_table", None)
        if frozen is None or self._syncing_frozen_geometry:
            return

        self._syncing_frozen_geometry = True
        try:
            total_width = sum(
                self.columnWidth(column)
                for column in range(min(self.frozen_cols, self._jumlah_kolom_model()))
                if not self.isColumnHidden(column)
            )
            main_header = self.horizontalHeader()
            frozen_header = frozen.horizontalHeader()
            header_height = 0 if main_header.isHidden() else main_header.height()
            frozen_header.setVisible(not main_header.isHidden())
            frozen_header.setFixedHeight(header_height)
            frozen_header.setHighlightSections(main_header.highlightSections())
            frozen_header.setSectionsClickable(main_header.sectionsClickable())
            frozen_header.setSectionsMovable(main_header.sectionsMovable())

            for _ in range(3):
                frozen.updateGeometries()
                main_rect = self.viewport().geometry()
                frozen_rect = frozen.viewport().geometry()
                left = frozen_rect.x()
                top = frozen_rect.y()
                right = max(0, frozen.width() - left - frozen_rect.width())
                bottom = max(0, frozen.height() - top - frozen_rect.height())
                target = (
                    main_rect.x() - left,
                    main_rect.y() - top,
                    total_width + left + right,
                    main_rect.height() + top + bottom,
                )
                current = (frozen.x(), frozen.y(), frozen.width(), frozen.height())
                if current == target:
                    break
                frozen.setGeometry(*target)

            frozen.raise_()
            self._posisikan_separator()
            self._perbarui_separator()
        finally:
            self._syncing_frozen_geometry = False

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.update_frozen_geometry)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._jadwalkan_update_frozen_geometry()

    def scrollTo(self, index, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        if not index.isValid():
            return
        if index.column() < self.frozen_cols and self._jumlah_kolom_model() > self.frozen_cols:
            target = self.model().index(index.row(), self.frozen_cols)
            if target.isValid():
                super().scrollTo(target, hint)
                return
        super().scrollTo(index, hint)

    def setColumnWidth(self, column, width):
        super().setColumnWidth(column, width)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None and column < self.frozen_cols:
            blocker = QSignalBlocker(frozen.horizontalHeader())
            frozen.setColumnWidth(column, width)
            del blocker
            self.update_frozen_geometry()

    def setColumnHidden(self, column, hide):
        super().setColumnHidden(column, hide)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None and 0 <= column < self._jumlah_kolom_model():
            frozen.setColumnHidden(column, bool(hide) or column >= self.frozen_cols)
            self.update_frozen_geometry()

    def setRowHidden(self, row, hide):
        super().setRowHidden(row, hide)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None and frozen.model() is self.model():
            frozen.setRowHidden(row, hide)

    def setRowHeight(self, row, height):
        # Main verticalHeader.sectionResized sudah terhubung ke
        # _sinkronkan_tinggi_baris_ke_frozen(). Jangan resize overlay sekali
        # lagi di sini; itu menggandakan kerja untuk setiap baris multiline.
        header = self.verticalHeader()
        signals_blocked = header.signalsBlocked()
        super().setRowHeight(row, height)

        # Fallback untuk pemanggil yang sengaja memblokir sinyal header.
        # Jalur normal cukup memakai koneksi sectionResized di atas.
        if signals_blocked:
            self._sinkronkan_tinggi_baris_ke_frozen(row, 0, height)

    def setWordWrap(self, enabled):
        super().setWordWrap(enabled)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setWordWrap(enabled)

    def setTextElideMode(self, mode):
        super().setTextElideMode(mode)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setTextElideMode(mode)

    def setEditTriggers(self, triggers):
        super().setEditTriggers(triggers)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setEditTriggers(triggers)

    def setSelectionMode(self, mode):
        super().setSelectionMode(mode)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setSelectionMode(mode)

    def setSelectionBehavior(self, behavior):
        super().setSelectionBehavior(behavior)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setSelectionBehavior(behavior)

    def setAlternatingRowColors(self, enabled):
        super().setAlternatingRowColors(enabled)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setAlternatingRowColors(enabled)

    def setShowGrid(self, show):
        super().setShowGrid(show)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setShowGrid(show)

    def setGridStyle(self, style):
        super().setGridStyle(style)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setGridStyle(style)

    def setVerticalScrollMode(self, mode):
        super().setVerticalScrollMode(mode)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setVerticalScrollMode(mode)

    def setHorizontalScrollMode(self, mode):
        super().setHorizontalScrollMode(mode)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setHorizontalScrollMode(mode)

    def setUpdatesEnabled(self, enabled):
        super().setUpdatesEnabled(enabled)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setUpdatesEnabled(enabled)

    def setFont(self, font):
        super().setFont(font)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setFont(font)

    def setPalette(self, palette):
        super().setPalette(palette)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setPalette(palette)
        self._perbarui_warna_separator()
        self._perbarui_separator()

    def setStyleSheet(self, style_sheet):
        super().setStyleSheet(style_sheet)
        frozen = getattr(self, "frozen_table", None)
        if frozen is not None:
            frozen.setStyleSheet(style_sheet)
            frozen.setPalette(self.palette())
            frozen.setGridStyle(self.gridStyle())
            self._perbarui_warna_separator()
            self.update_frozen_geometry()
