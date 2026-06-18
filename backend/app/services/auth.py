"""Panel authentication: password hashing + JWT (single-tenant admin)."""

from __future__ import annotations

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
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str | None:
    """Return the username (sub) if the token is valid, else None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


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
