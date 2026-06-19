"""Port allocation ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.server import Server


class PortAllocation(Base):
    __tablename__ = "port_allocations"
    __table_args__ = (
        # A host port can be shared across protocols (tcp+udp) but never reused
        # for the same protocol by another server.
        UniqueConstraint("host_port", "protocol", name="uq_hostport_protocol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(32))  # template port name, e.g. "game"
    protocol: Mapped[str] = mapped_column(String(3))  # "tcp" | "udp"
    # We bind the same number inside the container and on the host to avoid UDP
    # port-translation problems (the #1 game-server failure mode).
    host_port: Mapped[int] = mapped_column(Integer, index=True)
    # The base port of a consecutive block is "primary" and the only one exposed
    # as the {{PORT_<name>}} placeholder; extra ports (port+1, ...) are published
    # to Docker but never referenced directly in the startup command.
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    server: Mapped[Server] = relationship(back_populates="ports")
