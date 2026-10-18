"""Panel authentication: password hashing + JWT (single-tenant admin).

Two token scopes share the same signing key:
- ``admin``: the panel user (full API).
- ``server``: the public control page of ONE server, obtained with that
  server's SERVER_PASSWORD; only valid on ``/api/control/{server_id}``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

logger = logging.getLogger("steamcmd-manager.auth")
settings = get_settings()

# pbkdf2_sha256 is pure-python (no native bcrypt build / version pitfalls).
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": username, "scope": "admin", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str | None:
    """Return the username (sub) if this is a valid ADMIN token, else None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    # Tokens issued before scopes existed have none: they are admin tokens.
    if payload.get("scope", "admin") != "admin":
        return None
    return payload.get("sub")


# -- server control page tokens ----------------------------------------------

SERVER_TOKEN_MINUTES = 12 * 60


def _password_fingerprint(password: str) -> str:
    """Keyed hash of the server password, embedded in its control tokens so a
    password change invalidates every session issued with the old one."""
    digest = hmac.new(settings.jwt_secret.encode(), password.encode(), hashlib.sha256)
    return digest.hexdigest()[:16]


def create_server_token(server_id: str, password: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=SERVER_TOKEN_MINUTES)
    payload = {
        "sub": f"server:{server_id}",
        "scope": "server",
        "sid": server_id,
        "pwh": _password_fingerprint(password),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_server_token(token: str, server_id: str, current_password: str) -> bool:
    """True if ``token`` is a control token for this server, issued with its
    current (non-empty) password."""
    if not current_password:
        return False
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return False
    return (
        payload.get("scope") == "server"
        and payload.get("sid") == server_id
        and hmac.compare_digest(
            str(payload.get("pwh", "")), _password_fingerprint(current_password)
        )
    )


def check_server_password(provided: str, current_password: str) -> bool:
    """Constant-time compare; an empty server password never matches."""
    return bool(current_password) and hmac.compare_digest(
        provided.encode(), current_password.encode()
    )


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


async def seed_admin(session: AsyncSession) -> None:
    """Create the configured admin user on first boot if it doesn't exist."""
    result = await session.execute(select(User).where(User.username == settings.admin_user))
    if result.scalar_one_or_none() is not None:
        return
    session.add(
        User(username=settings.admin_user, password_hash=hash_password(settings.admin_password))
    )
    await session.commit()
    logger.info("seeded admin user '%s'", settings.admin_user)
