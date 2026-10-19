"""Public control page of one server: basic info + start/stop/restart.

Not behind the panel login. Access is granted with the server's own
SERVER_PASSWORD (a server-scoped token that the admin API rejects); a server
without that password has the page disabled.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.integration import IntegrationTunnel, TunnelStatus
from app.models.server import Server
from app.schemas.control import (
    ControlLogin,
    ControlMeta,
    ControlPortOut,
    ControlToken,
    PublicServerOut,
)
from app.schemas.server import QueryOut
from app.services import auth as auth_service
from app.services import query_service, server_service
from app.services.integration_service import PANEL_TUNNEL_NAME
from app.services.template_loader import TemplateError, get_template

router = APIRouter(prefix="/api/control/{server_id}", tags=["control"])

bearer = HTTPBearer(auto_error=False)

# Brute-force throttle: failed logins per (client ip, server) in a sliding window.
_MAX_FAILURES = 10
_WINDOW_SECONDS = 5 * 60
_failures: dict[tuple[str, str], list[float]] = defaultdict(list)


def _password(server: Server) -> str:
    return (server.variables or {}).get("SERVER_PASSWORD", "") or ""


def _game_name(server: Server) -> str:
    try:
        return get_template(server.template_id).name
    except TemplateError:
        return server.template_id


async def _get_or_404(db: AsyncSession, server_id: str) -> Server:
    server = await server_service.get_server(db, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    return server


async def require_server_access(
    server_id: str,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Server:
    """Dependency: a valid control token for THIS server and its current password."""
    server = await _get_or_404(db, server_id)
    if creds is None or not auth_service.verify_server_token(
        creds.credentials, server.id, _password(server)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")
    return server


def _client_ip(request: Request) -> str:
    """The page is normally reached through the panel's same-origin proxy
    (frontend /api/control), which passes the browser's address on."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "?")


def _recent_failures(key: tuple[str, str]) -> list[float]:
    cutoff = time.monotonic() - _WINDOW_SECONDS
    attempts = [t for t in _failures[key] if t > cutoff]
    _failures[key] = attempts
    return attempts


async def _public(db: AsyncSession, server: Server) -> PublicServerOut:
    # Active tunnels of this server's ports, plus the panel's own tunnel.
    rows = (
        await db.execute(
            select(IntegrationTunnel).where(
                IntegrationTunnel.status == TunnelStatus.ACTIVE.value,
                IntegrationTunnel.remote_domain.is_not(None),
                or_(
                    IntegrationTunnel.server_id == server.id,
                    (IntegrationTunnel.server_id.is_(None))
                    & (IntegrationTunnel.name == PANEL_TUNNEL_NAME),
                ),
            )
        )
    ).scalars().all()
    by_port = {
        (t.local_port, t.protocol): t.remote_domain for t in rows if t.server_id == server.id
    }
    panel = next((t for t in rows if t.server_id is None), None)
    return PublicServerOut(
        id=server.id,
        name=server.name,
        game=_game_name(server),
        status=server.status,
        ports=[
            ControlPortOut(
                name=p.name,
                protocol=p.protocol,
                host_port=p.host_port,
                public_address=by_port.get((p.host_port, p.protocol)),
            )
            for p in server.ports
            if p.is_primary
        ],
        panel_public_host=panel.remote_domain.rsplit(":", 1)[0] if panel else None,
    )


@router.get("/meta", response_model=ControlMeta)
async def meta(server_id: str, db: AsyncSession = Depends(get_db)) -> ControlMeta:
    server = await _get_or_404(db, server_id)
    return ControlMeta(name=server.name, game=_game_name(server), enabled=bool(_password(server)))


@router.post("/login", response_model=ControlToken)
async def login(
    server_id: str, payload: ControlLogin, request: Request, db: AsyncSession = Depends(get_db)
) -> ControlToken:
    server = await _get_or_404(db, server_id)
    current = _password(server)
    if not current:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this server has no control password set")
    key = (_client_ip(request), server.id)
    if len(_recent_failures(key)) >= _MAX_FAILURES:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts, try again in a few minutes"
        )
    if not auth_service.check_server_password(payload.password, current):
        _failures[key].append(time.monotonic())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong password")
    _failures.pop(key, None)
    return ControlToken(access_token=auth_service.create_server_token(server.id, current))


@router.get("", response_model=PublicServerOut)
async def info(
    server: Server = Depends(require_server_access), db: AsyncSession = Depends(get_db)
) -> PublicServerOut:
    await server_service.reconcile(db, server)
    return await _public(db, server)


@router.get("/query", response_model=QueryOut)
async def query(server: Server = Depends(require_server_access)) -> QueryOut:
    """Live player count/list, so players can see who's on before a restart."""
    return await query_service.query_server(server)


@router.post("/start", response_model=PublicServerOut)
async def start(
    server: Server = Depends(require_server_access), db: AsyncSession = Depends(get_db)
) -> PublicServerOut:
    try:
        await server_service.start_server(db, server)
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return await _public(db, server)


@router.post("/stop", response_model=PublicServerOut)
async def stop(
    server: Server = Depends(require_server_access), db: AsyncSession = Depends(get_db)
) -> PublicServerOut:
    await server_service.stop_server(db, server)
    return await _public(db, server)


@router.post("/restart", response_model=PublicServerOut)
async def restart(
    server: Server = Depends(require_server_access), db: AsyncSession = Depends(get_db)
) -> PublicServerOut:
    try:
        await server_service.restart_server(db, server)
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return await _public(db, server)
