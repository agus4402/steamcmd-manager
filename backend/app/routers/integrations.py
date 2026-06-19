"""Integrations API — provider cards, connect flow, and tunnel management.

Thin endpoints that delegate to ``integration_service`` and map domain errors to
HTTP, exactly like ``routers/servers.py``. Registered under ``require_user``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.integration import Integration
from app.schemas.integration import (
    ConnectStartOut,
    ConnectStatusOut,
    IntegrationOut,
    TunnelCreate,
    TunnelOut,
)
from app.services import integration_service as svc

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


async def _get_or_404(db: AsyncSession, integration_id: str) -> Integration:
    integration = await svc.get_integration(db, integration_id)
    if integration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "integration not found")
    return integration


def _map_error(exc: svc.IntegrationError) -> HTTPException:
    if isinstance(exc, svc.ProviderUnavailable):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, svc.NotConnected):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("", response_model=list[IntegrationOut])
async def list_integrations(db: AsyncSession = Depends(get_db)) -> list[IntegrationOut]:
    cards = await svc.list_integrations(db)
    return [IntegrationOut(**card) for card in cards]


@router.get("/{integration_id}", response_model=IntegrationOut)
async def get_integration(
    integration_id: str, db: AsyncSession = Depends(get_db)
) -> IntegrationOut:
    integration = await _get_or_404(db, integration_id)
    from app.integrations.registry import get_provider

    provider = get_provider(integration.provider)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not available")
    return IntegrationOut(
        id=integration.id,
        provider=provider.id,
        name=provider.name,
        description=provider.description,
        icon=provider.icon,
        capabilities=[c.value for c in provider.capabilities],
        status=integration.status,
        account_label=integration.account_label,
        last_sync_at=integration.last_sync_at,
        error_message=integration.error_message,
        tunnel_count=len(integration.tunnels),
    )


@router.post(
    "/{provider}/connect",
    response_model=ConnectStartOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def connect(provider: str, db: AsyncSession = Depends(get_db)) -> ConnectStartOut:
    try:
        result = await svc.start_connect(db, provider)
    except svc.IntegrationError as exc:
        raise _map_error(exc) from exc
    return ConnectStartOut(
        integration_id=result.integration_id,
        claim_url=result.claim_url,
        expires_at=result.expires_at,
    )


@router.get("/{integration_id}/connect/status", response_model=ConnectStatusOut)
async def connect_status(
    integration_id: str, db: AsyncSession = Depends(get_db)
) -> ConnectStatusOut:
    await _get_or_404(db, integration_id)
    try:
        integration = await svc.poll_connect(db, integration_id)
    except svc.IntegrationError as exc:
        raise _map_error(exc) from exc
    return ConnectStatusOut(
        integration_id=integration.id,
        status=integration.status,
        account_label=integration.account_label,
        error_message=integration.error_message,
    )


@router.post("/{integration_id}/sync", response_model=IntegrationOut)
async def sync(integration_id: str, db: AsyncSession = Depends(get_db)) -> IntegrationOut:
    integration = await _get_or_404(db, integration_id)
    await svc.sync_integration(db, integration)
    return await get_integration(integration_id, db)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(integration_id: str, db: AsyncSession = Depends(get_db)) -> None:
    await _get_or_404(db, integration_id)
    try:
        await svc.disconnect(db, integration_id)
    except svc.IntegrationError as exc:
        raise _map_error(exc) from exc


@router.get("/{integration_id}/tunnels", response_model=list[TunnelOut])
async def list_tunnels(
    integration_id: str, db: AsyncSession = Depends(get_db)
) -> list[TunnelOut]:
    integration = await _get_or_404(db, integration_id)
    # Reconcile against the provider so freshly-allocated domains/states surface
    # without waiting for the periodic sync loop (best-effort).
    try:
        await svc.sync_integration(db, integration)
    except Exception:  # noqa: BLE001
        pass
    tunnels = await svc.list_tunnels(db, integration)
    return [TunnelOut.model_validate(t) for t in tunnels]


@router.post(
    "/{integration_id}/tunnels",
    response_model=TunnelOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_tunnel(
    integration_id: str, payload: TunnelCreate, db: AsyncSession = Depends(get_db)
) -> TunnelOut:
    integration = await _get_or_404(db, integration_id)
    try:
        tunnel = await svc.create_tunnel(
            db,
            integration,
            server_id=payload.server_id,
            local_port=payload.local_port,
            protocol=payload.protocol,
            name=payload.name,
        )
    except svc.IntegrationError as exc:
        raise _map_error(exc) from exc
    return TunnelOut.model_validate(tunnel)


@router.delete(
    "/{integration_id}/tunnels/{tunnel_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_tunnel(
    integration_id: str, tunnel_id: str, db: AsyncSession = Depends(get_db)
) -> None:
    integration = await _get_or_404(db, integration_id)
    try:
        await svc.delete_tunnel(db, integration, tunnel_id)
    except svc.IntegrationError as exc:
        raise _map_error(exc) from exc
