"""Server ORM model."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.port_allocation import PortAllocation


class ServerStatus(str, enum.Enum):
    CREATED = "created"
    INSTALLING = "installing"
    UPDATING = "updating"
    RUNNING = "running"
    STOPPED = "stopped"
    ERRORED = "errored"


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    template_id: Mapped[str] = mapped_column(String(64))
    app_id: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(16), default=ServerStatus.CREATED.value)

    # Resolved variable values (key -> value), including any generated secrets.
    variables: Mapped[dict] = mapped_column(JSON, default=dict)
    # Startup command template copied from the game template at create time so
    # later edits to the template file don't silently change existing servers.
    startup_template: Mapped[str] = mapped_column(Text)

    anonymous_login: Mapped[bool] = mapped_column(Boolean, default=True)
    update_on_start: Mapped[bool] = mapped_column(Boolean, default=True)

    container_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Encrypted Steam credentials (Phase 8). Fernet token; never stored plain.
    steam_credentials_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    max_backups: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Steam beta branch to install/update from (steamcmd `-beta <name>`);
    # NULL = the public default branch.
    steam_branch: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # User order/toggles of game maps provided by workshop mods, e.g.
    # [{"name": "RavenCreek", "enabled": true}, ...]; NULL = mod order.
    map_order: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Steam Workshop content app id, copied from the template at create time when
    # the game is workshop-capable; NULL means workshop is not supported (the UI
    # hides the Workshop tab).
    workshop_app_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # How installed workshop mods are kept current: disabled | 15min | daily | weekly | startup.
    workshop_auto_update: Mapped[str] = mapped_column(
        String(16), default="disabled", server_default="disabled"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ports: Mapped[list[PortAllocation]] = relationship(
        back_populates="server", cascade="all, delete-orphan", lazy="selectin"
    )
