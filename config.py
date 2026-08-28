# config.py
import copy
import hmac
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
APP_ENV_PATH = BASE_DIR / "app_env.json"
DEFAULT_DATABASE_NAME = "database_cargo.db"


def _muat_app_environment() -> Dict[str, Any]:
    """Membaca app_env.json; konfigurasi rusak tetap jatuh ke default."""
    if not APP_ENV_PATH.exists():
        return {}
    try:
        with APP_ENV_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"ℹ️ app_env.json tidak dapat dibaca: {exc}")
        return {}


APP_ENV_DATA = _muat_app_environment()


def _normalisasi_path_database(path_value: Any) -> str:
    """Menghasilkan path database absolut relatif terhadap folder aplikasi."""
    raw_path = str(path_value or "").strip() or DEFAULT_DATABASE_NAME
    database_path = Path(raw_path)
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path
    return str(database_path.resolve())


db_aktif = _normalisasi_path_database(
    APP_ENV_DATA.get("active_db", DEFAULT_DATABASE_NAME)
)

def _session_default(database_path: str) -> Dict[str, Any]:
    return {
        "username": "",
        "role": "",
        "kode_cabang": "PUSAT",
        "nama_cabang": "KANTOR PUSAT",
        "home_kode_cabang": "PUSAT",
        "home_nama_cabang": "KANTOR PUSAT",
        "allowed_branches": [],
        "db_name": database_path,
        "resi_prefix": "INV",
        "aturan_prefix": {},
        "is_developer": False,
    }


CURRENT_SESSION = _session_default(db_aktif)


def reset_current_session() -> None:
    """Mengosongkan sesi login tanpa mengubah database aktif."""
    active_database = CURRENT_SESSION.get("db_name") or db_aktif
    CURRENT_SESSION.clear()
    CURRENT_SESSION.update(_session_default(active_database))


DEVELOPER_USERNAME = str(
    APP_ENV_DATA.get("developer_username", "DEV_SUPER") or "DEV_SUPER"
).strip().upper()
DEVELOPER_PASSWORD = str(APP_ENV_DATA.get("developer_password", "") or "")

# Alias legacy tetap dipertahankan.
DEVELOPER_ACCOUNTS = {DEVELOPER_USERNAME: DEVELOPER_PASSWORD}
DEV_PREFIX_RULES = {
    "PROVINSI A": "A",
    "PROVINSI B": "B",
    "PROVINSI C": "C",
    "DEFAULT": "SYS",
}

CENTRAL_BRANCH_ROLES = {"SUPER_ADMIN", "OWNER", "ADMIN_PUSAT", "FINANCE"}


def _password_sama(password_input: Any, password_tersimpan: Any) -> bool:
    """Membandingkan password memakai compare_digest."""
    return hmac.compare_digest(
        str(password_input or ""),
        str(password_tersimpan or ""),
    )


def _verifikasi_login_developer(
    username: str,
    password: str,
) -> Optional[Tuple[bool, str, str]]:
    """Memeriksa akun developer sebelum akun database."""
    if not DEVELOPER_PASSWORD:
        return None
    if not (
        hmac.compare_digest(username, DEVELOPER_USERNAME)
        and _password_sama(password, DEVELOPER_PASSWORD)
    ):
        return None

    CURRENT_SESSION.update({
        "id_user": DEVELOPER_USERNAME,
        "username": DEVELOPER_USERNAME,
        "role": "SUPER_ADMIN",
        "kode_cabang": "DEV_SYS",
        "nama_cabang": "SUPER MODE (DEV)",
        "home_kode_cabang": "DEV_SYS",
        "home_nama_cabang": "SUPER MODE (DEV)",
        "resi_prefix": "SYS",
        "aturan_prefix": DEV_PREFIX_RULES.copy(),
        "is_developer": True,
    })
    refresh_akses_cabang_session()
    return True, "SUPER_ADMIN", "DEVELOPER UTAMA"


def _parse_prefix_rules(
    aturan_prefix: Any,
    default_prefix: str,
) -> Dict[str, str]:
    """Mengubah aturan prefix JSON menjadi dictionary yang valid."""
    if isinstance(aturan_prefix, dict):
        parsed = aturan_prefix
    else:
        try:
            parsed = json.loads(str(aturan_prefix or "{}"))
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed = None

    if isinstance(parsed, dict):
        return {str(key): str(value) for key, value in parsed.items()}
    return {"DEFAULT": str(default_prefix or "INV")}


def _ambil_data_login_user(database_path: str, username: str):
    with sqlite3.connect(database_path, timeout=20.0) as conn:
        return conn.execute(
            """
            SELECT
                u.id_user, u.password, u.role, u.nama_lengkap, u.kode_cabang,
                c.nama_cabang, c.resi_prefix, c.aturan_prefix,
                COALESCE(u.status_user, 'AKTIF')
            FROM manajemen_user AS u
            INNER JOIN data_cabang AS c ON u.kode_cabang = c.kode_cabang
            WHERE UPPER(u.username) = ?
            LIMIT 1
            """,
            (username,),
        ).fetchone()


def _ambil_cabang_diizinkan(
    database_path: str,
    *,
    id_user: str,
    role: str,
    home_kode_cabang: str,
    is_developer: bool = False,
):
    """Ambil branch scope user. Role pusat melihat semua cabang bisnis."""
    home = str(home_kode_cabang or "PUSAT").strip().upper() or "PUSAT"
    role = str(role or "ADMIN").strip().upper() or "ADMIN"
    user_id = str(id_user or "").strip()

    with sqlite3.connect(database_path, timeout=20.0) as conn:
        if is_developer:
            rows = conn.execute(
                """
                SELECT kode_cabang, nama_cabang, resi_prefix, aturan_prefix
                FROM data_cabang
                ORDER BY CASE WHEN kode_cabang = ? THEN 0 ELSE 1 END,
                         nama_cabang COLLATE NOCASE, kode_cabang
                """,
                (home,),
            ).fetchall()
        elif role in CENTRAL_BRANCH_ROLES or home == "PUSAT":
            rows = conn.execute(
                """
                SELECT kode_cabang, nama_cabang, resi_prefix, aturan_prefix
                FROM data_cabang
                WHERE UPPER(kode_cabang) <> 'DEV_SYS'
                ORDER BY CASE WHEN kode_cabang = ? THEN 0 ELSE 1 END,
                         nama_cabang COLLATE NOCASE, kode_cabang
                """,
                (home,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.kode_cabang, c.nama_cabang, c.resi_prefix, c.aturan_prefix
                FROM data_cabang AS c
                WHERE c.kode_cabang = ?
                   OR EXISTS (
                        SELECT 1
                        FROM user_cabang_access AS a
                        WHERE a.id_user = ?
                          AND a.kode_cabang = c.kode_cabang
                   )
                ORDER BY CASE WHEN c.kode_cabang = ? THEN 0 ELSE 1 END,
                         c.nama_cabang COLLATE NOCASE, c.kode_cabang
                """,
                (home, user_id, home),
            ).fetchall()

    hasil = []
    for kode, nama, prefix, aturan in rows:
        kode_bersih = str(kode or "").strip().upper()
        if not kode_bersih:
            continue
        prefix_bersih = str(prefix or "INV").strip().upper() or "INV"
        hasil.append({
            "kode_cabang": kode_bersih,
            "nama_cabang": str(nama or kode_bersih).strip(),
            "resi_prefix": prefix_bersih,
            "aturan_prefix": _parse_prefix_rules(aturan, prefix_bersih),
        })
    return hasil


def refresh_akses_cabang_session() -> List[Dict[str, Any]]:
    """Segarkan daftar cabang yang boleh diakses tanpa mengubah akun login."""
    database_path = str(CURRENT_SESSION.get("db_name") or db_aktif)
    home = str(
        CURRENT_SESSION.get("home_kode_cabang")
        or CURRENT_SESSION.get("kode_cabang")
        or "PUSAT"
    ).strip().upper()
    role = str(CURRENT_SESSION.get("role") or "ADMIN").strip().upper()
    is_developer = bool(CURRENT_SESSION.get("is_developer"))

    try:
        branches = _ambil_cabang_diizinkan(
            database_path,
            id_user=str(CURRENT_SESSION.get("id_user") or ""),
            role=role,
            home_kode_cabang=home,
            is_developer=is_developer,
        )
    except sqlite3.Error as exc:
        print(f"⚠️ Gagal memuat akses cabang: {exc}")
        branches = []

    if not branches:
        branches = [{
            "kode_cabang": str(CURRENT_SESSION.get("kode_cabang") or home),
            "nama_cabang": str(CURRENT_SESSION.get("nama_cabang") or home),
            "resi_prefix": str(CURRENT_SESSION.get("resi_prefix") or "INV"),
            "aturan_prefix": dict(CURRENT_SESSION.get("aturan_prefix") or {}),
        }]

    CURRENT_SESSION["allowed_branches"] = branches
    allowed_codes = {item["kode_cabang"] for item in branches}
    current = str(CURRENT_SESSION.get("kode_cabang") or home).strip().upper()
    if current not in allowed_codes:
        current = home if home in allowed_codes else branches[0]["kode_cabang"]
        aktifkan_cabang_session(current, refresh_access=False)
    return branches


def aktifkan_cabang_session(kode_cabang: Any, *, refresh_access: bool = True) -> bool:
    """Ganti cabang operasional aktif setelah memvalidasi branch scope user."""
    kode = str(kode_cabang or "").strip().upper()
    if not kode or kode == "__ALL__":
        return False
    if refresh_access:
        refresh_akses_cabang_session()
    branches = CURRENT_SESSION.get("allowed_branches") or []
    target = next(
        (item for item in branches if str(item.get("kode_cabang", "")).upper() == kode),
        None,
    )
    if not target:
        return False
    CURRENT_SESSION.update({
        "kode_cabang": kode,
        "nama_cabang": str(target.get("nama_cabang") or kode),
        "resi_prefix": str(target.get("resi_prefix") or "INV").strip().upper() or "INV",
        "aturan_prefix": dict(target.get("aturan_prefix") or {}),
    })
    return True


def _terapkan_session_user(username: str, row) -> str:
    (
        id_user, _, db_role, db_nama, kode_cabang,
        nama_cabang, resi_prefix, aturan_prefix, _status_user,
    ) = row
    resolved_prefix = str(resi_prefix or "INV").strip().upper() or "INV"
    kode_home = str(kode_cabang or "PUSAT").strip().upper()
    nama_home = str(nama_cabang or "KANTOR PUSAT").strip()
    CURRENT_SESSION.update({
        "id_user": str(id_user or "").strip(),
        "username": username,
        "role": str(db_role or "").strip().upper(),
        "kode_cabang": kode_home,
        "nama_cabang": nama_home,
        "home_kode_cabang": kode_home,
        "home_nama_cabang": nama_home,
        "resi_prefix": resolved_prefix,
        "aturan_prefix": _parse_prefix_rules(aturan_prefix, resolved_prefix),
        "is_developer": False,
    })
    refresh_akses_cabang_session()
    return str(db_nama or username)


def verifikasi_login_sistem(
    username_input: Any,
    password_input: Any,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Memverifikasi developer lebih dahulu, lalu user multi-cabang database."""
    username = str(username_input or "").strip().upper()
    password = str(password_input or "").strip()
    if not username or not password:
        return False, None, None

    hasil_developer = _verifikasi_login_developer(username, password)
    if hasil_developer is not None:
        return hasil_developer

    try:
        row = _ambil_data_login_user(
            CURRENT_SESSION.get("db_name") or db_aktif,
            username,
        )
        if row is None or not _password_sama(password, row[1]):
            return False, None, None
        status_user = str(row[8] or "AKTIF").strip().upper()
        if status_user != "AKTIF":
            return False, None, None

        nama_lengkap = _terapkan_session_user(username, row)
        return True, CURRENT_SESSION["role"], nama_lengkap
    except sqlite3.Error as exc:
        print(f"⚠️ Gagal mencocokkan login ke database: {exc}")
        return False, None, None


DEFAULT_CLIENT_DATA = {
    "nama_perusahaan": "PT KARGO EKSPEDISI",
    "alamat_perusahaan": "ALAMAT PERUSAHAAN",
    "telp_perusahaan": "0000-0000-0000",
    "logo_text_html": "KARGO EKSPEDISI",
    "rekening_nonpajak": [],
    "rekening_pajak": [],
    "format_resi_manual": False,
    "template_no_resi": "[PREFIX][COUNTER][SUFFIX]",
    "kode_akhiran_pajak": "-P",
    "prefix_invoice": "INV",
    "provinsi_tujuan": ["PROVINSI A", "PROVINSI B", "PROVINSI C"],
}
DATA_CLIENT = copy.deepcopy(DEFAULT_CLIENT_DATA)

_TRUE_VALUES = {"1", "true", "yes", "ya", "aktif", "on"}
_FALSE_VALUES = {"0", "false", "no", "tidak", "nonaktif", "off"}
_TEXT_SETTING_KEYS = (
    "nama_perusahaan",
    "alamat_perusahaan",
    "telp_perusahaan",
    "logo_text_html",
    "template_no_resi",
    "kode_akhiran_pajak",
    "prefix_invoice",
)
_LIST_SETTING_KEYS = ("rekening_pajak", "rekening_nonpajak", "provinsi_tujuan")


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
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
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


def _baca_pengaturan_database(database_path: str) -> Dict[str, Any]:
    with sqlite3.connect(database_path, timeout=20.0) as conn:
        return dict(conn.execute("SELECT kunci, nilai FROM pengaturan_sistem").fetchall())


def muat_pengaturan_sistem() -> Dict[str, Any]:
    """Membaca setting database aktif dengan fallback white-label default."""
    hasil_db = copy.deepcopy(DEFAULT_CLIENT_DATA)
    try:
        db_data = _baca_pengaturan_database(CURRENT_SESSION.get("db_name") or db_aktif)
        for key in _TEXT_SETTING_KEYS:
            if key in db_data:
                hasil_db[key] = str(db_data[key] or "")
        for key in _LIST_SETTING_KEYS:
            hasil_db[key] = _parse_json_list(db_data.get(key), DEFAULT_CLIENT_DATA[key])
        hasil_db["format_resi_manual"] = _parse_bool(
            db_data.get("format_resi_manual"),
            DEFAULT_CLIENT_DATA["format_resi_manual"],
        )
    except sqlite3.Error as exc:
        print(f"ℹ️ Database belum siap, menggunakan pengaturan default: {exc}")
    return hasil_db


def refresh_data_client() -> Dict[str, Any]:
    """Memuat ulang DATA_CLIENT tanpa mengganti object dictionary."""
    DATA_CLIENT.clear()
    DATA_CLIENT.update(muat_pengaturan_sistem())
    return DATA_CLIENT


def identitas_perusahaan_masih_dummy() -> bool:
    """True bila identitas perusahaan masih menggunakan placeholder bawaan."""
    nama = str(DATA_CLIENT.get("nama_perusahaan", "")).strip().upper()
    alamat = str(DATA_CLIENT.get("alamat_perusahaan", "")).strip().upper()
    telepon = str(DATA_CLIENT.get("telp_perusahaan", "")).strip()
    return (
        nama == "PT KARGO EKSPEDISI"
        or alamat == "ALAMAT PERUSAHAAN"
        or telepon == "0000-0000-0000"
    )