"""Live server info (name, map, players) via the template's query protocol."""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
import time

from app.config import get_settings
from app.models.server import Server, ServerStatus
from app.schemas.server import QueryInfoOut, QueryOut, QueryPlayerOut
from app.schemas.template import QuerySpec
from app.services import a2s
from app.services.template_loader import TemplateError, get_template

logger = logging.getLogger("steamcmd-manager.query")
settings = get_settings()

# Several tabs/viewers poll the same server; answer them from one recent query.
_CACHE_TTL = 3.0
_cache: dict[str, tuple[float, QueryOut]] = {}
_locks: dict[str, asyncio.Lock] = {}


def query_spec(server: Server) -> QuerySpec | None:
    try:
        return get_template(server.template_id).query
    except TemplateError:
        return None


def query_port(server: Server, spec: QuerySpec) -> int | None:
    """Host port to query: `offset` within the named port's UDP block."""
    block = sorted(
        p.host_port for p in server.ports if p.name == spec.port and p.protocol == "udp"
    )
    return block[spec.offset] if spec.offset < len(block) else None


async def query_server(server: Server) -> QueryOut:
    spec = query_spec(server)
    if spec is None:
        return QueryOut(supported=False)
    if server.status != ServerStatus.RUNNING.value:
        return QueryOut(supported=True, online=False)

    lock = _locks.setdefault(server.id, asyncio.Lock())
    async with lock:
        cached = _cache.get(server.id)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL:
            return cached[1]
        out = await _query(server, spec)
        _cache[server.id] = (time.monotonic(), out)
        return out


def default_gateway(route_table: str | None = None) -> str | None:
    """IPv4 default gateway from /proc/net/route (inside a container: the Docker
    host's address on the container's network)."""
    try:
        if route_table is None:
            with open("/proc/net/route") as f:
                route_table = f.read()
    except OSError:
        return None
    for line in route_table.splitlines()[1:]:
        fields = line.split()
        # Destination 0.0.0.0 with the RTF_GATEWAY flag.
        if len(fields) > 3 and fields[1] == "00000000" and int(fields[3], 16) & 0x2:
            return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    return None


_resolved_host: str | None = None


async def _query_host() -> str:
    """QUERY_HOST, or the default gateway when it doesn't resolve.

    host.docker.internal only exists when compose maps it (extra_hosts:
    host-gateway); an older compose file lacks it. The gateway is also a host
    address, so the published game ports are reachable through it.
    """
    global _resolved_host
    if _resolved_host:
        return _resolved_host
    host = settings.query_host
    try:
        await asyncio.get_running_loop().getaddrinfo(host, None)
        _resolved_host = host
    except socket.gaierror:
        gateway = default_gateway()
        if gateway is None:
            return host  # surfaces the resolution error to the UI
        logger.info("query host %r doesn't resolve; using gateway %s", host, gateway)
        _resolved_host = gateway
    return _resolved_host


async def _query(server: Server, spec: QuerySpec) -> QueryOut:
    port = query_port(server, spec)
    if port is None:
        return QueryOut(supported=True, online=False, error="query port is not allocated")

    host, timeout = await _query_host(), settings.query_timeout
    info_res, players_res = await asyncio.gather(
        a2s.info(host, port, timeout), a2s.players(host, port, timeout), return_exceptions=True
    )
    if isinstance(info_res, BaseException):
        # Normal while the game is still booting: the container runs before
        # the server starts answering queries.
        logger.debug("A2S info %s:%s for %s failed: %s", host, port, server.id, info_res)
        return QueryOut(supported=True, online=False, query_port=port, error=_reason(info_res))

    players: list[QueryPlayerOut] | None = None
    if not isinstance(players_res, BaseException):
        players = [
            QueryPlayerOut(name=p.name, score=p.score, duration=round(p.duration))
            for p in players_res
        ]
    return QueryOut(
        supported=True,
        online=True,
        query_port=port,
        info=QueryInfoOut(
            name=info_res.name,
            map=info_res.map,
            game=info_res.game,
            version=info_res.version,
            players=info_res.players,
            max_players=info_res.max_players,
            bots=info_res.bots,
            password=info_res.password,
            vac=info_res.vac,
        ),
        players=players,
    )


def _reason(exc: BaseException) -> str:
    if isinstance(exc, a2s.A2SError):
        return str(exc)
    if isinstance(exc, OSError):
        return f"network error: {exc.strerror or exc}"
    return f"query failed: {exc}"
