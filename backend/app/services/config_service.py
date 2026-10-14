"""Config editor: list / read / write a server's game config files.

The template's `config_files` + `config_dirs` are the whitelist of what may be
touched in the server's data dir (the agent adds generic path checks on top).
Declared files with a structured `format` are also exposed as form fields
(see app/config_formats) and can be edited by changing individual values.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config_formats import ini, pz_sandbox
from app.config_formats.base import ConfigField, validate_value
from app.models.server import Server, ServerStatus
from app.schemas.template import ConfigFileSpec, GameTemplate
from app.services import server_service
from app.services.docker_orchestrator import orchestrator
from app.services.template_loader import get_template

logger = logging.getLogger("steamcmd-manager.config")

BACKUP_SUFFIX = ".panel-bak"
TREE_DEPTH = 4


class ConfigError(RuntimeError):
    """Domain error the API layer turns into a 4xx."""


class NotAllowed(ConfigError):
    pass


class Conflict(ConfigError):
    pass


class NotFound(ConfigError):
    pass


def _template(server: Server) -> GameTemplate:
    return get_template(server.template_id)


def _spec_for(template: GameTemplate, path: str) -> ConfigFileSpec | None:
    return next((f for f in template.config_files if f.path == path), None)


def check_allowed(template: GameTemplate, path: str) -> ConfigFileSpec | None:
    """Raise NotAllowed unless `path` is a declared file or lives under a
    declared config dir. Returns the file's spec when it is a declared one."""
    path = path.strip()
    parts = path.split("/")
    if not path or path.startswith("/") or ".." in parts or "" in parts:
        raise NotAllowed("invalid path")
    spec = _spec_for(template, path)
    if spec is not None:
        return spec
    if any(path.startswith(d + "/") for d in template.config_dirs):
        return None
    raise NotAllowed("this file is not editable from the panel")


def _fields(spec: ConfigFileSpec | None, text: str) -> list[ConfigField] | None:
    if spec is None or spec.format == "text":
        return None
    if spec.format == "ini":
        return ini.parse(text, set(spec.managed_keys))
    return pz_sandbox.parse(text)


def _apply(spec: ConfigFileSpec, text: str, changes: dict[str, str]) -> str:
    fields = {f.path: f for f in _fields(spec, text) or []}
    clean: dict[str, str] = {}
    for path, value in changes.items():
        f = fields.get(path)
        if f is None:
            raise ConfigError(f"unknown setting: {path}")
        if f.managed:
            raise ConfigError(
                f"{path} is managed by the panel; change it in Config → Variables instead"
            )
        try:
            clean[path] = validate_value(f, value)
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    if spec.format == "ini":
        return ini.apply(text, clean)
    return pz_sandbox.apply(text, clean)


async def list_files(server: Server) -> dict:
    template = _template(server)
    entries: dict[str, dict] = {}
    roots = {f.path.rsplit("/", 1)[0] for f in template.config_files} | set(template.config_dirs)
    for root in sorted(roots):
        for e in await run_in_threadpool(orchestrator.list_files, server.id, root, TREE_DEPTH):
            entries[e.path] = asdict(e)
    declared = []
    for f in template.config_files:
        e = entries.get(f.path)
        declared.append(
            {
                "path": f.path,
                "label": f.label,
                "format": f.format,
                "exists": e is not None,
                "size": e["size"] if e else 0,
                "mtime": e["mtime"] if e else 0,
                "has_backup": f.path + BACKUP_SUFFIX in entries,
            }
        )
    tree = [
        {**e, "has_backup": e["path"] + BACKUP_SUFFIX in entries}
        for p, e in sorted(entries.items())
        if any(p == d or p.startswith(d + "/") for d in template.config_dirs)
        and not p.endswith(BACKUP_SUFFIX)
    ]
    return {"files": declared, "tree": tree, "dirs": template.config_dirs}


async def read(server: Server, path: str) -> dict:
    spec = check_allowed(_template(server), path)
    result = await run_in_threadpool(orchestrator.read_file, server.id, path)
    if result is None:
        raise NotFound("file does not exist yet — start the server once to generate it")
    raw, mtime = result
    text = raw.decode("utf-8", "replace")
    fields = _fields(spec, text)
    return {
        "path": path,
        "content": text,
        "mtime": mtime,
        "format": spec.format if spec else "text",
        "fields": [asdict(f) for f in fields] if fields is not None else None,
    }


async def write(
    session: AsyncSession,
    server: Server,
    path: str,
    *,
    content: str | None,
    changes: dict[str, str] | None,
    base_mtime: int | None,
    restart: bool,
) -> dict:
    """Write a whole file (`content`) or individual settings (`changes`).

    With `restart` on a running server: graceful stop → write → start, so the
    game can't overwrite the edit while shutting down.
    """
    spec = check_allowed(_template(server), path)
    if (content is None) == (changes is None):
        raise ConfigError("send either content or changes")
    if changes is not None and (spec is None or spec.format == "text"):
        raise ConfigError("this file has no structured editor; send content")

    running = server.status == ServerStatus.RUNNING.value
    if restart and running:
        await server_service._stop_container(server)

    current = await run_in_threadpool(orchestrator.read_file, server.id, path)
    if base_mtime is not None and current is not None and current[1] != base_mtime:
        if restart and running:
            await server_service._do_start(session, server, None)
        raise Conflict("the file changed since it was opened; reload and try again")

    if changes is not None:
        if current is None:
            raise NotFound("file does not exist yet — start the server once to generate it")
        newline_text = _apply(spec, current[0].decode("utf-8", "replace"), changes)
        data = newline_text.encode("utf-8")
    else:
        data = content.encode("utf-8")

    try:
        mtime = await run_in_threadpool(orchestrator.write_file, server.id, path, data)
    finally:
        if restart and running:
            await server_service._do_start(session, server, None)
    logger.info("wrote %s on server %s (%d bytes)", path, server.id, len(data))
    return {"path": path, "mtime": mtime, "restarted": restart and running}


async def restore_backup(session: AsyncSession, server: Server, path: str, restart: bool) -> dict:
    """Swap the file with its `.panel-bak` copy (the version before the last save)."""
    check_allowed(_template(server), path)
    backup = await run_in_threadpool(orchestrator.read_file, server.id, path + BACKUP_SUFFIX)
    if backup is None:
        raise NotFound("there is no previous version of this file")
    return await write(
        session,
        server,
        path,
        content=backup[0].decode("utf-8", "replace"),
        changes=None,
        base_mtime=None,
        restart=restart,
    )
