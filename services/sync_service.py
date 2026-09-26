# services/sync_service.py
"""Mesin sinkronisasi offline-first Kargo.

Master wilayah/cabang_wilayah bersifat two-way:
- perubahan dari Settings -> SQLite -> outbox -> Supabase
- perubahan langsung di Supabase -> pull penuh master -> SQLite

Supabase tetap menjadi sumber pusat. Untuk konflik master konfigurasi,
perubahan server yang lebih baru menang dan perubahan lokal lama ditandai
sebagai CONFLICT agar tidak menimpa server secara diam-diam.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config import CURRENT_SESSION
from supabase_client import supabase

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
TABLES = {"data_resi", "data_resi_detail", "master_wilayah", "cabang_wilayah", "numbering_settings", "master_option"}
MASTER_TABLES = {"master_wilayah", "cabang_wilayah", "numbering_settings", "master_option"}


def _db_path() -> str:
    return str(CURRENT_SESSION.get("db_name") or "database_cargo.db")


def _connect():
    conn = sqlite3.connect(_db_path(), timeout=20.0)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    return conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_state(conn, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT nilai FROM sync_state WHERE kunci = ? LIMIT 1", (key,)
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else default


def _set_state(conn, key: str, value: Any) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO sync_state(kunci, nilai) VALUES (?, ?)",
        (key, str(value)),
    )


def _set_suppress(conn, enabled: bool) -> None:
    conn.execute(
        "UPDATE sync_control SET suppress_outbox = ? WHERE id = 1",
        (1 if enabled else 0,),
    )


def _session_ready() -> bool:
    # auth_email diisi hanya ketika login Supabase berhasil.
    if not str(CURRENT_SESSION.get("auth_email") or "").strip():
        return False
    try:
        return supabase.auth.get_session() is not None
    except Exception:
        return False


def _to_int(value: Any, default: int = 0) -> int:
    """Normalisasi angka ke integer PostgreSQL; string kosong menjadi default."""
    if value is None:
        return int(default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return int(default)
    try:
        return int(float(text))
    except (TypeError, ValueError):
        raise ValueError(f"Nilai integer tidak valid untuk sync: {value!r}")


def _to_float(value: Any, default: float = 0.0) -> float:
    """Normalisasi angka ke float; string kosong menjadi default."""
    if value is None:
        return float(default)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return float(default)
    try:
        return float(text.replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"Nilai float tidak valid untuk sync: {value!r}")


def _to_date_or_none(value: Any):
    """Tanggal kosong dikirim sebagai NULL, bukan string kosong."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_payload(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Payload sync tidak berbentuk object JSON.")

    payload = dict(value)

    # SQLite lama menyimpan beberapa field numerik sebagai '' ketika form
    # belum mengisinya. PostgreSQL bigint/double precision menolak ''.
    if "data_resi" in TABLES or "no_resi" in payload:
        for key in (
            "ongkir_per_kg",
            "ongkir_per_cbm",
            "subtotal_ongkir",
            "total_ongkir",
            "revision",
        ):
            if key in payload:
                payload[key] = _to_int(payload.get(key), 0)

        for key in ("berat", "cbm"):
            if key in payload:
                payload[key] = _to_float(payload.get(key), 0.0)

        for key in ("tanggal_masuk", "tanggal_keluar"):
            if key in payload:
                payload[key] = _to_date_or_none(payload.get(key))

    # Detail barang juga dinormalisasi agar aman terhadap database SQLite lama.
    if "data_resi_detail" in TABLES and "sync_id" in payload:
        if "urutan" in payload:
            payload["urutan"] = _to_int(payload.get("urutan"), 1)
        for key in ("berat", "cbm"):
            if key in payload:
                payload[key] = _to_float(payload.get(key), 0.0)

    if isinstance(payload.get("rincian_json"), str):
        raw = payload.get("rincian_json") or "[]"
        try:
            payload["rincian_json"] = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload["rincian_json"] = []

    if "numbering_settings" in TABLES or "document_type" in payload:
        for key in ("starting_count", "current_count", "padding", "urutan"):
            if key in payload:
                payload[key] = _to_int(payload.get(key), 0)
        payload["aktif"] = 1 if payload.get("aktif", True) else 0

    if "master_option" in TABLES or "option_group" in payload:
        if "urutan" in payload:
            payload["urutan"] = _to_int(payload.get("urutan"), 0)
        payload["aktif"] = 1 if payload.get("aktif", True) else 0

    return payload


def _server_upsert(table_name: str, operation: str, payload: Dict[str, Any]) -> None:
    clean = _json_payload(payload)

    # Server memakai soft-delete: row tetap ada, tetapi deleted_at diisi.
    if operation == "DELETE":
        clean["deleted_at"] = _utc_now()

    # Supabase menjaga kolom identitas internal. Untuk detail barang, `sync_id`
    # adalah conflict target agar id_detail boleh berbeda antar perangkat.
    if table_name == "data_resi":
        # Conflict target sync_id mencegah dua perangkat offline yang kebetulan
        # menghasilkan no_resi sama saling menimpa secara diam-diam. Dalam kasus
        # collision no_resi dengan sync_id berbeda, server akan menolak dan item
        # tetap berada di outbox untuk ditangani sebagai konflik.
        response = (
            supabase
            .table("data_resi")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    elif table_name == "data_resi_detail":
        if not clean.get("sync_id"):
            raise ValueError("data_resi_detail tidak memiliki sync_id.")
        # id_detail adalah identity server dan tidak boleh dipaksakan dari
        # perangkat lain; sync_id menjadi identitas lintas perangkat.
        clean.pop("id_detail", None)
        response = (
            supabase
            .table("data_resi_detail")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    elif table_name == "master_wilayah":
        clean.pop("id", None)
        response = (
            supabase
            .table("master_wilayah")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    elif table_name == "cabang_wilayah":
        clean.pop("id", None)
        response = (
            supabase
            .table("cabang_wilayah")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    elif table_name == "numbering_settings":
        clean.pop("id", None)
        response = (
            supabase
            .table("numbering_settings")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    elif table_name == "master_option":
        clean.pop("id", None)
        response = (
            supabase
            .table("master_option")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    else:
        raise ValueError(f"Tabel sync belum didukung: {table_name}")

    if getattr(response, "data", None) is None:
        # Client biasanya melempar exception bila HTTP/API gagal.
        # Tetap anggap response tanpa data sebagai sukses karena beberapa
        # konfigurasi return representation dapat kosong.
        return


def _mark_success(conn, outbox_id: int, table_name: str, record_key: str) -> None:
    conn.execute(
        """
        UPDATE sync_outbox
        SET status = 'SYNCED', last_error = NULL
        WHERE id = ?
        """,
        (outbox_id,),
    )
    if table_name == "data_resi":
        conn.execute(
            "UPDATE data_resi SET is_synced = 1 WHERE no_resi = ?",
            (record_key,),
        )


def _mark_error(conn, outbox_id: int, error: Exception) -> None:
    conn.execute(
        """
        UPDATE sync_outbox
        SET status = 'PENDING', retry_count = retry_count + 1,
            last_error = ?
        WHERE id = ?
        """,
        (str(error)[:2000], outbox_id),
    )


def _parse_dt(value: Any):
    """Parse timestamps into comparable timezone-aware UTC datetimes.

    SQLite often returns CURRENT_TIMESTAMP as a naive UTC string, while
    PostgreSQL/Supabase returns timestamptz values with an explicit offset.
    Normalizing both to UTC prevents "offset-naive and offset-aware" errors.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if dt.tzinfo is None:
        # SQLite CURRENT_TIMESTAMP is UTC but stored without tzinfo.
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _server_master_row(table_name: str, sync_id: str) -> Optional[Dict[str, Any]]:
    if table_name not in MASTER_TABLES or not sync_id:
        return None
    response = (
        supabase
        .table(table_name)
        .select("*")
        .eq("sync_id", sync_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def _local_master_is_older_than_server(
    table_name: str,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return remote row when it is newer than the local pending change."""
    if table_name not in MASTER_TABLES:
        return None
    sync_id = str(payload.get("sync_id") or "").strip()
    if not sync_id:
        return None
    remote = _server_master_row(table_name, sync_id)
    if not remote:
        return None
    local_dt = _parse_dt(payload.get("updated_at"))
    remote_dt = _parse_dt(remote.get("updated_at"))
    if local_dt is None or remote_dt is None:
        return None
    if remote_dt > local_dt:
        return remote
    return None


def _mark_conflict(
    conn,
    outbox_id: int,
    table_name: str,
    record_key: str,
    local_payload: Dict[str, Any],
    remote_payload: Dict[str, Any],
) -> None:
    event_key = f"PUSH-CONFLICT:{table_name}:{record_key}:{remote_payload.get('updated_at') or ''}"
    conn.execute(
        """
        INSERT OR IGNORE INTO sync_conflicts(
            event_key, table_name, record_key, local_payload, remote_payload, status
        ) VALUES (?, ?, ?, ?, ?, 'OPEN')
        """,
        (
            event_key,
            table_name,
            record_key,
            json.dumps(local_payload, ensure_ascii=False),
            json.dumps(remote_payload, ensure_ascii=False),
        ),
    )
    conn.execute(
        """
        UPDATE sync_outbox
        SET status = 'CONFLICT',
            retry_count = retry_count + 1,
            last_error = ?
        WHERE id = ?
        """,
        (
            "Perubahan lokal kalah dari perubahan server yang lebih baru.",
            outbox_id,
        ),
    )


def push_pending(limit: int = BATCH_SIZE) -> int:
    if not _session_ready():
        return 0

    conn = _connect()
    berhasil = 0
    try:
        rows = conn.execute(
            """
            SELECT id, table_name, record_key, operation, payload_json
            FROM sync_outbox
            WHERE status = 'PENDING'
              AND table_name IN (
                  'master_wilayah', 'cabang_wilayah',
                  'data_resi', 'data_resi_detail'
              )
            ORDER BY
                CASE table_name
                    WHEN 'master_wilayah' THEN 1
                    WHEN 'cabang_wilayah' THEN 2
                    WHEN 'data_resi' THEN 3
                    WHEN 'data_resi_detail' THEN 4
                    ELSE 9
                END, id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

        for outbox_id, table_name, record_key, operation, payload_json in rows:
            try:
                payload = json.loads(payload_json)

                # Untuk master konfigurasi, cek apakah Supabase sudah berubah
                # lebih baru. Kalau iya, server menang; local change tidak
                # boleh menimpa edit server secara diam-diam.
                if table_name in MASTER_TABLES and operation in {'UPDATE', 'DELETE'}:
                    remote_newer = _local_master_is_older_than_server(table_name, payload)
                    if remote_newer:
                        _mark_conflict(
                            conn, outbox_id, table_name, record_key, payload, remote_newer
                        )
                        conn.commit()
                        logger.warning(
                            "[SYNC] Konflik %s/%s: server lebih baru, perubahan lokal ditahan.",
                            table_name, record_key,
                        )
                        continue

                _server_upsert(table_name, operation, payload)
                _mark_success(conn, outbox_id, table_name, record_key)
                conn.commit()
                berhasil += 1
            except Exception as exc:
                conn.rollback()
                _mark_error(conn, outbox_id, exc)
                conn.commit()
                logger.warning(
                    "[SYNC] Push gagal #%s %s/%s: %s",
                    outbox_id, table_name, record_key, exc,
                )
                # Jangan menerobos antrean. Urutan perubahan satu per satu lebih aman.
                break
        return berhasil
    finally:
        conn.close()


def _has_pending(conn, table_name: str, record_key: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM sync_outbox
        WHERE status = 'PENDING'
          AND table_name = ?
          AND record_key = ?
        LIMIT 1
        """,
        (table_name, record_key),
    ).fetchone()
    return row is not None


def _record_key_from_remote(table_name: str, payload: Dict[str, Any]) -> str:
    if table_name == "data_resi":
        return str(payload.get("no_resi") or "").strip().upper()
    return str(payload.get("sync_id") or "").strip()


def _apply_remote_resi(conn, payload: Dict[str, Any]) -> None:
    columns = [
        "no_resi", "kode_cabang", "tanggal_masuk", "tanggal_keluar", "pengirim",
        "hp_pengirim", "alamat_pengirim", "kota_asal", "penerima", "hp_penerima",
        "alamat_penerima", "kota_tujuan", "nama_barang", "koli", "berat", "cbm",
        "ongkir_per_kg", "ongkir_per_cbm", "subtotal_ongkir", "jenis_pajak",
        "total_ongkir", "pembayaran", "status_resi", "foto_bukti", "truk",
        "ket_buku_gudang", "no_manifest", "ket_manifest", "rincian_json", "is_synced",
        "revision", "created_at", "updated_at", "sync_id", "deleted_at",
    ]
    values = [payload.get(c) for c in columns]
    if isinstance(values[28], (dict, list)):
        values[28] = json.dumps(values[28], ensure_ascii=False)
    values[29] = 1
    conn.execute(
        f"""
        INSERT INTO data_resi ({', '.join(columns)})
        VALUES ({', '.join('?' for _ in columns)})
        ON CONFLICT(no_resi) DO UPDATE SET
            {', '.join(f'{c}=excluded.{c}' for c in columns if c != 'no_resi')}
        """,
        values,
    )


def _apply_remote_detail(conn, payload: Dict[str, Any], operation: str) -> None:
    sync_id = str(payload.get("sync_id") or "").strip()
    if not sync_id:
        raise ValueError("Perubahan detail dari server tidak memiliki sync_id.")

    if operation == "DELETE":
        conn.execute(
            "DELETE FROM data_resi_detail WHERE sync_id = ?",
            (sync_id,),
        )
        return

    existing = conn.execute(
        "SELECT id_detail FROM data_resi_detail WHERE sync_id = ? LIMIT 1",
        (sync_id,),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE data_resi_detail
            SET no_resi=?, urutan=?, nama_barang=?, koli=?, berat=?, cbm=?,
                created_at=?, updated_at=?, deleted_at=?
            WHERE sync_id=?
            """,
            (
                payload.get("no_resi"), payload.get("urutan"), payload.get("nama_barang"),
                payload.get("koli"), payload.get("berat", 0), payload.get("cbm", 0),
                payload.get("created_at"), payload.get("updated_at"), payload.get("deleted_at"),
                sync_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO data_resi_detail
            (no_resi, urutan, nama_barang, koli, berat, cbm, created_at, updated_at, sync_id, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("no_resi"), payload.get("urutan"), payload.get("nama_barang"),
                payload.get("koli"), payload.get("berat", 0), payload.get("cbm", 0),
                payload.get("created_at"), payload.get("updated_at"), sync_id, payload.get("deleted_at"),
            ),
        )


def _apply_remote_numbering(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    sid = str(payload.get("sync_id") or "").strip()
    branch = str(payload.get("kode_cabang") or "").strip().upper()
    doc = str(payload.get("document_type") or "").strip().upper()
    if not sid or not branch or not doc:
        return False
    local = conn.execute("SELECT updated_at FROM numbering_settings WHERE sync_id=? LIMIT 1", (sid,)).fetchone()
    if not force and local and _parse_dt(local[0]) and _parse_dt(payload.get("updated_at")) and _parse_dt(payload.get("updated_at")) <= _parse_dt(local[0]):
        return False
    conn.execute("""
        INSERT INTO numbering_settings(kode_cabang,document_type,format_template,starting_count,current_count,padding,reset_rule,aktif,sync_id,created_at,updated_at,deleted_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(kode_cabang,document_type) DO UPDATE SET
          format_template=excluded.format_template, starting_count=excluded.starting_count, current_count=excluded.current_count,
          padding=excluded.padding, reset_rule=excluded.reset_rule, aktif=excluded.aktif, sync_id=excluded.sync_id,
          created_at=excluded.created_at, updated_at=excluded.updated_at, deleted_at=excluded.deleted_at
    """, (branch,doc,str(payload.get("format_template") or "{SEQ}"),_to_int(payload.get("starting_count"),1),_to_int(payload.get("current_count"),0),_to_int(payload.get("padding"),5),str(payload.get("reset_rule") or "NONE"),1 if payload.get("aktif",True) else 0,sid,payload.get("created_at"),payload.get("updated_at"),payload.get("deleted_at")))
    return True


def _apply_remote_option(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    sid = str(payload.get("sync_id") or "").strip()
    group = str(payload.get("option_group") or "").strip().upper()
    code = str(payload.get("option_code") or "").strip().upper()
    scope = str(payload.get("kode_cabang") or "*").strip().upper() or "*"
    if not sid or not group or not code:
        return False
    local = conn.execute("SELECT updated_at FROM master_option WHERE sync_id=? LIMIT 1", (sid,)).fetchone()
    if not force and local and _parse_dt(local[0]) and _parse_dt(payload.get("updated_at")) and _parse_dt(payload.get("updated_at")) <= _parse_dt(local[0]):
        return False
    conn.execute("""
        INSERT INTO master_option(option_group,option_code,option_label,kode_cabang,urutan,aktif,sync_id,created_at,updated_at,deleted_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(kode_cabang,option_group,option_code) DO UPDATE SET
          option_label=excluded.option_label, urutan=excluded.urutan, aktif=excluded.aktif, sync_id=excluded.sync_id,
          created_at=excluded.created_at, updated_at=excluded.updated_at, deleted_at=excluded.deleted_at
    """, (group,code,str(payload.get("option_label") or code),scope,_to_int(payload.get("urutan"),0),1 if payload.get("aktif",True) else 0,sid,payload.get("created_at"),payload.get("updated_at"),payload.get("deleted_at")))
    return True


def sync_generic_masters() -> Dict[str, int]:
    if not _session_ready():
        return {"numbering":0,"options":0}
    numbering = _fetch_all("numbering_settings", columns="kode_cabang,document_type,format_template,starting_count,current_count,padding,reset_rule,aktif,sync_id,created_at,updated_at,deleted_at", page_size=500)
    options = _fetch_all("master_option", columns="option_group,option_code,option_label,kode_cabang,urutan,aktif,sync_id,created_at,updated_at,deleted_at", page_size=500)
    conn=_connect(); n=o=0
    try:
        _set_suppress(conn, True)
        for row in numbering:
            if _apply_remote_numbering(conn,row,force=False): n+=1
        for row in options:
            if _apply_remote_option(conn,row,force=False): o+=1
        _set_suppress(conn, False); conn.commit(); return {"numbering":n,"options":o}
    except Exception:
        _set_suppress(conn, False); conn.rollback(); raise
    finally: conn.close()


def pull_server_changes(limit: int = BATCH_SIZE) -> int:
    if not _session_ready():
        return 0

    conn = _connect()
    diterapkan = 0
    try:
        cursor = int(_get_state(conn, "last_server_change_id", "0") or 0)
        response = (
            supabase
            .table("sync_changes")
            .select("id,event_id,table_name,record_sync_id,operation,row_data,changed_at")
            .gt("id", cursor)
            .in_("table_name", ["data_resi", "data_resi_detail", "numbering_settings", "master_option", "master_wilayah", "cabang_wilayah"])
            .order("id", desc=False)
            .limit(int(limit))
            .execute()
        )
        events = response.data or []

        for event in events:
            event_id = str(event.get("event_id") or "")
            table_name = str(event.get("table_name") or "").strip()
            operation = str(event.get("operation") or "").strip().upper()
            payload = event.get("row_data")
            if table_name not in TABLES or not isinstance(payload, dict):
                _set_state(conn, "last_server_change_id", event.get("id", cursor))
                conn.commit()
                continue

            record_key = _record_key_from_remote(table_name, payload)
            if not record_key:
                _set_state(conn, "last_server_change_id", event.get("id", cursor))
                conn.commit()
                continue

            if _has_pending(conn, table_name, record_key):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO sync_conflicts(
                        event_key, table_name, record_key, local_payload, remote_payload
                    ) VALUES (?, ?, ?,
                        (SELECT payload_json FROM sync_outbox
                         WHERE status='PENDING' AND table_name=? AND record_key=?
                         ORDER BY id DESC LIMIT 1),
                        ?
                    )
                    """,
                    (
                        event_id or str(uuid.uuid4()), table_name, record_key,
                        table_name, record_key, json.dumps(payload, ensure_ascii=False),
                    ),
                )
                logger.warning(
                    "[SYNC] Conflict %s/%s; perubahan remote disimpan di sync_conflicts.",
                    table_name, record_key,
                )
                _set_state(conn, "last_server_change_id", event.get("id", cursor))
                conn.commit()
                continue

            try:
                _set_suppress(conn, True)
                if table_name == "data_resi":
                    if operation == "DELETE":
                        conn.execute(
                            "DELETE FROM data_resi WHERE no_resi = ?",
                            (record_key,),
                        )
                    elif payload.get("deleted_at"):
                        conn.execute(
                            "DELETE FROM data_resi WHERE no_resi = ?",
                            (record_key,),
                        )
                    else:
                        _apply_remote_resi(conn, payload)
                elif table_name == "numbering_settings":
                    _apply_remote_numbering(conn, payload, force=True)
                elif table_name == "master_option":
                    _apply_remote_option(conn, payload, force=True)
                elif table_name == "master_wilayah":
                    _apply_remote_master_wilayah(conn, payload, force=True)
                elif table_name == "cabang_wilayah":
                    _apply_remote_cabang_wilayah(conn, payload, force=True)
                else:
                    _apply_remote_detail(conn, payload, operation)
                _set_suppress(conn, False)
                _set_state(conn, "last_server_change_id", event.get("id", cursor))
                conn.commit()
                diterapkan += 1
            except Exception:
                _set_suppress(conn, False)
                raise
        return diterapkan
    finally:
        conn.close()



def _fetch_all(table_name: str, *, columns: str = "*", page_size: int = 500):
    """Ambil seluruh isi tabel Supabase secara bertahap agar tidak bergantung pada satu page."""
    offset = 0
    rows = []
    while True:
        response = (
            supabase
            .table(table_name)
            .select(columns)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def _bootstrap_state(conn) -> str:
    return _get_state(conn, "initial_sync_done", "0").strip()


def _local_is_safe_for_initial_sync(conn) -> bool:
    """Bootstrap hanya otomatis pada DB yang belum berisi data operasional / antrean lokal."""
    data_resi = conn.execute("SELECT COUNT(*) FROM data_resi").fetchone()[0]
    data_detail = conn.execute("SELECT COUNT(*) FROM data_resi_detail").fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM sync_outbox WHERE status='PENDING'"
    ).fetchone()[0]
    return int(data_resi or 0) == 0 and int(data_detail or 0) == 0 and int(pending or 0) == 0


def _snapshot_change_id() -> int:
    response = (
        supabase
        .table("sync_changes")
        .select("id")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return 0
    try:
        return int(rows[0].get("id") or 0)
    except (TypeError, ValueError):
        return 0


def _apply_remote_branch(conn, payload: Dict[str, Any]) -> None:
    kode = str(payload.get("kode_cabang") or "").strip().upper()
    if not kode:
        return
    start_seq = payload.get("start_seq_json")
    aturan_prefix = payload.get("aturan_prefix")
    if isinstance(start_seq, (dict, list)):
        start_seq = json.dumps(start_seq, ensure_ascii=False)
    if isinstance(aturan_prefix, (dict, list)):
        aturan_prefix = json.dumps(aturan_prefix, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO data_cabang(
            kode_cabang, nama_cabang, resi_prefix,
            start_seq_json, aturan_prefix, created_at
        ) VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
        ON CONFLICT(kode_cabang) DO UPDATE SET
            nama_cabang=excluded.nama_cabang,
            resi_prefix=excluded.resi_prefix,
            start_seq_json=excluded.start_seq_json,
            aturan_prefix=excluded.aturan_prefix
        """,
        (
            kode,
            str(payload.get("nama_cabang") or kode),
            str(payload.get("resi_prefix") or "INV"),
            json.dumps(start_seq, ensure_ascii=False) if isinstance(start_seq, dict) else (start_seq or "{}"),
            json.dumps(aturan_prefix, ensure_ascii=False) if isinstance(aturan_prefix, dict) else (aturan_prefix or "{}"),
            payload.get("created_at"),
        ),
    )



def _apply_remote_master_wilayah(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    kode = str(payload.get("kode_wilayah") or "").strip().upper()
    if not kode:
        return False
    if not force:
        local = conn.execute(
            "SELECT updated_at FROM master_wilayah WHERE kode_wilayah = ? LIMIT 1",
            (kode,),
        ).fetchone()
        local_dt = _parse_dt(local[0]) if local and local[0] else None
        remote_dt = _parse_dt(payload.get("updated_at"))
        if local_dt is not None and remote_dt is not None and remote_dt <= local_dt:
            return False
    conn.execute(
        """
        INSERT INTO master_wilayah(
            kode_wilayah, nama_wilayah, tipe_wilayah, aktif, urutan,
            sync_id, created_at, updated_at, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(kode_wilayah) DO UPDATE SET
            nama_wilayah=excluded.nama_wilayah,
            tipe_wilayah=excluded.tipe_wilayah,
            aktif=excluded.aktif,
            urutan=excluded.urutan,
            sync_id=excluded.sync_id,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at,
            deleted_at=excluded.deleted_at
        """,
        (
            kode,
            str(payload.get("nama_wilayah") or kode),
            str(payload.get("tipe_wilayah") or "PROVINSI"),
            1 if payload.get("aktif", True) else 0,
            int(payload.get("urutan") or 0),
            str(payload.get("sync_id") or uuid.uuid4()),
            payload.get("created_at"),
            payload.get("updated_at"),
            payload.get("deleted_at"),
        ),
    )
    return True


def _apply_remote_cabang_wilayah(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    kode_cabang = str(payload.get("kode_cabang") or "").strip().upper()
    kode_wilayah = str(payload.get("kode_wilayah") or "").strip().upper()
    if not kode_cabang or not kode_wilayah:
        return False
    if not force:
        local = conn.execute(
            "SELECT updated_at FROM cabang_wilayah WHERE kode_cabang = ? AND kode_wilayah = ? LIMIT 1",
            (kode_cabang, kode_wilayah),
        ).fetchone()
        local_dt = _parse_dt(local[0]) if local and local[0] else None
        remote_dt = _parse_dt(payload.get("updated_at"))
        if local_dt is not None and remote_dt is not None and remote_dt <= local_dt:
            return False
    conn.execute(
        """
        INSERT INTO cabang_wilayah(
            kode_cabang, kode_wilayah, prefix_resi, aktif,
            sync_id, created_at, updated_at, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(kode_cabang, kode_wilayah) DO UPDATE SET
            prefix_resi=excluded.prefix_resi,
            aktif=excluded.aktif,
            sync_id=excluded.sync_id,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at,
            deleted_at=excluded.deleted_at
        """,
        (
            kode_cabang,
            kode_wilayah,
            (str(payload.get("prefix_resi") or "").strip().upper() or None),
            1 if payload.get("aktif", True) else 0,
            str(payload.get("sync_id") or uuid.uuid4()),
            payload.get("created_at"),
            payload.get("updated_at"),
            payload.get("deleted_at"),
        ),
    )
    return True


def sync_master_wilayah() -> Dict[str, int]:
    """Tarik master wilayah + aturan prefix cabang dari Supabase.

    Kedua tabel sengaja diambil penuh karena ukurannya kecil. Pull penuh membuat
    edit langsung di Supabase ikut menyebar ke semua perangkat tanpa compile ulang.
    Hanya row server yang lebih baru yang diterapkan pada sync incremental.
    """
    if not _session_ready():
        return {"wilayah": 0, "cabang_wilayah": 0}

    wilayah_rows = _fetch_all(
        "master_wilayah",
        columns=(
            "kode_wilayah,nama_wilayah,tipe_wilayah,aktif,urutan,"
            "sync_id,created_at,updated_at,deleted_at"
        ),
        page_size=250,
    )
    cabang_wilayah_rows = _fetch_all(
        "cabang_wilayah",
        columns=(
            "kode_cabang,kode_wilayah,prefix_resi,aktif,sync_id,"
            "created_at,updated_at,deleted_at"
        ),
        page_size=500,
    )

    conn = _connect()
    applied_wilayah = applied_cabang_wilayah = 0
    try:
        _set_suppress(conn, True)
        # Parent dulu, baru relasinya.
        for payload in wilayah_rows:
            if _apply_remote_master_wilayah(conn, payload, force=False):
                applied_wilayah += 1
        for payload in cabang_wilayah_rows:
            if _apply_remote_cabang_wilayah(conn, payload, force=False):
                applied_cabang_wilayah += 1
        _set_suppress(conn, False)
        conn.commit()
        return {
            "wilayah": applied_wilayah,
            "cabang_wilayah": applied_cabang_wilayah,
        }
    except Exception:
        _set_suppress(conn, False)
        conn.rollback()
        raise
    finally:
        conn.close()


def sync_all_branches() -> int:
    """Cabang adalah master kecil; sinkronkan seluruh daftar agar Ganti Cabang selalu terbaru."""
    if not _session_ready():
        return 0
    rows = _fetch_all(
        "data_cabang",
        columns="kode_cabang,nama_cabang,resi_prefix,start_seq_json,aturan_prefix,created_at",
        page_size=250,
    )
    conn = _connect()
    count = 0
    try:
        _set_suppress(conn, True)
        for payload in rows:
            _apply_remote_branch(conn, payload)
            count += 1
        _set_suppress(conn, False)
        conn.commit()
        return count
    except Exception:
        _set_suppress(conn, False)
        conn.rollback()
        raise
    finally:
        conn.close()


def initial_sync() -> Dict[str, int]:
    """Isi SQLite baru dari snapshot Supabase sebelum incremental sync dimulai."""
    if not _session_ready():
        return {"branches": 0, "wilayah": 0, "cabang_wilayah": 0, "numbering": 0, "options": 0, "resi": 0, "details": 0}

    conn = _connect()
    try:
        if _bootstrap_state(conn) == "1":
            return {"branches": 0, "wilayah": 0, "cabang_wilayah": 0, "numbering": 0, "options": 0, "resi": 0, "details": 0}
    finally:
        conn.close()

    # Ambil posisi perubahan sebelum snapshot data. Perubahan yang terjadi
    # selama bootstrap akan ditarik pada incremental sync berikutnya.
    snapshot_id = _snapshot_change_id()

    branches = _fetch_all(
        "data_cabang",
        columns="kode_cabang,nama_cabang,resi_prefix,start_seq_json,aturan_prefix,created_at",
        page_size=250,
    )
    wilayah_rows = _fetch_all(
        "master_wilayah",
        columns=(
            "kode_wilayah,nama_wilayah,tipe_wilayah,aktif,urutan,"
            "sync_id,created_at,updated_at,deleted_at"
        ),
        page_size=250,
    )
    cabang_wilayah_rows = _fetch_all(
        "cabang_wilayah",
        columns=(
            "kode_cabang,kode_wilayah,prefix_resi,aktif,sync_id,"
            "created_at,updated_at,deleted_at"
        ),
        page_size=500,
    )
    numbering_rows = _fetch_all("numbering_settings", columns="kode_cabang,document_type,format_template,starting_count,current_count,padding,reset_rule,aktif,sync_id,created_at,updated_at,deleted_at", page_size=500)
    option_rows = _fetch_all("master_option", columns="option_group,option_code,option_label,kode_cabang,urutan,aktif,sync_id,created_at,updated_at,deleted_at", page_size=500)
    resi_rows = _fetch_all("data_resi", page_size=500)
    detail_rows = _fetch_all("data_resi_detail", page_size=500)

    conn = _connect()
    applied_branches = applied_wilayah = applied_cabang_wilayah = 0
    applied_numbering = applied_options = 0
    applied_resi = applied_details = 0
    try:
        _set_suppress(conn, True)

        for payload in branches:
            _apply_remote_branch(conn, payload)
            applied_branches += 1

        # Parent master dulu, kemudian relasi prefix per cabang.
        for payload in wilayah_rows:
            if _apply_remote_master_wilayah(conn, payload, force=True):
                applied_wilayah += 1

        for payload in cabang_wilayah_rows:
            if _apply_remote_cabang_wilayah(conn, payload, force=True):
                applied_cabang_wilayah += 1

        for payload in numbering_rows:
            if _apply_remote_numbering(conn, payload, force=True):
                applied_numbering += 1

        for payload in option_rows:
            if _apply_remote_option(conn, payload, force=True):
                applied_options += 1

        for payload in resi_rows:
            if payload.get("deleted_at"):
                continue
            _apply_remote_resi(conn, payload)
            applied_resi += 1

        for payload in detail_rows:
            if payload.get("deleted_at"):
                continue
            _apply_remote_detail(conn, payload, "UPSERT")
            applied_details += 1

        _set_suppress(conn, False)
        _set_state(conn, "last_server_change_id", snapshot_id)
        _set_state(conn, "initial_sync_done", "1")
        _set_state(conn, "initial_sync_at", _utc_now())
        conn.commit()
        return {
            "branches": applied_branches,
            "wilayah": applied_wilayah,
            "cabang_wilayah": applied_cabang_wilayah,
            "numbering": applied_numbering,
            "options": applied_options,
            "resi": applied_resi,
            "details": applied_details,
        }
    except Exception:
        _set_suppress(conn, False)
        conn.rollback()
        raise
    finally:
        conn.close()

def sync_once() -> Dict[str, int]:
    """Bootstrap bila perlu, lalu push/pull incremental."""
    if not _session_ready():
        return {"pushed": 0, "pulled": 0}

    bootstrap = initial_sync()

    # Push dulu agar perubahan lokal yang masih antre tidak ditimpa oleh
    # snapshot server sebelum sempat dikirim. Konflik master dicek terhadap
    # updated_at server sebelum push.
    pushed = push_pending()

    # Setelah push, tarik kondisi server. Master kecil ditarik penuh sehingga
    # perubahan langsung dari Supabase (Table Editor/admin tooling) ikut turun.
    branches = sync_all_branches()
    wilayah = sync_master_wilayah()
    generic = sync_generic_masters()
    pulled = pull_server_changes()

    return {
        "pushed": pushed,
        "pulled": pulled,
        "initial_resi": int(bootstrap.get("resi", 0)),
        "initial_details": int(bootstrap.get("details", 0)),
        "branches": int(branches),
        "wilayah": int(wilayah.get("wilayah", 0)),
        "cabang_wilayah": int(wilayah.get("cabang_wilayah", 0)),
        "numbering": int(generic.get("numbering", 0)),
        "options": int(generic.get("options", 0)),
    }


class AutoSyncController:
    """Timer + Python worker thread yang tidak menyentuh Qt dari worker.

    Implementasi sebelumnya memakai QThread yang dibuat sebagai subclass lokal
    setiap siklus. Pada Python/PySide6 tertentu, lifecycle wrapper QThread dapat
    memicu access violation saat objek Qt dibersihkan bersamaan dengan event loop.
    Di sini pekerjaan network tetap asynchronous, tetapi worker memakai
    ``threading.Thread`` murni sehingga worker tidak membuat/menghancurkan objek Qt.
    Hanya QTimer di thread GUI yang memicu start.
    """

    def __init__(self, parent, interval_ms: int = 15_000):
        from PySide6.QtCore import QTimer

        self.parent = parent
        self.interval_ms = int(interval_ms)
        self.timer = QTimer(parent)
        self.timer.setInterval(self.interval_ms)
        self.timer.timeout.connect(self._start_worker)

        self._worker_lock = threading.Lock()
        self._worker_thread = None
        self._stopping = False

        self.timer.start()
        self._start_worker()

    def _run_worker(self):
        try:
            result = sync_once()
            print(f"[SYNC] {result}", flush=True)
        except Exception as exc:
            print(f"[SYNC] Gagal: {exc}", flush=True)
        finally:
            self._worker_lock.release()
            self._worker_thread = None

    def _start_worker(self):
        if self._stopping:
            return

        # Lock memastikan hanya satu sync berjalan pada satu waktu.
        if not self._worker_lock.acquire(blocking=False):
            return

        if not _session_ready():
            self._worker_lock.release()
            return

        try:
            worker = threading.Thread(
                target=self._run_worker,
                name="KargoSyncWorker",
                daemon=True,
            )
            self._worker_thread = worker
            worker.start()
        except Exception:
            self._worker_thread = None
            self._worker_lock.release()
            raise

    def stop(self):
        self._stopping = True
        self.timer.stop()

        worker = self._worker_thread
        if worker is not None and worker.is_alive():
            # Beri worker kesempatan menutup koneksi network dengan rapi.
            # Thread dibuat daemon sehingga aplikasi tetap bisa keluar bila
            # network request pihak ketiga menggantung lebih lama.
            worker.join(timeout=5.0)

        self._worker_thread = None