"""Request/response schemas for notifications."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    level: str
    title: str
    message: str | None
    server_id: str | None
    read: bool
    created_at: datetime
    # Resolved by the router for display.
    server_name: str | None = None


class UnreadCount(BaseModel):
    count: int
