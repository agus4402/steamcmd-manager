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

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models.server import Server, ServerStatus
from app.schemas.server import ServerCreate
from app.schemas.template import PLACEHOLDER_RE, GameTemplate, render_startup
from app.services import load_order_service, notification_service
from app.services.load_order_service import WorkshopRuntime
from app.services.crypto import decrypt_credentials, encrypt_credentials
from app.services.docker_orchestrator import DEFAULT_STOP_TIMEOUT, DockerError, orchestrator
from app.services.port_manager import allocate_ports
from app.services.template_loader import get_template

logger = logging.getLogger("steamcmd-manager.servers")


def _notif_excerpt(text: str | None) -> str | None:
    """Short, single-line excerpt of an error for a notification message."""
    if not text:
        return None
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first[:200] or None

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
        if value == "" and var.should_generate():
            value = secrets.token_urlsafe(12)
        values[var.key] = value
    return values


def port_map(server: Server) -> dict[str, int]:
    """Placeholder name -> base host port (only the primary port of each block)."""
    return {f"PORT_{p.name}": p.host_port for p in server.ports if p.is_primary}


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
    if not template.supported:
        reason = template.unsupported_reason or "this game is not supported"
        raise ServerError(f"template '{template.id}' is not supported: {reason}")
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
        workshop_app_id=template.workshop.app_id if template.workshop else None,
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


async def clone_server(session: AsyncSession, source: Server, new_name: str) -> Server:
    """Create a new server with the same template/config and a copy of the data.

    Ports are freshly allocated for the clone; the data volume is copied so an
    installed source yields a ready-to-start clone.
    """
    if source.status in INFLIGHT:
        raise ServerError("cannot clone while an install/update is in progress")
    template = get_template(source.template_id)

    clone = Server(
        name=new_name,
        template_id=source.template_id,
        app_id=source.app_id,
        status=ServerStatus.CREATED.value,
        variables=dict(source.variables),
        startup_template=source.startup_template,
        anonymous_login=source.anonymous_login,
        update_on_start=source.update_on_start,
        workshop_app_id=source.workshop_app_id,
    )
    session.add(clone)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise NameTaken(f"server name '{new_name}' already exists") from exc

    await allocate_ports(session, clone.id, template.ports)
    await run_in_threadpool(orchestrator.ensure_volume, orchestrator.data_volume(clone.id))
    await run_in_threadpool(orchestrator.copy_data, source.id, clone.id)
    # If the source had installed files, the clone is ready to start.
    if source.status in (ServerStatus.RUNNING.value, ServerStatus.STOPPED.value):
        clone.status = ServerStatus.STOPPED.value

    await session.commit()
    await session.refresh(clone)
    logger.info("cloned server %s -> %s (%s)", source.id, clone.id, clone.name)
    return clone


async def reinstall_server(
    session: AsyncSession, server: Server, creds: dict[str, str] | None = None
) -> None:
    """Wipe the server's container + data volume, then run a fresh install."""
    if server.status in INFLIGHT:
        raise ServerError("an install/update is already in progress")
    creds = await _resolve_creds(server, creds)
    # Tear down the running container and wipe the data volume.
    await run_in_threadpool(orchestrator.remove, server.id, True)
    server.container_id = None
    server.status = ServerStatus.INSTALLING.value
    server.error_message = None
    await session.commit()
    env = build_install_env(server, creds)
    asyncio.create_task(_install_job(server.id, env, ServerStatus.STOPPED))


# -- backups ------------------------------------------------------------------

# In-memory backup job state per server. A snapshot tars the whole data volume
# and can run for minutes, so it's a fire-and-forget background task the UI polls
# (instead of a long-blocking request that the browser would time out on).
_backup_jobs: dict[str, dict] = {}


def get_backup_job(server_id: str) -> dict | None:
    return _backup_jobs.get(server_id)


async def start_backup(server: Server) -> dict:
    job = _backup_jobs.get(server.id)
    if job and job["status"] == "creating":
        raise ServerError("a backup is already in progress")
    _backup_jobs[server.id] = {
        "status": "creating",
        "id": None,
        "size": 0,
        "error": None,
        "max_backups": server.max_backups,
    }
    asyncio.create_task(_backup_job(server.id))
    return _backup_jobs[server.id]


async def _backup_job(server_id: str) -> None:
    try:
        snap = await run_in_threadpool(orchestrator.create_snapshot, server_id)
        max_backups = _backup_jobs[server_id].get("max_backups", 0)
        _backup_jobs[server_id] = {"status": "done", "id": snap.id, "size": snap.size, "error": None}
        logger.info("backup %s for %s complete (%d bytes)", snap.id, server_id, snap.size)
        if max_backups > 0:
            await _enforce_backup_limit(server_id, max_backups)
    except DockerError as exc:
        _backup_jobs[server_id] = {"status": "error", "id": None, "size": 0, "error": str(exc)}
        logger.error("backup failed for %s: %s", server_id, exc)
        await notification_service.notify("error", "Backup failed", str(exc)[:200], server_id)
    except Exception as exc:  # noqa: BLE001 — never let a job crash the panel
        _backup_jobs[server_id] = {"status": "error", "id": None, "size": 0, "error": str(exc)}
        logger.exception("backup crashed for %s", server_id)
        await notification_service.notify("error", "Backup failed", str(exc)[:200], server_id)


async def _enforce_backup_limit(server_id: str, max_backups: int) -> None:
    try:
        snaps = await run_in_threadpool(orchestrator.list_snapshots, server_id)
        if len(snaps) <= max_backups:
            return
        # Sort oldest first; delete all that exceed the limit
        snaps.sort(key=lambda s: s.created_at)
        to_delete = snaps[: len(snaps) - max_backups]
        for snap in to_delete:
            await run_in_threadpool(orchestrator.delete_snapshot, server_id, snap.id)
            logger.info("auto-deleted old backup %s for %s (limit=%d)", snap.id, server_id, max_backups)
    except Exception as exc:  # noqa: BLE001
        logger.error("backup limit enforcement failed for %s: %s", server_id, exc)


async def list_snapshots(server: Server):
    return await run_in_threadpool(orchestrator.list_snapshots, server.id)


async def restore_snapshot(
    session: AsyncSession, server: Server, snapshot_id: str, start_after: bool = False
) -> None:
    """Stop the server (files can't be replaced underneath it) and restore."""
    if server.status in INFLIGHT:
        raise ServerError("an install/update is in progress")
    await _stop_container(server)
    await run_in_threadpool(orchestrator.restore_snapshot, server.id, snapshot_id)
    if start_after:
        await _do_start(session, server, None)
    elif server.status == ServerStatus.RUNNING.value:
        server.status = ServerStatus.STOPPED.value
    await session.commit()


async def delete_snapshot(server: Server, snapshot_id: str) -> None:
    await run_in_threadpool(orchestrator.delete_snapshot, server.id, snapshot_id)


async def list_servers(session: AsyncSession) -> list[Server]:
    result = await session.execute(select(Server).order_by(Server.created_at))
    return list(result.scalars().all())


async def get_server(session: AsyncSession, server_id: str) -> Server | None:
    return await session.get(Server, server_id)


# -- environment builders -----------------------------------------------------


def _base_steam_env(server: Server, creds: dict[str, str] | None) -> dict[str, str]:
    env: dict[str, str] = {"STEAM_APP_ID": str(server.app_id), "INSTALL_DIR": "/data"}
    if server.steam_branch:
        env["STEAM_BRANCH"] = server.steam_branch
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


def build_runtime_env(
    server: Server,
    creds: dict[str, str] | None = None,
    workshop: WorkshopRuntime | None = None,
) -> dict[str, str]:
    # The long-lived server container NEVER runs steamcmd: installs/updates always
    # happen in a separate one-shot container (so progress shows as installing/
    # updating, never hidden behind a misleading "running" status).
    env = _base_steam_env(server, creds)
    env["RUN_INSTALL"] = "0"
    env["VALIDATE"] = "0"
    env["STARTUP_CMD"] = render_startup_for(server)
    # Static, operator-defined env from the template (e.g. SteamAppId for Valheim).
    template = get_template(server.template_id)
    for key, value in template.env.items():
        env[key] = str(value)
    # Expose declared variables to the startup script's environment too.
    for key, value in server.variables.items():
        env[key] = str(value)
    # ...and the allocated ports, so prestart hooks can write them into the
    # game's own config (e.g. a query/RCON port the CLI can't set).
    for key, value in port_map(server).items():
        env[key] = str(value)
    if template.prestart_hook:
        env["PRESTART_HOOK"] = template.prestart_hook
    if workshop is not None:
        env["WORKSHOP_ITEMS"] = ";".join(workshop.items)
        if workshop.mod_ids is not None:
            # Enabled mod ids in the user's load order (+ their maps); without
            # them the prestart hook falls back to auto-detecting every mod.
            env["WORKSHOP_MOD_IDS"] = ";".join(workshop.mod_ids)
            env["WORKSHOP_MAPS"] = ";".join(workshop.maps or [])
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


# steamcmd surfaces the real cause on lines like "ERROR! Failed to install ...".
_ERROR_LINE_RE = re.compile(r"^.*(?:ERROR!|FAILED|Fatal Error).*$", re.MULTILINE | re.IGNORECASE)
_ERROR_MESSAGE_MAX = 4000


def summarize_failure(logs: str, code: int) -> str:
    """Build a user-facing error message that leads with steamcmd's own error.

    The full log is always written to the application log; this returns a bounded
    summary (highlighted error lines + recent tail) for the `error_message` field.
    """
    if not logs:
        return f"install failed (exit code {code})"
    error_lines = _ERROR_LINE_RE.findall(logs)
    highlight = ""
    if error_lines:
        highlight = "\n".join(dict.fromkeys(error_lines)) + "\n\n--- recent output ---\n"
    return (highlight + logs)[-_ERROR_MESSAGE_MAX:]


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
    except DockerError as exc:
        logs = f"orchestration error: {exc}"
        logger.error("install job orchestration failed for %s: %s", server_id, exc)
    except Exception as exc:  # noqa: BLE001 — last-resort guard so a job never crashes the panel
        logs = f"unexpected error: {exc}"
        logger.exception("install job crashed for %s", server_id)

    if code != 0:
        logger.error("install failed for %s (exit %s):\n%s", server_id, code, logs)

    notify: tuple[str, str, str | None] | None = None
    async with SessionLocal() as session:
        server = await session.get(Server, server_id)
        if server is None:
            return
        if code != 0:
            server.status = ServerStatus.ERRORED.value
            server.error_message = summarize_failure(logs, code)
            notify = ("error", "Install failed", _notif_excerpt(server.error_message))
        elif then_start:
            try:
                await _do_start(session, server, runtime_creds)
            except DockerError as exc:
                server.status = ServerStatus.ERRORED.value
                server.error_message = f"install ok but start failed: {exc}"
                await session.commit()
                notify = ("error", "Server failed to start", str(exc)[:200])
        else:
            server.status = success_status.value
            server.error_message = None
            notify = ("success", "Install complete", None)
        await session.commit()
    if notify is not None:
        await notification_service.notify(*notify, server_id=server_id)
    logger.info("install job for %s finished (code=%s, then_start=%s)", server_id, code, then_start)


async def _resolve_install_outcome(
    session: AsyncSession, server: Server, code: int, logs: str
) -> None:
    """Persist the terminal state of a finished install (STOPPED or ERRORED)."""
    if code == 0:
        server.status = ServerStatus.STOPPED.value
        server.error_message = None
    else:
        server.status = ServerStatus.ERRORED.value
        server.error_message = summarize_failure(logs, code)
    await session.commit()


async def _resume_install_job(server_id: str) -> None:
    """Re-attach to an install container that outlived a panel restart."""
    code, logs = -1, ""
    try:
        code, logs = await run_in_threadpool(orchestrator.wait_install, server_id)
    except DockerError as exc:
        logs = f"orchestration error: {exc}"
        logger.error("resumed install failed for %s: %s", server_id, exc)
    except Exception as exc:  # noqa: BLE001 — last-resort guard
        logs = f"unexpected error: {exc}"
        logger.exception("resumed install crashed for %s", server_id)
    async with SessionLocal() as session:
        server = await session.get(Server, server_id)
        if server is not None:
            await _resolve_install_outcome(session, server, code, logs)


async def recover_inflight_on_boot(session: AsyncSession) -> None:
    """Resolve servers left INSTALLING/UPDATING by a panel crash/restart.

    - install container still running  -> resume waiting on it
    - install container finished        -> record its exit outcome
    - install container gone            -> mark ERRORED (must be retried)
    """
    result = await session.execute(select(Server).where(Server.status.in_(INFLIGHT)))
    for server in result.scalars().all():
        try:
            st = await run_in_threadpool(orchestrator.install_state, server.id)
        except DockerError as exc:
            logger.warning("boot recovery: cannot check %s: %s", server.id, exc)
            continue
        if st.exists and st.status == "running":
            asyncio.create_task(_resume_install_job(server.id))
            logger.info("boot recovery: resuming in-flight install for %s", server.id)
        elif st.exists:
            code = st.exit_code if st.exit_code is not None else -1
            logs = await run_in_threadpool(orchestrator.recent_install_logs, server.id, 200)
            await _resolve_install_outcome(session, server, code, logs)
            logger.info("boot recovery: resolved finished install for %s (code=%s)", server.id, code)
        else:
            server.status = ServerStatus.ERRORED.value
            server.error_message = "install/update was interrupted by a panel restart — please retry"
            await session.commit()
            logger.info("boot recovery: marked interrupted install for %s as errored", server.id)


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
    await _stop_container(server)
    server.status = ServerStatus.UPDATING.value
    server.error_message = None
    await session.commit()
    env = build_install_env(server, creds)
    asyncio.create_task(_install_job(server.id, env, ServerStatus.STOPPED))


async def _stop_container(server: Server) -> None:
    """Stop the server container, letting the game save + exit on its own first
    when its template defines a `stop_command` (e.g. Project Zomboid's `quit`)."""
    command, timeout = None, DEFAULT_STOP_TIMEOUT
    try:
        template = get_template(server.template_id)
        command, timeout = template.stop_command, template.stop_timeout
    except Exception:  # noqa: BLE001 — unknown/removed template: plain stop
        pass
    await run_in_threadpool(orchestrator.stop, server.id, timeout, command)


async def _do_start(
    session: AsyncSession, server: Server, creds: dict[str, str] | None
) -> None:
    """Create + start the long-lived server container (no steamcmd here)."""
    env = build_runtime_env(server, creds, await load_order_service.runtime(session, server))
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
    # "Every startup" workshop auto-update: refresh mods in the background (they
    # apply on the following start, matching the panel's general workshop model).
    if server.workshop_auto_update == "startup":
        from app.services import workshop_service  # late import avoids a cycle

        asyncio.create_task(workshop_service.run_auto_update(server.id, restart=False))
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
    await _stop_container(server)
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
    # Graceful stop + fresh container (not `docker restart`): the game gets to
    # save, and the new container picks up current env/mods/prestart hook.
    await _stop_container(server)
    await _do_start(session, server, creds)


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
    *,
    steam_branch: str | None = None,
    set_branch: bool = False,
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
    if set_branch:
        server.steam_branch = steam_branch or None
    await session.commit()
    await session.refresh(server)
    return server


# -- state reconciliation -----------------------------------------------------


# An in-flight install/update older than this with no live container is stuck.
_STALE_INFLIGHT = timedelta(seconds=2 * 3600)


async def _backfill_workshop(session: AsyncSession, server: Server) -> None:
    """Self-heal `workshop_app_id` for servers created before workshop support
    existed (or before their template declared workshop). Runs once per server —
    after the first access it's a no-op."""
    if server.workshop_app_id is not None:
        return
    try:
        template = get_template(server.template_id)
    except Exception:  # noqa: BLE001 — unknown/removed template: nothing to backfill
        return
    if template.workshop is not None:
        server.workshop_app_id = template.workshop.app_id
        await session.commit()


async def reconcile(session: AsyncSession, server: Server) -> Server:
    """Align the persisted status with the live container state.

    In-flight installs/updates are normally owned by a background job; here we
    only step in when the job is demonstrably gone (its install container exited
    or vanished while the row is stale), so a crashed job can't strand a server.
    """
    await _backfill_workshop(session, server)
    if server.status in INFLIGHT:
        return await _reconcile_inflight(session, server)
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
        crashed_now = (
            new_status == ServerStatus.ERRORED.value
            and server.status == ServerStatus.RUNNING.value
        )
        server.status = new_status
        await session.commit()
        if crashed_now:
            await notification_service.notify(
                "error",
                "Server crashed",
                f"The container exited unexpectedly (exit code {state.exit_code}).",
                server.id,
            )
    return server


async def _reconcile_inflight(session: AsyncSession, server: Server) -> Server:
    """Resolve a stuck INSTALLING/UPDATING row when its job is no longer alive."""
    try:
        st = await run_in_threadpool(orchestrator.install_state, server.id)
    except DockerError:
        return server  # agent hiccup — leave the row for the next poll
    if st.exists and st.status == "running":
        return server  # a job is still legitimately installing
    if st.exists:
        # Container finished but the row was never updated — the waiter died.
        code = st.exit_code if st.exit_code is not None else -1
        logs = await run_in_threadpool(orchestrator.recent_install_logs, server.id, 200)
        await _resolve_install_outcome(session, server, code, logs)
    elif _is_stale(server):
        server.status = ServerStatus.ERRORED.value
        server.error_message = "install/update stalled with no active job — please retry"
        await session.commit()
    return server


def _is_stale(server: Server) -> bool:
    updated = server.updated_at
    if updated is None:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated > _STALE_INFLIGHT
