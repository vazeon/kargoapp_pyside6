# database_manager.py
import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_NAME = "database_cargo.db"
DB_SCHEMA_VERSION = 7

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



_SCHEMA_MIGRATIONS = {
    1: _migration_v1,
    2: _migration_v2,
    3: _migration_v3,
    4: _migration_v4,
    5: _migration_v5,
    6: _migration_v6,
    7: _migration_v7,
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