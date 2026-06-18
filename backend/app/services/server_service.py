"""Server lifecycle orchestration: create/read now, lifecycle in Phase 5.

Bridges the DB models, the port manager, the template loader and the Docker
orchestrator. Routers stay thin and call into here.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.models.server import Server, ServerStatus
from app.schemas.server import ServerCreate
from app.schemas.template import PLACEHOLDER_RE, GameTemplate, render_startup
from app.services.crypto import decrypt_credentials, encrypt_credentials
from app.services.docker_orchestrator import orchestrator
from app.services.port_manager import allocate_ports
from app.services.template_loader import get_template

logger = logging.getLogger("steamcmd-manager.servers")

# Statuses during which lifecycle actions must be rejected (a job owns the row).
INFLIGHT = {ServerStatus.INSTALLING.value, ServerStatus.UPDATING.value}


class ServerError(RuntimeError):
    """Domain error the API layer turns into a 4xx."""


class NameTaken(ServerError):
    pass


def _resolve_variables(template: GameTemplate, overrides: dict[str, str]) -> dict[str, str]:
    known = {v.key for v in template.variables}
    unknown = set(overrides) - known
    if unknown:
        raise ServerError(f"unknown variables: {sorted(unknown)}")

    values: dict[str, str] = {}
    for var in template.variables:
        value = overrides.get(var.key, var.default)
        # Generate a strong secret for empty password-like variables.
        if value == "" and var.key.upper().endswith("PASSWORD"):
            value = secrets.token_urlsafe(12)
        values[var.key] = value
    return values


def port_map(server: Server) -> dict[str, int]:
    """Placeholder name -> host port (deduped across tcp/udp of the same name)."""
    return {f"PORT_{p.name}": p.host_port for p in server.ports}


def render_startup_for(server: Server) -> str:
    pm = port_map(server)
    values: dict[str, str] = {**pm, **server.variables}
    allowed = set(pm) | set(server.variables)
    return render_startup(server.startup_template, values, allowed)


def docker_port_bindings(server: Server) -> dict[str, int]:
    """{'27015/udp': 27015, ...} — same number on host and in container."""
    return {f"{p.host_port}/{p.protocol}": p.host_port for p in server.ports}


async def create_server(session: AsyncSession, payload: ServerCreate) -> Server:
    template = get_template(payload.template_id)
    values = _resolve_variables(template, payload.variables)

    server = Server(
        name=payload.name,
        template_id=template.id,
        app_id=template.app_id,
        status=ServerStatus.CREATED.value,
        variables=values,
        startup_template=template.startup,
        anonymous_login=template.anonymous_login,
        update_on_start=template.update_on_start,
    )
    session.add(server)
    try:
        await session.flush()  # assign id, surface name-uniqueness violation
    except IntegrityError as exc:
        await session.rollback()
        raise NameTaken(f"server name '{payload.name}' already exists") from exc

    await allocate_ports(session, server.id, template.ports)

    # Pre-create the per-server data volume (blocking docker call).
    await run_in_threadpool(orchestrator.ensure_volume, orchestrator.data_volume(server.id))

    await session.commit()
    await session.refresh(server)
    logger.info("created server %s (%s) from template %s", server.name, server.id, template.id)
    return server


async def list_servers(session: AsyncSession) -> list[Server]:
    result = await session.execute(select(Server).order_by(Server.created_at))
    return list(result.scalars().all())


async def get_server(session: AsyncSession, server_id: str) -> Server | None:
    return await session.get(Server, server_id)


# -- environment builders -----------------------------------------------------


def _base_steam_env(server: Server, creds: dict[str, str] | None) -> dict[str, str]:
    env: dict[str, str] = {"STEAM_APP_ID": str(server.app_id), "INSTALL_DIR": "/data"}
    if server.anonymous_login or not creds:
        env["STEAM_LOGIN_USER"] = "anonymous"
    else:
        env["STEAM_LOGIN_USER"] = creds["username"]
        env["STEAM_LOGIN_PASSWORD"] = creds["password"]
        if creds.get("guard_code"):
            env["STEAM_GUARD_CODE"] = creds["guard_code"]
    return env


def build_install_env(server: Server, creds: dict[str, str] | None = None) -> dict[str, str]:
    env = _base_steam_env(server, creds)
    env["VALIDATE"] = "1"
    return env


def build_runtime_env(server: Server, creds: dict[str, str] | None = None) -> dict[str, str]:
    # The long-lived server container NEVER runs steamcmd: installs/updates always
    # happen in a separate one-shot container (so progress shows as installing/
    # updating, never hidden behind a misleading "running" status).
    env = _base_steam_env(server, creds)
    env["RUN_INSTALL"] = "0"
    env["VALIDATE"] = "0"
    env["STARTUP_CMD"] = render_startup_for(server)
    # Expose declared variables to the startup script's environment too.
    for key, value in server.variables.items():
        env[key] = str(value)
    return env


# -- install progress ---------------------------------------------------------

# steamcmd prints e.g.: "Update state (0x61) downloading, progress: 5.26 (357.. / 679..)"
_PROGRESS_RE = re.compile(r"progress:\s*([\d.]+)\s*\((\d+)\s*/\s*(\d+)\)")


def parse_progress(logs: str) -> dict[str, float | int] | None:
    """Return the latest steamcmd download/validate progress, or None."""
    matches = _PROGRESS_RE.findall(logs)
    if not matches:
        return None
    percent, downloaded, total = matches[-1]
    return {"percent": float(percent), "downloaded": int(downloaded), "total": int(total)}


async def get_progress(server: Server) -> dict[str, float | int] | None:
    """Install/update progress for a server currently downloading, else None."""
    if server.status not in INFLIGHT:
        return None
    logs = await run_in_threadpool(orchestrator.recent_install_logs, server.id, 50)
    return parse_progress(logs)


async def _resolve_creds(server: Server, provided: dict[str, str] | None) -> dict[str, str] | None:
    """Decide which Steam credentials to use and persist reusable ones.

    - Anonymous templates: no credentials.
    - Provided credentials: persist username+password (encrypted); the one-time
      Steam Guard code is used now but never stored.
    - Otherwise: fall back to previously stored encrypted credentials.
    """
    if server.anonymous_login:
        return None
    if provided and provided.get("username"):
        server.steam_credentials_enc = encrypt_credentials(
            {"username": provided["username"], "password": provided.get("password", "")}
        )
        return provided
    if server.steam_credentials_enc:
        return decrypt_credentials(server.steam_credentials_enc)
    raise ServerError("Steam credentials are required for this game")


# -- background install / update job ------------------------------------------


async def _install_job(
    server_id: str,
    env: dict[str, str],
    success_status: ServerStatus,
    then_start: bool = False,
    runtime_creds: dict[str, str] | None = None,
) -> None:
    """Run the one-shot install container to completion and persist the outcome.

    Runs in its own DB session because it outlives the originating request. If
    `then_start` is set, the server container is created + started on success
    (used by update_on_start, so the user sees updating→running automatically).
    """
    code, logs = -1, ""
    try:
        await run_in_threadpool(orchestrator.run_install, server_id, env)
        code, logs = await run_in_threadpool(orchestrator.wait_install, server_id)
    except Exception as exc:  # noqa: BLE001 — never let a job crash the panel
        logs = str(exc)
        logger.exception("install job failed for %s", server_id)

    async with SessionLocal() as session:
        server = await session.get(Server, server_id)
        if server is None:
            return
        if code != 0:
            server.status = ServerStatus.ERRORED.value
            server.error_message = (logs or f"steamcmd exited with code {code}")[-1000:]
        elif then_start:
            try:
                await _do_start(session, server, runtime_creds)
            except Exception as exc:  # noqa: BLE001
                server.status = ServerStatus.ERRORED.value
                server.error_message = f"install ok but start failed: {exc}"
                await session.commit()
        else:
            server.status = success_status.value
            server.error_message = None
        await session.commit()
    logger.info("install job for %s finished (code=%s, then_start=%s)", server_id, code, then_start)


# -- lifecycle actions --------------------------------------------------------


async def install_server(
    session: AsyncSession, server: Server, creds: dict[str, str] | None = None
) -> None:
    if server.status in INFLIGHT:
        raise ServerError("an install/update is already in progress")
    creds = await _resolve_creds(server, creds)
    server.status = ServerStatus.INSTALLING.value
    server.error_message = None
    await session.commit()
    env = build_install_env(server, creds)
    asyncio.create_task(_install_job(server.id, env, ServerStatus.STOPPED))


async def update_server(
    session: AsyncSession, server: Server, creds: dict[str, str] | None = None
) -> None:
    if server.status in INFLIGHT:
        raise ServerError("an install/update is already in progress")
    creds = await _resolve_creds(server, creds)
    # Stop the server before updating files underneath it.
    await run_in_threadpool(orchestrator.stop, server.id)
    server.status = ServerStatus.UPDATING.value
    server.error_message = None
    await session.commit()
    env = build_install_env(server, creds)
    asyncio.create_task(_install_job(server.id, env, ServerStatus.STOPPED))


async def _do_start(
    session: AsyncSession, server: Server, creds: dict[str, str] | None
) -> None:
    """Create + start the long-lived server container (no steamcmd here)."""
    env = build_runtime_env(server, creds)
    bindings = docker_port_bindings(server)
    container_id = await run_in_threadpool(
        orchestrator.create_server_container, server.id, env, bindings
    )
    await run_in_threadpool(orchestrator.start, server.id)
    server.container_id = container_id
    server.status = ServerStatus.RUNNING.value
    server.error_message = None
    await session.commit()


async def start_server(
    session: AsyncSession, server: Server, creds: dict[str, str] | None = None
) -> None:
    if server.status in INFLIGHT:
        raise ServerError("an install/update is in progress")
    creds = await _resolve_creds(server, creds)
    if server.update_on_start:
        # Download/validate first (shown as 'updating' + progress), then auto-start.
        server.status = ServerStatus.UPDATING.value
        server.error_message = None
        await session.commit()
        asyncio.create_task(
            _install_job(
                server.id,
                build_install_env(server, creds),
                ServerStatus.STOPPED,
                then_start=True,
                runtime_creds=creds,
            )
        )
    else:
        await _do_start(session, server, creds)


async def stop_server(session: AsyncSession, server: Server) -> None:
    await run_in_threadpool(orchestrator.stop, server.id)
    server.status = ServerStatus.STOPPED.value
    await session.commit()


async def restart_server(
    session: AsyncSession, server: Server, creds: dict[str, str] | None = None
) -> None:
    if server.status in INFLIGHT:
        raise ServerError("an install/update is in progress")
    state = await run_in_threadpool(orchestrator.state, server.id)
    if not state.exists:
        # Nothing to restart — bring it up fresh.
        await start_server(session, server, creds)
        return
    await run_in_threadpool(orchestrator.restart, server.id)
    server.status = ServerStatus.RUNNING.value
    server.error_message = None
    await session.commit()


async def delete_server(session: AsyncSession, server: Server) -> None:
    # Remove container + install container + data volume; no orphans left behind.
    await run_in_threadpool(orchestrator.remove, server.id, True)
    # Deleting the row cascades to port_allocations, freeing the host ports.
    await session.delete(server)
    await session.commit()


async def patch_server(
    session: AsyncSession,
    server: Server,
    variables: dict[str, str] | None,
    startup_template: str | None,
) -> Server:
    if variables is not None:
        unknown = set(variables) - set(server.variables)
        if unknown:
            raise ServerError(f"unknown variables: {sorted(unknown)}")
        server.variables = {**server.variables, **variables}
    if startup_template is not None:
        allowed = {f"PORT_{p.name}" for p in server.ports} | set(server.variables)
        used = set(PLACEHOLDER_RE.findall(startup_template))
        unknown_ph = used - allowed
        if unknown_ph:
            raise ServerError(f"startup references unknown placeholders: {sorted(unknown_ph)}")
        server.startup_template = startup_template
    await session.commit()
    await session.refresh(server)
    return server


# -- state reconciliation -----------------------------------------------------


async def reconcile(session: AsyncSession, server: Server) -> Server:
    """Align the persisted status with the live container state.

    Skips servers with an in-flight install/update (a background job owns them).
    """
    if server.status in INFLIGHT:
        return server
    state = await run_in_threadpool(orchestrator.state, server.id)
    new_status = server.status
    if not state.exists:
        if server.status == ServerStatus.RUNNING.value:
            new_status = ServerStatus.STOPPED.value
    elif state.status == "running":
        new_status = ServerStatus.RUNNING.value
    elif state.status in ("exited", "dead", "created"):
        if server.status == ServerStatus.RUNNING.value:
            # A running server whose container died with a non-zero code crashed.
            crashed = state.exit_code not in (0, None)
            new_status = ServerStatus.ERRORED.value if crashed else ServerStatus.STOPPED.value
    if new_status != server.status:
        server.status = new_status
        await session.commit()
    return server
