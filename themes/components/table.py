# themes/components/table.py

def get_table_styles(is_dark: bool) -> str:
    """Style modern untuk QTableWidget dengan warna dinamis via Python."""

    grid_color = "#334155" if is_dark else "#cbd5e1"
    focus_bg = "#0f172a" if is_dark else "#ffffff"
    text_color = "#e2e8f0" if is_dark else "#1e293b"

    return f"""

        QTableWidget {{
            gridline-color: {grid_color};
        }}


        QTableWidget QLineEdit {{
            border: none;
            background: transparent;
            padding: 0px 4px;
            color: {text_color};
        }}

        QTableWidget QLineEdit:hover {{
            background: transparent;
            border: none;
        }}
        
        QTableWidget::item:hover {{
            background: transparent;
        }}

        QTableWidget::item:selected {{
            background: transparent;
        }}

        
        QTableWidget::item:hover:!selected {{
            background: transparent;
        }}

        QTableWidget QLineEdit:focus {{
            background: {focus_bg};
        }}
    """