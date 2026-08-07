# seed_initial_db_mahkota.py
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from database_manager import init_db

try:
    from config import db_aktif
except ImportError:
    db_aktif = "database_cargo.db"

BASE_DIR = Path(__file__).resolve().parent

PENGATURAN_AWAL = (
    ("nama_perusahaan", "PT MAHKOTA KARGO LOGISTIK"),
    ("alamat_perusahaan", "Jl. Sidotopo Lor No. 71 - Surabaya"),
    ("telp_perusahaan", "031-37302708"),
    ("logo_text_html", "MAHKOTA KARGO"),
    ("rekening_pajak", ["BCA, 829 257 2980, PT MAHKOTA KARGO LOGISTIK"]),
    (
        "rekening_nonpajak",
        [
            "MANDIRI, 141 001 991 2963, REGGY ANITA RIANDA",
            "BCA, 187 064 1628, REGGY ANITA RIANDA",
        ],
    ),
    ("format_resi_manual", False),
    ("template_no_resi", "[PREFIX][COUNTER][SUFFIX]"),
    ("kode_akhiran_pajak", "-P"),
    ("prefix_invoice", "INV-MKT"),
    (
        "provinsi_tujuan",
        ["KALIMANTAN TIMUR", "KALIMANTAN SELATAN", "PROVINSI LAINNYA"],
    ),
)

CABANG_AWAL = (
    {
        "kode_cabang": "SBY",
        "nama_cabang": "SURABAYA (PUSAT)",
        "resi_prefix": "MKT",
        "start_seq": {"KT": 18000, "KS": 5000, "DEFAULT": 1000},
        "aturan_prefix": {
            "KALIMANTAN TIMUR": "KT",
            "KALIMANTAN SELATAN": "KS",
            "DEFAULT": "IND",
        },
    },
    {
        "kode_cabang": "JKT",
        "nama_cabang": "JAKARTA (CABANG)",
        "resi_prefix": "MKTJ",
        "start_seq": {"J-KT": 8000, "J-KS": 4000, "DEFAULT": 1000},
        "aturan_prefix": {
            "KALIMANTAN TIMUR": "J-KT",
            "KALIMANTAN SELATAN": "J-KS",
            "DEFAULT": "J-IND",
        },
    },
)

USERS_AWAL = (
    {
        "id_user": "USR-SUPER",
        "username": "SUPER",
        "password": "123",
        "role": "SUPER_ADMIN",
        "nama_lengkap": "OWNER MAHKOTA",
        "kode_cabang": "SBY",
    },
    {
        "id_user": "USR-SBY",
        "username": "ADMINSBY",
        "password": "123",
        "role": "ADMIN",
        "nama_lengkap": "STAFF SBY",
        "kode_cabang": "SBY",
    },
    {
        "id_user": "USR-JKT",
        "username": "ADMINJKT",
        "password": "123",
        "role": "ADMIN",
        "nama_lengkap": "STAFF JKT",
        "kode_cabang": "JKT",
    },
)


def _normalisasi_path_database(path_value: Optional[str] = None) -> Path:
    raw_path = str(path_value or db_aktif or "database_cargo.db").strip()
    database_path = Path(raw_path)
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path
    return database_path.resolve()


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    return cursor.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone() is not None


def _table_columns(
    cursor: sqlite3.Cursor,
    table_name: str,
) -> Dict[str, Dict[str, Any]]:
    rows = cursor.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return {
        row[1]: {
            "type": str(row[2] or "").upper(),
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": bool(row[5]),
        }
        for row in rows
    }


def _insert_row_adaptif(
    cursor: sqlite3.Cursor,
    table_name: str,
    data: Dict[str, Any],
    *,
    replace: bool = False,
) -> None:
    columns = _table_columns(cursor, table_name)
    filtered_data = {key: value for key, value in data.items() if key in columns}
    if not filtered_data:
        raise RuntimeError(
            f"Tidak ada kolom seed yang cocok dengan tabel '{table_name}'."
        )

    column_names = list(filtered_data)
    placeholders = ", ".join("?" for _ in column_names)
    quoted_columns = ", ".join(f'"{column}"' for column in column_names)
    command = "INSERT OR REPLACE" if replace else "INSERT"
    cursor.execute(
        f'{command} INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})',
        tuple(filtered_data[column] for column in column_names),
    )


def _serialize_seed_value(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)


def _upsert_pengaturan(
    cursor: sqlite3.Cursor,
    settings: Iterable[Tuple[str, Any]],
) -> None:
    if not _table_exists(cursor, "pengaturan_sistem"):
        raise RuntimeError(
            "Tabel pengaturan_sistem belum dibuat oleh database_manager.py."
        )

    columns = _table_columns(cursor, "pengaturan_sistem")
    if "kunci" not in columns or "nilai" not in columns:
        raise RuntimeError(
            "Schema pengaturan_sistem harus memiliki kolom kunci dan nilai."
        )

    cursor.executemany(
        "INSERT OR REPLACE INTO pengaturan_sistem (kunci, nilai) VALUES (?, ?)",
        [(str(key), _serialize_seed_value(value)) for key, value in settings],
    )


def _seed_pengaturan(cursor: sqlite3.Cursor) -> None:
    _upsert_pengaturan(cursor, PENGATURAN_AWAL)


def _seed_cabang(cursor: sqlite3.Cursor) -> None:
    if not _table_exists(cursor, "data_cabang"):
        raise RuntimeError(
            "Tabel data_cabang belum dibuat oleh database_manager.py."
        )

    for cabang in CABANG_AWAL:
        _insert_row_adaptif(
            cursor,
            "data_cabang",
            {
                "kode_cabang": cabang["kode_cabang"],
                "nama_cabang": cabang["nama_cabang"],
                "resi_prefix": cabang["resi_prefix"],
                "start_seq_json": json.dumps(cabang["start_seq"], ensure_ascii=False),
                "aturan_prefix": json.dumps(
                    cabang["aturan_prefix"],
                    ensure_ascii=False,
                ),
            },
            replace=True,
        )


def _seed_users(cursor: sqlite3.Cursor) -> None:
    if not _table_exists(cursor, "manajemen_user"):
        raise RuntimeError(
            "Tabel manajemen_user belum dibuat oleh database_manager.py."
        )

    id_user_column = _table_columns(cursor, "manajemen_user").get("id_user")
    include_id_user = bool(id_user_column and "INT" not in id_user_column["type"])

    for user in USERS_AWAL:
        data = dict(user)
        if not include_id_user:
            data.pop("id_user", None)
        _insert_row_adaptif(cursor, "manajemen_user", data, replace=True)


def _seed_data_awal(cursor: sqlite3.Cursor) -> None:
    _seed_pengaturan(cursor)
    _seed_cabang(cursor)
    _seed_users(cursor)


def _cetak_seed_sudah_ada(database_path: Path) -> None:
    print(f"ℹ️ Database '{database_path.name}' sudah tersedia.")
    print("Seed dibatalkan agar data yang ada tidak tertimpa.")
    print(
        "Hapus atau ganti nama database tersebut secara manual "
        "jika memang ingin membuat database awal baru."
    )


def _cetak_seed_sukses(database_path: Path) -> None:
    print("")
    print("✅ DATABASE AWAL MAHKOTA BERHASIL DIBUAT")
    print(f"📍 Lokasi: {database_path}")
    print("")
    print("Akun awal database:")
    print("  SUPER    / 123")
    print("  ADMINSBY / 123")
    print("  ADMINJKT / 123")
    print("")
    print(
        "Akun DEV_SUPER tetap dibaca dari app_env.json, "
        "bukan dari seed database."
    )
    print("")
    print(
        "Catatan: database ini adalah data awal/testing, "
        "bukan klaim bahwa integrasi Supabase sudah selesai."
    )


def _bersihkan_database_gagal(database_path: Path, database_created: bool) -> None:
    if not database_created or not database_path.exists():
        return
    try:
        database_path.unlink()
        print("ℹ️ File database awal yang gagal dibuat telah dibersihkan.")
    except OSError as cleanup_error:
        print(f"⚠️ Database gagal dibersihkan otomatis: {cleanup_error}")


def generate_mahkota_environment(
    db_path: Optional[str] = None,
) -> bool:
    database_path = _normalisasi_path_database(db_path)
    if database_path.exists():
        _cetak_seed_sudah_ada(database_path)
        return False

    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_created = False
    try:
        print(f"📁 Membuat schema database: {database_path}")
        init_db(str(database_path))
        database_created = database_path.exists()
        if not database_created:
            raise RuntimeError(
                "database_manager.init_db() tidak menghasilkan file database."
            )

        with sqlite3.connect(str(database_path), timeout=30.0) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            _seed_data_awal(conn.cursor())
            conn.commit()

        _cetak_seed_sukses(database_path)
        return True
    except Exception as exc:
        print(f"❌ Seed database gagal: {exc}")
        _bersihkan_database_gagal(database_path, database_created)
        return False


if __name__ == "__main__":
    generate_mahkota_environment()