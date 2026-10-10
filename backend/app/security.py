"""API-key authentication."""
from __future__ import annotations

import hmac
import logging

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import DEV_API_KEY, get_settings

log = logging.getLogger(__name__)
_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str = Security(_header)) -> str:
    if not key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header")
    if not any(hmac.compare_digest(key, k) for k in get_settings().api_key_list):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid API key")
    return key


def warn_if_insecure() -> None:
    s = get_settings()
    if s.environment == "production" and DEV_API_KEY in s.api_key_list:
        log.warning("Running in production with the default development API key. Set AOBS_API_KEYS.")
