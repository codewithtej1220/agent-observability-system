"""Encryption for stored provider API keys.

Keys are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) under the server
secret AOBS_SECRET_KEY. Plaintext keys never leave the server: the API only
ever returns a short hint (last 4 characters).

Rotation: put the new key first and old keys after it, comma-separated, in
AOBS_SECRET_KEY. New values are encrypted with the first key; any listed key
can decrypt. Re-save credentials to move them to the new key.

In development, if AOBS_SECRET_KEY is unset, a key is generated once and
stored in backend/data/secret.key. Production refuses to start without one.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from .config import BACKEND_DIR, get_settings

log = logging.getLogger(__name__)
DEV_KEY_FILE = BACKEND_DIR / "data" / "secret.key"


def _dev_key() -> str:
    if DEV_KEY_FILE.exists():
        return DEV_KEY_FILE.read_text(encoding="utf-8").strip()
    DEV_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key().decode()
    DEV_KEY_FILE.write_text(key, encoding="utf-8")
    try:
        os.chmod(DEV_KEY_FILE, 0o600)
    except OSError:
        pass
    log.warning("Generated a development encryption key at %s. Set AOBS_SECRET_KEY in production.", DEV_KEY_FILE)
    return key


@lru_cache
def _fernet() -> MultiFernet:
    s = get_settings()
    raw = s.secret_key
    if not raw:
        if s.environment == "production":
            raise RuntimeError("AOBS_SECRET_KEY must be set in production (generate with "
                               "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`)")
        raw = _dev_key()
    return MultiFernet([Fernet(k.strip().encode()) for k in raw.split(",") if k.strip()])


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise RuntimeError("Stored credential cannot be decrypted; was AOBS_SECRET_KEY changed?") from e


def hint(secret: str) -> str:
    return f"…{secret[-4:]}" if len(secret) >= 8 else "…"


def check_ready() -> None:
    """Fail fast at startup if encryption is misconfigured."""
    decrypt(encrypt("ok"))

