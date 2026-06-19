"""Provider abstraction for external-service integrations.

The core (service, router, models) only knows this interface and the registry;
concrete providers (Playit, Cloudflare, Discord, ...) implement it and
self-register, so adding a new integration never touches the core. This mirrors
the brief's TypeScript ``IntegrationProvider`` interface in Python.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import Integration, IntegrationTunnel


class ProviderCapability(str, enum.Enum):
    """What a provider can do — drives which UI a card renders."""

    TUNNELS = "tunnels"
    NOTIFICATIONS = "notifications"
    STORAGE = "storage"


@dataclass(slots=True)
class ConnectStart:
    """What the UI needs to complete a connect flow (e.g. a claim URL)."""

    integration_id: str
    claim_url: str | None = None
    expires_at: str | None = None


@dataclass(slots=True)
class StatusResult:
    """Connection status reported by a provider."""

    status: str  # IntegrationStatus value
    account_label: str | None = None
    error: str | None = None


@dataclass(slots=True)
class TunnelSpec:
    """A request to create a tunnel."""

    server_id: str | None
    local_port: int
    protocol: str
    name: str


@dataclass(slots=True)
class TunnelResult:
    """A tunnel as reported by the provider (create / list)."""

    external_id: str | None
    remote_domain: str | None
    status: str  # TunnelStatus value
    local_port: int | None = None
    protocol: str | None = None
    name: str | None = None
    error: str | None = None


class IntegrationProvider(ABC):
    """Base class every integration implements.

    Lifecycle methods are async and receive the live ``AsyncSession`` plus the
    ``Integration`` row so a provider can read its (encrypted) credentials and
    persist results. Host actions are delegated to the agent via the orchestrator.
    """

    id: str
    name: str
    description: str
    capabilities: tuple[ProviderCapability, ...] = ()
    icon: str = "plug"

    @property
    def supports_tunnels(self) -> bool:
        return ProviderCapability.TUNNELS in self.capabilities

    # -- lifecycle ------------------------------------------------------------

    @abstractmethod
    async def connect(self, session: AsyncSession, integration: Integration) -> ConnectStart:
        """Begin linking the external account; returns data the UI needs."""

    @abstractmethod
    async def poll_connect(self, session: AsyncSession, integration: Integration) -> StatusResult:
        """Advance an in-progress connect; persist credentials when complete."""

    @abstractmethod
    async def disconnect(self, session: AsyncSession, integration: Integration) -> None:
        """Tear down host resources for this link (idempotent)."""

    @abstractmethod
    async def validate_connection(self, session: AsyncSession, integration: Integration) -> bool:
        """Cheap check that the stored credentials still work."""

    @abstractmethod
    async def get_status(self, session: AsyncSession, integration: Integration) -> StatusResult:
        """Current connection status (used by cards and detail views)."""

    async def sync(self, session: AsyncSession, integration: Integration) -> None:
        """Reconcile platform state against the provider (optional, no-op default)."""
        return None

    # -- tunnels (tunnel-capable providers override) --------------------------

    async def create_tunnel(
        self, session: AsyncSession, integration: Integration, spec: TunnelSpec
    ) -> TunnelResult:
        raise NotImplementedError(f"{self.id} does not support tunnels")

    async def delete_tunnel(
        self, session: AsyncSession, integration: Integration, tunnel: IntegrationTunnel
    ) -> None:
        raise NotImplementedError(f"{self.id} does not support tunnels")

    async def list_tunnels(
        self, session: AsyncSession, integration: Integration
    ) -> list[TunnelResult]:
        raise NotImplementedError(f"{self.id} does not support tunnels")
