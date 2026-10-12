# config.py
import copy
import hmac
import json
import os
import sqlite3
from supabase_client import supabase

def _is_network_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    name = type(exc).__name__.lower()
    markers = (
        "connecterror", "connecttimeout", "getaddrinfo failed",
        "network is unreachable", "connection reset", "connection refused",
        "connection aborted", "winerror 10054", "winerror 10060",
        "errno 11001", "errno 10054", "errno 10060", "timed out",
    )
    return any(marker in text or marker in name for marker in markers)

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
APP_ENV_PATH = BASE_DIR / "app_env.json"
DEFAULT_DATABASE_NAME = "database_cargo.db"
# Database khusus sandbox akun developer/offline tester.
# File ini sengaja dipisahkan dari database online agar perubahan tester
# tidak pernah ikut masuk ke sync_outbox milik database online.
DEVELOPER_DATABASE_NAME = "database_cargo_dev.db"


def _muat_app_environment() -> Dict[str, Any]:
    """Membaca app_env.json; konfigurasi rusak tetap jatuh ke default."""
    if not APP_ENV_PATH.exists():
        return {}
    try:
        with APP_ENV_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"INFO: app_env.json tidak dapat dibaca: {exc}")
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

# Hak akses cabang operasional Mahkota:
# - SUPER: full ke semua cabang.
# - User home SBY: full ke SBY + JKT.
# - User home cabang non-pusat (mis. JKT): full ke home, view-only ke cabang lain.
CENTRAL_BRANCH_ROLES = {"SUPER_ADMIN"}
CENTRAL_FULL_ACCESS_HOME_BRANCHES = {"SBY"}
BRANCH_ACCESS_FULL = "FULL"
BRANCH_ACCESS_VIEW = "VIEW"

def _session_default(database_path: str) -> Dict[str, Any]:
    return {
        "id_user": "",
        "username": "",
        "nama_lengkap": "",
        "auth_email": "",
        "role": "",
        "kode_cabang": "PUSAT",
        "nama_cabang": "KANTOR PUSAT",
        "home_kode_cabang": "PUSAT",
        "home_nama_cabang": "KANTOR PUSAT",
        "allowed_branches": [],
        "active_access_mode": BRANCH_ACCESS_FULL,
        "db_name": database_path,
        "resi_prefix": "INV",
        "aturan_prefix": {},
        "is_developer": False,
        "is_offline_session": False,
    }


CURRENT_SESSION = _session_default(db_aktif)


def reset_current_session() -> None:
    """Mengosongkan sesi login dan kembali ke database online/default."""
    CURRENT_SESSION.clear()
    CURRENT_SESSION.update(_session_default(db_aktif))


DEVELOPER_USERNAME = str(
    os.getenv(
        "KARGO_DEV_USERNAME",
        APP_ENV_DATA.get("developer_username", "DEV_SUPER"),
    )
    or "DEV_SUPER"
).strip().upper()
# Jangan pernah menyimpan password developer di app_env.json/source.
# .env lokal tetap dibaca oleh supabase_client.py melalui load_dotenv().
DEVELOPER_PASSWORD = str(os.getenv("KARGO_DEV_PASSWORD", "") or "")

# Alias legacy tetap dipertahankan tanpa mengekspos password ketika belum
# dikonfigurasi di environment lokal.
DEVELOPER_ACCOUNTS = (
    {DEVELOPER_USERNAME: DEVELOPER_PASSWORD}
    if DEVELOPER_PASSWORD
    else {}
)
DEV_PREFIX_RULES = {
    "PROVINSI A": "A",
    "PROVINSI B": "B",
    "PROVINSI C": "C",
    "DEFAULT": "SYS",
}

# Model role final: SUPER (database/RLS) dan SUPER_ADMIN (legacy UI internal).
# ADMIN mencakup semua role non-SUPER dari data lama.
ROLE_SUPER_DB = "SUPER"
ROLE_SUPER_APP = "SUPER_ADMIN"
ROLE_ADMIN_APP = "ADMIN"


def _password_sama(password_input: Any, password_tersimpan: Any) -> bool:
    """Membandingkan password memakai compare_digest."""
    return hmac.compare_digest(
        str(password_input or ""),
        str(password_tersimpan or ""),
    )

def _verifikasi_login_supabase(
    email: str,
    password: str,
) -> Optional[Tuple[bool, str, str]]:
    """
    Login melalui Supabase Auth.

    Login dianggap sukses hanya bila Auth + profile + cabang berhasil dimuat
    seluruhnya. Bila tahap lanjutan gagal setelah Auth berhasil, sesi Supabase
    dibatalkan dan CURRENT_SESSION dikembalikan ke keadaan kosong.
    """
    CURRENT_SESSION["db_name"] = db_aktif
    authenticated = False
    login_complete = False
    try:
        response = supabase.auth.sign_in_with_password({
            "email": str(email).strip(),
            "password": str(password),
        })

        user = getattr(response, "user", None)
        if user is None:
            return False, None, None

        user_id = str(getattr(user, "id", "") or "").strip()
        if not user_id:
            return False, None, None
        authenticated = True

        profile_response = (
            supabase
            .table("user_profiles")
            .select(
                "id, username, role, nama_lengkap, kode_cabang, "
                "status_user, auth_email"
            )
            .eq("id", user_id)
            .single()
            .execute()
        )

        profile = profile_response.data
        if not isinstance(profile, dict):
            return False, None, None

        status_user = str(
            profile.get("status_user") or "AKTIF"
        ).strip().upper()
        if status_user != "AKTIF":
            return False, None, None

        kode_cabang = str(
            profile.get("kode_cabang") or "PUSAT"
        ).strip().upper()

        role_db = str(
            profile.get("role") or "ADMIN"
        ).strip().upper()
        role = ROLE_SUPER_APP if role_db == ROLE_SUPER_DB else ROLE_ADMIN_APP

        username = str(
            profile.get("username") or email
        ).strip()
        nama_lengkap = str(
            profile.get("nama_lengkap") or username
        ).strip()
        auth_email = str(
            profile.get("auth_email") or email
        ).strip()

        cabang_response = (
            supabase
            .table("data_cabang")
            .select(
                "kode_cabang, nama_cabang, resi_prefix, aturan_prefix"
            )
            .eq("kode_cabang", kode_cabang)
            .single()
            .execute()
        )
        cabang = cabang_response.data or {}

        nama_cabang = str(
            cabang.get("nama_cabang") or kode_cabang
        ).strip()
        resi_prefix = str(
            cabang.get("resi_prefix") or "INV"
        ).strip().upper() or "INV"
        aturan_prefix = _parse_prefix_rules(
            cabang.get("aturan_prefix"),
            resi_prefix,
        )

        CURRENT_SESSION.update({
            "id_user": user_id,
            "username": username,
            "nama_lengkap": nama_lengkap,
            "auth_email": auth_email,
            "role": role,
            "kode_cabang": kode_cabang,
            "nama_cabang": nama_cabang,
            "home_kode_cabang": kode_cabang,
            "home_nama_cabang": nama_cabang,
            "resi_prefix": resi_prefix,
            "aturan_prefix": aturan_prefix,
            "is_developer": False,
            "is_offline_session": False,
        })
        refresh_akses_cabang_session()
        login_complete = True
        return True, role, nama_lengkap

    except Exception as exc:
        if _is_network_error(exc) and not authenticated:
            cached = _verifikasi_login_offline_cache(email, password)
            if cached:
                print(
                    "INFO: Offline login aktif — memakai cache akun lokal "
                    f"({str(email).strip()}).",
                    flush=True,
                )
                return cached
            print(
                "INFO: Supabase offline dan akun ini belum pernah login online "
                "di komputer ini.",
                flush=True,
            )
        else:
            print(f"WARNING: Login Supabase gagal: {exc}", flush=True)
        return False, None, None
    finally:
        # Jangan pernah meninggalkan access token valid ketika login tidak
        # selesai sampai tahap pembentukan session aplikasi.
        if authenticated and not login_complete:
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            reset_current_session()


def _verifikasi_login_developer(
    username: str,
    password: str,
) -> Optional[Tuple[bool, str, str]]:
    """Login developer selalu memakai database sandbox offline terpisah."""
    if not DEVELOPER_PASSWORD:
        return None
    if not (
        hmac.compare_digest(username, DEVELOPER_USERNAME)
        and _password_sama(password, DEVELOPER_PASSWORD)
    ):
        return None

    # Putuskan session Supabase bila ada agar DEV_SUPER benar-benar offline.
    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    # Pastikan sesi developer selalu diarahkan ke DB sandbox, bukan DB online.
    CURRENT_SESSION["db_name"] = _normalisasi_path_database(DEVELOPER_DATABASE_NAME)
    CURRENT_SESSION.update({
        "auth_email": "",
        "id_user": DEVELOPER_USERNAME,
        "nama_lengkap": "DEVELOPER UTAMA",
        "username": DEVELOPER_USERNAME,
        "role": "SUPER_ADMIN",
        "kode_cabang": "DEV_SYS",
        "nama_cabang": "SUPER MODE (DEV)",
        "home_kode_cabang": "DEV_SYS",
        "home_nama_cabang": "SUPER MODE (DEV)",
        "resi_prefix": "SYS",
        "aturan_prefix": DEV_PREFIX_RULES.copy(),
        "is_developer": True,
        "is_offline_session": False,
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


def _mode_akses_cabang(kode_cabang: Any, *, home_kode_cabang: Any = None, role: Any = None, is_developer: bool = None) -> str:
    """Tentukan mode akses cabang aktif secara konsisten di seluruh aplikasi."""
    kode = str(kode_cabang or "").strip().upper()
    home = str(home_kode_cabang or CURRENT_SESSION.get("home_kode_cabang") or "").strip().upper()
    role_bersih = str(role or CURRENT_SESSION.get("role") or "ADMIN").strip().upper()
    developer = bool(CURRENT_SESSION.get("is_developer") if is_developer is None else is_developer)

    if developer or role_bersih in CENTRAL_BRANCH_ROLES:
        return BRANCH_ACCESS_FULL
    if home in CENTRAL_FULL_ACCESS_HOME_BRANCHES:
        return BRANCH_ACCESS_FULL
    if kode and kode == home:
        return BRANCH_ACCESS_FULL
    return BRANCH_ACCESS_VIEW


def cabang_boleh_baca(kode_cabang: Any) -> bool:
    """Periksa apakah cabang target termasuk scope baca sesi aktif."""
    target = str(kode_cabang or "").strip().upper()
    if not target or target == "DEV_SYS":
        return False
    allowed = {
        str(item.get("kode_cabang") or "").strip().upper()
        for item in (CURRENT_SESSION.get("allowed_branches") or [])
        if str(item.get("kode_cabang") or "").strip()
    }
    return target in allowed


def cabang_boleh_tulis(kode_cabang: Any = None) -> bool:
    """True hanya bila user aktif mempunyai hak tulis pada cabang target."""
    target = str(kode_cabang or CURRENT_SESSION.get("kode_cabang") or "").strip().upper()
    return _mode_akses_cabang(target) == BRANCH_ACCESS_FULL


def mode_akses_cabang(kode_cabang: Any = None) -> str:
    """Mode FULL/VIEW untuk cabang yang sedang dibuka."""
    target = str(kode_cabang or CURRENT_SESSION.get("kode_cabang") or "").strip().upper()
    return _mode_akses_cabang(target)


def _ambil_cabang_diizinkan(
    database_path: str,
    *,
    id_user: str,
    role: str,
    home_kode_cabang: str,
    is_developer: bool = False,
):
    """Ambil scope cabang dari cache SQLite dengan policy yang sama seperti online.

    Fallback offline tidak boleh memperlebar hak akses. SUPER dan user home SBY
    memperoleh seluruh cabang bisnis; user cabang lain hanya memperoleh home +
    baris yang memang ada di user_cabang_access.
    """
    home = str(home_kode_cabang or "PUSAT").strip().upper() or "PUSAT"
    role_bersih = str(role or CURRENT_SESSION.get("role") or "ADMIN").strip().upper()
    user_id_bersih = str(id_user or "").strip()
    otomatis_full = (
        bool(is_developer)
        or role_bersih in CENTRAL_BRANCH_ROLES
        or home in CENTRAL_FULL_ACCESS_HOME_BRANCHES
        or home == "PUSAT"
    )

    with sqlite3.connect(database_path, timeout=20.0) as conn:
        if otomatis_full:
            rows = conn.execute(
                """
                SELECT kode_cabang, nama_cabang, resi_prefix, aturan_prefix
                FROM data_cabang
                WHERE UPPER(kode_cabang) <> 'DEV_SYS'
                ORDER BY CASE WHEN UPPER(kode_cabang) = ? THEN 0 ELSE 1 END,
                         nama_cabang COLLATE NOCASE, kode_cabang
                """,
                (home,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT DISTINCT
                    c.kode_cabang, c.nama_cabang, c.resi_prefix, c.aturan_prefix
                FROM data_cabang AS c
                LEFT JOIN user_cabang_access AS a
                    ON a.kode_cabang = c.kode_cabang
                   AND a.id_user = ?
                WHERE UPPER(c.kode_cabang) <> 'DEV_SYS'
                  AND (UPPER(c.kode_cabang) = ? OR a.id_user IS NOT NULL)
                ORDER BY CASE WHEN UPPER(c.kode_cabang) = ? THEN 0 ELSE 1 END,
                         c.nama_cabang COLLATE NOCASE, c.kode_cabang
                """,
                (user_id_bersih, home, home),
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
            "access_mode": _mode_akses_cabang(
                kode_bersih,
                home_kode_cabang=home_kode_cabang,
                role=role,
                is_developer=is_developer,
            ),
        })
    return hasil


def _ambil_cabang_diizinkan_supabase(*, home: str, role: str) -> List[Dict[str, Any]]:
    """Ambil branch scope online dari Supabase, lalu normalisasi ke format UI."""
    user_id = str(CURRENT_SESSION.get("id_user") or "").strip()
    if not user_id or not str(CURRENT_SESSION.get("auth_email") or "").strip():
        return []

    branch_response = (
        supabase
        .table("data_cabang")
        .select("kode_cabang, nama_cabang, resi_prefix, aturan_prefix")
        .neq("kode_cabang", "DEV_SYS")
        .order("nama_cabang", desc=False)
        .execute()
    )
    branch_rows = branch_response.data or []
    access_response = (
        supabase
        .table("user_cabang_access")
        .select("kode_cabang")
        .eq("id_user", user_id)
        .execute()
    )
    allowed_codes = {
        str(row.get("kode_cabang") or "").strip().upper()
        for row in (access_response.data or [])
        if str(row.get("kode_cabang") or "").strip()
    }

    # SUPER tetap full access walaupun tabel access sedang kosong.
    role_super = role in CENTRAL_BRANCH_ROLES
    hasil = []
    for row in branch_rows:
        kode = str(row.get("kode_cabang") or "").strip().upper()
        if not kode:
            continue
        if role_super or home == "PUSAT" or home in CENTRAL_FULL_ACCESS_HOME_BRANCHES:
            # SUPER, akun pusat/fallback, dan user home SBY boleh membuka
            # seluruh cabang bisnis (SBY + JKT) tanpa harus bergantung
            # pada baris user_cabang_access satu per satu.
            boleh = True
        else:
            # User cabang non-pusat hanya mendapat home + cabang yang
            # memang diberikan melalui user_cabang_access.
            boleh = kode in allowed_codes or kode == home
        if not boleh:
            continue
        prefix = str(row.get("resi_prefix") or "INV").strip().upper() or "INV"
        hasil.append({
            "kode_cabang": kode,
            "nama_cabang": str(row.get("nama_cabang") or kode).strip(),
            "resi_prefix": prefix,
            "aturan_prefix": _parse_prefix_rules(row.get("aturan_prefix"), prefix),
            "access_mode": _mode_akses_cabang(
                kode,
                home_kode_cabang=home,
                role=role,
                is_developer=False,
            ),
        })
    hasil.sort(key=lambda item: (0 if item["kode_cabang"] == home else 1, item["nama_cabang"].lower(), item["kode_cabang"]))
    return hasil


def refresh_akses_cabang_session() -> List[Dict[str, Any]]:
    """Segarkan branch scope; Supabase menjadi sumber utama untuk akun online."""
    database_path = str(CURRENT_SESSION.get("db_name") or db_aktif)
    home = str(
        CURRENT_SESSION.get("home_kode_cabang")
        or CURRENT_SESSION.get("kode_cabang")
        or "PUSAT"
    ).strip().upper()
    role = str(CURRENT_SESSION.get("role") or "ADMIN").strip().upper()
    is_developer = bool(CURRENT_SESSION.get("is_developer"))

    branches = []
    if not is_developer and str(CURRENT_SESSION.get("auth_email") or "").strip():
        try:
            branches = _ambil_cabang_diizinkan_supabase(home=home, role=role)
        except Exception as exc:
            # Offline-first: cache lokal tetap dipakai saat Supabase sementara tidak tersedia.
            print(f"INFO: Branch scope Supabase tidak tersedia, memakai cache lokal: {exc}")

    if not branches:
        try:
            branches = _ambil_cabang_diizinkan(
                database_path,
                id_user=str(CURRENT_SESSION.get("id_user") or ""),
                role=role,
                home_kode_cabang=home,
                is_developer=is_developer,
            )
        except sqlite3.Error as exc:
            print(f"WARNING: Gagal memuat cache branch: {exc}")
            branches = []

    if not branches:
        branches = [{
            "kode_cabang": str(CURRENT_SESSION.get("kode_cabang") or home),
            "nama_cabang": str(CURRENT_SESSION.get("nama_cabang") or home),
            "resi_prefix": str(CURRENT_SESSION.get("resi_prefix") or "INV"),
            "aturan_prefix": dict(CURRENT_SESSION.get("aturan_prefix") or {}),
            "access_mode": _mode_akses_cabang(
                CURRENT_SESSION.get("kode_cabang") or home,
                home_kode_cabang=home,
                role=role,
                is_developer=is_developer,
            ),
        }]

    CURRENT_SESSION["allowed_branches"] = branches
    allowed_codes = {item["kode_cabang"] for item in branches}
    current = str(CURRENT_SESSION.get("kode_cabang") or home).strip().upper()
    if current not in allowed_codes:
        current = home if home in allowed_codes else branches[0]["kode_cabang"]
        aktifkan_cabang_session(current, refresh_access=False)
    else:
        CURRENT_SESSION["active_access_mode"] = _mode_akses_cabang(
            current,
            home_kode_cabang=home,
            role=role,
            is_developer=is_developer,
        )
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
    access_mode = str(target.get("access_mode") or _mode_akses_cabang(kode)).strip().upper()
    CURRENT_SESSION.update({
        "kode_cabang": kode,
        "nama_cabang": str(target.get("nama_cabang") or kode),
        "resi_prefix": str(target.get("resi_prefix") or "INV").strip().upper() or "INV",
        "aturan_prefix": dict(target.get("aturan_prefix") or {}),
        "active_access_mode": access_mode,
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
    db_role_bersih = str(db_role or "ADMIN").strip().upper()
    role_app = ROLE_SUPER_APP if db_role_bersih in {"SUPER", "SUPER_ADMIN"} else ROLE_ADMIN_APP

    CURRENT_SESSION.update({
        "id_user": str(id_user or "").strip(),
        "username": username,
        "nama_lengkap": str(db_nama or username),
        "role": role_app,
        "kode_cabang": kode_home,
        "nama_cabang": nama_home,
        "home_kode_cabang": kode_home,
        "home_nama_cabang": nama_home,
        "resi_prefix": resolved_prefix,
        "aturan_prefix": _parse_prefix_rules(aturan_prefix, resolved_prefix),
        "is_developer": False,
        "is_offline_session": True,
    })
    refresh_akses_cabang_session()
    return str(db_nama or username)


def _verifikasi_login_offline_cache(
    identifier: Any,
    password: Any = "",
) -> Optional[Tuple[bool, str, str]]:
    """Login offline memakai verifier + snapshot akun yang pernah login online.

    Cache ini tidak membuat akun baru. Ia hanya mengizinkan akun yang sebelumnya
    berhasil login online pada mesin ini untuk masuk kembali saat Supabase tidak
    terjangkau.
    """
    ident = str(identifier or "").strip()
    secret = str(password or "")
    if not ident or not secret:
        return None

    try:
        from session_store import load_offline_login_cache
        cached_profile = load_offline_login_cache(ident, secret)
    except Exception:
        cached_profile = None

    if isinstance(cached_profile, dict) and cached_profile.get("id_user"):
        branches = cached_profile.get("allowed_branches") or []
        normalized_branches = []
        for item in branches:
            if not isinstance(item, dict):
                continue
            kode = str(item.get("kode_cabang") or "").strip().upper()
            if not kode:
                continue
            normalized_branches.append({
                "kode_cabang": kode,
                "nama_cabang": str(item.get("nama_cabang") or kode).strip(),
                "resi_prefix": str(item.get("resi_prefix") or "INV").strip().upper() or "INV",
                "aturan_prefix": _parse_prefix_rules(
                    item.get("aturan_prefix"),
                    str(item.get("resi_prefix") or "INV"),
                ),
                "access_mode": str(item.get("access_mode") or BRANCH_ACCESS_FULL).strip().upper(),
            })

        home = str(cached_profile.get("home_kode_cabang") or cached_profile.get("kode_cabang") or "PUSAT").strip().upper()
        current = str(cached_profile.get("kode_cabang") or home).strip().upper()
        if not normalized_branches:
            normalized_branches = [{
                "kode_cabang": current,
                "nama_cabang": str(cached_profile.get("nama_cabang") or current).strip(),
                "resi_prefix": str(cached_profile.get("resi_prefix") or "INV").strip().upper() or "INV",
                "aturan_prefix": _parse_prefix_rules(
                    cached_profile.get("aturan_prefix"),
                    str(cached_profile.get("resi_prefix") or "INV"),
                ),
                "access_mode": BRANCH_ACCESS_FULL,
            }]

        allowed_codes = {item["kode_cabang"] for item in normalized_branches}
        if current not in allowed_codes:
            current = home if home in allowed_codes else normalized_branches[0]["kode_cabang"]

        active = next(item for item in normalized_branches if item["kode_cabang"] == current)
        role = str(cached_profile.get("role") or ROLE_ADMIN_APP).strip().upper()
        CURRENT_SESSION.update({
            "id_user": str(cached_profile.get("id_user") or "").strip(),
            "username": str(cached_profile.get("username") or ident).strip(),
            "nama_lengkap": str(cached_profile.get("nama_lengkap") or ident).strip(),
            "auth_email": "",
            "role": ROLE_SUPER_APP if role in {ROLE_SUPER_APP, ROLE_SUPER_DB} else ROLE_ADMIN_APP,
            "kode_cabang": current,
            "nama_cabang": str(active.get("nama_cabang") or current),
            "home_kode_cabang": home,
            "home_nama_cabang": str(cached_profile.get("home_nama_cabang") or home),
            "allowed_branches": normalized_branches,
            "active_access_mode": str(active.get("access_mode") or BRANCH_ACCESS_FULL),
            "resi_prefix": str(active.get("resi_prefix") or cached_profile.get("resi_prefix") or "INV").strip().upper() or "INV",
            "aturan_prefix": dict(active.get("aturan_prefix") or {}),
            "is_developer": False,
            "is_offline_session": True,
            "db_name": db_aktif,
        })
        return True, CURRENT_SESSION["role"], CURRENT_SESSION["nama_lengkap"]

    # Backward-compatible fallback: cache profil lama yang tersimpan di SQLite.
    try:
        database_path = str(CURRENT_SESSION.get("db_name") or db_aktif)
        candidates = [ident.upper()]
        if "@" in ident:
            local_part = ident.split("@", 1)[0].strip()
            if local_part and local_part.upper() not in candidates:
                candidates.append(local_part.upper())
        with sqlite3.connect(database_path, timeout=5.0) as conn:
            row = None
            for candidate in candidates:
                row = conn.execute(
                    """
                    SELECT
                        u.id_user, u.role, u.nama_lengkap, u.kode_cabang,
                        c.nama_cabang, c.resi_prefix, c.aturan_prefix,
                        COALESCE(u.status_user, 'AKTIF')
                    FROM manajemen_user AS u
                    INNER JOIN data_cabang AS c ON u.kode_cabang = c.kode_cabang
                    WHERE UPPER(u.username) = ?
                    LIMIT 1
                    """,
                    (candidate,),
                ).fetchone()
                if row is not None:
                    break
        if row is None:
            return None
        (id_user, db_role, nama_lengkap, kode_cabang, nama_cabang,
         resi_prefix, aturan_prefix, status_user) = row
        if str(status_user or "AKTIF").strip().upper() != "AKTIF":
            return None
        username = str(ident).strip().upper()
        role = ROLE_SUPER_APP if str(db_role or "ADMIN").strip().upper() in {"SUPER", "SUPER_ADMIN"} else ROLE_ADMIN_APP
        CURRENT_SESSION.update({
            "id_user": str(id_user or "").strip(),
            "username": username,
            "nama_lengkap": str(nama_lengkap or username).strip(),
            "auth_email": "",
            "role": role,
            "kode_cabang": str(kode_cabang or "PUSAT").strip().upper(),
            "nama_cabang": str(nama_cabang or kode_cabang or "PUSAT").strip(),
            "home_kode_cabang": str(kode_cabang or "PUSAT").strip().upper(),
            "home_nama_cabang": str(nama_cabang or kode_cabang or "PUSAT").strip(),
            "resi_prefix": str(resi_prefix or "INV").strip().upper() or "INV",
            "aturan_prefix": _parse_prefix_rules(aturan_prefix, resi_prefix),
            "is_developer": False,
            "is_offline_session": True,
        })
        refresh_akses_cabang_session()
        return True, role, CURRENT_SESSION["nama_lengkap"]
    except sqlite3.Error as exc:
        print(f"INFO: Cache login offline tidak tersedia: {exc}")
        return None


def verifikasi_login_sistem(
    username_input: Any,
    password_input: Any,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Memverifikasi login dan memilih database sesuai mode akun.

    - Email/Supabase -> database_cargo.db (online)
    - DEV_SUPER      -> database_cargo_dev.db (offline sandbox)
    """
    login_identifier = str(username_input or "").strip()
    username = login_identifier.upper()
    password = str(password_input or "").strip()
    if not username or not password:
        return False, None, None

    # Setiap login menentukan target DB lebih dahulu agar pergantian
    # dev_super <-> akun Supabase tidak pernah mewarisi DB sesi sebelumnya.
    if "@" in login_identifier:
        CURRENT_SESSION["db_name"] = db_aktif
        return _verifikasi_login_supabase(
            login_identifier,
            password,
        )

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
        print(f"WARNING: Gagal mencocokkan login ke database: {exc}")
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
        print(f"INFO: Database belum siap, menggunakan pengaturan default: {exc}")
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