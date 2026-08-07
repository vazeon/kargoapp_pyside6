# database_manager.py
import json
import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_NAME = "database_cargo.db"

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS pengaturan_sistem (
        kunci TEXT PRIMARY KEY,
        nilai TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_cabang (
        kode_cabang TEXT PRIMARY KEY,
        nama_cabang TEXT NOT NULL,
        resi_prefix TEXT NOT NULL,
        start_seq_json TEXT DEFAULT '{"DEFAULT": 1000}',
        aturan_prefix TEXT DEFAULT '{"DEFAULT": "INV"}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS manajemen_user (
        id_user TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'ADMIN',
        nama_lengkap TEXT,
        kode_cabang TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_resi (
        no_resi TEXT PRIMARY KEY,
        kode_cabang TEXT NOT NULL,
        tanggal_masuk DATE,
        tanggal_keluar DATE,
        pengirim TEXT,
        hp_pengirim TEXT,
        alamat_pengirim TEXT,
        kota_asal TEXT,
        penerima TEXT,
        hp_penerima TEXT,
        alamat_penerima TEXT,
        kota_tujuan TEXT,
        nama_barang TEXT,
        koli TEXT,
        berat REAL,
        cbm REAL,
        ongkir_per_kg INTEGER,
        ongkir_per_cbm INTEGER,
        total_ongkir INTEGER,
        pembayaran TEXT,
        status_resi TEXT,
        foto_bukti TEXT,
        truk TEXT,
        ket_buku_gudang TEXT,
        no_manifest TEXT,
        ket_manifest TEXT,
        rincian_json TEXT,
        is_synced INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
    )
    """,
    """
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
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang),
        FOREIGN KEY (no_resi)
            REFERENCES data_resi (no_resi)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS manifest (
        id_manifest TEXT PRIMARY KEY,
        kode_cabang TEXT NOT NULL,
        tanggal DATE,
        no_polisi TEXT,
        nama_sopir TEXT,
        nama_kapal TEXT,
        note_manifest TEXT,
        status_manifest TEXT,
        is_synced INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invoice_header (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_invoice TEXT UNIQUE NOT NULL,
        tanggal TEXT NOT NULL,
        client TEXT NOT NULL,
        tipe_invoice TEXT NOT NULL,
        jenis_pajak TEXT NOT NULL,
        subtotal INTEGER NOT NULL DEFAULT 0,
        total_akhir INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        template_version INTEGER NOT NULL DEFAULT 1,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invoice_detail (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_invoice TEXT NOT NULL,
        nomor_urut INTEGER NOT NULL,
        data_kolom TEXT NOT NULL,
        nominal_subtotal INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (no_invoice)
            REFERENCES invoice_header (no_invoice)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS master_pengirim (
        id_pengirim TEXT PRIMARY KEY,
        kode_cabang TEXT NOT NULL,
        nama TEXT,
        no_hp TEXT,
        alamat TEXT,
        kota TEXT,
        is_synced INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS master_penerima (
        id_penerima TEXT PRIMARY KEY,
        kode_cabang TEXT NOT NULL,
        nama TEXT,
        no_hp TEXT,
        alamat TEXT,
        kota TEXT,
        provinsi TEXT,
        total_transaksi INTEGER DEFAULT 0,
        pembayaran TEXT DEFAULT 'TF / INVOICE',
        status_tagihan TEXT DEFAULT 'NORMAL',
        is_synced INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS truk (
        kode_cabang TEXT NOT NULL,
        jenis_truk TEXT NOT NULL,
        no_polisi TEXT NOT NULL,
        nama_sopir TEXT,
        hp_sopir TEXT,
        ket_truk TEXT,
        foto_truk TEXT,
        is_synced INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (kode_cabang, no_polisi),
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
            ON UPDATE CASCADE
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kapal (
        nama_kapal TEXT PRIMARY KEY,
        tujuan TEXT,
        ket_kapal TEXT,
        foto_kapal TEXT,
        is_synced INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


def _resolve_db_path(db_name: str = DEFAULT_DB_NAME) -> str:
    """Mengubah nama/path database menjadi path absolut."""
    db_path = Path(str(db_name or DEFAULT_DB_NAME).strip())
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path.resolve())


def _pastikan_migrasi_manifest(cursor) -> None:
    """Menambahkan kolom Manifest yang tidak dibuat oleh IF NOT EXISTS."""
    kolom_manifest = {
        str(row[1])
        for row in cursor.execute("PRAGMA table_info(manifest)").fetchall()
    }
    if "note_manifest" not in kolom_manifest:
        cursor.execute("ALTER TABLE manifest ADD COLUMN note_manifest TEXT")


def init_db(db_name: str = DEFAULT_DB_NAME) -> str:
    """
    Membuat seluruh struktur database aplikasi.

    Fungsi ini hanya membuat tabel dan tidak memasukkan data demo.
    Data demo dimasukkan melalui seed_demo_db_mahkota.py.
    """
    db_path = _resolve_db_path(db_name)
    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()
            for statement in _SCHEMA_STATEMENTS:
                cursor.execute(statement)
            _pastikan_migrasi_manifest(cursor)
            conn.commit()
        print(f"✅ Database berhasil dibuat/diperiksa: {db_path}")
        return db_path
    except sqlite3.Error as exc:
        raise RuntimeError(f"Gagal membuat struktur database: {exc}") from exc


def _serialize_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)


def set_config(
    db_name: str,
    key: str,
    value: Any,
) -> None:
    """Menyimpan satu pengaturan sistem."""
    db_path = _resolve_db_path(db_name)
    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pengaturan_sistem (
                    kunci,
                    nilai
                )
                VALUES (?, ?)
                """,
                (str(key), _serialize_config_value(value)),
            )
            conn.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(f"Gagal menyimpan pengaturan '{key}': {exc}") from exc


if __name__ == "__main__":
    init_db()