# services/database_service.py

import sqlite3
import json
import logging
import re
import uuid
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from audit_context import install_sqlite_audit_functions
from config import CURRENT_SESSION, DATA_CLIENT, CENTRAL_BRANCH_ROLES, BRANCH_ACCESS_VIEW, cabang_boleh_tulis, mode_akses_cabang
from supabase_client import SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, supabase
import services.numbering_service as numbering_service

logger = logging.getLogger(__name__)

_AUTOCOMPLETE_CACHE = {}
_AUTOCOMPLETE_CACHE_TTL = 5.0


# ==============================================================================
# 01. ERROR TERSTRUKTUR
# Dipakai supaya caller (mis. tab_resi.py) tidak perlu cocokkan string pesan
# mentah dari SQLite untuk menentukan jenis kegagalan — cukup cek `.kode`.
# ==============================================================================

class KesalahanTransaksiResi(Exception):
    def __init__(self, kode, pesan):
        self.kode = kode
        self.pesan = pesan
        super().__init__(pesan)

    def __str__(self):
        return self.pesan

KODE_RESI_DUPLIKAT = "RESI_DUPLIKAT"
KODE_RESI_KONFLIK = "RESI_KONFLIK_EDIT"
KODE_DB_ERROR = "DB_ERROR"

# ==============================================================================
# 02. DATABASE CORE & GLOBAL UTILITIES
# ==============================================================================

def get_db_connection(db_name=None):
    """Membuka koneksi SQLite aktif dengan foreign key dan timeout."""
    target_db = db_name or CURRENT_SESSION.get("db_name", "database_cargo.db")
    conn = sqlite3.connect(str(target_db), timeout=20.0)
    conn.execute("PRAGMA foreign_keys = ON")
    install_sqlite_audit_functions(conn)
    # SQLite performance tuning (safe for existing schema)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA busy_timeout = 20000")
    return conn

@contextmanager
def _db_transaction(db_name=None, *, immediate=False):
    """Kelola transaksi SQLite dan cegah mutation saat cabang aktif VIEW ONLY."""
    if immediate and str(CURRENT_SESSION.get("active_access_mode") or "FULL").strip().upper() == BRANCH_ACCESS_VIEW:
        raise PermissionError(
            "Cabang aktif sedang dalam mode VIEW ONLY. Operasi perubahan data tidak diizinkan."
        )
    conn = get_db_connection(db_name)
    try:
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        yield conn, conn.cursor()
        if conn.in_transaction:
            conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()

def _text(value):
    return str(value or "").strip()

def _upper(value):
    return _text(value).upper()

def _audit_actor_values():
    """Ambil snapshot user aktif untuk penulisan record lokal.

    Identitas ini harus menempel pada record saat dibuat, sehingga tetap benar
    ketika antrean offline baru dikirim setelah user berganti akun.
    """
    user_id = str(CURRENT_SESSION.get("id_user") or "").strip() or None
    username = str(CURRENT_SESSION.get("username") or "").strip().upper() or None
    name = str(CURRENT_SESSION.get("nama_lengkap") or "").strip() or username
    return user_id, username, name

def _rollback(conn):
    if conn:
        conn.rollback()

def _close(conn):
    if conn:
        conn.close()

def _kode_cabang_aktif(kode_cabang=None):
    """Menghasilkan kode cabang baku untuk operasi yang memakai cabang aktif."""
    return _upper(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT") or "PUSAT"
    )

def _pastikan_boleh_tulis_cabang(kode_cabang=None):
    """Blok mutation lokal saat user membuka cabang dalam mode VIEW ONLY."""
    kode = _kode_cabang_aktif(kode_cabang)
    if not cabang_boleh_tulis(kode):
        raise PermissionError(
            f"Cabang {kode} sedang dalam mode VIEW ONLY. Data cabang ini tidak dapat diubah oleh akun ini."
        )
    return kode

def _fetchall(query, params=(), *, db_name=None):
    """Eksekusi query baca dan selalu tutup koneksi setelah fetchall."""
    conn = get_db_connection(db_name)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()

def _fetchone(query, params=(), *, db_name=None):
    """Eksekusi query baca dan selalu tutup koneksi setelah fetchone."""
    conn = get_db_connection(db_name)
    try:
        return conn.execute(query, params).fetchone()
    finally:
        conn.close()

def get_setting(key):
    """
    Mengambil satu pengaturan dari database.
    Jika belum tersedia, gunakan DATA_CLIENT dari config.py.
    """
    try:
        row = _fetchone(
            "SELECT nilai FROM pengaturan_sistem WHERE kunci = ?",
            (str(key),),
        )
        if row is not None:
            return row[0]
    except sqlite3.Error as exc:
        logger.warning("[Setting] Gagal membaca %s: %s", key, exc)
    return DATA_CLIENT.get(key, "")

def ambil_persen_ppn_resi():
    """Ambil persentase PPN Resi untuk kalkulasi/preview cetak.

    Nilai setting diperlakukan sebagai persen (contoh: ``1,1`` berarti 1,1%).
    Beberapa nama key lama tetap dibaca agar konfigurasi existing kompatibel.
    Bila setting tidak tersedia/tidak valid, gunakan default operasional 1,1%.
    """
    from decimal import Decimal, InvalidOperation

    for key in ("persen_ppn_resi", "ppn_persen", "persen_ppn"):
        raw = get_setting(key)
        if raw in (None, ""):
            continue

        teks = str(raw).strip().replace("%", "").replace(",", ".")
        try:
            nilai = Decimal(teks)
        except (InvalidOperation, ValueError, TypeError):
            continue

        if nilai.is_finite() and Decimal("0") <= nilai <= Decimal("100"):
            return nilai

    return Decimal("1.1")


def sesuaikan_nomor_resi_dengan_pajak(no_resi, jenis_pajak):
    """Sesuaikan hanya suffix pajak tanpa membuat ulang prefix/counter resi.

    Dipakai saat Edit Resi agar perubahan NONPAJAK <-> PAJAK tetap menjaga
    nomor dasar yang sama. Suffix mengikuti pengaturan white-label
    ``kode_akhiran_pajak`` (fallback ``-P``).
    """
    nomor = str(no_resi or "").strip().upper()
    if not nomor:
        return ""

    suffix = str(get_setting("kode_akhiran_pajak") or "-P").strip().upper()
    if not suffix:
        return nomor

    is_pajak = str(jenis_pajak or "NONPAJAK").strip().upper().startswith("PAJAK")
    punya_suffix = nomor.endswith(suffix)

    if is_pajak:
        return nomor if punya_suffix else f"{nomor}{suffix}"

    if punya_suffix:
        nomor_dasar = nomor[:-len(suffix)].rstrip()
        return nomor_dasar or nomor
    return nomor

def _sinkronkan_metadata_invoice_resi_cursor(
    cursor, no_resi_lama, no_resi_baru, kode_cabang
):
    """Perbarui referensi source_resi Invoice setelah suffix Resi berubah.

    Detail Invoice sengaja tetap menjadi snapshot historis. Metadata sumber
    harus menunjuk ke nomor aktif agar Invoice lama masih dapat dibuka dan
    validasi revision berikutnya tidak menganggap Resi menghilang.
    """
    lama = str(no_resi_lama or "").strip().upper()
    baru = str(no_resi_baru or "").strip().upper()
    cabang = str(kode_cabang or "").strip().upper()
    if not lama or not baru or lama == baru:
        return 0

    try:
        rows = cursor.execute(
            """
            SELECT DISTINCT h.no_invoice, h.metadata_json
            FROM invoice_header AS h
            INNER JOIN invoice_resi AS ir ON ir.no_invoice = h.no_invoice
            WHERE UPPER(ir.no_resi) = UPPER(?)
              AND (ir.kode_cabang IS NULL OR UPPER(ir.kode_cabang) = ?)
            """,
            (lama, cabang),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table: invoice_resi" not in str(exc).lower():
            raise
        return 0

    diperbarui = 0
    for no_invoice, metadata_json in rows:
        try:
            metadata = json.loads(metadata_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning(
                "[Invoice] Metadata %s tidak valid; referensi Resi tidak diubah.",
                no_invoice,
            )
            continue
        if not isinstance(metadata, dict):
            continue

        sumber = metadata.get("source_resi")
        if not isinstance(sumber, list):
            continue

        berubah = False
        for item in sumber:
            if not isinstance(item, dict):
                continue
            nomor_key = next(
                (
                    key for key in ("no_resi", "resi", "nomor_resi")
                    if str(item.get(key) or "").strip()
                ),
                None,
            )
            if not nomor_key or str(item[nomor_key]).strip().upper() != lama:
                continue
            item[nomor_key] = baru
            if "kode_cabang" in item and not item.get("kode_cabang"):
                item["kode_cabang"] = cabang
            berubah = True

        if not berubah:
            continue
        cursor.execute(
            """
            UPDATE invoice_header
            SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE no_invoice = ?
            """,
            (json.dumps(metadata, ensure_ascii=False), no_invoice),
        )
        diperbarui += cursor.rowcount
    return diperbarui


def _rename_resi_aman(cursor, no_resi_lama, no_resi_baru, kode_cabang):
    """Ganti primary key resi sambil menjaga seluruh FK internal tetap valid.

    Strategi copy -> pindah child -> hapus parent lama sengaja dipakai agar
    database existing yang tabel ``buku_gudang``-nya belum memiliki
    ``ON UPDATE CASCADE`` tetap aman tanpa migrasi schema.
    """
    lama = str(no_resi_lama or "").strip().upper()
    baru = str(no_resi_baru or "").strip().upper()
    cabang = str(kode_cabang or "").strip().upper()
    if not lama or not baru or lama == baru:
        return lama or baru

    if cursor.execute(
        "SELECT 1 FROM data_resi WHERE no_resi = ? LIMIT 1",
        (baru,),
    ).fetchone():
        raise KesalahanTransaksiResi(
            KODE_RESI_DUPLIKAT,
            f"Nomor resi {baru} sudah ada di database.",
        )

    columns = [
        str(row[1])
        for row in cursor.execute("PRAGMA table_info(data_resi)").fetchall()
    ]
    if "no_resi" not in columns:
        raise KesalahanTransaksiResi(
            KODE_DB_ERROR, "Schema data_resi tidak memiliki kolom no_resi."
        )

    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    select_parts = [
        "?" if column == "no_resi" else ("?" if column == "sync_id" else f'"{column}"')
        for column in columns
    ]
    cursor.execute(
        f"""
        INSERT INTO data_resi ({quoted_columns})
        SELECT {', '.join(select_parts)}
        FROM data_resi
        WHERE no_resi = ? AND kode_cabang = ?
        """,
        (baru, str(uuid.uuid4()), lama, cabang),
    )
    if cursor.rowcount != 1:
        raise KesalahanTransaksiResi(
            KODE_DB_ERROR, f"Resi {lama} gagal disalin ke nomor baru {baru}."
        )

    # Parent baru sudah ada, sehingga child aman dipindahkan tanpa mematikan FK.
    cursor.execute(
        "UPDATE data_resi_detail SET no_resi = ?, updated_at = CURRENT_TIMESTAMP WHERE no_resi = ?",
        (baru, lama),
    )

    id_gudang_lama = f"GDG-{lama}"
    id_gudang_baru = f"GDG-{baru}"
    cursor.execute(
        """
        UPDATE buku_gudang
        SET no_resi = ?,
            id_gudang = CASE WHEN id_gudang = ? THEN ? ELSE id_gudang END,
            is_synced = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE no_resi = ? AND kode_cabang = ?
        """,
        (baru, id_gudang_lama, id_gudang_baru, lama, cabang),
    )

    # Metadata Invoice masih menunjuk nomor lama pada titik ini; perbarui
    # sebelum relasi invoice_resi dipindahkan ke nomor baru.
    _sinkronkan_metadata_invoice_resi_cursor(
        cursor, lama, baru, cabang
    )

    # invoice_detail tetap menjadi snapshot historis. invoice_resi adalah relasi
    # operasional ke nomor Resi aktif, sehingga ikut bergerak saat nomor berubah.
    try:
        cursor.execute(
            """
            DELETE FROM invoice_resi
            WHERE UPPER(no_resi) = UPPER(?)
              AND no_invoice IN (
                  SELECT no_invoice
                  FROM invoice_resi
                  WHERE UPPER(no_resi) = UPPER(?)
              )
            """,
            (lama, baru),
        )
        cursor.execute(
            """
            UPDATE invoice_resi
            SET no_resi = ?, kode_cabang = ?
            WHERE UPPER(no_resi) = UPPER(?)
            """,
            (baru, cabang, lama),
        )
    except sqlite3.OperationalError as exc:
        # Kompatibilitas hanya untuk database legacy yang memang belum
        # memiliki tabel relasi. Error SQL lain harus membatalkan transaksi.
        if "no such table: invoice_resi" not in str(exc).lower():
            raise

    cursor.execute(
        "DELETE FROM data_resi WHERE no_resi = ? AND kode_cabang = ?",
        (lama, cabang),
    )
    if cursor.rowcount != 1:
        raise KesalahanTransaksiResi(
            KODE_DB_ERROR, f"Resi lama {lama} gagal diselesaikan saat perubahan nomor."
        )

    return baru

# ==============================================================================
# 03. RESI — FORM INPUT, HISTORI, DETAIL, AUDIT & TRANSAKSI
# ==============================================================================

def cari_histori_resi(keyword, kode_cabang):
    """Pencarian live histori resi pada cabang aktif."""

    keyword = str(keyword or "").strip().lower()
    kode_cabang = str(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()
    pattern = f"%{keyword}%"
    try:
        return _fetchall(
            """
            SELECT no_resi, penerima
            FROM data_resi
            WHERE kode_cabang = ?
              AND (
                  LOWER(COALESCE(no_resi, '')) LIKE ?
                  OR LOWER(COALESCE(pengirim, '')) LIKE ?
                  OR LOWER(COALESCE(penerima, '')) LIKE ?
              )
            ORDER BY rowid DESC
            LIMIT 50
            """,
            (kode_cabang, pattern, pattern, pattern),
        )
    except sqlite3.Error as exc:
        logger.error("[Resi] Gagal mencari histori: %s", exc)
        return []

def ambil_histori_resi_by_tanggal(tgl_pilih, kode_cabang):
    """Memuat daftar resi di sidebar kanan berdasarkan kalender yang dipilih"""
    return _fetchall(
        "SELECT no_resi, penerima FROM data_resi WHERE tanggal_masuk = ? AND kode_cabang = ? ORDER BY rowid ASC",
        (tgl_pilih, kode_cabang),
    )

def ambil_histori_resi_by_rentang(
    tanggal_awal, tanggal_akhir, keyword="", kode_cabang=None
):
    """Ambil histori Resi dalam satu rentang tanggal, opsional berdasarkan keyword.

    Filter periode dan pencarian dikerjakan langsung di SQLite agar caller tidak
    perlu mengambil data di luar rentang lalu memfilternya di Python. Tanggal
    disertakan pada hasil untuk kebutuhan grouping bulan di panel histori.
    """

    tanggal_awal = str(tanggal_awal or "").strip()
    tanggal_akhir = str(tanggal_akhir or "").strip()
    cabang = _kode_cabang_aktif(kode_cabang)
    keyword = str(keyword or "").strip().casefold()

    if not tanggal_awal or not tanggal_akhir or tanggal_awal > tanggal_akhir:
        return []

    query = [
        "SELECT no_resi, penerima, tanggal_masuk",
        "FROM data_resi",
        "WHERE kode_cabang = ?",
        "  AND tanggal_masuk BETWEEN ? AND ?",
    ]
    params = [cabang, tanggal_awal, tanggal_akhir]

    if keyword:
        pola = f"%{keyword}%"
        query.append(
            "  AND (LOWER(COALESCE(no_resi, '')) LIKE ? "
            "OR LOWER(COALESCE(pengirim, '')) LIKE ? "
            "OR LOWER(COALESCE(penerima, '')) LIKE ?)"
        )
        params.extend((pola, pola, pola))

    query.append("ORDER BY tanggal_masuk ASC, rowid ASC")

    try:
        return _fetchall("\n".join(query), tuple(params))
    except sqlite3.Error as exc:
        logger.error("[Resi] Gagal mengambil histori rentang: %s", exc)
        return []

def ambil_identitas_pembuat_resi(no_resi):
    """Ambil snapshot identitas pembuat/perubahan Resi."""
    try:
        row = _fetchone(
            """
            SELECT created_by_user_id, created_by_username, created_by_name,
                   updated_by_user_id, updated_by_username, updated_by_name
            FROM data_resi
            WHERE no_resi = ?
            LIMIT 1
            """,
            (str(no_resi or "").strip().upper(),),
        )
        if not row:
            return {}
        return {
            "created_by_user_id": row[0],
            "created_by_username": row[1],
            "created_by_name": row[2],
            "updated_by_user_id": row[3],
            "updated_by_username": row[4],
            "updated_by_name": row[5],
        }
    except sqlite3.Error:
        logger.exception("[Resi] Gagal membaca identitas pembuat %s", no_resi)
        return {}

def ambil_detail_resi(no_resi):
    """Mengambil data lengkap satu resi untuk keperluan Cetak / Preview Nota.

    Detail barang dibaca dari data_resi_detail. Kolom rincian_json tetap
    dikembalikan pada posisi lama sebagai representasi kompatibilitas untuk UI
    dan modul cetak yang sudah ada.
    """

    conn = None
    try:
        conn = get_db_connection()
        row = conn.execute(
            """
            SELECT tanggal_masuk,
                   pengirim,
                   hp_pengirim,
                   alamat_pengirim,
                   penerima,
                   hp_penerima,
                   alamat_penerima,
                   kota_tujuan,
                   nama_barang,
                   berat,
                   koli,
                   cbm,
                   total_ongkir,
                   pembayaran,
                   rincian_json,
                   ongkir_per_kg,
                   ongkir_per_cbm,
                   kota_asal,
                   jenis_pajak,
                   subtotal_ongkir,
                   revision,
                   created_by_user_id,
                   created_by_username,
                   created_by_name,
                   updated_by_user_id,
                   updated_by_username,
                   updated_by_name
            FROM data_resi
            WHERE no_resi = ?
            """,
            (no_resi,),
        ).fetchone()
        if row is None:
            return None

        rincian = _ambil_rincian_resi_cursor(conn.cursor(), no_resi)
        if rincian:
            hasil = list(row)
            hasil[14] = json.dumps(rincian, ensure_ascii=False)
            return tuple(hasil)
        return row
    finally:
        _close(conn)

def _autocomplete_db_fingerprint(cursor, kode_cabang):
    """Fingerprint ringan untuk mendeteksi master yang berubah di SQLite.

    Sync worker menulis langsung ke SQLite, sehingga cache Python tidak menerima
    callback. Kombinasi jumlah + MAX(updated_at) + MAX(sync_id) cukup murah dan
    menangkap insert/update/delete/sync ulang tanpa menghapus cache setiap query.
    """
    row = cursor.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM master_pengirim
                WHERE kode_cabang = ?
                  AND TRIM(COALESCE(nama, '')) <> ''
            ) AS pengirim_count,
            COALESCE((
                SELECT MAX(updated_at)
                FROM master_pengirim
                WHERE kode_cabang = ?
                  AND TRIM(COALESCE(nama, '')) <> ''
            ), '') AS pengirim_updated,
            COALESCE((
                SELECT MAX(sync_id)
                FROM master_pengirim
                WHERE kode_cabang = ?
                  AND TRIM(COALESCE(nama, '')) <> ''
            ), '') AS pengirim_sync,
            (
                SELECT COUNT(*)
                FROM master_penerima
                WHERE kode_cabang = ?
                  AND TRIM(COALESCE(nama, '')) <> ''
            ) AS penerima_count,
            COALESCE((
                SELECT MAX(updated_at)
                FROM master_penerima
                WHERE kode_cabang = ?
                  AND TRIM(COALESCE(nama, '')) <> ''
            ), '') AS penerima_updated,
            COALESCE((
                SELECT MAX(sync_id)
                FROM master_penerima
                WHERE kode_cabang = ?
                  AND TRIM(COALESCE(nama, '')) <> ''
            ), '') AS penerima_sync
        """,
        (kode_cabang,) * 6,
    ).fetchone()
    return tuple(row or ())


def clear_autocomplete_cache(kode_cabang=None):
    """Invalidate cache autocomplete global atau hanya satu cabang."""
    if kode_cabang is None:
        _AUTOCOMPLETE_CACHE.clear()
        return
    _AUTOCOMPLETE_CACHE.pop(
        str(kode_cabang or '').strip().upper(),
        None,
    )


def ambil_data_autocomplete(kode_cabang):
    """Menyediakan daftar Pengirim/Penerima yang selalu konsisten dengan SQLite lokal."""
    kode_cabang = str(kode_cabang or CURRENT_SESSION.get(
        'kode_cabang',
        'PUSAT',
    )).strip().upper()

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        fingerprint = _autocomplete_db_fingerprint(cursor, kode_cabang)
        cache_key = kode_cabang
        sekarang = time.monotonic()
        cached = _AUTOCOMPLETE_CACHE.get(cache_key)
        if cached:
            cache_time, cache_fingerprint, cache_data = cached
            if (
                sekarang - cache_time < _AUTOCOMPLETE_CACHE_TTL
                and cache_fingerprint == fingerprint
            ):
                return cache_data

        pengirim, penerima = [], []
        load_ok = True

        try:
            cursor.execute("""
                SELECT DISTINCT TRIM(nama)
                FROM master_pengirim
                WHERE TRIM(COALESCE(nama, '')) != ''
                  AND kode_cabang = ?
                ORDER BY TRIM(nama) COLLATE NOCASE ASC
            """, (kode_cabang,))
            pengirim = [str(r[0]).strip().upper() for r in cursor.fetchall() if r[0]]
        except sqlite3.OperationalError as e:
            load_ok = False
            print(f"[Autocomplete Service] Gagal memuat pengirim: {e}")

        try:
            cursor.execute("""
                SELECT DISTINCT TRIM(nama)
                FROM master_penerima
                WHERE TRIM(COALESCE(nama, '')) != ''
                  AND kode_cabang = ?
                ORDER BY TRIM(nama) COLLATE NOCASE ASC
            """, (kode_cabang,))
            penerima = [str(r[0]).strip().upper() for r in cursor.fetchall() if r[0]]
        except sqlite3.OperationalError as e:
            load_ok = False
            print(f"[Autocomplete Service] Gagal memuat penerima: {e}")

        hasil = (pengirim, penerima)
        if load_ok:
            _AUTOCOMPLETE_CACHE[cache_key] = (
                time.monotonic(),
                fingerprint,
                hasil,
            )
        return hasil

    except Exception as e:
        print(f"[Autocomplete Service] Critical Error: {e}")
        return [], []
    finally:
        _close(conn)

def ambil_detail_pengirim(name_clean, kode_cabang):
    """Autofill detail profil pengirim saat nama dipilih di form resi"""
    return _fetchone(
        """
        SELECT no_hp, alamat, kota
        FROM master_pengirim
        WHERE TRIM(UPPER(nama)) = TRIM(UPPER(?))
          AND kode_cabang = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (name_clean, kode_cabang),
    )

def ambil_detail_penerima(nama_penerima, kode_cabang):
    """Autofill detail profil penerima saat nama dipilih di form resi"""
    return _fetchone(
        """
        SELECT no_hp, alamat, kota, provinsi
        FROM master_penerima
        WHERE TRIM(UPPER(nama)) = TRIM(UPPER(?))
          AND kode_cabang = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (nama_penerima, kode_cabang),
    )

def _ambil_sekuens_resi_cursor(cursor, kode_cabang, pref):
    """Hitung sequence Resi memakai cursor aktif agar dapat dipakai secara atomic."""
    base_number = 0
    cursor.execute(
        "SELECT start_seq_json FROM data_cabang WHERE kode_cabang = ?",
        (kode_cabang,),
    )
    row = cursor.fetchone()
    if row and row[0]:
        try:
            seq_dict = json.loads(row[0])
            base_number = seq_dict.get(pref, seq_dict.get("DEFAULT", 0))
        except Exception:
            pass

    cursor.execute(
        "SELECT no_resi FROM data_resi WHERE no_resi LIKE ? AND kode_cabang = ?",
        (f"{pref}%", kode_cabang),
    )
    rows = cursor.fetchall()

    max_num = 0
    for r in rows:
        no_resi_db = str(r[0] or "").strip()
        if no_resi_db.upper().startswith(str(pref).upper()):
            bagian_counter = no_resi_db[len(str(pref)):]
        else:
            bagian_counter = no_resi_db

        m = re.findall(r'\d+', bagian_counter)
        if m:
            try:
                max_num = max(max_num, int(m[-1]))
            except ValueError:
                pass

    return base_number, max_num


def ambil_sekuens_resi(kode_cabang, pref):
    """Menghitung nomor urut/counter resi otomatis berdasarkan cabang dan tipe transaksi."""

    conn = None
    try:
        conn = get_db_connection()
        return _ambil_sekuens_resi_cursor(conn.cursor(), kode_cabang, pref)
    finally:
        _close(conn)


def _nomor_resi_atomic_cursor(cursor, data, kode_cabang, fallback_no_resi):
    """Alokasikan nomor RESI fixed di dalam transaction penyimpanan."""
    cfg = data.get("_atomic_resi")
    if not isinstance(cfg, dict):
        return fallback_no_resi
    wilayah = str(cfg.get("wilayah") or data.get("provinsi_tujuan") or "").strip().upper()
    suffix = str(cfg.get("suffix") or "").strip().upper()
    try:
        result = numbering_service.allocate_number_cursor(
            cursor, "RESI", kode_cabang,
            wilayah=wilayah, tanggal=data.get("tanggal_masuk"), suffix=suffix,
        )
        return result.nomor
    except Exception as exc:
        logger.error("[Resi] Gagal alokasi numbering fixed: %s", exc)
        return fallback_no_resi

def _insert_resi_baru(cursor, data, no_resi, kode_cabang):
    cursor.execute(
        """
        INSERT INTO data_resi (
            no_resi, kode_cabang, tanggal_masuk,
            pengirim, hp_pengirim, alamat_pengirim, kota_asal,
            penerima, hp_penerima, alamat_penerima, kota_tujuan,
            nama_barang, berat, koli, cbm,
            ongkir_per_kg, ongkir_per_cbm, subtotal_ongkir, jenis_pajak, total_ongkir,
            pembayaran, status_resi, foto_bukti, rincian_json, sync_id,
            created_by_user_id, created_by_username, created_by_name,
            updated_by_user_id, updated_by_username, updated_by_name, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                'DI GUDANG', 'BELUM', ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            no_resi, kode_cabang, data.get("tanggal_masuk"),
            str(data.get("pengirim", "")).strip().upper(),
            str(data.get("hp_pengirim", "")).strip(),
            str(data.get("alamat_pengirim", "")).strip().upper(),
            str(data.get("kota_asal", "")).strip().upper(),
            str(data.get("penerima", "")).strip().upper(),
            str(data.get("hp_penerima", "")).strip(),
            str(data.get("alamat_penerima", "")).strip().upper(),
            str(data.get("kota_tujuan", "")).strip().upper(),
            str(data.get("nama_barang", "")).strip().upper(),
            data.get("berat", 0), data.get("koli", ""), data.get("cbm", 0),
            data.get("ongkir_per_kg", 0), data.get("ongkir_per_cbm", 0),
            data.get("subtotal_ongkir", 0),
            str(data.get("jenis_pajak", "NONPAJAK")).strip().upper() or "NONPAJAK",
            data.get("total_ongkir", 0),
            str(data.get("pembayaran", "")).strip().upper(),
            data.get("rincian_json", "[]"),
            str(data.get("sync_id") or uuid.uuid4()),
            *_audit_actor_values(),
            *_audit_actor_values(),
        ),
    )

def _upsert_buku_gudang_resi(cursor, data, no_resi, kode_cabang):
    cursor.execute(
        """
        INSERT INTO buku_gudang (
            id_gudang, kode_cabang, tanggal, no_resi,
            jenis, status_resi, sync_id, updated_at
        )
        VALUES (?, ?, ?, ?, 'BARANG MASUK', 'DI GUDANG', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id_gudang) DO UPDATE SET
            kode_cabang = excluded.kode_cabang,
            tanggal = excluded.tanggal,
            no_resi = excluded.no_resi,
            jenis = excluded.jenis,
            status_resi = excluded.status_resi,
            deleted_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            f"GDG-{no_resi}",
            kode_cabang,
            data.get("tanggal_masuk"),
            no_resi,
            str(uuid.uuid4()),
        ),
    )

def _upsert_master_pengirim_resi(cursor, data, kode_cabang):
    nama = str(data.get("pengirim", "")).strip().upper()
    if not nama:
        return

    row = cursor.execute(
        """
        SELECT id_pengirim FROM master_pengirim
        WHERE kode_cabang = ? AND TRIM(UPPER(nama)) = TRIM(UPPER(?))
        ORDER BY updated_at DESC LIMIT 1
        """,
        (kode_cabang, nama),
    ).fetchone()
    values = (
        nama,
        str(data.get("hp_pengirim", "")).strip() or None,
        str(data.get("alamat_pengirim", "")).strip().upper(),
        str(data.get("kota_asal", "")).strip().upper(),
    )
    if row:
        cursor.execute(
            """
            UPDATE master_pengirim
            SET nama = ?, no_hp = ?, alamat = ?, kota = ?,
                is_synced = 0, updated_at = CURRENT_TIMESTAMP
            WHERE id_pengirim = ? AND kode_cabang = ?
            """,
            values + (row[0], kode_cabang),
        )
        return

    cursor.execute(
        """
        INSERT INTO master_pengirim (
            id_pengirim, kode_cabang, nama, no_hp, alamat, kota, is_synced
        ) VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (f"SHP-{uuid.uuid4().hex[:12].upper()}", kode_cabang) + values,
    )

def _upsert_master_penerima_resi(cursor, data, kode_cabang):
    nama = str(data.get("penerima", "")).strip().upper()
    if not nama:
        return

    kota_tujuan = str(data.get("kota_tujuan", "")).strip().upper()
    if " - " in kota_tujuan:
        provinsi_dari_kota, kota = [bagian.strip() for bagian in kota_tujuan.split(" - ", 1)]
    else:
        provinsi_dari_kota, kota = "", kota_tujuan

    provinsi = (
        str(data.get("provinsi_tujuan", "")).strip().upper()
        or provinsi_dari_kota
        or None
    )
    hp = str(data.get("hp_penerima", "")).strip() or None
    alamat = str(data.get("alamat_penerima", "")).strip().upper()
    pembayaran = (
        str(data.get("pembayaran", "TF / INVOICE")).strip().upper()
        or "TF / INVOICE"
    )
    row = cursor.execute(
        """
        SELECT id_penerima FROM master_penerima
        WHERE kode_cabang = ? AND TRIM(UPPER(nama)) = TRIM(UPPER(?))
        ORDER BY updated_at DESC LIMIT 1
        """,
        (kode_cabang, nama),
    ).fetchone()
    total_transaksi = cursor.execute(
        """
        SELECT COUNT(*) FROM data_resi
        WHERE kode_cabang = ? AND TRIM(UPPER(penerima)) = TRIM(UPPER(?))
        """,
        (kode_cabang, nama),
    ).fetchone()[0]

    if row:
        cursor.execute(
            """
            UPDATE master_penerima
            SET nama = ?, no_hp = ?, alamat = ?, kota = ?, provinsi = ?,
                pembayaran = ?, total_transaksi = ?, is_synced = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id_penerima = ? AND kode_cabang = ?
            """,
            (nama, hp, alamat, kota, provinsi, pembayaran,
             total_transaksi, row[0], kode_cabang),
        )
        return

    cursor.execute(
        """
        INSERT INTO master_penerima (
            id_penerima, kode_cabang, nama, no_hp, alamat, kota,
            provinsi, total_transaksi, pembayaran, is_synced
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (f"CNE-{uuid.uuid4().hex[:12].upper()}", kode_cabang, nama, hp,
         alamat, kota, provinsi, total_transaksi, pembayaran),
    )

def _refresh_total_transaksi_master_penerima(cursor, nama, kode_cabang):
    """Sinkronkan counter master penerima setelah nama penerima resi berubah."""
    nama = _upper(nama)
    if not nama:
        return

    total = cursor.execute(
        """
        SELECT COUNT(*) FROM data_resi
        WHERE kode_cabang = ? AND TRIM(UPPER(COALESCE(penerima, ''))) = ?
        """,
        (kode_cabang, nama),
    ).fetchone()[0]
    cursor.execute(
        """
        UPDATE master_penerima
        SET total_transaksi = ?, is_synced = 0, updated_at = CURRENT_TIMESTAMP
        WHERE kode_cabang = ? AND TRIM(UPPER(COALESCE(nama, ''))) = ?
        """,
        (total, kode_cabang, nama),
    )

def _normalisasi_rincian_ringkas(data):
    """Bangun satu baris rincian dari kolom ringkasan data_resi.

    Dipakai bila detail barang diedit dari Buku Gudang, karena editor Buku Gudang
    hanya memiliki kolom ringkasan dan tidak mengetahui pembagian multi-item.
    """
    return json.dumps(
        [{
            "nama": str(data.get("nama_barang", "") or "").strip().upper(),
            "qty": str(data.get("koli", "") or "").strip(),
            "berat": str(data.get("berat", "") or "").strip(),
            "cbm": str(data.get("cbm", "") or "").strip(),
        }],
        ensure_ascii=False,
    )

def _normalisasi_rincian_resi(data):
    """Ambil rincian barang terstruktur, termasuk baris parsial tanpa nama.

    Sebuah baris dipertahankan bila salah satu dari nama/qty/berat/cbm berisi
    data. Ini memungkinkan Tab Resi menyimpan kombinasi input apa pun tanpa
    memaksa nama barang sebagai kunci keberadaan detail.
    """
    rincian = data.get("rincian")
    if not isinstance(rincian, list):
        raw = data.get("rincian_json")
        if raw:
            try:
                rincian = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                rincian = []
        else:
            rincian = []

    hasil = []
    for item in rincian or []:
        if not isinstance(item, dict):
            continue
        nama = str(item.get("nama", item.get("nama_barang", "")) or "").strip().upper()
        qty = str(item.get("qty", item.get("koli", "")) or "").strip()
        berat = item.get("berat", 0) or 0
        cbm = item.get("cbm", 0) or 0
        if not nama and not qty and _angka_detail(berat) == 0 and _angka_detail(cbm) == 0:
            continue
        hasil.append({
            "nama": nama,
            "qty": qty,
            "berat": berat,
            "cbm": cbm,
        })

    if hasil:
        return hasil

    nama_ringkas = str(data.get("nama_barang", "") or "").strip().upper()
    qty_ringkas = str(data.get("koli", "") or "").strip()
    berat_ringkas = data.get("berat", 0) or 0
    cbm_ringkas = data.get("cbm", 0) or 0
    if (
        not nama_ringkas
        and not qty_ringkas
        and _angka_detail(berat_ringkas) == 0
        and _angka_detail(cbm_ringkas) == 0
    ):
        return []
    return [{
        "nama": nama_ringkas,
        "qty": qty_ringkas,
        "berat": berat_ringkas,
        "cbm": cbm_ringkas,
    }]

def _ganti_rincian_resi(cursor, no_resi, data):
    """Ganti seluruh detail barang satu Resi secara atomic."""
    rincian = _normalisasi_rincian_resi(data)
    cursor.execute("DELETE FROM data_resi_detail WHERE no_resi = ?", (no_resi,))
    for urutan, item in enumerate(rincian, start=1):
        cursor.execute(
            """
            INSERT INTO data_resi_detail (
                no_resi, urutan, nama_barang, koli, berat, cbm, sync_id,
                created_by_user_id, created_by_username, created_by_name,
                updated_by_user_id, updated_by_username, updated_by_name, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                no_resi, urutan, item["nama"], item["qty"],
                item["berat"], item["cbm"], str(uuid.uuid4()),
                *_audit_actor_values(),
                *_audit_actor_values(),
            ),
        )
    return rincian

def _ambil_rows_rincian_resi(cursor, no_resi):
    return cursor.execute(
        """
        SELECT nama_barang, koli, berat, cbm
        FROM data_resi_detail
        WHERE no_resi = ?
        ORDER BY urutan ASC, id_detail ASC
        """,
        (no_resi,),
    ).fetchall()

def _rows_ke_rincian_resi(rows):
    return [
        {
            "nama": str(row[0] or "").strip().upper(),
            "qty": str(row[1] or "").strip(),
            "berat": str(row[2] or "") if row[2] not in (None, 0, 0.0) else "",
            "cbm": str(row[3] or "") if row[3] not in (None, 0, 0.0) else "",
        }
        for row in rows
    ]

def _ambil_rincian_resi_cursor(cursor, no_resi):
    return _rows_ke_rincian_resi(_ambil_rows_rincian_resi(cursor, no_resi))

def _angka_detail(nilai):
    try:
        return float(nilai or 0)
    except (TypeError, ValueError):
        return 0.0

def _koli_detail(nilai):
    teks = str(nilai or "").strip().replace(".", "").replace(",", ".")
    try:
        return int(float(teks)) if teks else 0
    except (TypeError, ValueError):
        return 0

def _sinkronkan_ringkasan_resi_dari_detail(cursor, no_resi, kode_cabang):
    """Jaga kolom ringkasan data_resi untuk Manifest/Invoice/kode lama."""
    rows = _ambil_rows_rincian_resi(cursor, no_resi)
    if not rows:
        return

    nama = [str(row[0] or "").strip().upper() for row in rows if str(row[0] or "").strip()]
    total_koli = sum(_koli_detail(row[1]) for row in rows)
    total_berat = sum(_angka_detail(row[2]) for row in rows)
    total_cbm = sum(_angka_detail(row[3]) for row in rows)
    rincian = _rows_ke_rincian_resi(rows)
    cursor.execute(
        """
        UPDATE data_resi
        SET nama_barang = ?, koli = ?, berat = ?, cbm = ?, rincian_json = ?,
            is_synced = 0, updated_at = CURRENT_TIMESTAMP
        WHERE no_resi = ? AND kode_cabang = ?
        """,
        (
            ", ".join(nama), str(total_koli) if total_koli > 0 else "",
            total_berat, total_cbm, json.dumps(rincian, ensure_ascii=False),
            no_resi, kode_cabang,
        ),
    )

_AUDIT_RESI_HEADER_FIELDS = (
    "tanggal_masuk", "tanggal_keluar", "status_resi", "truk",
    "pengirim", "hp_pengirim", "alamat_pengirim", "kota_asal",
    "penerima", "hp_penerima", "alamat_penerima", "kota_tujuan",
    "ongkir_per_kg", "ongkir_per_cbm", "subtotal_ongkir", "jenis_pajak",
    "total_ongkir", "pembayaran", "ket_buku_gudang",
    "no_manifest", "ket_manifest",
)

_AUDIT_RESI_SCHEMA_SQL = """
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
"""

def _pastikan_tabel_audit_resi(cursor):
    """Pastikan tabel audit tersedia juga pada database testing yang sudah ada."""
    cursor.execute(_AUDIT_RESI_SCHEMA_SQL)
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_resi_audit_nomor_lama
        ON resi_audit (no_resi_lama, kode_cabang, created_at)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_resi_audit_nomor_baru
        ON resi_audit (no_resi_baru, kode_cabang, created_at)
        """
    )

def _snapshot_resi_untuk_audit(cursor, no_resi, kode_cabang):
    """Ambil snapshot field editable + detail barang tanpa field turunan ringkasan."""
    nomor = str(no_resi or "").strip().upper()
    cabang = str(kode_cabang or "").strip().upper()
    if not nomor or not cabang:
        return None

    kolom = ", ".join(_AUDIT_RESI_HEADER_FIELDS)
    row = cursor.execute(
        f"SELECT {kolom}, revision FROM data_resi WHERE no_resi = ? AND kode_cabang = ? LIMIT 1",
        (nomor, cabang),
    ).fetchone()
    if row is None:
        return None

    header = {
        field: row[index]
        for index, field in enumerate(_AUDIT_RESI_HEADER_FIELDS)
    }
    revision = int(row[len(_AUDIT_RESI_HEADER_FIELDS)] or 0)
    detail_rows = cursor.execute(
        """
        SELECT urutan, nama_barang, koli, berat, cbm
        FROM data_resi_detail
        WHERE no_resi = ?
        ORDER BY urutan ASC, id_detail ASC
        """,
        (nomor,),
    ).fetchall()
    barang = [
        {
            "urutan": int(detail[0] or 0),
            "nama_barang": detail[1],
            "koli": detail[2],
            "berat": detail[3],
            "cbm": detail[4],
        }
        for detail in detail_rows
    ]
    return {
        "header": header,
        "barang": barang,
        "revision": revision,
    }

def _perubahan_snapshot_resi(snapshot_lama, snapshot_baru):
    """Hasilkan hanya field yang benar-benar berubah untuk disimpan sebagai JSON."""
    if not snapshot_lama or not snapshot_baru:
        return {}

    perubahan_header = {}
    header_lama = snapshot_lama.get("header", {})
    header_baru = snapshot_baru.get("header", {})
    for field in _AUDIT_RESI_HEADER_FIELDS:
        sebelum = header_lama.get(field)
        sesudah = header_baru.get(field)
        if sebelum != sesudah:
            perubahan_header[field] = {
                "sebelum": sebelum,
                "sesudah": sesudah,
            }

    perubahan = {}
    if perubahan_header:
        perubahan["header"] = perubahan_header

    barang_lama = snapshot_lama.get("barang", [])
    barang_baru = snapshot_baru.get("barang", [])
    if barang_lama != barang_baru:
        perubahan["barang"] = {
            "sebelum": barang_lama,
            "sesudah": barang_baru,
        }
    return perubahan

def _catat_audit_resi(
    cursor, *, kode_cabang, no_resi_lama, no_resi_baru,
    sumber, snapshot_lama, snapshot_baru,
):
    """Catat audit di transaksi DB yang sama; tidak membuat log bila data identik."""
    nomor_lama = str(no_resi_lama or "").strip().upper()
    nomor_baru = str(no_resi_baru or no_resi_lama or "").strip().upper()
    perubahan = _perubahan_snapshot_resi(snapshot_lama, snapshot_baru)
    if not perubahan and nomor_lama == nomor_baru:
        return False

    _pastikan_tabel_audit_resi(cursor)
    username = str(CURRENT_SESSION.get("username") or "SYSTEM").strip().upper() or "SYSTEM"
    cursor.execute(
        """
        INSERT INTO resi_audit (
            kode_cabang, no_resi_lama, no_resi_baru,
            username, sumber, revision_sebelum, revision_sesudah,
            perubahan_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(kode_cabang or "").strip().upper(),
            nomor_lama,
            nomor_baru,
            username,
            str(sumber or "SYSTEM").strip().upper() or "SYSTEM",
            snapshot_lama.get("revision") if snapshot_lama else None,
            snapshot_baru.get("revision") if snapshot_baru else None,
            json.dumps(perubahan, ensure_ascii=False, separators=(",", ":")),
        ),
    )
    return True

def ambil_audit_resi(no_resi, kode_cabang=None, limit=200):
    """Ambil audit manual Edit Resi/Buku Gudang untuk nomor atau varian suffix pajaknya."""

    cabang = str(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()
    kandidat = sorted(_varian_nomor_resi_pajak(no_resi))
    if not kandidat or not cabang:
        return []
    try:
        batas = max(1, min(int(limit or 200), 2000))
    except (TypeError, ValueError):
        batas = 200

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _pastikan_tabel_audit_resi(cursor)
        placeholders = ",".join("?" for _ in kandidat)
        params = [cabang] + kandidat + kandidat + [batas]
        return cursor.execute(
            f"""
            SELECT id_audit, no_resi_lama, no_resi_baru, username, sumber,
                   revision_sebelum, revision_sesudah, perubahan_json, created_at
            FROM resi_audit
            WHERE kode_cabang = ?
              AND (
                    no_resi_lama IN ({placeholders})
                 OR no_resi_baru IN ({placeholders})
              )
            ORDER BY id_audit DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    except sqlite3.Error as exc:
        logger.error("[Audit Resi] Gagal mengambil histori %s: %s", no_resi, exc)
        return []
    finally:
        if conn:
            conn.commit()
            conn.close()

def simpan_transaksi_resi(data):
    """Menyimpan resi, buku gudang, serta master pengirim/penerima dalam satu transaksi."""

    no_resi = str(data.get("no_resi", "")).strip().upper()
    kode_cabang = str(
        data.get("kode_cabang") or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()
    if not no_resi:
        return False, KesalahanTransaksiResi(KODE_DB_ERROR, "Nomor resi tidak boleh kosong.")
    if not kode_cabang:
        return False, KesalahanTransaksiResi(KODE_DB_ERROR, "Kode cabang tidak boleh kosong.")
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError as exc:
        return False, KesalahanTransaksiResi(KODE_DB_ERROR, str(exc))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        # Bila caller mengirim konteks atomic, nomor final baru ditentukan
        # setelah write-lock SQLite didapat. Caller lama tetap memakai no_resi
        # yang dikirim sehingga kontrak fungsi ini tetap kompatibel.
        no_resi = _nomor_resi_atomic_cursor(
            cursor, data, kode_cabang, no_resi
        )
        if not no_resi:
            conn.rollback()
            return False, KesalahanTransaksiResi(
                KODE_DB_ERROR, "Nomor resi tidak boleh kosong."
            )

        if cursor.execute(
            "SELECT 1 FROM data_resi WHERE no_resi = ? LIMIT 1", (no_resi,)
        ).fetchone():
            conn.rollback()
            return False, KesalahanTransaksiResi(
                KODE_RESI_DUPLIKAT, "Nomor resi sudah ada di database."
            )

        _insert_resi_baru(cursor, data, no_resi, kode_cabang)
        _ganti_rincian_resi(cursor, no_resi, data)
        _sinkronkan_ringkasan_resi_dari_detail(cursor, no_resi, kode_cabang)
        _upsert_buku_gudang_resi(cursor, data, no_resi, kode_cabang)
        _upsert_master_pengirim_resi(cursor, data, kode_cabang)
        _upsert_master_penerima_resi(cursor, data, kode_cabang)
        conn.commit()
        return True, ""

    except sqlite3.IntegrityError as exc:
        _rollback(conn)
        message = str(exc)
        if "data_resi.no_resi" in message:
            return False, KesalahanTransaksiResi(
                KODE_RESI_DUPLIKAT, "Nomor resi sudah ada di database."
            )
        logger.exception("IntegrityError saat menyimpan transaksi resi")
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR, f"Gagal menyimpan karena aturan database: {message}"
        )
    except Exception as exc:
        _rollback(conn)
        logger.exception("Gagal menyimpan transaksi resi")
        return False, KesalahanTransaksiResi(KODE_DB_ERROR, f"Gagal menyimpan resi: {exc}")
    finally:
        _close(conn)

def _update_transaksi_resi_cursor(
    cursor, data, no_resi_lama, no_resi_baru, kode_cabang, jenis_pajak
):
    """Jalankan isi transaksi edit Resi memakai cursor aktif."""
    row_lama = cursor.execute(
        """
        SELECT penerima, revision
        FROM data_resi
        WHERE no_resi = ? AND kode_cabang = ?
        LIMIT 1
        """,
        (no_resi_lama, kode_cabang),
    ).fetchone()
    if row_lama is None:
        return None, None, KesalahanTransaksiResi(
            KODE_DB_ERROR,
            f"Resi {no_resi_lama} tidak ditemukan pada cabang {kode_cabang}.",
        )

    revision_db = int(row_lama[1] or 0)
    snapshot_audit_lama = _snapshot_resi_untuk_audit(
        cursor, no_resi_lama, kode_cabang
    )
    revision_diharapkan = data.get("revision")
    if revision_diharapkan is not None:
        try:
            revision_diharapkan = int(revision_diharapkan)
        except (TypeError, ValueError):
            return None, None, KesalahanTransaksiResi(
                KODE_DB_ERROR, "Revision Resi tidak valid."
            )
        if revision_db != revision_diharapkan:
            return None, None, KesalahanTransaksiResi(
                KODE_RESI_KONFLIK,
                "Data Resi telah berubah dari modul lain. Muat ulang data sebelum menyimpan.",
            )

    no_resi = no_resi_lama
    if no_resi_baru != no_resi_lama:
        no_resi = _rename_resi_aman(
            cursor, no_resi_lama, no_resi_baru, kode_cabang
        )

    cursor.execute(
        """
        UPDATE data_resi
        SET tanggal_masuk = ?,
            pengirim = ?, hp_pengirim = ?, alamat_pengirim = ?, kota_asal = ?,
            penerima = ?, hp_penerima = ?, alamat_penerima = ?, kota_tujuan = ?,
            nama_barang = ?, berat = ?, koli = ?, cbm = ?,
            ongkir_per_kg = ?, ongkir_per_cbm = ?, subtotal_ongkir = ?,
            jenis_pajak = ?, total_ongkir = ?,
            pembayaran = ?, rincian_json = ?,
            is_synced = 0, revision = revision + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE no_resi = ? AND kode_cabang = ?
        """,
        (
            data.get("tanggal_masuk"),
            str(data.get("pengirim", "")).strip().upper(),
            str(data.get("hp_pengirim", "")).strip(),
            str(data.get("alamat_pengirim", "")).strip().upper(),
            str(data.get("kota_asal", "")).strip().upper(),
            str(data.get("penerima", "")).strip().upper(),
            str(data.get("hp_penerima", "")).strip(),
            str(data.get("alamat_penerima", "")).strip().upper(),
            str(data.get("kota_tujuan", "")).strip().upper(),
            str(data.get("nama_barang", "")).strip().upper(),
            data.get("berat", 0),
            data.get("koli", ""),
            data.get("cbm", 0),
            data.get("ongkir_per_kg", 0),
            data.get("ongkir_per_cbm", 0),
            data.get("subtotal_ongkir", 0),
            jenis_pajak,
            data.get("total_ongkir", 0),
            str(data.get("pembayaran", "")).strip().upper(),
            data.get("rincian_json", "[]"),
            no_resi,
            kode_cabang,
        ),
    )
    if cursor.rowcount == 0:
        return None, None, KesalahanTransaksiResi(
            KODE_DB_ERROR, f"Resi {no_resi} tidak berhasil diperbarui."
        )

    _ganti_rincian_resi(cursor, no_resi, data)
    _sinkronkan_ringkasan_resi_dari_detail(cursor, no_resi, kode_cabang)
    cursor.execute(
        """
        UPDATE buku_gudang
        SET tanggal = ?, is_synced = 0, updated_at = CURRENT_TIMESTAMP
        WHERE no_resi = ? AND kode_cabang = ?
        """,
        (data.get("tanggal_masuk"), no_resi, kode_cabang),
    )

    _upsert_master_pengirim_resi(cursor, data, kode_cabang)
    _upsert_master_penerima_resi(cursor, data, kode_cabang)

    penerima_lama = str(row_lama[0] or "").strip().upper()
    penerima_baru = str(data.get("penerima", "") or "").strip().upper()
    if penerima_lama and penerima_lama != penerima_baru:
        _refresh_total_transaksi_master_penerima(cursor, penerima_lama, kode_cabang)
    if penerima_baru:
        _refresh_total_transaksi_master_penerima(cursor, penerima_baru, kode_cabang)

    snapshot_audit_baru = _snapshot_resi_untuk_audit(cursor, no_resi, kode_cabang)
    _catat_audit_resi(
        cursor,
        kode_cabang=kode_cabang,
        no_resi_lama=no_resi_lama,
        no_resi_baru=no_resi,
        sumber="TAB_RESI",
        snapshot_lama=snapshot_audit_lama,
        snapshot_baru=snapshot_audit_baru,
    )
    return no_resi, revision_db, None

def update_transaksi_resi(data):
    """Perbarui data input Resi dan suffix pajaknya secara atomic."""

    no_resi_lama = str(
        data.get("no_resi_lama") or data.get("no_resi") or ""
    ).strip().upper()
    kode_cabang = str(
        data.get("kode_cabang") or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()
    jenis_pajak = (
        str(data.get("jenis_pajak", "NONPAJAK")).strip().upper() or "NONPAJAK"
    )
    no_resi_baru = sesuaikan_nomor_resi_dengan_pajak(no_resi_lama, jenis_pajak)

    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError as exc:
        return False, KesalahanTransaksiResi(KODE_DB_ERROR, str(exc))

    if not no_resi_lama:
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR, "Nomor resi tidak boleh kosong."
        )
    if not kode_cabang:
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR, "Kode cabang tidak boleh kosong."
        )
    if not no_resi_baru:
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR, "Nomor resi hasil edit tidak valid."
        )

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        no_resi, revision_db, error = _update_transaksi_resi_cursor(
            cursor,
            data,
            no_resi_lama,
            no_resi_baru,
            kode_cabang,
            jenis_pajak,
        )
        if error is not None:
            conn.rollback()
            return False, error

        conn.commit()
        data["no_resi"] = no_resi
        data["revision"] = revision_db + 1
        return True, ""
    except KesalahanTransaksiResi as exc:
        _rollback(conn)
        return False, exc
    except sqlite3.IntegrityError as exc:
        _rollback(conn)
        message = str(exc)
        if (
            "data_resi.no_resi" in message
            or "UNIQUE constraint failed: data_resi.no_resi" in message
        ):
            return False, KesalahanTransaksiResi(
                KODE_RESI_DUPLIKAT,
                f"Nomor resi {no_resi_baru} sudah ada di database.",
            )
        logger.exception("IntegrityError saat memperbarui transaksi resi")
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR, f"Gagal memperbarui karena aturan database: {message}"
        )
    except Exception as exc:
        _rollback(conn)
        logger.exception("Gagal memperbarui transaksi resi")
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR, f"Gagal memperbarui resi: {exc}"
        )
    finally:
        _close(conn)

# ==============================================================================
# 04. BUKU GUDANG — MONITORING RESI MASUK & KELUAR
# ==============================================================================

def _normalisasi_filter_bulan(value):
    if value in (None, ""):
        return []

    sumber = value if isinstance(value, (list, tuple, set, frozenset)) else (value,)
    hasil = []
    for item in sumber:
        try:
            nomor = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= nomor <= 12 and nomor not in hasil:
            hasil.append(nomor)
    return sorted(hasil)

def _normalisasi_filter_status_penagihan(value):
    return str(
        getattr(value, "value", value) or ""
    ).strip().upper().replace("_", " ")

def _status_penagihan_cocok(info, filter_status):
    pilihan = _normalisasi_filter_status_penagihan(filter_status)
    if pilihan in {"", "SEMUA", "SEMUA TAGIHAN"}:
        return True

    ada_invoice = bool(info and str(info.get("no_invoice", "")).strip())
    status = str((info or {}).get("status", "") or "").strip().upper()
    if pilihan == "BELUM INVOICE":
        return not ada_invoice
    if pilihan in {"SUDAH INVOICE", "SUDAH DITAGIH"}:
        return ada_invoice
    if pilihan in {"BELUM LUNAS", "DRAFT"}:
        return ada_invoice and status not in {"LUNAS", "MACET"}
    if pilihan == "LUNAS":
        return ada_invoice and status == "LUNAS"
    if pilihan == "MACET":
        return ada_invoice and status == "MACET"
    return True

def _ambil_peta_status_penagihan_batch(no_resi_list):
    """Baca status terbaru secara batch setiap reload, tanpa cache lintas edit."""
    daftar = list(dict.fromkeys(
        str(no_resi or "").strip().upper()
        for no_resi in (no_resi_list or [])
        if str(no_resi or "").strip()
    ))
    if not daftar:
        return {}

    hasil = {}
    conn = None
    try:
        conn = get_db_connection()
        placeholders = ",".join("?" for _ in daftar)

        rows = conn.execute(
            f"""
            SELECT h.no_invoice, h.status, h.tanggal, h.created_at, ir.no_resi
            FROM invoice_resi ir
            INNER JOIN invoice_header h ON h.no_invoice = ir.no_invoice
            WHERE UPPER(ir.no_resi) IN ({placeholders})
            ORDER BY h.updated_at DESC, h.id DESC
            """,
            daftar,
        ).fetchall()

        for no_invoice, status, tanggal, created_at, no_resi in rows:
            key = str(no_resi or "").strip().upper()
            if key and key not in hasil:
                hasil[key] = {
                    "no_invoice": str(no_invoice or "").strip().upper(),
                    "status": str(status or "").strip().upper(),
                    "tanggal": str(tanggal or "").strip(),
                    "created_at": str(created_at or "").strip(),
                    "jumlah_invoice": 1,
                }

        for key in daftar:
            value = hasil.get(key, {
                "no_invoice": "",
                "status": "",
                "tanggal": "",
                "created_at": "",
                "jumlah_invoice": 0,
            })
            hasil[key] = value

        return hasil
    except sqlite3.Error as exc:
        logger.error("[Invoice] Gagal membangun status penagihan Buku Gudang: %s", exc)
        return {}
    finally:
        _close(conn)

def ambil_data_buku_gudang(kode_cabang, wilayah, tahun_terpilih, filters=None):
    """Ambil Buku Gudang grouped multi-row beserta status penagihan terbaru.

    Signature lama dipertahankan. Filter periode tambahan dikirim melalui
    ``filters['_bulan']`` dan dapat berupa satu nomor bulan atau kumpulan
    beberapa bulan. Filter penagihan dikirim melalui
    ``filters['_status_penagihan']``. Kolom filter indeks 5 juga diperlakukan
    sebagai STATUS PENAGIHAN pada Buku Gudang V2.
    """

    incoming_filters = dict(filters or {})
    bulan_terpilih = incoming_filters.pop("_bulan", None)
    status_penagihan = incoming_filters.pop("_status_penagihan", None)
    status_header = incoming_filters.pop(5, None)
    filter_penagihan = [
        value for value in (status_penagihan, status_header)
        if str(value or "").strip()
    ]

    mapping = {
        2: "r.tanggal_masuk", 3: "r.tanggal_keluar", 4: "r.status_resi",
        6: "r.truk", 7: "r.pengirim", 8: "r.kota_asal", 9: "r.penerima",
        10: "r.kota_tujuan", 11: "COALESCE(d.nama_barang, r.nama_barang)",
        15: "r.total_ongkir", 16: "r.pembayaran", 17: "r.ket_buku_gudang",
    }

    bulan_pilihan = _normalisasi_filter_bulan(bulan_terpilih)

    query = """
        SELECT r.no_resi, r.tanggal_masuk, r.tanggal_keluar, r.status_resi, r.truk,
               r.pengirim, r.kota_asal, r.penerima, r.kota_tujuan,
               COALESCE(d.nama_barang, r.nama_barang),
               COALESCE(d.koli, r.koli), COALESCE(d.berat, r.berat),
               COALESCE(d.cbm, r.cbm), r.total_ongkir, r.pembayaran,
               r.ket_buku_gudang, d.id_detail, COALESCE(d.urutan, 1),
               r.revision
        FROM data_resi r
        LEFT JOIN data_resi_detail d ON d.no_resi = r.no_resi
        WHERE r.kode_cabang = ?
          AND r.kota_tujuan LIKE ?
          AND r.tanggal_masuk LIKE ?
    """
    params = [kode_cabang, f"%{wilayah}%", f"{tahun_terpilih}%"]

    if bulan_pilihan and len(bulan_pilihan) < 12:
        placeholders = ", ".join("?" for _ in bulan_pilihan)
        query += f" AND substr(r.tanggal_masuk, 6, 2) IN ({placeholders})"
        params.extend(f"{bulan:02d}" for bulan in bulan_pilihan)

    for col_idx, val in incoming_filters.items():
        expression = mapping.get(col_idx)
        if not expression:
            continue
        if col_idx == 15:
            val = str(val).replace(".", "")
        query += f" AND {expression} LIKE ?"
        params.append(f"%{val}%")

    query += " ORDER BY r.tanggal_masuk ASC, r.rowid ASC, COALESCE(d.urutan, 1) ASC, d.id_detail ASC"
    rows = _fetchall(query, params) or []
    if not rows:
        return []

    daftar_resi = list(dict.fromkeys(
        str(row[0] or "").strip().upper() for row in rows if str(row[0] or "").strip()
    ))
    peta_invoice = _ambil_peta_status_penagihan_batch(daftar_resi)

    hasil = []
    for row in rows:
        no_resi = str(row[0] or "").strip().upper()
        info = peta_invoice.get(no_resi)
        if not all(
            _status_penagihan_cocok(info, pilihan)
            for pilihan in filter_penagihan
        ):
            continue
        info = info or {}
        hasil.append(tuple(row) + (
            str(info.get("no_invoice", "") or ""),
            str(info.get("status", "") or "").upper(),
            str(info.get("created_at", "") or info.get("tanggal", "") or ""),
            int(info.get("jumlah_invoice", 0) or 0),
        ))
    return hasil

_BUKU_GUDANG_HEADER_FIELDS = {
    "tanggal_masuk", "tanggal_keluar", "status_resi", "truk",
    "pengirim", "kota_asal", "penerima", "kota_tujuan",
    "total_ongkir", "pembayaran", "ket_buku_gudang",
    "no_manifest", "ket_manifest",
}
_BUKU_GUDANG_ITEM_FIELDS = {"nama_barang", "koli", "berat", "cbm"}

def _siapkan_update_buku_gudang(updates_dict, barang_payload):
    incoming = dict(updates_dict or {})
    item_updates = {
        key: incoming.get(key)
        for key in _BUKU_GUDANG_ITEM_FIELDS
        if key in incoming
    }
    for key in _BUKU_GUDANG_ITEM_FIELDS:
        if barang_payload and key in barang_payload:
            item_updates[key] = barang_payload[key]
    safe_updates = {
        key: value
        for key, value in incoming.items()
        if key in _BUKU_GUDANG_HEADER_FIELDS
    }
    return safe_updates, item_updates

def _sesuaikan_subtotal_buku_gudang(safe_updates, jenis_pajak):
    if "total_ongkir" not in safe_updates:
        return
    try:
        total_baru = max(0, int(float(safe_updates.get("total_ongkir") or 0)))
    except (TypeError, ValueError):
        total_baru = 0

    if str(jenis_pajak or "").strip().upper().startswith("PAJAK"):
        from decimal import Decimal, ROUND_HALF_UP
        safe_updates["subtotal_ongkir"] = int(
            (Decimal(str(total_baru)) / Decimal("1.011")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    else:
        safe_updates["subtotal_ongkir"] = total_baru

def _update_detail_buku_gudang(
    cursor, no_resi, kode_cabang, item_updates, detail_id
):
    target_detail_id = detail_id
    if target_detail_id in (None, "", 0, "0"):
        row_detail = cursor.execute(
            """
            SELECT id_detail FROM data_resi_detail
            WHERE no_resi = ? ORDER BY urutan ASC, id_detail ASC LIMIT 1
            """,
            (no_resi,),
        ).fetchone()
        target_detail_id = row_detail[0] if row_detail else None

    if target_detail_id is None:
        cursor.execute(
            """
            INSERT INTO data_resi_detail (
                no_resi, urutan, nama_barang, koli, berat, cbm, updated_at
            ) VALUES (?, 1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                no_resi,
                str(item_updates.get("nama_barang", "") or "").strip().upper(),
                str(item_updates.get("koli", "") or "").strip(),
                item_updates.get("berat", 0) or 0,
                item_updates.get("cbm", 0) or 0,
                str(uuid.uuid4()),
            ),
        )
    else:
        detail_fields = [f"{column} = ?" for column in item_updates]
        detail_values = list(item_updates.values()) + [target_detail_id, no_resi]
        cursor.execute(
            f"""
            UPDATE data_resi_detail
            SET {", ".join(detail_fields)}, updated_at = CURRENT_TIMESTAMP
            WHERE id_detail = ? AND no_resi = ?
            """,
            detail_values,
        )
        if cursor.rowcount == 0:
            return False

    _sinkronkan_ringkasan_resi_dari_detail(cursor, no_resi, kode_cabang)
    return True

def _update_buku_gudang_cursor(
    cursor,
    no_resi,
    kode_cabang,
    safe_updates,
    item_updates,
    detail_id,
    expected_revision,
    detail_barang=None,
):
    """Jalankan isi transaksi edit Buku Gudang memakai cursor aktif."""
    row_lama = cursor.execute(
        """
        SELECT tanggal_masuk, status_resi, penerima, jenis_pajak, revision
        FROM data_resi
        WHERE no_resi = ? AND kode_cabang = ?
        LIMIT 1
        """,
        (no_resi, kode_cabang),
    ).fetchone()
    if row_lama is None:
        return False

    lama = {
        "tanggal_masuk": row_lama[0],
        "status_resi": row_lama[1],
        "penerima": row_lama[2],
        "jenis_pajak": str(row_lama[3] or "NONPAJAK").strip().upper(),
        "revision": int(row_lama[4] or 0),
    }
    snapshot_audit_lama = _snapshot_resi_untuk_audit(
        cursor, no_resi, kode_cabang
    )

    if expected_revision is not None:
        try:
            expected_revision = int(expected_revision)
        except (TypeError, ValueError):
            return False
        if lama["revision"] != expected_revision:
            return False

    _sesuaikan_subtotal_buku_gudang(safe_updates, lama["jenis_pajak"])

    if safe_updates:
        fields = [f"{column} = ?" for column in safe_updates]
        values = list(safe_updates.values()) + [no_resi, kode_cabang]
        cursor.execute(
            f"""
            UPDATE data_resi
            SET {", ".join(fields)}, is_synced = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE no_resi = ? AND kode_cabang = ?
            """,
            values,
        )
        if cursor.rowcount == 0:
            return False

    if item_updates and not _update_detail_buku_gudang(
        cursor, no_resi, kode_cabang, item_updates, detail_id
    ):
        return False

    if detail_barang is not None:
        rincian = _ganti_rincian_resi(cursor, no_resi, {"rincian": detail_barang})
        if rincian:
            _sinkronkan_ringkasan_resi_dari_detail(cursor, no_resi, kode_cabang)
        else:
            cursor.execute(
                """UPDATE data_resi SET nama_barang = '', koli = '', berat = 0,
                   cbm = 0, rincian_json = '[]', is_synced = 0
                   WHERE no_resi = ? AND kode_cabang = ?""",
                (no_resi, kode_cabang),
            )

    cursor.execute(
        """
        UPDATE data_resi
        SET revision = revision + 1, updated_at = CURRENT_TIMESTAMP
        WHERE no_resi = ? AND kode_cabang = ? AND revision = ?
        """,
        (no_resi, kode_cabang, lama["revision"]),
    )
    if cursor.rowcount == 0:
        return False

    cursor.execute(
        """
        UPDATE buku_gudang
        SET tanggal = ?, status_resi = ?, is_synced = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE no_resi = ? AND kode_cabang = ?
        """,
        (
            safe_updates.get("tanggal_masuk", lama["tanggal_masuk"]),
            safe_updates.get("status_resi", lama["status_resi"]),
            no_resi,
            kode_cabang,
        ),
    )

    penerima_lama = str(lama["penerima"] or "").strip().upper()
    penerima_baru = str(
        safe_updates.get("penerima", lama["penerima"]) or ""
    ).strip().upper()
    if penerima_lama:
        _refresh_total_transaksi_master_penerima(
            cursor, penerima_lama, kode_cabang
        )
    if penerima_baru and penerima_baru != penerima_lama:
        _refresh_total_transaksi_master_penerima(
            cursor, penerima_baru, kode_cabang
        )

    snapshot_audit_baru = _snapshot_resi_untuk_audit(
        cursor, no_resi, kode_cabang
    )
    _catat_audit_resi(
        cursor,
        kode_cabang=kode_cabang,
        no_resi_lama=no_resi,
        no_resi_baru=no_resi,
        sumber="BUKU_GUDANG",
        snapshot_lama=snapshot_audit_lama,
        snapshot_baru=snapshot_audit_baru,
    )
    return True

def update_detail_barang_dari_buku_gudang(no_resi, kode_cabang, detail_barang):
    """Sinkronkan seluruh detail barang dari popup Buku Gudang ke data_resi_detail.

    Buku Gudang hanya menjadi editor operasional; sumber detail tetap data_resi_detail.
    """

    no_resi = str(no_resi or "").strip().upper()
    kode_cabang = str(kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")).strip().upper()

    if not no_resi:
        return False
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError:
        return False

    try:
        with _db_transaction(immediate=True) as (conn, cursor):
            row_resi = cursor.execute(
                """
                SELECT revision
                FROM data_resi
                WHERE no_resi = ? AND kode_cabang = ?
                LIMIT 1
                """,
                (no_resi, kode_cabang),
            ).fetchone()
            if row_resi is None:
                return False

            revision_lama = int(row_resi[0] or 0)
            cursor.execute(
                "DELETE FROM data_resi_detail WHERE no_resi = ?",
                (no_resi,),
            )

            for idx, item in enumerate(detail_barang or [], start=1):
                cursor.execute(
                    """
                    INSERT INTO data_resi_detail
                    (no_resi, urutan, nama_barang, koli, berat, cbm, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        no_resi,
                        idx,
                        str(item.get("nama_barang", "") or "").strip().upper(),
                        str(item.get("koli", "") or ""),
                        item.get("berat", 0) or 0,
                        item.get("cbm", 0) or 0,
                        str(uuid.uuid4()),
                    ),
                )

            _sinkronkan_ringkasan_resi_dari_detail(cursor, no_resi, kode_cabang)
            cursor.execute(
                """
                UPDATE data_resi
                SET revision = revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE no_resi = ? AND kode_cabang = ? AND revision = ?
                """,
                (no_resi, kode_cabang, revision_lama),
            )
            if cursor.rowcount != 1:
                raise sqlite3.DatabaseError("Revision Resi berubah saat detail disimpan.")
        return True
    except Exception as exc:
        logger.error("[Buku Gudang] Sinkron detail gagal: %s", exc)
        return False


def ambil_data_edit_buku_gudang(no_resi, kode_cabang):
    """Baca header dan seluruh detail dalam satu snapshot, tanpa filter tabel."""
    with _db_transaction() as (_, cursor):
        cursor.execute("BEGIN")
        snapshot = _snapshot_resi_untuk_audit(cursor, no_resi, kode_cabang)
        if snapshot is not None and not snapshot["barang"]:
            row = cursor.execute(
                """SELECT nama_barang, koli, berat, cbm FROM data_resi
                   WHERE no_resi = ? AND kode_cabang = ?""",
                (no_resi, kode_cabang),
            ).fetchone()
            if row and any(row):
                snapshot["barang"] = [dict(zip(
                    ("nama_barang", "koli", "berat", "cbm"), row
                ))]
        return snapshot


def _siapkan_daftar_detail_buku_gudang(detail_barang):
    """API menerima angka kanonik; format lokal ditangani editor."""
    from math import isfinite
    hasil = []
    for detail in detail_barang:
        koli = str(detail.get("koli", "") or "").strip()
        if koli and (not koli.isascii() or not koli.isdecimal()):
            raise ValueError("Koli harus angka bulat positif atau kosong.")
        berat = float(detail.get("berat", 0) or 0)
        cbm = float(detail.get("cbm", 0) or 0)
        if any(not isfinite(value) or value < 0 for value in (berat, cbm)):
            raise ValueError("Berat dan kubik harus angka nonnegatif.")
        hasil.append({
            "nama_barang": str(detail.get("nama_barang", "") or "").strip().upper(),
            "koli": koli,
            "berat": berat,
            "cbm": cbm,
        })
    return hasil


def update_baris_buku_gudang(
    no_resi, kode_cabang, updates_dict, barang_payload=None, detail_id=None,
    expected_revision=None, *, detail_barang=None,
):
    """Simpan header dan detail secara atomic, dengan pemeriksaan revision."""

    no_resi = str(no_resi or "").strip().upper()
    kode_cabang = str(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()
    safe_updates, item_updates = _siapkan_update_buku_gudang(
        updates_dict, barang_payload
    )
    if detail_barang is not None:
        if item_updates or detail_id is not None or not isinstance(detail_barang, list):
            return False
        try:
            detail_barang = _siapkan_daftar_detail_buku_gudang(detail_barang)
        except (ValueError, TypeError, AttributeError, OverflowError):
            return False
    if not safe_updates and not item_updates and detail_barang is None:
        return True
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        berhasil = _update_buku_gudang_cursor(
            cursor,
            no_resi,
            kode_cabang,
            safe_updates,
            item_updates,
            detail_id,
            expected_revision,
            detail_barang,
        )
        if not berhasil:
            conn.rollback()
            return False
        conn.commit()
        return True
    except sqlite3.Error as exc:
        _rollback(conn)
        logger.error("[Buku Gudang] Gagal memperbarui resi: %s", exc)
        return False
    finally:
        _close(conn)

def tandai_resi_selesai_massal(resi_terpilih, kode_cabang):

    daftar_resi = list(dict.fromkeys(
        str(no_resi).strip().upper()
        for no_resi in (resi_terpilih or [])
        if str(no_resi).strip()
    ))
    if not daftar_resi:
        return True
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cabang = str(kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")).strip().upper()
        for no_resi in daftar_resi:
            if not _update_buku_gudang_cursor(
                cursor, no_resi, cabang, {"status_resi": "SELESAI"}, {}, None, None
            ):
                conn.rollback()
                return False
        conn.commit()
        return True
    except sqlite3.Error as exc:
        _rollback(conn)
        logger.error("[Buku Gudang] Gagal menyelesaikan resi massal: %s", exc)
        return False
    finally:
        _close(conn)

# ==============================================================================
# 05. MANIFEST — PEMBERANGKATAN & TRACKING
# ==============================================================================

def ambil_truk_list(kode_cabang=None):
    """Daftar nomor polisi dan sopir milik cabang aktif."""
    return _fetchall(
        """
        SELECT no_polisi, nama_sopir
        FROM truk
        WHERE kode_cabang = ?
        ORDER BY no_polisi ASC
        """,
        (_kode_cabang_aktif(kode_cabang),),
    )

def ambil_detail_truk_by_nopol(nopol, kode_cabang=None):
    """Detail truk berdasarkan nomor polisi pada cabang aktif."""
    return _fetchone(
        """
        SELECT nama_sopir, jenis_truk
        FROM truk
        WHERE kode_cabang = ? AND no_polisi = ?
        LIMIT 1
        """,
        (_kode_cabang_aktif(kode_cabang), str(nopol or "").strip().upper()),
    )

def ambil_detail_truk_by_sopir(sopir, kode_cabang=None):
    """Detail truk berdasarkan nama sopir pada cabang aktif."""
    return _fetchone(
        """
        SELECT no_polisi, jenis_truk, ket_truk
        FROM truk
        WHERE kode_cabang = ? AND nama_sopir = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (_kode_cabang_aktif(kode_cabang), str(sopir or "").strip().upper()),
    )

def ambil_no_manifest_list_by_prefix(prefix, kode_cabang):
    return _fetchall(
        "SELECT no_manifest FROM data_resi WHERE no_manifest LIKE ? AND kode_cabang = ?",
        (f"{prefix}-%", kode_cabang),
    )

def ambil_daftar_tahun_manifest(kode_cabang):
    return _fetchall(
        "SELECT DISTINCT substr(tanggal_keluar, 1, 4) FROM data_resi WHERE no_manifest IS NOT NULL AND tanggal_keluar IS NOT NULL AND kode_cabang = ?",
        (kode_cabang,),
    )

def ambil_resi_untuk_manifest(kode_cabang, wilayah, is_edit_mode, edit_manifest_id):
    if is_edit_mode:
        query = """SELECT no_resi, tanggal_masuk, pengirim, penerima, kota_tujuan,
                          nama_barang, koli, berat, cbm, no_manifest,
                          total_ongkir, ket_manifest
                   FROM data_resi
                   WHERE kode_cabang = ?
                     AND (no_manifest = ? OR (kota_tujuan LIKE ? AND (no_manifest IS NULL OR TRIM(no_manifest) = '')))
                   ORDER BY CASE WHEN no_manifest = ? THEN 0 ELSE 1 END, tanggal_masuk ASC"""
        params = (kode_cabang, edit_manifest_id, f"%{wilayah}%", edit_manifest_id)
    else:
        query = """SELECT no_resi, tanggal_masuk, pengirim, penerima, kota_tujuan,
                          nama_barang, koli, berat, cbm, NULL as no_manifest,
                          total_ongkir, NULL as ket_manifest
                   FROM data_resi
                   WHERE kode_cabang = ?
                     AND kota_tujuan LIKE ?
                     AND (no_manifest IS NULL OR TRIM(no_manifest) = '')
                   ORDER BY tanggal_masuk ASC"""
        params = (kode_cabang, f"%{wilayah}%")
    return _fetchall(query, params)

def ambil_histori_manifest(kode_cabang, tahun_terpilih):
    query = """
        SELECT DISTINCT r1.tanggal_keluar, r1.no_manifest, r1.truk,
                        COALESCE(m.nama_kapal, ''),
                        (SELECT COUNT(*)
                         FROM data_resi r2
                         WHERE r2.no_manifest = r1.no_manifest
                           AND r2.kode_cabang = r1.kode_cabang),
                        COALESCE(m.note_manifest, '')
        FROM data_resi r1
        LEFT JOIN manifest m
          ON m.id_manifest = r1.no_manifest
         AND m.kode_cabang = r1.kode_cabang
        WHERE r1.no_manifest IS NOT NULL
          AND r1.kode_cabang = ?
    """
    params = [kode_cabang]
    if tahun_terpilih and tahun_terpilih != "Semua":
        query += " AND r1.tanggal_keluar LIKE ?"
        params.append(f"{tahun_terpilih}-%")
    query += " ORDER BY r1.tanggal_keluar ASC, r1.no_manifest ASC"
    return _fetchall(query, params)

def _normalisasi_payload_manifest(truk_payload):
    nopol = str(truk_payload.get("no_polisi", "")).strip().upper()
    sopir = str(truk_payload.get("nama_sopir", "")).strip().upper()
    jenis = str(truk_payload.get("jenis_truk", "")).strip()
    ket_truk = str(truk_payload.get("ket_truk", "")).strip().upper()
    nama_truk = str(truk_payload.get("nama_truk", "")).strip()
    nama_kapal = str(truk_payload.get("nama_kapal", "")).strip().upper()
    note_manifest = str(truk_payload.get("note_manifest", "")).strip().upper()
    if not nama_truk and note_manifest:
        nama_truk = note_manifest
    return nopol, sopir, jenis, ket_truk, nama_truk, nama_kapal, note_manifest

def _upsert_truk_manifest(cursor, kode_cabang, nopol, sopir, jenis, ket_truk):
    if not nopol:
        return
    cursor.execute(
        """
        INSERT INTO truk (
            kode_cabang, no_polisi, jenis_truk, nama_sopir,
            ket_truk, is_synced, updated_at
        ) VALUES (?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
        ON CONFLICT(kode_cabang, no_polisi) DO UPDATE SET
            jenis_truk = CASE WHEN TRIM(excluded.jenis_truk) <> ''
                              THEN excluded.jenis_truk ELSE truk.jenis_truk END,
            nama_sopir = CASE WHEN TRIM(excluded.nama_sopir) <> ''
                              THEN excluded.nama_sopir ELSE truk.nama_sopir END,
            ket_truk = CASE WHEN TRIM(excluded.ket_truk) <> ''
                            THEN excluded.ket_truk ELSE truk.ket_truk END,
            is_synced = 0,
            updated_at = CURRENT_TIMESTAMP
        """,
        (kode_cabang, nopol, jenis or "BELUM DIKETAHUI", sopir, ket_truk),
    )

def _reset_manifest_lama(cursor, manifest_id, kode_cabang, resi_list=None):
    """Lepas hanya Resi yang dikeluarkan dari Manifest saat edit.

    Resi yang tetap dipilih tidak di-reset dahulu karena itu akan membuat dua
    update/outbox untuk satu penyimpanan Manifest. Setiap perubahan operasional
    pada data_resi menaikkan revision agar CAS sinkronisasi dapat menerimanya.
    """
    selected_resi = []
    for item in (resi_list or []):
        no_resi = str(item[0] if item else "").strip()
        if no_resi:
            selected_resi.append(no_resi)

    sql = """
        UPDATE data_resi
        SET truk = NULL, status_resi = 'DI GUDANG', tanggal_keluar = NULL,
            no_manifest = NULL, ket_manifest = NULL,
            revision = COALESCE(revision, 0) + 1,
            is_synced = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE no_manifest = ? AND kode_cabang = ?
    """
    params = [manifest_id, kode_cabang]
    if selected_resi:
        placeholders = ",".join("?" for _ in selected_resi)
        sql += f" AND no_resi NOT IN ({placeholders})"
        params.extend(selected_resi)
    cursor.execute(sql, tuple(params))

def _upsert_header_manifest(cursor, manifest_id, kode_cabang, tgl_k,
                            nopol, sopir, nama_kapal, note_manifest):
    cursor.execute(
        """
        INSERT INTO manifest (
            id_manifest, kode_cabang, tanggal, no_polisi, nama_sopir,
            nama_kapal, note_manifest, status_manifest, sync_id, deleted_at,
            is_synced, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PERJALANAN', ?, NULL, 0, CURRENT_TIMESTAMP)
        ON CONFLICT(id_manifest) DO UPDATE SET
            kode_cabang = excluded.kode_cabang,
            tanggal = excluded.tanggal,
            no_polisi = excluded.no_polisi,
            nama_sopir = excluded.nama_sopir,
            nama_kapal = excluded.nama_kapal,
            note_manifest = excluded.note_manifest,
            status_manifest = excluded.status_manifest,
            deleted_at = NULL,
            is_synced = 0,
            updated_at = CURRENT_TIMESTAMP
        """,
        (manifest_id, kode_cabang, tgl_k, nopol or None, sopir,
         nama_kapal or None, note_manifest or None, str(uuid.uuid4())),
    )

def _pasang_resi_ke_manifest(cursor, resi_list, nama_truk, tgl_k,
                             manifest_id, kode_cabang):
    for resi_data in resi_list:
        no_resi = str(resi_data[0] if resi_data else "").strip()
        ket_manifest = (
            str(resi_data[1]).strip()
            if len(resi_data) > 1 and resi_data[1] is not None
            else ""
        )
        cursor.execute(
            """
            UPDATE data_resi
            SET truk = ?, status_resi = 'PERJALANAN', tanggal_keluar = ?,
                no_manifest = ?, ket_manifest = ?,
                revision = COALESCE(revision, 0) + 1,
                is_synced = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE no_resi = ? AND kode_cabang = ?
            """,
            (nama_truk, tgl_k, manifest_id, ket_manifest, no_resi, kode_cabang),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Resi {no_resi} tidak ditemukan pada cabang {kode_cabang}.")

def simpan_atau_update_manifest_data(
    manifest_id,
    kode_cabang,
    truk_payload,
    resi_list,
    is_edit_mode,
    tgl_k,
):

    manifest_id = str(manifest_id or "").strip().upper()
    kode_cabang = str(kode_cabang or "").strip().upper()
    if not kode_cabang:
        return False, "Kode cabang tidak boleh kosong."
    if not resi_list:
        return False, "Pilih minimal satu resi."
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError as exc:
        return False, str(exc)

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        payload = _normalisasi_payload_manifest(truk_payload)
        nopol, sopir, jenis, ket_truk, nama_truk, nama_kapal, note_manifest = payload
        if not nama_truk:
            return False, "Detail truk atau Note manifest tidak boleh kosong."

        if is_edit_mode:
            if not manifest_id:
                return False, "Nomor manifest tidak boleh kosong."
        else:
            wilayah = str(
                truk_payload.get("wilayah") or truk_payload.get("provinsi") or ""
            ).strip().upper()
            allocated = numbering_service.allocate_number_cursor(
                cursor, "MANIFEST", kode_cabang,
                wilayah=wilayah, tanggal=tgl_k,
            )
            manifest_id = allocated.nomor

        _upsert_truk_manifest(cursor, kode_cabang, nopol, sopir, jenis, ket_truk)
        if is_edit_mode:
            _reset_manifest_lama(cursor, manifest_id, kode_cabang, resi_list=resi_list)
        _upsert_header_manifest(
            cursor, manifest_id, kode_cabang, tgl_k,
            nopol, sopir, nama_kapal, note_manifest,
        )
        _pasang_resi_ke_manifest(
            cursor, resi_list, nama_truk, tgl_k, manifest_id, kode_cabang
        )
        conn.commit()
        return True, manifest_id
    except Exception as exc:
        _rollback(conn)
        return False, str(exc)
    finally:
        _close(conn)

def _ambil_teks_manifest(kolom, manifest_id, kode_cabang, label_error):
    kolom_sql = {"note_manifest": "note_manifest", "nama_kapal": "nama_kapal"}[kolom]
    manifest_id = str(manifest_id or "").strip().upper()
    kode_cabang = str(kode_cabang or "").strip().upper()
    if not manifest_id or not kode_cabang:
        return ""
    try:
        row = _fetchone(
            f"""
            SELECT COALESCE({kolom_sql}, '') FROM manifest
            WHERE id_manifest = ? AND kode_cabang = ? LIMIT 1
            """,
            (manifest_id, kode_cabang),
        )
        return str(row[0] or "").strip() if row else ""
    except sqlite3.Error as exc:
        logger.error(label_error, exc)
        return ""

def ambil_note_manifest(manifest_id, kode_cabang):
    """Mengambil Note umum yang tersimpan pada satu Manifest."""
    return _ambil_teks_manifest(
        "note_manifest", manifest_id, kode_cabang,
        "[Manifest] Gagal mengambil Note manifest: %s",
    )

def ambil_nama_kapal_manifest(manifest_id, kode_cabang):
    """Mengambil hanya nama kapal yang tersimpan pada satu Manifest."""
    return _ambil_teks_manifest(
        "nama_kapal", manifest_id, kode_cabang,
        "[Manifest] Gagal mengambil nama kapal: %s",
    )

def ambil_resi_detail_untuk_cetak(kode_cabang, resi_list):
    daftar_resi = [str(no_resi).strip() for no_resi in (resi_list or []) if str(no_resi).strip()]
    if not daftar_resi:
        return []
    placeholders = ",".join("?" for _ in daftar_resi)
    params = [kode_cabang] + daftar_resi
    try:
        return _fetchall(
            f"""
            SELECT no_resi, pengirim, penerima, kota_tujuan,
                   nama_barang, koli, berat, cbm,
                   total_ongkir, ket_manifest
            FROM data_resi
            WHERE kode_cabang = ? AND no_resi IN ({placeholders})
            """,
            params,
        )
    except sqlite3.Error as exc:
        logger.error("[Manifest] Gagal mengambil detail cetak: %s", exc)
        return []

def ambil_resi_list_by_manifest(manifest_id, kode_cabang):
    rows = _fetchall(
        "SELECT no_resi FROM data_resi WHERE no_manifest = ? AND kode_cabang = ?",
        (manifest_id, kode_cabang),
    )
    return [row[0] for row in rows]

def _varian_nomor_resi_pajak(no_resi):
    """Nomor yang dianggap identitas Resi sama untuk pencarian snapshot Invoice.

    Nomor Resi dapat berubah hanya pada suffix PAJAK/NONPAJAK. Karena Invoice
    bersifat snapshot dan tidak ikut diubah ketika suffix Resi dikoreksi, lookup
    harus mengenali kedua bentuk nomor tersebut.
    """
    nomor = str(no_resi or "").strip().upper()
    if not nomor:
        return set()
    return {
        nomor,
        sesuaikan_nomor_resi_dengan_pajak(nomor, "PAJAK"),
        sesuaikan_nomor_resi_dengan_pajak(nomor, "NONPAJAK"),
    } - {""}

def _json_memuat_nomor_resi(value, kandidat):
    """True bila JSON/list/dict berisi scalar nomor Resi secara persis."""
    if isinstance(value, dict):
        return any(_json_memuat_nomor_resi(v, kandidat) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_json_memuat_nomor_resi(v, kandidat) for v in value)
    return str(value if value is not None else "").strip().upper() in kandidat

def _teks_memuat_nomor_resi(teks, kandidat):
    """Fallback untuk data_kolom lama yang mungkin bukan JSON valid."""
    raw = str(teks or "")
    for nomor in kandidat:
        if re.search(rf"(?<![A-Z0-9]){re.escape(nomor)}(?![A-Z0-9])", raw, re.I):
            return True
    return False

def _kumpulkan_nomor_resi_snapshot(value, *, izinkan_fallback=True):
    """Ambil kandidat nomor Resi dari snapshot JSON Invoice.

    Field eksplisit ``resi``/``no_resi`` diprioritaskan. Untuk snapshot lama
    yang tidak memiliki key baku, scalar tetap dikumpulkan sebagai fallback dan
    baru dicocokkan secara exact terhadap nomor Resi aktif.
    """
    eksplisit = set()
    fallback = set()

    def walk(node):
        if isinstance(node, dict):
            for key, val in node.items():
                key_norm = str(key or "").strip().casefold()
                if key_norm in {"resi", "no_resi", "nomor_resi"} and not isinstance(
                    val, (dict, list, tuple)
                ):
                    text = str(val if val is not None else "").strip().upper()
                    if text:
                        eksplisit.add(text)
                walk(val)
            return
        if isinstance(node, (list, tuple)):
            for val in node:
                walk(val)
            return
        text = str(node if node is not None else "").strip().upper()
        if text:
            fallback.add(text)

    walk(value)
    if eksplisit:
        return eksplisit
    return fallback if izinkan_fallback else set()

def ambil_invoice_terkait_resi(no_resi):
    """Ambil Invoice terkait Resi; prioritaskan relasi invoice_resi, fallback snapshot."""

    kandidat = _varian_nomor_resi_pajak(no_resi)
    if not kandidat:
        return []

    conn = None
    try:
        conn = get_db_connection()
        placeholders = ",".join("?" for _ in kandidat)
        try:
            rows_relasi = conn.execute(
                f"""
                SELECT DISTINCT h.no_invoice, h.status, h.tanggal,
                       h.updated_at, h.id
                FROM invoice_header AS h
                INNER JOIN invoice_resi AS ir ON ir.no_invoice = h.no_invoice
                WHERE UPPER(ir.no_resi) IN ({placeholders})
                ORDER BY h.updated_at DESC, h.id DESC
                """,
                tuple(kandidat),
            ).fetchall()
        except sqlite3.OperationalError:
            rows_relasi = []

        if rows_relasi:
            return [
                {
                    "no_invoice": str(row[0] or "").strip(),
                    "status": str(row[1] or "").strip().upper(),
                    "tanggal": str(row[2] or "").strip(),
                }
                for row in rows_relasi
                if str(row[0] or "").strip()
            ]

        # Fallback kompatibilitas untuk invoice legacy yang belum berhasil dibackfill.
        rows = conn.execute(
            """
            SELECT h.no_invoice, h.status, h.tanggal,
                   d.data_kolom, h.metadata_json
            FROM invoice_header AS h
            INNER JOIN invoice_detail AS d
                ON d.no_invoice = h.no_invoice
            ORDER BY h.updated_at DESC, h.id DESC, d.nomor_urut ASC
            """
        ).fetchall()

        hasil = []
        sudah = set()
        for no_invoice, status, tanggal, data_kolom, metadata_json in rows:
            cocok = False
            for raw in (data_kolom, metadata_json):
                if raw in (None, ""):
                    continue
                try:
                    parsed = json.loads(str(raw))
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed = None

                if parsed is not None and _json_memuat_nomor_resi(parsed, kandidat):
                    cocok = True
                    break
                if parsed is None and _teks_memuat_nomor_resi(raw, kandidat):
                    cocok = True
                    break

            invoice = str(no_invoice or "").strip()
            if cocok and invoice and invoice not in sudah:
                sudah.add(invoice)
                hasil.append({
                    "no_invoice": invoice,
                    "status": str(status or "").strip().upper(),
                    "tanggal": str(tanggal or "").strip(),
                })
        return hasil
    except sqlite3.Error as exc:
        logger.error("[Invoice] Gagal memeriksa keterkaitan Resi %s: %s", no_resi, exc)
        return []
    finally:
        _close(conn)

def _nomor_resi_snapshot_invoice_cursor(cursor, no_invoice):
    try:
        rows_relasi = cursor.execute(
            "SELECT no_resi FROM invoice_resi WHERE no_invoice = ? ORDER BY id ASC",
            (no_invoice,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows_relasi = []

    hasil = {
        str(row[0] or "").strip().upper()
        for row in rows_relasi
        if row and str(row[0] or "").strip()
    }
    if hasil:
        return hasil

    rows = cursor.execute(
        "SELECT data_kolom FROM invoice_detail WHERE no_invoice = ?",
        (no_invoice,),
    ).fetchall()
    for row in rows:
        raw = row[0] if row else None
        if raw in (None, ""):
            continue
        try:
            parsed = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if parsed is not None:
            hasil.update(_kumpulkan_nomor_resi_snapshot(parsed, izinkan_fallback=False))
    return hasil

def ubah_status_penagihan_invoice(no_invoice, status_baru, kode_cabang=None):
    """Ubah status tagihan Invoice secara atomic.

    ``LUNAS`` juga menandai seluruh Resi aktif yang tersimpan pada snapshot
    Invoice sebagai ``SELESAI``. ``MACET`` dan ``BELUM LUNAS`` tidak mengubah
    status operasional Resi.
    """

    invoice = str(no_invoice or "").strip().upper()
    status = str(status_baru or "").strip().upper()
    if not invoice:
        return False, "Nomor invoice tidak boleh kosong."
    if status not in {"BELUM LUNAS", "LUNAS", "MACET"}:
        return False, "Status penagihan tidak valid."

    cabang = str(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()
    try:
        _pastikan_boleh_tulis_cabang(cabang)
    except PermissionError as exc:
        return False, str(exc)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        exists = cursor.execute(
            "SELECT 1 FROM invoice_header WHERE no_invoice = ? LIMIT 1",
            (invoice,),
        ).fetchone()
        if not exists:
            conn.rollback()
            return False, f"Invoice {invoice} tidak ditemukan."

        cursor.execute(
            """
            UPDATE invoice_header
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE no_invoice = ?
            """,
            (status, invoice),
        )

        if status == "LUNAS":
            snapshot_resi = _nomor_resi_snapshot_invoice_cursor(cursor, invoice)
            for nomor_snapshot in snapshot_resi:
                nomor = str(nomor_snapshot or "").strip().upper()
                if not nomor:
                    continue
                # invoice_resi menyimpan nomor aktif lintas cabang. Bila berasal dari
                # snapshot legacy, fallback varian PAJAK/NONPAJAK tetap dipertahankan.
                cursor.execute(
                    """
                    SELECT no_resi, kode_cabang FROM data_resi
                    WHERE UPPER(no_resi) = UPPER(?)
                    """,
                    (nomor,),
                )
                targets = cursor.fetchall()
                if not targets:
                    kandidat = sorted(_varian_nomor_resi_pajak(nomor))
                    if kandidat:
                        placeholders = ",".join("?" for _ in kandidat)
                        cursor.execute(
                            f"""
                            SELECT no_resi, kode_cabang FROM data_resi
                            WHERE UPPER(no_resi) IN ({placeholders})
                            """,
                            kandidat,
                        )
                        targets = cursor.fetchall()
                for nomor_aktif, cabang_aktif in targets:
                    if not _update_buku_gudang_cursor(
                        cursor, nomor_aktif, cabang_aktif,
                        {"status_resi": "SELESAI"}, {}, None, None,
                    ):
                        conn.rollback()
                        return False, f"Status Resi {nomor_aktif} gagal diperbarui."

        conn.commit()
        return True, f"Invoice {invoice} berhasil ditandai {status}."
    except sqlite3.Error as exc:
        _rollback(conn)
        logger.error("[Invoice] Gagal mengubah status penagihan %s: %s", invoice, exc)
        return False, f"Gagal mengubah status penagihan: {exc}"
    finally:
        _close(conn)

def cek_proteksi_invoice_resi(no_resi, perubahan=None, kode_cabang=None):
    """Klasifikasikan warning Edit Resi yang sudah masuk Invoice.

    Return dict tidak memblokir update di backend. Keputusan lanjut/batal tetap
    berada di UI supaya koreksi Resi sah masih dimungkinkan. Invoice tetap
    merupakan snapshot dan tidak diubah otomatis.
    """
    invoices = ambil_invoice_terkait_resi(no_resi)
    hasil = {
        "terkait": bool(invoices),
        "invoices": invoices,
        "perubahan_finansial": False,
    }
    if not invoices or not perubahan:
        return hasil

    row = _fetchone(
        """
        SELECT jenis_pajak, subtotal_ongkir, total_ongkir, pembayaran
        FROM data_resi
        WHERE no_resi = ? AND kode_cabang = ?
        LIMIT 1
        """,
        (
            str(no_resi or "").strip().upper(),
            str(kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")).strip().upper(),
        ),
    )
    if row is None:
        return hasil

    lama = {
        "jenis_pajak": str(row[0] or "NONPAJAK").strip().upper(),
        "subtotal_ongkir": int(row[1] or 0),
        "total_ongkir": int(row[2] or 0),
        "pembayaran": str(row[3] or "").strip().upper(),
    }

    for key in ("jenis_pajak", "pembayaran"):
        if key in perubahan:
            baru = str(perubahan.get(key) or "").strip().upper()
            if baru != lama[key]:
                hasil["perubahan_finansial"] = True
                return hasil

    for key in ("subtotal_ongkir", "total_ongkir"):
        if key in perubahan:
            try:
                baru = int(float(perubahan.get(key) or 0))
            except (TypeError, ValueError):
                baru = 0
            if baru != lama[key]:
                hasil["perubahan_finansial"] = True
                return hasil

    return hasil

# ==============================================================================
# 06. INVOICE — TAGIHAN & TEMPLATE JSON
# ==============================================================================

def ambil_daftar_cabang_billing():
    """Daftar cabang untuk filter Billing Queue."""
    try:
        return _fetchall(
            """
            SELECT kode_cabang, nama_cabang
            FROM data_cabang
            ORDER BY nama_cabang COLLATE NOCASE ASC, kode_cabang ASC
            """
        )
    except sqlite3.Error as exc:
        logger.error("[Invoice] Gagal memuat daftar cabang billing: %s", exc)
        return []


def cek_revision_resi(no_resi, expected_revision, kode_cabang=None):
    """Memastikan Resi masih pada revision yang dilihat saat dipilih untuk Invoice."""
    nomor = str(no_resi or "").strip().upper()
    if not nomor:
        return False, None
    try:
        revision_diharapkan = int(expected_revision)
    except (TypeError, ValueError):
        return False, None

    cabang = str(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT") or "PUSAT"
    ).strip().upper()
    try:
        conn = get_db_connection()
        row = conn.execute(
            """
            SELECT revision
            FROM data_resi
            WHERE UPPER(no_resi) = UPPER(?) AND kode_cabang = ?
            LIMIT 1
            """,
            (nomor, cabang),
        ).fetchone()
        if row is None:
            return False, None
        revision_sekarang = int(row[0] or 0)
        return revision_sekarang == revision_diharapkan, revision_sekarang
    except (sqlite3.Error, TypeError, ValueError) as exc:
        logger.error("[Invoice] Gagal cek revision Resi %s: %s", nomor, exc)
        return False, None
    finally:
        _close(locals().get("conn"))


def ambil_resi_belum_ditagihkan(
    kode_cabang=None,
    *,
    semua_cabang=False,
    kode_cabang_list=None,
    keyword="",
    tanggal_awal=None,
    tanggal_akhir=None,
    limit=1000,
):
    """Ambil Resi yang belum mempunyai relasi Invoice untuk Billing Queue."""

    cabang = str(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT") or "PUSAT"
    ).strip().upper()
    keyword = str(keyword or "").strip().casefold()
    try:
        batas = max(1, min(int(limit), 5000))
    except (TypeError, ValueError):
        batas = 1000

    where = [
        """
        NOT EXISTS (
            SELECT 1
            FROM invoice_resi AS ir
            WHERE UPPER(ir.no_resi) = UPPER(r.no_resi)
        )
        """
    ]
    params = []

    if semua_cabang:
        allowed = [
            str(item or "").strip().upper()
            for item in (kode_cabang_list or [])
            if str(item or "").strip()
        ]
        allowed = list(dict.fromkeys(allowed))
        if allowed:
            placeholders = ",".join("?" for _ in allowed)
            where.append(f"r.kode_cabang IN ({placeholders})")
            params.extend(allowed)
    else:
        where.append("r.kode_cabang = ?")
        params.append(cabang)
    if tanggal_awal:
        where.append("DATE(r.tanggal_masuk) >= DATE(?)")
        params.append(str(tanggal_awal))
    if tanggal_akhir:
        where.append("DATE(r.tanggal_masuk) <= DATE(?)")
        params.append(str(tanggal_akhir))
    if keyword:
        pola = f"%{keyword}%"
        where.append(
            """
            (
                LOWER(COALESCE(r.no_resi, '')) LIKE ? OR
                LOWER(COALESCE(r.pengirim, '')) LIKE ? OR
                LOWER(COALESCE(r.penerima, '')) LIKE ? OR
                LOWER(COALESCE(r.kota_tujuan, '')) LIKE ? OR
                LOWER(COALESCE(r.nama_barang, '')) LIKE ?
            )
            """
        )
        params.extend([pola] * 5)

    params.append(batas)
    conn = None
    try:
        conn = get_db_connection()
        rows = conn.execute(
            f"""
            SELECT r.no_resi, r.kode_cabang, r.tanggal_masuk,
                   COALESCE(r.pengirim, ''), COALESCE(r.penerima, ''),
                   COALESCE(r.kota_tujuan, ''), COALESCE(r.nama_barang, ''),
                   COALESCE(r.koli, 0), COALESCE(r.berat, 0),
                   COALESCE(r.cbm, 0),
                   COALESCE(r.total_ongkir, 0),
                   COALESCE(r.jenis_pajak, 'NONPAJAK'),
                   COALESCE(r.subtotal_ongkir, r.total_ongkir, 0),
                   COALESCE(r.status_resi, ''),
                   COALESCE(r.revision, 0)
            FROM data_resi AS r
            WHERE {' AND '.join(where)}
            ORDER BY DATE(r.tanggal_masuk) DESC, r.no_resi DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "no_resi": str(row[0] or "").strip().upper(),
                "kode_cabang": str(row[1] or "").strip().upper(),
                "tanggal": str(row[2] or "").strip(),
                "pengirim": str(row[3] or "").strip().upper(),
                "penerima": str(row[4] or "").strip().upper(),
                "tujuan": str(row[5] or "").strip().upper(),
                "nama_barang": str(row[6] or "").strip().upper(),
                "koli": str(row[7] if row[7] is not None else "0"),
                "berat": str(row[8] if row[8] is not None else "0"),
                "kubik": str(row[9] if row[9] is not None else "0"),
                # Tetap expose total untuk kebutuhan tampilan Billing Queue,
                # tetapi Invoice akan memakai subtotal_ongkir sebagai dasar pajak.
                "ongkir": str(row[10] if row[10] is not None else "0"),
                "jenis_pajak": str(row[11] or "NONPAJAK").strip().upper(),
                "subtotal_ongkir": str(
                    row[12] if row[12] is not None else row[10] if row[10] is not None else "0"
                ),
                "status_resi": str(row[13] or "").strip().upper(),
                "revision": int(row[14] or 0),
            }
            for row in rows
        ]
    except sqlite3.Error as exc:
        logger.error("[Invoice] Gagal memuat Billing Queue: %s", exc)
        return []
    finally:
        _close(conn)


def _resolve_resi_aktif_cursor(cursor, nomor_resi):
    nomor = str(nomor_resi or "").strip().upper()
    if not nomor:
        return None
    kandidat = [nomor]
    kandidat.extend(
        varian for varian in sorted(_varian_nomor_resi_pajak(nomor))
        if varian not in kandidat
    )
    for kandidat_nomor in kandidat:
        row = cursor.execute(
            """
            SELECT no_resi, kode_cabang
            FROM data_resi
            WHERE UPPER(no_resi) = UPPER(?)
            LIMIT 1
            """,
            (kandidat_nomor,),
        ).fetchone()
        if row:
            return (
                str(row[0] or "").strip().upper(),
                str(row[1] or "").strip().upper() or None,
            )
    return nomor, None


def _sinkronkan_invoice_resi_cursor(cursor, no_invoice, items, source_resi=None):
    """Sinkronkan relasi operasional Invoice-Resi hanya dari metadata sumber.

    ``source_resi`` dipisahkan dari kolom Invoice yang terlihat supaya relasi
    operasional tetap utuh walaupun template menyembunyikan/menghapus kolom RESI.
    Bila invoice legacy tidak memiliki metadata sumber, relasi lama dipertahankan.
    """
    relasi = set()

    sumber = source_resi if isinstance(source_resi, (list, tuple, set)) else []
    if not sumber:
        if cursor.execute(
            "SELECT 1 FROM invoice_resi WHERE no_invoice = ? LIMIT 1",
            (no_invoice,),
        ).fetchone():
            return

    cursor.execute("DELETE FROM invoice_resi WHERE no_invoice = ?", (no_invoice,))
    for item in sumber:
        if isinstance(item, dict):
            nomor_snapshot = str(
                item.get("no_resi") or item.get("resi") or item.get("nomor_resi") or ""
            ).strip().upper()
            kode_cabang_snapshot = str(
                item.get("kode_cabang") or ""
            ).strip().upper() or None
        else:
            nomor_snapshot = str(item or "").strip().upper()
            kode_cabang_snapshot = None

        if not nomor_snapshot:
            continue
        resolved = _resolve_resi_aktif_cursor(cursor, nomor_snapshot)
        if resolved:
            no_resi_aktif, kode_cabang_aktif = resolved
            if kode_cabang_snapshot and kode_cabang_aktif:
                if kode_cabang_snapshot != str(kode_cabang_aktif).strip().upper():
                    continue
            relasi.add((no_resi_aktif, kode_cabang_aktif))

    if relasi:
        cursor.executemany(
            """
            INSERT OR IGNORE INTO invoice_resi (
                no_invoice, no_resi, kode_cabang
            ) VALUES (?, ?, ?)
            """,
            [
                (no_invoice, no_resi, kode_cabang)
                for no_resi, kode_cabang in sorted(relasi)
            ],
        )


def _sequence_invoice_berikutnya_cursor(cursor, prefix=None):
    """Preview sequence Invoice fixed; final number is always allocated atomically on save."""
    row = cursor.execute(
        """
        SELECT starting_count,current_count
        FROM numbering_counters
        WHERE kode_cabang=? AND document_type='INVOICE' AND series_code='INV'
          AND COALESCE(aktif,0)=1 AND deleted_at IS NULL
        LIMIT 1
        """,
        (numbering_service.CENTRAL_INVOICE_BRANCH,),
    ).fetchone()
    if not row:
        return 1
    return max(int(row[0] or 0), int(row[1] or 0) + 1)

def dapatkan_sequence_invoice_baru(prefix=None):
    conn = None
    try:
        conn = get_db_connection()
        return _sequence_invoice_berikutnya_cursor(conn.cursor(), prefix)
    except (sqlite3.Error, ValueError) as exc:
        logger.error("[Invoice] Gagal membaca sequence: %s", exc)
        return 1
    finally:
        _close(conn)

def _alokasikan_nomor_invoice_otomatis_cursor(cursor, header):
    result = numbering_service.allocate_number_cursor(
        cursor, "INVOICE", numbering_service.CENTRAL_INVOICE_BRANCH,
        tanggal=header.get("tanggal"),
    )
    return result.nomor

def _validasi_source_resi_invoice_cursor(cursor, source_resi):
    sumber = source_resi if isinstance(source_resi, (list, tuple, set)) else []
    for item in sumber:
        if not isinstance(item, dict):
            continue
        nomor = str(item.get("no_resi") or item.get("resi") or "").strip().upper()
        if not nomor:
            continue
        kode_cabang = str(item.get("kode_cabang") or "").strip().upper()
        revision_diharapkan = item.get("revision")
        try:
            revision_diharapkan = int(revision_diharapkan)
        except (TypeError, ValueError):
            return f"Revision Resi {nomor} tidak valid. Muat ulang Billing Queue."

        if kode_cabang:
            row = cursor.execute(
                """
                SELECT revision
                FROM data_resi
                WHERE UPPER(no_resi) = UPPER(?) AND kode_cabang = ?
                LIMIT 1
                """,
                (nomor, kode_cabang),
            ).fetchone()
        else:
            row = cursor.execute(
                """
                SELECT revision
                FROM data_resi
                WHERE UPPER(no_resi) = UPPER(?)
                LIMIT 1
                """,
                (nomor,),
            ).fetchone()

        if row is None:
            return f"Resi sumber {nomor} tidak ditemukan. Muat ulang Billing Queue."
        revision_sekarang = int(row[0] or 0)
        if revision_sekarang != revision_diharapkan:
            return (
                f"Resi {nomor} sudah berubah sejak dipilih. "
                "Muat ulang Billing Queue sebelum menyimpan Invoice."
            )
    return None


def _simpan_header_invoice(cursor, header, no_invoice, now, is_update):
    if is_update:
        existing = cursor.execute(
            "SELECT status FROM invoice_header WHERE no_invoice = ? LIMIT 1",
            (no_invoice,),
        ).fetchone()
        if existing and str(existing[0] or "").strip().upper() == "LUNAS":
            return "Invoice berstatus LUNAS tidak dapat diubah."
        cursor.execute(
            """
            UPDATE invoice_header
            SET tanggal = ?, client = ?, tipe_invoice = ?, jenis_pajak = ?,
                subtotal = ?, total_akhir = ?, status = ?, metadata_json = ?,
                template_version = ?, updated_at = ?
            WHERE no_invoice = ?
            """,
            (
                header["tanggal"], header["client"], header["tipe_invoice"],
                header["jenis_pajak"], header["subtotal"], header["total_akhir"],
                header["status"], header["metadata_json"],
                header["template_version"], now, no_invoice,
            ),
        )
        if cursor.rowcount == 0:
            return "Invoice yang akan diperbarui tidak ditemukan."
        cursor.execute("DELETE FROM invoice_detail WHERE no_invoice = ?", (no_invoice,))
        return None

    if cursor.execute(
        "SELECT 1 FROM invoice_header WHERE no_invoice = ?", (no_invoice,)
    ).fetchone():
        return "Nomor invoice sudah digunakan."

    cursor.execute(
        """
        INSERT INTO invoice_header (
            no_invoice, tanggal, client, tipe_invoice, jenis_pajak,
            subtotal, total_akhir, status, created_at,
            metadata_json, template_version, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            no_invoice, header["tanggal"], header["client"], header["tipe_invoice"],
            header["jenis_pajak"], header["subtotal"], header["total_akhir"],
            header["status"], now, header["metadata_json"],
            header["template_version"], now,
        ),
    )
    return None

def _simpan_detail_invoice(cursor, no_invoice, items):
    cursor.executemany(
        """
        INSERT INTO invoice_detail (
            no_invoice, nomor_urut, data_kolom, nominal_subtotal
        ) VALUES (?, ?, ?, ?)
        """,
        [
            (no_invoice, item["nomor_urut"], item["data_kolom"], item["nominal"])
            for item in items
        ],
    )

def simpan_atau_update_invoice(header, items, is_update=False):
    """Menyimpan atau memperbarui invoice beserta detailnya secara atomic."""

    no_invoice = str(header.get("no_invoice", "")).strip().upper()
    auto_prefix = str(header.get("auto_invoice_prefix") or "").strip().upper()
    if is_update and not no_invoice:
        return False, "Nomor invoice tidak boleh kosong."
    if not items:
        return False, "Item invoice tidak boleh kosong."
    # Invoice terpusat di SBY; hak tulis diperiksa pada branch efektif.
    invoice_branch = str(numbering_service.CENTRAL_INVOICE_BRANCH).strip().upper()
    try:
        _pastikan_boleh_tulis_cabang(invoice_branch)
    except PermissionError as exc:
        return False, str(exc)

    conn = None
    try:
        from datetime import datetime

        creator_name = str(
            CURRENT_SESSION.get("nama_lengkap")
            or CURRENT_SESSION.get("username")
            or "ADMIN"
        ).strip()
        if not is_update:
            try:
                metadata_obj = json.loads(str(header.get("metadata_json") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                metadata_obj = {}
            if not isinstance(metadata_obj, dict):
                metadata_obj = {}
            if not str(metadata_obj.get("signer") or "").strip():
                metadata_obj["signer"] = creator_name.upper()
                header["metadata_json"] = json.dumps(metadata_obj, ensure_ascii=False)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        if not is_update:
            no_invoice = _alokasikan_nomor_invoice_otomatis_cursor(cursor, header)
            if not no_invoice:
                conn.rollback()
                return False, "Nomor invoice tidak berhasil dibuat."
            header["no_invoice"] = no_invoice

        pesan = _validasi_source_resi_invoice_cursor(
            cursor, header.get("source_resi")
        )
        if pesan:
            conn.rollback()
            return False, pesan

        pesan = _simpan_header_invoice(cursor, header, no_invoice, now, is_update)
        if pesan:
            conn.rollback()
            return False, pesan

        _simpan_detail_invoice(cursor, no_invoice, items)
        _sinkronkan_invoice_resi_cursor(
            cursor, no_invoice, items, header.get("source_resi")
        )
        conn.commit()
        return True, "Sukses"
    except sqlite3.IntegrityError as exc:
        _rollback(conn)
        if "invoice_header.no_invoice" in str(exc):
            return False, "Nomor invoice sudah digunakan."
        logger.exception("[Invoice] Integrity error")
        return False, str(exc)
    except Exception as exc:
        _rollback(conn)
        logger.exception("[Invoice] Gagal simpan/update")
        return False, str(exc)
    finally:
        _close(conn)

def ambil_histori_invoice(limit=300):
    """Mengambil daftar histori invoice untuk tabel sebelah kiri."""
    try:
        return _fetchall(
            "SELECT no_invoice, tanggal, client, status, created_by_name FROM invoice_header ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    except Exception as e:
        logger.error(f"[Invoice] Gagal ambil histori: {e}")
        return []

def ambil_invoice_by_no(no_invoice):
    """Membaca data lengkap invoice (header & detail) untuk ditampilkan ke editor."""

    conn = None
    try:
        conn = get_db_connection()
        header = conn.execute(
            """
            SELECT client, tipe_invoice, jenis_pajak, status, tanggal, metadata_json,
                   created_by_user_id, created_by_username, created_by_name,
                   updated_by_user_id, updated_by_username, updated_by_name
            FROM invoice_header
            WHERE no_invoice = ?
            """,
            (no_invoice,)
        ).fetchone()

        if not header:
            return None, None

        details = conn.execute(
            "SELECT data_kolom FROM invoice_detail WHERE no_invoice = ? ORDER BY nomor_urut ASC",
            (no_invoice,)
        ).fetchall()

        return header, details
    except Exception as e:
        logger.error(f"[Invoice] Gagal baca detail invoice: {e}")
        return None, None
    finally:
        _close(conn)

# ==============================================================================
# 07. MASTER PENGIRIM (SHIPPER)
# ==============================================================================

def ambil_semua_master_pengirim(kode_cabang):
    """Menarik semua data pelanggan tetap pengirim di cabang saat ini"""
    kode_cabang = str(
        kode_cabang or CURRENT_SESSION.get('kode_cabang', 'PUSAT')
    ).strip()
    try:
        return _fetchall(
            """
            SELECT id_pengirim, kode_cabang,
                   COALESCE(nama, '') AS nama,
                   COALESCE(no_hp, '') AS no_hp,
                   COALESCE(alamat, '') AS alamat,
                   COALESCE(kota, '') AS kota
            FROM master_pengirim
            WHERE kode_cabang = ?
            ORDER BY TRIM(COALESCE(nama, '')) COLLATE NOCASE ASC
            """,
            (kode_cabang,),
        )
    except Exception as e:
        print(f"[Master Pengirim] Gagal mengambil data: {e}")
        return []

def ambil_histori_transaksi_by_pengirim(nama_pengirim, kode_cabang):
    """Melacak histori resi berdasarkan nama pengirim."""
    nama_pengirim = str(nama_pengirim or "").strip()
    kode_cabang = str(
        kode_cabang or CURRENT_SESSION.get('kode_cabang', 'PUSAT')
    ).strip()
    if not nama_pengirim:
        return []
    try:
        return _fetchall(
            """
            SELECT COALESCE(tanggal_masuk, '') AS tanggal_masuk,
                   COALESCE(no_resi, '') AS no_resi,
                   COALESCE(penerima, '') AS penerima,
                   COALESCE(koli, 0) AS koli,
                   COALESCE(berat, 0) AS berat,
                   COALESCE(cbm, 0) AS cbm,
                   COALESCE(total_ongkir, 0) AS total_ongkir
            FROM data_resi
            WHERE TRIM(UPPER(COALESCE(pengirim, ''))) = TRIM(UPPER(?))
              AND TRIM(UPPER(COALESCE(kode_cabang, ''))) = TRIM(UPPER(?))
            ORDER BY tanggal_masuk DESC, rowid DESC
            """,
            (nama_pengirim, kode_cabang),
        )
    except Exception as e:
        print(f"[Histori Pengirim] Gagal mengambil data: {e}")
        return []

def tambah_master_pengirim(kode_cabang, nama, no_hp="", kota="", alamat=""):
    """Menambah master pengirim baru tanpa mengubah data master yang sudah ada."""
    kode_cabang = _kode_cabang_aktif(kode_cabang)
    nama, no_hp, kota, alamat = (
        _upper(nama), _text(no_hp), _upper(kota), _upper(alamat)
    )
    if not nama:
        return False, "Nama pengirim tidak boleh kosong."
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError as exc:
        return False, str(exc)

    try:
        with _db_transaction(immediate=True) as (conn, cursor):
            sudah_ada = cursor.execute(
                """
                SELECT id_pengirim FROM master_pengirim
                WHERE kode_cabang = ?
                  AND TRIM(UPPER(COALESCE(nama, ''))) = TRIM(UPPER(?))
                LIMIT 1
                """,
                (kode_cabang, nama),
            ).fetchone()
            if sudah_ada:
                conn.rollback()
                return False, f"Pengirim '{nama}' sudah terdaftar di cabang ini."

            cursor.execute(
                """
                INSERT INTO master_pengirim (
                    id_pengirim, kode_cabang, nama, no_hp, alamat, kota, is_synced
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    f"SHP-{uuid.uuid4().hex[:12].upper()}",
                    kode_cabang, nama, no_hp if no_hp else None, alamat, kota,
                ),
            )
        return True, "Pengirim berhasil ditambahkan."
    except Exception as exc:
        return False, str(exc)

def update_master_pengirim_dari_tabel(
    id_pengirim, kode_cabang, nama, no_hp, kota, alamat
):
    nama, no_hp, kota, alamat = (
        _upper(nama), _text(no_hp), _upper(kota), _upper(alamat)
    )
    if not nama:
        return False, "Nama pengirim tidak boleh kosong."
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError as exc:
        return False, str(exc)

    try:
        with _db_transaction() as (_, cursor):
            cursor.execute(
                """
                UPDATE master_pengirim
                SET nama = ?, no_hp = ?, kota = ?, alamat = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id_pengirim = ? AND kode_cabang = ?
                """,
                (nama, no_hp if no_hp else None, kota, alamat,
                 id_pengirim, kode_cabang),
            )
        return True, ""
    except Exception as exc:
        return False, str(exc)

# ==============================================================================
# 08. MASTER PENERIMA (CONSIGNEE)
# ==============================================================================

def ambil_semua_master_penerima(kode_cabang):
    """Menarik semua data pelanggan tetap penerima di cabang saat ini untuk ditampilkan di tabel"""
    return _fetchall(
        """
        SELECT id_penerima, kode_cabang, nama, no_hp, alamat, kota
        FROM master_penerima
        WHERE kode_cabang = ?
        ORDER BY nama ASC
        """,
        (kode_cabang,),
    )

def ambil_histori_transaksi_by_penerima(nama_penerima, kode_cabang):
    """(Opsional) Melacak seluruh histori resi kargo yang pernah diterima oleh penerima ini"""
    return _fetchall(
        """
        SELECT tanggal_masuk, no_resi, pengirim, koli, berat, cbm, kota_asal, total_ongkir
        FROM data_resi
        WHERE penerima = ? AND kode_cabang = ?
        ORDER BY tanggal_masuk DESC, rowid DESC
        """,
        (nama_penerima, kode_cabang),
    )

def ambil_semua_master_penerima_full(kode_cabang):
    """Mengambil data lengkap master penerima ter-optimasi dengan GROUP BY."""
    kode_cabang = str(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()
    try:
        return _fetchall(
            """
            SELECT p.id_penerima,
                   COALESCE(p.nama, ''),
                   COALESCE(p.no_hp, ''),
                   COALESCE(p.alamat, ''),
                   COALESCE(p.kota, ''),
                   COALESCE(p.provinsi, ''),
                   COUNT(r.no_resi) AS total_transaksi,
                   COALESCE(p.pembayaran, 'TF / INVOICE'),
                   COALESCE(p.status_tagihan, 'NORMAL')
            FROM master_penerima p
            LEFT JOIN data_resi r 
                   ON r.kode_cabang = p.kode_cabang 
                  AND TRIM(UPPER(r.penerima)) = TRIM(UPPER(p.nama))
            WHERE p.kode_cabang = ?
            GROUP BY p.id_penerima
            ORDER BY TRIM(COALESCE(p.nama, '')) COLLATE NOCASE ASC
            """,
            (kode_cabang,),
        )
    except sqlite3.Error as exc:
        logger.error("[Master Penerima] Gagal mengambil data: %s", exc)
        return []

def tambah_master_penerima(
    kode_cabang,
    nama,
    no_hp="",
    alamat="",
    kota="",
    provinsi="",
    pembayaran="TF / INVOICE",
):
    """Menambah master penerima baru tanpa mengubah data master yang sudah ada."""
    kode_cabang = _kode_cabang_aktif(kode_cabang)
    nama, no_hp, alamat, kota, provinsi = (
        _upper(nama), _text(no_hp), _upper(alamat), _upper(kota), _upper(provinsi)
    )
    pembayaran = _upper(pembayaran or "TF / INVOICE") or "TF / INVOICE"
    if not nama:
        return False, "Nama penerima tidak boleh kosong."
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError as exc:
        return False, str(exc)

    try:
        with _db_transaction(immediate=True) as (conn, cursor):
            sudah_ada = cursor.execute(
                """
                SELECT id_penerima FROM master_penerima
                WHERE kode_cabang = ?
                  AND TRIM(UPPER(COALESCE(nama, ''))) = TRIM(UPPER(?))
                LIMIT 1
                """,
                (kode_cabang, nama),
            ).fetchone()
            if sudah_ada:
                conn.rollback()
                return False, f"Penerima '{nama}' sudah terdaftar di cabang ini."

            cursor.execute(
                """
                INSERT INTO master_penerima (
                    id_penerima, kode_cabang, nama, no_hp, alamat, kota,
                    provinsi, total_transaksi, pembayaran, status_tagihan, is_synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'NORMAL', 0)
                """,
                (
                    f"CNE-{uuid.uuid4().hex[:12].upper()}",
                    kode_cabang, nama, no_hp if no_hp else None, alamat, kota,
                    provinsi if provinsi else None, pembayaran,
                ),
            )
        return True, "Penerima berhasil ditambahkan."
    except Exception as exc:
        return False, str(exc)

def ubah_status_tagihan_penerima(id_penerima, status_baru, kode_cabang):
    """Mengubah status tagihan penerima."""
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
        with _db_transaction() as (_, cursor):
            cursor.execute(
                """
                UPDATE master_penerima
                SET status_tagihan = ?, is_synced = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id_penerima = ? AND kode_cabang = ?
                """,
                (status_baru, id_penerima, kode_cabang),
            )
            berubah = cursor.rowcount > 0
        return berubah
    except sqlite3.Error as exc:
        logger.error("[Master Penerima] Gagal mengubah status: %s", exc)
        return False

def update_master_penerima_dari_tabel(
    id_penerima, kode_cabang, nama, no_hp, alamat, kota, provinsi, pembayaran
):
    id_penerima = _text(id_penerima)
    kode_cabang = _text(kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT"))
    nama, no_hp, alamat, kota, provinsi = (
        _upper(nama), _text(no_hp), _upper(alamat), _upper(kota), _upper(provinsi)
    )
    pembayaran = _upper(pembayaran or "TF / INVOICE")
    if not nama:
        return False, "Nama penerima tidak boleh kosong."
    try:
        _pastikan_boleh_tulis_cabang(kode_cabang)
    except PermissionError as exc:
        return False, str(exc)

    try:
        with _db_transaction() as (_, cursor):
            cursor.execute(
                """
                UPDATE master_penerima
                SET nama = ?, no_hp = ?, alamat = ?, kota = ?, provinsi = ?,
                    pembayaran = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id_penerima = ? AND kode_cabang = ?
                """,
                (
                    nama, no_hp if no_hp else None, alamat, kota,
                    provinsi if provinsi else None, pembayaran,
                    id_penerima, kode_cabang,
                ),
            )
        return True, ""
    except Exception as exc:
        return False, str(exc)

# ==============================================================================
# 09. MASTER TRUK & SOPIR
# ==============================================================================

def _normalisasi_input_truk(nopol, jenis, sopir, hp, ket, foto):
    return (
        str(nopol or "").strip().upper(),
        str(jenis or "").strip(),
        str(sopir or "").strip().upper(),
        str(hp or "").strip(),
        str(ket or "").strip().upper(),
        str(foto or "").strip(),
    )

def simpan_atau_update_truk(
    db_name,
    no_polisi,
    nama_sopir,
    jenis_truk,
    hp_sopir,
    ket_truk,
    foto_truk="",
    kode_cabang=None,
):
    """Menambah atau memperbarui truk pada cabang aktif."""
    cabang = _kode_cabang_aktif(kode_cabang)
    nopol, jenis, sopir, hp, ket, foto = _normalisasi_input_truk(
        no_polisi, jenis_truk, nama_sopir, hp_sopir, ket_truk, foto_truk
    )
    if not cabang:
        return False, "Kode cabang tidak tersedia. Silakan login ulang."
    if not nopol:
        return False, "No. Polisi wajib diisi."
    if not jenis:
        return False, "Jenis truk wajib diisi."
    try:
        _pastikan_boleh_tulis_cabang(cabang)
    except PermissionError as exc:
        return False, str(exc)

    try:
        with _db_transaction(db_name, immediate=True) as (_, cursor):
            cursor.execute(
                """
                INSERT INTO truk (
                    kode_cabang, no_polisi, jenis_truk,
                    nama_sopir, hp_sopir, ket_truk,
                    foto_truk, is_synced, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                ON CONFLICT(kode_cabang, no_polisi) DO UPDATE SET
                    jenis_truk = CASE WHEN TRIM(excluded.jenis_truk) <> ''
                                      THEN excluded.jenis_truk ELSE truk.jenis_truk END,
                    nama_sopir = CASE WHEN TRIM(excluded.nama_sopir) <> ''
                                      THEN excluded.nama_sopir ELSE truk.nama_sopir END,
                    hp_sopir = CASE WHEN TRIM(excluded.hp_sopir) <> ''
                                    THEN excluded.hp_sopir ELSE truk.hp_sopir END,
                    ket_truk = CASE WHEN TRIM(excluded.ket_truk) <> ''
                                    THEN excluded.ket_truk ELSE truk.ket_truk END,
                    foto_truk = CASE WHEN TRIM(excluded.foto_truk) <> ''
                                     THEN excluded.foto_truk ELSE truk.foto_truk END,
                    is_synced = 0,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (cabang, nopol, jenis, sopir, hp, ket, foto),
            )
        return True, ""
    except sqlite3.Error as exc:
        return False, str(exc)

def ambil_semua_truk(db_name=None, kode_cabang=None):
    """Menampilkan daftar truk milik cabang aktif."""
    try:
        return _fetchall(
            """
            SELECT no_polisi, nama_sopir, jenis_truk, hp_sopir, ket_truk
            FROM truk
            WHERE kode_cabang = ?
            ORDER BY no_polisi ASC
            """,
            (_kode_cabang_aktif(kode_cabang),),
            db_name=db_name,
        )
    except sqlite3.Error as exc:
        logger.error("[Truk] Gagal mengambil data: %s", exc)
        return []

def ambil_semua_truk_full(kode_cabang=None):
    """Mengambil seluruh data truk milik cabang aktif untuk tabel UI."""
    try:
        return _fetchall(
            """
            SELECT no_polisi, jenis_truk, nama_sopir,
                   hp_sopir, ket_truk, foto_truk
            FROM truk
            WHERE kode_cabang = ?
            ORDER BY no_polisi ASC
            """,
            (_kode_cabang_aktif(kode_cabang),),
        )
    except sqlite3.Error as exc:
        logger.error("[Truk] Gagal mengambil data lengkap: %s", exc)
        return []

def simpan_atau_update_truk_full(
    nopol, jenis, sopir, hp, ket, foto, mode="TAMBAH", kode_cabang=None
):
    """Tambah/edit master Truk hanya pada cabang login aktif."""
    cabang = _kode_cabang_aktif(kode_cabang)
    nopol, jenis, sopir, hp, ket, foto = _normalisasi_input_truk(
        nopol, jenis, sopir, hp, ket, foto
    )
    mode = _upper(mode or "TAMBAH")
    if not cabang:
        return False, "Kode cabang tidak tersedia. Silakan login ulang."
    if not nopol:
        return False, "No. Polisi wajib diisi."
    if not jenis:
        return False, "Jenis truk wajib diisi."
    try:
        _pastikan_boleh_tulis_cabang(cabang)
    except PermissionError as exc:
        return False, str(exc)

    try:
        with _db_transaction(immediate=True) as (conn, cursor):
            ada = cursor.execute(
                "SELECT 1 FROM truk WHERE kode_cabang = ? AND no_polisi = ?",
                (cabang, nopol),
            ).fetchone() is not None

            if mode == "TAMBAH":
                if ada:
                    conn.rollback()
                    return False, (
                        f"No. Polisi {nopol} sudah terdaftar pada "
                        f"cabang {cabang}. Gunakan menu Edit untuk memperbarui data."
                    )
                cursor.execute(
                    """
                    INSERT INTO truk (
                        kode_cabang, no_polisi, jenis_truk,
                        nama_sopir, hp_sopir, ket_truk,
                        foto_truk, is_synced, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                    """,
                    (cabang, nopol, jenis, sopir, hp, ket, foto),
                )
            elif mode == "EDIT":
                if not ada:
                    conn.rollback()
                    return False, (
                        f"Data truk {nopol} tidak ditemukan pada cabang {cabang}."
                    )
                cursor.execute(
                    """
                    UPDATE truk
                    SET jenis_truk = ?, nama_sopir = ?, hp_sopir = ?,
                        ket_truk = ?, foto_truk = ?, is_synced = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE kode_cabang = ? AND no_polisi = ?
                    """,
                    (jenis, sopir, hp, ket, foto, cabang, nopol),
                )
            else:
                conn.rollback()
                return False, f"Mode penyimpanan truk tidak dikenal: {mode}"
        return True, ""
    except sqlite3.Error as exc:
        return False, str(exc)

# ==============================================================================
# 10. MASTER KAPAL
# ==============================================================================

def ambil_semua_kapal_full():
    """Menarik semua kolom data kapal kargo terdaftar untuk di-render ke UI"""
    try:
        return _fetchall(
            """
            SELECT COALESCE(nama_kapal,''), COALESCE(tujuan,''),
                   COALESCE(ket_kapal,''), COALESCE(foto_kapal,'')
            FROM kapal
            ORDER BY nama_kapal ASC
            """
        )
    except Exception as e:
        logger.error(f"[Kapal] Gagal mengambil data: {e}")
        return []

def simpan_atau_update_kapal_full(nama_kapal, tujuan, ket, foto, mode="TAMBAH"):
    """Menyimpan atau memperbarui data kapal ke database SQLite."""
    nama_kapal, tujuan, ket, foto = (
        _upper(nama_kapal), _upper(tujuan), _upper(ket), _text(foto)
    )
    mode = _upper(mode or "TAMBAH")
    if not nama_kapal:
        return False, "Nama Kapal wajib diisi."

    try:
        with _db_transaction(immediate=True) as (conn, cursor):
            ada = cursor.execute(
                "SELECT 1 FROM kapal WHERE nama_kapal = ?", (nama_kapal,)
            ).fetchone() is not None
            if mode == "TAMBAH":
                if ada:
                    conn.rollback()
                    return (
                        False,
                        f"Kapal '{nama_kapal}' sudah terdaftar. Gunakan menu Edit untuk memperbarui data.",
                    )
                cursor.execute(
                    """
                    INSERT INTO kapal (
                        nama_kapal, tujuan, ket_kapal, foto_kapal,
                        is_synced, updated_at
                    ) VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                    """,
                    (nama_kapal, tujuan, ket, foto),
                )
            elif mode == "EDIT":
                if not ada:
                    conn.rollback()
                    return False, f"Data Kapal '{nama_kapal}' tidak ditemukan."
                cursor.execute(
                    """
                    UPDATE kapal
                    SET tujuan = ?, ket_kapal = ?, foto_kapal = ?,
                        is_synced = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE nama_kapal = ?
                    """,
                    (tujuan, ket, foto, nama_kapal),
                )
            else:
                conn.rollback()
                return False, f"Mode penyimpanan Kapal tidak dikenal: {mode}"
        return True, ""
    except Exception as exc:
        return False, str(exc)

# ==============================================================================
# 11. SETTING SISTEM & CABANG
# ==============================================================================

def ambil_semua_data_cabang(limit=10):
    """Mengambil daftar kantor cabang dari database."""
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 10
    try:
        return _fetchall(
            """
            SELECT kode_cabang, nama_cabang, resi_prefix,
                   start_seq_json, aturan_prefix
            FROM data_cabang
            ORDER BY kode_cabang ASC
            LIMIT ?
            """,
            (limit,),
        )
    except sqlite3.Error as exc:
        logger.error("[Setting] Gagal mengambil cabang: %s", exc)
        return []

_ADMIN_USER_FUNCTION = "admin-user-management"


def _online_user_management_active() -> bool:
    """True hanya untuk akun Supabase aktif; DEV_SUPER tetap lokal."""
    return (
        not bool(CURRENT_SESSION.get("is_developer"))
        and bool(str(CURRENT_SESSION.get("auth_email") or "").strip())
    )


def _invoke_user_management(action: str, payload: dict | None = None) -> dict:
    """Panggil Edge Function manajemen user dengan JWT sesi aktif.

    Dipanggil langsung via HTTP agar error body dari Edge Function dapat
    diteruskan ke UI/log secara jelas, tanpa bergantung pada formatting
    exception versi supabase-py. Tidak pernah menggunakan service-role key.
    """
    if not _online_user_management_active():
        raise RuntimeError("Manajemen user Supabase hanya tersedia untuk akun online.")

    token = _supabase_access_token()
    if not token:
        raise RuntimeError("Sesi Supabase tidak aktif. Silakan login ulang.")

    endpoint = (
        f"{str(SUPABASE_URL or '').rstrip('/')}/functions/v1/"
        f"{_ADMIN_USER_FUNCTION}"
    )
    if not endpoint.startswith("http"):
        raise RuntimeError("SUPABASE_URL belum dikonfigurasi.")

    body = {"action": str(action or '').strip().lower()}
    if isinstance(payload, dict):
        body.update(payload)

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": str(SUPABASE_PUBLISHABLE_KEY or ""),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
        detail = str(
            data.get("error")
            or data.get("message")
            or raw
            or f"HTTP {exc.code}"
        ).strip()
        raise RuntimeError(
            f"Edge Function {_ADMIN_USER_FUNCTION} mengembalikan HTTP "
            f"{exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Tidak dapat menghubungi Edge Function {_ADMIN_USER_FUNCTION}: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Gagal memanggil Edge Function {_ADMIN_USER_FUNCTION}: {exc}"
        ) from exc

    try:
        data = json.loads(raw) if raw else {}
    except Exception as exc:
        raise RuntimeError(
            f"Respons Edge Function {_ADMIN_USER_FUNCTION} bukan JSON yang valid "
            f"(HTTP {status_code})."
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Respons Edge Function {_ADMIN_USER_FUNCTION} tidak valid "
            f"(HTTP {status_code})."
        )
    if not bool(data.get("ok", False)):
        raise RuntimeError(
            str(data.get("error") or data.get("message") or
                f"Operasi manajemen user gagal (HTTP {status_code}).")
        )
    return data


def _cache_remote_user_data(payload: dict) -> None:
    """Cerminkan data user remote ke SQLite hanya sebagai cache/UI offline."""
    branches = list(payload.get("branches") or [])
    users = list(payload.get("users") or [])
    with _db_transaction(immediate=True) as (_, cursor):
        valid_branches = {
            _upper(item.get("kode_cabang"))
            for item in branches
            if _upper(item.get("kode_cabang"))
        }
        # Data user online adalah cache; jangan sentuh DEV_SYS/local sandbox.
        cursor.execute(
            "DELETE FROM user_cabang_access WHERE id_user IN (SELECT id_user FROM manajemen_user WHERE UPPER(kode_cabang) <> 'DEV_SYS')"
        )
        cursor.execute("DELETE FROM manajemen_user WHERE UPPER(kode_cabang) <> 'DEV_SYS'")

        for user in users:
            user_id = _text(user.get("id_user"))
            username = _upper(user.get("username"))
            home = _upper(user.get("kode_cabang"))
            if not user_id or not username or not home:
                continue
            if home not in valid_branches:
                continue
            role_remote = _upper(user.get("role") or "ADMIN") or "ADMIN"
            role_local = "SUPER_ADMIN" if role_remote == "SUPER" else role_remote
            status = _upper(user.get("status_user") or "AKTIF") or "AKTIF"
            cursor.execute(
                """
                INSERT INTO manajemen_user(
                    id_user, username, password, role, nama_lengkap,
                    kode_cabang, status_user
                ) VALUES (?, ?, '', ?, ?, ?, ?)
                """
                , (
                    user_id,
                    username,
                    role_local,
                    _text(user.get("nama_lengkap")) or username,
                    home,
                    status,
                ),
            )
            akses = {
                _upper(code)
                for code in (user.get("akses_cabang") or [])
                if _upper(code) and _upper(code) in valid_branches
            }
            akses.add(home)
            if bool(user.get("akses_otomatis")):
                akses = set(valid_branches)
            cursor.executemany(
                "INSERT OR IGNORE INTO user_cabang_access(id_user, kode_cabang) VALUES (?, ?)",
                [(user_id, code) for code in sorted(akses)],
            )


def _remote_user_list() -> dict:
    payload = _invoke_user_management("list")
    _cache_remote_user_data(payload)
    return {
        "branches": list(payload.get("branches") or []),
        "users": list(payload.get("users") or []),
    }


def ambil_data_akses_cabang_user():
    """Remote-first untuk akun Supabase; SQLite tetap dipakai sebagai fallback/cache offline."""
    if _online_user_management_active():
        try:
            return _remote_user_list()
        except Exception as exc:
            logger.warning("[User] Remote list gagal, memakai cache lokal: %s", exc)
    return _ambil_data_akses_cabang_user_local()


def simpan_akses_cabang_users(user_access_rows):
    """Simpan branch scope ke Supabase untuk akun online, lalu refresh cache lokal."""
    try:
        _pastikan_super_admin()
        rows = list(user_access_rows or [])
        if _online_user_management_active():
            result = _invoke_user_management(
                "access",
                {"rows": [
                    {
                        "id_user": _text(row.get("id_user")),
                        "kode_cabang": [
                            _upper(code)
                            for code in (row.get("kode_cabang") or [])
                            if _upper(code)
                        ],
                    }
                    for row in rows
                ]},
            )
            _cache_remote_user_data(result)
            return True, str(result.get("message") or "Akses cabang user berhasil disimpan di Supabase.")
        return _simpan_akses_cabang_users_local(rows)
    except PermissionError as exc:
        return False, str(exc)
    except Exception as exc:
        logger.exception("[User] Gagal menyimpan akses cabang")
        return False, str(exc)


def buat_user_baru(data_user):
    """Buat user online di Supabase/Auth + profile + branch access; developer tetap lokal."""
    try:
        _pastikan_super_admin()
        if _online_user_management_active():
            data = dict(data_user or {})
            username = _upper(data.get("username"))
            if "@" not in username:
                return False, "Username akun online harus berupa email Supabase (contoh: user@mkt.log)."
            result = _invoke_user_management(
                "create",
                {
                    "username": username,
                    "nama_lengkap": _text(data.get("nama_lengkap")),
                    "password": str(data.get("password") or ""),
                    "role": _upper(data.get("role") or "ADMIN"),
                    "kode_cabang": _upper(data.get("kode_cabang")),
                    "akses_cabang": [_upper(code) for code in (data.get("akses_cabang") or []) if _upper(code)],
                },
            )
            _cache_remote_user_data(result)
            return True, str(result.get("message") or f"User {username} berhasil dibuat di Supabase.")
        return _buat_user_baru_local(data_user)
    except PermissionError as exc:
        return False, str(exc)
    except Exception as exc:
        logger.exception("[User] Gagal membuat user")
        return False, str(exc)


def ubah_user(data_user):
    """Update profile/role/home/access di Supabase untuk akun online."""
    try:
        _pastikan_super_admin()
        data = dict(data_user or {})
        if _online_user_management_active():
            result = _invoke_user_management(
                "update",
                {
                    "id_user": _text(data.get("id_user")),
                    "nama_lengkap": _text(data.get("nama_lengkap")),
                    "role": _upper(data.get("role") or "ADMIN"),
                    "kode_cabang": _upper(data.get("kode_cabang")),
                    "akses_cabang": [_upper(code) for code in (data.get("akses_cabang") or []) if _upper(code)],
                },
            )
            _cache_remote_user_data(result)
            updated = next(
                (
                    item for item in result.get("users", [])
                    if _text(item.get("id_user")) == _text(data.get("id_user"))
                ),
                None,
            )
            if updated and _text(updated.get("id_user")) == _text(CURRENT_SESSION.get("id_user")):
                CURRENT_SESSION["nama_lengkap"] = _text(updated.get("nama_lengkap"))
                CURRENT_SESSION["home_kode_cabang"] = _upper(updated.get("kode_cabang"))
                CURRENT_SESSION["home_nama_cabang"] = _text(updated.get("nama_cabang"))
                CURRENT_SESSION["kode_cabang"] = _upper(updated.get("kode_cabang"))
                CURRENT_SESSION["role"] = "SUPER_ADMIN" if _upper(updated.get("role")) == "SUPER" else _upper(updated.get("role") or "ADMIN")
                refresh_session = globals().get("_refresh_current_session_access")
                if callable(refresh_session):
                    refresh_session()
            return True, str(result.get("message") or "User berhasil diperbarui di Supabase.")
        return _ubah_user_local(data_user)
    except PermissionError as exc:
        return False, str(exc)
    except Exception as exc:
        logger.exception("[User] Gagal mengubah user")
        return False, str(exc)


def _refresh_current_session_access() -> None:
    """Refresh helper lokal agar tidak menambah dependency import config secara global."""
    try:
        from config import refresh_akses_cabang_session
        refresh_akses_cabang_session()
    except Exception as exc:
        logger.warning("[User] Gagal refresh branch scope sesi aktif: %s", exc)


def _ambil_data_akses_cabang_user_local():
    """Data user dan branch scope untuk UI Manajemen Akses Cabang."""

    try:
        branches = _fetchall(
            """
            SELECT kode_cabang, nama_cabang
            FROM data_cabang
            WHERE UPPER(kode_cabang) <> 'DEV_SYS'
            ORDER BY nama_cabang COLLATE NOCASE, kode_cabang
            """
        )
        users = _fetchall(
            """
            SELECT
                u.id_user, u.username, u.role, u.nama_lengkap,
                u.kode_cabang, COALESCE(c.nama_cabang, u.kode_cabang),
                COALESCE(u.status_user, 'AKTIF'),
                GROUP_CONCAT(a.kode_cabang, ',')
            FROM manajemen_user AS u
            LEFT JOIN data_cabang AS c
                ON c.kode_cabang = u.kode_cabang
            LEFT JOIN user_cabang_access AS a
                ON a.id_user = u.id_user
            GROUP BY
                u.id_user, u.username, u.role, u.nama_lengkap,
                u.kode_cabang, c.nama_cabang, u.status_user
            ORDER BY u.username COLLATE NOCASE, u.id_user
            """
        )
    except sqlite3.Error as exc:
        logger.error("[Setting] Gagal mengambil akses cabang user: %s", exc)
        return {"branches": [], "users": []}

    branch_rows = [
        {
            "kode_cabang": _upper(kode),
            "nama_cabang": _text(nama) or _upper(kode),
        }
        for kode, nama in branches
        if _upper(kode)
    ]

    user_rows = []
    for (
        id_user, username, role, nama_lengkap,
        kode_cabang, nama_cabang, status_user, akses_csv,
    ) in users:
        akses = {
            _upper(kode)
            for kode in str(akses_csv or "").split(",")
            if _upper(kode)
        }
        home = _upper(kode_cabang)
        if home:
            akses.add(home)
        role_bersih = _upper(role or "ADMIN") or "ADMIN"
        akses_otomatis = (
            role_bersih in CENTRAL_BRANCH_ROLES
            or home == "PUSAT"
        )
        user_rows.append({
            "id_user": _text(id_user),
            "username": _upper(username),
            "role": role_bersih,
            "nama_lengkap": _text(nama_lengkap),
            "kode_cabang": home,
            "nama_cabang": _text(nama_cabang) or home,
            "status_user": _upper(status_user or "AKTIF") or "AKTIF",
            "akses_cabang": sorted(akses),
            "akses_otomatis": akses_otomatis,
        })

    return {"branches": branch_rows, "users": user_rows}


def _simpan_akses_cabang_users_local(user_access_rows):
    """
    Menyimpan branch scope user secara atomic.

    Home branch selalu dipertahankan. Role pusat dan user ber-home PUSAT
    selalu memperoleh seluruh cabang bisnis, sesuai policy login di config.py.
    """

    try:
        _pastikan_super_admin()
    except Exception as exc:
        return False, str(exc)

    rows = list(user_access_rows or [])
    try:
        with _db_transaction(immediate=True) as (_, cursor):
            valid_branches = {
                _upper(row[0])
                for row in cursor.execute(
                    "SELECT kode_cabang FROM data_cabang"
                ).fetchall()
                if _upper(row[0])
            }
            business_branches = {
                kode for kode in valid_branches
                if kode != "DEV_SYS"
            }

            for entry in rows:
                id_user = _text(entry.get("id_user"))
                if not id_user:
                    continue

                user_row = cursor.execute(
                    """
                    SELECT role, kode_cabang
                    FROM manajemen_user
                    WHERE id_user = ?
                    LIMIT 1
                    """,
                    (id_user,),
                ).fetchone()
                if user_row is None:
                    raise ValueError(
                        f"User dengan ID '{id_user}' tidak ditemukan."
                    )

                role = _upper(user_row[0] or "ADMIN") or "ADMIN"
                home = _upper(user_row[1])
                akses_otomatis = (
                    role in CENTRAL_BRANCH_ROLES
                    or home == "PUSAT"
                )

                if akses_otomatis:
                    desired = set(business_branches)
                    if home in valid_branches:
                        desired.add(home)
                else:
                    requested = {
                        _upper(kode)
                        for kode in entry.get("kode_cabang", [])
                        if _upper(kode)
                    }
                    unknown = requested - valid_branches
                    if unknown:
                        raise ValueError(
                            "Cabang tidak dikenal pada akses user "
                            f"{id_user}: {', '.join(sorted(unknown))}."
                        )
                    desired = requested & business_branches
                    if home in valid_branches:
                        desired.add(home)

                cursor.execute(
                    "DELETE FROM user_cabang_access WHERE id_user = ?",
                    (id_user,),
                )
                cursor.executemany(
                    """
                    INSERT INTO user_cabang_access (id_user, kode_cabang)
                    VALUES (?, ?)
                    """,
                    [(id_user, kode) for kode in sorted(desired)],
                )

        return True, "Akses cabang user berhasil disimpan."
    except Exception as exc:
        logger.exception("[Setting] Gagal menyimpan akses cabang user")
        return False, str(exc)


_VALID_USER_ROLES = {"SUPER_ADMIN", "OWNER", "ADMIN_PUSAT", "FINANCE", "ADMIN"}


def _pastikan_super_admin():
    role = _upper(CURRENT_SESSION.get("role"))
    if role != "SUPER_ADMIN":
        raise PermissionError("Hanya SUPER_ADMIN yang dapat mengelola akun user.")


def _ambil_cabang_bisnis_cursor(cursor):
    rows = cursor.execute(
        """
        SELECT kode_cabang
        FROM data_cabang
        WHERE UPPER(kode_cabang) <> 'DEV_SYS'
        """
    ).fetchall()
    return {_upper(row[0]) for row in rows if _upper(row[0])}


def _normalisasi_role_user(role):
    role_bersih = _upper(role or "ADMIN") or "ADMIN"
    if role_bersih not in _VALID_USER_ROLES:
        raise ValueError(f"Role user tidak valid: {role_bersih}.")
    return role_bersih


def _set_akses_user_cursor(cursor, id_user, role, home, requested=None):
    valid_branches = _ambil_cabang_bisnis_cursor(cursor)
    home = _upper(home)
    if home not in valid_branches:
        raise ValueError(f"Home branch '{home}' tidak ditemukan/valid.")

    otomatis = role in CENTRAL_BRANCH_ROLES or home == "PUSAT"
    if otomatis:
        desired = set(valid_branches)
    else:
        requested_set = {_upper(kode) for kode in (requested or []) if _upper(kode)}
        unknown = requested_set - valid_branches
        if unknown:
            raise ValueError(
                "Cabang akses tidak dikenal: " + ", ".join(sorted(unknown))
            )
        desired = requested_set
        desired.add(home)

    cursor.execute("DELETE FROM user_cabang_access WHERE id_user = ?", (id_user,))
    cursor.executemany(
        """
        INSERT INTO user_cabang_access (id_user, kode_cabang)
        VALUES (?, ?)
        """,
        [(id_user, kode) for kode in sorted(desired)],
    )


def _buat_user_baru_local(data_user):
    """Membuat akun + branch access dalam satu transaksi. Khusus SUPER_ADMIN."""
    try:
        _pastikan_super_admin()
        data = dict(data_user or {})
        username = _upper(data.get("username"))
        nama = _text(data.get("nama_lengkap"))
        password = str(data.get("password") or "")
        role = _normalisasi_role_user(data.get("role"))
        home = _upper(data.get("kode_cabang"))
        akses = list(data.get("akses_cabang") or [])

        if not username:
            raise ValueError("Username wajib diisi.")
        if not re.fullmatch(r"[A-Z0-9._-]{3,32}", username):
            raise ValueError(
                "Username minimal 3 karakter dan hanya boleh berisi huruf, angka, titik, garis bawah, atau strip."
            )
        if not nama:
            raise ValueError("Nama lengkap wajib diisi.")
        if not password:
            raise ValueError("Password wajib diisi.")

        id_user = f"USR-{uuid.uuid4().hex[:12].upper()}"
        with _db_transaction(immediate=True) as (_, cursor):
            if cursor.execute(
                "SELECT 1 FROM manajemen_user WHERE UPPER(username) = ? LIMIT 1",
                (username,),
            ).fetchone():
                raise ValueError(f"Username '{username}' sudah digunakan.")
            if home not in _ambil_cabang_bisnis_cursor(cursor):
                raise ValueError(f"Home branch '{home}' tidak valid.")

            cursor.execute(
                """
                INSERT INTO manajemen_user (
                    id_user, username, password, role, nama_lengkap,
                    kode_cabang, status_user
                ) VALUES (?, ?, ?, ?, ?, ?, 'AKTIF')
                """,
                (id_user, username, password, role, nama, home),
            )
            _set_akses_user_cursor(cursor, id_user, role, home, akses)
        return True, f"User {username} berhasil dibuat."
    except PermissionError as exc:
        return False, str(exc)
    except Exception as exc:
        logger.exception("[User] Gagal membuat user")
        return False, str(exc)


def _ubah_user_local(data_user):
    """Mengubah profil/role/home branch tanpa mengubah username/password."""
    try:
        _pastikan_super_admin()
        data = dict(data_user or {})
        id_user = _text(data.get("id_user"))
        nama = _text(data.get("nama_lengkap"))
        role_baru = _normalisasi_role_user(data.get("role"))
        home_baru = _upper(data.get("kode_cabang"))
        akses = list(data.get("akses_cabang") or [])
        if not id_user:
            raise ValueError("ID user tidak valid.")
        if not nama:
            raise ValueError("Nama lengkap wajib diisi.")

        with _db_transaction(immediate=True) as (_, cursor):
            existing = cursor.execute(
                """
                SELECT username, role, kode_cabang, COALESCE(status_user, 'AKTIF')
                FROM manajemen_user
                WHERE id_user = ?
                LIMIT 1
                """,
                (id_user,),
            ).fetchone()
            if existing is None:
                raise ValueError("User tidak ditemukan.")
            if home_baru not in _ambil_cabang_bisnis_cursor(cursor):
                raise ValueError(f"Home branch '{home_baru}' tidak valid.")

            current_id = _text(CURRENT_SESSION.get("id_user"))
            if id_user == current_id and role_baru != "SUPER_ADMIN":
                raise ValueError(
                    "SUPER_ADMIN yang sedang login tidak dapat menurunkan role dirinya sendiri."
                )

            cursor.execute(
                """
                UPDATE manajemen_user
                SET nama_lengkap = ?, role = ?, kode_cabang = ?
                WHERE id_user = ?
                """,
                (nama, role_baru, home_baru, id_user),
            )
            _set_akses_user_cursor(cursor, id_user, role_baru, home_baru, akses)
        return True, f"User {_upper(existing[0])} berhasil diperbarui."
    except PermissionError as exc:
        return False, str(exc)
    except Exception as exc:
        logger.exception("[User] Gagal mengubah user")
        return False, str(exc)


def _supabase_access_token() -> str:
    """Ambil access token session Supabase saat ini dari client session."""
    try:
        session_result = supabase.auth.get_session()
    except Exception:
        return ""
    session_obj = getattr(session_result, "session", None) or session_result
    return str(getattr(session_obj, "access_token", "") or "").strip()


def _resolve_supabase_target_user_id(local_id_user: str) -> tuple[str, str]:
    """Resolve ID user lokal ke UUID Auth Supabase + username.

    Local SQLite dapat memakai id seperti ``USR-...`` untuk akun yang dibuat
    dari menu aplikasi, sementara Supabase Auth memakai UUID. Untuk akun online,
    cari username lokal lalu cocokkan ke public.user_profiles.id.
    """
    local_id = _text(local_id_user)
    if not local_id:
        return "", ""

    # UUID Supabase dapat dipakai langsung.
    try:
        uuid.UUID(local_id)
        row = _fetchone(
            "SELECT username FROM manajemen_user WHERE id_user = ? LIMIT 1",
            (local_id,),
        )
        return local_id, _upper(row[0]) if row else ""
    except (ValueError, AttributeError, TypeError):
        pass

    local_row = _fetchone(
        "SELECT username FROM manajemen_user WHERE id_user = ? LIMIT 1",
        (local_id,),
    )
    username = _upper(local_row[0]) if local_row else ""
    if not username:
        return "", ""

    try:
        response = (
            supabase
            .table("user_profiles")
            .select("id, username")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        profile = (response.data or [None])[0]
        if isinstance(profile, dict):
            return _text(profile.get("id")), _upper(profile.get("username") or username)
    except Exception as exc:
        logger.warning("[User] Gagal resolve user Supabase %s: %s", username, exc)
    return "", username


def _reset_password_supabase(id_user: str, password_baru: str) -> tuple[bool, str]:
    """Reset password user online melalui Edge Function.

    Service-role key tetap hanya berada di Edge Function; desktop app hanya
    mengirim access token user yang sedang login (SUPER) dan target Auth UUID.
    """
    token = _supabase_access_token()
    if not token:
        return False, "Session Supabase tidak aktif. Silakan login ulang."

    target_user_id, username = _resolve_supabase_target_user_id(id_user)
    if not target_user_id:
        return False, (
            f"User {username or id_user} belum memiliki ID Auth Supabase yang valid. "
            "Pastikan user tersebut sudah dibuat di Supabase Authentication dan "
            "sudah terpetakan di public.user_profiles."
        )

    endpoint = f"{str(SUPABASE_URL or '').rstrip('/')}/functions/v1/admin-reset-password"
    if not endpoint.startswith("http"):
        return False, "SUPABASE_URL belum dikonfigurasi."

    body = json.dumps({
        "target_user_id": target_user_id,
        "new_password": str(password_baru),
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": str(SUPABASE_PUBLISHABLE_KEY or ""),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
            message = str(data.get("error") or data.get("message") or raw).strip()
        except Exception:
            message = raw.strip() or f"HTTP {exc.code}"
        return False, message
    except urllib.error.URLError as exc:
        return False, f"Tidak dapat menghubungi Supabase: {exc.reason}"
    except Exception as exc:
        return False, f"Reset password gagal: {exc}"

    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    if isinstance(data, dict) and data.get("error"):
        return False, str(data["error"])
    return True, str(data.get("message") or "Password user berhasil diubah di Supabase.")


def reset_password_user(id_user, password_baru):
    """Reset password user: offline developer ke SQLite, online ke Supabase Auth."""
    try:
        _pastikan_super_admin()
        user_id = _text(id_user)
        password = str(password_baru or "")
        if not user_id:
            raise ValueError("ID user tidak valid.")
        if not password:
            raise ValueError("Password baru wajib diisi.")

        # Akun developer tetap memakai database sandbox offline.
        if bool(CURRENT_SESSION.get("is_developer")):
            with _db_transaction(immediate=True) as (_, cursor):
                row = cursor.execute(
                    "SELECT username FROM manajemen_user WHERE id_user = ? LIMIT 1",
                    (user_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("User tidak ditemukan.")
                cursor.execute(
                    "UPDATE manajemen_user SET password = ? WHERE id_user = ?",
                    (password, user_id),
                )
            return True, f"Password user {_upper(row[0])} berhasil direset di database offline."

        # Online: sumber password adalah Supabase Auth.
        return _reset_password_supabase(user_id, password)
    except PermissionError as exc:
        return False, str(exc)
    except Exception as exc:
        logger.exception("[User] Gagal reset password")
        return False, str(exc)


def set_status_user(id_user, aktif):
    """Aktif/nonaktif user; online melalui Supabase, developer melalui SQLite."""
    try:
        _pastikan_super_admin()
        user_id = _text(id_user)
        status_baru = "AKTIF" if bool(aktif) else "NONAKTIF"
        if not user_id:
            return False, "ID user tidak valid."
        if user_id == _text(CURRENT_SESSION.get("id_user")) and status_baru != "AKTIF":
            return False, "Akun SUPER_ADMIN yang sedang login tidak dapat dinonaktifkan."

        if _online_user_management_active():
            result = _invoke_user_management(
                "status",
                {"id_user": user_id, "status_user": status_baru},
            )
            _cache_remote_user_data(result)
            return True, str(result.get("message") or f"User sekarang {status_baru}.")
        return _set_status_user_local(user_id, aktif)
    except PermissionError as exc:
        return False, str(exc)
    except Exception as exc:
        logger.exception("[User] Gagal mengubah status user")
        return False, str(exc)


def _set_status_user_local(id_user, aktif):
    """Aktif/nonaktifkan akun tanpa menghapus row user dan histori terkait."""
    try:
        _pastikan_super_admin()
        user_id = _text(id_user)
        status_baru = "AKTIF" if bool(aktif) else "NONAKTIF"
        if not user_id:
            raise ValueError("ID user tidak valid.")
        if user_id == _text(CURRENT_SESSION.get("id_user")) and status_baru != "AKTIF":
            raise ValueError("Akun SUPER_ADMIN yang sedang login tidak dapat dinonaktifkan.")

        with _db_transaction(immediate=True) as (_, cursor):
            row = cursor.execute(
                """
                SELECT username, role, COALESCE(status_user, 'AKTIF')
                FROM manajemen_user
                WHERE id_user = ?
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                raise ValueError("User tidak ditemukan.")

            role = _upper(row[1])
            if status_baru == "NONAKTIF" and role == "SUPER_ADMIN":
                count_other = cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM manajemen_user
                    WHERE id_user <> ?
                      AND UPPER(role) = 'SUPER_ADMIN'
                      AND UPPER(COALESCE(status_user, 'AKTIF')) = 'AKTIF'
                    """,
                    (user_id,),
                ).fetchone()[0]
                if int(count_other or 0) <= 0 and not bool(CURRENT_SESSION.get("is_developer")):
                    raise ValueError("Minimal satu SUPER_ADMIN database harus tetap aktif.")

            cursor.execute(
                "UPDATE manajemen_user SET status_user = ? WHERE id_user = ?",
                (status_baru, user_id),
            )
        return True, f"User {_upper(row[0])} sekarang {status_baru}."
    except PermissionError as exc:
        return False, str(exc)
    except Exception as exc:
        logger.exception("[User] Gagal mengubah status user")
        return False, str(exc)


def _normalisasi_data_cabang(branch):
    kode = str(branch.get("kode_cabang", "")).strip().upper()
    nama = str(branch.get("nama_cabang", "")).strip().upper()
    prefix = str(branch.get("resi_prefix", "")).strip().upper()
    start_seq = str(branch.get("start_seq_json", '{"DEFAULT": 0}')).strip()
    aturan = str(branch.get("aturan_prefix", '{"DEFAULT": "INV"}')).strip()
    if not kode or not nama or not prefix:
        raise ValueError("Kode, nama, dan prefix cabang wajib diisi.")
    json.loads(start_seq)
    aturan_dict = json.loads(aturan)
    return kode, nama, prefix, start_seq, aturan, aturan_dict

def _upsert_data_cabang(cursor, data_cabang):
    kode, nama, prefix, start_seq, aturan, _aturan_dict = data_cabang
    cursor.execute(
        """
        INSERT INTO data_cabang (
            kode_cabang, nama_cabang, resi_prefix, start_seq_json, aturan_prefix
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(kode_cabang) DO UPDATE SET
            nama_cabang = excluded.nama_cabang,
            resi_prefix = excluded.resi_prefix,
            start_seq_json = excluded.start_seq_json,
            aturan_prefix = excluded.aturan_prefix
        """,
        (kode, nama, prefix, start_seq, aturan),
    )

def simpan_semua_pengaturan_dan_cabang(settings_to_save, branches_to_save):
    """Menyimpan pengaturan dan cabang secara atomic tanpa REPLACE parent row."""

    try:
        with _db_transaction(immediate=True) as (_, cursor):
            for kunci, nilai in settings_to_save:
                cursor.execute(
                    """
                    INSERT INTO pengaturan_sistem (kunci, nilai) VALUES (?, ?)
                    ON CONFLICT(kunci) DO UPDATE SET nilai = excluded.nilai
                    """,
                    (str(kunci), str(nilai)),
                )

            seen_codes = set()
            cabang_aktif = _upper(CURRENT_SESSION.get("kode_cabang", ""))
            for branch in branches_to_save:
                data_cabang = _normalisasi_data_cabang(branch)
                kode, nama, prefix, _start_seq, _aturan, aturan_dict = data_cabang
                if kode in seen_codes:
                    raise ValueError(
                        f"Kode cabang {kode} digunakan lebih dari sekali."
                    )
                seen_codes.add(kode)
                _upsert_data_cabang(cursor, data_cabang)
                if kode == cabang_aktif:
                    CURRENT_SESSION.update({
                        "nama_cabang": nama,
                        "resi_prefix": prefix,
                        "aturan_prefix": aturan_dict,
                    })
        return True, "Sukses"
    except Exception as exc:
        logger.exception("[Setting] Gagal menyimpan pengaturan/cabang")
        return False, str(exc)
# ==============================================================================
# PERFORMANCE MONITORING & CACHE HELPERS
# Internal optimization helpers. Public behavior preserved.
# ==============================================================================

_PERFORMANCE_REPORT = False

_PERFORMANCE_CACHE = {
    "invoice_status": {},
    "autocomplete": {},
}


def set_performance_report(enabled=True):
    """Enable/disable lightweight performance logging."""
    global _PERFORMANCE_REPORT
    _PERFORMANCE_REPORT = bool(enabled)


@contextmanager
def performance_timer(label, threshold=0.5):
    """Monitoring ringan proses lambat."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if _PERFORMANCE_REPORT and elapsed >= threshold:
            logger.info("[PERF] %s : %.4fs", label, elapsed)


def clear_performance_cache():
    """Membersihkan seluruh cache runtime tanpa mengubah data database."""
    for cache in _PERFORMANCE_CACHE.values():
        cache.clear()
    clear_autocomplete_cache()


def clear_invoice_cache():
    """Membersihkan cache status invoice."""
    _PERFORMANCE_CACHE["invoice_status"].clear()


def get_performance_cache():
    """Expose cache read-only untuk modul internal."""
    return _PERFORMANCE_CACHE


def get_cached_invoice_status(key):
    """Internal getter status invoice."""
    return _PERFORMANCE_CACHE["invoice_status"].get(str(key))


def set_cached_invoice_status(key, value):
    """Internal setter status invoice."""
    _PERFORMANCE_CACHE["invoice_status"][str(key)] = value


def get_cached_autocomplete(key):
    """Internal getter autocomplete."""
    return _PERFORMANCE_CACHE["autocomplete"].get(str(key))


def set_cached_autocomplete(key, value):
    """Internal setter autocomplete."""
    _PERFORMANCE_CACHE["autocomplete"][str(key)] = value