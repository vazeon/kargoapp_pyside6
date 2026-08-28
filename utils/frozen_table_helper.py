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

        self.frozen_table = QTableView(self)
        self._konfigurasi_frozen_table()
        self._konfigurasi_shadow()
        self._hubungkan_sinkronisasi()

    def _konfigurasi_frozen_table(self):
        frozen = self.frozen_table
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
        main_header.sectionResized.connect(self.update_section_width)
        frozen_header.sectionResized.connect(self.update_main_section_width)

        main_vheader.sectionResized.connect(self._sinkronkan_tinggi_baris_ke_frozen)
        frozen_vheader.sectionResized.connect(self._sinkronkan_tinggi_baris_ke_main)
        main_scroll.valueChanged.connect(frozen_scroll.setValue)
        frozen_scroll.valueChanged.connect(main_scroll.setValue)
        main_scroll.rangeChanged.connect(frozen_scroll.setRange)
        self.horizontalScrollBar().valueChanged.connect(self.update_shadow)

    def _sinkronkan_tinggi_header(self):
        self.frozen_table.horizontalHeader().setFixedHeight(self.horizontalHeader().height())

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
        total_w = sum(
            self.columnWidth(col)
            for col in range(self.frozen_cols)
            if not self.isColumnHidden(col)
        )
        header_height = self.horizontalHeader().height()
        self.frozen_table.horizontalHeader().setFixedHeight(header_height)
        self.frozen_table.setGeometry(
            self.verticalHeader().width() + self.frameWidth(),
            self.frameWidth(),
            total_w,
            self.viewport().height() + header_height,
        )

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

    def setColumnWidth(self, column, width):
        super().setColumnWidth(column, width)
        if column < self.frozen_cols:
            self.frozen_table.setColumnWidth(column, width)
            self.update_frozen_geometry()

    def setRowHidden(self, row, hide):
        super().setRowHidden(row, hide)
        self.frozen_table.setRowHidden(row, hide)

    def setStyleSheet(self, styleSheet):
        style_frozen = styleSheet.replace("QTableWidget", "QTableView")
        css_center_checkbox = """
            QTableWidget::indicator, QTableView::indicator {{
                subcontrol-origin: padding;
                subcontrol-position: center;
            }}
        """
        self.frozen_table.setStyleSheet(style_frozen + css_center_checkbox)
        self.frozen_table.setPalette(self.palette())
        self.frozen_table.setGridStyle(self.gridStyle())
        super().setStyleSheet(styleSheet + css_center_checkbox)

    def setSelectionMode(self, mode):
        super().setSelectionMode(mode)
        self.frozen_table.setSelectionMode(mode)

    def setSelectionBehavior(self, behavior):
        super().setSelectionBehavior(behavior)
        self.frozen_table.setSelectionBehavior(behavior)