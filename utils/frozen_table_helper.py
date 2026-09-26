# utils/frozen_table_helper.py
from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsDropShadowEffect,
    QHeaderView,
    QTableView,
    QTableWidget,
)

class FrozenTableWidget(QTableWidget):
    """QTableWidget dengan view bayangan untuk membekukan kolom kiri."""

    def __init__(self, frozen_cols=2, fixed_cols=None, fixed_widths=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frozen_cols = frozen_cols
        self.fixed_cols = fixed_cols or []
        self.fixed_widths = fixed_widths or {}
        self._syncing_frozen_geometry = False

        self.frozen_table = QTableView(self)
        self._konfigurasi_frozen_table()
        self._konfigurasi_shadow()
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

    def _konfigurasi_shadow(self):
        self.shadow_effect = QGraphicsDropShadowEffect(self)
        self.shadow_effect.setBlurRadius(15)
        self.shadow_effect.setXOffset(5)
        self.shadow_effect.setYOffset(0)
        self.shadow_effect.setColor(QColor(0, 0, 0, 60))
        self.shadow_effect.setEnabled(False)
        self.frozen_table.setGraphicsEffect(self.shadow_effect)

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

        main_vheader.sectionResized.connect(self._sinkronkan_tinggi_baris_ke_frozen)
        frozen_vheader.sectionResized.connect(self._sinkronkan_tinggi_baris_ke_main)
        main_scroll.valueChanged.connect(frozen_scroll.setValue)
        frozen_scroll.valueChanged.connect(main_scroll.setValue)
        main_scroll.rangeChanged.connect(frozen_scroll.setRange)
        self.horizontalScrollBar().valueChanged.connect(self.update_shadow)

    def _sinkronkan_tinggi_header(self):
        self.update_frozen_geometry()

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

    def update_shadow(self, value):
        self.shadow_effect.setEnabled(value > 0)

    def update_section_width(self, logicalIndex, oldSize, newSize):
        if logicalIndex >= self.frozen_cols:
            return

        # sectionResized dipancarkan oleh QHeaderView, bukan QTableView.
        # Blokir header tujuan agar sinkronisasi tidak memantul balik.
        frozen_header = self.frozen_table.horizontalHeader()
        blocker = QSignalBlocker(frozen_header)
        self.frozen_table.setColumnWidth(logicalIndex, newSize)
        del blocker
        self.update_frozen_geometry()

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
        self.update_frozen_geometry()

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
        finally:
            self._syncing_frozen_geometry = False

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.update_frozen_geometry)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.update_frozen_geometry)

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
            self.update_frozen_geometry()

    def setSelectionMode(self, mode):
        super().setSelectionMode(mode)
        self.frozen_table.setSelectionMode(mode)

    def setSelectionBehavior(self, behavior):
        super().setSelectionBehavior(behavior)
        self.frozen_table.setSelectionBehavior(behavior)