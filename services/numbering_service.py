# services/numbering_service.py
"""Service penomoran fixed untuk Resi, Manifest, dan Invoice."""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from audit_context import install_sqlite_audit_functions
from config import CURRENT_SESSION, cabang_boleh_tulis, ROLE_SUPER_APP

logger = logging.getLogger(__name__)

# Rentang kecil membatasi lompatan nomor yang tidak terpakai, tetapi tetap memberi
# cadangan untuk beberapa transaksi saat koneksi terputus.
RESERVATION_BLOCK_SIZE = 5
RESERVATION_PREFETCH_THRESHOLD = 1
LOCAL_RESERVATION_TABLE = "numbering_local_reservations"

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


def _is_local_only_mode() -> bool:
    """DEV_SUPER harus tetap sepenuhnya lokal dan tidak memanggil Supabase."""
    role = str(CURRENT_SESSION.get("role") or "").strip().upper()
    return bool(
        CURRENT_SESSION.get("is_developer")
        or CURRENT_SESSION.get("is_dev_super")
        or CURRENT_SESSION.get("dev_super")
        or role in {"DEV_SUPER", "DEV SUPER"}
    )


def _online_supabase_client():
    """Ambil client hanya untuk sesi user normal yang sudah online."""
    if _is_local_only_mode() or bool(CURRENT_SESSION.get("is_offline_session")):
        return None
    if not str(CURRENT_SESSION.get("auth_email") or "").strip():
        return None
    try:
        from supabase_client import supabase
        if supabase.auth.get_session() is None:
            return None
        return supabase
    except Exception:
        return None


def _ensure_local_reservation_schema(cursor) -> None:
    """Tabel cadangan lokal tidak disinkronkan; hanya menyimpan rentang milik PC ini."""
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LOCAL_RESERVATION_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode_cabang TEXT NOT NULL,
            document_type TEXT NOT NULL,
            series_code TEXT NOT NULL,
            next_value INTEGER NOT NULL,
            end_value INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (next_value <= end_value + 1)
        )
        """
    )
    cursor.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{LOCAL_RESERVATION_TABLE}_available
        ON {LOCAL_RESERVATION_TABLE}
           (kode_cabang, document_type, series_code, next_value, end_value)
        """
    )


def _reservation_remaining(cursor, branch: str, doc: str, series: str) -> int:
    _ensure_local_reservation_schema(cursor)
    row = cursor.execute(
        f"""
        SELECT COALESCE(SUM(end_value - next_value + 1), 0)
        FROM {LOCAL_RESERVATION_TABLE}
        WHERE kode_cabang=? AND document_type=? AND series_code=?
          AND next_value <= end_value
        """,
        (branch, doc, series),
    ).fetchone()
    return max(0, int(row[0] or 0)) if row else 0


def _next_reserved_sequence_cursor(cursor, branch: str, doc: str, series: str):
    """Nomor cadangan berikutnya, hanya untuk preview dan allocation lokal."""
    _ensure_local_reservation_schema(cursor)
    row = cursor.execute(
        f"""
        SELECT next_value
        FROM {LOCAL_RESERVATION_TABLE}
        WHERE kode_cabang=? AND document_type=? AND series_code=?
          AND next_value <= end_value
        ORDER BY next_value ASC, id ASC
        LIMIT 1
        """,
        (branch, doc, series),
    ).fetchone()
    return int(row[0]) if row else None


def _reserve_remote_range(
    cursor, branch: str, doc: str, series: str, *, block_size: int = RESERVATION_BLOCK_SIZE
) -> tuple[int, int, int, int]:
    """Reservasi rentang atomik di PostgreSQL dan simpan salinannya di SQLite.

    RPC mengunci counter server dan menghitung rentang setelah nilai maksimum
    counter server serta high-water lokal. Ini mencegah dua PC online mengambil
    rentang yang tumpang tindih. Jika RPC sukses tetapi commit lokal gagal, rentang
    mungkin terbuang; rentang tersebut tidak akan dipakai ulang.
    """
    branch = str(branch or "").strip().upper()
    doc = normalize_document_type(doc)
    series = str(series or "").strip().upper()
    if not branch or not series:
        raise NumberingError("Cabang dan seri wajib diisi untuk reservasi nomor.")
    size = int(block_size)
    if size < 1 or size > 50:
        raise NumberingError("Ukuran reservasi nomor harus antara 1 dan 50.")

    local_counter = cursor.execute(
        """
        SELECT starting_count, current_count, padding
        FROM numbering_counters
        WHERE kode_cabang=? AND document_type=? AND series_code=?
          AND COALESCE(aktif,0)=1 AND deleted_at IS NULL
        LIMIT 1
        """,
        (branch, doc, series),
    ).fetchone()
    if not local_counter:
        raise NumberingError(
            f"Counter {branch}/{doc}/{series} tidak aktif atau belum tersedia di database lokal. "
            "Sinkronkan konfigurasi penomoran terlebih dahulu."
        )

    client = _online_supabase_client()
    if client is None:
        raise NumberingError(
            f"Tidak ada nomor cadangan tersisa untuk {branch}/{doc}/{series}. "
            "Sambungkan ke Supabase dan jalankan sinkronisasi sebelum membuat dokumen berikutnya."
        )

    local_start = int(local_counter[0] or 0)
    local_current = int(local_counter[1] or 0)
    try:
        response = client.rpc(
            "reserve_number_range",
            {
                "p_kode_cabang": branch,
                "p_document_type": doc,
                "p_series_code": series,
                "p_local_starting_count": local_start,
                "p_local_current_count": local_current,
                "p_block_size": size,
            },
        ).execute()
    except Exception as exc:
        raise NumberingError(
            f"Gagal reservasi nomor {branch}/{doc}/{series} di server. "
            "Nomor tidak dibuat agar tidak berisiko bentrok. Periksa koneksi dan SQL reservasi Supabase."
        ) from exc

    data = getattr(response, "data", None)
    if isinstance(data, dict):
        row = data
    elif isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
        row = data[0]
    else:
        row = None
    if not row:
        raise NumberingError(
            f"Supabase tidak mengembalikan rentang nomor untuk {branch}/{doc}/{series}. "
            "Pastikan counter aktif, izin cabang benar, dan SQL reservasi sudah dipasang."
        )

    try:
        range_start = int(row.get("range_start"))
        range_end = int(row.get("range_end"))
        effective_start = int(row.get("starting_count", local_start))
        padding = max(1, int(row.get("padding", local_counter[2] or DEFAULT_PADDING[doc])))
    except (TypeError, ValueError) as exc:
        raise NumberingError("Respons rentang nomor dari Supabase tidak valid.") from exc
    if range_start < 0 or range_end < range_start or range_end - range_start + 1 != size:
        raise NumberingError("Rentang nomor dari Supabase tidak valid atau ukurannya tidak sesuai.")

    _ensure_local_reservation_schema(cursor)
    cursor.execute(
        f"""
        INSERT INTO {LOCAL_RESERVATION_TABLE}
            (kode_cabang, document_type, series_code, next_value, end_value)
        VALUES (?, ?, ?, ?, ?)
        """,
        (branch, doc, series, range_start, range_end),
    )
    # High-water lokal juga mencerminkan seluruh rentang yang telah diklaim di
    # server. Karena RPC sudah memajukan counter Supabase secara atomik, update
    # lokal ini bukan perubahan baru yang perlu dimasukkan lagi ke sync_outbox.
    # Supress hanya trigger outbox untuk update counter ini; pulihkan nilai lama
    # agar status suppress milik pemanggil (jika ada) tidak tertimpa.
    has_sync_control = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sync_control' LIMIT 1"
    ).fetchone()
    previous_suppress = None
    if has_sync_control:
        cursor.execute(
            "INSERT OR IGNORE INTO sync_control(id, suppress_outbox) VALUES (1, 0)"
        )
        state_row = cursor.execute(
            "SELECT suppress_outbox FROM sync_control WHERE id=1 LIMIT 1"
        ).fetchone()
        previous_suppress = int(state_row[0] or 0) if state_row else 0
        cursor.execute("UPDATE sync_control SET suppress_outbox=1 WHERE id=1")
    try:
        cursor.execute(
            """
            UPDATE numbering_counters
            SET starting_count=MAX(COALESCE(starting_count,0), ?),
                current_count=MAX(COALESCE(current_count,0), ?),
                padding=?, updated_at=CURRENT_TIMESTAMP
            WHERE kode_cabang=? AND document_type=? AND series_code=?
            """,
            (effective_start, range_end, padding, branch, doc, series),
        )
    finally:
        if previous_suppress is not None:
            cursor.execute(
                "UPDATE sync_control SET suppress_outbox=? WHERE id=1",
                (previous_suppress,),
            )
    return range_start, range_end, effective_start, padding


def _consume_reserved_sequence(cursor, branch: str, doc: str, series: str) -> Optional[int]:
    _ensure_local_reservation_schema(cursor)
    row = cursor.execute(
        f"""
        SELECT id, next_value
        FROM {LOCAL_RESERVATION_TABLE}
        WHERE kode_cabang=? AND document_type=? AND series_code=?
          AND next_value <= end_value
        ORDER BY next_value ASC, id ASC
        LIMIT 1
        """,
        (branch, doc, series),
    ).fetchone()
    if not row:
        return None
    reservation_id, sequence = int(row[0]), int(row[1])
    cursor.execute(
        f"""
        UPDATE {LOCAL_RESERVATION_TABLE}
        SET next_value = next_value + 1
        WHERE id=? AND next_value=? AND next_value <= end_value
        """,
        (reservation_id, sequence),
    )
    if cursor.rowcount != 1:
        raise NumberingError("Cadangan nomor lokal berubah saat sedang dipakai; ulangi transaksi.")
    return sequence


def peek_reserved_sequence_cursor(cursor, kode_cabang, document_type, series_code):
    """API kecil untuk preview modul yang membaca sequence counter langsung."""
    branch = str(kode_cabang or "").strip().upper()
    doc = normalize_document_type(document_type)
    series = str(series_code or "").strip().upper()
    if not branch or not series or doc == "INVOICE" or _is_local_only_mode():
        return None
    return _next_reserved_sequence_cursor(cursor, branch, doc, series)


def prefetch_local_reservations(*, db_name: Optional[str] = None) -> int:
    """Siapkan rentang offline setelah satu siklus sync online berhasil.

    Hanya series RESI/MANIFEST pada cabang aktif yang diisi agar tidak mengambil
    rentang untuk cabang lain tanpa perlu. Invoice sengaja tidak diubah karena
    modul invoice-sync belum masuk cakupan perubahan ini.
    """
    if _is_local_only_mode() or bool(CURRENT_SESSION.get("is_offline_session")):
        return 0
    client = _online_supabase_client()
    if client is None:
        return 0

    branch = str(CURRENT_SESSION.get("kode_cabang") or "").strip().upper()
    if not branch or not cabang_boleh_tulis(branch):
        return 0

    conn = _conn(db_name)
    reserved = 0
    try:
        cur = conn.cursor()
        _ensure_local_reservation_schema(cur)
        conn.commit()
        keys = cur.execute(
            """
            SELECT kode_cabang, document_type, series_code
            FROM numbering_counters
            WHERE kode_cabang=?
              AND document_type IN ('RESI','MANIFEST')
              AND COALESCE(aktif,0)=1 AND deleted_at IS NULL
            ORDER BY document_type, series_code
            """,
            (branch,),
        ).fetchall()

        for counter_branch, doc, series in keys:
            try:
                conn.execute("BEGIN IMMEDIATE")
                remaining = _reservation_remaining(cur, counter_branch, doc, series)
                if remaining <= RESERVATION_PREFETCH_THRESHOLD:
                    _reserve_remote_range(
                        cur, counter_branch, doc, series,
                        block_size=RESERVATION_BLOCK_SIZE,
                    )
                    conn.commit()
                    reserved += 1
                elif conn.in_transaction:
                    conn.rollback()
            except Exception as exc:
                if conn.in_transaction:
                    conn.rollback()
                # Kegagalan prefetch tidak menggagalkan sync data lainnya. Bila
                # nanti rentang benar-benar habis, allocator akan menolak dengan
                # pesan aman alih-alih memakai counter lokal yang bisa bentrok.
                logger.debug(
                    "[Numbering] Prefetch %s/%s/%s tertunda: %s",
                    counter_branch, doc, series, exc,
                )
        return reserved
    finally:
        conn.close()


def allocate_number_cursor(
    cursor,
    document_type,
    kode_cabang,
    *,
    wilayah="",
    tanggal=None,
    suffix="",
):
    """Alokasikan nomor di transaksi SQLite caller.

    Untuk RESI/MANIFEST user normal, nomor selalu berasal dari rentang yang
    sebelumnya dicadangkan atomik di Supabase. Ketika offline, rentang lokal yang
    tersisa tetap dapat dipakai. DEV_SUPER tetap sepenuhnya lokal; Invoice tidak
    diubah karena alur invoice-sync belum termasuk perubahan ini.
    """
    doc = normalize_document_type(document_type)
    branch, series, default_start, default_padding = resolve_series(
        cursor, doc, kode_cabang, wilayah
    )
    _pastikan_boleh_tulis_cabang(branch)
    start, current, padding, _aktif = _ensure_counter(
        cursor, branch, doc, series, default_start, default_padding
    )
    start = int(start or 0)
    current = int(current or 0)
    padding = max(1, int(padding or default_padding))

    # DEV_SUPER adalah aplikasi lokal independen. Invoice tetap menggunakan alur
    # counter yang sudah ada karena sinkronisasi invoice belum diaktifkan.
    if doc == "INVOICE" or _is_local_only_mode():
        sequence = max(start, current + 1)
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
        nomor = _format_number(doc, series, sequence, padding, tanggal, suffix)
        return NumberingResult(doc, branch, series, sequence, nomor, start, padding)

    _ensure_local_reservation_schema(cursor)
    sequence = _consume_reserved_sequence(cursor, branch, doc, series)
    if sequence is None:
        _reserve_remote_range(cursor, branch, doc, series, block_size=RESERVATION_BLOCK_SIZE)
        sequence = _consume_reserved_sequence(cursor, branch, doc, series)
    if sequence is None:
        raise NumberingError(
            f"Rentang nomor {branch}/{doc}/{series} tidak tersedia. "
            "Sinkronkan aplikasi saat online, lalu ulangi penyimpanan."
        )

    # Baca metadata lokal setelah reservasi, karena RPC dapat menyelaraskan
    # padding/starting_count dengan konfigurasi resmi server.
    local = cursor.execute(
        """
        SELECT starting_count, padding
        FROM numbering_counters
        WHERE kode_cabang=? AND document_type=? AND series_code=?
        LIMIT 1
        """,
        (branch, doc, series),
    ).fetchone()
    if local:
        start = int(local[0] or start)
        padding = max(1, int(local[1] or padding))
    nomor = _format_number(doc, series, sequence, padding, tanggal, suffix)
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
        reserved_sequence = None
        if doc != "INVOICE" and not _is_local_only_mode():
            reserved_sequence = _next_reserved_sequence_cursor(cursor, branch, doc, series)
        sequence = (
            int(reserved_sequence)
            if reserved_sequence is not None
            else max(int(start or 0), int(current or 0) + 1)
        )
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
        # Rentang lokal untuk counter yang diubah tidak boleh digunakan setelah
        # konfigurasi berubah. Rentang yang sudah dicadangkan server tetap tidak
        # pernah dipakai ulang; nilai berikutnya akan diminta setelah high-water.
        _ensure_local_reservation_schema(conn.cursor())
        conn.execute(
            f"DELETE FROM {LOCAL_RESERVATION_TABLE} WHERE kode_cabang=? AND document_type=? AND series_code=?",
            (branch, doc, series),
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
    "peek_reserved_sequence_cursor",
    "prefetch_local_reservations",
]