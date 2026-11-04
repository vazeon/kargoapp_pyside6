# supabase_client.py

import os
import threading

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")

# Batas waktu request PostgREST agar worker sync tidak menunggu jaringan
# bermasalah terlalu lama. Nilai dapat dioverride tanpa mengubah source code.
try:
    SUPABASE_REST_TIMEOUT_SECONDS = max(
        3.0,
        min(30.0, float(os.getenv("KARGO_SUPABASE_REST_TIMEOUT", "10"))),
    )
except (TypeError, ValueError):
    SUPABASE_REST_TIMEOUT_SECONDS = 10.0


class DeveloperSupabaseAccessBlocked(RuntimeError):
    """Raised if code tries to access Supabase during a DEV_SUPER session."""

    pass


class _LazySupabaseClient:
    """Create the actual Supabase client only when needed."""

    def __init__(self):
        self._client = None
        self._lock = threading.Lock()

    @staticmethod
    def _assert_not_developer_session() -> None:
        # Import locally to avoid a config <-> supabase_client import cycle.
        try:
            from config import CURRENT_SESSION
        except (ImportError, AttributeError):
            # config may still be initializing during application startup.
            return

        if bool(CURRENT_SESSION.get("is_developer")):
            raise DeveloperSupabaseAccessBlocked(
                "Akses Supabase dinonaktifkan selama sesi DEV_SUPER. "
                "Gunakan database sandbox lokal."
            )

    def _get_client(self):
        self._assert_not_developer_session()

        if self._client is not None:
            return self._client

        with self._lock:
            # Recheck inside the lock in case the active session changed.
            self._assert_not_developer_session()
            if self._client is None:
                if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
                    raise RuntimeError(
                        "SUPABASE_URL dan SUPABASE_PUBLISHABLE_KEY "
                        "belum dikonfigurasi."
                    )

                from supabase import create_client

                # ClientOptions pada versi supabase-py yang mendukungnya
                # memberi timeout eksplisit pada request PostgREST. Fallback
                # mempertahankan kompatibilitas dengan versi SDK lama yang
                # belum menyediakan opsi ini.
                options = None
                try:
                    try:
                        from supabase.client import ClientOptions
                    except ImportError:
                        from supabase import ClientOptions
                    options = ClientOptions(
                        postgrest_client_timeout=SUPABASE_REST_TIMEOUT_SECONDS,
                    )
                except (ImportError, TypeError, AttributeError):
                    options = None

                if options is not None:
                    try:
                        self._client = create_client(
                            SUPABASE_URL,
                            SUPABASE_PUBLISHABLE_KEY,
                            options=options,
                        )
                    except (TypeError, AttributeError) as exc:
                        # Jangan gagalkan startup bila versi SDK yang terpasang
                        # memiliki perbedaan pada ClientOptions.
                        print(
                            "[SUPABASE] Timeout khusus tidak didukung SDK ini; "
                            f"menggunakan konfigurasi default ({type(exc).__name__}).",
                            flush=True,
                        )
                        self._client = create_client(
                            SUPABASE_URL,
                            SUPABASE_PUBLISHABLE_KEY,
                        )
                else:
                    self._client = create_client(
                        SUPABASE_URL,
                        SUPABASE_PUBLISHABLE_KEY,
                    )

        return self._client

    def __getattr__(self, name):
        # Central guard: an accidental Supabase access in developer mode
        # is blocked before the actual client can make a request.
        return getattr(self._get_client(), name)


supabase = _LazySupabaseClient()
