# audit_context.py
"""Context SQLite untuk audit user per connection.

Audit fields diisi oleh trigger lokal menggunakan CURRENT_SESSION.
Mode sync bersifat per-connection agar pull remote tidak menimpa identitas
pembuat asli dengan user yang sedang melakukan pull.
"""
from __future__ import annotations

from typing import Any


def _session_value(key: str, default: Any = None) -> Any:
    try:
        from config import CURRENT_SESSION
        value = CURRENT_SESSION.get(key)
    except Exception:
        value = None
    if value is None or str(value).strip() == "":
        return default
    return value


def install_sqlite_audit_functions(conn):
    """Pasang UDF audit pada koneksi SQLite dan kembalikan controller."""
    if conn is None:
        return None

    state = {"sync": False}

    def actor_id():
        return _session_value("id_user", None)

    def actor_username():
        return str(_session_value("username", "SYSTEM") or "SYSTEM").strip().upper() or "SYSTEM"

    def actor_name():
        return str(
            _session_value("nama_lengkap", "")
            or actor_username()
        ).strip() or actor_username()

    def audit_is_sync():
        return 1 if state["sync"] else 0

    conn.create_function("mkt_audit_user_id", 0, actor_id)
    conn.create_function("mkt_audit_username", 0, actor_username)
    conn.create_function("mkt_audit_name", 0, actor_name)
    conn.create_function("mkt_audit_is_sync", 0, audit_is_sync)

    class _Controller:
        def set_sync(self, enabled: bool) -> None:
            state["sync"] = bool(enabled)

    return _Controller()


def set_sqlite_audit_sync(conn, enabled: bool) -> None:
    """Nonaktifkan audit trigger sementara pada koneksi sync/bootstrap."""
    if conn is None:
        return
    conn.create_function("mkt_audit_is_sync", 0, lambda: 1 if enabled else 0)
