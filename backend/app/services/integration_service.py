"""Integration lifecycle and tunnel management.

Mirrors ``server_service``: async functions take an ``AsyncSession``, raise
domain errors the router maps to HTTP, and run slow host work as background
asyncio tasks with their own DB session. All provider-specific behaviour lives
behind the ``IntegrationProvider`` abstraction, so this module is generic.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.integrations  # noqa: F401 — importing registers all providers
from app.config import get_settings
from app.db import SessionLocal
from app.integrations.base import IntegrationProvider, TunnelSpec
from app.integrations.registry import get_provider, list_providers
from app.models.integration import (
    Integration,
    IntegrationStatus,
    IntegrationTunnel,
    TunnelStatus,
)
from app.models.server import Server
from app.services.template_loader import get_template

logger = logging.getLogger("steamcmd-manager.integrations")


class IntegrationError(RuntimeError):
    """Domain error the API layer turns into a 4xx."""


class ProviderUnavailable(IntegrationError):
    """Unknown provider id."""


class NotConnected(IntegrationError):
    """Operation requires a connected integration."""


# -- lookups ------------------------------------------------------------------


def _require_provider(provider_id: str) -> IntegrationProvider:
    provider = get_provider(provider_id)
    if provider is None:
        raise ProviderUnavailable(f"unknown integration provider '{provider_id}'")
    return provider


async def _row_for_provider(session: AsyncSession, provider_id: str) -> Integration | None:
    result = await session.execute(
        select(Integration).where(Integration.provider == provider_id)
    )
    return result.scalars().first()


async def get_integration(session: AsyncSession, integration_id: str) -> Integration | None:
    return await session.get(Integration, integration_id)


# -- listing (catalog merged with state) --------------------------------------


async def list_integrations(session: AsyncSession) -> list[dict]:
    """Every registered provider as a card, merged with its connection row."""
    result = await session.execute(select(Integration))
    rows = {row.provider: row for row in result.scalars().all()}

    cards: list[dict] = []
    for provider in list_providers():
        row = rows.get(provider.id)
        cards.append(
            {
                "id": row.id if row else None,
                "provider": provider.id,
                "name": provider.name,
                "description": provider.description,
                "icon": provider.icon,
                "capabilities": [c.value for c in provider.capabilities],
                "status": row.status if row else IntegrationStatus.NOT_CONNECTED.value,
                "account_label": row.account_label if row else None,
                "last_sync_at": row.last_sync_at if row else None,
                "error_message": row.error_message if row else None,
                "tunnel_count": len(row.tunnels) if row else 0,
            }
        )
    return cards


# -- connect / disconnect -----------------------------------------------------


async def start_connect(session: AsyncSession, provider_id: str):
    """Begin the connect flow; returns provider ``ConnectStart`` data."""
    provider = _require_provider(provider_id)
    integration = await _row_for_provider(session, provider_id)
    if integration is None:
        integration = Integration(provider=provider_id, status=IntegrationStatus.PENDING.value)
        session.add(integration)
        await session.flush()
    else:
        integration.status = IntegrationStatus.PENDING.value
        integration.error_message = None
    await session.flush()

    try:
        result = await provider.connect(session, integration)
    except Exception as exc:  # noqa: BLE001 — surface a clean 4xx
        integration.status = IntegrationStatus.ERROR.value
        integration.error_message = str(exc)
        await session.commit()
        raise IntegrationError(f"connect failed: {exc}") from exc

    # connect() may set the integration id on the result before commit.
    result.integration_id = integration.id
    await session.commit()
    return result


async def poll_connect(session: AsyncSession, integration_id: str) -> Integration:
    """Advance an in-progress connect and persist the new status."""
    integration = await get_integration(session, integration_id)
    if integration is None:
        raise IntegrationError("integration not found")
    provider = _require_provider(integration.provider)

    status = await provider.poll_connect(session, integration)
    integration.status = status.status
    integration.error_message = status.error
    if status.account_label:
        integration.account_label = status.account_label
    if status.status == IntegrationStatus.CONNECTED.value:
        integration.last_sync_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(integration)
    return integration


async def disconnect(session: AsyncSession, integration_id: str) -> None:
    integration = await get_integration(session, integration_id)
    if integration is None:
        raise IntegrationError("integration not found")
    provider = _require_provider(integration.provider)
    await provider.disconnect(session, integration)
    # Removing the row cascades to credentials + tunnels and reverts the card
    # to its catalog "not connected" state.
    await session.delete(integration)
    await session.commit()


# -- status / sync ------------------------------------------------------------


async def refresh_status(session: AsyncSession, integration: Integration) -> Integration:
    provider = _require_provider(integration.provider)
    status = await provider.get_status(session, integration)
    integration.status = status.status
    integration.error_message = status.error
    if status.account_label:
        integration.account_label = status.account_label
    await session.commit()
    await session.refresh(integration)
    return integration


async def sync_integration(session: AsyncSession, integration: Integration) -> None:
    """Reconcile one integration's tunnels against the provider."""
    provider = _require_provider(integration.provider)
    if not provider.supports_tunnels:
        await refresh_status(session, integration)
        return

    try:
        upstream = await provider.list_tunnels(session, integration)
    except Exception as exc:  # noqa: BLE001 — sync is best-effort
        logger.warning("sync list_tunnels failed for %s: %s", integration.id, exc)
        return

    upstream_by_ext = {t.external_id: t for t in upstream if t.external_id}
    local = list(integration.tunnels)
    local_by_ext = {t.external_id: t for t in local if t.external_id}

    for tunnel in local:
        # No external id yet → still being provisioned by us; leave it alone.
        if not tunnel.external_id:
            continue
        if tunnel.external_id in upstream_by_ext:
            up = upstream_by_ext[tunnel.external_id]
            tunnel.status = up.status or tunnel.status
            if up.remote_domain:
                tunnel.remote_domain = up.remote_domain
            tunnel.error_message = None
        elif tunnel.status == TunnelStatus.ACTIVE.value:
            # A previously-active tunnel vanished upstream → deleted manually.
            # (Pending tunnels missing upstream are still allocating — don't flap.)
            tunnel.status = TunnelStatus.ERROR.value
            tunnel.error_message = "tunnel no longer exists at provider"

    # Tunnels created out-of-band at the provider get imported.
    for ext_id, up in upstream_by_ext.items():
        if ext_id not in local_by_ext:
            session.add(
                IntegrationTunnel(
                    integration_id=integration.id,
                    name=up.name or f"imported-{ext_id[:8]}",
                    remote_domain=up.remote_domain,
                    local_port=up.local_port or 0,
                    protocol=up.protocol or "tcp",
                    external_id=ext_id,
                    status=up.status or TunnelStatus.ACTIVE.value,
                )
            )

    integration.last_sync_at = datetime.now(timezone.utc)
    for tunnel in local:
        await _advertise_public_ports(session, tunnel)
    await session.commit()


def _public_port(remote_domain: str | None) -> int | None:
    _, sep, port = (remote_domain or "").rpartition(":")
    return int(port) if sep and port.isdigit() else None


async def _advertise_public_ports(
    session: AsyncSession, tunnel: IntegrationTunnel, *, removed: bool = False
) -> None:
    """Make the game listen on the tunnel's public port numbers (applies on the
    next start).

    Only for ports with a tunnel profile: those tunnels reserve the whole port
    block contiguously (e.g. playit "project-zomboid": public P, P+1 -> local
    L, L+1), and games like Project Zomboid tell clients to open their second
    port by number — which must exist on the public side. Docker then maps
    host L -> container P, so the provider still forwards to the host ports.
    """
    if tunnel.server_id is None or await _tunnel_profile(session, tunnel) is None:
        return
    server = await session.get(Server, tunnel.server_id)
    if server is None:
        return
    primary = next(
        (p for p in server.ports if p.is_primary and p.host_port == tunnel.local_port), None
    )
    if primary is None:
        return
    block = [p for p in server.ports if p.name == primary.name and p.protocol == primary.protocol]
    public = None if removed else _public_port(tunnel.remote_domain)
    if tunnel.status != TunnelStatus.ACTIVE.value:
        public = None
    for p in block:
        wanted = public + (p.host_port - primary.host_port) if public else None
        if p.container_port != wanted:
            p.container_port = wanted
            logger.info(
                "server %s port %s/%s now listens on %s (restart to apply)",
                server.id, p.host_port, p.protocol, wanted or p.host_port,
            )


async def sync_all() -> None:
    """Reconcile every connected integration (called by the periodic loop)."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Integration).where(Integration.status == IntegrationStatus.CONNECTED.value)
        )
        integrations = list(result.scalars().all())
        for integration in integrations:
            try:
                await sync_integration(session, integration)
            except Exception:  # noqa: BLE001 — one bad integration must not stop the rest
                logger.exception("sync failed for integration %s", integration.id)


# -- tunnels ------------------------------------------------------------------


async def list_tunnels(session: AsyncSession, integration: Integration) -> list[IntegrationTunnel]:
    result = await session.execute(
        select(IntegrationTunnel)
        .where(IntegrationTunnel.integration_id == integration.id)
        .order_by(IntegrationTunnel.created_at.desc())
    )
    return list(result.scalars().all())


async def create_tunnel(
    session: AsyncSession,
    integration: Integration,
    *,
    server_id: str | None,
    local_port: int,
    protocol: str,
    name: str | None,
) -> IntegrationTunnel:
    provider = _require_provider(integration.provider)
    if not provider.supports_tunnels:
        raise IntegrationError(f"{provider.name} does not support tunnels")
    if integration.status != IntegrationStatus.CONNECTED.value:
        raise NotConnected(f"{provider.name} is not connected")

    if server_id is not None:
        server = await session.get(Server, server_id)
        if server is None:
            raise IntegrationError("server not found")
        if not name:
            name = f"{server.name}-{protocol}-{local_port}"
    if not name:
        name = f"{protocol}-{local_port}"

    tunnel = IntegrationTunnel(
        integration_id=integration.id,
        server_id=server_id,
        name=name,
        local_port=local_port,
        protocol=protocol,
        status=TunnelStatus.PENDING.value,
    )
    session.add(tunnel)
    await session.commit()
    await session.refresh(tunnel)

    # Provisioning calls the agent/provider — run it as a background job so the
    # request returns immediately (202); the UI polls for the tunnel to go active.
    asyncio.create_task(_provision_tunnel_job(integration.id, tunnel.id))
    return tunnel


async def _tunnel_profile(session: AsyncSession, tunnel: IntegrationTunnel) -> str | None:
    """The template's tunnel profile for the server port this tunnel exposes."""
    if tunnel.server_id is None:
        return None
    server = await session.get(Server, tunnel.server_id)
    if server is None:
        return None
    try:
        template = get_template(server.template_id)
    except Exception:  # noqa: BLE001 — unknown/removed template: provider default
        return None
    names = {
        p.name for p in server.ports if p.host_port == tunnel.local_port and p.is_primary
    }
    for spec in template.ports:
        if spec.name in names and tunnel.protocol in spec.protocols():
            return spec.tunnel_profile
    return None


async def _provision_tunnel_job(integration_id: str, tunnel_id: str) -> None:
    async with SessionLocal() as session:
        integration = await get_integration(session, integration_id)
        tunnel = await session.get(IntegrationTunnel, tunnel_id)
        if integration is None or tunnel is None:
            return
        provider = get_provider(integration.provider)
        if provider is None:
            return
        spec = TunnelSpec(
            server_id=tunnel.server_id,
            local_port=tunnel.local_port,
            protocol=tunnel.protocol,
            name=tunnel.name,
            profile=await _tunnel_profile(session, tunnel),
        )
        try:
            result = await provider.create_tunnel(session, integration, spec)
        except Exception as exc:  # noqa: BLE001
            tunnel.status = TunnelStatus.ERROR.value
            tunnel.error_message = str(exc)
            await session.commit()
            return

        tunnel.external_id = result.external_id
        tunnel.remote_domain = result.remote_domain
        tunnel.status = result.status
        tunnel.error_message = result.error
        await session.commit()


async def delete_tunnel(session: AsyncSession, integration: Integration, tunnel_id: str) -> None:
    tunnel = await session.get(IntegrationTunnel, tunnel_id)
    if tunnel is None or tunnel.integration_id != integration.id:
        raise IntegrationError("tunnel not found")
    provider = _require_provider(integration.provider)
    try:
        await provider.delete_tunnel(session, integration, tunnel)
    except Exception as exc:  # noqa: BLE001
        raise IntegrationError(f"could not delete tunnel: {exc}") from exc
    await _advertise_public_ports(session, tunnel, removed=True)
    await session.delete(tunnel)
    await session.commit()


# -- panel tunnel (public access to the web panel) ----------------------------

# The tunnel that exposes the web panel itself (e.g. the public server control
# pages). Identified by name, so it survives a re-import from the provider.
PANEL_TUNNEL_NAME = "steamcmd-panel"


def panel_default_port() -> int | None:
    """Host port the panel is published on, guessed from FRONTEND_ORIGIN."""
    parsed = urlparse(get_settings().frontend_origin)
    if parsed.port:
        return parsed.port
    return {"http": 80, "https": 443}.get(parsed.scheme)


async def tunnel_integration(session: AsyncSession) -> Integration | None:
    """The connected integration that can create tunnels (Playit), if any."""
    result = await session.execute(
        select(Integration).where(Integration.status == IntegrationStatus.CONNECTED.value)
    )
    for row in result.scalars().all():
        provider = get_provider(row.provider)
        if provider is not None and provider.supports_tunnels:
            return row
    return None


async def find_panel_tunnel(
    session: AsyncSession, integration: Integration
) -> IntegrationTunnel | None:
    result = await session.execute(
        select(IntegrationTunnel).where(
            IntegrationTunnel.integration_id == integration.id,
            IntegrationTunnel.server_id.is_(None),
            IntegrationTunnel.name == PANEL_TUNNEL_NAME,
        )
    )
    return result.scalars().first()


async def create_panel_tunnel(
    session: AsyncSession, integration: Integration, local_port: int
) -> IntegrationTunnel:
    if await find_panel_tunnel(session, integration) is not None:
        raise IntegrationError("the panel already has a tunnel")
    # Plain TCP: HTTP rides on it, so the panel is reachable at
    # http://<tunnel address>/ without any HTTPS/domain setup on the provider.
    return await create_tunnel(
        session,
        integration,
        server_id=None,
        local_port=local_port,
        protocol="tcp",
        name=PANEL_TUNNEL_NAME,
    )
