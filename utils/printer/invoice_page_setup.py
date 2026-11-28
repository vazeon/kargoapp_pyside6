# utils/printer/invoice_page_setup.py
"""Dialog dan penyimpanan pengaturan halaman khusus Invoice."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import QSettings, Signal, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QSpinBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from utils.typography import APPLICATION_NAME, ORGANIZATION_NAME


_SETTINGS_GROUP = "invoice/page_setup"

# Dimensi disimpan dalam orientasi dasar/portrait. Orientation menentukan
# apakah halaman diputar ketika diterapkan ke QPageLayout.
_DEFAULT_SETTINGS: dict[str, Any] = {
    "paper_size": "NCR",
    "orientation": "landscape",
    "width_mm": 139.7,
    "height_mm": 241.3,
    "style_preset": "NCR",
    "margin_preset": "normal",
    "margins": {
        "top": 4.0,
        "bottom": 4.0,
        "left": 4.0,
        "right": 4.0,
    },
    "scaling": "actual",
    "print_gridlines": False,
    "repeat_header_rows": 1,
}


def _angka(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        result = float(default)
    return min(max(result, minimum), maximum)


def normalisasi_page_setup(settings: dict | None = None) -> dict:
    """Normalisasi konfigurasi halaman agar aman dipakai seluruh jalur cetak."""
    source = settings if isinstance(settings, dict) else {}
    result = deepcopy(_DEFAULT_SETTINGS)

    paper = str(source.get("paper_size", result["paper_size"])).upper()
    # A3 is no longer offered by Kargo. Migrate a previously saved A3 setting
    # to A4 so existing preferences remain valid after this update.
    if paper == "A3":
        paper = "A4"
    if paper not in {"A4", "NCR", "CUSTOM"}:
        paper = "NCR"
    result["paper_size"] = paper

    default_orientation = "landscape" if paper == "NCR" else "portrait"
    orientation = str(source.get("orientation", default_orientation)).lower()
    if orientation not in {"portrait", "landscape"}:
        orientation = default_orientation
    result["orientation"] = orientation

    if paper == "A4":
        default_width, default_height = 210.0, 297.0
        result["style_preset"] = "A4"
    elif paper == "NCR":
        default_width, default_height = 139.7, 241.3
        result["style_preset"] = "NCR"
    else:
        default_width, default_height = 210.0, 297.0
        style = str(source.get("style_preset", "A4")).upper()
        result["style_preset"] = style if style in {"A4", "NCR"} else "A4"

    result["width_mm"] = _angka(
        source.get("width_mm", default_width), default_width, 25.0, 1000.0
    )
    result["height_mm"] = _angka(
        source.get("height_mm", default_height), default_height, 25.0, 1000.0
    )

    margin_preset = str(source.get("margin_preset", "normal")).lower()
    if margin_preset not in {"normal", "narrow", "wide", "custom"}:
        margin_preset = "normal"
    result["margin_preset"] = margin_preset

    default_margin = 4.0 if paper == "NCR" else 8.0
    source_margins = source.get("margins", {})
    if not isinstance(source_margins, dict):
        source_margins = {}
    result["margins"] = {
        edge: _angka(source_margins.get(edge, default_margin), default_margin, 0.0, 100.0)
        for edge in ("top", "bottom", "left", "right")
    }
    scaling = str(source.get("scaling", "actual")).lower()
    result["scaling"] = scaling if scaling in {"actual", "fit_width"} else "actual"
    raw_gridlines = source.get("print_gridlines", False)
    if isinstance(raw_gridlines, str):
        raw_gridlines = raw_gridlines.strip().lower() in {"1", "true", "yes", "on"}
    result["print_gridlines"] = bool(raw_gridlines)
    result["repeat_header_rows"] = int(_angka(
        source.get("repeat_header_rows", 1), 1, 0, 20
    ))
    return result


def muat_page_setup() -> dict:
    """Muat pengaturan terakhir pengguna; default tetap NCR seperti perilaku lama."""
    settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
    settings.beginGroup(_SETTINGS_GROUP)
    raw = {
        "paper_size": settings.value("paper_size", _DEFAULT_SETTINGS["paper_size"]),
        "orientation": settings.value("orientation", _DEFAULT_SETTINGS["orientation"]),
        "width_mm": settings.value("width_mm", _DEFAULT_SETTINGS["width_mm"]),
        "height_mm": settings.value("height_mm", _DEFAULT_SETTINGS["height_mm"]),
        "style_preset": settings.value("style_preset", _DEFAULT_SETTINGS["style_preset"]),
        "margin_preset": settings.value("margin_preset", _DEFAULT_SETTINGS["margin_preset"]),
        "margins": {
            edge: settings.value(f"margins/{edge}", _DEFAULT_SETTINGS["margins"][edge])
            for edge in ("top", "bottom", "left", "right")
        },
        "scaling": settings.value("scaling", _DEFAULT_SETTINGS["scaling"]),
        "print_gridlines": settings.value("print_gridlines", _DEFAULT_SETTINGS["print_gridlines"]),
        "repeat_header_rows": settings.value("repeat_header_rows", _DEFAULT_SETTINGS["repeat_header_rows"]),
    }
    settings.endGroup()
    return normalisasi_page_setup(raw)


def simpan_page_setup(page_setup: dict) -> dict:
    """Simpan pengaturan halaman setelah dinormalisasi."""
    normalized = normalisasi_page_setup(page_setup)
    settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
    settings.beginGroup(_SETTINGS_GROUP)
    for key in (
        "paper_size", "orientation", "width_mm", "height_mm",
        "style_preset", "margin_preset", "scaling",
        "print_gridlines", "repeat_header_rows",
    ):
        settings.setValue(key, normalized[key])
    for edge, value in normalized["margins"].items():
        settings.setValue(f"margins/{edge}", value)
    settings.endGroup()
    settings.sync()
    return normalized


class InvoicePageSetupDialog(QDialog):
    """Dialog Page Setup Qt untuk media cetak Invoice Kargo."""

    def __init__(self, page_setup: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Page Setup - Invoice")
        self.setMinimumWidth(460)
        self._settings = normalisasi_page_setup(page_setup or muat_page_setup())
        self._building = True
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)

        paper_group = QGroupBox("Paper")
        paper_form = QFormLayout(paper_group)
        paper_form.setContentsMargins(12, 14, 12, 12)
        paper_form.setHorizontalSpacing(18)
        paper_form.setVerticalSpacing(9)

        self.cmb_paper = QComboBox()
        self.cmb_paper.addItem("A4 (210 × 297 mm)", "A4")
        self.cmb_paper.addItem("NCR (9.5 × 5.5 inch)", "NCR")
        self.cmb_paper.addItem("Custom Size", "CUSTOM")
        paper_form.addRow("Paper Size", self.cmb_paper)

        self.cmb_orientation = QComboBox()
        self.cmb_orientation.addItem("Portrait", "portrait")
        self.cmb_orientation.addItem("Landscape", "landscape")
        paper_form.addRow("Orientation", self.cmb_orientation)

        dimensions_widget = QWidget()
        dimensions_layout = QGridLayout(dimensions_widget)
        dimensions_layout.setContentsMargins(0, 0, 0, 0)
        dimensions_layout.setHorizontalSpacing(8)
        self.spin_width = self._buat_spin(25.0, 1000.0, 1)
        self.spin_height = self._buat_spin(25.0, 1000.0, 1)
        dimensions_layout.addWidget(QLabel("Width"), 0, 0)
        dimensions_layout.addWidget(self.spin_width, 0, 1)
        dimensions_layout.addWidget(QLabel("Height"), 0, 2)
        dimensions_layout.addWidget(self.spin_height, 0, 3)
        dimensions_layout.addWidget(QLabel("mm"), 0, 4)
        paper_form.addRow("Custom Dimensions", dimensions_widget)
        self._dimensions_widget = dimensions_widget

        root.addWidget(paper_group)

        margin_group = QGroupBox("Margins")
        margin_form = QFormLayout(margin_group)
        margin_form.setContentsMargins(12, 14, 12, 12)
        margin_form.setHorizontalSpacing(18)
        margin_form.setVerticalSpacing(9)
        self.cmb_margin = QComboBox()
        self.cmb_margin.addItem("Normal", "normal")
        self.cmb_margin.addItem("Narrow", "narrow")
        self.cmb_margin.addItem("Wide", "wide")
        self.cmb_margin.addItem("Custom", "custom")
        margin_form.addRow("Preset", self.cmb_margin)

        margins_widget = QWidget()
        margins_grid = QGridLayout(margins_widget)
        margins_grid.setContentsMargins(0, 0, 0, 0)
        margins_grid.setHorizontalSpacing(8)
        margins_grid.setVerticalSpacing(8)
        self.margin_spins = {
            edge: self._buat_spin(0.0, 100.0, 1)
            for edge in ("top", "bottom", "left", "right")
        }
        margins_grid.addWidget(QLabel("Top"), 0, 0)
        margins_grid.addWidget(self.margin_spins["top"], 0, 1)
        margins_grid.addWidget(QLabel("Bottom"), 0, 2)
        margins_grid.addWidget(self.margin_spins["bottom"], 0, 3)
        margins_grid.addWidget(QLabel("Left"), 1, 0)
        margins_grid.addWidget(self.margin_spins["left"], 1, 1)
        margins_grid.addWidget(QLabel("Right"), 1, 2)
        margins_grid.addWidget(self.margin_spins["right"], 1, 3)
        margin_form.addRow("Custom Margins (mm)", margins_widget)
        self._margins_widget = margins_widget
        root.addWidget(margin_group)

        output_group = QGroupBox("Scaling & Worksheet")
        output_form = QFormLayout(output_group)
        output_form.setContentsMargins(12, 14, 12, 12)
        output_form.setHorizontalSpacing(18)
        output_form.setVerticalSpacing(9)
        self.cmb_scaling = QComboBox()
        self.cmb_scaling.addItem("Actual Size (100%)", "actual")
        self.cmb_scaling.addItem("Fit All Columns to One Page", "fit_width")
        output_form.addRow("Scaling", self.cmb_scaling)
        self.chk_gridlines = QCheckBox("Print Gridlines")
        output_form.addRow("Gridlines", self.chk_gridlines)
        self.spin_repeat_header_rows = QSpinBox()
        self.spin_repeat_header_rows.setRange(0, 20)
        self.spin_repeat_header_rows.setToolTip(
            "Jumlah baris teratas yang diulang pada setiap halaman. Isi 0 untuk menonaktifkan."
        )
        output_form.addRow("Repeat Header Rows", self.spin_repeat_header_rows)
        root.addWidget(output_group)

        self.lbl_note = QLabel(
            "Page Setup ini diterapkan ke PDF hasil render worksheet Univer."
        )
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet("color: #64748b;")
        root.addWidget(self.lbl_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.cmb_paper.currentIndexChanged.connect(self._paper_changed)
        self.cmb_margin.currentIndexChanged.connect(self._margin_preset_changed)
        self._load_controls()
        self._building = False
        self._update_enabled_state()

    @staticmethod
    def _buat_spin(minimum: float, maximum: float, decimals: int) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(1.0)
        spin.setSuffix(" mm")
        return spin

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _load_controls(self) -> None:
        settings = self._settings
        self._set_combo_data(self.cmb_paper, settings["paper_size"])
        self._set_combo_data(self.cmb_orientation, settings["orientation"])
        self.spin_width.setValue(settings["width_mm"])
        self.spin_height.setValue(settings["height_mm"])
        self._set_combo_data(self.cmb_margin, settings["margin_preset"])
        self._set_combo_data(self.cmb_scaling, settings["scaling"])
        self.chk_gridlines.setChecked(settings["print_gridlines"])
        self.spin_repeat_header_rows.setValue(settings["repeat_header_rows"])
        for edge, spin in self.margin_spins.items():
            spin.setValue(settings["margins"][edge])

    def _paper_changed(self, *_args) -> None:
        if self._building:
            return
        paper = self.cmb_paper.currentData()
        if paper == "A4":
            self.spin_width.setValue(210.0)
            self.spin_height.setValue(297.0)
            self.cmb_orientation.setCurrentIndex(self.cmb_orientation.findData("portrait"))
        elif paper == "NCR":
            self.spin_width.setValue(139.7)
            self.spin_height.setValue(241.3)
            self.cmb_orientation.setCurrentIndex(self.cmb_orientation.findData("landscape"))
        self._update_enabled_state()
        self._apply_margin_preset(self.cmb_margin.currentData())

    def _margin_preset_changed(self, *_args) -> None:
        if self._building:
            return
        self._apply_margin_preset(self.cmb_margin.currentData())
        self._update_enabled_state()

    def _apply_margin_preset(self, preset: str) -> None:
        if preset == "custom":
            self._update_enabled_state()
            return
        paper = self.cmb_paper.currentData()
        normal = 4.0 if paper == "NCR" else 8.0
        margin = {
            "normal": normal,
            "narrow": 4.0,
            "wide": 15.0,
        }.get(str(preset), normal)
        for spin in self.margin_spins.values():
            spin.setValue(margin)
        self._update_enabled_state()

    def _update_enabled_state(self) -> None:
        custom_paper = self.cmb_paper.currentData() == "CUSTOM"
        custom_margins = self.cmb_margin.currentData() == "custom"
        self._dimensions_widget.setEnabled(custom_paper)
        self._margins_widget.setEnabled(custom_margins)

    def page_setup(self) -> dict:
        paper = str(self.cmb_paper.currentData() or "NCR")
        result = {
            "paper_size": paper,
            "orientation": str(self.cmb_orientation.currentData() or "landscape"),
            "width_mm": self.spin_width.value(),
            "height_mm": self.spin_height.value(),
            "style_preset": "NCR" if paper == "NCR" else "A4",
            "margin_preset": str(self.cmb_margin.currentData() or "normal"),
            "margins": {edge: spin.value() for edge, spin in self.margin_spins.items()},
            "scaling": str(self.cmb_scaling.currentData() or "actual"),
            "print_gridlines": self.chk_gridlines.isChecked(),
            "repeat_header_rows": self.spin_repeat_header_rows.value(),
        }
        return normalisasi_page_setup(result)



class InvoicePageSetupPanel(QWidget):
    """Panel Page Setup ringkas untuk sisi kiri jendela Print Preview.

    API kelas ini dipakai oleh InvoicePdfPreviewDialog:
    - applyRequested(dict): sinyal saat pengguna meminta preview dibuat ulang.
    - page_setup(): mengambil konfigurasi saat ini.
    - set_status(str): menampilkan status render/preview.
    - set_busy(bool): menonaktifkan kontrol saat PDF sedang dibuat.
    """

    applyRequested = Signal(dict)

    def __init__(self, page_setup: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = normalisasi_page_setup(page_setup or muat_page_setup())
        self._building = True
        # Dipakai oleh _update_enabled_state() dan set_busy(). Harus diinisialisasi
        # sebelum widget dibuat/diaktifkan agar konstruksi panel tidak melempar AttributeError.
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)

        paper_group = QGroupBox("Paper")
        paper_form = QFormLayout(paper_group)
        paper_form.setContentsMargins(10, 12, 10, 10)
        paper_form.setVerticalSpacing(6)
        self.cmb_paper = QComboBox()
        self.cmb_paper.addItem("A4 (210 × 297 mm)", "A4")
        self.cmb_paper.addItem("NCR (9.5 × 5.5 inch)", "NCR")
        self.cmb_paper.addItem("Custom Size", "CUSTOM")
        paper_form.addRow("Paper Size", self.cmb_paper)

        self.cmb_orientation = QComboBox()
        self.cmb_orientation.addItem("Portrait", "portrait")
        self.cmb_orientation.addItem("Landscape", "landscape")
        paper_form.addRow("Orientation", self.cmb_orientation)

        dimensions = QWidget(self)
        dimensions_grid = QGridLayout(dimensions)
        dimensions_grid.setContentsMargins(0, 0, 0, 0)
        dimensions_grid.setHorizontalSpacing(5)
        self.spin_width = self._buat_spin(25.0, 1000.0, 1)
        self.spin_height = self._buat_spin(25.0, 1000.0, 1)
        dimensions_grid.addWidget(QLabel("Width"), 0, 0)
        dimensions_grid.addWidget(self.spin_width, 0, 1)
        dimensions_grid.addWidget(QLabel("Height"), 1, 0)
        dimensions_grid.addWidget(self.spin_height, 1, 1)
        paper_form.addRow("Custom (mm)", dimensions)
        self._dimensions_widget = dimensions
        root.addWidget(paper_group)

        margin_group = QGroupBox("Margins")
        margin_form = QFormLayout(margin_group)
        margin_form.setContentsMargins(10, 12, 10, 10)
        margin_form.setVerticalSpacing(6)
        self.cmb_margin = QComboBox()
        self.cmb_margin.addItem("Normal", "normal")
        self.cmb_margin.addItem("Narrow", "narrow")
        self.cmb_margin.addItem("Wide", "wide")
        self.cmb_margin.addItem("Custom", "custom")
        margin_form.addRow("Preset", self.cmb_margin)

        margins = QWidget(self)
        margins_grid = QGridLayout(margins)
        margins_grid.setContentsMargins(0, 0, 0, 0)
        margins_grid.setHorizontalSpacing(5)
        margins_grid.setVerticalSpacing(5)
        self.margin_spins = {
            edge: self._buat_spin(0.0, 100.0, 1)
            for edge in ("top", "bottom", "left", "right")
        }
        margins_grid.addWidget(QLabel("Top"), 0, 0)
        margins_grid.addWidget(self.margin_spins["top"], 0, 1)
        margins_grid.addWidget(QLabel("Bottom"), 1, 0)
        margins_grid.addWidget(self.margin_spins["bottom"], 1, 1)
        margins_grid.addWidget(QLabel("Left"), 2, 0)
        margins_grid.addWidget(self.margin_spins["left"], 2, 1)
        margins_grid.addWidget(QLabel("Right"), 3, 0)
        margins_grid.addWidget(self.margin_spins["right"], 3, 1)
        margin_form.addRow("Custom (mm)", margins)
        self._margins_widget = margins
        root.addWidget(margin_group)

        output_group = QGroupBox("Scaling & Worksheet")
        output_form = QFormLayout(output_group)
        output_form.setContentsMargins(10, 12, 10, 10)
        output_form.setVerticalSpacing(6)
        self.cmb_scaling = QComboBox()
        self.cmb_scaling.addItem("Actual Size (100%)", "actual")
        self.cmb_scaling.addItem("Fit All Columns to One Page", "fit_width")
        output_form.addRow("Scaling", self.cmb_scaling)
        self.chk_gridlines = QCheckBox("Print Gridlines")
        output_form.addRow("Gridlines", self.chk_gridlines)
        self.spin_repeat_header_rows = QSpinBox()
        self.spin_repeat_header_rows.setRange(0, 20)
        self.spin_repeat_header_rows.setToolTip(
            "Jumlah baris teratas yang diulang pada setiap halaman; 0 untuk nonaktif."
        )
        output_form.addRow("Repeat Header Rows", self.spin_repeat_header_rows)
        root.addWidget(output_group)

        self.lbl_status = QLabel("Perubahan Page Setup akan diterapkan otomatis ke Preview.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setMinimumHeight(42)
        self.lbl_status.setStyleSheet("color: #64748b; padding: 4px 2px;")
        root.addWidget(self.lbl_status)
        root.addStretch(1)

        self.cmb_paper.currentIndexChanged.connect(self._paper_changed)
        self.cmb_margin.currentIndexChanged.connect(self._margin_preset_changed)
        self._load_controls()
        self._building = False
        self._update_enabled_state()

        # Live Preview: debounce rapid control changes (for example, paper
        # selection also changes orientation and preset margins) into a single
        # PDF regeneration request. This keeps the QWebChannel/pdfmake pipeline
        # from receiving several overlapping requests for one user action.
        self._live_preview_timer = QTimer(self)
        self._live_preview_timer.setSingleShot(True)
        self._live_preview_timer.setInterval(450)
        self._live_preview_timer.timeout.connect(self._emit_apply)

        for signal in (
            self.cmb_paper.currentIndexChanged,
            self.cmb_orientation.currentIndexChanged,
            self.cmb_margin.currentIndexChanged,
            self.cmb_scaling.currentIndexChanged,
            self.chk_gridlines.toggled,
            self.spin_width.valueChanged,
            self.spin_height.valueChanged,
            self.spin_repeat_header_rows.valueChanged,
            *(spin.valueChanged for spin in self.margin_spins.values()),
        ):
            signal.connect(self._schedule_live_preview)

    @staticmethod
    def _buat_spin(minimum: float, maximum: float, decimals: int) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(1.0)
        spin.setSuffix(" mm")
        return spin

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _load_controls(self) -> None:
        settings = self._settings
        self._set_combo_data(self.cmb_paper, settings["paper_size"])
        self._set_combo_data(self.cmb_orientation, settings["orientation"])
        self.spin_width.setValue(settings["width_mm"])
        self.spin_height.setValue(settings["height_mm"])
        self._set_combo_data(self.cmb_margin, settings["margin_preset"])
        self._set_combo_data(self.cmb_scaling, settings["scaling"])
        self.chk_gridlines.setChecked(settings["print_gridlines"])
        self.spin_repeat_header_rows.setValue(settings["repeat_header_rows"])
        for edge, spin in self.margin_spins.items():
            spin.setValue(settings["margins"][edge])

    def _paper_changed(self, *_args) -> None:
        if self._building:
            return
        paper = self.cmb_paper.currentData()
        if paper == "A4":
            self.spin_width.setValue(210.0)
            self.spin_height.setValue(297.0)
            self._set_combo_data(self.cmb_orientation, "portrait")
        elif paper == "NCR":
            self.spin_width.setValue(139.7)
            self.spin_height.setValue(241.3)
            self._set_combo_data(self.cmb_orientation, "landscape")
        self._apply_margin_preset(self.cmb_margin.currentData())
        self._update_enabled_state()

    def _margin_preset_changed(self, *_args) -> None:
        if self._building:
            return
        self._apply_margin_preset(self.cmb_margin.currentData())
        self._update_enabled_state()

    def _apply_margin_preset(self, preset: str) -> None:
        if preset == "custom":
            return
        paper = self.cmb_paper.currentData()
        normal = 4.0 if paper == "NCR" else 8.0
        margin = {"normal": normal, "narrow": 4.0, "wide": 15.0}.get(
            str(preset), normal
        )
        for spin in self.margin_spins.values():
            spin.setValue(margin)

    def _update_enabled_state(self) -> None:
        active = not bool(getattr(self, "_busy", False))
        self._dimensions_widget.setEnabled(
            active and self.cmb_paper.currentData() == "CUSTOM"
        )
        self._margins_widget.setEnabled(
            active and self.cmb_margin.currentData() == "custom"
        )

    def page_setup(self) -> dict:
        paper = str(self.cmb_paper.currentData() or "NCR")
        return normalisasi_page_setup({
            "paper_size": paper,
            "orientation": str(self.cmb_orientation.currentData() or "landscape"),
            "width_mm": self.spin_width.value(),
            "height_mm": self.spin_height.value(),
            "style_preset": "NCR" if paper == "NCR" else "A4",
            "margin_preset": str(self.cmb_margin.currentData() or "normal"),
            "margins": {edge: spin.value() for edge, spin in self.margin_spins.items()},
            "scaling": str(self.cmb_scaling.currentData() or "actual"),
            "print_gridlines": self.chk_gridlines.isChecked(),
            "repeat_header_rows": self.spin_repeat_header_rows.value(),
        })

    def _schedule_live_preview(self, *_args) -> None:
        """Queue one preview rebuild after the user finishes changing controls."""
        if self._building or self._busy:
            return
        self._live_preview_timer.start(450)
        self.set_status("Pengaturan berubah. Preview akan diperbarui otomatis...")

    def _emit_apply(self) -> None:
        if self._building or self._busy:
            return
        self.applyRequested.emit(self.page_setup())

    def set_status(self, message: str) -> None:
        self.lbl_status.setText(str(message or ""))

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        enabled = not self._busy
        for widget in (
            self.cmb_paper,
            self.cmb_orientation,
            self.spin_width,
            self.spin_height,
            self.cmb_margin,
            *self.margin_spins.values(),
            self.cmb_scaling,
            self.chk_gridlines,
            self.spin_repeat_header_rows,
        ):
            widget.setEnabled(enabled)
        if busy and hasattr(self, "_live_preview_timer"):
            self._live_preview_timer.stop()
        self._update_enabled_state()


def page_setup_untuk_kertas(paper: str, base_settings: dict | None = None) -> dict:
    """Buat override preset A4/NCR untuk aksi cetak cepat lama."""
    setup = normalisasi_page_setup(base_settings)
    paper = str(paper or "NCR").upper()
    if paper == "A4":
        setup.update({
            "paper_size": "A4",
            "orientation": "portrait",
            "width_mm": 210.0,
            "height_mm": 297.0,
            "style_preset": "A4",
            "margin_preset": "normal",
            "margins": {"top": 8.0, "bottom": 8.0, "left": 8.0, "right": 8.0},
        })
    else:
        setup.update({
            "paper_size": "NCR",
            "orientation": "landscape",
            "width_mm": 139.7,
            "height_mm": 241.3,
            "style_preset": "NCR",
            "margin_preset": "normal",
            "margins": {"top": 4.0, "bottom": 4.0, "left": 4.0, "right": 4.0},
        })
    return normalisasi_page_setup(setup)