"""A game-level mod contained in a downloaded workshop item.

One Steam Workshop item can ship several mods (e.g. Project Zomboid: the mod
plus optional addons, each with its own mod id). These rows are discovered by
inspecting the downloaded files and let the user toggle each mod id and set the
load order, which is what the game's config (e.g. PZ `Mods=`) receives.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class WorkshopSubmod(Base):
    __tablename__ = "workshop_submods"
    __table_args__ = (
        UniqueConstraint("server_id", "mod_id", name="uq_workshop_submod_server_mod"),
    )

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    # The workshop item this mod was found in (deleted with it).
    workshop_mod_id: Mapped[str] = mapped_column(
        ForeignKey("workshop_mods.id", ondelete="CASCADE"), index=True
    )
    mod_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Folder inside the item (e.g. "mods/Serving plates Build42").
    folder: Mapped[str] = mapped_column(String(512))
    # Mod ids this one requires (from mod.info `require=`).
    requires: Mapped[list] = mapped_column(JSON, default=list)
    # Map folder names this mod adds (for the game's map list).
    maps: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    load_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
