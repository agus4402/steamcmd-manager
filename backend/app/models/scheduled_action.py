"""Scheduled action ORM model — cron-driven automation for a server.

Each row is one recurring task (start/stop/restart/update/backup) for a server,
expressed as a 5-field crontab. The APScheduler engine in ``scheduler_service``
loads enabled rows on boot and fires them; outcomes are written back here.
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


class ScheduledAction(Base):
    __tablename__ = "scheduled_actions"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    server_id: Mapped[str] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True
    )
    # One of: start | stop | restart | update | backup
    action: Mapped[str] = mapped_column(String(16))
    # 5-field crontab expression (UTC), e.g. "0 4 * * *".
    cron: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ok | error
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    server: Mapped[Server] = relationship(lazy="selectin")
