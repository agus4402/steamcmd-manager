"""Workshop mod ORM model — a Steam Workshop item installed on a server.

Each row tracks one workshop item downloaded (via steamcmd) into a server's data
volume. The download runs as a background job, so ``status`` moves
installing -> installed | error and the UI polls it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.server import Server


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class WorkshopMod(Base):
    __tablename__ = "workshop_mods"
    __table_args__ = (
        UniqueConstraint("server_id", "item_id", name="uq_workshop_server_item"),
    )

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    server_id: Mapped[str] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True
    )
    # Mod source ("steam" today; CurseForge/Mod.io/Nexus later).
    provider: Mapped[str] = mapped_column(String(16), default="steam")
    # Workshop item id (numeric string for Steam).
    item_id: Mapped[str] = mapped_column(String(20))
    # User-supplied label; falls back to the fetched title.
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # queued | downloading | installing | installed | update_available | error | missing_dependency
    status: Mapped[str] = mapped_column(String(20), default="queued")
    size: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cached metadata (best-effort, refreshed on add / sync / update checks).
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscribers: Mapped[int] = mapped_column(Integer, default=0)
    favorites: Mapped[int] = mapped_column(Integer, default=0)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    # Remote last-updated time vs. the time captured at last successful download;
    # a newer remote time means an update is available.
    time_updated_remote: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    installed_time_updated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Dependency tracking: auto-added deps and the item that required them.
    is_dependency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    required_by: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    server: Mapped[Server] = relationship(lazy="selectin")
