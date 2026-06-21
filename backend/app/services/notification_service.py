"""In-app notification service.

``notify`` is the fire-and-forget entry point other services call to record an
event. It opens its own DB session (so it's independent of the caller's
transaction) and never raises — a failure to record a notification must never
break the operation that triggered it.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models.notification import Notification

logger = logging.getLogger("steamcmd-manager.notifications")

LEVELS = {"info", "success", "warning", "error"}


async def notify(
    level: str, title: str, message: str | None = None, server_id: str | None = None
) -> None:
    """Record a notification. Safe to await from anywhere; never raises."""
    try:
        async with SessionLocal() as session:
            session.add(
                Notification(
                    level=level if level in LEVELS else "info",
                    title=title[:255],
                    message=message,
                    server_id=server_id,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 — recording a notification must never break callers
        logger.exception("failed to emit notification: %s", title)


async def list_notifications(
    session: AsyncSession, *, unread_only: bool = False, limit: int = 100
) -> list[Notification]:
    stmt = select(Notification)
    if unread_only:
        stmt = stmt.where(Notification.read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def unread_count(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count()).select_from(Notification).where(Notification.read.is_(False))
    )
    return int(result.scalar_one())


async def get(session: AsyncSession, notif_id: str) -> Notification | None:
    return await session.get(Notification, notif_id)


async def mark_read(session: AsyncSession, notif: Notification) -> None:
    notif.read = True
    await session.commit()


async def mark_all_read(session: AsyncSession) -> int:
    result = await session.execute(
        update(Notification).where(Notification.read.is_(False)).values(read=True)
    )
    await session.commit()
    return result.rowcount or 0


async def delete(session: AsyncSession, notif: Notification) -> None:
    await session.delete(notif)
    await session.commit()


async def clear_all(session: AsyncSession) -> int:
    from sqlalchemy import delete as sa_delete

    result = await session.execute(sa_delete(Notification))
    await session.commit()
    return result.rowcount or 0
