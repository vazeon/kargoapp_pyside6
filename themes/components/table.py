# themes/components/table.py
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from themes.colors import get_theme_colors

from utils.typography import dapatkan_font_aplikasi_aktif, get_fixed_font_sizes_pt


def _dapatkan_ukuran_font_default() -> float:
    return get_fixed_font_sizes_pt().get("sz_base", 9.0)


@dataclass
class TableMetrics:
    font_family: str = field(default_factory=dapatkan_font_aplikasi_aktif)
    font_size_pt: float = field(default_factory=_dapatkan_ukuran_font_default)

    item_pad: int = 4
    header_v: int = 4
    header_h: int = 8
    indicator_size: int = 16


def get_table_styles(
        is_dark: bool,
        metrics: Optional[TableMetrics] = None,
        ui_colors: Optional[Dict[str, Any]] = None,
        *,
        cell_editors: bool = False,
) -> str:
    metrics = metrics or TableMetrics()

    if ui_colors is None:
        ui_colors = get_theme_colors(is_dark)["ui"]

    bg = ui_colors["table_background"]
    alt_bg = ui_colors["table_alternate_background"]
    text_color = ui_colors["table_text"]
    grid_color = ui_colors["table_grid"]

    selected_bg = ui_colors["selection_background"]
    selected_text = ui_colors["selection_text"]
    focus_bg = ui_colors["field_focus_background"]

    item_pad = 0 if cell_editors else metrics.item_pad
    editor_focus_bg = bg if cell_editors else focus_bg
    selection_styles = ""
    if cell_editors:
        selection_styles = f"""
            QTableWidget::item:selected, QTableView::item:selected,
            QTableWidget::item:selected:hover, QTableView::item:selected:hover {{
                background-color: {bg};
                color: {text_color};
            }}
            QTableWidget::item:alternate:selected,
            QTableView::item:alternate:selected,
            QTableWidget::item:alternate:selected:hover,
            QTableView::item:alternate:selected:hover {{
                background-color: {alt_bg};
                color: {text_color};
            }}
        """

    return f"""
        QTableWidget, QTableView {{
            background-color: {bg};
            alternate-background-color: {alt_bg};
            color: {text_color};
            gridline-color: {grid_color};
            border: 1px solid {grid_color};
            font-family: '{metrics.font_family}';
            font-size: {metrics.font_size_pt}pt;

            selection-background-color: {selected_bg};
            selection-color: {selected_text};

            outline: none;
        }}

        QTableWidget::item, QTableView::item {{
            padding: {item_pad}px;
        }}

        QHeaderView::section {{
            font-family: '{metrics.font_family}';
            font-size: {metrics.font_size_pt}pt;
            font-weight: 600;
            padding-top: {metrics.header_v}px;
            padding-bottom: {metrics.header_v}px;
        }}

        QTableWidget::item:selected, 
        QTableView::item:selected,
        QTableWidget::item:selected:hover, 
        QTableView::item:selected:hover {{
            background-color: {selected_bg};
            color: {selected_text};
        }}

        QTableWidget::item:hover:!selected, 
        QTableView::item:hover:!selected {{
            background-color: none;
        }}

        QTableWidget QLineEdit, QTableView QLineEdit {{
            border: 1px solid transparent;
            border-radius: 0px;
            margin: 0px;
            min-height: 0px;
            background: transparent;
            padding: 0px 4px;
            color: {text_color};
        }}

        QTableWidget QLineEdit:hover, QTableView QLineEdit:hover {{
            background: transparent;
            border: 1px solid transparent;
        }}

        QTableView[tableFrozenView="true"] {{
            border: none;
        }}

        QTableWidget::indicator, QTableView::indicator {{
            subcontrol-origin: padding;
            subcontrol-position: center;
        }}

        QTableWidget QLineEdit:focus, QTableView QLineEdit:focus,
        QTableWidget QLineEdit:focus:hover, QTableView QLineEdit:focus:hover {{
            background: {editor_focus_bg};
            border: 1px solid {selected_bg};
        }}

        QCheckBox::indicator, QRadioButton::indicator {{
            width: {metrics.indicator_size}px; 
            height: {metrics.indicator_size}px;
        }}

        /* Checkbox normal di dalam tabel */
        QTableWidget::indicator, QTableView::indicator {{
            subcontrol-origin: padding;
            subcontrol-position: center;
        }}

        /* Checkbox saat baris/sel terpilih (highlight biru) */
        QTableWidget::item:selected QCheckBox::indicator,
        QTableView::item:selected QCheckBox::indicator,
        QTableWidget::indicator:selected,
        QTableView::indicator:selected {{
            background-color: #FFFFFF;
            border: 1px solid #FFFFFF;
        }}

        /* Centangan saat terdaftar/terceklis pada highlight biru */
        QTableWidget::indicator:checked:selected,
        QTableView::indicator:checked:selected {{
            background-color: #0078D4; /* Warna isi centang atau aksen biru */
            border: 1px solid #FFFFFF;  /* Border luar tetap putih kontras */
        }}

        QHeaderView::section:horizontal,
        QHeaderView::section:horizontal:hover,
        QHeaderView::section:horizontal:checked,
        QHeaderView::section:horizontal:selected,
        QHeaderView::section:horizontal:checked:hover,
        QHeaderView::section:horizontal:selected:hover {{
            border-top: 1px solid transparent;
        }}

        {selection_styles}
    """

def get_table_input_styles(
        is_dark: bool,
        theme: Optional[Dict[str, Any]] = None,
        metrics: Optional[TableMetrics] = None,
) -> str:
    ui = dict(get_theme_colors(is_dark)["ui"])
    if theme is not None:
        for source, target in (
                ("background", "table_background"),
                ("alternate_background", "table_alternate_background"),
                ("text", "table_text"),
                ("grid", "table_grid"),
                ("selection_background", "selection_background"),
                ("selection_text", "selection_text"),
        ):
            if source in theme:
                ui[target] = theme[source]
    return get_table_styles(
        is_dark, metrics=metrics, ui_colors=ui, cell_editors=True,
    )