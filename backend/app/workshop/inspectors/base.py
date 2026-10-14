"""Shared types for workshop item inspectors (game-specific mod discovery)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SubmodInfo:
    """One game-level mod found inside a downloaded workshop item."""

    mod_id: str
    name: str | None
    folder: str  # relative to the item root
    requires: list[str] = field(default_factory=list)
    maps: list[str] = field(default_factory=list)
