# themes/components/splitter
def get_splitter_style(is_dark: bool) -> str:
    c_border = "#475569" if is_dark else "#CBD5E1"

    return f"""
        QSplitter {{
            background: transparent;
        }}

        QSplitter::handle {{
            background-color: {c_border};
            margin: 14px 1px;
            border-radius: 1px;
        }}
    """