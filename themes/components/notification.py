# themes/components/notifications.py

"""Style notification popup aplikasi."""

from utils.typography import get_master_font


FADE_NOTIFICATION_STYLE = f"""
    QLabel {{
        background-color: rgba(15, 23, 42, 0.95);
        color: #10b981;
        font-size: 22px;
        font-weight: bold;
        border-radius: 12px;
        padding: 20px 50px;
        border: 2px solid #10b981;
        font-family: '{get_master_font()}';
    }}
"""