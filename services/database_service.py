# services/database_service.py
import sqlite3
import json
import logging
import re
import uuid
from config import CURRENT_SESSION, DATA_CLIENT

logger = logging.getLogger(__name__)

# 🌟 SAKLAR UTAMA: Set ke True jika nanti sudah siap online ke Supabase
USE_CLOUD = False

# ==============================================================================
# 🧯 ERROR TERSTRUKTUR
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
KODE_DB_ERROR = "DB_ERROR"

# ==============================================================================
# ⚙️ KONEKSI INTI & UTILITY SISTEM (GLOBAL)
# ==============================================================================


def get_db_connection(db_name=None):
    """Membuka koneksi SQLite aktif dengan foreign key dan timeout."""
    target_db = db_name or CURRENT_SESSION.get("db_name", "database_cargo.db")
    conn = sqlite3.connect(str(target_db), timeout=20.0)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _kode_cabang_aktif(kode_cabang=None):
    """Menghasilkan kode cabang baku untuk seluruh operasi master Truk."""
    return str(
        kode_cabang
        or CURRENT_SESSION.get("kode_cabang", "PUSAT")
        or "PUSAT"
    ).strip().upper()


def get_setting(key):
    """
    Mengambil satu pengaturan dari database.
    Jika belum tersedia, gunakan DATA_CLIENT dari config.py.
    """
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT nilai FROM pengaturan_sistem WHERE kunci = ?",
                (str(key),),
            ).fetchone()
            if row is not None:
                return row[0]
    except sqlite3.Error as exc:
        logger.warning("[Setting] Gagal membaca %s: %s", key, exc)

    return DATA_CLIENT.get(key, "")

# ==============================================================================
# 📋 TAB RESI (FORM INPUT SURAT JALAN & HISTORI HARIAN)
# ==============================================================================


def cari_histori_resi(keyword, kode_cabang):
    """Pencarian live histori resi pada cabang aktif."""
    if USE_CLOUD:
        return []

    keyword = str(keyword or "").strip().lower()
    kode_cabang = str(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()

    try:
        with get_db_connection() as conn:
            pattern = f"%{keyword}%"
            return conn.execute(
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
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error("[Resi] Gagal mencari histori: %s", exc)
        return []


def ambil_histori_resi_by_tanggal(tgl_pilih, kode_cabang):
    """Memuat daftar resi di sidebar kanan berdasarkan kalender yang dipilih"""
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT no_resi, penerima FROM data_resi WHERE tanggal_masuk = ? AND kode_cabang = ? ORDER BY rowid ASC",
                (tgl_pilih, kode_cabang),
            )
            hasil = cursor.fetchall()
            return hasil
        finally:
            if conn:
                conn.close()


def ambil_detail_resi(no_resi):
    """Mengambil data lengkap satu resi untuk keperluan Cetak / Preview Nota"""
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
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
                                  ongkir_per_cbm
                           FROM data_resi
                           WHERE no_resi = ?
                           """, (no_resi,))
            row = cursor.fetchone()
            return row
        finally:
            if conn:
                conn.close()


def ambil_data_autocomplete(kode_cabang):
    """Menyediakan daftar nama Pengirim dan Penerima untuk QCompleter di form input Resi"""
    if USE_CLOUD:
        return [], []

    pengirim, penerima = [], []
    conn = None

    kode_cabang = str(kode_cabang or CURRENT_SESSION.get(
        'kode_cabang',
        'PUSAT',
    )).strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

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
            print(f"[Autocomplete Service] Gagal memuat penerima: {e}")

    except Exception as e:
        print(f"[Autocomplete Service] Critical Error: {e}")

    finally:
        if conn:
            conn.close()

    return pengirim, penerima


def ambil_detail_pengirim(name_clean, kode_cabang):
    """Autofill detail profil pengirim saat nama dipilih di form resi"""
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT no_hp, alamat, kota
                FROM master_pengirim
                WHERE TRIM(UPPER(nama)) = TRIM(UPPER(?))
                  AND kode_cabang = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """, (name_clean, kode_cabang))
            row = cursor.fetchone()
            return row
        finally:
            if conn:
                conn.close()


def ambil_detail_penerima(nama_penerima, kode_cabang):
    """Autofill detail profil penerima saat nama dipilih di form resi"""
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT no_hp, alamat, kota, provinsi
                FROM master_penerima
                WHERE TRIM(UPPER(nama)) = TRIM(UPPER(?))
                  AND kode_cabang = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """, (nama_penerima, kode_cabang))
            row = cursor.fetchone()
            return row
        finally:
            if conn:
                conn.close()


def ambil_sekuens_resi(kode_cabang, pref):
    """Menghitung nomor urut/counter resi otomatis berdasarkan cabang dan tipe transaksi"""
    if USE_CLOUD:
        pass
    else:
        base_number = 0
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
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
        finally:
            if conn:
                conn.close()


def simpan_transaksi_resi(data):
    """Menyimpan resi, buku gudang, serta master pengirim/penerima dalam satu transaksi."""
    if USE_CLOUD:
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR,
            "Penyimpanan cloud belum diaktifkan.",
        )

    no_resi = str(data.get("no_resi", "")).strip().upper()
    kode_cabang = str(
        data.get("kode_cabang")
        or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()

    if not no_resi:
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR,
            "Nomor resi tidak boleh kosong.",
        )
    if not kode_cabang:
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR,
            "Kode cabang tidak boleh kosong.",
        )

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        # no_resi adalah primary key global pada schema.
        if cursor.execute(
            "SELECT 1 FROM data_resi WHERE no_resi = ? LIMIT 1",
            (no_resi,),
        ).fetchone():
            conn.rollback()
            return False, KesalahanTransaksiResi(
                KODE_RESI_DUPLIKAT,
                "Nomor resi sudah ada di database.",
            )

        cursor.execute(
            """
            INSERT INTO data_resi (
                no_resi, kode_cabang, tanggal_masuk,
                pengirim, hp_pengirim, alamat_pengirim, kota_asal,
                penerima, hp_penerima, alamat_penerima, kota_tujuan,
                nama_barang, berat, koli, cbm,
                ongkir_per_kg, ongkir_per_cbm, total_ongkir,
                pembayaran, status_resi, foto_bukti, rincian_json,
                updated_at
            )
            VALUES (
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, 'DI GUDANG', 'BELUM', ?,
                CURRENT_TIMESTAMP
            )
            """,
            (
                no_resi,
                kode_cabang,
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
                data.get("total_ongkir", 0),
                str(data.get("pembayaran", "")).strip().upper(),
                data.get("rincian_json", "[]"),
            ),
        )

        id_gudang = f"GDG-{no_resi}"
        cursor.execute(
            """
            INSERT INTO buku_gudang (
                id_gudang, kode_cabang, tanggal,
                no_resi, jenis, status_resi, updated_at
            )
            VALUES (?, ?, ?, ?, 'BARANG MASUK', 'DI GUDANG', CURRENT_TIMESTAMP)
            ON CONFLICT(id_gudang) DO UPDATE SET
                kode_cabang = excluded.kode_cabang,
                tanggal = excluded.tanggal,
                no_resi = excluded.no_resi,
                jenis = excluded.jenis,
                status_resi = excluded.status_resi,
                updated_at = CURRENT_TIMESTAMP
            """,
            (id_gudang, kode_cabang, data.get("tanggal_masuk"), no_resi),
        )

        nama_pengirim = str(data.get("pengirim", "")).strip().upper()
        if nama_pengirim:
            pengirim_lama = cursor.execute(
                """
                SELECT id_pengirim
                FROM master_pengirim
                WHERE kode_cabang = ?
                  AND TRIM(UPPER(nama)) = TRIM(UPPER(?))
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (kode_cabang, nama_pengirim),
            ).fetchone()

            values_pengirim = (
                nama_pengirim,
                str(data.get("hp_pengirim", "")).strip() or None,
                str(data.get("alamat_pengirim", "")).strip().upper(),
                str(data.get("kota_asal", "")).strip().upper(),
            )

            if pengirim_lama:
                cursor.execute(
                    """
                    UPDATE master_pengirim
                    SET nama = ?, no_hp = ?, alamat = ?, kota = ?,
                        is_synced = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE id_pengirim = ? AND kode_cabang = ?
                    """,
                    values_pengirim + (pengirim_lama[0], kode_cabang),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO master_pengirim (
                        id_pengirim, kode_cabang, nama,
                        no_hp, alamat, kota, is_synced
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        f"SHP-{uuid.uuid4().hex[:12].upper()}",
                        kode_cabang,
                    ) + values_pengirim,
                )

        nama_penerima = str(data.get("penerima", "")).strip().upper()
        if nama_penerima:
            kota_tujuan = str(data.get("kota_tujuan", "")).strip().upper()
            if " - " in kota_tujuan:
                provinsi_dari_kota, kota_bersih = [
                    bagian.strip()
                    for bagian in kota_tujuan.split(" - ", 1)
                ]
            else:
                provinsi_dari_kota = ""
                kota_bersih = kota_tujuan

            provinsi = (
                str(data.get("provinsi_tujuan", "")).strip().upper()
                or provinsi_dari_kota
                or None
            )
            hp_penerima = str(data.get("hp_penerima", "")).strip() or None
            alamat_penerima = (
                str(data.get("alamat_penerima", "")).strip().upper()
            )
            pembayaran = (
                str(data.get("pembayaran", "TF / INVOICE")).strip().upper()
                or "TF / INVOICE"
            )

            penerima_lama = cursor.execute(
                """
                SELECT id_penerima
                FROM master_penerima
                WHERE kode_cabang = ?
                  AND TRIM(UPPER(nama)) = TRIM(UPPER(?))
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (kode_cabang, nama_penerima),
            ).fetchone()

            total_transaksi = cursor.execute(
                """
                SELECT COUNT(*)
                FROM data_resi
                WHERE kode_cabang = ?
                  AND TRIM(UPPER(penerima)) = TRIM(UPPER(?))
                """,
                (kode_cabang, nama_penerima),
            ).fetchone()[0]

            if penerima_lama:
                cursor.execute(
                    """
                    UPDATE master_penerima
                    SET nama = ?, no_hp = ?, alamat = ?, kota = ?,
                        provinsi = ?, pembayaran = ?,
                        total_transaksi = ?, is_synced = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id_penerima = ? AND kode_cabang = ?
                    """,
                    (
                        nama_penerima, hp_penerima, alamat_penerima,
                        kota_bersih, provinsi, pembayaran,
                        total_transaksi, penerima_lama[0], kode_cabang,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO master_penerima (
                        id_penerima, kode_cabang, nama, no_hp,
                        alamat, kota, provinsi, total_transaksi,
                        pembayaran, is_synced
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        f"CNE-{uuid.uuid4().hex[:12].upper()}",
                        kode_cabang, nama_penerima, hp_penerima,
                        alamat_penerima, kota_bersih, provinsi,
                        total_transaksi, pembayaran,
                    ),
                )

        conn.commit()
        return True, ""

    except sqlite3.IntegrityError as exc:
        if conn:
            conn.rollback()
        message = str(exc)
        if "data_resi.no_resi" in message:
            return False, KesalahanTransaksiResi(
                KODE_RESI_DUPLIKAT,
                "Nomor resi sudah ada di database.",
            )
        logger.exception("IntegrityError saat menyimpan transaksi resi")
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR,
            f"Gagal menyimpan karena aturan database: {message}",
        )
    except Exception as exc:
        if conn:
            conn.rollback()
        logger.exception("Gagal menyimpan transaksi resi")
        return False, KesalahanTransaksiResi(
            KODE_DB_ERROR,
            f"Gagal menyimpan resi: {exc}",
        )
    finally:
        if conn:
            conn.close()

# ==============================================================================
# 🏭 TAB BUKU GUDANG (MONITORING DATA RESI MASUK & KELUAR)
# ==============================================================================


def ambil_data_buku_gudang(kode_cabang, wilayah, tahun_terpilih, filters=None):
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            mapping = {
                2: "tanggal_masuk", 3: "tanggal_keluar", 4: "status_resi", 5: "truk",
                6: "pengirim", 7: "kota_asal", 8: "penerima",
                9: "kota_tujuan", 10: "nama_barang", 14: "total_ongkir",
                15: "pembayaran", 16: "ket_buku_gudang"
            }

            query = """
                    SELECT no_resi, \
                           tanggal_masuk, \
                           tanggal_keluar, \
                           status_resi, \
                           truk, \
                           pengirim, \
                           kota_asal, \
                           penerima, \
                           kota_tujuan, \
                           nama_barang, \
                           koli, \
                           berat, \
                           cbm, \
                           total_ongkir, \
                           pembayaran, \
                           ket_buku_gudang
                    FROM data_resi
                    WHERE kode_cabang = ? \
                      AND kota_tujuan LIKE ? \
                      AND tanggal_masuk LIKE ? \
                    """
            params = [kode_cabang, f"%{wilayah}%", f"{tahun_terpilih}%"]

            if filters:
                for col_idx, val in filters.items():
                    if col_idx in mapping:
                        if col_idx == 14:
                            val = val.replace(".", "")
                        query += f" AND {mapping[col_idx]} LIKE ?"
                        params.append(f"%{val}%")

            query += " ORDER BY tanggal_masuk ASC, rowid ASC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return rows
        finally:
            if conn:
                conn.close()


def update_baris_buku_gudang(no_resi, kode_cabang, updates_dict, barang_payload=None):
    """Memperbarui data resi dari tab buku gudang dengan kolom yang diizinkan."""
    if USE_CLOUD:
        return False

    allowed_columns = {
        "tanggal_masuk", "tanggal_keluar", "status_resi", "truk",
        "pengirim", "kota_asal", "penerima", "kota_tujuan",
        "nama_barang", "koli", "berat", "cbm", "total_ongkir",
        "pembayaran", "ket_buku_gudang", "no_manifest", "ket_manifest",
    }

    safe_updates = {
        key: value
        for key, value in (updates_dict or {}).items()
        if key in allowed_columns
    }

    if barang_payload:
        for key in ("nama_barang", "koli", "berat", "cbm"):
            if key in barang_payload:
                safe_updates[key] = barang_payload[key]

    if not safe_updates:
        return True

    conn = None
    try:
        conn = get_db_connection()
        fields = [f"{column} = ?" for column in safe_updates]
        values = list(safe_updates.values())
        values.extend([no_resi, kode_cabang])

        cursor = conn.execute(
            f"""
            UPDATE data_resi
            SET {", ".join(fields)},
                updated_at = CURRENT_TIMESTAMP
            WHERE no_resi = ? AND kode_cabang = ?
            """,
            values,
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as exc:
        if conn:
            conn.rollback()
        logger.error("[Buku Gudang] Gagal memperbarui resi: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def tandai_resi_selesai_massal(resi_terpilih, kode_cabang):
    if USE_CLOUD:
        return False

    daftar_resi = [
        str(no_resi).strip()
        for no_resi in (resi_terpilih or [])
        if str(no_resi).strip()
    ]
    if not daftar_resi:
        return True

    conn = None
    try:
        conn = get_db_connection()
        conn.executemany(
            """
            UPDATE data_resi
            SET status_resi = 'SELESAI',
                updated_at = CURRENT_TIMESTAMP
            WHERE no_resi = ? AND kode_cabang = ?
            """,
            [(no_resi, kode_cabang) for no_resi in daftar_resi],
        )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        if conn:
            conn.rollback()
        logger.error("[Buku Gudang] Gagal menyelesaikan resi massal: %s", exc)
        return False
    finally:
        if conn:
            conn.close()

# ==============================================================================
# 🚚 TAB MANIFEST (PROSES PEMBERANGKATAN & TRACKING TRUK)
# ==============================================================================


def ambil_truk_list(kode_cabang=None):
    """Daftar nomor polisi dan sopir milik cabang aktif."""
    if USE_CLOUD:
        return []

    cabang = _kode_cabang_aktif(kode_cabang)
    conn = None
    try:
        conn = get_db_connection()
        return conn.execute(
            """
            SELECT no_polisi, nama_sopir
            FROM truk
            WHERE kode_cabang = ?
            ORDER BY no_polisi ASC
            """,
            (cabang,),
        ).fetchall()
    finally:
        if conn:
            conn.close()


def ambil_detail_truk_by_nopol(nopol, kode_cabang=None):
    """Detail truk berdasarkan nomor polisi pada cabang aktif."""
    if USE_CLOUD:
        return None

    cabang = _kode_cabang_aktif(kode_cabang)
    conn = None
    try:
        conn = get_db_connection()
        return conn.execute(
            """
            SELECT nama_sopir, jenis_truk
            FROM truk
            WHERE kode_cabang = ? AND no_polisi = ?
            LIMIT 1
            """,
            (cabang, str(nopol or "").strip().upper()),
        ).fetchone()
    finally:
        if conn:
            conn.close()


def ambil_detail_truk_by_sopir(sopir, kode_cabang=None):
    """Detail truk berdasarkan nama sopir pada cabang aktif."""
    if USE_CLOUD:
        return None

    cabang = _kode_cabang_aktif(kode_cabang)
    conn = None
    try:
        conn = get_db_connection()
        return conn.execute(
            """
            SELECT no_polisi, jenis_truk, ket_truk
            FROM truk
            WHERE kode_cabang = ? AND nama_sopir = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (cabang, str(sopir or "").strip().upper()),
        ).fetchone()
    finally:
        if conn:
            conn.close()


def ambil_no_manifest_list_by_prefix(prefix, kode_cabang):
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT no_manifest FROM data_resi WHERE no_manifest LIKE ? AND kode_cabang = ?",
                (f"{prefix}-%", kode_cabang),
            )
            rows = cursor.fetchall()
            return rows
        finally:
            if conn:
                conn.close()


def ambil_daftar_tahun_manifest(kode_cabang):
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT substr(tanggal_keluar, 1, 4) FROM data_resi WHERE no_manifest IS NOT NULL AND tanggal_keluar IS NOT NULL AND kode_cabang = ?",
                (kode_cabang,),
            )
            rows = cursor.fetchall()
            return rows
        finally:
            if conn:
                conn.close()


def ambil_resi_untuk_manifest(kode_cabang, wilayah, is_edit_mode, edit_manifest_id):
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            if is_edit_mode:
                cursor.execute(
                    """SELECT no_resi, tanggal_masuk, pengirim, penerima, kota_tujuan,
                              nama_barang, koli, berat, cbm, no_manifest,
                              total_ongkir, ket_manifest
                       FROM data_resi
                       WHERE kode_cabang = ?
                         AND (no_manifest = ? OR (kota_tujuan LIKE ? AND (no_manifest IS NULL OR TRIM(no_manifest) = '')))
                       ORDER BY CASE WHEN no_manifest = ? THEN 0 ELSE 1 END, tanggal_masuk ASC""",
                    (kode_cabang, edit_manifest_id, f"%{wilayah}%", edit_manifest_id)
                )
            else:
                cursor.execute(
                    """SELECT no_resi, tanggal_masuk, pengirim, penerima, kota_tujuan,
                              nama_barang, koli, berat, cbm, NULL as no_manifest,
                              total_ongkir, NULL as ket_manifest
                       FROM data_resi
                       WHERE kode_cabang = ?
                         AND kota_tujuan LIKE ?
                         AND (no_manifest IS NULL OR TRIM(no_manifest) = '')
                       ORDER BY tanggal_masuk ASC""",
                    (kode_cabang, f"%{wilayah}%")
                )
            rows = cursor.fetchall()
            return rows
        finally:
            if conn:
                conn.close()


def ambil_histori_manifest(kode_cabang, tahun_terpilih):
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
                    SELECT DISTINCT r1.tanggal_keluar, \
                                    r1.no_manifest, \
                                    r1.truk,
                                    COALESCE(m.nama_kapal, ''),
                                    (SELECT COUNT(*) \
                                     FROM data_resi r2 \
                                     WHERE r2.no_manifest = r1.no_manifest \
                                       AND r2.kode_cabang = r1.kode_cabang),
                                    COALESCE(m.note_manifest, '')
                    FROM data_resi r1 \
                    LEFT JOIN manifest m \
                      ON m.id_manifest = r1.no_manifest \
                     AND m.kode_cabang = r1.kode_cabang \
                    WHERE r1.no_manifest IS NOT NULL \
                      AND r1.kode_cabang = ? \
                    """
            params = [kode_cabang]
            if tahun_terpilih and tahun_terpilih != "Semua":
                query += " AND r1.tanggal_keluar LIKE ?"
                params.append(f"{tahun_terpilih}-%")
            query += " ORDER BY r1.tanggal_keluar ASC, r1.no_manifest ASC"

            rows = cursor.execute(query, params).fetchall()
            return rows
        finally:
            if conn:
                conn.close()


def simpan_atau_update_manifest_data(
    manifest_id,
    kode_cabang,
    truk_payload,
    resi_list,
    is_edit_mode,
    tgl_k,
):

    if USE_CLOUD:
        return False, "Penyimpanan cloud belum diaktifkan."

    manifest_id = str(manifest_id or "").strip().upper()
    kode_cabang = str(kode_cabang or "").strip().upper()
    if not manifest_id:
        return False, "Nomor manifest tidak boleh kosong."
    if not kode_cabang:
        return False, "Kode cabang tidak boleh kosong."
    if not resi_list:
        return False, "Pilih minimal satu resi."

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        nopol = str(truk_payload.get("no_polisi", "")).strip().upper()
        sopir = str(truk_payload.get("nama_sopir", "")).strip().upper()
        jenis = str(truk_payload.get("jenis_truk", "")).strip()
        ket_truk = str(
            truk_payload.get("ket_truk", "")
        ).strip().upper()
        nama_truk = str(
            truk_payload.get("nama_truk", "")
        ).strip()
        nama_kapal = str(
            truk_payload.get("nama_kapal", "")
        ).strip().upper()
        note_manifest = str(
            truk_payload.get("note_manifest", "")
        ).strip().upper()

        # Untuk manifest tanpa armada, Note menjadi representasi tampilan pada
        # data_resi.truk agar tetap kompatibel dengan histori dan laporan lama.
        if not nama_truk and note_manifest:
            nama_truk = note_manifest

        if not nama_truk:
            return False, "Detail truk atau Note manifest tidak boleh kosong."

        if nopol:
            cursor.execute(
                """
                INSERT INTO truk (
                    kode_cabang, no_polisi, jenis_truk, nama_sopir,
                    ket_truk, is_synced, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                ON CONFLICT(kode_cabang, no_polisi) DO UPDATE SET
                    jenis_truk = CASE
                        WHEN TRIM(excluded.jenis_truk) <> ''
                        THEN excluded.jenis_truk ELSE truk.jenis_truk
                    END,
                    nama_sopir = CASE
                        WHEN TRIM(excluded.nama_sopir) <> ''
                        THEN excluded.nama_sopir ELSE truk.nama_sopir
                    END,
                    ket_truk = CASE
                        WHEN TRIM(excluded.ket_truk) <> ''
                        THEN excluded.ket_truk ELSE truk.ket_truk
                    END,
                    is_synced = 0,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    kode_cabang,
                    nopol,
                    jenis or "BELUM DIKETAHUI",
                    sopir,
                    ket_truk,
                ),
            )

        if is_edit_mode:
            cursor.execute(
                """
                UPDATE data_resi
                SET truk = NULL,
                    status_resi = 'DI GUDANG',
                    tanggal_keluar = NULL,
                    no_manifest = NULL,
                    ket_manifest = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE no_manifest = ? AND kode_cabang = ?
                """,
                (manifest_id, kode_cabang),
            )

        cursor.execute(
            """
            INSERT INTO manifest (
                id_manifest, kode_cabang, tanggal,
                no_polisi, nama_sopir, nama_kapal, note_manifest,
                status_manifest, is_synced, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PERJALANAN', 0, CURRENT_TIMESTAMP)
            ON CONFLICT(id_manifest) DO UPDATE SET
                kode_cabang = excluded.kode_cabang,
                tanggal = excluded.tanggal,
                no_polisi = excluded.no_polisi,
                nama_sopir = excluded.nama_sopir,
                nama_kapal = excluded.nama_kapal,
                note_manifest = excluded.note_manifest,
                status_manifest = excluded.status_manifest,
                is_synced = 0,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                manifest_id,
                kode_cabang,
                tgl_k,
                nopol or None,
                sopir,
                nama_kapal or None,
                note_manifest or None,
            ),
        )

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
                SET truk = ?,
                    status_resi = 'PERJALANAN',
                    tanggal_keluar = ?,
                    no_manifest = ?,
                    ket_manifest = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE no_resi = ? AND kode_cabang = ?
                """,
                (
                    nama_truk, tgl_k, manifest_id,
                    ket_manifest, no_resi, kode_cabang,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    f"Resi {no_resi} tidak ditemukan pada cabang {kode_cabang}."
                )

        conn.commit()
        return True, ""
    except Exception as exc:
        if conn:
            conn.rollback()
        return False, str(exc)
    finally:
        if conn:
            conn.close()


def ambil_note_manifest(manifest_id, kode_cabang):
    """Mengambil Note umum yang tersimpan pada satu Manifest."""
    if USE_CLOUD:
        return ""

    manifest_id = str(manifest_id or "").strip().upper()
    kode_cabang = str(kode_cabang or "").strip().upper()
    if not manifest_id or not kode_cabang:
        return ""

    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(note_manifest, '')
                FROM manifest
                WHERE id_manifest = ?
                  AND kode_cabang = ?
                LIMIT 1
                """,
                (manifest_id, kode_cabang),
            ).fetchone()
            return str(row[0] or "").strip() if row else ""
    except sqlite3.Error as exc:
        logger.error(
            "[Manifest] Gagal mengambil Note manifest: %s",
            exc,
        )
        return ""


def ambil_nama_kapal_manifest(manifest_id, kode_cabang):
    """Mengambil hanya nama kapal yang tersimpan pada satu Manifest."""
    if USE_CLOUD:
        return ""

    manifest_id = str(manifest_id or "").strip().upper()
    kode_cabang = str(kode_cabang or "").strip().upper()
    if not manifest_id or not kode_cabang:
        return ""

    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(nama_kapal, '')
                FROM manifest
                WHERE id_manifest = ?
                  AND kode_cabang = ?
                LIMIT 1
                """,
                (manifest_id, kode_cabang),
            ).fetchone()
            return str(row[0] or "").strip() if row else ""
    except sqlite3.Error as exc:
        logger.error(
            "[Manifest] Gagal mengambil nama kapal: %s",
            exc,
        )
        return ""


def ambil_resi_detail_untuk_cetak(kode_cabang, resi_list):
    if USE_CLOUD:
        return []

    daftar_resi = [
        str(no_resi).strip()
        for no_resi in (resi_list or [])
        if str(no_resi).strip()
    ]
    if not daftar_resi:
        return []

    placeholders = ",".join("?" for _ in daftar_resi)
    params = [kode_cabang] + daftar_resi

    try:
        with get_db_connection() as conn:
            return conn.execute(
                f"""
                SELECT no_resi, pengirim, penerima, kota_tujuan,
                       nama_barang, koli, berat, cbm,
                       total_ongkir, ket_manifest
                FROM data_resi
                WHERE kode_cabang = ?
                  AND no_resi IN ({placeholders})
                """,
                params,
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error("[Manifest] Gagal mengambil detail cetak: %s", exc)
        return []


def ambil_resi_list_by_manifest(manifest_id, kode_cabang):
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            rows = cursor.execute("SELECT no_resi FROM data_resi WHERE no_manifest = ? AND kode_cabang = ?",
                                  (manifest_id, kode_cabang)).fetchall()
            return [r[0] for r in rows]
        finally:
            if conn:
                conn.close()

# ==============================================================================
# 🧾 TAB INVOICE (TAGIHAN & TEMPLATE JSON)
# ==============================================================================


def dapatkan_sequence_invoice_baru(prefix):
    """Menghasilkan sequence berikutnya dari angka terakhir nomor invoice."""
    if USE_CLOUD:
        return 1

    prefix = str(prefix or "").strip()
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT no_invoice
                FROM invoice_header
                WHERE no_invoice LIKE ?
                """,
                (f"{prefix}-%",),
            ).fetchall()

        max_sequence = 0
        for row in rows:
            nomor = str(row[0] or "")
            match = re.search(r"-(\d+)$", nomor)
            if match:
                max_sequence = max(max_sequence, int(match.group(1)))

        return max_sequence + 1
    except (sqlite3.Error, ValueError) as exc:
        logger.error("[Invoice] Gagal membuat sequence: %s", exc)
        return 1


def simpan_atau_update_invoice(header, items, is_update=False):
    """Menyimpan atau memperbarui invoice beserta detailnya secara atomic."""
    if USE_CLOUD:
        return False, "Penyimpanan cloud belum diaktifkan."

    no_invoice = str(header.get("no_invoice", "")).strip().upper()
    if not no_invoice:
        return False, "Nomor invoice tidak boleh kosong."
    if not items:
        return False, "Item invoice tidak boleh kosong."

    conn = None
    try:
        from datetime import datetime

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        if is_update:
            cursor.execute(
                """
                UPDATE invoice_header
                SET tanggal = ?, client = ?, tipe_invoice = ?,
                    jenis_pajak = ?, subtotal = ?, total_akhir = ?,
                    status = ?, metadata_json = ?,
                    template_version = ?, updated_at = ?
                WHERE no_invoice = ?
                """,
                (
                    header["tanggal"], header["client"],
                    header["tipe_invoice"], header["jenis_pajak"],
                    header["subtotal"], header["total_akhir"],
                    header["status"], header["metadata_json"],
                    header["template_version"], now, no_invoice,
                ),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return False, "Invoice yang akan diperbarui tidak ditemukan."

            cursor.execute(
                "DELETE FROM invoice_detail WHERE no_invoice = ?",
                (no_invoice,),
            )
        else:
            if cursor.execute(
                "SELECT 1 FROM invoice_header WHERE no_invoice = ?",
                (no_invoice,),
            ).fetchone():
                conn.rollback()
                return False, "Nomor invoice sudah digunakan."

            cursor.execute(
                """
                INSERT INTO invoice_header (
                    no_invoice, tanggal, client, tipe_invoice,
                    jenis_pajak, subtotal, total_akhir, status,
                    created_at, metadata_json, template_version, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    no_invoice, header["tanggal"], header["client"],
                    header["tipe_invoice"], header["jenis_pajak"],
                    header["subtotal"], header["total_akhir"],
                    header["status"], now, header["metadata_json"],
                    header["template_version"], now,
                ),
            )

        cursor.executemany(
            """
            INSERT INTO invoice_detail (
                no_invoice, nomor_urut, data_kolom, nominal_subtotal
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    no_invoice,
                    item["nomor_urut"],
                    item["data_kolom"],
                    item["nominal"],
                )
                for item in items
            ],
        )

        conn.commit()
        return True, "Sukses"
    except sqlite3.IntegrityError as exc:
        if conn:
            conn.rollback()
        if "invoice_header.no_invoice" in str(exc):
            return False, "Nomor invoice sudah digunakan."
        logger.exception("[Invoice] Integrity error")
        return False, str(exc)
    except Exception as exc:
        if conn:
            conn.rollback()
        logger.exception("[Invoice] Gagal simpan/update")
        return False, str(exc)
    finally:
        if conn:
            conn.close()


def ambil_histori_invoice(limit=300):
    """Mengambil daftar histori invoice untuk tabel sebelah kiri."""
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            return conn.execute(
                "SELECT no_invoice, tanggal, client, status FROM invoice_header ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        except Exception as e:
            logger.error(f"[Invoice] Gagal ambil histori: {e}")
            return []
        finally:
            if conn:
                conn.close()


def ambil_invoice_by_no(no_invoice):
    """Membaca data lengkap invoice (header & detail) untuk ditampilkan ke editor."""
    if USE_CLOUD:
        pass
    else:
        conn = None
        try:
            conn = get_db_connection()
            header = conn.execute(
                "SELECT client, tipe_invoice, jenis_pajak, status, tanggal, metadata_json FROM invoice_header WHERE no_invoice = ?",
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
            if conn:
                conn.close()

# --- 📁 SUB-TAB: MASTER PENGIRIM (SHIPPER) ---


def ambil_semua_master_pengirim(kode_cabang):
    """Menarik semua data pelanggan tetap pengirim di cabang saat ini"""
    conn = None
    try:
        kode_cabang = str(kode_cabang or CURRENT_SESSION.get(
            'kode_cabang',
            'PUSAT',
        )).strip()

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id_pengirim,
                kode_cabang,
                COALESCE(nama, '') AS nama,
                COALESCE(no_hp, '') AS no_hp,
                COALESCE(alamat, '') AS alamat,
                COALESCE(kota, '') AS kota
            FROM master_pengirim
            WHERE kode_cabang = ?
            ORDER BY TRIM(COALESCE(nama, '')) COLLATE NOCASE ASC
        """, (kode_cabang,))

        rows = cursor.fetchall()
        return rows

    except Exception as e:
        print(f"[Master Pengirim] Gagal mengambil data: {e}")
        return []

    finally:
        if conn:
            conn.close()


def ambil_histori_transaksi_by_pengirim(nama_pengirim, kode_cabang):
    """Melacak histori resi berdasarkan nama pengirim."""
    conn = None
    try:
        nama_pengirim = str(nama_pengirim or "").strip()
        kode_cabang = str(kode_cabang or CURRENT_SESSION.get(
            'kode_cabang',
            'PUSAT',
        )).strip()

        if not nama_pengirim:
            return []

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(tanggal_masuk, '') AS tanggal_masuk,
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
        """, (nama_pengirim, kode_cabang))

        return cursor.fetchall()

    except Exception as e:
        print(f"[Histori Pengirim] Gagal mengambil data: {e}")
        return []

    finally:
        if conn:
            conn.close()


def update_master_pengirim_dari_tabel(
    id_pengirim,
    kode_cabang,
    nama,
    no_hp,
    kota,
    alamat,
):
    conn = None
    try:
        nama = str(nama or "").strip().upper()
        no_hp = str(no_hp or "").strip()
        kota = str(kota or "").strip().upper()
        alamat = str(alamat or "").strip().upper()

        if not nama:
            return False, "Nama pengirim tidak boleh kosong."

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE master_pengirim
            SET nama = ?,
                no_hp = ?,
                kota = ?,
                alamat = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id_pengirim = ?
              AND kode_cabang = ?
        """, (nama, no_hp if no_hp else None, kota, alamat, id_pengirim, kode_cabang))

        conn.commit()
        return True, ""

    except Exception as e:
        if conn:
            conn.rollback()
        return False, str(e)

    finally:
        if conn:
            conn.close()

# --- 📁 SUB-TAB: MASTER PENERIMA (CONSIGNEE) ---


def ambil_semua_master_penerima(kode_cabang):
    """Menarik semua data pelanggan tetap penerima di cabang saat ini untuk ditampilkan di tabel"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Menembak ke tabel master_penerima sesuai struktur database_manager.py
        cursor.execute("""
            SELECT id_penerima, kode_cabang, nama, no_hp, alamat, kota 
            FROM master_penerima 
            WHERE kode_cabang = ?
            ORDER BY nama ASC
        """, (kode_cabang,))
        rows = cursor.fetchall()
        return rows
    finally:
        if conn:
            conn.close()


def ambil_histori_transaksi_by_penerima(nama_penerima, kode_cabang):
    """(Opsional) Melacak seluruh histori resi kargo yang pernah diterima oleh penerima ini"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tanggal_masuk, no_resi, pengirim, koli, berat, cbm, kota_asal, total_ongkir 
            FROM data_resi 
            WHERE penerima = ? AND kode_cabang = ?
            ORDER BY tanggal_masuk DESC, rowid DESC
        """, (nama_penerima, kode_cabang))
        rows = cursor.fetchall()
        return rows
    finally:
        if conn:
            conn.close()


def ambil_semua_master_penerima_full(kode_cabang):
    """Mengambil data lengkap master penerima untuk tabel UI."""
    kode_cabang = str(
        kode_cabang or CURRENT_SESSION.get("kode_cabang", "PUSAT")
    ).strip().upper()

    try:
        with get_db_connection() as conn:
            return conn.execute(
                """
                SELECT
                    id_penerima,
                    COALESCE(nama, ''),
                    COALESCE(no_hp, ''),
                    COALESCE(alamat, ''),
                    COALESCE(kota, ''),
                    COALESCE(provinsi, ''),
                    (
                        SELECT COUNT(*)
                        FROM data_resi
                        WHERE kode_cabang = master_penerima.kode_cabang
                          AND TRIM(UPPER(penerima))
                              = TRIM(UPPER(master_penerima.nama))
                    ) AS total_transaksi,
                    COALESCE(pembayaran, 'TF / INVOICE'),
                    COALESCE(status_tagihan, 'NORMAL')
                FROM master_penerima
                WHERE kode_cabang = ?
                ORDER BY TRIM(COALESCE(nama, '')) COLLATE NOCASE ASC
                """,
                (kode_cabang,),
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error("[Master Penerima] Gagal mengambil data: %s", exc)
        return []


def ubah_status_tagihan_penerima(id_penerima, status_baru, kode_cabang):
    """Mengubah status tagihan penerima."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.execute(
            """
            UPDATE master_penerima
            SET status_tagihan = ?,
                is_synced = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id_penerima = ? AND kode_cabang = ?
            """,
            (status_baru, id_penerima, kode_cabang),
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as exc:
        if conn:
            conn.rollback()
        logger.error("[Master Penerima] Gagal mengubah status: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def update_master_penerima_dari_tabel(
    id_penerima,
    kode_cabang,
    nama,
    no_hp,
    alamat,
    kota,
    provinsi,
    pembayaran,
):
    conn = None
    try:
        id_penerima = str(id_penerima or "").strip()
        kode_cabang = str(kode_cabang or CURRENT_SESSION.get(
            'kode_cabang',
            'PUSAT',
        )).strip()
        nama = str(nama or "").strip().upper()
        no_hp = str(no_hp or "").strip()
        alamat = str(alamat or "").strip().upper()
        kota = str(kota or "").strip().upper()
        provinsi = str(provinsi or "").strip().upper()
        pembayaran = str(pembayaran or "TF / INVOICE").strip().upper()

        if not nama:
            return False, "Nama penerima tidak boleh kosong."

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE master_penerima
            SET nama = ?,
                no_hp = ?,
                alamat = ?,
                kota = ?,
                provinsi = ?,
                pembayaran = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id_penerima = ?
              AND kode_cabang = ?
        """, (
            nama,
            no_hp if no_hp else None,
            alamat,
            kota,
            provinsi if provinsi else None,
            pembayaran,
            id_penerima,
            kode_cabang
        ))

        conn.commit()
        return True, ""

    except Exception as e:
        if conn:
            conn.rollback()
        return False, str(e)

    finally:
        if conn:
            conn.close()

# --- 📁 SUB-TAB: DATA TRUK & SOPIR ---


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
    nopol = str(no_polisi or "").strip().upper()
    sopir = str(nama_sopir or "").strip().upper()
    jenis = str(jenis_truk or "").strip()
    hp = str(hp_sopir or "").strip()
    ket = str(ket_truk or "").strip().upper()
    foto = str(foto_truk or "").strip()

    if not cabang:
        return False, "Kode cabang tidak tersedia. Silakan login ulang."
    if not nopol:
        return False, "No. Polisi wajib diisi."
    if not jenis:
        return False, "Jenis truk wajib diisi."

    conn = None
    try:
        conn = get_db_connection(db_name)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO truk (
                kode_cabang, no_polisi, jenis_truk,
                nama_sopir, hp_sopir, ket_truk,
                foto_truk, is_synced, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(kode_cabang, no_polisi) DO UPDATE SET
                jenis_truk = CASE
                    WHEN TRIM(excluded.jenis_truk) <> ''
                    THEN excluded.jenis_truk ELSE truk.jenis_truk
                END,
                nama_sopir = CASE
                    WHEN TRIM(excluded.nama_sopir) <> ''
                    THEN excluded.nama_sopir ELSE truk.nama_sopir
                END,
                hp_sopir = CASE
                    WHEN TRIM(excluded.hp_sopir) <> ''
                    THEN excluded.hp_sopir ELSE truk.hp_sopir
                END,
                ket_truk = CASE
                    WHEN TRIM(excluded.ket_truk) <> ''
                    THEN excluded.ket_truk ELSE truk.ket_truk
                END,
                foto_truk = CASE
                    WHEN TRIM(excluded.foto_truk) <> ''
                    THEN excluded.foto_truk ELSE truk.foto_truk
                END,
                is_synced = 0,
                updated_at = CURRENT_TIMESTAMP
            """,
            (cabang, nopol, jenis, sopir, hp, ket, foto),
        )
        conn.commit()
        return True, ""
    except sqlite3.Error as exc:
        if conn:
            conn.rollback()
        return False, str(exc)
    finally:
        if conn:
            conn.close()


def ambil_semua_truk(db_name=None, kode_cabang=None):
    """Menampilkan daftar truk milik cabang aktif."""
    cabang = _kode_cabang_aktif(kode_cabang)
    try:
        with get_db_connection(db_name) as conn:
            return conn.execute(
                """
                SELECT no_polisi, nama_sopir, jenis_truk,
                       hp_sopir, ket_truk
                FROM truk
                WHERE kode_cabang = ?
                ORDER BY no_polisi ASC
                """,
                (cabang,),
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error("[Truk] Gagal mengambil data: %s", exc)
        return []


def ambil_semua_truk_full(kode_cabang=None):
    """Mengambil seluruh data truk milik cabang aktif untuk tabel UI."""
    cabang = _kode_cabang_aktif(kode_cabang)
    conn = None
    try:
        conn = get_db_connection()
        return conn.execute(
            """
            SELECT no_polisi, jenis_truk, nama_sopir,
                   hp_sopir, ket_truk, foto_truk
            FROM truk
            WHERE kode_cabang = ?
            ORDER BY no_polisi ASC
            """,
            (cabang,),
        ).fetchall()
    except sqlite3.Error as exc:
        logger.error("[Truk] Gagal mengambil data lengkap: %s", exc)
        return []
    finally:
        if conn:
            conn.close()


def simpan_atau_update_truk_full(
    nopol,
    jenis,
    sopir,
    hp,
    ket,
    foto,
    mode="TAMBAH",
    kode_cabang=None,
):
    """Tambah/edit master Truk hanya pada cabang login aktif."""
    cabang = _kode_cabang_aktif(kode_cabang)
    nopol = str(nopol or "").strip().upper()
    jenis = str(jenis or "").strip()
    sopir = str(sopir or "").strip().upper()
    hp = str(hp or "").strip()
    ket = str(ket or "").strip().upper()
    foto = str(foto or "").strip()
    mode = str(mode or "TAMBAH").strip().upper()

    if not cabang:
        return False, "Kode cabang tidak tersedia. Silakan login ulang."
    if not nopol:
        return False, "No. Polisi wajib diisi."
    if not jenis:
        return False, "Jenis truk wajib diisi."

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            """
            SELECT 1
            FROM truk
            WHERE kode_cabang = ? AND no_polisi = ?
            """,
            (cabang, nopol),
        )
        ada = cursor.fetchone() is not None

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
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
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
                SET jenis_truk = ?,
                    nama_sopir = ?,
                    hp_sopir = ?,
                    ket_truk = ?,
                    foto_truk = ?,
                    is_synced = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE kode_cabang = ? AND no_polisi = ?
                """,
                (jenis, sopir, hp, ket, foto, cabang, nopol),
            )
        else:
            conn.rollback()
            return False, f"Mode penyimpanan truk tidak dikenal: {mode}"

        conn.commit()
        return True, ""
    except sqlite3.Error as exc:
        if conn:
            conn.rollback()
        return False, str(exc)
    finally:
        if conn:
            conn.close()

# 🚢 SUB-TAB: MASTER DATA KAPAL


def ambil_semua_kapal_full():
    """Menarik semua kolom data kapal kargo terdaftar untuk di-render ke UI"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(nama_kapal,''),
                COALESCE(tujuan,''),
                COALESCE(ket_kapal,''),
                COALESCE(foto_kapal,'')
            FROM kapal
            ORDER BY nama_kapal ASC
        """)
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"[Kapal] Gagal mengambil data: {e}")
        return []
    finally:
        if conn:
            conn.close()


def simpan_atau_update_kapal_full(nama_kapal, tujuan, ket, foto, mode="TAMBAH"):
    """Menyimpan atau memperbarui data kapal ke database SQLite"""
    nama_kapal = str(nama_kapal or '').strip().upper()
    tujuan = str(tujuan or '').strip().upper()
    ket = str(ket or '').strip().upper()
    foto = str(foto or '').strip()
    mode = str(mode or 'TAMBAH').strip().upper()

    if not nama_kapal:
        return False, "Nama Kapal wajib diisi."

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute("SELECT 1 FROM kapal WHERE nama_kapal = ?", (nama_kapal,))
        ada = cursor.fetchone() is not None

        if mode == 'TAMBAH':
            if ada:
                conn.rollback()
                return (
                    False,
                    f"Kapal '{nama_kapal}' sudah terdaftar. Gunakan menu Edit untuk memperbarui data.",
                )

            cursor.execute('''
                INSERT INTO kapal (
                    nama_kapal, tujuan, ket_kapal, foto_kapal,
                    is_synced, updated_at
                )
                VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            ''', (nama_kapal, tujuan, ket, foto))

        elif mode == 'EDIT':
            if not ada:
                conn.rollback()
                return False, f"Data Kapal '{nama_kapal}' tidak ditemukan."

            cursor.execute('''
                UPDATE kapal
                SET tujuan = ?,
                    ket_kapal = ?,
                    foto_kapal = ?,
                    is_synced = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE nama_kapal = ?
            ''', (tujuan, ket, foto, nama_kapal))
        else:
            conn.rollback()
            return False, f"Mode penyimpanan Kapal tidak dikenal: {mode}"

        conn.commit()
        return True, ""
    except Exception as e:
        if conn:
            conn.rollback()
        return False, str(e)
    finally:
        if conn:
            conn.close()

# ==============================================================================
# ⚙️ TAB SETTING SISTEM
# ==============================================================================


def ambil_semua_data_cabang(limit=10):
    """Mengambil daftar kantor cabang dari database."""
    if USE_CLOUD:
        return []

    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 10

    try:
        with get_db_connection() as conn:
            return conn.execute(
                """
                SELECT kode_cabang, nama_cabang, resi_prefix,
                       start_seq_json, aturan_prefix
                FROM data_cabang
                ORDER BY kode_cabang ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error("[Setting] Gagal mengambil cabang: %s", exc)
        return []


def simpan_semua_pengaturan_dan_cabang(
    settings_to_save,
    branches_to_save,
):
    """Menyimpan pengaturan dan cabang secara atomic tanpa REPLACE parent row."""
    if USE_CLOUD:
        return False, "Penyimpanan cloud belum diaktifkan."

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        for kunci, nilai in settings_to_save:
            cursor.execute(
                """
                INSERT INTO pengaturan_sistem (kunci, nilai)
                VALUES (?, ?)
                ON CONFLICT(kunci) DO UPDATE SET
                    nilai = excluded.nilai
                """,
                (str(kunci), str(nilai)),
            )

        seen_codes = set()
        for branch in branches_to_save:
            kode = str(branch.get("kode_cabang", "")).strip().upper()
            nama = str(branch.get("nama_cabang", "")).strip().upper()
            prefix = str(branch.get("resi_prefix", "")).strip().upper()
            start_seq = str(
                branch.get("start_seq_json", '{"DEFAULT": 0}')
            ).strip()
            aturan = str(
                branch.get("aturan_prefix", '{"DEFAULT": "INV"}')
            ).strip()

            if not kode or not nama or not prefix:
                raise ValueError(
                    "Kode, nama, dan prefix cabang wajib diisi."
                )
            if kode in seen_codes:
                raise ValueError(f"Kode cabang {kode} digunakan lebih dari sekali.")

            json.loads(start_seq)
            json.loads(aturan)
            seen_codes.add(kode)

            cursor.execute(
                """
                INSERT INTO data_cabang (
                    kode_cabang, nama_cabang, resi_prefix,
                    start_seq_json, aturan_prefix
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(kode_cabang) DO UPDATE SET
                    nama_cabang = excluded.nama_cabang,
                    resi_prefix = excluded.resi_prefix,
                    start_seq_json = excluded.start_seq_json,
                    aturan_prefix = excluded.aturan_prefix
                """,
                (kode, nama, prefix, start_seq, aturan),
            )

            if kode == str(
                CURRENT_SESSION.get("kode_cabang", "")
            ).strip().upper():
                CURRENT_SESSION.update(
                    {
                        "nama_cabang": nama,
                        "resi_prefix": prefix,
                        "aturan_prefix": json.loads(aturan),
                    }
                )

        conn.commit()
        return True, "Sukses"
    except Exception as exc:
        if conn:
            conn.rollback()
        logger.exception("[Setting] Gagal menyimpan pengaturan/cabang")
        return False, str(exc)
    finally:
        if conn:
            conn.close()
