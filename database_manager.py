# database_manager.py
import json
import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_NAME = "database_cargo.db"
DB_SCHEMA_VERSION = 4

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
        status_user TEXT NOT NULL DEFAULT 'AKTIF',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_cabang_access (
        id_user TEXT NOT NULL,
        kode_cabang TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id_user, kode_cabang),
        FOREIGN KEY (id_user)
            REFERENCES manajemen_user (id_user)
            ON DELETE CASCADE,
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
            ON UPDATE CASCADE
            ON DELETE CASCADE
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
        subtotal_ongkir INTEGER DEFAULT 0,
        jenis_pajak TEXT DEFAULT 'NONPAJAK',
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
        revision INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resi_audit (
        id_audit INTEGER PRIMARY KEY AUTOINCREMENT,
        kode_cabang TEXT NOT NULL,
        no_resi_lama TEXT NOT NULL,
        no_resi_baru TEXT NOT NULL,
        username TEXT NOT NULL DEFAULT 'SYSTEM',
        sumber TEXT NOT NULL,
        revision_sebelum INTEGER,
        revision_sesudah INTEGER,
        perubahan_json TEXT NOT NULL DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_resi_audit_nomor_lama
    ON resi_audit (no_resi_lama, kode_cabang, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_resi_audit_nomor_baru
    ON resi_audit (no_resi_baru, kode_cabang, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS data_resi_detail (
        id_detail INTEGER PRIMARY KEY AUTOINCREMENT,
        no_resi TEXT NOT NULL,
        urutan INTEGER NOT NULL,
        nama_barang TEXT,
        koli TEXT,
        berat REAL DEFAULT 0,
        cbm REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (no_resi, urutan),
        FOREIGN KEY (no_resi)
            REFERENCES data_resi (no_resi)
            ON UPDATE CASCADE
            ON DELETE CASCADE
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
    CREATE TABLE IF NOT EXISTS invoice_resi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_invoice TEXT NOT NULL,
        no_resi TEXT NOT NULL,
        kode_cabang TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (no_invoice, no_resi),
        FOREIGN KEY (no_invoice)
            REFERENCES invoice_header (no_invoice)
            ON DELETE CASCADE,
        FOREIGN KEY (kode_cabang)
            REFERENCES data_cabang (kode_cabang)
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

# Index tambahan yang mengikuti pola query aktual aplikasi.
# Dikelola sebagai migration agar database existing mendapat index yang sama
# tanpa perlu reset atau kehilangan data.
_PERFORMANCE_INDEX_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS idx_data_resi_cabang_tanggal_masuk
    ON data_resi (kode_cabang, tanggal_masuk)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_data_resi_cabang_manifest_tanggal_keluar
    ON data_resi (kode_cabang, no_manifest, tanggal_keluar)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_invoice_detail_invoice_urut
    ON invoice_detail (no_invoice, nomor_urut)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_master_pengirim_cabang_nama
    ON master_pengirim (kode_cabang, nama COLLATE NOCASE)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_master_penerima_cabang_nama
    ON master_penerima (kode_cabang, nama COLLATE NOCASE)
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


def _ambil_schema_version(cursor) -> int:
    """Membaca versi schema SQLite yang tersimpan pada PRAGMA user_version."""
    row = cursor.execute("PRAGMA user_version").fetchone()
    try:
        return int(row[0]) if row else 0
    except (TypeError, ValueError):
        return 0


def _set_schema_version(cursor, version: int) -> None:
    """Menyimpan versi schema setelah satu migration berhasil."""
    version = int(version)
    if version < 0:
        raise ValueError("Versi schema tidak boleh negatif.")
    cursor.execute(f"PRAGMA user_version = {version}")


def _migration_v1(cursor) -> None:
    """Baseline schema versioning + index performa untuk query utama aplikasi."""
    _pastikan_migrasi_manifest(cursor)
    for statement in _PERFORMANCE_INDEX_STATEMENTS:
        cursor.execute(statement)


def _ambil_nomor_resi_snapshot_invoice(value):
    """Ambil nomor Resi eksplisit dari snapshot JSON detail Invoice."""
    hasil = set()

    def walk(node):
        if isinstance(node, dict):
            for key, val in node.items():
                key_norm = str(key or "").strip().casefold()
                if key_norm in {"resi", "no_resi", "nomor_resi"} and not isinstance(
                    val, (dict, list, tuple)
                ):
                    nomor = str(val if val is not None else "").strip().upper()
                    if nomor:
                        hasil.add(nomor)
                walk(val)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(value)
    return hasil


def _varian_resi_migrasi(nomor, suffix_pajak):
    """Bentuk varian sederhana untuk mencocokkan nomor Resi legacy PAJAK/NONPAJAK."""
    nomor = str(nomor or "").strip().upper()
    suffix = str(suffix_pajak or "-P").strip().upper()
    if not nomor:
        return ()
    hasil = [nomor]
    if suffix:
        if nomor.endswith(suffix):
            dasar = nomor[:-len(suffix)].rstrip()
            if dasar:
                hasil.append(dasar)
        else:
            hasil.append(f"{nomor}{suffix}")
    return tuple(dict.fromkeys(hasil))


def _backfill_invoice_resi(cursor) -> None:
    """Bangun relasi Invoice-Resi dari snapshot invoice existing tanpa mengubah snapshot."""
    resi_rows = cursor.execute(
        "SELECT no_resi, kode_cabang FROM data_resi"
    ).fetchall()
    peta_resi = {
        str(no_resi or "").strip().upper(): (
            str(no_resi or "").strip().upper(),
            str(kode_cabang or "").strip().upper() or None,
        )
        for no_resi, kode_cabang in resi_rows
        if str(no_resi or "").strip()
    }

    setting = cursor.execute(
        "SELECT nilai FROM pengaturan_sistem WHERE kunci = ? LIMIT 1",
        ("kode_akhiran_pajak",),
    ).fetchone()
    suffix_pajak = str(
        setting[0] if setting and setting[0] is not None else "-P"
    ).strip().upper()

    rows = cursor.execute(
        """
        SELECT no_invoice, data_kolom
        FROM invoice_detail
        ORDER BY no_invoice, nomor_urut
        """
    ).fetchall()

    relasi = set()
    for no_invoice, raw in rows:
        invoice = str(no_invoice or "").strip().upper()
        if not invoice or raw in (None, ""):
            continue
        try:
            parsed = json.loads(str(raw))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

        for snapshot in _ambil_nomor_resi_snapshot_invoice(parsed):
            nomor_aktif = snapshot
            kode_cabang = None
            for kandidat in _varian_resi_migrasi(snapshot, suffix_pajak):
                data_aktif = peta_resi.get(kandidat)
                if data_aktif:
                    nomor_aktif, kode_cabang = data_aktif
                    break
            relasi.add((invoice, nomor_aktif, kode_cabang))

    if relasi:
        cursor.executemany(
            """
            INSERT OR IGNORE INTO invoice_resi (
                no_invoice, no_resi, kode_cabang
            ) VALUES (?, ?, ?)
            """,
            sorted(relasi),
        )


def _migration_v2(cursor) -> None:
    """Relasi Invoice-Resi untuk Billing Queue dan status tanpa scan JSON penuh."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_resi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            no_invoice TEXT NOT NULL,
            no_resi TEXT NOT NULL,
            kode_cabang TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (no_invoice, no_resi),
            FOREIGN KEY (no_invoice)
                REFERENCES invoice_header (no_invoice)
                ON DELETE CASCADE,
            FOREIGN KEY (kode_cabang)
                REFERENCES data_cabang (kode_cabang)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_invoice_resi_no_resi
        ON invoice_resi (no_resi COLLATE NOCASE)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_invoice_resi_invoice
        ON invoice_resi (no_invoice)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_data_resi_billing_queue
        ON data_resi (kode_cabang, tanggal_masuk, no_resi)
        """
    )
    _backfill_invoice_resi(cursor)


def _migration_v3(cursor) -> None:
    """Hak akses multi-cabang per user; home branch selalu menjadi akses minimum."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_cabang_access (
            id_user TEXT NOT NULL,
            kode_cabang TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id_user, kode_cabang),
            FOREIGN KEY (id_user)
                REFERENCES manajemen_user (id_user)
                ON DELETE CASCADE,
            FOREIGN KEY (kode_cabang)
                REFERENCES data_cabang (kode_cabang)
                ON UPDATE CASCADE
                ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_cabang_access_cabang
        ON user_cabang_access (kode_cabang, id_user)
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO user_cabang_access (id_user, kode_cabang)
        SELECT id_user, kode_cabang
        FROM manajemen_user
        WHERE TRIM(COALESCE(id_user, '')) != ''
          AND TRIM(COALESCE(kode_cabang, '')) != ''
        """
    )


def _migration_v4(cursor) -> None:
    """Status akun untuk manajemen user tanpa menghapus histori user lama."""
    columns = {
        str(row[1]).strip().lower()
        for row in cursor.execute("PRAGMA table_info(manajemen_user)").fetchall()
    }
    if "status_user" not in columns:
        cursor.execute(
            "ALTER TABLE manajemen_user "
            "ADD COLUMN status_user TEXT NOT NULL DEFAULT 'AKTIF'"
        )

    cursor.execute(
        """
        UPDATE manajemen_user
        SET status_user = 'AKTIF'
        WHERE TRIM(COALESCE(status_user, '')) = ''
           OR UPPER(TRIM(status_user)) NOT IN ('AKTIF', 'NONAKTIF')
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_manajemen_user_status_role
        ON manajemen_user (status_user, role, username COLLATE NOCASE)
        """
    )


_SCHEMA_MIGRATIONS = {
    1: _migration_v1,
    2: _migration_v2,
    3: _migration_v3,
    4: _migration_v4,
}


def _jalankan_migrasi_schema(cursor) -> None:
    """Upgrade schema berurutan tanpa menurunkan database yang lebih baru."""
    versi_sekarang = _ambil_schema_version(cursor)
    if versi_sekarang > DB_SCHEMA_VERSION:
        raise RuntimeError(
            "Versi database lebih baru daripada versi aplikasi "
            f"({versi_sekarang} > {DB_SCHEMA_VERSION}). "
            "Gunakan versi aplikasi yang sesuai agar schema tidak rusak."
        )

    for target_version in range(versi_sekarang + 1, DB_SCHEMA_VERSION + 1):
        migrasi = _SCHEMA_MIGRATIONS.get(target_version)
        if migrasi is None:
            raise RuntimeError(
                f"Migration schema versi {target_version} tidak tersedia."
            )
        migrasi(cursor)
        _set_schema_version(cursor, target_version)


def _pastikan_bootstrap_cabang_minimal(cursor) -> None:
    """
    Menjamin foreign key cabang selalu valid walau aplikasi dijalankan tanpa seed.

    PUSAT adalah cabang default white-label yang dipakai CURRENT_SESSION, sedangkan
    DEV_SYS adalah cabang internal untuk sesi developer. INSERT OR IGNORE sengaja
    digunakan agar konfigurasi cabang yang sudah ada tidak pernah ditimpa.
    """
    cabang_minimal = (
        (
            "PUSAT",
            "KANTOR PUSAT",
            "INV",
            json.dumps({"DEFAULT": 1000}, ensure_ascii=False),
            json.dumps({"DEFAULT": "INV"}, ensure_ascii=False),
        ),
        (
            "DEV_SYS",
            "DEVELOPER SYSTEM",
            "SYS",
            json.dumps({"DEFAULT": 1000}, ensure_ascii=False),
            json.dumps({"DEFAULT": "SYS"}, ensure_ascii=False),
        ),
    )
    cursor.executemany(
        """
        INSERT OR IGNORE INTO data_cabang (
            kode_cabang, nama_cabang, resi_prefix,
            start_seq_json, aturan_prefix
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        cabang_minimal,
    )


def init_db(db_name: str = DEFAULT_DB_NAME) -> str:
    """
    Membuat, memigrasikan, dan memeriksa struktur database aplikasi.

    Seluruh bootstrap schema dan migration dilakukan dalam satu transaksi agar
    perubahan tidak tersisa setengah jalan bila salah satu langkah gagal.
    Data customer, akun contoh, dan branding tetap menjadi tanggung jawab seed opsional.
    """
    db_path = _resolve_db_path(db_name)
    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()

            for statement in _SCHEMA_STATEMENTS:
                cursor.execute(statement)

            _jalankan_migrasi_schema(cursor)
            _pastikan_bootstrap_cabang_minimal(cursor)
            conn.commit()

        print(
            f"✅ Database berhasil dibuat/diperiksa: {db_path} "
            f"(schema v{DB_SCHEMA_VERSION})"
        )
        return db_path
    except (sqlite3.Error, RuntimeError, ValueError) as exc:
        raise RuntimeError(f"Gagal membuat/memigrasikan struktur database: {exc}") from exc

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