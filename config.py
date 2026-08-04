# config.py
import copy
import hmac
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# =====================================================================
# 1. PATH APLIKASI DAN DATABASE AKTIF
# =====================================================================
BASE_DIR = Path(__file__).resolve().parent
APP_ENV_PATH = BASE_DIR / "app_env.json"
DEFAULT_DATABASE_NAME = "database_cargo.db"


def _muat_app_environment() -> Dict[str, Any]:
    """
    Membaca konfigurasi instalasi lokal dari app_env.json.

    Jika file belum tersedia, kosong, atau rusak, aplikasi tetap berjalan
    menggunakan konfigurasi default.
    """
    if not APP_ENV_PATH.exists():
        return {}

    try:
        with APP_ENV_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"ℹ️ app_env.json tidak dapat dibaca: {exc}")

    return {}

APP_ENV_DATA = _muat_app_environment()


def _normalisasi_path_database(path_value: Any) -> str:
    """
    Menghasilkan path database absolut.

    Path relatif pada app_env.json dihitung dari folder aplikasi,
    bukan dari folder tempat terminal dijalankan.
    """
    raw_path = str(path_value or "").strip()

    if not raw_path:
        raw_path = DEFAULT_DATABASE_NAME

    database_path = Path(raw_path)

    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path

    return str(database_path.resolve())

db_aktif = _normalisasi_path_database(
    APP_ENV_DATA.get("active_db", DEFAULT_DATABASE_NAME)
)

# =====================================================================
# 2. VARIABEL SESI AKTIF (MANAJER RAM / STATE MANAGEMENT)
# =====================================================================
CURRENT_SESSION = {
    "username": "",
    "role": "",
    "kode_cabang": "PUSAT",
    "nama_cabang": "KANTOR PUSAT",
    "db_name": db_aktif,
    "resi_prefix": "INV",
    "aturan_prefix": {},
    "is_developer": False,
}


def reset_current_session() -> None:
    """Mengosongkan sesi login tanpa mengubah database aktif."""
    active_database = CURRENT_SESSION.get("db_name") or db_aktif

    CURRENT_SESSION.clear()
    CURRENT_SESSION.update(
        {
            "username": "",
            "role": "",
            "kode_cabang": "PUSAT",
            "nama_cabang": "KANTOR PUSAT",
            "db_name": active_database,
            "resi_prefix": "INV",
            "aturan_prefix": {},
            "is_developer": False,
        }
    )

DEVELOPER_USERNAME = str(
    APP_ENV_DATA.get("developer_username", "DEV_SUPER") or "DEV_SUPER"
).strip().upper()

DEVELOPER_PASSWORD = str(
    APP_ENV_DATA.get("developer_password", "") or ""
)

# Dipertahankan agar modul lama yang mengimpor DEVELOPER_ACCOUNTS
# tidak langsung rusak.
DEVELOPER_ACCOUNTS = {
    DEVELOPER_USERNAME: DEVELOPER_PASSWORD,
}

DEV_PREFIX_RULES = {
    "PROVINSI A": "A",
    "PROVINSI B": "B",
    "PROVINSI C": "C",
    "DEFAULT": "SYS",
}


def _password_sama(password_input: Any, password_tersimpan: Any) -> bool:
    """
    Membandingkan password dengan compare_digest.

    Password user database masih mengikuti schema aplikasi yang sekarang.
    """
    return hmac.compare_digest(
        str(password_input or ""),
        str(password_tersimpan or ""),
    )


def _verifikasi_login_developer(
    username: str,
    password: str,
) -> Optional[Tuple[bool, str, str]]:
    """
    Memeriksa akun developer sebelum akun database.

    Login developer hanya aktif apabila developer_password tersedia
    di app_env.json.
    """
    if not DEVELOPER_PASSWORD:
        return None

    username_benar = hmac.compare_digest(
        username,
        DEVELOPER_USERNAME,
    )
    password_benar = _password_sama(
        password,
        DEVELOPER_PASSWORD,
    )

    if not username_benar or not password_benar:
        return None

    CURRENT_SESSION.update(
        {
            "username": DEVELOPER_USERNAME,
            "role": "SUPER_ADMIN",
            "kode_cabang": "DEV_SYS",
            "nama_cabang": "SUPER MODE (DEV)",
            "resi_prefix": "SYS",
            "aturan_prefix": DEV_PREFIX_RULES.copy(),
            "is_developer": True,
        }
    )

    return True, "SUPER_ADMIN", "DEVELOPER UTAMA"

# =====================================================================
# 4. HELPER ATURAN PREFIX
# =====================================================================


def _parse_prefix_rules(
    aturan_prefix: Any,
    default_prefix: str,
) -> Dict[str, str]:
    """Mengubah aturan prefix JSON menjadi dictionary yang valid."""
    if isinstance(aturan_prefix, dict):
        return {
            str(key): str(value)
            for key, value in aturan_prefix.items()
        }

    try:
        parsed = json.loads(str(aturan_prefix or "{}"))

        if isinstance(parsed, dict):
            return {
                str(key): str(value)
                for key, value in parsed.items()
            }

    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    return {
        "DEFAULT": str(default_prefix or "INV"),
    }

# =====================================================================
# 5. FUNGSI VALIDASI LOGIN PINTAR (MEMBACA MULTI-CABANG)
# =====================================================================


def verifikasi_login_sistem(
    username_input: Any,
    password_input: Any,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Urutan login:
    1. Akun developer dari app_env.json.
    2. Akun pengguna dari tabel manajemen_user.
    """
    username = str(username_input or "").strip().upper()
    password = str(password_input or "").strip()

    if not username or not password:
        return False, None, None

    hasil_developer = _verifikasi_login_developer(
        username,
        password,
    )

    if hasil_developer is not None:
        return hasil_developer

    database_path = CURRENT_SESSION.get("db_name") or db_aktif

    try:
        with sqlite3.connect(
            database_path,
            timeout=20.0,
        ) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    u.password,
                    u.role,
                    u.nama_lengkap,
                    u.kode_cabang,
                    c.nama_cabang,
                    c.resi_prefix,
                    c.aturan_prefix
                FROM manajemen_user AS u
                INNER JOIN data_cabang AS c
                    ON u.kode_cabang = c.kode_cabang
                WHERE UPPER(u.username) = ?
                LIMIT 1
                """,
                (username,),
            )

            row = cursor.fetchone()

        if row is None:
            return False, None, None

        (
            db_password,
            db_role,
            db_nama,
            kode_cabang,
            nama_cabang,
            resi_prefix,
            aturan_prefix,
        ) = row

        if not _password_sama(password, db_password):
            return False, None, None

        resolved_prefix = (
            str(resi_prefix or "INV")
            .strip()
            .upper()
            or "INV"
        )

        CURRENT_SESSION.update(
            {
                "username": username,
                "role": str(db_role or "").strip().upper(),
                "kode_cabang": (
                    str(kode_cabang or "PUSAT")
                    .strip()
                    .upper()
                ),
                "nama_cabang": (
                    str(nama_cabang or "KANTOR PUSAT")
                    .strip()
                ),
                "resi_prefix": resolved_prefix,
                "aturan_prefix": _parse_prefix_rules(
                    aturan_prefix,
                    resolved_prefix,
                ),
                "is_developer": False,
            }
        )

        return (
            True,
            CURRENT_SESSION["role"],
            str(db_nama or username),
        )

    except sqlite3.Error as exc:
        print(
            "⚠️ Gagal mencocokkan login "
            f"ke database: {exc}"
        )

    return False, None, None

# =====================================================================
# 6. DATA BAWAAN DEFAULT WHITE-LABEL
# =====================================================================
# Nilai ini hanya placeholder agar aplikasi tidak kosong ketika database
# baru belum memiliki pengaturan. Seluruh nilai bisa ditimpa dari menu
# Pengaturan dan tabel pengaturan_sistem.
DEFAULT_CLIENT_DATA = {
    "nama_perusahaan": "PT KARGO EKSPEDISI",
    "alamat_perusahaan": "ALAMAT PERUSAHAAN",
    "telp_perusahaan": "0000-0000-0000",
    "logo_text_html": "KARGO EKSPEDISI",

    # Sengaja kosong agar rekening contoh tidak ikut tercetak.
    "rekening_nonpajak": [],
    "rekening_pajak": [],

    "format_resi_manual": False,
    "template_no_resi": "[PREFIX][COUNTER][SUFFIX]",
    "kode_akhiran_pajak": "-P",
    "prefix_invoice": "INV",
    "provinsi_tujuan": [
        "PROVINSI A",
        "PROVINSI B",
        "PROVINSI C",
    ],
}

# deepcopy diperlukan karena dictionary memiliki nilai list.
DATA_CLIENT = copy.deepcopy(DEFAULT_CLIENT_DATA)

# =====================================================================
# 7. HELPER KONVERSI NILAI PENGATURAN
# =====================================================================


def _parse_bool(
    value: Any,
    default: bool = False,
) -> bool:
    """Mengubah nilai SQLite menjadi boolean secara konsisten."""
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    normalized = str(value).strip().lower()

    if normalized in {
        "1",
        "true",
        "yes",
        "ya",
        "aktif",
        "on",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "tidak",
        "nonaktif",
        "off",
    }:
        return False

    return default


def _parse_json_list(
    value: Any,
    default: List[Any],
) -> List[Any]:
    """Mengubah nilai JSON menjadi list tanpa menghentikan aplikasi."""
    if isinstance(value, list):
        return copy.deepcopy(value)

    if value is None or str(value).strip() == "":
        return copy.deepcopy(default)

    try:
        parsed = json.loads(str(value))

        if isinstance(parsed, list):
            return parsed

    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    return copy.deepcopy(default)

# =====================================================================
# 8. FUNGSI PENGAMBIL DATA PENGATURAN SISTEM
# =====================================================================


def muat_pengaturan_sistem() -> Dict[str, Any]:
    """
    Membaca konfigurasi dari database aktif.

    Jika database atau tabel belum siap, fungsi tetap mengembalikan
    default white-label.
    """
    hasil_db = copy.deepcopy(DEFAULT_CLIENT_DATA)
    database_path = CURRENT_SESSION.get("db_name") or db_aktif

    try:
        with sqlite3.connect(
            database_path,
            timeout=20.0,
        ) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT kunci, nilai
                FROM pengaturan_sistem
                """
            )
            rows = cursor.fetchall()

        db_data = dict(rows)

        text_keys = (
            "nama_perusahaan",
            "alamat_perusahaan",
            "telp_perusahaan",
            "logo_text_html",
            "template_no_resi",
            "kode_akhiran_pajak",
            "prefix_invoice",
        )

        for key in text_keys:
            if key in db_data:
                hasil_db[key] = str(db_data[key] or "")

        hasil_db["rekening_pajak"] = _parse_json_list(
            db_data.get("rekening_pajak"),
            DEFAULT_CLIENT_DATA["rekening_pajak"],
        )

        hasil_db["rekening_nonpajak"] = _parse_json_list(
            db_data.get("rekening_nonpajak"),
            DEFAULT_CLIENT_DATA["rekening_nonpajak"],
        )

        hasil_db["provinsi_tujuan"] = _parse_json_list(
            db_data.get("provinsi_tujuan"),
            DEFAULT_CLIENT_DATA["provinsi_tujuan"],
        )

        hasil_db["format_resi_manual"] = _parse_bool(
            db_data.get("format_resi_manual"),
            DEFAULT_CLIENT_DATA["format_resi_manual"],
        )

    except sqlite3.Error as exc:
        print(
            "ℹ️ Database belum siap, "
            f"menggunakan pengaturan default: {exc}"
        )

    return hasil_db


def refresh_data_client() -> Dict[str, Any]:
    """
    Memuat ulang DATA_CLIENT tanpa mengganti object dictionary.

    Aman untuk modul yang memakai:
        from config import DATA_CLIENT
    """
    DATA_CLIENT.clear()
    DATA_CLIENT.update(
        muat_pengaturan_sistem()
    )

    return DATA_CLIENT


def identitas_perusahaan_masih_dummy() -> bool:
    """
    Mengembalikan True jika identitas masih menggunakan placeholder.
    Bisa dipakai untuk memberi peringatan sebelum mencetak dokumen.
    """
    nama = str(
        DATA_CLIENT.get(
            "nama_perusahaan",
            "",
        )
    ).strip().upper()

    alamat = str(
        DATA_CLIENT.get(
            "alamat_perusahaan",
            "",
        )
    ).strip().upper()

    telepon = str(
        DATA_CLIENT.get(
            "telp_perusahaan",
            "",
        )
    ).strip()

    return (
        nama == "PT KARGO EKSPEDISI"
        or alamat == "ALAMAT PERUSAHAAN"
        or telepon == "0000-0000-0000"
    )
