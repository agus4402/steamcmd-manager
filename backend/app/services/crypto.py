"""Symmetric encryption for Steam credentials at rest (Fernet).

The Fernet key is derived from PANEL_SECRET so operators only manage one secret.
Credentials are decrypted only in-memory when invoking steamcmd and are never
written to logs.
"""

from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    secret = get_settings().panel_secret.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_credentials(data: dict[str, str]) -> str:
    token = _fernet().encrypt(json.dumps(data).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_credentials(token: str) -> dict[str, str]:
    try:
        raw = _fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:  # noqa: BLE001
        raise ValueError("could not decrypt credentials (wrong PANEL_SECRET?)") from exc
    return json.loads(raw.decode("utf-8"))
