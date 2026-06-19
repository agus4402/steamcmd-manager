"""Integration ORM models — extensible external-service connections.

An ``Integration`` is one link between the panel and an external provider
(Playit, Cloudflare, Discord, ...). Secrets live in a separate 1:1
``integration_credentials`` row (Fernet token) so tokens are isolated from the
display record. Tunnel-capable providers track their tunnels in
``integration_tunnels``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
    pass


class IntegrationStatus(str, enum.Enum):
    NOT_CONNECTED = "not_connected"
    PENDING = "pending"
    CONNECTED = "connected"
    ERROR = "error"


class TunnelStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class Integration(Base):
    __tablename__ = "integrations"
    # One connection per provider per user (user_id is nullable for the current
    # single-tenant deployment; the constraint still prevents duplicate links).
    __table_args__ = (
        UniqueConstraint("provider", "user_id", name="uq_integration_provider_user"),
    )

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    # Nullable FK for forward-compat with multi-user; global for now.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=IntegrationStatus.NOT_CONNECTED.value
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Human-readable account identifier for display (e.g. Playit account/email).
    account_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    credentials: Mapped["IntegrationCredential | None"] = relationship(
        back_populates="integration",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    tunnels: Mapped[list["IntegrationTunnel"]] = relationship(
        back_populates="integration", cascade="all, delete-orphan", lazy="selectin"
    )


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"

    integration_id: Mapped[str] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), primary_key=True
    )
    # Fernet token over a JSON dict; never stored or logged in plaintext.
    encrypted_credentials: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    integration: Mapped[Integration] = relationship(back_populates="credentials")


class IntegrationTunnel(Base):
    __tablename__ = "integration_tunnels"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    integration_id: Mapped[str] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), index=True
    )
    # Tunnels may outlive their server; null out the link rather than cascade.
    server_id: Mapped[str | None] = mapped_column(
        ForeignKey("servers.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128))
    remote_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    local_port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(8), default="tcp")
    # Provider-side identifier used to reconcile against the upstream service.
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=TunnelStatus.PENDING.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    integration: Mapped[Integration] = relationship(back_populates="tunnels")
