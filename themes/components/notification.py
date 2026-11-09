# themes/components/notifications.py

"""Style notification popup aplikasi."""

from utils.typography import get_font_weights, get_master_font, get_fixed_font_sizes


_FONT_WEIGHTS = get_font_weights()

FADE_NOTIFICATION_STYLE = f"""
    QLabel {{
        background-color: rgba(15, 23, 42, 0.95);
        color: #10b981;
        font-size: {get_fixed_font_sizes()["display"]}px;
        font-weight: {_FONT_WEIGHTS["bold"]};
        border-radius: 12px;
        padding: 20px 50px;
        border: 2px solid #10b981;
        font-family: '{get_master_font()}';
    }}
"""