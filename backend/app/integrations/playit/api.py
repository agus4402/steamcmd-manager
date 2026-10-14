"""Playit.gg control-plane API client.

Runs in the **backend** (which has internet egress). The privileged agent is
egress-less by design, so every ``api.playit.gg`` call lives here; the agent only
runs the ``playitd`` container, which gets its own egress via host networking.

Claim flow (no secret): generate a 5-byte hex code, register it with
``/claim/setup``, the user approves at ``https://playit.gg/claim/<code>``, poll
``/claim/setup`` until ``UserAccepted``, then ``/claim/exchange`` returns the
permanent agent secret. Tunnel management authenticates with
``Authorization: agent-key <secret>``. All responses use a ``{status, data}``
envelope.
"""

from __future__ import annotations

import secrets

import httpx

from app.config import get_settings

settings = get_settings()

AGENT_TYPE = "self-managed"
AGENT_VERSION = "steamcmd-manager-playit 1.0"
_TIMEOUT = httpx.Timeout(15.0)


class PlayitApiError(RuntimeError):
    """A Playit control-plane call failed (network or API-level)."""


def new_claim_code() -> str:
    return secrets.token_hex(5)  # 5-byte code, e.g. "2f4ad939c5"


def _unwrap(resp: httpx.Response) -> object:
    try:
        body = resp.json()
    except ValueError as exc:
        raise PlayitApiError(f"{resp.status_code}: non-JSON response") from exc
    if body.get("status") == "success":
        return body.get("data")
    data = body.get("data")
    if isinstance(data, dict):
        msg = data.get("message") or data.get("type") or str(data)
    else:
        msg = str(data)
    raise PlayitApiError(str(msg))


async def _post(path: str, payload: dict, headers: dict | None = None) -> object:
    url = f"{settings.playit_api_base.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise PlayitApiError(f"playit api unreachable: {exc}") from exc
    return _unwrap(resp)


# -- claim (unauthenticated) --------------------------------------------------


async def claim_setup(code: str) -> str:
    """Register/advance a claim. Returns one of:
    WaitingForUserVisit | WaitingForUser | UserAccepted | UserRejected."""
    status = await _post(
        "/claim/setup", {"code": code, "agent_type": AGENT_TYPE, "version": AGENT_VERSION}
    )
    return str(status)


async def claim_exchange(code: str) -> str | None:
    """Exchange an accepted claim code for the permanent secret key."""
    data = await _post("/claim/exchange", {"code": code})
    if isinstance(data, dict):
        return data.get("secret_key")
    return data if isinstance(data, str) else None


# -- authenticated (agent-key secret) -----------------------------------------

# A self-managed agent must create tunnels with a themed tunnel_type (the API
# rejects type-less custom tunnels with "TunnelTypeRequiresDescription"). The
# type DOES matter: playit filters traffic per game profile — a
# "minecraft-bedrock" UDP tunnel only passes Bedrock/RakNet pings (verified:
# Steam queries and arbitrary datagrams were dropped). Templates can pick the
# game's own profile per port (e.g. "project-zomboid"); otherwise UDP uses
# "valheim", which passed arbitrary UDP in testing (it reserves 2 ports).
_TUNNEL_TYPE = {"tcp": "minecraft-java", "udp": "valheim"}


def _public_address(tunnel: dict) -> str | None:
    """assigned/custom domain + the allocated public port, e.g. host.playit.gg:12345."""
    domain = tunnel.get("custom_domain") or tunnel.get("assigned_domain")
    if not domain:
        return None
    port = (tunnel.get("port") or {}).get("from")
    return f"{domain}:{port}" if port is not None else domain


class PlayitApi:
    def __init__(self, secret: str) -> None:
        self._headers = {
            "Authorization": f"agent-key {secret}",
            "Content-Type": "application/json",
        }

    async def rundata(self) -> dict:
        """Agent run data: agent_id, account_status, active + pending tunnels."""
        data = await _post("/agents/rundata", {}, self._headers)
        return data if isinstance(data, dict) else {}

    async def account_label(self) -> str | None:
        rd = await self.rundata()
        aid = rd.get("agent_id")
        return f"agent {aid[:8]}" if aid else None

    async def create_tunnel(
        self, local_port: int, protocol: str, name: str, tunnel_type: str | None = None
    ) -> dict:
        rd = await self.rundata()
        agent_id = rd.get("agent_id")
        if not agent_id:
            raise PlayitApiError("no agent registered for this account")
        data = await _post(
            "/tunnels/create",
            {
                "name": name,
                "tunnel_type": tunnel_type or _TUNNEL_TYPE.get(protocol, "minecraft-java"),
                "port_type": protocol,
                "port_count": 1,
                "origin": {
                    "type": "agent",
                    "data": {
                        "agent_id": agent_id,
                        "local_ip": "127.0.0.1",
                        "local_port": local_port,
                    },
                },
                "enabled": True,
            },
            self._headers,
        )
        tunnel = data if isinstance(data, dict) else {}
        # Newly created tunnels start unallocated (no domain yet); sync fills it in.
        return {
            "external_id": str(tunnel.get("id") or ""),
            "remote_domain": None,
            "status": "pending",
        }

    async def list_tunnels(self) -> list[dict]:
        rd = await self.rundata()
        out: list[dict] = []
        for t in rd.get("tunnels", []):  # active, allocated
            out.append(
                {
                    "external_id": str(t.get("id") or ""),
                    "remote_domain": _public_address(t),
                    "local_port": t.get("local_port"),
                    "protocol": t.get("proto"),
                    "name": t.get("name"),
                    "status": "disabled" if t.get("disabled") else "active",
                }
            )
        for t in rd.get("pending", []):  # allocating, no address yet
            out.append(
                {
                    "external_id": str(t.get("id") or ""),
                    "remote_domain": None,
                    "local_port": None,
                    "protocol": t.get("proto"),
                    "name": t.get("name"),
                    "status": "pending",
                }
            )
        return out

    async def delete_tunnel(self, external_id: str) -> None:
        await _post("/tunnels/delete", {"tunnel_id": external_id}, self._headers)
