"""Provider abstraction for Workshop / mod sources.

The core (service, router, models) only knows this interface and the registry;
concrete providers (Steam, and later CurseForge / Mod.io / Nexus) implement it and
self-register, so adding a new mod source never touches the core. This mirrors the
``IntegrationProvider`` pattern in ``app/integrations/base.py``.

Note: the *install mechanism* (downloading items into a server's data volume) is
provider-specific. For Steam it is SteamCMD, orchestrated via the agent and kept
in ``docker_orchestrator`` — not on this interface. This interface covers only the
metadata side: search, details, dependencies, and collection resolution.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


class WorkshopSort(str, enum.Enum):
    """UI-facing sort options for search (provider maps these to its own query)."""

    POPULAR = "popular"
    SUBSCRIBED = "subscribed"
    TRENDING = "trending"
    UPDATED = "updated"
    NEWEST = "newest"


@dataclass(slots=True)
class Dependency:
    """A required item referenced by a mod (its Workshop ``children``)."""

    item_id: str
    title: str | None = None


@dataclass(slots=True)
class ModSummary:
    """Lightweight metadata for cards / search results."""

    item_id: str
    title: str | None = None
    author_id: str | None = None
    author_name: str | None = None
    preview_url: str | None = None
    subscribers: int = 0
    favorites: int = 0
    file_size: int = 0
    time_updated: datetime | None = None
    time_created: datetime | None = None


@dataclass(slots=True)
class ModDetails(ModSummary):
    """Full metadata for the details drawer, including dependencies."""

    description: str | None = None
    images: list[str] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)


@dataclass(slots=True)
class SearchResult:
    items: list[ModSummary]
    total: int
    page: int


class WorkshopProviderError(RuntimeError):
    """Domain error the API layer turns into a 4xx/5xx."""


class WorkshopProvider(ABC):
    """Base class every mod source implements.

    Methods are async; the service layer owns persistence and recursive
    dependency walking. Providers should raise ``WorkshopProviderError`` for
    user-facing failures (e.g. missing API key, unknown item).
    """

    id: str
    name: str
    description: str
    icon: str = "boxes"

    @abstractmethod
    async def search(
        self,
        *,
        query: str,
        app_id: int,
        page: int = 1,
        page_size: int = 30,
        sort: WorkshopSort = WorkshopSort.POPULAR,
    ) -> SearchResult:
        """Search the provider's catalog for ``app_id``."""

    @abstractmethod
    async def get_summaries(self, item_ids: list[str]) -> list[ModSummary]:
        """Batch lightweight metadata (for cards / import preview / sync).
        Items that don't exist are omitted from the result."""

    @abstractmethod
    async def get_details(self, item_id: str) -> ModDetails:
        """Full metadata + direct dependencies for a single item."""

    @abstractmethod
    async def get_dependencies(self, item_id: str) -> list[Dependency]:
        """Direct (one level) dependencies for an item. The service walks these
        recursively; providers need not recurse."""

    @abstractmethod
    async def resolve_collection(self, collection_id: str) -> list[str]:
        """Return the member item ids of a collection (empty if not a collection)."""
