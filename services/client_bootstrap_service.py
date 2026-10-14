# service/client_bootstrap_service.py
from __future__ import annotations

"""Bootstrap white-label client config dari Supabase -> SQLite lokal.

Supabase project per client hanya perlu mempunyai satu baris public.app_config
(config_key='default'). JSON di kolom config menjadi sumber konfigurasi awal.
Business data (resi, manifest, invoice, dll.) tetap tidak di-seed di sini.
"""

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict

from audit_context import install_sqlite_audit_functions, set_sqlite_audit_sync
from config import CURRENT_SESSION
from database_manager import init_db
from supabase_client import supabase

EXPECTED_SCHEMA_VERSION = 1
CONFIG_KEY = "default"


def _db_path(db_name: str | None = None) -> str:
    return str(db_name or CURRENT_SESSION.get("db_name") or "database_cargo.db")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _fetch_remote_config() -> Dict[str, Any]:
    response = (
        supabase.table("app_config")
        .select("config_key, schema_version, config_version, client_code, config, is_active")
        .eq("config_key", CONFIG_KEY)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise RuntimeError(
            "Konfigurasi client belum tersedia di Supabase "
            "(public.app_config / config_key='default')."
        )

    row = rows[0]
    config = row.get("config")
    if not isinstance(config, dict):
        raise RuntimeError("Kolom app_config.config bukan object JSON.")

    schema_version = _as_int(row.get("schema_version"), _as_int(config.get("schema_version"), 0))
    if schema_version != EXPECTED_SCHEMA_VERSION:
        raise RuntimeError(
            f"schema_version client config tidak didukung: {schema_version}. "
            f"Aplikasi mengharapkan {EXPECTED_SCHEMA_VERSION}."
        )

    config_version = _as_int(row.get("config_version"), _as_int(config.get("config_version"), 0))
    client_code = str(row.get("client_code") or config.get("client_code") or "").strip().upper()
    if not client_code:
        raise RuntimeError("client_code pada app_config wajib diisi.")

    config["schema_version"] = schema_version
    config["config_version"] = config_version
    config["client_code"] = client_code
    return config


def _local_config_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT nilai FROM sync_state WHERE kunci = 'client_config_version' LIMIT 1"
    ).fetchone()
    return _as_int(row[0], 0) if row else 0


def _local_client_code(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT nilai FROM sync_state WHERE kunci = 'client_code' LIMIT 1"
    ).fetchone()
    return str(row[0] or "").strip().upper() if row else ""


def _set_state(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO sync_state(kunci, nilai) VALUES (?, ?)",
        (key, str(value)),
    )


def _is_business_db_empty(conn: sqlite3.Connection) -> bool:
    checks = (
        ("data_resi",),
        ("data_resi_detail",),
        ("manifest",),
        ("invoice_header",),
    )
    for (table_name,) in checks:
        row = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
        if row and int(row[0] or 0) > 0:
            return False
    return True


def _set_suppress_outbox(conn: sqlite3.Connection, enabled: bool) -> None:
    conn.execute(
        "UPDATE sync_control SET suppress_outbox = ? WHERE id = 1",
        (1 if enabled else 0,),
    )
    set_sqlite_audit_sync(conn, enabled)


def _apply_remote_counter_baseline(conn: sqlite3.Connection) -> None:
    """Tarik current_count server saat bootstrap online tanpa pernah menurunkannya."""
    try:
        rows = (
            supabase
            .table("numbering_counters")
            .select("kode_cabang,document_type,series_code,starting_count,current_count,padding,aktif,sync_id,created_at,updated_at,deleted_at")
            .execute()
        ).data or []
    except Exception as exc:
        # Bootstrap config tetap bisa dipakai offline bila query baseline gagal.
        print(f"[CLIENT_BOOTSTRAP] Baseline numbering server gagal diambil: {exc}", flush=True)
        return

    for row in rows:
        branch = str(row.get("kode_cabang") or "").strip().upper()
        doc = str(row.get("document_type") or "").strip().upper()
        series = str(row.get("series_code") or "").strip().upper()
        sid = str(row.get("sync_id") or "").strip()
        if not branch or not doc or not series or not sid:
            continue

        local = conn.execute(
            """
            SELECT starting_count,current_count
            FROM numbering_counters
            WHERE kode_cabang=? AND document_type=? AND series_code=?
            LIMIT 1
            """,
            (branch, doc, series),
        ).fetchone()

        local_start = _as_int(local[0], 0) if local else 0
        local_current = _as_int(local[1], 0) if local else 0
        start_count = max(local_start, _as_int(row.get("starting_count"), 1))
        current_count = max(local_current, _as_int(row.get("current_count"), 0))

        conn.execute(
            """
            INSERT INTO numbering_counters(
                kode_cabang,document_type,series_code,starting_count,current_count,padding,aktif,sync_id,created_at,updated_at,deleted_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(kode_cabang,document_type,series_code) DO UPDATE SET
                starting_count=MAX(numbering_counters.starting_count, excluded.starting_count),
                current_count=MAX(numbering_counters.current_count, excluded.current_count),
                padding=excluded.padding,
                aktif=excluded.aktif,
                sync_id=excluded.sync_id,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                deleted_at=excluded.deleted_at
            """,
            (
                branch, doc, series, start_count, current_count,
                max(1, _as_int(row.get("padding"), 5)),
                1 if row.get("aktif", True) else 0, sid,
                row.get("created_at"), row.get("updated_at"), row.get("deleted_at"),
            ),
        )


def _clear_client_seed_area(conn: sqlite3.Connection) -> None:
    # Hanya dipakai saat DB bisnis masih benar-benar kosong.
    conn.execute("DELETE FROM user_cabang_access")
    conn.execute("DELETE FROM manajemen_user")
    conn.execute("DELETE FROM cabang_wilayah")
    conn.execute("DELETE FROM numbering_settings")
    conn.execute("DELETE FROM data_cabang")
    conn.execute("DELETE FROM pengaturan_sistem")


def _apply_settings(conn: sqlite3.Connection, settings: Dict[str, Any]) -> None:
    rows = []
    for key, value in settings.items():
        if isinstance(value, (list, dict, bool, tuple)):
            value = json.dumps(value, ensure_ascii=False) if not isinstance(value, bool) else ("1" if value else "0")
        elif value is None:
            value = ""
        else:
            value = str(value)
        rows.append((str(key), value))
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO pengaturan_sistem(kunci, nilai) VALUES (?, ?)",
            rows,
        )


def _apply_branches(conn: sqlite3.Connection, branches: list[Dict[str, Any]]) -> None:
    for branch in branches:
        kode = str(branch.get("kode_cabang") or "").strip().upper()
        nama = str(branch.get("nama_cabang") or kode).strip().upper()
        prefix = str(branch.get("resi_prefix") or "INV").strip().upper()
        if not kode:
            raise RuntimeError("Cabang pada client config tidak memiliki kode_cabang.")
        conn.execute(
            """
            INSERT INTO data_cabang(
                kode_cabang, nama_cabang, resi_prefix,
                start_seq_json, aturan_prefix
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(kode_cabang) DO UPDATE SET
                nama_cabang = excluded.nama_cabang,
                resi_prefix = excluded.resi_prefix,
                start_seq_json = excluded.start_seq_json,
                aturan_prefix = excluded.aturan_prefix
            """,
            (
                kode,
                nama,
                prefix,
                json.dumps(branch.get("start_seq") or {"DEFAULT": 1000}, ensure_ascii=False),
                json.dumps(branch.get("aturan_prefix") or {"DEFAULT": prefix}, ensure_ascii=False),
            ),
        )



MAHKOTA_FIXED_CABANG_WILAYAH = (
    ("SBY", "KALTIM", "KT"),
    ("SBY", "KALSEL", "KS"),
    ("SBY", "LAINNYA", "IND"),
    ("JKT", "KALTIM", "J-KT"),
    ("JKT", "KALSEL", "J-KS"),
    ("JKT", "LAINNYA", "J-IND"),
)

MAHKOTA_FIXED_REGIONS = (
    {
        "kode_wilayah": "KALTIM",
        "nama_wilayah": "KALIMANTAN TIMUR",
        "tipe_wilayah": "PROVINSI",
        "aktif": 1,
        "urutan": 10,
    },
    {
        "kode_wilayah": "KALSEL",
        "nama_wilayah": "KALIMANTAN SELATAN",
        "tipe_wilayah": "PROVINSI",
        "aktif": 1,
        "urutan": 20,
    },
    {
        "kode_wilayah": "LAINNYA",
        "nama_wilayah": "PROVINSI LAINNYA",
        "tipe_wilayah": "PROVINSI",
        "aktif": 1,
        "urutan": 30,
    },
)


def _regions_for_client(client_code: str, configured: Any) -> list[Dict[str, Any]]:
    """Mahkota memakai tiga wilayah tetap; jangan mengambil daftar editable dari cloud."""
    if str(client_code or "").strip().upper() == "MAHKOTA":
        return [dict(row) for row in MAHKOTA_FIXED_REGIONS]
    return configured if isinstance(configured, list) else []

def _apply_regions(conn: sqlite3.Connection, regions: list[Dict[str, Any]]) -> None:
    # Untuk Mahkota, daftar wilayah benar-benar fixed. Bersihkan sisa wilayah
    # lama sebelum memastikan ketiga wilayah resmi tersedia.
    fixed_codes = {
        str(row.get("kode_wilayah") or "").strip().upper()
        for row in regions
    }
    if fixed_codes == {"KALTIM", "KALSEL", "LAINNYA"}:
        placeholders = ", ".join("?" for _ in fixed_codes)
        conn.execute(
            f"DELETE FROM cabang_wilayah WHERE kode_wilayah NOT IN ({placeholders})",
            tuple(sorted(fixed_codes)),
        )
        conn.execute(
            f"DELETE FROM master_wilayah WHERE kode_wilayah NOT IN ({placeholders})",
            tuple(sorted(fixed_codes)),
        )

    for index, region in enumerate(regions, start=1):
        kode = str(region.get("kode_wilayah") or "").strip().upper()
        nama = str(region.get("nama_wilayah") or "").strip().upper()
        if not kode or not nama:
            raise RuntimeError("Wilayah pada client config belum lengkap.")
        sync_id = str(region.get("sync_id") or uuid.uuid4())
        conn.execute(
            """
            INSERT INTO master_wilayah(
                kode_wilayah, nama_wilayah, tipe_wilayah,
                aktif, urutan, sync_id, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(kode_wilayah) DO UPDATE SET
                nama_wilayah = excluded.nama_wilayah,
                tipe_wilayah = excluded.tipe_wilayah,
                aktif = excluded.aktif,
                urutan = excluded.urutan,
                sync_id = excluded.sync_id,
                deleted_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                kode,
                nama,
                str(region.get("tipe_wilayah") or "PROVINSI"),
                _as_int(region.get("aktif"), 1),
                _as_int(region.get("urutan"), index * 10),
                sync_id,
            ),
        )


def _apply_branch_regions(conn: sqlite3.Connection, branches: list[Dict[str, Any]], regions: list[Dict[str, Any]], client_code: str = "") -> None:
    # Mahkota: mapping prefix cabang/wilayah juga fixed. Jangan bergantung
    # pada aturan prefix editable dari konfigurasi lama.
    fixed_rows = MAHKOTA_FIXED_CABANG_WILAYAH if str(client_code or "").strip().upper() == "MAHKOTA" else ()
    if fixed_rows:
        conn.execute("DELETE FROM cabang_wilayah WHERE kode_cabang IN ('SBY','JKT')")
        for kode_cabang, kode_wilayah, prefix in fixed_rows:
            sync_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kargo:mahkota:{kode_cabang}:{kode_wilayah}"))
            conn.execute(
                """
                INSERT INTO cabang_wilayah(
                    kode_cabang, kode_wilayah, prefix_resi, aktif, sync_id, deleted_at
                ) VALUES (?, ?, ?, 1, ?, NULL)
                ON CONFLICT(kode_cabang, kode_wilayah) DO UPDATE SET
                    prefix_resi = excluded.prefix_resi,
                    aktif = 1,
                    sync_id = excluded.sync_id,
                    deleted_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (kode_cabang, kode_wilayah, prefix, sync_id),
            )
        return

    region_by_name = {
        str(r.get("nama_wilayah") or "").strip().upper(): str(r.get("kode_wilayah") or "").strip().upper()
        for r in regions
    }
    for branch in branches:
        kode_cabang = str(branch.get("kode_cabang") or "").strip().upper()
        rules = branch.get("aturan_prefix") or {}
        if not isinstance(rules, dict):
            continue
        for raw_name, raw_prefix in rules.items():
            nama = str(raw_name or "").strip().upper()
            if nama == "DEFAULT":
                nama = "PROVINSI LAINNYA"
            kode_wilayah = region_by_name.get(nama)
            if not kode_wilayah:
                continue
            sync_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"kargo:{kode_cabang}:{kode_wilayah}"))
            conn.execute(
                """
                INSERT INTO cabang_wilayah(
                    kode_cabang, kode_wilayah, prefix_resi,
                    aktif, sync_id, deleted_at
                ) VALUES (?, ?, ?, 1, ?, NULL)
                ON CONFLICT(kode_cabang, kode_wilayah) DO UPDATE SET
                    prefix_resi = excluded.prefix_resi,
                    aktif = 1,
                    sync_id = excluded.sync_id,
                    deleted_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    kode_cabang,
                    kode_wilayah,
                    str(raw_prefix or "").strip().upper() or None,
                    sync_id,
                ),
            )


def _apply_numbering(conn: sqlite3.Connection, numbering: list[Dict[str, Any]], branches=None) -> None:
    for row in numbering:
        kode_cabang = str(row.get("kode_cabang") or "").strip().upper()
        document_type = str(row.get("document_type") or "").strip().upper()
        if not kode_cabang or not document_type:
            raise RuntimeError("Entry numbering pada client config belum lengkap.")
        conn.execute(
            """
            INSERT INTO numbering_settings(
                kode_cabang, document_type, format_template,
                starting_count, current_count, padding, reset_rule,
                aktif, sync_id, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(kode_cabang, document_type) DO UPDATE SET
                format_template = excluded.format_template,
                starting_count = excluded.starting_count,
                current_count = excluded.current_count,
                padding = excluded.padding,
                reset_rule = excluded.reset_rule,
                aktif = excluded.aktif,
                sync_id = excluded.sync_id,
                deleted_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                kode_cabang,
                document_type,
                str(row.get("format_template") or "{CABANG}-{SEQ}"),
                _as_int(row.get("starting_count"), 1),
                _as_int(row.get("current_count"), 0),
                max(1, _as_int(row.get("padding"), 5)),
                str(row.get("reset_rule") or "NONE").upper(),
                _as_int(row.get("aktif"), 1),
                str(row.get("sync_id") or uuid.uuid4()),
            ),
        )


    # Fixed-series counters: explicit series_code entries are preferred.
    explicit = [row for row in numbering if isinstance(row, dict) and row.get("series_code")]
    for row in explicit:
        kode_cabang = str(row.get("kode_cabang") or "").strip().upper()
        document_type = str(row.get("document_type") or "").strip().upper()
        series_code = str(row.get("series_code") or "").strip().upper()
        config_start = _as_int(row.get("starting_count"), 1)
        config_current = _as_int(row.get("current_count"), 0)
        config_padding = max(1, _as_int(row.get("padding"), 5))
        config_sync_id = str(row.get("sync_id") or uuid.uuid4())

        existing = conn.execute(
            """
            SELECT starting_count, current_count, sync_id
            FROM numbering_counters
            WHERE kode_cabang=? AND document_type=? AND series_code=?
            LIMIT 1
            """,
            (kode_cabang, document_type, series_code),
        ).fetchone()

        if existing:
            # Client config tidak pernah boleh menurunkan counter yang sudah
            # dicapai. Server/sync akan menjadi sumber baseline resmi sesudahnya.
            start_count = max(_as_int(existing[0], 0), config_start)
            current_count = max(_as_int(existing[1], 0), config_current)
            sync_id = str(existing[2] or config_sync_id)
            conn.execute(
                """
                UPDATE numbering_counters
                SET starting_count=?, current_count=?, padding=?, aktif=1,
                    sync_id=?, updated_at=CURRENT_TIMESTAMP, deleted_at=NULL
                WHERE kode_cabang=? AND document_type=? AND series_code=?
                """,
                (start_count, current_count, config_padding, sync_id, kode_cabang, document_type, series_code),
            )
        else:
            conn.execute(
                """
                INSERT INTO numbering_counters(
                    kode_cabang,document_type,series_code,starting_count,current_count,padding,aktif,sync_id,deleted_at
                ) VALUES (?,?,?,?,?,?,1,?,NULL)
                """,
                (kode_cabang, document_type, series_code, config_start, config_current, config_padding, config_sync_id),
            )
    if explicit or not isinstance(branches, list):
        return
    for branch in branches:
        code = str(branch.get("kode_cabang") or "").strip().upper()
        if not code:
            continue
        starts = {str(k).strip().upper(): _as_int(v,0) for k,v in (branch.get("start_seq") or {}).items()}
        rules = {str(k).strip().upper(): str(v or "").strip().upper() for k,v in (branch.get("aturan_prefix") or {}).items()}
        for key in ("KALIMANTAN TIMUR","KALIMANTAN SELATAN","DEFAULT"):
            series = rules.get(key)
            if not series:
                continue
            conn.execute("""
                INSERT OR IGNORE INTO numbering_counters(
                    kode_cabang,document_type,series_code,starting_count,current_count,padding,aktif,sync_id
                ) VALUES (?,?,?, ?,0,5,1,?)
            """, (code,"RESI",series,starts.get(series,starts.get("DEFAULT",1000)),str(uuid.uuid4())))
        jmark = "J-" if rules.get("KALIMANTAN TIMUR","").startswith("J-") else ""
        for base in ("MT","MS","MI"):
            conn.execute("""
                INSERT OR IGNORE INTO numbering_counters(
                    kode_cabang,document_type,series_code,starting_count,current_count,padding,aktif,sync_id
                ) VALUES (?,?,?,1,0,4,1,?)
            """, (code,"MANIFEST",f"{jmark}{base}",str(uuid.uuid4())))
        if code == "SBY":
            conn.execute("""
                INSERT OR IGNORE INTO numbering_counters(
                    kode_cabang,document_type,series_code,starting_count,current_count,padding,aktif,sync_id
                ) VALUES (?,?,?,1,0,4,1,?)
            """, (code,"INVOICE","INV",str(uuid.uuid4())))


def apply_client_config(db_name: str, config: Dict[str, Any]) -> bool:
    db_path = init_db(db_name)
    client_code = str(config.get("client_code") or "").strip().upper()
    config_version = _as_int(config.get("config_version"), 0)
    if not client_code or config_version < 1:
        raise RuntimeError("client config belum memiliki client_code/config_version yang valid.")

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        install_sqlite_audit_functions(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        current_version = _local_config_version(conn)
        current_client = _local_client_code(conn)

        if current_version == config_version and current_client == client_code:
            conn.commit()
            return False

        if not _is_business_db_empty(conn):
            # Config revision baru tidak boleh menghapus data bisnis.
            destructive = False
        else:
            destructive = True

        _set_suppress_outbox(conn, True)
        try:
            if destructive:
                _clear_client_seed_area(conn)

            _apply_settings(conn, config.get("settings") or {})
            branches = config.get("branches") or []
            configured_regions = config.get("regions") or []
            regions = _regions_for_client(client_code, configured_regions)
            numbering = config.get("numbering") or []
            if not isinstance(branches, list) or not isinstance(numbering, list):
                raise RuntimeError("Format client config: branches/numbering harus berupa array.")

            _apply_branches(conn, branches)
            _apply_regions(conn, regions)
            _apply_branch_regions(conn, branches, regions, client_code)
            _apply_numbering(conn, numbering, branches)
            # Online login: segera gunakan server sebagai baseline counter agar
            # UI tidak sempat melihat counter 0 dari client config lama.
            _apply_remote_counter_baseline(conn)

            _set_state(conn, "client_code", client_code)
            _set_state(conn, "client_config_version", config_version)
        finally:
            _set_suppress_outbox(conn, False)

        conn.commit()

    CURRENT_SESSION["client_code"] = client_code
    CURRENT_SESSION["client_config_version"] = config_version
    return True


def bootstrap_from_supabase(db_name: str | None = None) -> Dict[str, Any]:
    if not str(CURRENT_SESSION.get("auth_email") or "").strip():
        raise RuntimeError("Bootstrap client hanya dijalankan setelah login Supabase.")

    config = _fetch_remote_config()
    database = _db_path(db_name)
    changed = apply_client_config(database, config)
    return {
        "client_code": config["client_code"],
        "config_version": _as_int(config.get("config_version"), 0),
        "changed": changed,
    }


__all__ = [
    "bootstrap_from_supabase",
    "apply_client_config",
]
