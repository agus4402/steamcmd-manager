"""Notification center endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.notification import NotificationOut, UnreadCount
from app.services import notification_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _to_out(notif) -> NotificationOut:
    out = NotificationOut.model_validate(notif)
    out.server_name = notif.server.name if notif.server else None
    return out


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = False, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> list[NotificationOut]:
    rows = await notification_service.list_notifications(
        db, unread_only=unread_only, limit=min(limit, 200)
    )
    return [_to_out(n) for n in rows]


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(db: AsyncSession = Depends(get_db)) -> UnreadCount:
    return UnreadCount(count=await notification_service.unread_count(db))


@router.post("/read-all", response_model=UnreadCount)
async def mark_all_read(db: AsyncSession = Depends(get_db)) -> UnreadCount:
    marked = await notification_service.mark_all_read(db)
    return UnreadCount(count=marked)


@router.post("/{notif_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notif_id: str, db: AsyncSession = Depends(get_db)) -> None:
    notif = await notification_service.get(db, notif_id)
    if notif is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
    await notification_service.mark_read(db, notif)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all(db: AsyncSession = Depends(get_db)) -> None:
    await notification_service.clear_all(db)


@router.delete("/{notif_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(notif_id: str, db: AsyncSession = Depends(get_db)) -> None:
    notif = await notification_service.get(db, notif_id)
    if notif is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
    await notification_service.delete(db, notif)
