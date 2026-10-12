# services/numbering_service.py
"""Service penomoran fixed untuk Resi, Manifest, dan Invoice."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from audit_context import install_sqlite_audit_functions
from config import CURRENT_SESSION, cabang_boleh_tulis, ROLE_SUPER_APP

ALLOWED_DOCUMENT_TYPES = frozenset({"RESI", "MANIFEST", "INVOICE"})
DEFAULT_PADDING = {"RESI": 5, "MANIFEST": 4, "INVOICE": 4}
CENTRAL_INVOICE_BRANCH = "SBY"


class NumberingError(Exception):
    pass


@dataclass(frozen=True)
class NumberingResult:
    document_type: str
    kode_cabang: str
    series_code: str
    sequence: int
    nomor: str
    starting_count: int
    padding: int


def _db_path(db_name: Optional[str] = None) -> str:
    target = str(db_name or "").strip()
    if target:
        return target
    try:
        return str(CURRENT_SESSION.get("db_name") or "database_cargo.db")
    except Exception:
        return "database_cargo.db"


def _conn(db_name: Optional[str] = None):
    conn = sqlite3.connect(_db_path(db_name), timeout=20.0)
    conn.execute("PRAGMA foreign_keys = ON")
    install_sqlite_audit_functions(conn)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 20000")
    return conn


def _as_date(value=None) -> date:
    if value is None:
        return datetime.now().date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "toString"):
        text = value.toString("yyyy-MM-dd")
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            pass
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return datetime.fromisoformat(text[:10]).date()
            except ValueError:
                pass
    raise NumberingError("Tanggal penomoran tidak valid.")


def normalize_document_type(document_type: str) -> str:
    doc = str(document_type or "").strip().upper()
    if doc not in ALLOWED_DOCUMENT_TYPES:
        raise NumberingError(f"Jenis dokumen tidak didukung: {doc or '-'}")
    return doc


def _load_branch(cursor, kode_cabang):
    branch = str(kode_cabang or "").strip().upper()
    if not branch:
        raise NumberingError("Kode cabang wajib diisi.")
    row = cursor.execute(
        "SELECT start_seq_json, aturan_prefix FROM data_cabang WHERE kode_cabang=? LIMIT 1",
        (branch,),
    ).fetchone()
    if not row:
        raise NumberingError(f"Cabang {branch} tidak ditemukan.")
    try:
        starts_raw = json.loads(row[0] or "{}") if row[0] else {}
    except Exception:
        starts_raw = {}
    try:
        rules_raw = json.loads(row[1] or "{}") if row[1] else {}
    except Exception:
        rules_raw = {}
    starts = {
        str(k).strip().upper(): int(v or 0)
        for k, v in starts_raw.items()
        if str(k).strip()
    }
    rules = {
        str(k).strip().upper(): str(v or "").strip().upper()
        for k, v in rules_raw.items()
        if str(k).strip()
    }
    return branch, starts, rules


def _normalize_wilayah(value: str) -> str:
    text = " ".join(str(value or "").strip().upper().split())
    if "KALIMANTAN TIMUR" in text:
        return "KALIMANTAN TIMUR"
    if "KALIMANTAN SELATAN" in text:
        return "KALIMANTAN SELATAN"
    return "DEFAULT"


def resolve_series(cursor, document_type: str, kode_cabang: str, wilayah: str = ""):
    doc = normalize_document_type(document_type)
    branch, starts, rules = _load_branch(cursor, kode_cabang)

    if doc == "INVOICE":
        branch = CENTRAL_INVOICE_BRANCH
        branch, starts, rules = _load_branch(cursor, branch)
        return branch, "INV", 1, DEFAULT_PADDING[doc]

    province = _normalize_wilayah(wilayah)
    if doc == "RESI":
        series = rules.get(province) or rules.get("DEFAULT") or "IND"
        start = starts.get(series, starts.get("DEFAULT", 1000))
        return branch, series, start, DEFAULT_PADDING[doc]

    base = {
        "KALIMANTAN TIMUR": "MT",
        "KALIMANTAN SELATAN": "MS",
    }.get(province, "MI")
    jmark = "J-" if rules.get("KALIMANTAN TIMUR", "").startswith("J-") else ""
    return branch, f"{jmark}{base}", 1, DEFAULT_PADDING[doc]


def _ensure_counter(cursor, branch, doc, series, default_start, default_padding):
    row = cursor.execute(
        """
        SELECT starting_count, current_count, padding, aktif
        FROM numbering_counters
        WHERE kode_cabang=? AND document_type=? AND series_code=?
          AND COALESCE(aktif,0)=1 AND deleted_at IS NULL
        LIMIT 1
        """,
        (branch, doc, series),
    ).fetchone()
    if row:
        return row
    cursor.execute(
        """
        INSERT INTO numbering_counters(
            kode_cabang, document_type, series_code,
            starting_count, current_count, padding, aktif, sync_id
        ) VALUES (?, ?, ?, ?, 0, ?, 1, ?)
        """,
        (branch, doc, series, int(default_start), int(default_padding), str(uuid.uuid4())),
    )
    return int(default_start), 0, int(default_padding), 1


def _format_number(doc, series, sequence, padding, tanggal, suffix=""):
    seq = str(int(sequence)).zfill(max(1, int(padding)))
    if doc == "RESI":
        return f"{series}-{seq}{str(suffix or '').upper()}"
    if doc == "MANIFEST":
        return f"{series}-{seq}"
    yy = str(_as_date(tanggal).year % 100).zfill(2)
    return f"{seq}/INV/MKT-SUB/{yy}"


def allocate_number_cursor(
    cursor,
    document_type,
    kode_cabang,
    *,
    wilayah="",
    tanggal=None,
    suffix="",
):
    """Allocate one number inside the caller's already-open SQLite transaction."""
    doc = normalize_document_type(document_type)
    branch, series, default_start, default_padding = resolve_series(
        cursor, doc, kode_cabang, wilayah
    )
    # Invoice selalu dialokasikan di SBY, sehingga hak tulis harus diperiksa
    # pada cabang efektif (bukan sekadar cabang yang dikirim caller).
    _pastikan_boleh_tulis_cabang(branch)
    start, current, padding, _aktif = _ensure_counter(
        cursor, branch, doc, series, default_start, default_padding
    )
    start = int(start or 0)
    current = int(current or 0)
    padding = max(1, int(padding or default_padding))
    sequence = max(start, current + 1)
    nomor = _format_number(doc, series, sequence, padding, tanggal, suffix)
    cursor.execute(
        """
        UPDATE numbering_counters
        SET current_count=?, updated_at=CURRENT_TIMESTAMP
        WHERE kode_cabang=? AND document_type=? AND series_code=?
          AND COALESCE(aktif,0)=1 AND deleted_at IS NULL
        """,
        (sequence, branch, doc, series),
    )
    if cursor.rowcount != 1:
        raise NumberingError("Counter penomoran gagal diperbarui.")
    return NumberingResult(doc, branch, series, sequence, nomor, start, padding)


def peek_next_number(
    document_type,
    kode_cabang,
    *,
    wilayah="",
    tanggal=None,
    suffix="",
    db_name=None,
):
    doc = normalize_document_type(document_type)
    conn = _conn(db_name)
    try:
        cursor = conn.cursor()
        branch, series, default_start, default_padding = resolve_series(
            cursor, doc, kode_cabang, wilayah
        )
        row = cursor.execute(
            """
            SELECT starting_count,current_count,padding
            FROM numbering_counters
            WHERE kode_cabang=? AND document_type=? AND series_code=?
              AND COALESCE(aktif,0)=1 AND deleted_at IS NULL
            LIMIT 1
            """,
            (branch, doc, series),
        ).fetchone()
        if row is None:
            start, current, padding = default_start, 0, default_padding
        else:
            start, current, padding = row
        sequence = max(int(start or 0), int(current or 0) + 1)
        nomor = _format_number(doc, series, sequence, int(padding or default_padding), tanggal, suffix)
        return NumberingResult(
            doc,
            branch,
            series,
            sequence,
            nomor,
            int(start or 0),
            int(padding or default_padding),
        )
    finally:
        conn.close()


def _pastikan_boleh_tulis_cabang(kode_cabang):
    branch = str(kode_cabang or "").strip().upper()
    if not cabang_boleh_tulis(branch):
        raise NumberingError(
            f"Cabang {branch} sedang dalam mode VIEW ONLY. Penomoran tidak dapat diubah dari cabang ini."
        )
    return branch


def generate_number(
    document_type,
    kode_cabang,
    *,
    wilayah="",
    tanggal=None,
    suffix="",
    db_name=None,
):
    conn = _conn(db_name)
    try:
        conn.execute("BEGIN IMMEDIATE")
        result = allocate_number_cursor(
            conn.cursor(),
            document_type,
            kode_cabang,
            wilayah=wilayah,
            tanggal=tanggal,
            suffix=suffix,
        )
        conn.commit()
        return result
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def update_counter_settings(
    kode_cabang,
    document_type,
    series_code,
    *,
    starting_count,
    padding,
    current_count=None,
    db_name=None,
):
    doc = normalize_document_type(document_type)
    branch = str(kode_cabang or "").strip().upper()
    series = str(series_code or "").strip().upper()
    if str(CURRENT_SESSION.get("role") or "").strip().upper() not in {ROLE_SUPER_APP, "SUPER"}:
        raise NumberingError("Hanya SUPER yang dapat mengubah konfigurasi penomoran.")
    if not branch or not series:
        raise NumberingError("Cabang dan seri wajib diisi.")
    start = int(starting_count)
    pad = max(1, int(padding))
    if start < 0:
        raise NumberingError("Starting Number tidak boleh negatif.")
    conn = _conn(db_name)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT sync_id,current_count FROM numbering_counters WHERE kode_cabang=? AND document_type=? AND series_code=?",
            (branch, doc, series),
        ).fetchone()
        current = int(current_count) if current_count is not None else int(row[1] if row else 0)
        if current < 0:
            raise NumberingError("CURRENT tidak boleh negatif.")
        if row:
            conn.execute(
                """
                UPDATE numbering_counters
                SET starting_count=?, padding=?, current_count=?, aktif=1,
                    deleted_at=NULL, updated_at=CURRENT_TIMESTAMP
                WHERE kode_cabang=? AND document_type=? AND series_code=?
                """,
                (start, pad, current, branch, doc, series),
            )
        else:
            conn.execute(
                """
                INSERT INTO numbering_counters(
                    kode_cabang,document_type,series_code,
                    starting_count,current_count,padding,aktif,sync_id
                ) VALUES (?,?,?,?,?,?,1,?)
                """,
                (branch, doc, series, start, current, pad, str(uuid.uuid4())),
            )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


__all__ = [
    "ALLOWED_DOCUMENT_TYPES",
    "DEFAULT_PADDING",
    "CENTRAL_INVOICE_BRANCH",
    "NumberingError",
    "NumberingResult",
    "allocate_number_cursor",
    "generate_number",
    "peek_next_number",
    "normalize_document_type",
    "resolve_series",
    "update_counter_settings",
]