# database_manager.py
import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from audit_context import install_sqlite_audit_functions

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_NAME = "database_cargo.db"
DB_SCHEMA_VERSION = 17

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



def _migration_v5(cursor) -> None:
    """Fondasi offline-first: identitas sync, outbox lokal, cursor server, dan trigger."""
    # Tambahkan metadata sinkronisasi tanpa menghapus data lama.
    for table in ("data_resi", "data_resi_detail"):
        columns = {
            str(row[1]).strip().lower()
            for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if "sync_id" not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN sync_id TEXT")
        if "deleted_at" not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT")

        # Record lama mendapat identitas stabil, tetapi sengaja TIDAK dimasukkan
        # ke outbox. Upload massal existing data akan dilakukan pada tahap bootstrap.
        rows = cursor.execute(
            f"SELECT rowid FROM {table} WHERE sync_id IS NULL OR TRIM(sync_id) = ''"
        ).fetchall()
        for (rowid,) in rows:
            cursor.execute(
                f"UPDATE {table} SET sync_id = ? WHERE rowid = ?",
                (str(uuid.uuid4()), rowid),
            )

    cursor.execute(
        """
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
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_outbox_pending
        ON sync_outbox(status, id)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_outbox_record
        ON sync_outbox(table_name, record_key, id)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_state (
            kunci TEXT PRIMARY KEY,
            nilai TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT NOT NULL UNIQUE,
            table_name TEXT NOT NULL,
            record_key TEXT NOT NULL,
            local_payload TEXT,
            remote_payload TEXT,
            detected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'OPEN'
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_control (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            suppress_outbox INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cursor.execute(
        "INSERT OR IGNORE INTO sync_control(id, suppress_outbox) VALUES (1, 0)"
    )
    cursor.execute(
        "INSERT OR IGNORE INTO sync_state(kunci, nilai) VALUES ('last_server_change_id', '0')"
    )
    if not cursor.execute(
        "SELECT 1 FROM sync_state WHERE kunci = 'device_id' LIMIT 1"
    ).fetchone():
        cursor.execute(
            "INSERT INTO sync_state(kunci, nilai) VALUES ('device_id', ?)",
            (str(uuid.uuid4()),),
        )

    # Trigger untuk data_resi. Perubahan housekeeping `is_synced` dan `updated_at`
    # saja tidak membuat antrean baru. Hal ini mencegah loop saat sync engine
    # menandai row lokal sebagai sudah tersinkron.
    payload_new = "json_object(" + ", ".join([
        "'no_resi', NEW.no_resi",
        "'kode_cabang', NEW.kode_cabang",
        "'tanggal_masuk', NEW.tanggal_masuk",
        "'tanggal_keluar', NEW.tanggal_keluar",
        "'pengirim', NEW.pengirim",
        "'hp_pengirim', NEW.hp_pengirim",
        "'alamat_pengirim', NEW.alamat_pengirim",
        "'kota_asal', NEW.kota_asal",
        "'penerima', NEW.penerima",
        "'hp_penerima', NEW.hp_penerima",
        "'alamat_penerima', NEW.alamat_penerima",
        "'kota_tujuan', NEW.kota_tujuan",
        "'nama_barang', NEW.nama_barang",
        "'koli', NEW.koli",
        "'berat', NEW.berat",
        "'cbm', NEW.cbm",
        "'ongkir_per_kg', NEW.ongkir_per_kg",
        "'ongkir_per_cbm', NEW.ongkir_per_cbm",
        "'subtotal_ongkir', NEW.subtotal_ongkir",
        "'jenis_pajak', NEW.jenis_pajak",
        "'total_ongkir', NEW.total_ongkir",
        "'pembayaran', NEW.pembayaran",
        "'status_resi', NEW.status_resi",
        "'foto_bukti', NEW.foto_bukti",
        "'truk', NEW.truk",
        "'ket_buku_gudang', NEW.ket_buku_gudang",
        "'no_manifest', NEW.no_manifest",
        "'ket_manifest', NEW.ket_manifest",
        "'rincian_json', NEW.rincian_json",
        "'revision', NEW.revision",
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

    cursor.execute("DROP TRIGGER IF EXISTS trg_local_data_resi_outbox_insert")
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_outbox_insert
        AFTER INSERT ON data_resi
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi', NEW.no_resi, 'INSERT', {payload_new});
        END
    """)

    update_changed = " OR ".join([
        f"NEW.{c} IS NOT OLD.{c}" for c in (
            "no_resi","kode_cabang","tanggal_masuk","tanggal_keluar","pengirim",
            "hp_pengirim","alamat_pengirim","kota_asal","penerima","hp_penerima",
            "alamat_penerima","kota_tujuan","nama_barang","koli","berat","cbm",
            "ongkir_per_kg","ongkir_per_cbm","subtotal_ongkir","jenis_pajak",
            "total_ongkir","pembayaran","status_resi","foto_bukti","truk",
            "ket_buku_gudang","no_manifest","ket_manifest","rincian_json",
            "revision","sync_id","created_at","deleted_at",
        )
    ])
    cursor.execute("DROP TRIGGER IF EXISTS trg_local_data_resi_outbox_update")
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_outbox_update
        AFTER UPDATE ON data_resi
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
         AND ({update_changed})
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi', NEW.no_resi, 'UPDATE', {payload_new});
        END
    """)

    cursor.execute("DROP TRIGGER IF EXISTS trg_local_data_resi_outbox_delete")
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_outbox_delete
        AFTER DELETE ON data_resi
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi', OLD.no_resi, 'DELETE', {payload_old});
        END
    """)

    # Detail barang ikut disinkronkan karena satu transaksi Resi dapat memiliki
    # banyak baris detail. Identitas lintas perangkat memakai sync_id, bukan id_detail.
    detail_payload_new = "json_object(" + ", ".join([
        "'id_detail', NEW.id_detail",
        "'no_resi', NEW.no_resi",
        "'urutan', NEW.urutan",
        "'nama_barang', NEW.nama_barang",
        "'koli', NEW.koli",
        "'berat', NEW.berat",
        "'cbm', NEW.cbm",
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
    detail_payload_old = detail_payload_new.replace("NEW.", "OLD.")

    cursor.execute("DROP TRIGGER IF EXISTS trg_local_data_resi_detail_outbox_insert")
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_detail_outbox_insert
        AFTER INSERT ON data_resi_detail
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi_detail', COALESCE(NEW.sync_id, CAST(NEW.id_detail AS TEXT)), 'INSERT', {detail_payload_new});
        END
    """)
    detail_changed = " OR ".join([
        f"NEW.{c} IS NOT OLD.{c}" for c in (
            "id_detail","no_resi","urutan","nama_barang","koli","berat","cbm","sync_id","created_at","deleted_at"
        )
    ])
    cursor.execute("DROP TRIGGER IF EXISTS trg_local_data_resi_detail_outbox_update")
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_detail_outbox_update
        AFTER UPDATE ON data_resi_detail
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
         AND ({detail_changed})
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi_detail', COALESCE(NEW.sync_id, CAST(NEW.id_detail AS TEXT)), 'UPDATE', {detail_payload_new});
        END
    """)
    cursor.execute("DROP TRIGGER IF EXISTS trg_local_data_resi_detail_outbox_delete")
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_detail_outbox_delete
        AFTER DELETE ON data_resi_detail
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi_detail', COALESCE(OLD.sync_id, CAST(OLD.id_detail AS TEXT)), 'DELETE', {detail_payload_old});
        END
    """)


def _migration_v6(cursor) -> None:
    """Master wilayah lokal untuk white-label + sinkronisasi Supabase."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS master_wilayah (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode_wilayah TEXT NOT NULL UNIQUE,
            nama_wilayah TEXT NOT NULL,
            tipe_wilayah TEXT NOT NULL DEFAULT 'PROVINSI',
            aktif INTEGER NOT NULL DEFAULT 1,
            urutan INTEGER NOT NULL DEFAULT 0,
            sync_id TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cabang_wilayah (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode_cabang TEXT NOT NULL,
            kode_wilayah TEXT NOT NULL,
            prefix_resi TEXT,
            aktif INTEGER NOT NULL DEFAULT 1,
            sync_id TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            UNIQUE (kode_cabang, kode_wilayah),
            FOREIGN KEY (kode_cabang)
                REFERENCES data_cabang (kode_cabang)
                ON UPDATE CASCADE
                ON DELETE CASCADE,
            FOREIGN KEY (kode_wilayah)
                REFERENCES master_wilayah (kode_wilayah)
                ON UPDATE CASCADE
                ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_master_wilayah_aktif_urutan
        ON master_wilayah (aktif, urutan, nama_wilayah)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cabang_wilayah_cabang
        ON cabang_wilayah (kode_cabang, aktif)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cabang_wilayah_wilayah
        ON cabang_wilayah (kode_wilayah, aktif)
        """
    )

    def normalisasi_nama(value):
        return " ".join(str(value or "").strip().upper().split())

    def kode_default(nama):
        nama = normalisasi_nama(nama)
        alias = {
            "KALIMANTAN TIMUR": "KALTIM",
            "KALIMANTAN SELATAN": "KALSEL",
            "PROVINSI LAINNYA": "LAINNYA",
            "LAINNYA": "LAINNYA",
        }
        if nama in alias:
            return alias[nama]

        alnum = re.sub(r"[^A-Z0-9]+", "", nama)
        if not alnum:
            return ""
        return alnum[:12]

    # Migrasikan daftar lama pengaturan_sistem.provinsi_tujuan ke master_wilayah.
    row = cursor.execute(
        """
        SELECT nilai
        FROM pengaturan_sistem
        WHERE kunci = 'provinsi_tujuan'
        LIMIT 1
        """
    ).fetchone()

    daftar_wilayah = []
    if row and row[0]:
        try:
            parsed = json.loads(str(row[0]))
            if isinstance(parsed, list):
                daftar_wilayah.extend(parsed)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    # Jika setting lama kosong, ambil nama wilayah dari kamus prefix cabang.
    if not daftar_wilayah:
        branch_rows = cursor.execute(
            "SELECT aturan_prefix FROM data_cabang WHERE aturan_prefix IS NOT NULL"
        ).fetchall()
        for (raw_rules,) in branch_rows:
            try:
                rules = json.loads(str(raw_rules or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(rules, dict):
                daftar_wilayah.extend(rules.keys())

    nama_seen = set()
    for index, raw_name in enumerate(daftar_wilayah, start=1):
        nama = normalisasi_nama(raw_name)
        if not nama or nama in nama_seen:
            continue
        nama_seen.add(nama)
        kode = kode_default(nama)
        if not kode:
            continue

        existing = cursor.execute(
            """
            SELECT kode_wilayah
            FROM master_wilayah
            WHERE kode_wilayah = ?
            LIMIT 1
            """,
            (kode,),
        ).fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE master_wilayah
                SET nama_wilayah = ?,
                    aktif = 1,
                    urutan = MIN(urutan, ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE kode_wilayah = ?
                """,
                (nama, index * 10, kode),
            )
        else:
            cursor.execute(
                """
                INSERT INTO master_wilayah (
                    kode_wilayah, nama_wilayah, tipe_wilayah,
                    aktif, urutan, sync_id
                )
                VALUES (?, ?, 'PROVINSI', 1, ?, ?)
                """,
                (kode, nama, index * 10, str(uuid.uuid4())),
            )

    # Migrasikan aturan prefix lama ke cabang_wilayah.
    branch_rows = cursor.execute(
        """
        SELECT kode_cabang, aturan_prefix
        FROM data_cabang
        WHERE TRIM(COALESCE(kode_cabang, '')) != ''
        """
    ).fetchall()

    for kode_cabang, raw_rules in branch_rows:
        kode_cabang = str(kode_cabang or "").strip().upper()
        try:
            rules = json.loads(str(raw_rules or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            rules = {}

        if not isinstance(rules, dict):
            continue

        for raw_name, raw_prefix in rules.items():
            nama = normalisasi_nama(raw_name)
            if not nama or nama == "DEFAULT":
                continue

            kode_wilayah = kode_default(nama)
            if not kode_wilayah:
                continue

            # Pastikan master wilayah ada meskipun nama tersebut hanya muncul
            # pada aturan prefix cabang dan belum ada di provinsi_tujuan.
            if not cursor.execute(
                "SELECT 1 FROM master_wilayah WHERE kode_wilayah = ? LIMIT 1",
                (kode_wilayah,),
            ).fetchone():
                cursor.execute(
                    """
                    INSERT INTO master_wilayah (
                        kode_wilayah, nama_wilayah, tipe_wilayah,
                        aktif, urutan, sync_id
                    )
                    VALUES (?, ?, 'PROVINSI', 1, 999, ?)
                    """,
                    (kode_wilayah, nama, str(uuid.uuid4())),
                )

            cursor.execute(
                """
                INSERT OR IGNORE INTO cabang_wilayah (
                    kode_cabang, kode_wilayah, prefix_resi,
                    aktif, sync_id
                )
                VALUES (?, ?, ?, 1, ?)
                """,
                (
                    kode_cabang,
                    kode_wilayah,
                    str(raw_prefix or "").strip().upper() or None,
                    str(uuid.uuid4()),
                ),
            )



def _migration_v7(cursor) -> None:
    """Fondasi konfigurasi generic: penomoran dokumen + master opsi operasional."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS numbering_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode_cabang TEXT NOT NULL,
            document_type TEXT NOT NULL,
            format_template TEXT NOT NULL,
            starting_count INTEGER NOT NULL DEFAULT 1,
            current_count INTEGER NOT NULL DEFAULT 0,
            padding INTEGER NOT NULL DEFAULT 5,
            reset_rule TEXT NOT NULL DEFAULT 'NONE',
            aktif INTEGER NOT NULL DEFAULT 1,
            sync_id TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            UNIQUE (kode_cabang, document_type),
            FOREIGN KEY (kode_cabang)
                REFERENCES data_cabang (kode_cabang)
                ON UPDATE CASCADE
                ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_numbering_settings_branch_doc
        ON numbering_settings (kode_cabang, document_type, aktif)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS master_option (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            option_group TEXT NOT NULL,
            option_code TEXT NOT NULL,
            option_label TEXT NOT NULL,
            kode_cabang TEXT NOT NULL DEFAULT '*',
            urutan INTEGER NOT NULL DEFAULT 0,
            aktif INTEGER NOT NULL DEFAULT 1,
            sync_id TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            UNIQUE (kode_cabang, option_group, option_code)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_master_option_group
        ON master_option (option_group, kode_cabang, aktif, urutan)
        """
    )

    # Seed default client options sebelum trigger outbox dibuat. Ini hanya
    # bootstrap konfigurasi; perubahan berikutnya dilakukan dari Settings.
    numbering_defaults = {
        "RESI": ("{CABANG}-{WILAYAH}-{SEQ}", 1000, 0, 5, "NONE"),
        "BUKU_GUDANG": ("BG-{CABANG}-{TAHUN}-{SEQ}", 1, 0, 5, "YEARLY"),
        "MANIFEST": ("MAN-{CABANG}-{TAHUN}-{SEQ}", 1, 0, 5, "YEARLY"),
        "INVOICE": ("INV-{CABANG}-{TAHUN}-{SEQ}", 1, 0, 5, "YEARLY"),
    }
    branches = [str(r[0] or '').strip().upper() for r in cursor.execute(
        "SELECT kode_cabang FROM data_cabang WHERE TRIM(COALESCE(kode_cabang,'')) <> ''"
    ).fetchall()]
    for branch in branches:
        for doc_type, values in numbering_defaults.items():
            cursor.execute(
                """
                INSERT OR IGNORE INTO numbering_settings(
                    kode_cabang, document_type, format_template, starting_count,
                    current_count, padding, reset_rule, aktif, sync_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (branch, doc_type, *values, str(uuid.uuid4())),
            )

    option_defaults = [
        ("BUKU_STATUS_GUDANG", "DI GUDANG", "DI GUDANG", 10),
        ("BUKU_STATUS_GUDANG", "PERJALANAN", "PERJALANAN", 20),
        ("BUKU_STATUS_GUDANG", "SELESAI", "SELESAI", 30),
        ("BUKU_STATUS_TAGIHAN", "BELUM INVOICE", "BELUM INVOICE", 10),
        ("BUKU_STATUS_TAGIHAN", "BELUM LUNAS", "BELUM LUNAS", 20),
        ("BUKU_STATUS_TAGIHAN", "LUNAS", "LUNAS", 30),
        ("BUKU_STATUS_TAGIHAN", "MACET", "MACET", 40),
        ("BUKU_METODE_PEMBAYARAN", "TF / INVOICE", "TF / INVOICE", 10),
        ("BUKU_METODE_PEMBAYARAN", "CASH", "CASH", 20),
        ("ARMADA_JENIS_TRUK", "TB", "TB", 10),
        ("ARMADA_JENIS_TRUK", "TRONTON", "Tronton", 20),
        ("ARMADA_JENIS_TRUK", "CDD", "CDD", 30),
        ("ARMADA_JENIS_TRUK", "PICK-UP", "Pick-up", 40),
        ("ARMADA_JENIS_TRUK", "LAINNYA", "Lainnya...", 50),
    ]
    for group, code, label, order in option_defaults:
        cursor.execute(
            """
            INSERT OR IGNORE INTO master_option(
                option_group, option_code, option_label, kode_cabang,
                urutan, aktif, sync_id
            ) VALUES (?, ?, ?, '*', ?, 1, ?)
            """,
            (group, code, label, order, str(uuid.uuid4())),
        )
    destinations = cursor.execute(
        "SELECT DISTINCT TRIM(tujuan) FROM kapal WHERE TRIM(COALESCE(tujuan,'')) <> ''"
    ).fetchall()
    for idx, (destination,) in enumerate(destinations, start=100):
        label = str(destination).strip().upper()
        code = ' '.join(label.split())
        cursor.execute(
            """
            INSERT OR IGNORE INTO master_option(
                option_group, option_code, option_label, kode_cabang,
                urutan, aktif, sync_id
            ) VALUES ('ARMADA_TUJUAN_KAPAL', ?, ?, '*', ?, 1, ?)
            """,
            (code, label, idx, str(uuid.uuid4())),
        )

    # Local outbox triggers. Saat initial/incremental pull berjalan,
    # sync_control.suppress_outbox mencegah loop balik ke server.
    num_payload_new = "json_object(" + ", ".join([
        "'kode_cabang', NEW.kode_cabang",
        "'document_type', NEW.document_type",
        "'format_template', NEW.format_template",
        "'starting_count', NEW.starting_count",
        "'current_count', NEW.current_count",
        "'padding', NEW.padding",
        "'reset_rule', NEW.reset_rule",
        "'aktif', NEW.aktif",
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
    num_payload_old = num_payload_new.replace('NEW.', 'OLD.')
    for name in (
        'trg_local_numbering_insert',
        'trg_local_numbering_update',
        'trg_local_numbering_delete',
    ):
        cursor.execute(f'DROP TRIGGER IF EXISTS {name}')
    cursor.execute(f"""
        CREATE TRIGGER trg_local_numbering_insert
        AFTER INSERT ON numbering_settings
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
          INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
          VALUES('numbering_settings',NEW.sync_id,'INSERT',{num_payload_new});
        END
    """)
    cursor.execute(f"""
        CREATE TRIGGER trg_local_numbering_update
        AFTER UPDATE ON numbering_settings
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
          INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
          VALUES('numbering_settings',NEW.sync_id,'UPDATE',{num_payload_new});
        END
    """)
    cursor.execute(f"""
        CREATE TRIGGER trg_local_numbering_delete
        AFTER DELETE ON numbering_settings
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
          INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
          VALUES('numbering_settings',OLD.sync_id,'DELETE',{num_payload_old});
        END
    """)

    opt_payload_new = "json_object(" + ", ".join([
        "'option_group', NEW.option_group",
        "'option_code', NEW.option_code",
        "'option_label', NEW.option_label",
        "'kode_cabang', NEW.kode_cabang",
        "'urutan', NEW.urutan",
        "'aktif', NEW.aktif",
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
    opt_payload_old = opt_payload_new.replace('NEW.', 'OLD.')
    for name in (
        'trg_local_master_option_insert',
        'trg_local_master_option_update',
        'trg_local_master_option_delete',
    ):
        cursor.execute(f'DROP TRIGGER IF EXISTS {name}')
    cursor.execute(f"""
        CREATE TRIGGER trg_local_master_option_insert
        AFTER INSERT ON master_option
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
          INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
          VALUES('master_option',NEW.sync_id,'INSERT',{opt_payload_new});
        END
    """)
    cursor.execute(f"""
        CREATE TRIGGER trg_local_master_option_update
        AFTER UPDATE ON master_option
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
          INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
          VALUES('master_option',NEW.sync_id,'UPDATE',{opt_payload_new});
        END
    """)
    cursor.execute(f"""
        CREATE TRIGGER trg_local_master_option_delete
        AFTER DELETE ON master_option
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
          INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
          VALUES('master_option',OLD.sync_id,'DELETE',{opt_payload_old});
        END
    """)



def _migration_v8(cursor) -> None:
    """Penomoran fixed: counter terpisah per seri."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS numbering_counters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode_cabang TEXT NOT NULL,
            document_type TEXT NOT NULL,
            series_code TEXT NOT NULL,
            starting_count INTEGER NOT NULL DEFAULT 1,
            current_count INTEGER NOT NULL DEFAULT 0,
            padding INTEGER NOT NULL DEFAULT 5,
            aktif INTEGER NOT NULL DEFAULT 1,
            sync_id TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            UNIQUE (kode_cabang, document_type, series_code),
            FOREIGN KEY (kode_cabang) REFERENCES data_cabang(kode_cabang)
                ON UPDATE CASCADE ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_numbering_counters_lookup
        ON numbering_counters(kode_cabang, document_type, series_code, aktif)
    """)

    def _json(value):
        try:
            return json.loads(value or '{}') if value else {}
        except Exception:
            return {}

    def _branch(code):
        row = cursor.execute(
            'SELECT start_seq_json, aturan_prefix FROM data_cabang WHERE kode_cabang=?',
            (code,),
        ).fetchone()
        if not row:
            return {}, {}
        starts = {str(k).strip().upper(): int(v or 0) for k,v in _json(row[0]).items() if str(k).strip()}
        rules = {str(k).strip().upper(): str(v or '').strip().upper() for k,v in _json(row[1]).items() if str(k).strip()}
        return starts, rules

    def _max_resi(code, prefix):
        rows = cursor.execute(
            'SELECT no_resi FROM data_resi WHERE kode_cabang=? AND no_resi LIKE ?',
            (code, f'{prefix}%'),
        ).fetchall()
        best = 0
        for (raw,) in rows:
            text = str(raw or '').strip().upper()
            if text.startswith(prefix.upper()):
                nums = re.findall(r'\d+', text[len(prefix):])
                if nums:
                    best = max(best, int(nums[-1]))
        return best

    def _max_manifest(code, prefix):
        rows = cursor.execute(
            'SELECT no_manifest FROM data_resi WHERE kode_cabang=? AND no_manifest IS NOT NULL',
            (code,),
        ).fetchall()
        best = 0
        for (raw,) in rows:
            text = str(raw or '').strip().upper()
            if text.startswith(prefix.upper() + '-'):
                m = re.search(r'-(\d+)$', text)
                if m:
                    best = max(best, int(m.group(1)))
        return best

    def _max_invoice():
        rows = cursor.execute('SELECT no_invoice FROM invoice_header').fetchall()
        best = 0
        for (raw,) in rows:
            text = str(raw or '').strip().upper()
            m = re.match(r'^(\d+)/INV/MKT-SUB/\d{2}$', text)
            if m:
                best = max(best, int(m.group(1)))
        return best

    branches = [str(r[0] or '').strip().upper() for r in cursor.execute(
        "SELECT kode_cabang FROM data_cabang WHERE TRIM(COALESCE(kode_cabang,'')) <> ''"
    ).fetchall()]

    def _insert(code, doc, series, start, current, padding):
        cursor.execute("""
            INSERT OR IGNORE INTO numbering_counters(
                kode_cabang, document_type, series_code,
                starting_count, current_count, padding, aktif, sync_id
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, (code, doc, series, int(start), int(current), int(padding), str(uuid.uuid4())))

    for code in branches:
        starts, rules = _branch(code)
        series_list = []
        for key in ('KALIMANTAN TIMUR','KALIMANTAN SELATAN','DEFAULT'):
            val = rules.get(key, '')
            if val and val not in series_list:
                series_list.append(val)
        if not series_list:
            series_list = ['IND']
        for series in series_list:
            start = starts.get(series, starts.get('DEFAULT', 1000))
            _insert(code, 'RESI', series, start, _max_resi(code, series), 5)

        jmark = 'J-' if rules.get('KALIMANTAN TIMUR','').startswith('J-') else ''
        for base in ('MT','MS','MI'):
            _insert(code, 'MANIFEST', f'{jmark}{base}', 1, _max_manifest(code, f'{jmark}{base}'), 4)

        if code == 'SBY':
            _insert(code, 'INVOICE', 'INV', 1, _max_invoice(), 4)


    # Local outbox triggers for fixed-series counters.
    # suppress_outbox prevents pull/bootstrap loops.
    counter_payload_new = "json_object(" + ", ".join([
        "'kode_cabang', NEW.kode_cabang",
        "'document_type', NEW.document_type",
        "'series_code', NEW.series_code",
        "'starting_count', NEW.starting_count",
        "'current_count', NEW.current_count",
        "'padding', NEW.padding",
        "'aktif', NEW.aktif",
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
    counter_payload_old = counter_payload_new.replace('NEW.', 'OLD.')
    for name in (
        'trg_local_numbering_counter_insert',
        'trg_local_numbering_counter_update',
        'trg_local_numbering_counter_delete',
    ):
        cursor.execute(f'DROP TRIGGER IF EXISTS {name}')
    cursor.execute(f"""
        CREATE TRIGGER trg_local_numbering_counter_insert
        AFTER INSERT ON numbering_counters
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
          INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
          VALUES('numbering_counters',NEW.sync_id,'INSERT',{counter_payload_new});
        END
    """)
    cursor.execute(f"""
        CREATE TRIGGER trg_local_numbering_counter_update
        AFTER UPDATE ON numbering_counters
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
          INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
          VALUES('numbering_counters',NEW.sync_id,'UPDATE',{counter_payload_new});
        END
    """)
    cursor.execute(f"""
        CREATE TRIGGER trg_local_numbering_counter_delete
        AFTER DELETE ON numbering_counters
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id=1),0)=0
        BEGIN
          INSERT INTO sync_outbox(table_name,record_key,operation,payload_json)
          VALUES('numbering_counters',OLD.sync_id,'DELETE',{counter_payload_old});
        END
    """)


def _migration_v9(cursor) -> None:
    """Kunci wilayah Mahkota menjadi 3 wilayah tetap.

    master_wilayah tetap merupakan tabel lokal SQLite karena dipakai sebagai
    referensi UI/validasi dan parent untuk cabang_wilayah. Tabel ini tidak lagi
    disinkronkan ke Supabase dan tidak boleh berkembang dari Settings.
    """
    fixed_regions = (
        ("KALTIM", "KALIMANTAN TIMUR", 10),
        ("KALSEL", "KALIMANTAN SELATAN", 20),
        ("LAINNYA", "PROVINSI LAINNYA", 30),
    )
    allowed = tuple(row[0] for row in fixed_regions)
    placeholders = ", ".join("?" for _ in allowed)

    # Hapus relasi wilayah lama terlebih dahulu karena cabang_wilayah
    # mempunyai foreign key ke master_wilayah pada SQLite lokal.
    cursor.execute(
        f"DELETE FROM cabang_wilayah WHERE kode_wilayah NOT IN ({placeholders})",
        allowed,
    )
    cursor.execute(
        f"DELETE FROM master_wilayah WHERE kode_wilayah NOT IN ({placeholders})",
        allowed,
    )

    for kode, nama, urutan in fixed_regions:
        existing = cursor.execute(
            "SELECT sync_id FROM master_wilayah WHERE kode_wilayah = ? LIMIT 1",
            (kode,),
        ).fetchone()
        sync_id = str(existing[0]) if existing and existing[0] else str(uuid.uuid5(uuid.NAMESPACE_URL, f"kargo:mahkota:wilayah:{kode}"))
        cursor.execute(
            """
            INSERT INTO master_wilayah(
                kode_wilayah, nama_wilayah, tipe_wilayah,
                aktif, urutan, sync_id, deleted_at, updated_at
            ) VALUES (?, ?, 'PROVINSI', 1, ?, ?, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(kode_wilayah) DO UPDATE SET
                nama_wilayah = excluded.nama_wilayah,
                tipe_wilayah = excluded.tipe_wilayah,
                aktif = 1,
                urutan = excluded.urutan,
                sync_id = excluded.sync_id,
                deleted_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (kode, nama, urutan, sync_id),
        )

    # Pengaturan tujuan juga dikunci ke tiga wilayah yang sama agar dropdown
    # Resi/Buku Gudang/Kontak tidak dapat kembali menampilkan wilayah tambahan.
    cursor.execute(
        "INSERT OR REPLACE INTO pengaturan_sistem(kunci, nilai) VALUES (?, ?)",
        (
            "provinsi_tujuan",
            json.dumps(
                [
                    "KALIMANTAN TIMUR",
                    "KALIMANTAN SELATAN",
                    "PROVINSI LAINNYA",
                ],
                ensure_ascii=False,
            ),
        ),
    )



def _migration_v10(cursor) -> None:
    """Bersihkan cabang dummy lama TEST/PUSAT pada database Mahkota.

    Hanya dijalankan bila database sudah mengenal SBY dan JKT, sehingga
    migration ini tidak mengubah database white-label/non-Mahkota yang belum
    memiliki struktur cabang Mahkota.
    """
    def table_exists(name: str) -> bool:
        return cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone() is not None

    if not table_exists("data_cabang"):
        return

    rows = cursor.execute(
        "SELECT kode_cabang FROM data_cabang WHERE kode_cabang IN ('SBY','JKT')"
    ).fetchall()
    if len({str(r[0]).strip().upper() for r in rows}) < 2:
        return

    target = ("TEST", "PUSAT")

    # Hapus data turunan terlebih dahulu agar FK SQLite tetap konsisten.
    if table_exists("user_cabang_access"):
        cursor.execute(
            "DELETE FROM user_cabang_access WHERE kode_cabang IN (?, ?)",
            target,
        )
    if table_exists("manajemen_user"):
        cursor.execute(
            "DELETE FROM manajemen_user WHERE kode_cabang IN (?, ?)",
            target,
        )
    if table_exists("data_resi_detail") and table_exists("data_resi"):
        cursor.execute(
            "DELETE FROM data_resi_detail WHERE no_resi IN ("
            "SELECT no_resi FROM data_resi WHERE kode_cabang IN (?, ?)"
            ")",
            target,
        )
    if table_exists("buku_gudang"):
        if table_exists("data_resi"):
            cursor.execute(
                "DELETE FROM buku_gudang WHERE kode_cabang IN (?, ?) "
                "OR no_resi IN (SELECT no_resi FROM data_resi WHERE kode_cabang IN (?, ?))",
                target + target,
            )
        else:
            cursor.execute(
                "DELETE FROM buku_gudang WHERE kode_cabang IN (?, ?)", target
            )
    for table in (
        "manifest",
        "invoice_resi",
        "master_pengirim",
        "master_penerima",
        "truk",
        "cabang_wilayah",
        "numbering_settings",
        "numbering_counters",
        "resi_audit",
    ):
        if table_exists(table):
            cursor.execute(
                f"DELETE FROM {table} WHERE kode_cabang IN (?, ?)",
                target,
            )
    if table_exists("data_resi"):
        cursor.execute(
            "DELETE FROM data_resi WHERE kode_cabang IN (?, ?)", target
        )
    cursor.execute(
        "DELETE FROM data_cabang WHERE kode_cabang IN (?, ?)", target
    )



def _migration_v11(cursor) -> None:
    """Audit identitas pembuat/perubahan untuk seluruh tabel data aplikasi."""
    audit_tables = {
        "data_cabang": ["kode_cabang"],
        "manajemen_user": ["id_user"],
        "user_cabang_access": ["id_user", "kode_cabang"],
        "data_resi": ["no_resi"],
        "data_resi_detail": ["id_detail"],
        "buku_gudang": ["id_gudang"],
        "manifest": ["id_manifest"],
        "invoice_header": ["id"],
        "invoice_detail": ["id"],
        "invoice_resi": ["id"],
        "master_pengirim": ["id_pengirim"],
        "master_penerima": ["id_penerima"],
        "truk": ["kode_cabang", "no_polisi"],
        "kapal": ["nama_kapal"],
        "master_wilayah": ["id"],
        "cabang_wilayah": ["id"],
        "numbering_settings": ["id"],
        "numbering_counters": ["id"],
        "master_option": ["id"],
        "resi_audit": ["id_audit"],
    }

    audit_columns = (
        "created_by_user_id",
        "created_by_username",
        "created_by_name",
        "updated_by_user_id",
        "updated_by_username",
        "updated_by_name",
    )

    def table_exists(table):
        return cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone() is not None

    def columns(table):
        return {
            str(row[1]).strip()
            for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
        }

    for table, keys in audit_tables.items():
        if not table_exists(table):
            continue
        existing = columns(table)
        for column in audit_columns:
            if column not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")

        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_created_by_user "
            f"ON {table}(created_by_user_id)"
        )

        quoted_table = table.replace('"', '""')

        trigger_insert = f"trg_local_audit_{table}_insert"
        cursor.execute(f"DROP TRIGGER IF EXISTS {trigger_insert}")
        where_insert = " AND ".join(f"{key}=NEW.{key}" for key in keys)
        cursor.execute(
            f"""
            CREATE TRIGGER {trigger_insert}
            AFTER INSERT ON {quoted_table}
            WHEN mkt_audit_is_sync() = 0
            BEGIN
                UPDATE {quoted_table}
                SET created_by_user_id = COALESCE(created_by_user_id, mkt_audit_user_id()),
                    created_by_username = COALESCE(NULLIF(created_by_username, ''), mkt_audit_username()),
                    created_by_name = COALESCE(NULLIF(created_by_name, ''), mkt_audit_name()),
                    updated_by_user_id = COALESCE(updated_by_user_id, mkt_audit_user_id()),
                    updated_by_username = COALESCE(NULLIF(updated_by_username, ''), mkt_audit_username()),
                    updated_by_name = COALESCE(NULLIF(updated_by_name, ''), mkt_audit_name())
                WHERE {where_insert};
            END
            """
        )

        all_columns = columns(table)
        business_columns = [
            c for c in sorted(all_columns)
            if c not in set(audit_columns)
            and c not in {"updated_at", "created_at"}
        ]
        trigger_update = f"trg_local_audit_{table}_update"
        cursor.execute(f"DROP TRIGGER IF EXISTS {trigger_update}")
        if business_columns:
            update_of = ", ".join(business_columns)
            where_update = " AND ".join(f"{key}=NEW.{key}" for key in keys)
            cursor.execute(
                f"""
                CREATE TRIGGER {trigger_update}
                AFTER UPDATE OF {update_of} ON {quoted_table}
                WHEN mkt_audit_is_sync() = 0
                BEGIN
                    UPDATE {quoted_table}
                    SET updated_by_user_id = mkt_audit_user_id(),
                        updated_by_username = mkt_audit_username(),
                        updated_by_name = mkt_audit_name()
                    WHERE {where_update};
                END
                """
            )


def _migration_v12(cursor) -> None:
    """Perbaiki snapshot actor pada sync_outbox untuk Resi dan detail.

    Outbox dibuat di trigger SQLite. Trigger harus membawa identitas pembuat
    dari ROW lokal saat perubahan terjadi, bukan mengandalkan user yang sedang
    login ketika antrean akhirnya dikirim ke Supabase.
    """
    # --- data_resi ---------------------------------------------------------
    payload_insert = "json_object(" + ", ".join([
        "'no_resi', NEW.no_resi",
        "'kode_cabang', NEW.kode_cabang",
        "'tanggal_masuk', NEW.tanggal_masuk",
        "'tanggal_keluar', NEW.tanggal_keluar",
        "'pengirim', NEW.pengirim",
        "'hp_pengirim', NEW.hp_pengirim",
        "'alamat_pengirim', NEW.alamat_pengirim",
        "'kota_asal', NEW.kota_asal",
        "'penerima', NEW.penerima",
        "'hp_penerima', NEW.hp_penerima",
        "'alamat_penerima', NEW.alamat_penerima",
        "'kota_tujuan', NEW.kota_tujuan",
        "'nama_barang', NEW.nama_barang",
        "'koli', NEW.koli",
        "'berat', NEW.berat",
        "'cbm', NEW.cbm",
        "'ongkir_per_kg', NEW.ongkir_per_kg",
        "'ongkir_per_cbm', NEW.ongkir_per_cbm",
        "'subtotal_ongkir', NEW.subtotal_ongkir",
        "'jenis_pajak', NEW.jenis_pajak",
        "'total_ongkir', NEW.total_ongkir",
        "'pembayaran', NEW.pembayaran",
        "'status_resi', NEW.status_resi",
        "'foto_bukti', NEW.foto_bukti",
        "'truk', NEW.truk",
        "'ket_buku_gudang', NEW.ket_buku_gudang",
        "'no_manifest', NEW.no_manifest",
        "'ket_manifest', NEW.ket_manifest",
        "'rincian_json', NEW.rincian_json",
        "'revision', NEW.revision",
        "'sync_id', NEW.sync_id",
        "'created_at', NEW.created_at",
        "'updated_at', NEW.updated_at",
        "'deleted_at', NEW.deleted_at",
        "'created_by_user_id', COALESCE(NEW.created_by_user_id, mkt_audit_user_id())",
        "'created_by_username', COALESCE(NULLIF(NEW.created_by_username, ''), mkt_audit_username())",
        "'created_by_name', COALESCE(NULLIF(NEW.created_by_name, ''), mkt_audit_name())",
        "'updated_by_user_id', COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())",
        "'updated_by_username', COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())",
        "'updated_by_name', COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())",
    ]) + ")"
    payload_update = "json_object(" + ", ".join([
        "'no_resi', NEW.no_resi",
        "'kode_cabang', NEW.kode_cabang",
        "'tanggal_masuk', NEW.tanggal_masuk",
        "'tanggal_keluar', NEW.tanggal_keluar",
        "'pengirim', NEW.pengirim",
        "'hp_pengirim', NEW.hp_pengirim",
        "'alamat_pengirim', NEW.alamat_pengirim",
        "'kota_asal', NEW.kota_asal",
        "'penerima', NEW.penerima",
        "'hp_penerima', NEW.hp_penerima",
        "'alamat_penerima', NEW.alamat_penerima",
        "'kota_tujuan', NEW.kota_tujuan",
        "'nama_barang', NEW.nama_barang",
        "'koli', NEW.koli",
        "'berat', NEW.berat",
        "'cbm', NEW.cbm",
        "'ongkir_per_kg', NEW.ongkir_per_kg",
        "'ongkir_per_cbm', NEW.ongkir_per_cbm",
        "'subtotal_ongkir', NEW.subtotal_ongkir",
        "'jenis_pajak', NEW.jenis_pajak",
        "'total_ongkir', NEW.total_ongkir",
        "'pembayaran', NEW.pembayaran",
        "'status_resi', NEW.status_resi",
        "'foto_bukti', NEW.foto_bukti",
        "'truk', NEW.truk",
        "'ket_buku_gudang', NEW.ket_buku_gudang",
        "'no_manifest', NEW.no_manifest",
        "'ket_manifest', NEW.ket_manifest",
        "'rincian_json', NEW.rincian_json",
        "'revision', NEW.revision",
        "'sync_id', NEW.sync_id",
        "'created_at', NEW.created_at",
        "'updated_at', NEW.updated_at",
        "'deleted_at', NEW.deleted_at",
        "'created_by_user_id', COALESCE(NEW.created_by_user_id, OLD.created_by_user_id)",
        "'created_by_username', COALESCE(NULLIF(NEW.created_by_username, ''), NULLIF(OLD.created_by_username, ''))",
        "'created_by_name', COALESCE(NULLIF(NEW.created_by_name, ''), NULLIF(OLD.created_by_name, ''))",
        "'updated_by_user_id', COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())",
        "'updated_by_username', COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())",
        "'updated_by_name', COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())",
    ]) + ")"
    payload_delete = "json_object(" + ", ".join([
        "'no_resi', OLD.no_resi", "'kode_cabang', OLD.kode_cabang",
        "'tanggal_masuk', OLD.tanggal_masuk", "'tanggal_keluar', OLD.tanggal_keluar",
        "'pengirim', OLD.pengirim", "'hp_pengirim', OLD.hp_pengirim",
        "'alamat_pengirim', OLD.alamat_pengirim", "'kota_asal', OLD.kota_asal",
        "'penerima', OLD.penerima", "'hp_penerima', OLD.hp_penerima",
        "'alamat_penerima', OLD.alamat_penerima", "'kota_tujuan', OLD.kota_tujuan",
        "'nama_barang', OLD.nama_barang", "'koli', OLD.koli", "'berat', OLD.berat",
        "'cbm', OLD.cbm", "'ongkir_per_kg', OLD.ongkir_per_kg",
        "'ongkir_per_cbm', OLD.ongkir_per_cbm", "'subtotal_ongkir', OLD.subtotal_ongkir",
        "'jenis_pajak', OLD.jenis_pajak", "'total_ongkir', OLD.total_ongkir",
        "'pembayaran', OLD.pembayaran", "'status_resi', OLD.status_resi",
        "'foto_bukti', OLD.foto_bukti", "'truk', OLD.truk",
        "'ket_buku_gudang', OLD.ket_buku_gudang", "'no_manifest', OLD.no_manifest",
        "'ket_manifest', OLD.ket_manifest", "'rincian_json', OLD.rincian_json",
        "'revision', OLD.revision", "'sync_id', OLD.sync_id",
        "'created_at', OLD.created_at", "'updated_at', OLD.updated_at",
        "'deleted_at', OLD.deleted_at",
        "'created_by_user_id', OLD.created_by_user_id",
        "'created_by_username', OLD.created_by_username",
        "'created_by_name', OLD.created_by_name",
        "'updated_by_user_id', OLD.updated_by_user_id",
        "'updated_by_username', OLD.updated_by_username",
        "'updated_by_name', OLD.updated_by_name",
    ]) + ")"

    for name in (
        'trg_local_data_resi_outbox_insert',
        'trg_local_data_resi_outbox_update',
        'trg_local_data_resi_outbox_delete',
    ):
        cursor.execute(f'DROP TRIGGER IF EXISTS {name}')

    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_outbox_insert
        AFTER INSERT ON data_resi
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi', NEW.no_resi, 'INSERT', {payload_insert});
        END
    """)
    update_changed = " OR ".join([
        f"NEW.{c} IS NOT OLD.{c}" for c in (
            "no_resi","kode_cabang","tanggal_masuk","tanggal_keluar","pengirim",
            "hp_pengirim","alamat_pengirim","kota_asal","penerima","hp_penerima",
            "alamat_penerima","kota_tujuan","nama_barang","koli","berat","cbm",
            "ongkir_per_kg","ongkir_per_cbm","subtotal_ongkir","jenis_pajak",
            "total_ongkir","pembayaran","status_resi","foto_bukti","truk",
            "ket_buku_gudang","no_manifest","ket_manifest","rincian_json","revision",
            "sync_id","created_at","deleted_at",
        )
    ])
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_outbox_update
        AFTER UPDATE ON data_resi
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
         AND ({update_changed})
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi', NEW.no_resi, 'UPDATE', {payload_update});
        END
    """)
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_outbox_delete
        AFTER DELETE ON data_resi
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi', OLD.no_resi, 'DELETE', {payload_delete});
        END
    """)

    # --- data_resi_detail --------------------------------------------------
    detail_insert = "json_object(" + ", ".join([
        "'id_detail', NEW.id_detail", "'no_resi', NEW.no_resi", "'urutan', NEW.urutan",
        "'nama_barang', NEW.nama_barang", "'koli', NEW.koli", "'berat', NEW.berat",
        "'cbm', NEW.cbm", "'sync_id', NEW.sync_id", "'created_at', NEW.created_at",
        "'updated_at', NEW.updated_at", "'deleted_at', NEW.deleted_at",
        "'created_by_user_id', COALESCE(NEW.created_by_user_id, mkt_audit_user_id())",
        "'created_by_username', COALESCE(NULLIF(NEW.created_by_username, ''), mkt_audit_username())",
        "'created_by_name', COALESCE(NULLIF(NEW.created_by_name, ''), mkt_audit_name())",
        "'updated_by_user_id', COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())",
        "'updated_by_username', COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())",
        "'updated_by_name', COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())",
    ]) + ")"
    detail_update = "json_object(" + ", ".join([
        "'id_detail', NEW.id_detail", "'no_resi', NEW.no_resi", "'urutan', NEW.urutan",
        "'nama_barang', NEW.nama_barang", "'koli', NEW.koli", "'berat', NEW.berat",
        "'cbm', NEW.cbm", "'sync_id', NEW.sync_id", "'created_at', NEW.created_at",
        "'updated_at', NEW.updated_at", "'deleted_at', NEW.deleted_at",
        "'created_by_user_id', COALESCE(NEW.created_by_user_id, OLD.created_by_user_id)",
        "'created_by_username', COALESCE(NULLIF(NEW.created_by_username, ''), NULLIF(OLD.created_by_username, ''))",
        "'created_by_name', COALESCE(NULLIF(NEW.created_by_name, ''), NULLIF(OLD.created_by_name, ''))",
        "'updated_by_user_id', COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())",
        "'updated_by_username', COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())",
        "'updated_by_name', COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())",
    ]) + ")"
    detail_delete = "json_object(" + ", ".join([
        "'id_detail', OLD.id_detail", "'no_resi', OLD.no_resi", "'urutan', OLD.urutan",
        "'nama_barang', OLD.nama_barang", "'koli', OLD.koli", "'berat', OLD.berat",
        "'cbm', OLD.cbm", "'sync_id', OLD.sync_id", "'created_at', OLD.created_at",
        "'updated_at', OLD.updated_at", "'deleted_at', OLD.deleted_at",
        "'created_by_user_id', OLD.created_by_user_id",
        "'created_by_username', OLD.created_by_username",
        "'created_by_name', OLD.created_by_name",
        "'updated_by_user_id', OLD.updated_by_user_id",
        "'updated_by_username', OLD.updated_by_username",
        "'updated_by_name', OLD.updated_by_name",
    ]) + ")"

    for name in (
        'trg_local_data_resi_detail_outbox_insert',
        'trg_local_data_resi_detail_outbox_update',
        'trg_local_data_resi_detail_outbox_delete',
    ):
        cursor.execute(f'DROP TRIGGER IF EXISTS {name}')

    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_detail_outbox_insert
        AFTER INSERT ON data_resi_detail
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi_detail', COALESCE(NEW.sync_id, CAST(NEW.id_detail AS TEXT)), 'INSERT', {detail_insert});
        END
    """)
    detail_changed = " OR ".join([
        f"NEW.{c} IS NOT OLD.{c}" for c in (
            "id_detail","no_resi","urutan","nama_barang","koli","berat","cbm",
            "sync_id","created_at","deleted_at",
        )
    ])
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_detail_outbox_update
        AFTER UPDATE ON data_resi_detail
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
         AND ({detail_changed})
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi_detail', COALESCE(NEW.sync_id, CAST(NEW.id_detail AS TEXT)), 'UPDATE', {detail_update});
        END
    """)
    cursor.execute(f"""
        CREATE TRIGGER trg_local_data_resi_detail_outbox_delete
        AFTER DELETE ON data_resi_detail
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('data_resi_detail', COALESCE(OLD.sync_id, CAST(OLD.id_detail AS TEXT)), 'DELETE', {detail_delete});
        END
    """)



def _migration_v13(cursor) -> None:
    """Fondasi sync Buku Gudang: sync_id, soft-delete, actor snapshot, dan outbox."""
    table = "buku_gudang"
    columns = {
        str(row[1]).strip()
        for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
    }

    if "sync_id" not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN sync_id TEXT")
    if "deleted_at" not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT")

    actor_columns = (
        "created_by_user_id",
        "created_by_username",
        "created_by_name",
        "updated_by_user_id",
        "updated_by_username",
        "updated_by_name",
    )
    for column in actor_columns:
        if column not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")

    # Row lama mendapat identitas lintas perangkat yang stabil.
    rows = cursor.execute(
        f"SELECT rowid FROM {table} WHERE sync_id IS NULL OR TRIM(sync_id) = ''"
    ).fetchall()
    for (rowid,) in rows:
        cursor.execute(
            f"UPDATE {table} SET sync_id = ? WHERE rowid = ?",
            (str(uuid.uuid4()), rowid),
        )

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_buku_gudang_sync_id "
        "ON buku_gudang(sync_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_buku_gudang_cabang_sync "
        "ON buku_gudang(kode_cabang, sync_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_buku_gudang_resi "
        "ON buku_gudang(no_resi, kode_cabang)"
    )

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
        "'created_by_user_id', COALESCE(NEW.created_by_user_id, mkt_audit_user_id())",
        "'created_by_username', COALESCE(NULLIF(NEW.created_by_username, ''), mkt_audit_username())",
        "'created_by_name', COALESCE(NULLIF(NEW.created_by_name, ''), mkt_audit_name())",
        "'updated_by_user_id', COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())",
        "'updated_by_username', COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())",
        "'updated_by_name', COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())",
    ]) + ")"
    payload_old = "json_object(" + ", ".join([
        "'id_gudang', OLD.id_gudang",
        "'kode_cabang', OLD.kode_cabang",
        "'tanggal', OLD.tanggal",
        "'no_resi', OLD.no_resi",
        "'jenis', OLD.jenis",
        "'status_resi', OLD.status_resi",
        "'sync_id', OLD.sync_id",
        "'created_at', OLD.created_at",
        "'updated_at', OLD.updated_at",
        "'deleted_at', OLD.deleted_at",
        "'created_by_user_id', OLD.created_by_user_id",
        "'created_by_username', OLD.created_by_username",
        "'created_by_name', OLD.created_by_name",
        "'updated_by_user_id', OLD.updated_by_user_id",
        "'updated_by_username', OLD.updated_by_username",
        "'updated_by_name', OLD.updated_by_name",
    ]) + ")"

    for name in (
        "trg_local_buku_gudang_outbox_insert",
        "trg_local_buku_gudang_outbox_update",
        "trg_local_buku_gudang_outbox_delete",
    ):
        cursor.execute(f"DROP TRIGGER IF EXISTS {name}")

    cursor.execute(f"""
        CREATE TRIGGER trg_local_buku_gudang_outbox_insert
        AFTER INSERT ON buku_gudang
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('buku_gudang', NEW.sync_id, 'INSERT', {payload_new});
        END
    """)

    changed = " OR ".join(
        f"NEW.{column} IS NOT OLD.{column}"
        for column in (
            "id_gudang", "kode_cabang", "tanggal", "no_resi", "jenis",
            "status_resi", "sync_id", "created_at", "deleted_at",
            "created_by_user_id", "created_by_username", "created_by_name",
            "updated_by_user_id", "updated_by_username", "updated_by_name",
        )
    )
    cursor.execute(f"""
        CREATE TRIGGER trg_local_buku_gudang_outbox_update
        AFTER UPDATE ON buku_gudang
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
         AND ({changed})
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('buku_gudang', NEW.sync_id, 'UPDATE', {payload_new});
        END
    """)

    cursor.execute(f"""
        CREATE TRIGGER trg_local_buku_gudang_outbox_delete
        AFTER DELETE ON buku_gudang
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('buku_gudang', OLD.sync_id, 'DELETE', {payload_old});
        END
    """)

def _migration_v14(cursor) -> None:
    """Lengkapi metadata sync untuk master operasional lama.

    Tabel master_pengirim/master_penerima/truk/kapal dibuat pada schema awal
    sebelum fondasi offline-first diperluas. Schema lama itu belum memiliki
    sync_id/deleted_at, padahal services.sync_service sudah mensyaratkan kedua
    kolom tersebut. Migration ini dibuat idempotent dan aman untuk DB existing.
    """
    tables = (
        "master_pengirim",
        "master_penerima",
        "truk",
        "kapal",
    )

    for table in tables:
        columns = {
            str(row[1]).strip().lower()
            for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
        }

        if "sync_id" not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN sync_id TEXT")
        if "deleted_at" not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT")

        # Row lama mendapat identitas lintas perangkat yang stabil.
        rows = cursor.execute(
            f"SELECT rowid FROM {table} WHERE sync_id IS NULL OR TRIM(sync_id) = ''"
        ).fetchall()
        for (rowid,) in rows:
            cursor.execute(
                f"UPDATE {table} SET sync_id = ? WHERE rowid = ?",
                (str(uuid.uuid4()), rowid),
            )

        cursor.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_sync_id ON {table}(sync_id)"
        )
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_deleted_at ON {table}(deleted_at)"
        )



def _migration_v15(cursor) -> None:
    """Pastikan Buku Gudang lama/baru benar-benar masuk antrean push.

    Buku Gudang adalah projection dari transaksi Resi. Versi sebelumnya sudah
    memasang trigger/outbox, tetapi database yang pernah dibuat sebelum trigger
    terpasang dapat memiliki row buku_gudang tanpa outbox. Migration ini:
    - memastikan schema/trigger Buku Gudang tetap terpasang;
    - membuat ulang antrean INSERT untuk row lokal yang belum tersinkron;
    - tidak membuat antrean baru untuk row yang sudah ditandai synced.
    """
    _migration_v13(cursor)

    rows = cursor.execute(
        """
        SELECT id_gudang, sync_id, kode_cabang, tanggal, no_resi, jenis,
               status_resi, created_at, updated_at, deleted_at,
               created_by_user_id, created_by_username, created_by_name,
               updated_by_user_id, updated_by_username, updated_by_name
        FROM buku_gudang
        WHERE COALESCE(is_synced, 0) = 0
          AND sync_id IS NOT NULL
          AND TRIM(sync_id) <> ''
        """
    ).fetchall()

    for row in rows:
        (
            id_gudang, sync_id, kode_cabang, tanggal, no_resi, jenis,
            status_resi, created_at, updated_at, deleted_at,
            created_by_user_id, created_by_username, created_by_name,
            updated_by_user_id, updated_by_username, updated_by_name,
        ) = row
        already_pending = cursor.execute(
            """
            SELECT 1
            FROM sync_outbox
            WHERE table_name = 'buku_gudang'
              AND record_key = ?
              AND status = 'PENDING'
            LIMIT 1
            """,
            (str(sync_id),),
        ).fetchone()
        if already_pending:
            continue

        payload = json.dumps({
            "id_gudang": id_gudang,
            "kode_cabang": kode_cabang,
            "tanggal": tanggal,
            "no_resi": no_resi,
            "jenis": jenis,
            "status_resi": status_resi,
            "sync_id": sync_id,
            "created_at": created_at,
            "updated_at": updated_at,
            "deleted_at": deleted_at,
            "created_by_user_id": created_by_user_id,
            "created_by_username": created_by_username,
            "created_by_name": created_by_name,
            "updated_by_user_id": updated_by_user_id,
            "updated_by_username": updated_by_username,
            "updated_by_name": updated_by_name,
        }, ensure_ascii=False)
        cursor.execute(
            """
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('buku_gudang', ?, 'INSERT', ?)
            """,
            (str(sync_id), payload),
        )

def _migration_v16(cursor) -> None:
    """Tambahkan outbox trigger two-way untuk master pengirim/penerima, truk, dan kapal.

    Versi sebelumnya memiliki kolom sync_id/deleted_at pada empat master, tetapi
    belum memiliki trigger lokal yang memasukkan INSERT/UPDATE/DELETE ke sync_outbox.
    Akibatnya data master baru/hasil edit dapat tersimpan di SQLite namun tidak
    pernah masuk antrean push ke Supabase.

    Migration ini hanya memasang trigger. Rekonsiliasi row legacy yang belum
    tersinkron ditangani oleh sync_service setelah pull server memberi tanda
    is_synced=1 pada row yang memang berasal dari server.
    """
    # Pastikan kolom inti tersedia sebelum trigger dibuat.
    required = {
        "master_penerima": (
            "id_penerima", "kode_cabang", "nama", "no_hp", "alamat", "kota",
            "provinsi", "total_transaksi", "pembayaran", "status_tagihan",
            "sync_id", "created_at", "updated_at", "deleted_at",
            "created_by_user_id", "created_by_username", "created_by_name",
            "updated_by_user_id", "updated_by_username", "updated_by_name",
        ),
        "master_pengirim": (
            "id_pengirim", "kode_cabang", "nama", "no_hp", "alamat", "kota",
            "sync_id", "created_at", "updated_at", "deleted_at",
            "created_by_user_id", "created_by_username", "created_by_name",
            "updated_by_user_id", "updated_by_username", "updated_by_name",
        ),
        "truk": (
            "kode_cabang", "jenis_truk", "no_polisi", "nama_sopir", "hp_sopir",
            "ket_truk", "foto_truk", "sync_id", "created_at", "updated_at",
            "deleted_at", "created_by_user_id", "created_by_username",
            "created_by_name", "updated_by_user_id", "updated_by_username",
            "updated_by_name",
        ),
        "kapal": (
            "nama_kapal", "tujuan", "ket_kapal", "foto_kapal", "sync_id",
            "created_at", "updated_at", "deleted_at",
            "created_by_user_id", "created_by_username", "created_by_name",
            "updated_by_user_id", "updated_by_username", "updated_by_name",
        ),
    }

    payloads = {
        "master_penerima": [
            ("id_penerima", "NEW.id_penerima"),
            ("kode_cabang", "NEW.kode_cabang"),
            ("nama", "NEW.nama"),
            ("no_hp", "NEW.no_hp"),
            ("alamat", "NEW.alamat"),
            ("kota", "NEW.kota"),
            ("provinsi", "NEW.provinsi"),
            ("total_transaksi", "NEW.total_transaksi"),
            ("pembayaran", "NEW.pembayaran"),
            ("status_tagihan", "NEW.status_tagihan"),
            ("sync_id", "NEW.sync_id"),
            ("created_at", "NEW.created_at"),
            ("updated_at", "NEW.updated_at"),
            ("deleted_at", "NEW.deleted_at"),
            ("created_by_user_id", "COALESCE(NEW.created_by_user_id, mkt_audit_user_id())"),
            ("created_by_username", "COALESCE(NULLIF(NEW.created_by_username, ''), mkt_audit_username())"),
            ("created_by_name", "COALESCE(NULLIF(NEW.created_by_name, ''), mkt_audit_name())"),
            ("updated_by_user_id", "COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())"),
            ("updated_by_username", "COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())"),
            ("updated_by_name", "COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())"),
        ],
        "master_pengirim": [
            ("id_pengirim", "NEW.id_pengirim"),
            ("kode_cabang", "NEW.kode_cabang"),
            ("nama", "NEW.nama"),
            ("no_hp", "NEW.no_hp"),
            ("alamat", "NEW.alamat"),
            ("kota", "NEW.kota"),
            ("sync_id", "NEW.sync_id"),
            ("created_at", "NEW.created_at"),
            ("updated_at", "NEW.updated_at"),
            ("deleted_at", "NEW.deleted_at"),
            ("created_by_user_id", "COALESCE(NEW.created_by_user_id, mkt_audit_user_id())"),
            ("created_by_username", "COALESCE(NULLIF(NEW.created_by_username, ''), mkt_audit_username())"),
            ("created_by_name", "COALESCE(NULLIF(NEW.created_by_name, ''), mkt_audit_name())"),
            ("updated_by_user_id", "COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())"),
            ("updated_by_username", "COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())"),
            ("updated_by_name", "COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())"),
        ],
        "truk": [
            ("kode_cabang", "NEW.kode_cabang"),
            ("jenis_truk", "NEW.jenis_truk"),
            ("no_polisi", "NEW.no_polisi"),
            ("nama_sopir", "NEW.nama_sopir"),
            ("hp_sopir", "NEW.hp_sopir"),
            ("ket_truk", "NEW.ket_truk"),
            ("foto_truk", "NEW.foto_truk"),
            ("sync_id", "NEW.sync_id"),
            ("created_at", "NEW.created_at"),
            ("updated_at", "NEW.updated_at"),
            ("deleted_at", "NEW.deleted_at"),
            ("created_by_user_id", "COALESCE(NEW.created_by_user_id, mkt_audit_user_id())"),
            ("created_by_username", "COALESCE(NULLIF(NEW.created_by_username, ''), mkt_audit_username())"),
            ("created_by_name", "COALESCE(NULLIF(NEW.created_by_name, ''), mkt_audit_name())"),
            ("updated_by_user_id", "COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())"),
            ("updated_by_username", "COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())"),
            ("updated_by_name", "COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())"),
        ],
        "kapal": [
            ("nama_kapal", "NEW.nama_kapal"),
            ("tujuan", "NEW.tujuan"),
            ("ket_kapal", "NEW.ket_kapal"),
            ("foto_kapal", "NEW.foto_kapal"),
            ("sync_id", "NEW.sync_id"),
            ("created_at", "NEW.created_at"),
            ("updated_at", "NEW.updated_at"),
            ("deleted_at", "NEW.deleted_at"),
            ("created_by_user_id", "COALESCE(NEW.created_by_user_id, mkt_audit_user_id())"),
            ("created_by_username", "COALESCE(NULLIF(NEW.created_by_username, ''), mkt_audit_username())"),
            ("created_by_name", "COALESCE(NULLIF(NEW.created_by_name, ''), mkt_audit_name())"),
            ("updated_by_user_id", "COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())"),
            ("updated_by_username", "COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())"),
            ("updated_by_name", "COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())"),
        ],
    }

    for table, cols in required.items():
        existing = {
            str(row[1]).strip()
            for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
        }
        missing = [c for c in cols if c not in existing]
        if missing:
            raise RuntimeError(
                f"Migration v16: schema {table} belum lengkap; kolom hilang: {', '.join(missing)}"
            )

        # Row yang dibuat sebelum trigger v16 bisa belum memiliki sync_id.
        # Beri identitas lintas perangkat sekarang agar dapat diantrikan oleh
        # sync_service tanpa perlu menghapus atau menginput ulang data.
        rows_without_sync_id = cursor.execute(
            f"SELECT rowid FROM {table} WHERE sync_id IS NULL OR TRIM(sync_id) = ''"
        ).fetchall()
        for (rowid,) in rows_without_sync_id:
            cursor.execute(
                f"UPDATE {table} SET sync_id = ? WHERE rowid = ?",
                (str(uuid.uuid4()), rowid),
            )

        items = payloads[table]
        insert_expr = "json_object(" + ", ".join(
            f"'{k}', {expr}" for k, expr in items
        ) + ")"
        old_items = [(k, expr.replace("NEW.", "OLD.")) for k, expr in items]
        # For deleted rows, actor fallback must not suddenly use the sync actor.
        delete_items = []
        for k, expr in old_items:
            if k in {"created_by_user_id", "created_by_username", "created_by_name",
                     "updated_by_user_id", "updated_by_username", "updated_by_name"}:
                # use OLD values exactly
                raw = {
                    "created_by_user_id": "OLD.created_by_user_id",
                    "created_by_username": "OLD.created_by_username",
                    "created_by_name": "OLD.created_by_name",
                    "updated_by_user_id": "OLD.updated_by_user_id",
                    "updated_by_username": "OLD.updated_by_username",
                    "updated_by_name": "OLD.updated_by_name",
                }[k]
                delete_items.append((k, raw))
            else:
                delete_items.append((k, expr))
        delete_expr = "json_object(" + ", ".join(
            f"'{k}', {expr}" for k, expr in delete_items
        ) + ")"

        key_expr = "NEW.sync_id"
        old_key_expr = "OLD.sync_id"
        names = (
            f"trg_local_{table}_outbox_insert",
            f"trg_local_{table}_outbox_update",
            f"trg_local_{table}_outbox_delete",
        )
        for name in names:
            cursor.execute(f"DROP TRIGGER IF EXISTS {name}")

        cursor.execute(f"""
            CREATE TRIGGER {names[0]}
            AFTER INSERT ON {table}
            WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
            BEGIN
                INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
                VALUES ('{table}', {key_expr}, 'INSERT', {insert_expr});
            END
        """)
        cursor.execute(f"""
            CREATE TRIGGER {names[1]}
            AFTER UPDATE ON {table}
            WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
            BEGIN
                INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
                VALUES ('{table}', {key_expr}, 'UPDATE', {insert_expr});
            END
        """)
        cursor.execute(f"""
            CREATE TRIGGER {names[2]}
            AFTER DELETE ON {table}
            WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
            BEGIN
                INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
                VALUES ('{table}', {old_key_expr}, 'DELETE', {delete_expr});
            END
        """)



def _migration_v17(cursor) -> None:
    """Fondasi sinkronisasi dua arah untuk header Manifest.

    note_manifest adalah catatan satu Manifest; ket_manifest tetap berada di
    data_resi dan tidak disentuh oleh migrasi ini. Row Manifest lama diberi
    sync_id dan antrean INSERT agar bisa dimigrasikan dengan upsert idempoten
    setelah tabel public.manifest disiapkan di Supabase.
    """
    table = "manifest"
    columns = {
        str(row[1]).strip()
        for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
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
    for column, sql_type in additions.items():
        if column not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")

    # Beri identitas lintas perangkat pada header Manifest yang dibuat sebelum v17.
    rows_without_sync_id = cursor.execute(
        "SELECT rowid FROM manifest WHERE sync_id IS NULL OR TRIM(sync_id) = ''"
    ).fetchall()
    for (rowid,) in rows_without_sync_id:
        cursor.execute(
            "UPDATE manifest SET sync_id = ? WHERE rowid = ?",
            (str(uuid.uuid4()), rowid),
        )

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_manifest_sync_id ON manifest(sync_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_manifest_cabang_updated "
        "ON manifest(kode_cabang, updated_at)"
    )

    fields = (
        "id_manifest", "kode_cabang", "tanggal", "no_polisi", "nama_sopir",
        "nama_kapal", "note_manifest", "status_manifest", "sync_id",
        "created_at", "updated_at", "deleted_at",
        "created_by_user_id", "created_by_username", "created_by_name",
        "updated_by_user_id", "updated_by_username", "updated_by_name",
    )
    new_actor_expr = {
        "created_by_user_id": "COALESCE(NEW.created_by_user_id, mkt_audit_user_id())",
        "created_by_username": "COALESCE(NULLIF(NEW.created_by_username, ''), mkt_audit_username())",
        "created_by_name": "COALESCE(NULLIF(NEW.created_by_name, ''), mkt_audit_name())",
        "updated_by_user_id": "COALESCE(NEW.updated_by_user_id, mkt_audit_user_id())",
        "updated_by_username": "COALESCE(NULLIF(NEW.updated_by_username, ''), mkt_audit_username())",
        "updated_by_name": "COALESCE(NULLIF(NEW.updated_by_name, ''), mkt_audit_name())",
    }
    old_actor_expr = {
        "created_by_user_id": "OLD.created_by_user_id",
        "created_by_username": "OLD.created_by_username",
        "created_by_name": "OLD.created_by_name",
        "updated_by_user_id": "OLD.updated_by_user_id",
        "updated_by_username": "OLD.updated_by_username",
        "updated_by_name": "OLD.updated_by_name",
    }
    new_expr = "json_object(" + ", ".join(
        f"'{field}', {new_actor_expr.get(field, f'NEW.{field}')}"
        for field in fields
    ) + ")"
    old_expr = "json_object(" + ", ".join(
        f"'{field}', {old_actor_expr.get(field, f'OLD.{field}')}"
        for field in fields
    ) + ")"

    names = (
        "trg_local_manifest_outbox_insert",
        "trg_local_manifest_outbox_update",
        "trg_local_manifest_outbox_delete",
    )
    for name in names:
        cursor.execute(f"DROP TRIGGER IF EXISTS {name}")

    cursor.execute(f"""
        CREATE TRIGGER {names[0]}
        AFTER INSERT ON manifest
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('manifest', NEW.sync_id, 'INSERT', {new_expr});
        END
    """)

    changed_columns = (
        "id_manifest", "kode_cabang", "tanggal", "no_polisi", "nama_sopir",
        "nama_kapal", "note_manifest", "status_manifest", "sync_id",
        "created_at", "updated_at", "deleted_at",
    )
    changed_expr = " OR ".join(
        f"NEW.{column} IS NOT OLD.{column}" for column in changed_columns
    )
    cursor.execute(f"""
        CREATE TRIGGER {names[1]}
        AFTER UPDATE ON manifest
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
         AND ({changed_expr})
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('manifest', NEW.sync_id, 'UPDATE', {new_expr});
        END
    """)

    cursor.execute(f"""
        CREATE TRIGGER {names[2]}
        AFTER DELETE ON manifest
        WHEN COALESCE((SELECT suppress_outbox FROM sync_control WHERE id = 1), 0) = 0
        BEGIN
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('manifest', OLD.sync_id, 'DELETE', {old_expr});
        END
    """)

    # Manifest lama belum pernah memiliki trigger outbox. Antrekan sebagai INSERT
    # satu kali; handler push mencocokkan id_manifest agar data server yang sudah
    # ada tidak dibuat duplikat.
    select_fields = ", ".join(f'"{field}"' for field in fields)
    legacy_rows = cursor.execute(
        f"SELECT {select_fields} FROM manifest ORDER BY id_manifest"
    ).fetchall()
    for raw in legacy_rows:
        payload = dict(zip(fields, raw))
        sync_id = str(payload.get("sync_id") or "").strip()
        if not sync_id:
            continue
        pending = cursor.execute(
            """
            SELECT 1 FROM sync_outbox
            WHERE table_name = 'manifest' AND record_key = ?
              AND status IN ('PENDING', 'CONFLICT')
            LIMIT 1
            """,
            (sync_id,),
        ).fetchone()
        if pending:
            continue
        cursor.execute(
            """
            INSERT INTO sync_outbox(table_name, record_key, operation, payload_json)
            VALUES ('manifest', ?, 'INSERT', ?)
            """,
            (sync_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        )


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
    """Menjamin cabang internal developer tanpa membuat cabang PUSAT dummy.

    Mahkota production hanya menggunakan SBY dan JKT sebagai cabang bisnis.
    PUSAT lama tidak lagi dibuat otomatis. DEV_SYS dipertahankan sebagai
    cabang internal developer dan tidak dipakai sebagai cabang bisnis.
    """
    cabang_minimal = (
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


_SCHEMA_MIGRATIONS = {
    1: _migration_v1,
    2: _migration_v2,
    3: _migration_v3,
    4: _migration_v4,
    5: _migration_v5,
    6: _migration_v6,
    7: _migration_v7,
    8: _migration_v8,
    9: _migration_v9,
    10: _migration_v10,
    11: _migration_v11,
    12: _migration_v12,
    13: _migration_v13,
    14: _migration_v14,
    15: _migration_v15,
    16: _migration_v16,
    17: _migration_v17,
}


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
            install_sqlite_audit_functions(conn)
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()

            for statement in _SCHEMA_STATEMENTS:
                cursor.execute(statement)

            _jalankan_migrasi_schema(cursor)
            _pastikan_bootstrap_cabang_minimal(cursor)
            conn.commit()

        print(
            f"Database berhasil dibuat/diperiksa: {db_path} "
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