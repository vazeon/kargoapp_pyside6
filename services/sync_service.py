# services/sync_service.py
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
from audit_context import install_sqlite_audit_functions, set_sqlite_audit_sync
from supabase_client import supabase

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
TABLES = {"data_resi", "data_resi_detail", "cabang_wilayah", "numbering_settings", "numbering_counters", "master_penerima", "master_pengirim", "truk", "kapal", "buku_gudang", "manifest"}
MASTER_TABLES = {"cabang_wilayah", "numbering_settings", "numbering_counters", "master_penerima", "master_pengirim", "truk", "kapal", "buku_gudang", "manifest"}


class SyncConflictError(RuntimeError):
    """Push ditolak karena server sudah menerima perubahan yang lebih baru."""


class SyncOfflineError(RuntimeError):
    """Sinkronisasi tidak dapat dilakukan karena koneksi jaringan tidak tersedia."""


# Kolom yang benar-benar boleh keluar dari SQLite menuju Supabase.
# Jangan memakai TABLES sebagai penentu bentuk payload: kehadiran tabel di
# aplikasi bukan berarti setiap kolom tabel tersebut berlaku untuk payload lain.
SYNC_COLUMNS = {
    "data_resi": {
        "no_resi", "kode_cabang", "tanggal_masuk", "tanggal_keluar",
        "pengirim", "hp_pengirim", "alamat_pengirim", "kota_asal",
        "penerima", "hp_penerima", "alamat_penerima", "kota_tujuan",
        "nama_barang", "koli", "berat", "cbm",
        "ongkir_per_kg", "ongkir_per_cbm", "subtotal_ongkir",
        "jenis_pajak", "total_ongkir", "pembayaran", "status_resi",
        "foto_bukti", "truk", "ket_buku_gudang", "no_manifest",
        "ket_manifest", "rincian_json", "revision",
        "created_at", "updated_at", "sync_id", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
    },
    "data_resi_detail": {
        "no_resi", "urutan", "nama_barang", "koli", "berat", "cbm",
        "created_at", "updated_at", "sync_id", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
    },

    "cabang_wilayah": {
        "kode_cabang", "kode_wilayah", "prefix_resi", "aktif",
        "sync_id", "created_at", "updated_at", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
    },
    "numbering_settings": {
        "kode_cabang", "document_type", "format_template",
        "starting_count", "current_count", "padding", "reset_rule",
        "aktif", "sync_id", "created_at", "updated_at", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
    },
    "numbering_counters": {
        "kode_cabang", "document_type", "series_code",
        "starting_count", "current_count", "padding", "aktif",
        "sync_id", "created_at", "updated_at", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
    },
    "master_penerima": {
        "id_penerima", "kode_cabang", "nama", "no_hp", "alamat", "kota", "provinsi",
        "total_transaksi", "pembayaran", "status_tagihan", "sync_id", "created_at",
        "updated_at", "deleted_at", "created_by_user_id", "created_by_username",
        "created_by_name", "updated_by_user_id", "updated_by_username", "updated_by_name",
    },
    "master_pengirim": {
        "id_pengirim", "kode_cabang", "nama", "no_hp", "alamat", "kota", "sync_id",
        "created_at", "updated_at", "deleted_at", "created_by_user_id",
        "created_by_username", "created_by_name", "updated_by_user_id",
        "updated_by_username", "updated_by_name",
    },
    "truk": {
        "kode_cabang", "jenis_truk", "no_polisi", "nama_sopir", "hp_sopir", "ket_truk",
        "foto_truk", "sync_id", "created_at", "updated_at", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
    },
    "kapal": {
        "nama_kapal", "tujuan", "ket_kapal", "foto_kapal", "sync_id", "created_at",
        "updated_at", "deleted_at", "created_by_user_id", "created_by_username",
        "created_by_name", "updated_by_user_id", "updated_by_username", "updated_by_name",
    },
    "buku_gudang": {
        "id_gudang", "kode_cabang", "tanggal", "no_resi", "jenis", "status_resi",
        "sync_id", "created_at", "updated_at", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
    },
    "manifest": {
        "id_manifest", "kode_cabang", "tanggal", "no_polisi", "nama_sopir",
        "nama_kapal", "note_manifest", "status_manifest", "sync_id",
        "created_at", "updated_at", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
    },
}

MAHKOTA_FIXED_CABANG_WILAYAH = {
    ("SBY", "KALTIM"): "KT",
    ("SBY", "KALSEL"): "KS",
    ("SBY", "LAINNYA"): "IND",
    ("JKT", "KALTIM"): "J-KT",
    ("JKT", "KALSEL"): "J-KS",
    ("JKT", "LAINNYA"): "J-IND",
}

MAHKOTA_FIXED_BRANCH_RULES = {
    "SBY": {
        "KALIMANTAN TIMUR": "KT",
        "KALIMANTAN SELATAN": "KS",
        "DEFAULT": "IND",
    },
    "JKT": {
        "KALIMANTAN TIMUR": "J-KT",
        "KALIMANTAN SELATAN": "J-KS",
        "DEFAULT": "J-IND",
    },
}

SYNC_REQUIRED = {
    "data_resi": {"no_resi", "kode_cabang", "sync_id"},
    "data_resi_detail": {"no_resi", "sync_id"},
    "cabang_wilayah": {"kode_cabang", "kode_wilayah", "sync_id"},
    "numbering_settings": {"kode_cabang", "document_type", "sync_id"},
    "numbering_counters": {"kode_cabang", "document_type", "series_code", "sync_id"},
    "master_penerima": {"id_penerima", "kode_cabang", "sync_id"},
    "master_pengirim": {"id_pengirim", "kode_cabang", "sync_id"},
    "truk": {"kode_cabang", "no_polisi", "sync_id"},
    "kapal": {"nama_kapal", "sync_id"},
    "buku_gudang": {"id_gudang", "kode_cabang", "sync_id"},
    "manifest": {"id_manifest", "kode_cabang", "sync_id"},
}



def _db_path() -> str:
    return str(CURRENT_SESSION.get("db_name") or "database_cargo.db")
    print(f"[SYNC DB PATH] {os.path.abspath(path)}")
    return path


def _connect():
    conn = sqlite3.connect(_db_path(), timeout=20.0)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    install_sqlite_audit_functions(conn)

    # Safety net terawal: SEMUA jalur sync memakai _connect(), sehingga
    # schema Buku Gudang harus dipastikan siap sebelum caller menjalankan
    # query apa pun yang menyebut sync_id/deleted_at. Fungsi ini didefinisikan
    # di bawah tetapi sudah tersedia ketika module selesai di-import.
    try:
        _ensure_buku_gudang_local_schema(conn)
    except Exception:
        conn.close()
        raise
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
    set_sqlite_audit_sync(conn, enabled)


def _session_ready() -> bool:
    """True hanya bila sesi Supabase benar-benar aktif."""
    if not str(CURRENT_SESSION.get("auth_email") or "").strip():
        return False
    try:
        return supabase.auth.get_session() is not None
    except Exception:
        return False


def _ensure_online_session() -> bool:
    """Pulihkan sesi Supabase secara silent setelah aplikasi masuk mode offline.

    Offline-first tetap dipertahankan: user tidak dikeluarkan dari aplikasi dan
    data lokal tetap dapat dipakai. Saat koneksi tersedia lagi, kredensial
    last-session yang sudah terenkripsi dibaca dari session_store lalu dipakai
    untuk autentikasi ulang ke Supabase. Password tidak ditulis ulang ke file
    database atau log.
    """
    if bool(CURRENT_SESSION.get("is_developer")):
        return False

    if _session_ready():
        return True

    try:
        from session_store import load_last_login
        from config import verifikasi_login_sistem

        saved = load_last_login()
        if not isinstance(saved, dict):
            return False

        identifier = str(saved.get("identifier") or "").strip()
        password = str(saved.get("password") or "")
        if not identifier or not password:
            return False

        hasil = verifikasi_login_sistem(identifier, password)
        if not isinstance(hasil, (tuple, list)) or len(hasil) < 1 or not bool(hasil[0]):
            return False

        # verifikasi_login_sistem bertanggung jawab mengisi CURRENT_SESSION dan
        # membuat auth session Supabase. Pastikan flag offline lama tidak
        # menghambat sync setelah sesi berhasil pulih.
        CURRENT_SESSION["is_offline_session"] = False

        if not str(CURRENT_SESSION.get("auth_email") or "").strip():
            CURRENT_SESSION["auth_email"] = identifier

        ready = _session_ready()
        if ready:
            print(
                "[SESSION] Koneksi Supabase pulih — sesi online berhasil dipulihkan.",
                flush=True,
            )
        return ready
    except Exception as exc:
        # Gangguan jaringan saat reconnect bukan error fatal. Worker berikutnya
        # akan mencoba lagi tanpa logout dan tanpa menghapus last-session.
        logger.debug("[SESSION] Reconnect Supabase tertunda: %s", exc)
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


def _json_payload(table_name: str, value: Any) -> Dict[str, Any]:
    """Normalisasi payload secara eksplisit berdasarkan tabel tujuan.

    Payload SQLite boleh mempunyai metadata lokal, tetapi hanya kolom yang
    terdaftar untuk tabel Supabase yang boleh dikirim. Ini mencegah kolom lokal
    seperti ``aktif`` bocor ke ``data_resi`` hanya karena tabel master lain
    terdaftar di ``TABLES``.
    """
    table = str(table_name or "").strip()
    if table not in SYNC_COLUMNS:
        raise ValueError(f"Tabel sync tidak didukung: {table!r}")
    if not isinstance(value, dict):
        raise ValueError("Payload sync tidak berbentuk object JSON.")

    allowed = SYNC_COLUMNS[table]
    unknown = sorted(set(value) - allowed)
    if unknown:
        # Sengaja debug-level: kolom lokal memang boleh ada di payload outbox,
        # tetapi tidak boleh dikirim ke server. Tidak perlu membanjiri console.
        logger.debug(
            "[SYNC] %s: kolom lokal diabaikan saat push: %s",
            table,
            ", ".join(unknown),
        )

    payload = {key: value[key] for key in allowed if key in value}

    required = SYNC_REQUIRED.get(table, set())
    missing = sorted(key for key in required if not str(payload.get(key) or "").strip())
    if missing:
        raise ValueError(
            f"Payload {table} tidak lengkap; field wajib kosong: {', '.join(missing)}"
        )

    if table == "data_resi":
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

    elif table == "data_resi_detail":
        if "urutan" in payload:
            payload["urutan"] = _to_int(payload.get("urutan"), 1)
        for key in ("berat", "cbm"):
            if key in payload:
                payload[key] = _to_float(payload.get(key), 0.0)

    elif table == "cabang_wilayah":
        payload["aktif"] = 1 if payload.get("aktif", True) else 0

    elif table == "numbering_settings":
        for key in ("starting_count", "current_count", "padding"):
            if key in payload:
                payload[key] = _to_int(payload.get(key), 0)
        payload["aktif"] = 1 if payload.get("aktif", True) else 0

    elif table == "numbering_counters":
        for key in ("starting_count", "current_count", "padding"):
            if key in payload:
                payload[key] = _to_int(payload.get(key), 0)
        payload["aktif"] = 1 if payload.get("aktif", True) else 0

    if isinstance(payload.get("rincian_json"), str):
        raw = payload.get("rincian_json") or "[]"
        try:
            payload["rincian_json"] = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload["rincian_json"] = []

    return payload


def _server_resi_row(sync_id: str) -> Optional[Dict[str, Any]]:
    if not sync_id:
        return None
    response = (
        supabase
        .table("data_resi")
        .select("*")
        .eq("sync_id", sync_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def _resi_push_conflict(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Deteksi edit Resi server yang lebih baru sebelum push lokal."""
    sync_id = str(payload.get("sync_id") or "").strip()
    if not sync_id:
        return None
    remote = _server_resi_row(sync_id)
    if not remote:
        return None

    local_revision = _to_int(payload.get("revision"), 0)
    remote_revision = _to_int(remote.get("revision"), 0)
    local_dt = _parse_dt(payload.get("updated_at"))
    remote_dt = _parse_dt(remote.get("updated_at"))

    # Retry idempotent setelah response/network timeout.
    if remote_revision == local_revision and local_dt is not None and remote_dt is not None and remote_dt == local_dt:
        return None

    if remote_revision > local_revision:
        return remote
    # Timestamp server yang lebih baru tetap dianggap konflik walaupun revision
    # belum berubah, misalnya bila row diubah langsung dari Supabase Table Editor.
    if local_dt is not None and remote_dt is not None and remote_dt > local_dt:
        return remote
    if remote_revision == local_revision:
        # Revision sama tetapi timestamp berbeda berarti dua perangkat menulis
        # versi yang sama; tahan perubahan lokal daripada menimpa server.
        if local_dt is None or remote_dt is None or remote_dt != local_dt:
            return remote
    return None


def _update_resi_with_cas(clean: Dict[str, Any]) -> None:
    """Push Resi dengan compare-and-swap berbasis revision server."""
    sync_id = str(clean.get("sync_id") or "").strip()
    if not sync_id:
        raise ValueError("data_resi tidak memiliki sync_id.")

    remote = _server_resi_row(sync_id)
    if remote is None:
        # Jangan pernah mengandalkan auth user yang sedang login untuk actor
        # sebuah insert offline. Payload harus sudah membawa snapshot pembuat asli.
        if not clean.get("created_by_user_id") and not clean.get("created_by_username"):
            raise ValueError("Resi offline tidak memiliki identitas pembuat pada payload sync.")
        response = supabase.table("data_resi").insert(clean).select("sync_id").execute()
        if getattr(response, "data", None) is None:
            raise RuntimeError("Insert Resi ke Supabase tidak mengembalikan data.")
        return

    # created_by adalah immutable. Pada update, selalu pertahankan nilai yang
    # sudah ada di server agar user yang sedang melakukan sync tidak mengambil
    # alih histori pembuat.
    for field in ("created_by_user_id", "created_by_username", "created_by_name"):
        if remote.get(field) not in (None, ""):
            clean[field] = remote.get(field)

    local_revision = _to_int(clean.get("revision"), 0)
    remote_revision = _to_int(remote.get("revision"), 0)
    if remote_revision == local_revision:
        local_dt = _parse_dt(clean.get("updated_at"))
        remote_dt = _parse_dt(remote.get("updated_at"))
        if local_dt is not None and remote_dt is not None and local_dt == remote_dt:
            return
        raise SyncConflictError(
            "Perubahan Resi lokal berbenturan dengan perubahan server pada revision yang sama."
        )
    if remote_revision > local_revision:
        raise SyncConflictError(
            "Perubahan Resi lokal kalah dari revision server yang lebih baru."
        )

    # PENTING: updated_at lokal (SQLite CURRENT_TIMESTAMP) berbentuk string naif
    # tanpa zona waktu. _parse_dt membacanya sebagai UTC, tetapi filter PostgREST
    # akan ditafsirkan Postgres memakai timezone sesi database (mis. Asia/Jakarta),
    # sehingga filter .lte("updated_at") bisa meleset berjam-jam dan update
    # tidak mengenai baris apa pun. Karena itu kirim waktu eksplisit UTC.
    local_dt = _parse_dt(clean.get("updated_at"))
    local_updated_at = (
        local_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if local_dt is not None else None
    )
    if local_updated_at:
        clean["updated_at"] = local_updated_at

    query = (
        supabase
        .table("data_resi")
        .update(clean)
        .eq("sync_id", sync_id)
        .lt("revision", local_revision)
    )
    if local_updated_at:
        # Proteksi race kedua: bila revision server tidak berubah tetapi timestamp
        # server sempat maju, update ini tidak boleh menimpa perubahan tersebut.
        query = query.lte("updated_at", local_updated_at)
    response = query.select("sync_id").execute()
    if getattr(response, "data", None):
        return

    # Update tidak mengenai baris. Cek ulang server: apakah benar ada perangkat
    # lain yang menang, atau filter di atas saja yang meleset?
    latest = _server_resi_row(sync_id)
    if latest is None:
        raise SyncConflictError("Resi hilang dari server saat push berlangsung.")
    latest_revision = _to_int(latest.get("revision"), 0)
    latest_dt = _parse_dt(latest.get("updated_at"))
    if latest_revision >= local_revision or (
        local_dt is not None and latest_dt is not None and latest_dt > local_dt
    ):
        # Perangkat lain memang menang di antara SELECT dan UPDATE.
        raise SyncConflictError(
            "Perubahan Resi ditolak server karena perangkat lain lebih dulu menyimpan perubahan."
        )

    # Server tidak berubah (revision lebih kecil, timestamp tidak lebih baru),
    # jadi penolakan tadi bukan konflik nyata. Ulangi dengan compare-and-swap
    # murni pada revision yang baru saja kita lihat.
    retry = (
        supabase
        .table("data_resi")
        .update(clean)
        .eq("sync_id", sync_id)
        .eq("revision", latest_revision)
        .select("sync_id")
        .execute()
    )
    if getattr(retry, "data", None):
        return
    raise SyncConflictError(
        "Update Resi tidak mengenai baris di server; kemungkinan diblokir RLS atau diubah perangkat lain."
    )


def _server_buku_gudang_row(id_gudang: str) -> Optional[Dict[str, Any]]:
    """Ambil satu Buku Gudang dari server untuk idempotent push."""
    gid = str(id_gudang or "").strip().upper()
    if not gid:
        return None
    rows = (
        supabase
        .table("buku_gudang")
        .select("id_gudang,kode_cabang,tanggal,no_resi,jenis,status_resi,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name")
        .eq("id_gudang", gid)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _same_buku_gudang_business_state(local: Dict[str, Any], remote: Dict[str, Any]) -> bool:
    """Bandingkan field bisnis Buku Gudang, abaikan timestamp/aktor housekeeping."""
    fields = (
        "id_gudang", "kode_cabang", "tanggal", "no_resi", "jenis", "status_resi",
        "sync_id", "deleted_at",
    )
    for field in fields:
        lv = local.get(field)
        rv = remote.get(field)
        if field in {"id_gudang", "kode_cabang", "no_resi", "jenis", "status_resi", "sync_id"}:
            lv = str(lv or "").strip().upper()
            rv = str(rv or "").strip().upper()
        elif field == "deleted_at":
            lv = None if lv in (None, "") else str(lv)
            rv = None if rv in (None, "") else str(rv)
        if lv != rv:
            return False
    return True


def _same_manifest_business_state(local: Dict[str, Any], remote: Dict[str, Any]) -> bool:
    """Bandingkan field bisnis header Manifest, abaikan timestamp dan aktor."""
    fields = (
        "id_manifest", "kode_cabang", "tanggal", "no_polisi", "nama_sopir",
        "nama_kapal", "note_manifest", "status_manifest", "deleted_at",
    )
    uppercase_fields = {
        "id_manifest", "kode_cabang", "no_polisi", "nama_sopir",
        "nama_kapal", "status_manifest",
    }
    for field in fields:
        lv, rv = local.get(field), remote.get(field)
        if field in uppercase_fields:
            lv, rv = str(lv or "").strip().upper(), str(rv or "").strip().upper()
        elif field == "note_manifest":
            lv, rv = str(lv or "").strip(), str(rv or "").strip()
        else:
            lv = None if lv in (None, "") else str(lv).strip()
            rv = None if rv in (None, "") else str(rv).strip()
        if lv != rv:
            return False
    return True


def _server_upsert(table_name: str, operation: str, payload: Dict[str, Any]) -> None:
    clean = _json_payload(table_name, payload)

    # Server memakai soft-delete: row tetap ada, tetapi deleted_at diisi.
    if operation == "DELETE":
        clean["deleted_at"] = _utc_now()

    # Supabase menjaga kolom identitas internal. Untuk detail barang, `sync_id`
    # adalah conflict target agar id_detail boleh berbeda antar perangkat.
    if table_name == "data_resi":
        _update_resi_with_cas(clean)
        return
    elif table_name == "data_resi_detail":
        if not clean.get("sync_id"):
            raise ValueError("data_resi_detail tidak memiliki sync_id.")
        remote_detail = (
            supabase
            .table("data_resi_detail")
            .select("created_by_user_id,created_by_username,created_by_name")
            .eq("sync_id", clean.get("sync_id"))
            .limit(1)
            .execute()
        ).data or []
        if remote_detail:
            for field in ("created_by_user_id", "created_by_username", "created_by_name"):
                if remote_detail[0].get(field) not in (None, ""):
                    clean[field] = remote_detail[0].get(field)
        if operation == "INSERT" and not (clean.get("created_by_user_id") or clean.get("created_by_username")):
            raise ValueError("Detail Resi offline tidak memiliki identitas pembuat pada payload sync.")
        # id_detail adalah identity server dan tidak boleh dipaksakan dari
        # perangkat lain; sync_id menjadi identitas lintas perangkat.
        clean.pop("id_detail", None)
        response = (
            supabase
            .table("data_resi_detail")
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
    elif table_name == "numbering_counters":
        clean.pop("id", None)
        # Counter punya dua identitas: sync_id untuk sinkronisasi, dan
        # (kode_cabang, document_type, series_code) sebagai business key UNIQUE.
        # Local DB bisa saja membawa sync_id lama/berbeda akibat seed awal.
        # Karena itu JANGAN menjadikan sync_id satu-satunya conflict target.
        branch = str(clean.get("kode_cabang") or "").strip().upper()
        document_type = str(clean.get("document_type") or "").strip().upper()
        series_code = str(clean.get("series_code") or "").strip().upper()
        if not branch or not document_type or not series_code:
            raise ValueError(
                "numbering_counters membutuhkan kode_cabang, document_type, dan series_code."
            )

        remote_rows = (
            supabase
            .table("numbering_counters")
            .select("sync_id,starting_count,current_count,padding,aktif,deleted_at,updated_at")
            .eq("kode_cabang", branch)
            .eq("document_type", document_type)
            .eq("series_code", series_code)
            .limit(1)
            .execute()
        ).data or []

        if remote_rows:
            remote = remote_rows[0]
            # Server adalah identity resmi untuk counter ini. Pertahankan
            # sync_id server agar update berikutnya tidak membuat duplicate key
            # pada UNIQUE(kode_cabang, document_type, series_code).
            remote_sid = str(remote.get("sync_id") or "").strip()
            if remote_sid:
                clean["sync_id"] = remote_sid

            # Counter monotonic: nomor yang pernah dicapai tidak boleh mundur.
            clean["starting_count"] = max(
                _to_int(clean.get("starting_count"), 0),
                _to_int(remote.get("starting_count"), 0),
            )
            clean["current_count"] = max(
                _to_int(clean.get("current_count"), 0),
                _to_int(remote.get("current_count"), 0),
            )

            # Update berdasarkan sync_id resmi server. Ini menghindari UPSERT
            # yang mencoba INSERT karena sync_id lokal berbeda, tetapi business
            # key sudah ada di server.
            if remote_sid:
                response = (
                    supabase
                    .table("numbering_counters")
                    .update(clean)
                    .eq("sync_id", remote_sid)
                    .execute()
                )
            else:
                response = (
                    supabase
                    .table("numbering_counters")
                    .upsert(
                        clean,
                        on_conflict="kode_cabang,document_type,series_code",
                    )
                    .execute()
                )
        else:
            # Counter benar-benar baru di server. Insert dengan sync_id lokal.
            response = (
                supabase
                .table("numbering_counters")
                .insert(clean)
                .execute()
            )
    elif table_name == "master_penerima":
        clean.pop("is_synced", None)
        response = (
            supabase
            .table("master_penerima")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    elif table_name == "master_pengirim":
        clean.pop("is_synced", None)
        response = (
            supabase
            .table("master_pengirim")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    elif table_name == "truk":
        clean.pop("is_synced", None)
        response = (
            supabase
            .table("truk")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    elif table_name == "kapal":
        clean.pop("is_synced", None)
        response = (
            supabase
            .table("kapal")
            .upsert(clean, on_conflict="sync_id")
            .execute()
        )
    elif table_name == "buku_gudang":
        clean.pop("is_synced", None)
        # Jangan gunakan UPSERT untuk Buku Gudang: retry INSERT yang sebenarnya
        # sudah diterima server dapat berubah menjadi UPDATE dan mentok RLS.
        gid = str(clean.get("id_gudang") or "").strip().upper()
        sid = str(clean.get("sync_id") or "").strip()
        if not gid or not sid:
            raise ValueError("buku_gudang membutuhkan id_gudang dan sync_id.")

        remote = _server_buku_gudang_row(gid)

        if operation == "INSERT":
            if remote:
                remote_sid = str(remote.get("sync_id") or "").strip()
                if remote_sid == sid:
                    # INSERT sebelumnya sudah sukses; retry sekarang hanya perlu
                    # dianggap selesai, tanpa menyentuh UPDATE/RLS.
                    return
                raise SyncConflictError(
                    "Buku Gudang dengan id_gudang sama sudah dimiliki sync_id lain di server."
                )
            response = supabase.table("buku_gudang").insert(clean).execute()
        elif operation == "UPDATE":
            if remote is None:
                # Update lokal terjadi sebelum row pertama kali berhasil dikirim.
                # Kirim state terkini sebagai INSERT, bukan UPDATE.
                response = supabase.table("buku_gudang").insert(clean).execute()
            else:
                remote_sid = str(remote.get("sync_id") or "").strip()
                if remote_sid and remote_sid != sid:
                    raise SyncConflictError(
                        "Buku Gudang yang sama memiliki sync_id berbeda di server."
                    )
                if _same_buku_gudang_business_state(clean, remote):
                    # Perubahan lokal hanya mengulang state yang sudah ada di server.
                    # Ini terutama menangani retry/housekeeping tanpa membutuhkan
                    # izin UPDATE dari RLS.
                    return
                response = supabase.table("buku_gudang").update(clean).eq("id_gudang", gid).execute()
        else:
            # DELETE/soft-delete memang merupakan UPDATE server. Biarkan RLS
            # memutuskan apakah user berwenang melakukan penghapusan.
            response = supabase.table("buku_gudang").update(clean).eq("id_gudang", gid).execute()
    elif table_name == "manifest":
        clean.pop("is_synced", None)
        manifest_id = str(clean.get("id_manifest") or "").strip().upper()
        branch = str(clean.get("kode_cabang") or "").strip().upper()
        local_sid = str(clean.get("sync_id") or "").strip()
        if not manifest_id or not branch or not local_sid:
            raise ValueError("manifest membutuhkan id_manifest, kode_cabang, dan sync_id.")

        # Header Manifest memiliki business key id_manifest. Cocokkan dengan
        # key tersebut juga agar row legacy tidak diduplikasi hanya karena UUID
        # sinkronisasi lokal dibuat pada migrasi v17.
        by_sync = (supabase.table("manifest").select("*")
                  .eq("sync_id", local_sid).limit(1).execute()).data or []
        remote = by_sync[0] if by_sync else None
        if remote is None:
            by_id = (supabase.table("manifest").select("*")
                     .eq("id_manifest", manifest_id).limit(1).execute()).data or []
            remote = by_id[0] if by_id else None

        if remote is None:
            if operation == "DELETE":
                return  # Retry-safe: the row was already absent on the server.
            response = supabase.table("manifest").insert(clean).select("sync_id").execute()
        else:
            remote_id = str(remote.get("id_manifest") or "").strip().upper()
            remote_branch = str(remote.get("kode_cabang") or "").strip().upper()
            remote_sid = str(remote.get("sync_id") or "").strip()
            if remote_id != manifest_id:
                raise SyncConflictError("sync_id Manifest sudah digunakan oleh id_manifest berbeda.")
            if remote_branch != branch:
                raise SyncConflictError(
                    f"Manifest {manifest_id} terdaftar pada cabang {remote_branch}, bukan {branch}."
                )

            # Retry INSERT/UPDATE yang sama harus idempotent meski timestamp
            # server sedikit lebih baru akibat trigger updated_at.
            if operation != "DELETE" and _same_manifest_business_state(clean, remote):
                return

            local_dt = _parse_dt(clean.get("updated_at"))
            remote_dt = _parse_dt(remote.get("updated_at"))
            if remote_dt is not None and local_dt is not None and remote_dt > local_dt:
                raise SyncConflictError(
                    f"Manifest {manifest_id} sudah berubah lebih baru di server."
                )
            if operation == "DELETE":
                clean["deleted_at"] = clean.get("deleted_at") or _utc_now()
                clean["updated_at"] = _utc_now()

            # Pertahankan identitas pembuat yang sudah disimpan server. Metadata
            # legacy kosong juga diisi dari row resmi sebelum update.
            for field in ("created_by_user_id", "created_by_username", "created_by_name"):
                if remote.get(field) not in (None, ""):
                    clean[field] = remote.get(field)
            if clean.get("created_at") in (None, "") and remote.get("created_at") not in (None, ""):
                clean["created_at"] = remote.get("created_at")

            # UUID server adalah identitas kanonis jika row sudah lebih dahulu
            # ada di Supabase; generic snapshot kemudian menyelaraskan SQLite.
            if remote_sid:
                clean["sync_id"] = remote_sid
            query = supabase.table("manifest").update(clean)
            query = query.eq("sync_id", remote_sid) if remote_sid else query.eq("id_manifest", manifest_id)
            response = query.select("sync_id").execute()
        if not getattr(response, "data", None):
            raise RuntimeError(
                f"Push Manifest {manifest_id} tidak dikonfirmasi oleh server; periksa RLS dan row target."
            )
    else:
        raise ValueError(f"Tabel sync belum didukung: {table_name}")

    if getattr(response, "data", None) is None:
        # Client biasanya melempar exception bila HTTP/API gagal.
        # Tetap anggap response tanpa data sebagai sukses karena beberapa
        # konfigurasi return representation dapat kosong.
        return


def _server_detail_position_conflict(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Cari detail remote yang sudah memakai pasangan (no_resi, urutan).

    UNIQUE(no_resi, urutan) berarti dua perangkat tidak boleh membuat detail
    berbeda pada slot urutan yang sama. Konflik ini harus ditahan sebagai
    CONFLICT, bukan diulang terus sampai log penuh.
    """
    if not payload.get("no_resi") or payload.get("urutan") is None:
        return None
    try:
        rows = (
            supabase
            .table("data_resi_detail")
            .select("*")
            .eq("no_resi", str(payload.get("no_resi") or "").strip().upper())
            .eq("urutan", int(payload.get("urutan")))
            .limit(2)
            .execute()
        ).data or []
    except Exception:
        # Kegagalan network ditangani oleh push_pending/_is_offline_network_error.
        raise

    local_sync_id = str(payload.get("sync_id") or "").strip()
    for remote in rows:
        remote_sync_id = str(remote.get("sync_id") or "").strip()
        if remote_sync_id and remote_sync_id != local_sync_id:
            return remote
    return None


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
    elif table_name == "buku_gudang":
        conn.execute(
            "UPDATE buku_gudang SET is_synced = 1 WHERE sync_id = ? OR id_gudang = ?",
            (record_key, record_key),
        )
    elif table_name in {"master_penerima", "master_pengirim", "truk", "kapal", "manifest"}:
        # Migration v16 memasang trigger outbox master sebagai AFTER UPDATE ON
        # tanpa filter kolom. Karena itu UPDATE housekeeping is_synced=1 akan
        # membuat antrean UPDATE baru, push lagi, lalu mengulang tanpa henti.
        # Suppress outbox hanya selama penandaan housekeeping ini, lalu pulihkan
        # kondisi sebelumnya agar perubahan data pengguna tetap masuk outbox.
        table_trigger_always_fires = table_name in {
            "master_penerima", "master_pengirim", "truk", "kapal"
        }
        suppress_row = conn.execute(
            "SELECT suppress_outbox FROM sync_control WHERE id = 1 LIMIT 1"
        ).fetchone()
        was_suppressed = bool(suppress_row[0]) if suppress_row else False
        if table_trigger_always_fires and not was_suppressed:
            _set_suppress(conn, True)
        try:
            conn.execute(
                f"UPDATE {table_name} SET is_synced = 1 WHERE sync_id = ?",
                (record_key,),
            )
        finally:
            if table_trigger_always_fires and not was_suppressed:
                _set_suppress(conn, False)


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


def _is_offline_network_error(error: BaseException) -> bool:
    """Kenali error jaringan/DNS yang berarti Supabase sedang tidak terjangkau.

    Error semacam ini bukan bug aplikasi dan antrean sync harus tetap PENDING.
    Kita sengaja tidak bergantung pada class exception httpx agar tetap robust
    terhadap perubahan versi dependency.
    """
    seen: set[int] = set()
    current: Optional[BaseException] = error
    network_markers = (
        "connecterror",
        "connecttimeout",
        "readtimeout",
        "writetimeout",
        "pooltimeout",
        "getaddrinfo failed",
        "name or service not known",
        "temporary failure in name resolution",
        "network is unreachable",
        "connection reset",
        "connection refused",
        "connection aborted",
        "winerror 10054",
        "winerror 10060",
        "errno 11001",
        "errno 10054",
        "errno 10060",
        "timed out",
    )

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = type(current).__name__.lower()
        text = str(current).lower()
        if any(marker in name or marker in text for marker in network_markers):
            return True
        current = current.__cause__ or current.__context__
    return False


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
    """Detect a genuine remote-newer master conflict without flagging our own INSERT.

    Supabase may stamp/update ``updated_at`` a little later when the INSERT reaches
    the server. For a brand-new row, ``created_at`` remains the same identity
    timestamp that came from the local payload. Therefore a later server
    ``updated_at`` on a row with the same ``created_at`` is not a remote edit; it
    is normally the server acknowledgement/normalization of our own write.
    """
    if table_name not in MASTER_TABLES:
        return None
    sync_id = str(payload.get("sync_id") or "").strip()
    if not sync_id:
        return None

    remote = _server_master_row(table_name, sync_id)
    if not remote:
        return None

    local_created = _parse_dt(payload.get("created_at"))
    remote_created = _parse_dt(remote.get("created_at"))
    local_updated = _parse_dt(payload.get("updated_at"))
    remote_updated = _parse_dt(remote.get("updated_at"))

    # A freshly inserted master can get a slightly newer server-side updated_at
    # while still being the exact same record we just pushed. Do not manufacture
    # a conflict in that case.
    if (
        local_created is not None
        and remote_created is not None
        and local_created == remote_created
    ):
        return None

    if local_updated is None or remote_updated is None:
        return None

    if remote_updated > local_updated:
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


def _heal_false_master_conflicts(conn) -> int:
    """Reopen legacy master conflicts that were caused by server-side timestamp drift.

    A master row inserted locally carries its original created_at into Supabase.
    Older sync attempts could nevertheless mark a follow-up local UPDATE as a
    conflict because Supabase had a slightly newer updated_at. Once we know both
    payloads share the same created_at and sync_id, that is not a real competing
    edit; reopen the local outbox entry so it can be pushed normally.
    """
    rows = conn.execute(
        """
        SELECT id, table_name, record_key, local_payload, remote_payload
        FROM sync_conflicts
        WHERE status = 'OPEN'
          AND table_name IN ('master_penerima','master_pengirim','truk','kapal')
        ORDER BY id ASC
        """
    ).fetchall()
    healed = 0
    for conflict_id, table_name, record_key, local_raw, remote_raw in rows:
        try:
            local = json.loads(local_raw or '{}')
            remote = json.loads(remote_raw or '{}')
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

        local_sid = str(local.get('sync_id') or '').strip()
        remote_sid = str(remote.get('sync_id') or '').strip()
        local_created = _parse_dt(local.get('created_at'))
        remote_created = _parse_dt(remote.get('created_at'))
        if not local_sid or not remote_sid or local_sid != remote_sid:
            continue
        if local_created is None or remote_created is None or local_created != remote_created:
            continue

        # Reopen only the affected local outbox rows; they will be rechecked by
        # _local_master_is_older_than_server(), which now ignores this timestamp
        # drift case but still detects a genuine later remote edit.
        conn.execute(
            """
            UPDATE sync_outbox
            SET status = 'PENDING',
                last_error = NULL
            WHERE table_name = ?
              AND record_key = ?
              AND status = 'CONFLICT'
            """,
            (table_name, record_key),
        )
        conn.execute(
            "UPDATE sync_conflicts SET status = 'RESOLVED' WHERE id = ?",
            (conflict_id,),
        )
        healed += 1

    return healed


def _hydrate_immutable_created_by(conn, table_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Pastikan actor pembuat di outbox berasal dari row lokal, bukan session saat sync.

    Ini juga memperbaiki antrean lama yang dibuat sebelum snapshot audit dimasukkan
    ke payload outbox. ``created_by_*`` bersifat immutable; user login saat push
    tidak boleh menggantikan identitas pembuat asli.
    """
    result = dict(payload)
    if table_name == "data_resi":
        key = str(result.get("no_resi") or "").strip().upper()
        if not key:
            return result
        row = conn.execute(
            "SELECT created_by_user_id, created_by_username, created_by_name FROM data_resi WHERE UPPER(no_resi)=? LIMIT 1",
            (key,),
        ).fetchone()
    elif table_name == "data_resi_detail":
        key = str(result.get("sync_id") or "").strip()
        if not key:
            return result
        row = conn.execute(
            "SELECT created_by_user_id, created_by_username, created_by_name FROM data_resi_detail WHERE sync_id=? LIMIT 1",
            (key,),
        ).fetchone()
    elif table_name in {"master_penerima", "master_pengirim", "truk", "kapal", "manifest"}:
        key = str(result.get("sync_id") or "").strip()
        if not key:
            return result
        row = conn.execute(
            f"SELECT created_by_user_id, created_by_username, created_by_name FROM {table_name} WHERE sync_id=? LIMIT 1",
            (key,),
        ).fetchone()
    else:
        return result

    if not row:
        return result
    for field, value in zip(("created_by_user_id", "created_by_username", "created_by_name"), row):
        if value not in (None, ""):
            # created_by adalah histori immutable; row lokal menjadi sumber kebenaran.
            result[field] = value
    return result

def push_pending(limit: int = BATCH_SIZE) -> int:
    if not _session_ready():
        return 0

    conn = _connect()
    berhasil = 0
    try:
        healed = _heal_false_master_conflicts(conn)
        if healed:
            conn.commit()
            logger.info("[SYNC] Memulihkan %s konflik master lama yang ternyata hanya timestamp server.", healed)

        rows = conn.execute(
            """
            SELECT id, table_name, record_key, operation, payload_json
            FROM sync_outbox
            WHERE status = 'PENDING'
              AND table_name IN (
                  'cabang_wilayah',
                  'numbering_settings', 'numbering_counters',
                  'master_penerima', 'master_pengirim', 'truk', 'kapal',
                  'buku_gudang', 'manifest',
                  'data_resi', 'data_resi_detail'
              )
            ORDER BY
                CASE table_name
                    WHEN 'cabang_wilayah' THEN 1
                    WHEN 'numbering_settings' THEN 2
                    WHEN 'numbering_counters' THEN 3
                    WHEN 'master_penerima' THEN 5
                    WHEN 'master_pengirim' THEN 6
                    WHEN 'truk' THEN 7
                    WHEN 'kapal' THEN 8
                    WHEN 'manifest' THEN 9
                    -- Resi/detail must reach the server before Buku Gudang
                    -- because Buku Gudang references the Resi.
                    WHEN 'data_resi' THEN 10
                    WHEN 'data_resi_detail' THEN 11
                    WHEN 'buku_gudang' THEN 12
                    ELSE 12
                END, id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

        for outbox_id, table_name, record_key, operation, payload_json in rows:
            try:
                payload = json.loads(payload_json)
                payload = _hydrate_immutable_created_by(conn, table_name, payload)

                # Detail memiliki UNIQUE(no_resi, urutan). Bila slot tersebut
                # sudah dipakai oleh sync_id lain di server, jangan retry terus.
                if table_name == "data_resi_detail" and operation != "DELETE":
                    remote_detail = _server_detail_position_conflict(payload)
                    if remote_detail:
                        _mark_conflict(
                            conn, outbox_id, table_name, record_key, payload, remote_detail
                        )
                        conn.commit()
                        logger.warning(
                            "[SYNC] Konflik detail %s/%s urutan %s: slot sudah dipakai server.",
                            payload.get("no_resi"), record_key, payload.get("urutan"),
                        )
                        continue

                # Resi wajib melalui pemeriksaan revision/timestamp sebelum push.
                if table_name == "data_resi":
                    remote_newer = _resi_push_conflict(payload)
                    if remote_newer:
                        _mark_conflict(
                            conn, outbox_id, table_name, record_key, payload, remote_newer
                        )
                        conn.commit()
                        logger.warning(
                            "[SYNC] Konflik Resi %s: server lebih baru, perubahan lokal ditahan.",
                            record_key,
                        )
                        continue
                elif table_name in MASTER_TABLES and table_name != 'numbering_counters' and operation in {'UPDATE', 'DELETE'}:
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
            except SyncConflictError as exc:
                conn.rollback()
                remote = _server_resi_row(str(payload.get("sync_id") or "").strip()) or {}
                _mark_conflict(conn, outbox_id, table_name, record_key, payload, remote)
                conn.commit()
                logger.warning(
                    "[SYNC] Push konflik #%s %s/%s: %s",
                    outbox_id, table_name, record_key, exc,
                )
                continue
            except Exception as exc:
                conn.rollback()

                # Proteksi race: slot detail bisa diambil perangkat lain setelah
                # preflight tetapi sebelum upsert. 23505 tidak boleh di-retry terus.
                is_detail_unique_conflict = (
                    table_name == "data_resi_detail"
                    and "23505" in str(exc)
                    and "data_resi_detail_no_resi_urutan_key" in str(exc)
                )
                if is_detail_unique_conflict:
                    try:
                        remote_detail = _server_detail_position_conflict(payload) or {}
                    except Exception:
                        remote_detail = {}
                    _mark_conflict(
                        conn, outbox_id, table_name, record_key, payload, remote_detail
                    )
                    conn.commit()
                    logger.warning(
                        "[SYNC] Konflik detail #%s %s/%s: pasangan no_resi+urutan sudah dipakai server.",
                        outbox_id, table_name, record_key,
                    )
                    continue

                _mark_error(conn, outbox_id, exc)
                conn.commit()
                if _is_offline_network_error(exc):
                    # Jangan menghapus antrean. Perubahan lokal tetap PENDING dan
                    # akan dicoba lagi saat koneksi kembali. Logging dipindahkan
                    # ke level worker agar offline tidak memenuhi log per item.
                    raise SyncOfflineError(str(exc)) from exc
                logger.warning(
                    "[SYNC] Push gagal #%s %s %s/%s: %s",
                    outbox_id, operation, table_name, record_key, exc,
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


def _has_unresolved_conflict(conn, table_name: str, record_key: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM sync_conflicts
        WHERE table_name = ? AND record_key = ? AND status = 'OPEN'
        LIMIT 1
        """,
        (table_name, record_key),
    ).fetchone()
    if row is not None:
        return True
    row = conn.execute(
        """
        SELECT 1 FROM sync_outbox
        WHERE table_name = ? AND record_key = ? AND status = 'CONFLICT'
        LIMIT 1
        """,
        (table_name, record_key),
    ).fetchone()
    return row is not None


def _store_pull_conflict(conn, event_id: str, table_name: str, record_key: str, payload: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO sync_conflicts(
            event_key, table_name, record_key, local_payload, remote_payload
        ) VALUES (?, ?, ?,
            (SELECT payload_json FROM sync_outbox
             WHERE table_name=? AND record_key=? AND status IN ('PENDING','CONFLICT')
             ORDER BY id DESC LIMIT 1),
            ?
        )
        """,
        (
            event_id or f"PULL-CONFLICT:{table_name}:{record_key}",
            table_name, record_key, table_name, record_key,
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def _record_key_from_remote(table_name: str, payload: Dict[str, Any]) -> str:
    if table_name == "data_resi":
        return str(payload.get("no_resi") or "").strip().upper()
    return str(payload.get("sync_id") or "").strip()


def _manifest_local_key_by_id(conn, payload: Dict[str, Any]) -> str:
    """Lookup local canonical sync key for a Manifest by its business ID.

    Older local Manifest headers may receive a UUID during v17 migration while
    an existing server row already has a different canonical sync_id. Pending
    protection must therefore check both remote sync_id and local id_manifest.
    """
    manifest_id = str(payload.get("id_manifest") or "").strip().upper()
    if not manifest_id:
        return ""
    row = conn.execute(
        "SELECT sync_id FROM manifest WHERE UPPER(id_manifest)=? LIMIT 1",
        (manifest_id,),
    ).fetchone()
    return str(row[0] or "").strip() if row else ""


def _delete_local_resi(conn, no_resi: str) -> None:
    """Hapus resi beserta tabel child lokal yang memiliki FK ke data_resi.

    data_resi_detail memakai ON DELETE CASCADE, tetapi buku_gudang pada
    database lokal tidak memakai CASCADE. Karena itu child harus dihapus
    eksplisit sebelum parent agar SQLite tidak memblokir DELETE.
    """
    no_resi = str(no_resi or "").strip().upper()
    if not no_resi:
        return

    # Child tanpa CASCADE pada schema lokal.
    conn.execute("DELETE FROM buku_gudang WHERE no_resi = ?", (no_resi,))

    # Tetap eksplisit supaya aman bila schema lama belum memiliki ON DELETE CASCADE.
    conn.execute("DELETE FROM data_resi_detail WHERE no_resi = ?", (no_resi,))

    # Parent terakhir.
    conn.execute("DELETE FROM data_resi WHERE no_resi = ?", (no_resi,))


def _apply_remote_resi(conn, payload: Dict[str, Any]) -> None:
    columns = [
        "no_resi", "kode_cabang", "tanggal_masuk", "tanggal_keluar", "pengirim",
        "hp_pengirim", "alamat_pengirim", "kota_asal", "penerima", "hp_penerima",
        "alamat_penerima", "kota_tujuan", "nama_barang", "koli", "berat", "cbm",
        "ongkir_per_kg", "ongkir_per_cbm", "subtotal_ongkir", "jenis_pajak",
        "total_ongkir", "pembayaran", "status_resi", "foto_bukti", "truk",
        "ket_buku_gudang", "no_manifest", "ket_manifest", "rincian_json", "is_synced",
        "revision", "created_at", "updated_at", "sync_id", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
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
            {', '.join(
                (
                    f"{c}=COALESCE(excluded.{c}, data_resi.{c})"
                    if c in {
                        'created_by_user_id', 'created_by_username', 'created_by_name',
                        'updated_by_user_id', 'updated_by_username', 'updated_by_name',
                    }
                    else f"{c}=excluded.{c}"
                )
                for c in columns if c != 'no_resi'
            )}
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
                created_at=?, updated_at=?, deleted_at=?,
                created_by_user_id=?, created_by_username=?, created_by_name=?,
                updated_by_user_id=?, updated_by_username=?, updated_by_name=?
            WHERE sync_id=?
            """,
            (
                payload.get("no_resi"), payload.get("urutan"), payload.get("nama_barang"),
                payload.get("koli"), payload.get("berat", 0), payload.get("cbm", 0),
                payload.get("created_at"), payload.get("updated_at"), payload.get("deleted_at"),
                payload.get("created_by_user_id"), payload.get("created_by_username"), payload.get("created_by_name"),
                payload.get("updated_by_user_id"), payload.get("updated_by_username"), payload.get("updated_by_name"),
                sync_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO data_resi_detail
            (no_resi, urutan, nama_barang, koli, berat, cbm, created_at, updated_at, sync_id, deleted_at,
             created_by_user_id, created_by_username, created_by_name,
             updated_by_user_id, updated_by_username, updated_by_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("no_resi"), payload.get("urutan"), payload.get("nama_barang"),
                payload.get("koli"), payload.get("berat", 0), payload.get("cbm", 0),
                payload.get("created_at"), payload.get("updated_at"), sync_id, payload.get("deleted_at"),
                payload.get("created_by_user_id"), payload.get("created_by_username"), payload.get("created_by_name"),
                payload.get("updated_by_user_id"), payload.get("updated_by_username"), payload.get("updated_by_name"),
            ),
        )


def _apply_remote_numbering(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    sid = str(payload.get("sync_id") or "").strip()
    branch = str(payload.get("kode_cabang") or "").strip().upper()
    doc = str(payload.get("document_type") or "").strip().upper()
    if not sid or not branch or not doc:
        return False
    if not _ensure_local_branch_dependency(conn, branch):
        logger.warning("[SYNC] numbering_settings/%s ditahan: cabang %s belum tersedia lokal.", sid, branch)
        return False
    local = conn.execute("SELECT updated_at FROM numbering_settings WHERE sync_id=? LIMIT 1", (sid,)).fetchone()
    if not force and local and _parse_dt(local[0]) and _parse_dt(payload.get("updated_at")) and _parse_dt(payload.get("updated_at")) <= _parse_dt(local[0]):
        return False
    conn.execute("""
        INSERT INTO numbering_settings(kode_cabang,document_type,format_template,starting_count,current_count,padding,reset_rule,aktif,sync_id,created_at,updated_at,deleted_at,
                                       created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(kode_cabang,document_type) DO UPDATE SET
          format_template=excluded.format_template, starting_count=excluded.starting_count, current_count=excluded.current_count,
          padding=excluded.padding, reset_rule=excluded.reset_rule, aktif=excluded.aktif, sync_id=excluded.sync_id,
          created_at=excluded.created_at, updated_at=excluded.updated_at, deleted_at=excluded.deleted_at,
          created_by_user_id=excluded.created_by_user_id, created_by_username=excluded.created_by_username, created_by_name=excluded.created_by_name,
          updated_by_user_id=excluded.updated_by_user_id, updated_by_username=excluded.updated_by_username, updated_by_name=excluded.updated_by_name
    """, (branch,doc,str(payload.get("format_template") or "{SEQ}"),_to_int(payload.get("starting_count"),1),_to_int(payload.get("current_count"),0),_to_int(payload.get("padding"),5),str(payload.get("reset_rule") or "NONE"),1 if payload.get("aktif",True) else 0,sid,payload.get("created_at"),payload.get("updated_at"),payload.get("deleted_at"),
           payload.get("created_by_user_id"),payload.get("created_by_username"),payload.get("created_by_name"),payload.get("updated_by_user_id"),payload.get("updated_by_username"),payload.get("updated_by_name")))
    return True


def _apply_remote_numbering_counter(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    """Terapkan counter server tanpa pernah menurunkan sequence lokal.

    Counter diidentifikasi oleh business key (kode_cabang, document_type,
    series_code), bukan sync_id saja. Ini penting karena DB lokal baru/seed lama
    dapat memiliki UUID berbeda dari counter resmi di Supabase.

    Untuk counter berlaku aturan khusus: current_count dan starting_count
    monotonic. Timestamp bukan alasan untuk menolak snapshot server ketika local
    row baru saja dibuat. Jika server=18023 dan local=0, local menjadi 18023.
    Jika local sudah 18025 karena offline, angka 18025 dipertahankan dan akan
    dipush kembali sebagai nilai yang lebih tinggi.
    """
    sid = str(payload.get("sync_id") or "").strip()
    branch = str(payload.get("kode_cabang") or "").strip().upper()
    doc = str(payload.get("document_type") or "").strip().upper()
    series = str(payload.get("series_code") or "").strip().upper()
    if not sid or not branch or not doc or not series:
        return False
    if not _ensure_local_branch_dependency(conn, branch):
        logger.warning(
            "[SYNC] numbering_counters/%s ditahan: cabang %s belum tersedia lokal.",
            sid, branch,
        )
        return False

    local = conn.execute(
        """
        SELECT starting_count, current_count, padding, aktif, sync_id, updated_at
        FROM numbering_counters
        WHERE kode_cabang=? AND document_type=? AND series_code=?
        LIMIT 1
        """,
        (branch, doc, series),
    ).fetchone()

    remote_start = _to_int(payload.get("starting_count"), 1)
    remote_current = _to_int(payload.get("current_count"), 0)
    remote_padding = max(1, _to_int(payload.get("padding"), 5))
    remote_aktif = 1 if payload.get("aktif", True) else 0

    local_start = _to_int(local[0], 0) if local else 0
    local_current = _to_int(local[1], 0) if local else 0
    local_padding = _to_int(local[2], 0) if local else 0
    local_aktif = _to_int(local[3], 0) if local else 0

    # Counter tidak pernah turun. Metadata non-sequence mengikuti server.
    starting_count = max(local_start, remote_start)
    current_count = max(local_current, remote_current)
    padding = remote_padding or local_padding or 5

    conn.execute(
        """
        INSERT INTO numbering_counters(
            kode_cabang,document_type,series_code,starting_count,current_count,padding,aktif,sync_id,created_at,updated_at,deleted_at,
            created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(kode_cabang,document_type,series_code) DO UPDATE SET
            starting_count=MAX(numbering_counters.starting_count, excluded.starting_count),
            current_count=MAX(numbering_counters.current_count, excluded.current_count),
            padding=excluded.padding,
            aktif=excluded.aktif,
            sync_id=excluded.sync_id,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at,
            deleted_at=excluded.deleted_at,
            created_by_user_id=excluded.created_by_user_id,
            created_by_username=excluded.created_by_username,
            created_by_name=excluded.created_by_name,
            updated_by_user_id=excluded.updated_by_user_id,
            updated_by_username=excluded.updated_by_username,
            updated_by_name=excluded.updated_by_name
        """,
        (
            branch, doc, series, starting_count, current_count, padding, remote_aktif, sid,
            payload.get("created_at"), payload.get("updated_at"), payload.get("deleted_at"),
            payload.get("created_by_user_id"), payload.get("created_by_username"), payload.get("created_by_name"),
            payload.get("updated_by_user_id"), payload.get("updated_by_username"), payload.get("updated_by_name"),
        ),
    )

    if local is not None and (local_start != starting_count or local_current != current_count or local[4] != sid):
        logger.info(
            "[SYNC] numbering_counters %s/%s/%s: local=%s → server-baseline=%s (sid=%s)",
            branch, doc, series, local_current, current_count, sid,
        )
    return True


def _master_remote_is_newer(local_updated_at, remote_updated_at, force: bool) -> bool:
    if force:
        return True
    local_dt = _parse_dt(local_updated_at)
    remote_dt = _parse_dt(remote_updated_at)
    if local_dt is None or remote_dt is None:
        return True
    return remote_dt > local_dt


def _sqlite_master_upsert(conn, table_name, columns, values, conflict_columns, update_columns):
    """Safe local SQLite upsert with runtime column/value validation."""
    table = str(table_name or "").strip()
    columns = list(columns or [])
    values = tuple(values or ())
    if not table:
        raise ValueError("Nama tabel master kosong.")
    if len(columns) != len(values):
        raise RuntimeError(
            f"Internal sync SQL mismatch {table}: {len(values)} values untuk {len(columns)} kolom."
        )
    local_columns = {str(r[1]).strip() for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    missing = [c for c in columns if c not in local_columns]
    if missing:
        raise RuntimeError(
            f"Schema SQLite {table} belum lengkap; kolom hilang: {', '.join(missing)}"
        )
    if not conflict_columns:
        raise ValueError(f"Conflict target kosong untuk {table}.")
    placeholders = ",".join("?" for _ in columns)
    assignments = ",".join(f"{c}=excluded.{c}" for c in update_columns)
    sql = (
        f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders}) "
        f"ON CONFLICT({','.join(conflict_columns)}) DO UPDATE SET {assignments}"
    )
    conn.execute(sql, values)

def _apply_remote_master_penerima(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    sid = str(payload.get("sync_id") or "").strip()
    branch = str(payload.get("kode_cabang") or "").strip().upper()
    if not sid or not branch or not _ensure_local_branch_dependency(conn, branch):
        return False
    local = conn.execute("SELECT id_penerima, updated_at FROM master_penerima WHERE sync_id=? LIMIT 1", (sid,)).fetchone()
    if payload.get("deleted_at"):
        if local:
            conn.execute("DELETE FROM master_penerima WHERE sync_id=?", (sid,))
            return True
        return False
    if local and not _master_remote_is_newer(local[1], payload.get("updated_at"), force):
        return False
    name = str(payload.get("nama") or "").strip().upper()
    existing = conn.execute("SELECT id_penerima FROM master_penerima WHERE kode_cabang=? AND TRIM(UPPER(COALESCE(nama,'')))=TRIM(UPPER(?)) LIMIT 1", (branch, name)).fetchone()
    id_penerima = str(payload.get("id_penerima") or "").strip() or (local[0] if local else None) or f"CNE-{uuid.uuid4().hex[:12].upper()}"
    if existing and existing[0] != id_penerima:
        id_penerima = existing[0]
    columns = ["id_penerima","kode_cabang","nama","no_hp","alamat","kota","provinsi","total_transaksi","pembayaran","status_tagihan","sync_id","created_at","updated_at","deleted_at","created_by_user_id","created_by_username","created_by_name","updated_by_user_id","updated_by_username","updated_by_name","is_synced"]
    values = (id_penerima, branch, name, payload.get("no_hp"), payload.get("alamat"), payload.get("kota"), payload.get("provinsi"), _to_int(payload.get("total_transaksi"),0), str(payload.get("pembayaran") or "TF / INVOICE"), str(payload.get("status_tagihan") or "NORMAL"), sid, payload.get("created_at"), payload.get("updated_at"), payload.get("deleted_at"), payload.get("created_by_user_id"), payload.get("created_by_username"), payload.get("created_by_name"), payload.get("updated_by_user_id"), payload.get("updated_by_username"), payload.get("updated_by_name"), 1)
    _sqlite_master_upsert(conn,"master_penerima",columns,values,["id_penerima"],[c for c in columns if c != "id_penerima"])
    return True



def _apply_remote_master_pengirim(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    sid = str(payload.get("sync_id") or "").strip()
    branch = str(payload.get("kode_cabang") or "").strip().upper()
    if not sid or not branch or not _ensure_local_branch_dependency(conn, branch):
        return False
    local = conn.execute("SELECT id_pengirim, updated_at FROM master_pengirim WHERE sync_id=? LIMIT 1", (sid,)).fetchone()
    if payload.get("deleted_at"):
        if local:
            conn.execute("DELETE FROM master_pengirim WHERE sync_id=?", (sid,))
            return True
        return False
    if local and not _master_remote_is_newer(local[1], payload.get("updated_at"), force):
        return False
    name = str(payload.get("nama") or "").strip().upper()
    existing = conn.execute("SELECT id_pengirim FROM master_pengirim WHERE kode_cabang=? AND TRIM(UPPER(COALESCE(nama,'')))=TRIM(UPPER(?)) LIMIT 1", (branch, name)).fetchone()
    id_pengirim = str(payload.get("id_pengirim") or "").strip() or (local[0] if local else None) or f"SHP-{uuid.uuid4().hex[:12].upper()}"
    if existing and existing[0] != id_pengirim:
        id_pengirim = existing[0]
    columns=["id_pengirim","kode_cabang","nama","no_hp","alamat","kota","sync_id","created_at","updated_at","deleted_at","created_by_user_id","created_by_username","created_by_name","updated_by_user_id","updated_by_username","updated_by_name","is_synced"]
    values=(id_pengirim,branch,name,payload.get("no_hp"),payload.get("alamat"),payload.get("kota"),sid,payload.get("created_at"),payload.get("updated_at"),payload.get("deleted_at"),payload.get("created_by_user_id"),payload.get("created_by_username"),payload.get("created_by_name"),payload.get("updated_by_user_id"),payload.get("updated_by_username"),payload.get("updated_by_name"),1)
    _sqlite_master_upsert(conn,"master_pengirim",columns,values,["id_pengirim"],[c for c in columns if c != "id_pengirim"])
    return True



def _apply_remote_truk(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    sid=str(payload.get("sync_id") or "").strip(); branch=str(payload.get("kode_cabang") or "").strip().upper(); nopol=str(payload.get("no_polisi") or "").strip().upper()
    if not sid or not branch or not nopol or not _ensure_local_branch_dependency(conn, branch): return False
    local=conn.execute("SELECT updated_at FROM truk WHERE sync_id=? LIMIT 1",(sid,)).fetchone()
    if payload.get("deleted_at"):
        if local: conn.execute("DELETE FROM truk WHERE sync_id=?",(sid,)); return True
        return False
    if local and not _master_remote_is_newer(local[0],payload.get("updated_at"),force): return False
    columns=["kode_cabang","jenis_truk","no_polisi","nama_sopir","hp_sopir","ket_truk","foto_truk","sync_id","created_at","updated_at","deleted_at","created_by_user_id","created_by_username","created_by_name","updated_by_user_id","updated_by_username","updated_by_name","is_synced"]
    values=(branch,str(payload.get("jenis_truk") or ""),nopol,str(payload.get("nama_sopir") or ""),payload.get("hp_sopir"),payload.get("ket_truk"),payload.get("foto_truk"),sid,payload.get("created_at"),payload.get("updated_at"),payload.get("deleted_at"),payload.get("created_by_user_id"),payload.get("created_by_username"),payload.get("created_by_name"),payload.get("updated_by_user_id"),payload.get("updated_by_username"),payload.get("updated_by_name"),1)
    _sqlite_master_upsert(conn,"truk",columns,values,["kode_cabang","no_polisi"],[c for c in columns if c not in {"kode_cabang","no_polisi"}])
    return True



def _apply_remote_kapal(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    sid=str(payload.get("sync_id") or "").strip(); name=str(payload.get("nama_kapal") or "").strip().upper()
    if not sid or not name: return False
    local=conn.execute("SELECT updated_at FROM kapal WHERE sync_id=? LIMIT 1",(sid,)).fetchone()
    if payload.get("deleted_at"):
        if local: conn.execute("DELETE FROM kapal WHERE sync_id=?",(sid,)); return True
        return False
    if local and not _master_remote_is_newer(local[0],payload.get("updated_at"),force): return False
    columns=["nama_kapal","tujuan","ket_kapal","foto_kapal","sync_id","created_at","updated_at","deleted_at","created_by_user_id","created_by_username","created_by_name","updated_by_user_id","updated_by_username","updated_by_name","is_synced"]
    values=(name,payload.get("tujuan"),payload.get("ket_kapal"),payload.get("foto_kapal"),sid,payload.get("created_at"),payload.get("updated_at"),payload.get("deleted_at"),payload.get("created_by_user_id"),payload.get("created_by_username"),payload.get("created_by_name"),payload.get("updated_by_user_id"),payload.get("updated_by_username"),payload.get("updated_by_name"),1)
    _sqlite_master_upsert(conn,"kapal",columns,values,["nama_kapal"],[c for c in columns if c != "nama_kapal"])
    return True



def _apply_remote_buku_gudang(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    sid = str(payload.get("sync_id") or "").strip()
    gid = str(payload.get("id_gudang") or "").strip().upper()
    branch = str(payload.get("kode_cabang") or "").strip().upper()
    if not sid or not gid or not branch:
        return False
    if not _ensure_local_branch_dependency(conn, branch):
        logger.warning("[SYNC] buku_gudang/%s ditahan: cabang %s belum tersedia lokal.", sid, branch)
        return False

    local = conn.execute(
        "SELECT updated_at FROM buku_gudang WHERE id_gudang=? OR sync_id=? LIMIT 1",
        (gid, sid),
    ).fetchone()
    # Supabase authoritative: tombstone remote menghapus cache operasional lokal.
    if payload.get("deleted_at"):
        if local:
            conn.execute("DELETE FROM buku_gudang WHERE id_gudang=? OR sync_id=?", (gid, sid))
            return True
        return False

    if not force and local and not _master_remote_is_newer(local[0], payload.get("updated_at"), force):
        return False

    columns = [
        "id_gudang", "kode_cabang", "tanggal", "no_resi", "jenis", "status_resi",
        "sync_id", "created_at", "updated_at", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name", "is_synced",
    ]
    values = (
        gid,
        branch,
        payload.get("tanggal"),
        str(payload.get("no_resi") or "").strip().upper() or None,
        payload.get("jenis"),
        payload.get("status_resi"),
        sid,
        payload.get("created_at"),
        payload.get("updated_at"),
        payload.get("deleted_at"),
        payload.get("created_by_user_id"),
        payload.get("created_by_username"),
        payload.get("created_by_name"),
        payload.get("updated_by_user_id"),
        payload.get("updated_by_username"),
        payload.get("updated_by_name"),
        1,
    )
    _sqlite_master_upsert(
        conn,
        "buku_gudang",
        columns,
        values,
        ["id_gudang"],
        [c for c in columns if c != "id_gudang"],
    )
    return True



def _apply_remote_manifest(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    """Apply server Manifest header; note_manifest is not data_resi.ket_manifest."""
    sid = str(payload.get("sync_id") or "").strip()
    manifest_id = str(payload.get("id_manifest") or "").strip().upper()
    branch = str(payload.get("kode_cabang") or "").strip().upper()
    if not sid or not manifest_id or not branch:
        return False

    local = conn.execute(
        "SELECT id_manifest, kode_cabang, updated_at, sync_id FROM manifest "
        "WHERE sync_id=? OR id_manifest=? LIMIT 1", (sid, manifest_id)
    ).fetchone()
    if payload.get("deleted_at"):
        if local:
            conn.execute("DELETE FROM manifest WHERE sync_id=? OR id_manifest=?", (sid, manifest_id))
            return True
        return False

    if not _ensure_local_branch_dependency(conn, branch):
        logger.warning("[SYNC] manifest/%s ditahan: cabang %s belum tersedia lokal.", sid, branch)
        return False

    identity_changed = bool(local and str(local[3] or "").strip() != sid)
    if local and not identity_changed and not _master_remote_is_newer(
        local[2], payload.get("updated_at"), force
    ):
        return False

    columns = [
        "id_manifest", "kode_cabang", "tanggal", "no_polisi", "nama_sopir",
        "nama_kapal", "note_manifest", "status_manifest", "sync_id", "created_at",
        "updated_at", "deleted_at", "created_by_user_id", "created_by_username",
        "created_by_name", "updated_by_user_id", "updated_by_username",
        "updated_by_name", "is_synced",
    ]
    values = (
        manifest_id, branch, payload.get("tanggal"), payload.get("no_polisi"),
        payload.get("nama_sopir"), payload.get("nama_kapal"), payload.get("note_manifest"),
        payload.get("status_manifest"), sid, payload.get("created_at"), payload.get("updated_at"),
        payload.get("deleted_at"), payload.get("created_by_user_id"),
        payload.get("created_by_username"), payload.get("created_by_name"),
        payload.get("updated_by_user_id"), payload.get("updated_by_username"),
        payload.get("updated_by_name"), 1,
    )
    _sqlite_master_upsert(
        conn, "manifest", columns, values, ["id_manifest"],
        [column for column in columns if column != "id_manifest"],
    )
    return True


def _delete_local_manifest(conn, payload: Dict[str, Any], record_key: str = "") -> None:
    sid = str(payload.get("sync_id") or record_key or "").strip()
    manifest_id = str(payload.get("id_manifest") or "").strip().upper()
    if sid and manifest_id:
        conn.execute("DELETE FROM manifest WHERE sync_id=? OR id_manifest=?", (sid, manifest_id))
    elif sid:
        conn.execute("DELETE FROM manifest WHERE sync_id=?", (sid,))
    elif manifest_id:
        conn.execute("DELETE FROM manifest WHERE id_manifest=?", (manifest_id,))


def _ensure_buku_gudang_local_schema(conn) -> None:
    """Pastikan schema Buku Gudang tersedia sebelum sync menyentuh row lokal.

    Ini sengaja berada di sync_service sebagai safety net. Bila aplikasi startup
    menjalankan worker sync lebih cepat daripada bootstrap/migration database,
    pull tidak boleh langsung gagal hanya karena kolom sync_id belum ada.
    """
    table = "buku_gudang"
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    if not exists:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS buku_gudang (
                id_gudang TEXT PRIMARY KEY,
                kode_cabang TEXT NOT NULL,
                tanggal DATE,
                no_resi TEXT,
                jenis TEXT,
                status_resi TEXT,
                is_synced INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_id TEXT,
                deleted_at TEXT,
                created_by_user_id TEXT,
                created_by_username TEXT,
                created_by_name TEXT,
                updated_by_user_id TEXT,
                updated_by_username TEXT,
                updated_by_name TEXT
            )
        """)

    actual = {
        str(row[1]).strip()
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    additions = {
        "sync_id": "TEXT",
        "deleted_at": "TEXT",
        "created_by_user_id": "TEXT",
        "created_by_username": "TEXT",
        "created_by_name": "TEXT",
        "updated_by_user_id": "TEXT",
        "updated_by_username": "TEXT",
        "updated_by_name": "TEXT",
    }
    for column, ddl in additions.items():
        if column not in actual:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # Backfill identity for legacy/local rows exactly once.
    rows = conn.execute(
        f"SELECT rowid FROM {table} WHERE sync_id IS NULL OR TRIM(sync_id) = ''"
    ).fetchall()
    for (rowid,) in rows:
        conn.execute(
            f"UPDATE {table} SET sync_id=? WHERE rowid=?",
            (str(uuid.uuid4()), rowid),
        )

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_buku_gudang_sync_id "
        "ON buku_gudang(sync_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_buku_gudang_cabang_sync "
        "ON buku_gudang(kode_cabang, sync_id)"
    )

    # Pastikan infra outbox tersedia even bila DB bootstrap terlewat.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_key TEXT NOT NULL,
            operation TEXT NOT NULL CHECK(operation IN ('INSERT','UPDATE','DELETE')),
            payload_json TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'PENDING',
            retry_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_control (
            id INTEGER PRIMARY KEY CHECK(id=1),
            suppress_outbox INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("INSERT OR IGNORE INTO sync_control(id,suppress_outbox) VALUES(1,0)")

    payload_new = "json_object(" + ", ".join([
        "'id_gudang', NEW.id_gudang",
        "'kode_cabang', NEW.kode_cabang",
        "'tanggal', NEW.tanggal",
        "'no_resi', NEW.no_resi",
        "'jenis', NEW.jenis",
        "'status_resi', NEW.status_resi",
        "'sync_id', NEW.sync_id",
        "'created_at', NEW.created_at",
        "'updated_at', NEW.updated_at",
        "'deleted_at', NEW.deleted_at",
        "'created_by_user_id', NEW.created_by_user_id",
        "'created_by_username', NEW.created_by_username",
        "'created_by_name', NEW.created_by_name",
        "'updated_by_user_id', NEW.updated_by_user_id",
        "'updated_by_username', NEW.updated_by_username",
        "'updated_by_name', NEW.updated_by_name",
    ]) + ")"
    payload_old = payload_new.replace("NEW.", "OLD.")

    for name in (
        "trg_local_buku_gudang_outbox_insert",
        "trg_local_buku_gudang_outbox_update",
        "trg_local_buku_gudang_outbox_delete",
    ):
        conn.execute(f"DROP TRIGGER IF EXISTS {name}")

    conn.execute(f"""
        CREATE TRIGGER trg_local_buku_gudang_outbox_insert
        AFTER INSERT ON buku_gudang
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
            INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
            VALUES('buku_gudang',NEW.sync_id,'INSERT',{payload_new});
        END
    """)
    changed = " OR ".join(
        f"NEW.{c} IS NOT OLD.{c}" for c in (
            "id_gudang", "kode_cabang", "tanggal", "no_resi", "jenis",
            "status_resi", "sync_id", "created_at", "deleted_at",
            "created_by_user_id", "created_by_username", "created_by_name",
            "updated_by_user_id", "updated_by_username", "updated_by_name",
        )
    )
    conn.execute(f"""
        CREATE TRIGGER trg_local_buku_gudang_outbox_update
        AFTER UPDATE ON buku_gudang
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
         AND ({changed})
        BEGIN
            INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
            VALUES('buku_gudang',NEW.sync_id,'UPDATE',{payload_new});
        END
    """)
    conn.execute(f"""
        CREATE TRIGGER trg_local_buku_gudang_outbox_delete
        AFTER DELETE ON buku_gudang
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
            INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
            VALUES('buku_gudang',OLD.sync_id,'DELETE',{payload_old});
        END
    """)
    conn.commit()


def _validate_local_master_sync_schema(conn):
    expected={
        "master_penerima":{"id_penerima","kode_cabang","nama","sync_id","updated_at","deleted_at"},
        "master_pengirim":{"id_pengirim","kode_cabang","nama","sync_id","updated_at","deleted_at"},
        "truk":{"kode_cabang","no_polisi","sync_id","updated_at","deleted_at"},
        "kapal":{"nama_kapal","sync_id","updated_at","deleted_at"},
        "buku_gudang":{"id_gudang","kode_cabang","no_resi","sync_id","updated_at","deleted_at"},
        "manifest":{"id_manifest","kode_cabang","sync_id","updated_at","deleted_at","note_manifest"},
    }
    for table, required in expected.items():
        actual={str(r[1]).strip() for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        missing=sorted(required-actual)
        if missing:
            raise RuntimeError(f"Schema SQLite {table} belum siap untuk sync; kolom hilang: {', '.join(missing)}")


def sync_generic_masters() -> Dict[str, int]:
    if not _session_ready():
        return {
            "numbering": 0, "numbering_counters": 0,
            "master_penerima": 0, "master_pengirim": 0, "truk": 0, "kapal": 0, "manifest": 0,
        }

    numbering = _fetch_all(
        "numbering_settings",
        columns="kode_cabang,document_type,format_template,starting_count,current_count,padding,reset_rule,aktif,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=500,
    )
    counters = _fetch_all(
        "numbering_counters",
        columns="kode_cabang,document_type,series_code,starting_count,current_count,padding,aktif,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=1000,
    )
    penerima = _fetch_all(
        "master_penerima",
        columns="id_penerima,kode_cabang,nama,no_hp,alamat,kota,provinsi,total_transaksi,pembayaran,status_tagihan,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=500,
    )
    pengirim = _fetch_all(
        "master_pengirim",
        columns="id_pengirim,kode_cabang,nama,no_hp,alamat,kota,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=500,
    )
    truk = _fetch_all(
        "truk",
        columns="kode_cabang,jenis_truk,no_polisi,nama_sopir,hp_sopir,ket_truk,foto_truk,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=500,
    )
    kapal = _fetch_all(
        "kapal",
        columns="nama_kapal,tujuan,ket_kapal,foto_kapal,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=500,
    )
    buku_gudang = _fetch_all(
        "buku_gudang",
        columns="id_gudang,kode_cabang,tanggal,no_resi,jenis,status_resi,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=500,
    )
    manifest_rows = _fetch_all(
        "manifest",
        columns="id_manifest,kode_cabang,tanggal,no_polisi,nama_sopir,nama_kapal,note_manifest,status_manifest,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=500,
    )

    conn = _connect()
    _ensure_buku_gudang_local_schema(conn)
    counts = {"numbering": 0, "numbering_counters": 0, "master_penerima": 0, "master_pengirim": 0, "truk": 0, "kapal": 0, "buku_gudang": 0, "manifest": 0}
    try:
        _set_suppress(conn, True)
        repaired = _repair_unqueued_local_sync_rows(conn, {
            "master_penerima": penerima,
            "master_pengirim": pengirim,
            "truk": truk,
            "kapal": kapal,
            "buku_gudang": buku_gudang,
            "manifest": manifest_rows,
        })
        if repaired["queued"] or repaired["conflicts"]:
            logger.warning(
                "[SYNC] Pemulihan outbox legacy master: queued=%s, marked_synced=%s, conflicts=%s",
                repaired["queued"], repaired["marked_synced"], repaired["conflicts"],
            )
        for row in numbering:
            if _apply_remote_numbering(conn, row, force=False): counts["numbering"] += 1
        for row in counters:
            if _apply_remote_numbering_counter(conn, row, force=False): counts["numbering_counters"] += 1
        for row in penerima:
            key = str(row.get("sync_id") or "").strip()
            if key and _local_has_pending_or_conflict(conn, "master_penerima", key):
                continue
            if _apply_remote_master_penerima(conn, row, force=False): counts["master_penerima"] += 1
        for row in pengirim:
            key = str(row.get("sync_id") or "").strip()
            if key and _local_has_pending_or_conflict(conn, "master_pengirim", key):
                continue
            if _apply_remote_master_pengirim(conn, row, force=False): counts["master_pengirim"] += 1
        for row in truk:
            key = str(row.get("sync_id") or "").strip()
            if key and _local_has_pending_or_conflict(conn, "truk", key):
                continue
            if _apply_remote_truk(conn, row, force=False): counts["truk"] += 1
        for row in kapal:
            key = str(row.get("sync_id") or "").strip()
            if key and _local_has_pending_or_conflict(conn, "kapal", key):
                continue
            if _apply_remote_kapal(conn, row, force=False): counts["kapal"] += 1
        for row in buku_gudang:
            key = str(row.get("sync_id") or "").strip()
            if key and _local_has_pending_or_conflict(conn, "buku_gudang", key):
                continue
            if _apply_remote_buku_gudang(conn, row, force=False): counts["buku_gudang"] += 1
        for row in manifest_rows:
            key = str(row.get("sync_id") or "").strip()
            local_key = _manifest_local_key_by_id(conn, row)
            if (
                (key and _local_has_pending_or_conflict(conn, "manifest", key))
                or (local_key and _local_has_pending_or_conflict(conn, "manifest", local_key))
            ):
                continue
            if _apply_remote_manifest(conn, row, force=False): counts["manifest"] += 1

        # Supabase authoritative: row master/config yang sudah hilang di server
        # ikut dihapus dari cache lokal, kecuali perubahan offline masih pending
        # atau sedang conflict.
        for table_name, rows in (
            ("numbering_settings", numbering),
            ("numbering_counters", counters),
            ("master_penerima", penerima),
            ("master_pengirim", pengirim),
            ("truk", truk),
            ("kapal", kapal),
            ("buku_gudang", buku_gudang),
            ("manifest", manifest_rows),
        ):
            _reconcile_authoritative_table(conn, table_name, rows)

        _set_suppress(conn, False)
        conn.commit()
        return counts
    except Exception:
        _set_suppress(conn, False)
        conn.rollback()
        raise
    finally:
        conn.close()


def _resolve_superseded_data_resi_conflicts(conn) -> int:
    """Resolve stale Resi conflicts only after comparing against live Supabase state.

    A conflict's remote_payload is a historical snapshot; it may be older than a
    later successful Manifest edit. Therefore it must not be used as the source
    of truth for deciding whether the conflict is now resolved. This routine
    checks the current server row, requires a later successful outbox operation,
    requires no newer pending/conflicted operation, and compares business fields
    before changing only sync metadata plus queue/history status.

    If the live server row cannot be read, is deleted, or differs in any business
    field, the conflict is left untouched. No business field is copied from a
    historical payload.
    """
    open_rows = conn.execute(
        """
        SELECT record_key FROM sync_conflicts
        WHERE table_name = 'data_resi' AND status = 'OPEN'
        UNION
        SELECT record_key FROM sync_outbox
        WHERE table_name = 'data_resi' AND status = 'CONFLICT'
        ORDER BY record_key
        """
    ).fetchall()

    # Compare the full Resi business state, not just Manifest fields. Revision,
    # timestamps and actor metadata are synchronization/audit metadata and are
    # reconciled only after the business values are proven equal.
    compare_fields = (
        "no_resi", "kode_cabang", "tanggal_masuk", "tanggal_keluar",
        "pengirim", "hp_pengirim", "alamat_pengirim", "kota_asal",
        "penerima", "hp_penerima", "alamat_penerima", "kota_tujuan",
        "nama_barang", "koli", "berat", "cbm", "ongkir_per_kg",
        "ongkir_per_cbm", "subtotal_ongkir", "jenis_pajak", "total_ongkir",
        "pembayaran", "status_resi", "foto_bukti", "truk",
        "ket_buku_gudang", "no_manifest", "ket_manifest", "rincian_json",
        "deleted_at",
    )
    upper_fields = {"no_resi", "kode_cabang", "status_resi", "no_manifest"}
    integer_fields = {"koli", "ongkir_per_kg", "ongkir_per_cbm", "subtotal_ongkir", "total_ongkir"}
    float_fields = {"berat", "cbm"}

    def normalize(field, value):
        if value is None or value == "":
            return None
        if field in integer_fields:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return str(value).strip()
        if field in float_fields:
            try:
                # Round insignificant SQLite/Postgres float representation drift.
                return round(float(value), 8)
            except (TypeError, ValueError):
                return str(value).strip()
        if field == "rincian_json":
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
                return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            except (TypeError, ValueError, json.JSONDecodeError):
                return str(value).strip()
        text = str(value).strip()
        return text.upper() if field in upper_fields else text

    healed = 0
    local_columns = {
        str(row[1]).strip()
        for row in conn.execute("PRAGMA table_info(data_resi)").fetchall()
    }

    for (record_key_raw,) in open_rows:
        record_key = str(record_key_raw or "").strip().upper()
        if not record_key:
            continue

        local = _local_row_json(conn, "data_resi", "UPPER(no_resi) = ?", (record_key,))
        if not local or int(local.get("is_synced") or 0) != 1:
            continue

        local_sid = str(local.get("sync_id") or "").strip()
        if not local_sid:
            continue

        success_row = conn.execute(
            """
            SELECT MAX(id) FROM sync_outbox
            WHERE table_name = 'data_resi' AND record_key = ? AND status = 'SYNCED'
            """,
            (record_key,),
        ).fetchone()
        latest_success_id = int(success_row[0] or 0) if success_row else 0
        if not latest_success_id:
            continue

        conflict_row = conn.execute(
            """
            SELECT MAX(id) FROM sync_outbox
            WHERE table_name = 'data_resi' AND record_key = ? AND status = 'CONFLICT'
            """,
            (record_key,),
        ).fetchone()
        latest_conflict_id = int(conflict_row[0] or 0) if conflict_row else 0
        if latest_conflict_id >= latest_success_id:
            continue

        newer_local_change = conn.execute(
            """
            SELECT 1 FROM sync_outbox
            WHERE table_name = 'data_resi' AND record_key = ?
              AND status IN ('PENDING', 'CONFLICT') AND id > ?
            LIMIT 1
            """,
            (record_key, latest_success_id),
        ).fetchone()
        if newer_local_change:
            continue

        # Read the live row from Supabase. A stale sync_conflicts.remote_payload
        # is intentionally not used here because a later successful push can
        # legitimately supersede it.
        try:
            remote = _server_resi_row(local_sid)
        except Exception as exc:
            logger.debug(
                "[SYNC] Belum bisa merekonsiliasi konflik Resi %s; pembacaan server gagal: %s",
                record_key, exc,
            )
            continue
        if not isinstance(remote, dict) or not remote or remote.get("deleted_at"):
            continue
        if str(remote.get("sync_id") or "").strip() != local_sid:
            continue
        if any(
            field not in remote
            or normalize(field, local.get(field)) != normalize(field, remote.get(field))
            for field in compare_fields
        ):
            continue

        # Business state matches the CURRENT server row. Align only sync/audit
        # metadata so the next edit starts from the server's canonical revision.
        metadata = {}
        for field in (
            "revision", "updated_at", "deleted_at",
            "created_by_user_id", "created_by_username", "created_by_name",
            "updated_by_user_id", "updated_by_username", "updated_by_name",
        ):
            if field in local_columns and field in remote:
                value = remote.get(field)
                if field == "revision" and value is not None:
                    value = _to_int(value, 0)
                if field.startswith("created_by_") and value in (None, ""):
                    # Keep a non-empty immutable local creator if legacy server
                    # metadata is blank; do not erase attribution during repair.
                    continue
                metadata[field] = value
        if "is_synced" in local_columns:
            metadata["is_synced"] = 1

        if metadata:
            suppress_row = conn.execute(
                "SELECT suppress_outbox FROM sync_control WHERE id = 1 LIMIT 1"
            ).fetchone()
            was_suppressed = bool(suppress_row[0]) if suppress_row else False
            if not was_suppressed:
                _set_suppress(conn, True)
            try:
                assignments = ", ".join(f'"{field}" = ?' for field in metadata)
                conn.execute(
                    f"UPDATE data_resi SET {assignments} WHERE UPPER(no_resi) = ?",
                    (*metadata.values(), record_key),
                )
            finally:
                if not was_suppressed:
                    _set_suppress(conn, False)

        # Mark only older conflict outbox entries as superseded by this successful
        # push. Keep rows and conflict JSON for audit; do not delete queue history.
        conn.execute(
            """
            UPDATE sync_outbox
            SET status = 'SYNCED', last_error = NULL
            WHERE table_name = 'data_resi' AND record_key = ?
              AND status = 'CONFLICT' AND id < ?
            """,
            (record_key, latest_success_id),
        )
        conn.execute(
            """
            UPDATE sync_conflicts
            SET status = 'RESOLVED'
            WHERE table_name = 'data_resi' AND record_key = ? AND status = 'OPEN'
            """,
            (record_key,),
        )
        healed += 1

    if healed:
        logger.info(
            "[SYNC] Menutup %s konflik Resi lama setelah state bisnis cocok dengan kondisi Supabase terbaru; "
            "histori konflik dipertahankan.",
            healed,
        )
    return healed


def pull_server_changes(limit: int = BATCH_SIZE) -> int:
    if not _session_ready():
        return 0

    conn = _connect()
    diterapkan = 0
    try:
        _ensure_buku_gudang_local_schema(conn)
        _validate_local_master_sync_schema(conn)
        # Resolve only stale conflicts where a newer successful push exists and
        # retained server business fields match the current local Resi.
        _resolve_superseded_data_resi_conflicts(conn)
        conn.commit()
        cursor = int(_get_state(conn, "last_server_change_id", "0") or 0)
        response = (
            supabase
            .table("sync_changes")
            .select("id,event_id,table_name,record_sync_id,operation,row_data,changed_at")
            .gt("id", cursor)
            .in_("table_name", [
                "data_resi", "data_resi_detail", "numbering_settings", "numbering_counters",
                "cabang_wilayah", "master_penerima", "master_pengirim", "truk", "kapal", "buku_gudang", "manifest"
            ])
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

            manifest_local_key = (
                _manifest_local_key_by_id(conn, payload)
                if table_name == "manifest" else ""
            )
            if (
                _has_pending(conn, table_name, record_key)
                or _has_unresolved_conflict(conn, table_name, record_key)
                or (
                    manifest_local_key
                    and _local_has_pending_or_conflict(conn, "manifest", manifest_local_key)
                )
            ):
                _store_pull_conflict(
                    conn, event_id or str(uuid.uuid4()), table_name, record_key, payload
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
                        _delete_local_resi(conn, record_key)
                    elif payload.get("deleted_at"):
                        _delete_local_resi(conn, record_key)
                    else:
                        if not _ensure_local_branch_for_resi(conn, str(payload.get("kode_cabang") or "")):
                            _record_sync_dependency_conflict(
                                conn, "data_resi", record_key, payload, "MISSING_BRANCH"
                            )
                            _set_suppress(conn, False)
                            _set_state(conn, "last_server_change_id", event.get("id", cursor))
                            conn.commit()
                            continue
                        _apply_remote_resi(conn, payload)
                elif table_name == "numbering_settings":
                    _apply_remote_numbering(conn, payload, force=True)
                elif table_name == "numbering_counters":
                    _apply_remote_numbering_counter(conn, payload, force=True)
                elif table_name == "cabang_wilayah":
                    applied_wilayah = _apply_remote_cabang_wilayah(conn, payload, force=True)
                    if not applied_wilayah:
                        _record_sync_dependency_conflict(
                            conn, "cabang_wilayah", record_key, payload, "MISSING_LOCAL_DEPENDENCY"
                        )
                        _set_suppress(conn, False)
                        _set_state(conn, "last_server_change_id", event.get("id", cursor))
                        conn.commit()
                        continue
                elif table_name == "manifest":
                    if operation == "DELETE":
                        _delete_local_manifest(conn, payload, record_key)
                    else:
                        applied_manifest = _apply_remote_manifest(conn, payload, force=True)
                        if not applied_manifest:
                            _set_suppress(conn, False)
                            conn.rollback()
                            logger.warning(
                                "[SYNC] manifest/%s ditahan; cabang belum siap. Cursor tetap di %s.",
                                record_key, cursor,
                            )
                            break
                elif table_name in {"master_penerima", "master_pengirim", "truk", "kapal", "buku_gudang"}:
                    if table_name == "buku_gudang" and operation != "DELETE":
                        parent_no_resi = str(payload.get("no_resi") or "").strip().upper()
                        if parent_no_resi and not conn.execute(
                            "SELECT 1 FROM data_resi WHERE no_resi=? LIMIT 1",
                            (parent_no_resi,),
                        ).fetchone():
                            response_parent = (
                                supabase.table("data_resi").select("*").eq("no_resi", parent_no_resi).limit(1).execute()
                            )
                            parent_rows = response_parent.data or []
                            if parent_rows:
                                parent_payload = parent_rows[0]
                                if _ensure_local_branch_for_resi(conn, str(parent_payload.get("kode_cabang") or "")):
                                    _apply_remote_resi(conn, parent_payload)
                    handlers = {
                        "master_penerima": _apply_remote_master_penerima,
                        "master_pengirim": _apply_remote_master_pengirim,
                        "truk": _apply_remote_truk,
                        "kapal": _apply_remote_kapal,
                        "buku_gudang": _apply_remote_buku_gudang,
                    }
                    applied_master = handlers[table_name](conn, payload, force=True)
                    if not applied_master:
                        # Dependency failure is retryable. Do not advance the cursor;
                        # the next sync cycle will retry after branch/bootstrap repair.
                        _set_suppress(conn, False)
                        conn.rollback()
                        logger.warning(
                            "[SYNC] %s/%s ditahan; dependency belum siap. Cursor tetap di %s.",
                            table_name, record_key, cursor,
                        )
                        break
                else:
                    if operation != "DELETE":
                        parent_no_resi = str(payload.get("no_resi") or "").strip().upper()
                        if parent_no_resi and not conn.execute(
                            "SELECT 1 FROM data_resi WHERE no_resi=? LIMIT 1",
                            (parent_no_resi,),
                        ).fetchone():
                            response_parent = (
                                supabase.table("data_resi")
                                .select("*")
                                .eq("no_resi", parent_no_resi)
                                .limit(1)
                                .execute()
                            )
                            parent_rows = response_parent.data or []
                            if parent_rows:
                                parent_payload = parent_rows[0]
                                _ensure_local_branch_for_resi(
                                    conn, str(parent_payload.get("kode_cabang") or "")
                                )
                                _apply_remote_resi(conn, parent_payload)
                    _apply_remote_detail(conn, payload, operation)
                _set_suppress(conn, False)
                _set_state(conn, "last_server_change_id", event.get("id", cursor))
                conn.commit()
                diterapkan += 1
            except sqlite3.IntegrityError as exc:
                _set_suppress(conn, False)
                conn.rollback()
                # Umgeleitete/poisoned remote event: simpan sebagai conflict dan
                # majukan cursor agar satu event rusak tidak membuat seluruh sync
                # gagal berulang-ulang. Payload tetap tersimpan untuk rekonsiliasi.
                _record_recovery_conflict(
                    conn,
                    table_name,
                    record_key or event_id or str(event.get("id") or ""),
                    _local_row_json(
                        conn,
                        table_name,
                        "sync_id=?" if table_name != "data_resi" else "no_resi=?",
                        (record_key,),
                    ) if table_name in TABLES else None,
                    payload,
                    f"PULL_FK_OR_INTEGRITY: {exc}",
                )
                _set_state(conn, "last_server_change_id", event.get("id", cursor))
                conn.commit()
                logger.warning(
                    "[SYNC] Pull conflict %s/%s event #%s: %s",
                    table_name, record_key, event.get("id"), exc,
                )
                continue
            except Exception as exc:
                _set_suppress(conn, False)
                raise RuntimeError(
                    f"pull_server_changes: tabel={table_name}, operation={operation}, record={record_key}, event_id={event.get('id')}: {type(exc).__name__}: {exc}"
                ) from exc
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
    """True bila DB lokal masih layak dianggap *fresh* untuk initial snapshot.

    Jangan memakai tabel metadata/bootstrap sebagai penentu DB "sudah berisi data".
    database_manager dan seed client memang boleh membuat baris default seperti:
    - cabang_wilayah
    - numbering_settings / numbering_counters
    - cabang internal DEV_SYS

    Baris-baris tersebut bukan bukti bahwa perangkat sudah memiliki data
    operasional lokal. Bila kita menganggapnya sebagai DB lama, initial snapshot
    bisa salah dilewati lalu recovery langsung masuk ke incremental history.
    Itu dapat membuat parent/reference belum terpasang ketika event child ditarik
    dan memicu FOREIGN KEY constraint failed.

    Untuk membedakan DB fresh vs DB yang benar-benar sudah dipakai, gunakan
    indikator yang kuat: data Resi/detail dan antrean sync/conflict lokal.
    Perubahan metadata lokal yang sah juga akan masuk ke sync_outbox melalui trigger.
    """
    operational_tables = (
        "data_resi",
        "data_resi_detail",
        "manifest",
    )
    for table in operational_tables:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if int(row[0] or 0) != 0:
            return False

    # Schema v16 added outbox triggers for four masters, but existing v16
    # databases do not rerun that migration. Treat their unmarked rows as legacy
    # local changes so recovery can compare them with the server before pruning.
    for table in (
        "data_resi", "buku_gudang", "master_penerima", "master_pengirim", "truk", "kapal", "manifest",
    ):
        columns = {
            str(row[1]).strip()
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if "is_synced" in columns:
            dirty = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE COALESCE(is_synced, 0) = 0"
            ).fetchone()
            if int(dirty[0] or 0) > 0:
                return False

    pending = conn.execute(
        "SELECT COUNT(*) FROM sync_outbox WHERE status IN ('PENDING','CONFLICT')"
    ).fetchone()
    if int(pending[0] or 0) != 0:
        return False

    conflicts = conn.execute(
        "SELECT COUNT(*) FROM sync_conflicts WHERE status='OPEN'"
    ).fetchone()
    if int(conflicts[0] or 0) != 0:
        return False

    return True


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

    if str(CURRENT_SESSION.get("client_code") or "MAHKOTA").strip().upper() == "MAHKOTA" and kode in MAHKOTA_FIXED_BRANCH_RULES:
        aturan_prefix = json.dumps(MAHKOTA_FIXED_BRANCH_RULES[kode], ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO data_cabang(
            kode_cabang, nama_cabang, resi_prefix,
            start_seq_json, aturan_prefix, created_at,
            created_by_user_id, created_by_username, created_by_name,
            updated_by_user_id, updated_by_username, updated_by_name
        ) VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?, ?, ?)
        ON CONFLICT(kode_cabang) DO UPDATE SET
            nama_cabang=excluded.nama_cabang,
            resi_prefix=excluded.resi_prefix,
            start_seq_json=excluded.start_seq_json,
            aturan_prefix=excluded.aturan_prefix,
            created_by_user_id=excluded.created_by_user_id,
            created_by_username=excluded.created_by_username,
            created_by_name=excluded.created_by_name,
            updated_by_user_id=excluded.updated_by_user_id,
            updated_by_username=excluded.updated_by_username,
            updated_by_name=excluded.updated_by_name
        """,
        (
            kode,
            str(payload.get("nama_cabang") or kode),
            str(payload.get("resi_prefix") or "INV"),
            json.dumps(start_seq, ensure_ascii=False) if isinstance(start_seq, dict) else (start_seq or "{}"),
            json.dumps(aturan_prefix, ensure_ascii=False) if isinstance(aturan_prefix, dict) else (aturan_prefix or "{}"),
            payload.get("created_at"),
            payload.get("created_by_user_id"), payload.get("created_by_username"), payload.get("created_by_name"),
            payload.get("updated_by_user_id"), payload.get("updated_by_username"), payload.get("updated_by_name"),
        ),
    )



def _apply_remote_cabang_wilayah(conn, payload: Dict[str, Any], *, force: bool = False) -> bool:
    kode_cabang = str(payload.get("kode_cabang") or "").strip().upper()
    kode_wilayah = str(payload.get("kode_wilayah") or "").strip().upper()
    if not kode_cabang or not kode_wilayah:
        return False

    if not _ensure_local_branch_dependency(conn, kode_cabang):
        logger.warning("[SYNC] cabang_wilayah %s/%s ditahan: cabang parent belum tersedia lokal.", kode_cabang, kode_wilayah)
        return False

    if not _ensure_local_wilayah_dependency(conn, kode_wilayah):
        logger.warning("[SYNC] cabang_wilayah %s/%s ditahan: master wilayah %s belum tersedia lokal.", kode_cabang, kode_wilayah, kode_wilayah)
        return False

    if str(CURRENT_SESSION.get("client_code") or "MAHKOTA").strip().upper() == "MAHKOTA":
        fixed_prefix = MAHKOTA_FIXED_CABANG_WILAYAH.get((kode_cabang, kode_wilayah))
        if fixed_prefix is None:
            # Mahkota hanya mengenal 6 mapping resmi. Jangan masukkan row asing.
            return False
        payload = dict(payload)
        payload["prefix_resi"] = fixed_prefix
        payload["aktif"] = 1

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
            sync_id, created_at, updated_at, deleted_at,
            created_by_user_id, created_by_username, created_by_name,
            updated_by_user_id, updated_by_username, updated_by_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            payload.get("created_by_user_id"),
            payload.get("created_by_username"),
            payload.get("created_by_name"),
            payload.get("updated_by_user_id"),
            payload.get("updated_by_username"),
            payload.get("updated_by_name"),
        ),
    )
    return True



def sync_cabang_wilayah() -> Dict[str, int]:
    """Tarik aturan prefix cabang; daftar wilayah sendiri tetap lokal dan fixed."""
    if not _session_ready():
        return {"cabang_wilayah": 0}

    cabang_wilayah_rows = _fetch_all(
        "cabang_wilayah",
        columns=(
            "kode_cabang,kode_wilayah,prefix_resi,aktif,sync_id,"
            "created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,"
            "updated_by_user_id,updated_by_username,updated_by_name"
        ),
        page_size=500,
    )
    conn = _connect()
    applied = 0
    try:
        _set_suppress(conn, True)
        for payload in cabang_wilayah_rows:
            if _apply_remote_cabang_wilayah(conn, payload, force=False):
                applied += 1

        # Supabase authoritative untuk mapping cabang-wilayah juga: row yang
        # sudah tidak ada di server dibersihkan dari cache lokal, kecuali masih
        # ada perubahan lokal yang belum terselesaikan.
        _reconcile_authoritative_table(conn, "cabang_wilayah", cabang_wilayah_rows)

        _set_suppress(conn, False)
        conn.commit()
        return {"cabang_wilayah": applied}
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
        columns="kode_cabang,nama_cabang,resi_prefix,start_seq_json,aturan_prefix,created_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
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



def _local_row_json(conn, table_name: str, where_sql: str, params=()):
    row = conn.execute(f"SELECT * FROM {table_name} WHERE {where_sql} LIMIT 1", params).fetchone()
    if row is None:
        return None
    cols = [d[1] for d in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    return dict(zip(cols, row))


def _ensure_local_wilayah_dependency(conn, kode_wilayah: str) -> bool:
    """Pastikan master_wilayah lokal tersedia sebelum insert cabang_wilayah.

    master_wilayah memang master lokal fixed untuk Mahkota dan tidak di-pull dari
    sync_changes. DB lama/recovery bisa saja kehilangan salah satu dari tiga
    kode wilayah fixed, sehingga insert cabang_wilayah akan memicu FK.
    """
    kode = str(kode_wilayah or "").strip().upper()
    if not kode:
        return False

    if conn.execute(
        "SELECT 1 FROM master_wilayah WHERE kode_wilayah=? LIMIT 1",
        (kode,),
    ).fetchone():
        return True

    client = str(CURRENT_SESSION.get("client_code") or "MAHKOTA").strip().upper()
    fixed = {
        "KALTIM": ("KALIMANTAN TIMUR", 10),
        "KALSEL": ("KALIMANTAN SELATAN", 20),
        "LAINNYA": ("PROVINSI LAINNYA", 30),
    }
    if client != "MAHKOTA" or kode not in fixed:
        return False

    nama, urutan = fixed[kode]
    conn.execute(
        """
        INSERT OR IGNORE INTO master_wilayah(
            kode_wilayah, nama_wilayah, tipe_wilayah, aktif, urutan, sync_id,
            created_at, updated_at, deleted_at
        ) VALUES (?, ?, 'PROVINSI', 1, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL)
        """,
        (
            kode,
            nama,
            urutan,
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"kargo:mahkota:wilayah:{kode}")),
        ),
    )
    return conn.execute(
        "SELECT 1 FROM master_wilayah WHERE kode_wilayah=? LIMIT 1",
        (kode,),
    ).fetchone() is not None


def _ensure_local_branch_for_resi(conn, kode_cabang: str) -> bool:
    """Pastikan FK data_resi -> data_cabang tersedia sebelum recovery/pull detail."""
    kode = str(kode_cabang or "").strip().upper()
    if not kode:
        return False
    if conn.execute("SELECT 1 FROM data_cabang WHERE kode_cabang=? LIMIT 1", (kode,)).fetchone():
        return True
    response = (
        supabase.table("data_cabang")
        .select("kode_cabang,nama_cabang,resi_prefix,start_seq_json,aturan_prefix,created_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name")
        .eq("kode_cabang", kode)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return False
    _apply_remote_branch(conn, rows[0])
    return conn.execute("SELECT 1 FROM data_cabang WHERE kode_cabang=? LIMIT 1", (kode,)).fetchone() is not None


def _ensure_local_branch_dependency(conn, kode_cabang: str) -> bool:
    """Pastikan parent data_cabang ada sebelum menerapkan tabel yang ber-FK ke cabang.

    Recovery/sync harus tahan terhadap DB lokal yang lebih lama atau snapshot server
    yang datang dalam urutan berbeda. Jangan biarkan FOREIGN KEY menghentikan seluruh
    siklus sync hanya karena parent cabang belum ada.
    """
    return _ensure_local_branch_for_resi(conn, kode_cabang)


def _record_sync_dependency_conflict(
    conn, table_name: str, record_key: str, payload: Dict[str, Any], reason: str
) -> None:
    _record_recovery_conflict(
        conn, table_name, record_key, None, payload, reason
    )


def _record_recovery_conflict(conn, table_name: str, record_key: str, local_payload, remote_payload, reason: str):
    event_key = f"RECOVERY-CONFLICT:{table_name}:{record_key}:{reason}"
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
            json.dumps(local_payload or {}, ensure_ascii=False),
            json.dumps(remote_payload or {}, ensure_ascii=False),
        ),
    )


def _authoritative_allowed_branches() -> set[str]:
    """Cabang yang terlihat oleh sesi online; pruning hanya dilakukan di scope ini."""
    codes = {
        str(item.get("kode_cabang") or "").strip().upper()
        for item in (CURRENT_SESSION.get("allowed_branches") or [])
        if isinstance(item, dict) and str(item.get("kode_cabang") or "").strip()
    }
    current = str(CURRENT_SESSION.get("kode_cabang") or "").strip().upper()
    if current:
        codes.add(current)
    codes.discard("DEV_SYS")
    return codes


def _remote_identity(table_name: str, payload: Dict[str, Any]) -> str:
    if table_name == "data_resi":
        return str(payload.get("no_resi") or "").strip().upper()
    return str(payload.get("sync_id") or "").strip()


def _local_has_pending_or_conflict(conn, table_name: str, record_key: str) -> bool:
    return _has_pending(conn, table_name, record_key) or _has_unresolved_conflict(conn, table_name, record_key)


def _legacy_row_key(table_name: str, payload: Dict[str, Any]) -> str:
    if table_name == "data_resi":
        return str(payload.get("no_resi") or "").strip().upper()
    return str(payload.get("sync_id") or "").strip()


def _normalized_sync_value(value: Any, field: Optional[str] = None) -> Any:
    if value is None or value == "":
        return None
    if field == "rincian_json":
        # SQLite stores this field as JSON text while PostgREST may return a
        # decoded JSON array/object. Compare canonical JSON, not Python types.
        parsed = value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = value.strip()
        if isinstance(parsed, (dict, list)):
            return json.dumps(
                parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        return parsed
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value.strip()
    return value


def _legacy_business_state_matches(
    table_name: str,
    local: Dict[str, Any],
    remote: Dict[str, Any],
    *,
    ignore_updated_by: bool = True,
) -> bool:
    """Compare material fields; optionally require unchanged updater metadata."""
    ignored = {"created_at", "updated_at"}
    if ignore_updated_by:
        ignored.update({
            "updated_by_user_id", "updated_by_username", "updated_by_name",
        })
    fields = SYNC_COLUMNS.get(table_name, set()) - ignored
    return all(
        _normalized_sync_value(local.get(field), field)
        == _normalized_sync_value(remote.get(field), field)
        for field in fields
    )


def _legacy_business_identity(table_name: str, payload: Dict[str, Any]) -> tuple:
    if table_name in {"master_penerima", "master_pengirim"}:
        return (
            str(payload.get("kode_cabang") or "").strip().upper(),
            str(payload.get("nama") or "").strip().casefold(),
        )
    if table_name == "truk":
        return (
            str(payload.get("kode_cabang") or "").strip().upper(),
            str(payload.get("no_polisi") or "").strip().upper(),
        )
    if table_name == "kapal":
        return (str(payload.get("nama_kapal") or "").strip().casefold(),)
    if table_name == "buku_gudang":
        return (str(payload.get("id_gudang") or "").strip().upper(),)
    if table_name == "data_resi":
        return (str(payload.get("no_resi") or "").strip().upper(),)
    if table_name == "manifest":
        return (str(payload.get("kode_cabang") or "").strip().upper(),
                str(payload.get("id_manifest") or "").strip().upper())
    return ()


def _repair_unqueued_local_sync_rows(
    conn, remote_rows_by_table: Dict[str, list[Dict[str, Any]]]
) -> Dict[str, int]:
    """Recover dirty local rows missed by legacy outbox triggers before pruning.

    A row is only requeued when its local ``is_synced`` marker says it is dirty
    and it has no existing PENDING/CONFLICT protection. A matching server row is
    compared by business fields and timestamps first, so rows downloaded by older
    code are marked synced instead of being blindly pushed back to Supabase.
    """
    stats = {"queued": 0, "marked_synced": 0, "conflicts": 0}
    eligible = (
        "data_resi", "buku_gudang", "master_penerima", "master_pengirim", "truk", "kapal", "manifest",
    )

    for table_name in eligible:
        remote_rows = remote_rows_by_table.get(table_name)
        if remote_rows is None or table_name not in SYNC_COLUMNS:
            continue
        local_columns = [
            str(row[1]).strip()
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        ]
        if "is_synced" not in local_columns or "sync_id" not in local_columns:
            continue

        key_column = "no_resi" if table_name == "data_resi" else "sync_id"
        if key_column not in local_columns:
            continue

        remote_by_key = {}
        remote_by_business = {}
        for remote in remote_rows:
            key = _legacy_row_key(table_name, remote)
            if key:
                remote_by_key[key] = remote
            business_key = _legacy_business_identity(table_name, remote)
            if business_key and all(business_key):
                remote_by_business[business_key] = remote

        query_columns = list(dict.fromkeys(local_columns))
        quoted = ", ".join(f'"{column}"' for column in query_columns)
        local_rows = conn.execute(
            f"SELECT {quoted} FROM {table_name} WHERE COALESCE(is_synced, 0) = 0"
        ).fetchall()
        allowed_branches = _authoritative_allowed_branches()

        for raw_row in local_rows:
            if not _row_in_authoritative_scope(
                conn, table_name, raw_row, query_columns, allowed_branches
            ):
                continue
            local = dict(zip(query_columns, raw_row))
            record_key = _legacy_row_key(table_name, local)
            sync_id = str(local.get("sync_id") or "").strip()
            if not record_key:
                continue
            if _local_has_pending_or_conflict(conn, table_name, record_key):
                continue
            if not sync_id:
                # Resi is reconciled by no_resi, so a legacy row missing sync_id
                # would otherwise still be eligible for deletion. Preserve it for
                # explicit repair instead of silently losing its business data.
                if table_name == "data_resi":
                    _record_recovery_conflict(
                        conn, table_name, record_key, local,
                        remote_by_key.get(record_key), "LEGACY_SYNC_ID_MISSING",
                    )
                    stats["conflicts"] += 1
                continue

            remote = remote_by_key.get(record_key)
            if remote is None and table_name != "data_resi":
                business_key = _legacy_business_identity(table_name, local)
                candidate = remote_by_business.get(business_key) if business_key and all(business_key) else None
                if candidate is not None:
                    remote_sid = str(candidate.get("sync_id") or "").strip()
                    if remote_sid != sync_id:
                        _record_recovery_conflict(
                            conn, table_name, record_key, local, candidate,
                            "BUSINESS_IDENTITY_COLLISION",
                        )
                        stats["conflicts"] += 1
                        continue
                    remote = candidate

            # Older local caches can miss immutable metadata even when the row
            # already exists remotely. Fill only empty local fields; never replace
            # a non-empty creator identity with the currently logged-in user.
            if remote is not None:
                metadata_updates = {}
                for field in (
                    "created_at", "created_by_user_id", "created_by_username", "created_by_name",
                ):
                    if local.get(field) in (None, "") and remote.get(field) not in (None, ""):
                        local[field] = remote[field]
                        if field in local_columns:
                            metadata_updates[field] = remote[field]
                if metadata_updates:
                    assignments = ", ".join(f'"{field}" = ?' for field in metadata_updates)
                    conn.execute(
                        f"UPDATE {table_name} SET {assignments} WHERE {key_column} = ?",
                        tuple(metadata_updates.values()) + (record_key,),
                    )

            local_updated = _parse_dt(local.get("updated_at"))
            remote_updated = _parse_dt(remote.get("updated_at")) if remote else None
            local_deleted = bool(local.get("deleted_at"))
            remote_deleted = bool(remote and remote.get("deleted_at"))

            operation = None
            if remote is None:
                # Old v16 clients did not reliably mark rows downloaded from the
                # server as synced. Therefore an unqueued dirty row missing from
                # the current snapshot is ambiguous: it may be an offline insert,
                # or a stale cache entry for a row deleted in Supabase. Never
                # resurrect/delete that row automatically without provenance.
                if local_deleted:
                    conn.execute(
                        f"UPDATE {table_name} SET is_synced = 1 WHERE {key_column} = ?",
                        (record_key,),
                    )
                    stats["marked_synced"] += 1
                    continue

                previous = conn.execute(
                    """
                    SELECT payload_json
                    FROM sync_outbox
                    WHERE table_name = ? AND record_key = ? AND status = 'SYNCED'
                    ORDER BY id DESC LIMIT 1
                    """,
                    (table_name, record_key),
                ).fetchone()
                previous_payload = {}
                if previous:
                    try:
                        previous_payload = json.loads(previous[0] or "{}")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        previous_payload = {}

                previous_updated = _parse_dt(previous_payload.get("updated_at"))
                local_updated = _parse_dt(local.get("updated_at"))
                previous_state_unchanged = (
                    bool(previous_payload)
                    and _legacy_business_state_matches(
                        table_name, local, previous_payload, ignore_updated_by=False
                    )
                    and local_updated is not None
                    and previous_updated is not None
                    and local_updated <= previous_updated
                )
                if previous_state_unchanged:
                    # Only allow authoritative pruning when outbox history proves
                    # that the row was synced before and neither its material data,
                    # updater metadata, nor updated_at indicates a later local edit.
                    conn.execute(
                        f"UPDATE {table_name} SET is_synced = 1 WHERE {key_column} = ?",
                        (record_key,),
                    )
                    stats["marked_synced"] += 1
                    continue

                reason = (
                    "LOCAL_EDIT_AFTER_LAST_SYNC_SERVER_MISSING"
                    if previous_payload else "LEGACY_LOCAL_ROW_ABSENT_SERVER"
                )
                _record_recovery_conflict(
                    conn, table_name, record_key, local, previous_payload, reason
                )
                stats["conflicts"] += 1
                continue
            elif local_deleted and remote_deleted:
                conn.execute(
                    f"UPDATE {table_name} SET is_synced = 1 WHERE {key_column} = ?",
                    (record_key,),
                )
                stats["marked_synced"] += 1
                continue
            elif remote_deleted and not local_deleted:
                # Avoid silently resurrecting a record deleted remotely. A newer
                # local edit must be resolved explicitly; otherwise server wins.
                if local_updated is not None and remote_updated is not None and local_updated > remote_updated:
                    _record_recovery_conflict(
                        conn, table_name, record_key, local, remote,
                        "REMOTE_DELETE_LOCAL_EDIT",
                    )
                    stats["conflicts"] += 1
                    continue
                conn.execute(
                    f"UPDATE {table_name} SET is_synced = 1 WHERE {key_column} = ?",
                    (record_key,),
                )
                stats["marked_synced"] += 1
                continue
            elif local_deleted and not remote_deleted:
                if remote_updated is not None and (local_updated is None or remote_updated > local_updated):
                    _record_recovery_conflict(
                        conn, table_name, record_key, local, remote,
                        "REMOTE_UPDATE_LOCAL_DELETE",
                    )
                    stats["conflicts"] += 1
                    continue
                operation = "DELETE"
            elif _legacy_business_state_matches(table_name, local, remote):
                conn.execute(
                    f"UPDATE {table_name} SET is_synced = 1 WHERE {key_column} = ?",
                    (record_key,),
                )
                stats["marked_synced"] += 1
                continue
            elif local_updated is not None and remote_updated is not None and remote_updated > local_updated:
                # Server has a strictly later business snapshot; let the normal
                # pull apply it instead of sending stale local values back.
                conn.execute(
                    f"UPDATE {table_name} SET is_synced = 1 WHERE {key_column} = ?",
                    (record_key,),
                )
                stats["marked_synced"] += 1
                continue
            else:
                operation = "UPDATE"

            payload = {
                field: local.get(field)
                for field in SYNC_COLUMNS[table_name]
                if field in local
            }
            if remote is not None:
                for field in (
                    "created_at", "created_by_user_id", "created_by_username", "created_by_name",
                ):
                    if payload.get(field) in (None, "") and remote.get(field) not in (None, ""):
                        payload[field] = remote[field]
            if table_name == "data_resi":
                payload["no_resi"] = record_key
            payload["sync_id"] = sync_id
            conn.execute(
                """
                INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    table_name,
                    record_key,
                    operation,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            stats["queued"] += 1

    return stats


def _delete_local_by_server_absence(conn, table_name: str, record_key: str) -> None:
    """Hapus cache lokal row yang sudah hilang/terhapus di server."""
    if table_name == "data_resi":
        _delete_local_resi(conn, record_key)
        return
    key_col = {
        "data_resi_detail": "sync_id",
        "cabang_wilayah": "sync_id",
        "numbering_settings": "sync_id",
        "numbering_counters": "sync_id",
        "master_penerima": "sync_id",
        "master_pengirim": "sync_id",
        "truk": "sync_id",
        "kapal": "sync_id",
        "buku_gudang": "sync_id",
        "manifest": "sync_id",
    }.get(table_name)
    if key_col:
        conn.execute(f"DELETE FROM {table_name} WHERE {key_col}=?", (record_key,))


def _row_in_authoritative_scope(conn, table_name: str, row: tuple, columns: list[str], allowed_branches: set[str]) -> bool:
    """True bila row lokal berada di cabang yang memang terlihat user."""
    if not allowed_branches:
        return False
    data = dict(zip(columns, row))
    if table_name == "data_resi_detail":
        no_resi = str(data.get("no_resi") or "").strip().upper()
        if not no_resi:
            return False
        parent = conn.execute(
            "SELECT kode_cabang FROM data_resi WHERE no_resi=? LIMIT 1", (no_resi,)
        ).fetchone()
        return bool(parent and str(parent[0] or "").strip().upper() in allowed_branches)
    if table_name == "kapal":
        return True
    branch = str(data.get("kode_cabang") or "").strip().upper()
    return branch in allowed_branches


def _reconcile_authoritative_table(conn, table_name: str, remote_rows: list[dict[str, Any]]) -> dict[str, int]:
    """Mirror snapshot server ke cache lokal tanpa membuang perubahan offline."""
    result = {"deleted": 0, "protected": 0}
    remote_live = set()
    remote_deleted = set()
    for payload in remote_rows:
        key = _remote_identity(table_name, payload)
        if not key:
            continue
        if payload.get("deleted_at"):
            remote_deleted.add(key)
        else:
            remote_live.add(key)

    for key in remote_deleted:
        if not _local_has_pending_or_conflict(conn, table_name, key):
            before = conn.total_changes
            _delete_local_by_server_absence(conn, table_name, key)
            if conn.total_changes > before:
                result["deleted"] += 1

    columns = [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    key_column = "no_resi" if table_name == "data_resi" else "sync_id"
    if key_column not in columns:
        return result

    rows = conn.execute(f"SELECT {', '.join(columns)} FROM {table_name}").fetchall()
    allowed_branches = _authoritative_allowed_branches()
    for row in rows:
        data = dict(zip(columns, row))
        raw_key = str(data.get(key_column) or "").strip()
        key = raw_key.upper() if key_column == "no_resi" else raw_key
        if not key or key in remote_live or key in remote_deleted:
            continue
        if not _row_in_authoritative_scope(conn, table_name, row, columns, allowed_branches):
            continue
        if _local_has_pending_or_conflict(conn, table_name, key):
            result["protected"] += 1
            continue
        _delete_local_by_server_absence(conn, table_name, key)
        result["deleted"] += 1
    return result


def _authoritative_reconcile_operational_snapshot(conn) -> dict[str, int]:
    """Reconcile full operational snapshot agar hard-delete Supabase ikut lokal."""
    resi_rows = _fetch_all("data_resi", page_size=500)
    detail_rows = _fetch_all("data_resi_detail", page_size=500)
    buku_rows = _fetch_all(
        "buku_gudang",
        columns="id_gudang,kode_cabang,tanggal,no_resi,jenis,status_resi,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=500,
    )

    totals = {"resi": 0, "details": 0, "buku_gudang": 0, "deleted": 0, "protected": 0}
    _set_suppress(conn, True)
    try:
        repaired = _repair_unqueued_local_sync_rows(conn, {
            "data_resi": resi_rows,
            "buku_gudang": buku_rows,
        })
        if repaired["queued"] or repaired["conflicts"]:
            logger.warning(
                "[SYNC] Pemulihan outbox legacy operasional: queued=%s, marked_synced=%s, conflicts=%s",
                repaired["queued"], repaired["marked_synced"], repaired["conflicts"],
            )
        for payload in resi_rows:
            key = _remote_identity("data_resi", payload)
            if not key:
                continue
            if payload.get("deleted_at"):
                if not _local_has_pending_or_conflict(conn, "data_resi", key):
                    _delete_local_resi(conn, key)
                    totals["deleted"] += 1
                else:
                    totals["protected"] += 1
                continue
            if _local_has_pending_or_conflict(conn, "data_resi", key):
                totals["protected"] += 1
                continue
            if _ensure_local_branch_for_resi(conn, str(payload.get("kode_cabang") or "")):
                _apply_remote_resi(conn, payload)
                totals["resi"] += 1

        for payload in detail_rows:
            key = _remote_identity("data_resi_detail", payload)
            if not key:
                continue
            if payload.get("deleted_at"):
                if not _local_has_pending_or_conflict(conn, "data_resi_detail", key):
                    _delete_local_by_server_absence(conn, "data_resi_detail", key)
                    totals["deleted"] += 1
                else:
                    totals["protected"] += 1
                continue
            if _local_has_pending_or_conflict(conn, "data_resi_detail", key):
                totals["protected"] += 1
                continue
            no_resi = str(payload.get("no_resi") or "").strip().upper()
            if no_resi and conn.execute(
                "SELECT 1 FROM data_resi WHERE no_resi=? LIMIT 1", (no_resi,)
            ).fetchone():
                _apply_remote_detail(conn, payload, "UPSERT")
                totals["details"] += 1

        for payload in buku_rows:
            key = _remote_identity("buku_gudang", payload)
            if not key:
                continue
            if payload.get("deleted_at"):
                if not _local_has_pending_or_conflict(conn, "buku_gudang", key):
                    _delete_local_by_server_absence(conn, "buku_gudang", key)
                    totals["deleted"] += 1
                else:
                    totals["protected"] += 1
                continue
            if _local_has_pending_or_conflict(conn, "buku_gudang", key):
                totals["protected"] += 1
                continue
            no_resi = str(payload.get("no_resi") or "").strip().upper()
            if no_resi and not conn.execute(
                "SELECT 1 FROM data_resi WHERE no_resi=? LIMIT 1", (no_resi,)
            ).fetchone():
                continue
            if _apply_remote_buku_gudang(conn, payload, force=True):
                totals["buku_gudang"] += 1

        for table_name, rows in (
            ("data_resi", resi_rows),
            ("data_resi_detail", detail_rows),
            ("buku_gudang", buku_rows),
        ):
            pruned = _reconcile_authoritative_table(conn, table_name, rows)
            totals["deleted"] += pruned["deleted"]
            totals["protected"] += pruned["protected"]
        return totals
    finally:
        _set_suppress(conn, False)


def _reconcile_recovery_resi(conn, payload: Dict[str, Any]) -> str:
    """Merge snapshot Resi tanpa menimpa data lokal yang identitasnya berbeda."""
    no_resi = str(payload.get("no_resi") or "").strip().upper()
    sync_id = str(payload.get("sync_id") or "").strip()
    if not no_resi or not sync_id:
        return "SKIP"

    local_by_sync = conn.execute(
        "SELECT no_resi, sync_id, updated_at FROM data_resi WHERE sync_id=? LIMIT 1",
        (sync_id,),
    ).fetchone()
    if local_by_sync:
        if _has_pending(conn, "data_resi", no_resi) or _has_unresolved_conflict(conn, "data_resi", no_resi):
            return "PENDING"
        local_dt = _parse_dt(local_by_sync[2])
        remote_dt = _parse_dt(payload.get("updated_at"))
        if remote_dt is None or local_dt is None or remote_dt > local_dt:
            _ensure_local_branch_for_resi(conn, str(payload.get("kode_cabang") or ""))
            _apply_remote_resi(conn, payload)
            return "UPDATED"
        return "UNCHANGED"

    local_by_no = conn.execute(
        "SELECT sync_id FROM data_resi WHERE no_resi=? LIMIT 1",
        (no_resi,),
    ).fetchone()
    if local_by_no:
        local_payload = _local_row_json(conn, "data_resi", "no_resi=?", (no_resi,))
        if _has_pending(conn, "data_resi", no_resi) or _has_unresolved_conflict(conn, "data_resi", no_resi):
            reason = "LOCAL_PENDING"
        else:
            reason = "DIFFERENT_SYNC_ID"
        _record_recovery_conflict(conn, "data_resi", no_resi, local_payload, payload, reason)
        return "CONFLICT"

    if payload.get("deleted_at"):
        return "SKIP"

    if not _ensure_local_branch_for_resi(conn, str(payload.get("kode_cabang") or "")):
        _record_recovery_conflict(
            conn, "data_resi", no_resi, None, payload, "MISSING_BRANCH"
        )
        return "CONFLICT"

    _apply_remote_resi(conn, payload)
    return "INSERTED"


def _reconcile_recovery_detail(conn, payload: Dict[str, Any]) -> str:
    """Merge snapshot detail setelah parent Resi tersedia; tahan collision slot."""
    sync_id = str(payload.get("sync_id") or "").strip()
    no_resi = str(payload.get("no_resi") or "").strip().upper()
    urutan = _to_int(payload.get("urutan"), 1)
    if not sync_id or not no_resi:
        return "SKIP"

    # Bila parent sendiri sedang conflict, jangan memasukkan child remote ke
    # parent lokal yang identitasnya berbeda. Tahan child sampai conflict parent
    # diselesaikan.
    if _has_unresolved_conflict(conn, "data_resi", no_resi):
        _record_recovery_conflict(
            conn, "data_resi_detail", sync_id, None, payload, "PARENT_CONFLICT"
        )
        return "CONFLICT"

    # Parent wajib ada terlebih dahulu. Ambil dari server bila DB recovery belum memilikinya.
    parent = conn.execute("SELECT 1 FROM data_resi WHERE no_resi=? LIMIT 1", (no_resi,)).fetchone()
    if not parent:
        response = (
            supabase.table("data_resi")
            .select("*")
            .eq("no_resi", no_resi)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if rows:
            parent_payload = rows[0]
            if not _ensure_local_branch_for_resi(conn, str(parent_payload.get("kode_cabang") or "")):
                _record_recovery_conflict(conn, "data_resi_detail", sync_id, None, payload, "MISSING_BRANCH")
                return "CONFLICT"
            _apply_remote_resi(conn, parent_payload)
        else:
            # Parent sudah tidak ada di server; jangan memaksakan orphan FK lokal.
            _record_recovery_conflict(conn, "data_resi_detail", sync_id, None, payload, "MISSING_PARENT")
            return "CONFLICT"

    existing = conn.execute(
        "SELECT id_detail, no_resi, urutan, updated_at FROM data_resi_detail WHERE sync_id=? LIMIT 1",
        (sync_id,),
    ).fetchone()
    if existing:
        if _has_pending(conn, "data_resi_detail", sync_id) or _has_unresolved_conflict(conn, "data_resi_detail", sync_id):
            return "PENDING"
        local_dt = _parse_dt(existing[3])
        remote_dt = _parse_dt(payload.get("updated_at"))
        if remote_dt is None or local_dt is None or remote_dt > local_dt:
            _apply_remote_detail(conn, payload, "UPSERT")
            return "UPDATED"
        return "UNCHANGED"

    slot = conn.execute(
        "SELECT sync_id FROM data_resi_detail WHERE no_resi=? AND urutan=? LIMIT 1",
        (no_resi, urutan),
    ).fetchone()
    if slot:
        local_payload = _local_row_json(
            conn,
            "data_resi_detail",
            "no_resi=? AND urutan=?",
            (no_resi, urutan),
        )
        _record_recovery_conflict(
            conn, "data_resi_detail", sync_id, local_payload, payload, "SLOT_TAKEN"
        )
        return "CONFLICT"

    if payload.get("deleted_at"):
        return "SKIP"

    _apply_remote_detail(conn, payload, "UPSERT")
    return "INSERTED"


def _reconcile_existing_db_snapshot(conn) -> Dict[str, int]:
    """Bootstrap DB lama memakai snapshot server authoritative + offline-safe."""
    # Ambil watermark SEBELUM membaca snapshot tabel. Jika ada perubahan server
    # selama snapshot berlangsung, event-nya harus tetap berada di atas cursor
    # agar ditangkap oleh pull incremental berikutnya.
    baseline_id = _snapshot_change_id()
    generic = sync_generic_masters()
    operational = _authoritative_reconcile_operational_snapshot(conn)
    return {
        "resi": int(operational.get("resi", 0)),
        "details": int(operational.get("details", 0)),
        "conflicts": 0,
        "skipped": 0,
        "buku_gudang": int(operational.get("buku_gudang", 0)),
        "deleted": int(operational.get("deleted", 0)),
        "protected": int(operational.get("protected", 0)),
        "baseline_id": int(baseline_id),
        "generic": generic,
    }


def initial_sync() -> Dict[str, int]:
    """Isi SQLite baru dari snapshot Supabase sebelum incremental sync dimulai."""
    if not _session_ready():
        return {"branches": 0, "wilayah": 0, "cabang_wilayah": 0, "numbering": 0, "master_penerima": 0, "master_pengirim": 0, "truk": 0, "kapal": 0, "buku_gudang": 0, "manifest": 0, "resi": 0, "details": 0}

    conn = _connect()
    try:
        if _bootstrap_state(conn) == "1":
            return {"branches": 0, "wilayah": 0, "cabang_wilayah": 0, "numbering": 0, "master_penerima": 0, "master_pengirim": 0, "truk": 0, "kapal": 0, "buku_gudang": 0, "manifest": 0, "resi": 0, "details": 0}

        if not _local_is_safe_for_initial_sync(conn):
            # DB lama/non-kosong kini disamakan dengan snapshot server terkini.
            # Row yang hilang di server ikut dihapus lokal, sedangkan perubahan
            # offline PENDING/CONFLICT tetap dilindungi agar offline-first tidak
            # kehilangan pekerjaan yang belum terkirim.
            recovery = _reconcile_existing_db_snapshot(conn)
            # Nilai 0 adalah watermark valid bila sync_changes masih kosong;
            # jangan mengambil watermark baru setelah snapshot hanya karena 0 falsy.
            baseline_raw = recovery.get("baseline_id")
            baseline_id = int(baseline_raw) if baseline_raw is not None else _snapshot_change_id()
            _set_state(conn, "initial_sync_done", "1")
            _set_state(conn, "last_server_change_id", str(baseline_id))
            _set_state(conn, "initial_sync_mode", "AUTHORITATIVE_SNAPSHOT")
            _set_state(conn, "recovery_snapshot_at", _utc_now())
            conn.commit()
            logger.warning(
                "[SYNC] Authoritative snapshot diterapkan pada DB lokal lama "
                "(resi=%s, detail=%s, buku=%s, deleted=%s, protected=%s); "
                "incremental dimulai dari change_id=%s.",
                recovery.get("resi", 0),
                recovery.get("details", 0),
                recovery.get("buku_gudang", 0),
                recovery.get("deleted", 0),
                recovery.get("protected", 0),
                baseline_id,
            )
            return {
                "branches": 0,
                "wilayah": 0,
                "cabang_wilayah": 0,
                "numbering": 0,
                "resi": int(recovery.get("resi", 0)),
                "details": int(recovery.get("details", 0)),
            }

    finally:
        conn.close()

    # _connect() sudah menjamin schema Buku Gudang siap. Validasi eksplisit
    # tetap dipertahankan di titik sebelum snapshot sebagai guard tambahan.
    conn = _connect()
    conn.close()

    # Ambil posisi perubahan sebelum snapshot data. Perubahan yang terjadi
    # selama bootstrap akan ditarik pada incremental sync berikutnya.
    snapshot_id = _snapshot_change_id()

    branches = _fetch_all(
        "data_cabang",
        columns="kode_cabang,nama_cabang,resi_prefix,start_seq_json,aturan_prefix,created_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name",
        page_size=250,
    )
    cabang_wilayah_rows = _fetch_all(
        "cabang_wilayah",
        columns=(
            "kode_cabang,kode_wilayah,prefix_resi,aktif,sync_id,"
            "created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,"
            "updated_by_user_id,updated_by_username,updated_by_name"
        ),
        page_size=500,
    )
    numbering_rows = _fetch_all("numbering_settings", columns="kode_cabang,document_type,format_template,starting_count,current_count,padding,reset_rule,aktif,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name", page_size=500)
    penerima_rows = _fetch_all("master_penerima", columns="id_penerima,kode_cabang,nama,no_hp,alamat,kota,provinsi,total_transaksi,pembayaran,status_tagihan,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name", page_size=500)
    pengirim_rows = _fetch_all("master_pengirim", columns="id_pengirim,kode_cabang,nama,no_hp,alamat,kota,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name", page_size=500)
    truk_rows = _fetch_all("truk", columns="kode_cabang,jenis_truk,no_polisi,nama_sopir,hp_sopir,ket_truk,foto_truk,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name", page_size=500)
    kapal_rows = _fetch_all("kapal", columns="nama_kapal,tujuan,ket_kapal,foto_kapal,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name", page_size=500)
    buku_gudang_rows = _fetch_all("buku_gudang", columns="id_gudang,kode_cabang,tanggal,no_resi,jenis,status_resi,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name", page_size=500)
    manifest_rows = _fetch_all("manifest", columns="id_manifest,kode_cabang,tanggal,no_polisi,nama_sopir,nama_kapal,note_manifest,status_manifest,sync_id,created_at,updated_at,deleted_at,created_by_user_id,created_by_username,created_by_name,updated_by_user_id,updated_by_username,updated_by_name", page_size=500)
    resi_rows = _fetch_all("data_resi", page_size=500)
    detail_rows = _fetch_all("data_resi_detail", page_size=500)

    conn = _connect()
    _ensure_buku_gudang_local_schema(conn)
    applied_branches = applied_cabang_wilayah = 0
    applied_numbering = 0
    applied_master_penerima = applied_master_pengirim = 0
    applied_truk = applied_kapal = applied_buku_gudang = applied_manifest = 0
    applied_resi = applied_details = 0
    try:
        _set_suppress(conn, True)

        for payload in branches:
            _apply_remote_branch(conn, payload)
            applied_branches += 1

        # master_wilayah adalah master lokal fixed; hanya tarik relasi prefix cabang.
        for payload in cabang_wilayah_rows:
            if _apply_remote_cabang_wilayah(conn, payload, force=True):
                applied_cabang_wilayah += 1

        for payload in numbering_rows:
            if _apply_remote_numbering(conn, payload, force=True):
                applied_numbering += 1

        for payload in penerima_rows:
            if _apply_remote_master_penerima(conn, payload, force=True):
                applied_master_penerima += 1
        for payload in pengirim_rows:
            if _apply_remote_master_pengirim(conn, payload, force=True):
                applied_master_pengirim += 1
        for payload in truk_rows:
            if _apply_remote_truk(conn, payload, force=True):
                applied_truk += 1
        for payload in kapal_rows:
            if _apply_remote_kapal(conn, payload, force=True):
                applied_kapal += 1

        for payload in manifest_rows:
            if payload.get("deleted_at"):
                continue
            if _apply_remote_manifest(conn, payload, force=True):
                applied_manifest += 1

        # Buku Gudang bergantung pada Resi, jadi parent Resi dipasang lebih dulu.
        for payload in resi_rows:
            if payload.get("deleted_at"):
                continue
            _apply_remote_resi(conn, payload)
            applied_resi += 1

        for payload in buku_gudang_rows:
            if payload.get("deleted_at"):
                continue
            if _apply_remote_buku_gudang(conn, payload, force=True):
                applied_buku_gudang += 1

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
            "cabang_wilayah": applied_cabang_wilayah,
            "numbering": applied_numbering,
            "master_penerima": applied_master_penerima,
            "master_pengirim": applied_master_pengirim,
            "truk": applied_truk,
            "kapal": applied_kapal,
            "buku_gudang": applied_buku_gudang,
            "manifest": applied_manifest,
            "resi": applied_resi,
            "details": applied_details,
        }
    except Exception:
        _set_suppress(conn, False)
        conn.rollback()
        raise
    finally:
        conn.close()

def _preflight_repair_legacy_outbox() -> Dict[str, int]:
    eligible = (
        "data_resi", "buku_gudang", "master_penerima", "master_pengirim", "truk", "kapal", "manifest",
    )
    candidate_tables = []
    conn = _connect()
    try:
        allowed_branches = _authoritative_allowed_branches()
        for table_name in eligible:
            columns = [
                str(row[1]).strip()
                for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            ]
            if "is_synced" not in columns or "sync_id" not in columns:
                continue
            key_column = "no_resi" if table_name == "data_resi" else "sync_id"
            if key_column not in columns:
                continue
            quoted = ", ".join(f'"{column}"' for column in columns)
            rows = conn.execute(
                f"SELECT {quoted} FROM {table_name} WHERE COALESCE(is_synced, 0) = 0"
            ).fetchall()
            for raw_row in rows:
                if not _row_in_authoritative_scope(
                    conn, table_name, raw_row, columns, allowed_branches
                ):
                    continue
                local = dict(zip(columns, raw_row))
                key = _legacy_row_key(table_name, local)
                if key and not _local_has_pending_or_conflict(conn, table_name, key):
                    candidate_tables.append(table_name)
                    break
    finally:
        conn.close()

    candidate_tables = list(dict.fromkeys(candidate_tables))
    if not candidate_tables:
        return {"queued": 0, "marked_synced": 0, "conflicts": 0}

    remote_rows = {}
    for table_name in candidate_tables:
        columns = ",".join(sorted(SYNC_COLUMNS[table_name]))
        remote_rows[table_name] = _fetch_all(
            table_name, columns=columns, page_size=500
        )

    conn = _connect()
    try:
        _set_suppress(conn, True)
        try:
            stats = _repair_unqueued_local_sync_rows(conn, remote_rows)
            _set_suppress(conn, False)
            conn.commit()
        except Exception:
            _set_suppress(conn, False)
            conn.rollback()
            raise
        if stats["queued"] or stats["conflicts"]:
            logger.warning(
                "[SYNC] Pemulihan outbox legacy: queued=%s, marked_synced=%s, conflicts=%s, tables=%s",
                stats["queued"], stats["marked_synced"], stats["conflicts"],
                ",".join(candidate_tables),
            )
        return stats
    finally:
        conn.close()


def sync_once() -> Dict[str, int]:
    if not _ensure_online_session():
        return {"pushed": 0, "pulled": 0}

    try:

        try:
            _preflight_repair_legacy_outbox()
        except Exception as exc:
            if _is_offline_network_error(exc):
                raise SyncOfflineError(str(exc)) from exc
            raise RuntimeError(
                f"legacy_outbox_preflight: {type(exc).__name__}: {exc}"
            ) from exc

        bootstrap = initial_sync()

        try:
            pushed = push_pending()
        except Exception as exc:
            if _is_offline_network_error(exc):
                raise SyncOfflineError(str(exc)) from exc
            raise RuntimeError(f"push_pending: {type(exc).__name__}: {exc}") from exc

        try:
            branches = sync_all_branches()
        except Exception as exc:
            if _is_offline_network_error(exc):
                raise SyncOfflineError(str(exc)) from exc
            raise RuntimeError(f"sync_all_branches: {type(exc).__name__}: {exc}") from exc
        try:
            wilayah = sync_cabang_wilayah()
        except Exception as exc:
            if _is_offline_network_error(exc):
                raise SyncOfflineError(str(exc)) from exc
            raise RuntimeError(f"sync_cabang_wilayah: {type(exc).__name__}: {exc}") from exc
        try:
            generic = sync_generic_masters()
        except Exception as exc:
            if _is_offline_network_error(exc):
                raise SyncOfflineError(str(exc)) from exc
            raise RuntimeError(f"sync_generic_masters: {type(exc).__name__}: {exc}") from exc

        try:
            pulled = pull_server_changes()
        except Exception as exc:
            if _is_offline_network_error(exc):
                raise SyncOfflineError(str(exc)) from exc
            raise RuntimeError(f"pull_server_changes: {type(exc).__name__}: {exc}") from exc

        try:
            conn = _connect()
            try:
                operational_snapshot = _authoritative_reconcile_operational_snapshot(conn)
                _set_state(conn, "authoritative_sync_at", _utc_now())
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            if _is_offline_network_error(exc):
                raise SyncOfflineError(str(exc)) from exc
            raise RuntimeError(f"authoritative_reconcile: {type(exc).__name__}: {exc}") from exc
    except SyncOfflineError:
        raise
    except Exception as exc:
        if _is_offline_network_error(exc):
            raise SyncOfflineError(str(exc)) from exc
        raise

    return {
        "pushed": pushed,
        "pulled": pulled,
        "authoritative_deleted": int(operational_snapshot.get("deleted", 0)),
        "authoritative_protected": int(operational_snapshot.get("protected", 0)),
        "initial_resi": int(bootstrap.get("resi", 0)),
        "initial_details": int(bootstrap.get("details", 0)),
        "branches": int(branches),
        "cabang_wilayah": int(wilayah.get("cabang_wilayah", 0)),
        "numbering": int(generic.get("numbering", 0)),
        "numbering_counters": int(generic.get("numbering_counters", 0)),
        "master_penerima": int(generic.get("master_penerima", 0)),
        "master_pengirim": int(generic.get("master_pengirim", 0)),
        "truk": int(generic.get("truk", 0)),
        "kapal": int(generic.get("kapal", 0)),
        "buku_gudang": int(generic.get("buku_gudang", 0)),
        "manifest": int(generic.get("manifest", 0)),
    }


class AutoSyncController:
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
        self._offline_logged = False

        self.timer.start()
        self._start_worker()

    def _run_worker(self):
        try:
            result = sync_once()
            self._offline_logged = False
            print(f"[SYNC] {result}", flush=True)
        except SyncOfflineError:
            if not self._offline_logged:
                print(
                    "[SYNC] Offline — perubahan disimpan lokal, akan disinkronkan saat online.",
                    flush=True,
                )
                self._offline_logged = True
        except Exception as exc:
            print(f"[SYNC] Gagal: {type(exc).__name__}: {exc}", flush=True)
        finally:
            try:
                self._worker_lock.release()
            except RuntimeError:
                pass
            self._worker_thread = None

    def _start_worker(self):
        if self._stopping:
            return

        # Lock memastikan hanya satu sync berjalan pada satu waktu.
        if not self._worker_lock.acquire(blocking=False):
            return

        if not _ensure_online_session():
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

    def is_running(self) -> bool:
        worker = self._worker_thread
        return bool(worker is not None and worker.is_alive())

    def stop(self, *, wait: bool = False, timeout: float = 5.0):
        self._stopping = True
        self.timer.stop()

        worker = self._worker_thread
        if wait and worker is not None and worker.is_alive():
            worker.join(timeout=max(0.0, float(timeout)))

        if worker is None or not worker.is_alive():
            self._worker_thread = None