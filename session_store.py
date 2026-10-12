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
    candidates = {
        target,
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
    """Bangun key lokal deterministik untuk mengenkripsi sesi terakhir."""
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


def save_last_login(identifier: str, password: str) -> None:
    """Simpan identifier + password sesi terakhir secara terenkripsi."""
    identifier = str(identifier or "").strip()
    password = str(password or "")
    if not identifier or not password:
        return

    payload = json.dumps(
        {"identifier": identifier, "password": password},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    token = _fernet().encrypt(payload).decode("ascii")

    settings = _settings()
    settings.beginGroup(_SETTINGS_GROUP)
    settings.setValue(_SETTINGS_KEY, token)
    settings.endGroup()
    settings.sync()


def load_last_login() -> Optional[Dict[str, str]]:
    """Ambil sesi terakhir yang tersimpan; None bila tidak ada/tidak valid."""
    settings = _settings()
    settings.beginGroup(_SETTINGS_GROUP)
    token = str(settings.value(_SETTINGS_KEY, "") or "").strip()
    settings.endGroup()
    if not token:
        return None

    try:
        payload = _fernet().decrypt(token.encode("ascii"))
        data = json.loads(payload.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        clear_last_login()
        return None

    if not isinstance(data, dict):
        clear_last_login()
        return None
    identifier = str(data.get("identifier") or "").strip()
    password = str(data.get("password") or "")
    if not identifier or not password:
        clear_last_login()
        return None
    return {"identifier": identifier, "password": password}


def clear_last_login() -> None:
    """Hapus sesi login tersimpan; dipanggil oleh Logout."""
    settings = _settings()
    settings.beginGroup(_SETTINGS_GROUP)
    settings.remove(_SETTINGS_KEY)
    settings.endGroup()
    settings.sync()
