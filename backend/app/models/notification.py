"""Notification ORM model — in-app alerts surfaced in the notification center.

A notification records a noteworthy event (a crash, a failed install/backup, a
completed long-running job, ...). It optionally links to the server it concerns;
the link is nulled out (not cascaded) if that server is later deleted so the
historical record survives.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.server import Server


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    # info | success | warning | error
    level: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Keep the notification if its server is deleted (null the link, don't cascade).
    server_id: Mapped[str | None] = mapped_column(
        ForeignKey("servers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    server: Mapped[Server | None] = relationship(lazy="selectin")
