# session_store.py
"""Penyimpanan kredensial sesi terakhir secara lokal.

Tujuan modul ini hanya agar aplikasi dapat masuk kembali ke akun terakhir
setelah aplikasi ditutup. Data disimpan sebagai blob terenkripsi yang terikat
pada profil mesin/user Windows (dengan fallback lokal terenkripsi pada sistem
lain). Tombol Logout menghapus blob ini secara eksplisit.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import getpass
import hmac
from typing import Optional, Dict

from PySide6.QtCore import QSettings
from cryptography.fernet import Fernet, InvalidToken

try:
    from utils.typography import ORGANIZATION_NAME, APPLICATION_NAME
except Exception:
    ORGANIZATION_NAME = "KargoApp"
    APPLICATION_NAME = "Kargo"

_SETTINGS_GROUP = "Session"
_SETTINGS_KEY = "last_login"
_LAST_LOGIN_DPAPI_PREFIX = "dpapi:v1:"
_LAST_LOGIN_FERNET_PREFIX = "fernet:v1:"

_OFFLINE_AUTH_GROUP = "OfflineAuthV1"
_OFFLINE_AUTH_KEY = "accounts"
_OFFLINE_KDF_ITERATIONS = 310_000


def _normalize_identifier(identifier: str) -> str:
    return str(identifier or "").strip().casefold()


def _record_matches_identifier(record: dict, identifier: str) -> bool:
    """Cocokkan akun cache melalui identifier utama atau alias profil."""
    target = _normalize_identifier(identifier)
    if not target or not isinstance(record, dict):
        return False
    # Hanya cocokkan target terhadap identitas yang benar-benar tersimpan.
    # Jangan memasukkan ``target`` sendiri ke candidates: itu akan membuat
    # setiap identifier yang tidak dikenal cocok dengan record pertama.
    candidates = {
        _normalize_identifier(record.get("identifier")),
    }
    profile = record.get("profile")
    if isinstance(profile, dict):
        candidates.update({
            _normalize_identifier(profile.get("username")),
            _normalize_identifier(profile.get("auth_email")),
        })
    return target in {item for item in candidates if item}


def _find_offline_record(accounts: dict, identifier: str) -> tuple[str | None, dict | None]:
    """Cari record cache akun berdasarkan email/username/alias."""
    target = _normalize_identifier(identifier)
    if not target:
        return None, None
    direct = accounts.get(target)
    if isinstance(direct, dict):
        return target, direct
    for key, record in accounts.items():
        if isinstance(record, dict) and _record_matches_identifier(record, identifier):
            return key, record
    return None, None


def _load_offline_accounts() -> dict:
    settings = _settings()
    settings.beginGroup(_OFFLINE_AUTH_GROUP)
    token = str(settings.value(_OFFLINE_AUTH_KEY, "") or "").strip()
    settings.endGroup()
    if not token:
        return {}
    try:
        payload = _fernet().decrypt(token.encode("ascii"))
        data = json.loads(payload.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        # Cache rusak tidak boleh menghalangi login normal.
        _clear_offline_accounts()
        return {}


def _save_offline_accounts(accounts: dict) -> None:
    settings = _settings()
    settings.beginGroup(_OFFLINE_AUTH_GROUP)
    if not accounts:
        settings.remove(_OFFLINE_AUTH_KEY)
    else:
        payload = json.dumps(accounts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        token = _fernet().encrypt(payload).decode("ascii")
        settings.setValue(_OFFLINE_AUTH_KEY, token)
    settings.endGroup()
    settings.sync()


def _clear_offline_accounts() -> None:
    settings = _settings()
    settings.beginGroup(_OFFLINE_AUTH_GROUP)
    settings.remove(_OFFLINE_AUTH_KEY)
    settings.endGroup()
    settings.sync()


def save_offline_login_cache(
    identifier: str,
    password: str,
    metadata: dict | None = None,
) -> None:
    """Simpan verifier password + snapshot profil untuk login offline.

    Password asli tidak disimpan. Yang disimpan adalah PBKDF2-HMAC-SHA256
    verifier, seluruh blob dienkripsi dengan key yang terikat ke mesin/user.
    Snapshot profil dipakai untuk membentuk CURRENT_SESSION tanpa koneksi
    Supabase; data operasional tetap tersimpan di database lokal.
    """
    ident = _normalize_identifier(identifier)
    secret = str(password or "")
    if not ident or not secret:
        return

    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        salt,
        _OFFLINE_KDF_ITERATIONS,
    )
    accounts = _load_offline_accounts()
    previous = accounts.get(ident) if isinstance(accounts.get(ident), dict) else {}
    record = {
        "identifier": ident,
        "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
        "digest": base64.urlsafe_b64encode(digest).decode("ascii"),
        "iterations": _OFFLINE_KDF_ITERATIONS,
    }
    if isinstance(previous, dict) and isinstance(previous.get("profile"), dict):
        record["profile"] = dict(previous["profile"])
    if isinstance(metadata, dict):
        record["profile"] = dict(metadata)
    accounts[ident] = record
    _save_offline_accounts(accounts)


def update_offline_login_profile(identifier: str, metadata: dict | None) -> bool:
    """Perbarui snapshot profil cache tanpa menghitung ulang verifier password.

    Dipakai saat restore sesi setelah login online berhasil: kredensial tersimpan
    yang sama sudah diverifikasi oleh Supabase, sehingga PBKDF2 310.000 iterasi
    tidak perlu diulang hanya untuk menyegarkan metadata profil lokal.
    False berarti record tidak ada/tidak valid dan caller boleh memakai jalur
    penyimpanan lengkap sebagai fallback.
    """
    ident = _normalize_identifier(identifier)
    if not ident or not isinstance(metadata, dict):
        return False

    accounts = _load_offline_accounts()
    key, record = _find_offline_record(accounts, identifier)
    if key is None or not isinstance(record, dict):
        return False

    # Pastikan verifier lama valid sebelum mempertahankan record tersebut.
    if not record.get("salt") or not record.get("digest"):
        return False

    if record.get("profile") == metadata:
        # Hindari tulis QSettings jika snapshot tidak berubah.
        return True

    updated_record = dict(record)
    updated_record["profile"] = dict(metadata)
    accounts[key] = updated_record
    _save_offline_accounts(accounts)
    return True


def verify_offline_login_cache(identifier: str, password: str) -> bool:
    """Verifikasi password terhadap cache offline akun terkait."""
    ident = _normalize_identifier(identifier)
    secret = str(password or "")
    if not ident or not secret:
        return False
    _, record = _find_offline_record(_load_offline_accounts(), identifier)
    if not isinstance(record, dict):
        return False
    try:
        salt = base64.urlsafe_b64decode(str(record.get("salt") or "").encode("ascii"))
        expected = base64.urlsafe_b64decode(str(record.get("digest") or "").encode("ascii"))
        iterations = int(record.get("iterations") or _OFFLINE_KDF_ITERATIONS)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, base64.binascii.Error):
        return False


def load_offline_login_cache(identifier: str, password: str) -> dict | None:
    """Ambil snapshot profil akun setelah verifier password lolos."""
    if not verify_offline_login_cache(identifier, password):
        return None
    _, record = _find_offline_record(_load_offline_accounts(), identifier)
    if not isinstance(record, dict):
        return None
    profile = record.get("profile")
    return dict(profile) if isinstance(profile, dict) else {}


def clear_offline_login_cache(identifier: str | None = None) -> None:
    """Hapus cache offline satu akun atau semua akun secara eksplisit."""
    if identifier is None:
        _clear_offline_accounts()
        return
    ident = _normalize_identifier(identifier)
    accounts = _load_offline_accounts()
    key, _ = _find_offline_record(accounts, identifier)
    if key is not None:
        accounts.pop(key, None)
        _save_offline_accounts(accounts)


def _machine_key() -> bytes:
    """Bangun key lokal deterministik untuk blob cache login offline lama."""
    material = "|".join(
        (
            platform.node(),
            getpass.getuser(),
            os.environ.get("USERNAME", ""),
            os.environ.get("COMPUTERNAME", ""),
            str(getattr(__import__("uuid"), "getnode")()),
            ORGANIZATION_NAME,
            APPLICATION_NAME,
        )
    ).encode("utf-8", "ignore")
    digest = hashlib.sha256(material).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_machine_key())


def _settings() -> QSettings:
    return QSettings(ORGANIZATION_NAME, APPLICATION_NAME)


def _is_windows() -> bool:
    """True bila aplikasi berjalan di Windows."""
    return os.name == "nt"


def _dpapi_crypt(data: bytes, *, decrypt: bool) -> bytes:
    """Lindungi/buka blob dengan Windows DPAPI pada akun Windows saat ini.

    DPAPI mengikat data ke profil pengguna Windows. Tidak memakai flag
    LOCAL_MACHINE, sehingga akun Windows lain tidak otomatis dapat membukanya.
    Fungsi ini sengaja tidak menyediakan fallback kriptografi yang lebih lemah
    ketika DPAPI gagal pada Windows.
    """
    if not _is_windows():
        raise RuntimeError("Windows DPAPI hanya tersedia pada Windows.")

    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("Data DPAPI harus berupa bytes.")
    raw = bytes(data)
    if not raw:
        raise ValueError("Data DPAPI tidak boleh kosong.")

    input_buffer = ctypes.create_string_buffer(raw, len(raw))
    input_blob = DATA_BLOB(
        len(raw),
        ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    output_blob = DATA_BLOB()

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    local_free = kernel32.LocalFree
    local_free.argtypes = [wintypes.HLOCAL]
    local_free.restype = wintypes.HLOCAL

    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    description = wintypes.LPWSTR()

    if decrypt:
        function = crypt32.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(DATA_BLOB),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(DATA_BLOB),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(DATA_BLOB),
        ]
        function.restype = wintypes.BOOL
        ok = function(
            ctypes.byref(input_blob),
            ctypes.byref(description),
            None,
            None,
            None,
            flags,
            ctypes.byref(output_blob),
        )
    else:
        function = crypt32.CryptProtectData
        function.argtypes = [
            ctypes.POINTER(DATA_BLOB),
            wintypes.LPCWSTR,
            ctypes.POINTER(DATA_BLOB),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(DATA_BLOB),
        ]
        function.restype = wintypes.BOOL
        ok = function(
            ctypes.byref(input_blob),
            "Kargo saved login",
            None,
            None,
            None,
            flags,
            ctypes.byref(output_blob),
        )

    try:
        if not ok:
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "Windows DPAPI gagal memproses kredensial.")
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        if output_blob.pbData:
            local_free(ctypes.cast(output_blob.pbData, wintypes.HLOCAL))
        if decrypt and description:
            local_free(ctypes.cast(description, wintypes.HLOCAL))


def _protect_last_login(payload: bytes) -> str:
    """Buat token sesi terakhir dengan DPAPI di Windows."""
    if _is_windows():
        protected = _dpapi_crypt(payload, decrypt=False)
        encoded = base64.urlsafe_b64encode(protected).decode("ascii")
        return _LAST_LOGIN_DPAPI_PREFIX + encoded

    # Fallback untuk pengembangan/non-Windows agar perilaku lintas platform
    # tetap kompatibel. Build produksi Kargo di Windows selalu memakai DPAPI.
    encrypted = _fernet().encrypt(payload).decode("ascii")
    return _LAST_LOGIN_FERNET_PREFIX + encrypted


def _unprotect_last_login(token: str) -> tuple[bytes, bool]:
    """Kembalikan payload dan flag apakah token memakai format lama."""
    if token.startswith(_LAST_LOGIN_DPAPI_PREFIX):
        if not _is_windows():
            # Jangan hapus blob DPAPI hanya karena sedang dibaca di OS lain.
            raise RuntimeError("Kredensial sesi ini hanya dapat dibuka di Windows.")
        encoded = token[len(_LAST_LOGIN_DPAPI_PREFIX):]
        protected = base64.urlsafe_b64decode(encoded.encode("ascii"))
        return _dpapi_crypt(protected, decrypt=True), False

    if token.startswith(_LAST_LOGIN_FERNET_PREFIX):
        encrypted = token[len(_LAST_LOGIN_FERNET_PREFIX):]
    else:
        # Format Fernet tanpa prefix adalah format versi aplikasi sebelumnya.
        encrypted = token
    payload = _fernet().decrypt(encrypted.encode("ascii"))
    return payload, True


def save_last_login(identifier: str, password: str) -> None:
    """Simpan kredensial sesi; DPAPI user-scope dipakai pada Windows.

    Kegagalan DPAPI tidak menggagalkan login aplikasi, tetapi auto-login tidak
    disimpan. Pada Windows tidak ada downgrade diam-diam ke key buatan sendiri.
    """
    identifier = str(identifier or "").strip()
    password = str(password or "")
    if not identifier or not password:
        return

    payload = json.dumps(
        {"identifier": identifier, "password": password},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    try:
        token = _protect_last_login(payload)
    except Exception as exc:
        # Jangan meninggalkan credential lama dengan proteksi yang lebih lemah.
        clear_last_login()
        print(
            "[SESSION] Auto-login tidak disimpan karena proteksi kredensial "
            f"gagal: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return

    settings = _settings()
    settings.beginGroup(_SETTINGS_GROUP)
    settings.setValue(_SETTINGS_KEY, token)
    settings.endGroup()
    settings.sync()


def load_last_login() -> Optional[Dict[str, str]]:
    """Ambil sesi terakhir; token lama dimigrasikan ke proteksi terbaru."""
    settings = _settings()
    settings.beginGroup(_SETTINGS_GROUP)
    token = str(settings.value(_SETTINGS_KEY, "") or "").strip()
    settings.endGroup()
    if not token:
        return None

    try:
        payload, is_legacy = _unprotect_last_login(token)
        data = json.loads(payload.decode("utf-8"))
    except RuntimeError as exc:
        # Contoh: blob DPAPI dibuka pada OS non-Windows. Pertahankan nilai agar
        # tidak terhapus hanya karena aplikasi dijalankan pada OS berbeda.
        if token.startswith(_LAST_LOGIN_DPAPI_PREFIX) and not _is_windows():
            return None
        clear_last_login()
        print(f"[SESSION] Kredensial sesi tidak dapat dibuka: {exc}", flush=True)
        return None
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        clear_last_login()
        return None
    except OSError as exc:
        clear_last_login()
        print(
            "[SESSION] DPAPI tidak dapat membuka kredensial sesi: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None

    if not isinstance(data, dict):
        clear_last_login()
        return None
    identifier = str(data.get("identifier") or "").strip()
    password = str(data.get("password") or "")
    if not identifier or not password:
        clear_last_login()
        return None

    # Migrasi otomatis token Fernet lama. Login yang tersimpan tetap dapat
    # dipakai sekali, lalu ditulis ulang dengan DPAPI pada Windows.
    if is_legacy:
        save_last_login(identifier, password)

    return {"identifier": identifier, "password": password}


def clear_last_login() -> None:
    """Hapus sesi login tersimpan; dipanggil oleh Logout."""
    settings = _settings()
    settings.beginGroup(_SETTINGS_GROUP)
    settings.remove(_SETTINGS_KEY)
    settings.endGroup()
    settings.sync()
