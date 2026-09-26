# themes/components/inputs.py
"""QSS input form. Penerapan ke widget dikelola utils.input_style_helper."""

from themes.colors import get_theme_colors


_TEXT_SELECTORS = (
    'QLineEdit[globalFormInput="true"]',
    'QTextEdit[globalFormInput="true"]',
    'QPlainTextEdit[globalFormInput="true"]',
)
_INPUT_SELECTORS = _TEXT_SELECTORS + (
    'QComboBox[globalFormInput="true"]',
    'QAbstractSpinBox[globalFormInput="true"]',
)


def get_global_focus_qss() -> str:
    """API lama tetap tersedia; fokus hanya untuk input form terdaftar."""
    selectors = ",\n".join(f"{s}:focus" for s in _INPUT_SELECTORS)
    return f"""
        {selectors} {{
            border: 1px solid #0081db;
            border-radius: 4px;
        }}
    """


def get_global_input_qss(is_dark: bool, readonly: bool = False) -> str:
    """Style form bersama tanpa memaksakan font atau tinggi widget.

    Tombol/panah ComboBox dan spin/date tetap memakai style aplikasi.
    QSS fokus ada di sini; helper menangani palet kontrol tersebut.
    """
    ui = get_theme_colors(is_dark)["ui"]
    muted_bg = "#20242b" if is_dark else "#f8fafc"
    background = muted_bg if readonly else ui["field_background"]
    text = ui["text_muted"] if readonly else ui["table_text"]
    selectors = ",\n".join(_TEXT_SELECTORS)
    disabled = ",\n".join(f"{s}:disabled" for s in _TEXT_SELECTORS)
    return f"""
        {selectors} {{
            background-color: {background};
            color: {text};
            border: 1px solid {ui['field_border']};
            border-radius: 4px;
            padding: 2px 8px;
            placeholder-text-color: {ui['placeholder_text']};
            selection-background-color: #0081db;
            selection-color: #ffffff;
        }}
        {disabled} {{
            background-color: {muted_bg};
            color: {ui['text_muted']};
        }}
    """ + get_global_focus_qss()
