"""Playit.gg integration provider.

Split of responsibilities (see ``api.py``):
- **Control-plane** (claim flow, tunnel CRUD, account info) → ``PlayitApi`` /
  ``claim_*`` in the backend, which has internet egress.
- **Data-plane** (the running ``playitd`` forwarder) → the agent, via the
  orchestrator. The agent is egress-less; the playitd container it runs reaches
  Playit through host networking.

Credential model: the backend is the source of truth for the agent secret. It is
captured once at the end of the claim flow, stored Fernet-encrypted, and handed
to the agent when it (re)starts the playitd container.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.integrations.base import (
    ConnectStart,
    IntegrationProvider,
    ProviderCapability,
    StatusResult,
    TunnelResult,
    TunnelSpec,
)
from app.integrations.credentials import read_credentials, store_credentials
from app.integrations.playit.api import (
    PlayitApi,
    PlayitApiError,
    claim_exchange,
    claim_setup,
    new_claim_code,
)
from app.models.integration import Integration, IntegrationStatus, TunnelStatus
from app.services.docker_orchestrator import DockerError, orchestrator

logger = logging.getLogger("steamcmd-manager.integrations.playit")


class PlayitProvider(IntegrationProvider):
    id = "playit"
    name = "Playit.gg"
    description = (
        "Expose your game servers to the internet through Playit.gg tunnels — "
        "no port forwarding required."
    )
    capabilities = (ProviderCapability.TUNNELS,)
    icon = "globe"

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _secret(integration: Integration) -> str | None:
        creds = read_credentials(integration)
        return creds.get("secret_key") if creds else None

    async def _ensure_running(self, integration: Integration, secret: str) -> None:
        """Best-effort: make sure the playitd forwarder is up on the agent."""
        try:
            await run_in_threadpool(orchestrator.playit_run, integration.id, secret)
        except DockerError as exc:  # noqa: BLE001 — control-plane still works without it
            logger.warning("playit run (agent) for %s: %s", integration.id, exc)

    # -- lifecycle ------------------------------------------------------------

    async def connect(self, session: AsyncSession, integration: Integration) -> ConnectStart:
        code = new_claim_code()
        try:
            await claim_setup(code)
        except PlayitApiError as exc:
            raise RuntimeError(f"could not start Playit claim: {exc}") from exc
        # Persist the claim code so polling can advance the flow statelessly.
        await store_credentials(session, integration, {"claim_code": code})
        return ConnectStart(
            integration_id=integration.id,
            claim_url=f"https://playit.gg/claim/{code}",
        )

    async def poll_connect(self, session: AsyncSession, integration: Integration) -> StatusResult:
        creds = read_credentials(integration)
        code = creds.get("claim_code") if creds else None
        if not code:
            return StatusResult(
                status=IntegrationStatus.ERROR.value, error="no claim in progress"
            )
        try:
            status = await claim_setup(code)
            if status == "UserRejected":
                return StatusResult(
                    status=IntegrationStatus.ERROR.value, error="claim was rejected"
                )
            if status != "UserAccepted":
                return StatusResult(status=IntegrationStatus.PENDING.value)
            secret = await claim_exchange(code)
        except PlayitApiError as exc:
            return StatusResult(status=IntegrationStatus.ERROR.value, error=str(exc))

        if not secret:
            return StatusResult(
                status=IntegrationStatus.ERROR.value,
                error="claim approved but no secret returned",
            )
        # Replace the transient claim code with the permanent secret, then bring
        # up the forwarder container.
        await store_credentials(session, integration, {"secret_key": secret})
        await self._ensure_running(integration, secret)
        label = None
        try:
            label = await PlayitApi(secret).account_label()
        except PlayitApiError:
            pass
        return StatusResult(status=IntegrationStatus.CONNECTED.value, account_label=label)

    async def disconnect(self, session: AsyncSession, integration: Integration) -> None:
        try:
            await run_in_threadpool(orchestrator.playit_remove, integration.id)
        except DockerError as exc:  # noqa: BLE001 — never block local disconnect
            logger.warning("playit disconnect (agent) for %s: %s", integration.id, exc)

    async def validate_connection(self, session: AsyncSession, integration: Integration) -> bool:
        secret = self._secret(integration)
        if not secret:
            return False
        try:
            await PlayitApi(secret).account_label()
            return True
        except PlayitApiError:
            return False

    async def get_status(self, session: AsyncSession, integration: Integration) -> StatusResult:
        secret = self._secret(integration)
        if not secret:
            return StatusResult(status=IntegrationStatus.NOT_CONNECTED.value)
        try:
            label = await PlayitApi(secret).account_label()
        except PlayitApiError as exc:
            return StatusResult(status=IntegrationStatus.ERROR.value, error=str(exc))
        # Keep the forwarder running while connected.
        await self._ensure_running(integration, secret)
        return StatusResult(status=IntegrationStatus.CONNECTED.value, account_label=label)

    # -- tunnels --------------------------------------------------------------

    async def create_tunnel(
        self, session: AsyncSession, integration: Integration, spec: TunnelSpec
    ) -> TunnelResult:
        secret = self._secret(integration)
        if not secret:
            raise RuntimeError("Playit is not connected")
        await self._ensure_running(integration, secret)
        try:
            data = await PlayitApi(secret).create_tunnel(spec.local_port, spec.protocol, spec.name)
        except PlayitApiError as exc:
            return TunnelResult(
                external_id=None,
                remote_domain=None,
                status=TunnelStatus.ERROR.value,
                error=str(exc),
            )
        return TunnelResult(
            external_id=data.get("external_id"),
            remote_domain=data.get("remote_domain"),
            status=data.get("status", TunnelStatus.ACTIVE.value),
            local_port=spec.local_port,
            protocol=spec.protocol,
            name=spec.name,
        )

    async def delete_tunnel(
        self, session: AsyncSession, integration: Integration, tunnel
    ) -> None:
        if not tunnel.external_id:
            return
        secret = self._secret(integration)
        if not secret:
            raise RuntimeError("Playit is not connected")
        try:
            await PlayitApi(secret).delete_tunnel(tunnel.external_id)
        except PlayitApiError as exc:
            raise RuntimeError(f"could not delete tunnel: {exc}") from exc

    async def list_tunnels(
        self, session: AsyncSession, integration: Integration
    ) -> list[TunnelResult]:
        secret = self._secret(integration)
        if not secret:
            return []
        try:
            rows = await PlayitApi(secret).list_tunnels()
        except PlayitApiError as exc:
            logger.warning("playit list tunnels for %s: %s", integration.id, exc)
            return []
        return [
            TunnelResult(
                external_id=r.get("external_id"),
                remote_domain=r.get("remote_domain"),
                status=r.get("status", TunnelStatus.ACTIVE.value),
                local_port=r.get("local_port"),
                protocol=r.get("protocol"),
                name=r.get("name"),
            )
            for r in rows
        ]
