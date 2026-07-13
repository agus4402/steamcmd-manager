"""Steam Workshop mod management.

Mods are downloaded via steamcmd in a one-shot container (in the agent) into the
server's data volume. Downloads can take minutes, so they run as background jobs:
a WorkshopMod row is created with status ``installing`` and the UI polls it until
it becomes ``installed`` or ``error``.
"""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

import app.workshop  # noqa: F401 — importing registers all workshop providers
from app.db import SessionLocal
from app.models.server import Server, ServerStatus
from app.models.workshop_mod import WorkshopMod
from app.services import notification_service
from app.services.docker_orchestrator import DockerError, orchestrator
from app.services.template_loader import get_template
from app.workshop.base import (
    ModDetails,
    ModSummary,
    SearchResult,
    WorkshopProvider,
    WorkshopProviderError,
    WorkshopSort,
)
from app.workshop.registry import get_provider

logger = logging.getLogger("steamcmd-manager.workshop")

_DEFAULT_INSTALL_PATH = "steamapps/workshop"
_ID_IN_URL_RE = re.compile(r"[?&]id=(\d{2,20})")
_LONG_NUMBER_RE = re.compile(r"(\d{4,20})")
_TOKEN_RE = re.compile(r"\d{2,20}")

# Bounded download concurrency: queued mods wait on this semaphore, so the queue
# is just tasks blocked here. Status shows "queued" until a slot is acquired.
_MAX_CONCURRENT_DOWNLOADS = 2
_DEP_DEPTH_CAP = 5
_download_sem: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    # Lazily created so it binds to the running event loop.
    global _download_sem
    if _download_sem is None:
        _download_sem = asyncio.Semaphore(_MAX_CONCURRENT_DOWNLOADS)
    return _download_sem


class WorkshopError(RuntimeError):
    """Domain error the API layer turns into a 4xx."""


def _provider(provider_id: str = "steam") -> WorkshopProvider:
    provider = get_provider(provider_id)
    if provider is None:
        raise WorkshopError(f"unknown workshop provider '{provider_id}'")
    return provider


def parse_item_id(raw: str) -> str:
    """Extract a numeric workshop item id from a raw id or a workshop URL."""
    raw = raw.strip()
    m = _ID_IN_URL_RE.search(raw)
    if m:
        return m.group(1)
    if raw.isdigit():
        return raw
    m = _LONG_NUMBER_RE.search(raw)
    if m:
        return m.group(1)
    raise WorkshopError("could not parse a Steam Workshop item id from that input")


def parse_many(raw: str) -> tuple[list[str], list[str]]:
    """Parse a blob (commas / spaces / newlines, ids or workshop URLs) into a
    de-duplicated, order-preserving list of item ids. Returns (ids, unparsed)
    where ``unparsed`` are non-empty tokens no id could be extracted from."""
    ids: list[str] = []
    seen: set[str] = set()
    unparsed: list[str] = []
    for token in re.split(r"[\s,]+", raw.strip()):
        if not token:
            continue
        m = _ID_IN_URL_RE.search(token) or _TOKEN_RE.search(token)
        if not m:
            unparsed.append(token)
            continue
        iid = m.group(1) if m.re is _ID_IN_URL_RE else m.group(0)
        if iid not in seen:
            seen.add(iid)
            ids.append(iid)
    return ids, unparsed


def _install_path_for(server: Server) -> str:
    try:
        template = get_template(server.template_id)
        if template.workshop:
            return template.workshop.install_path
    except Exception:  # noqa: BLE001 — template may have changed; fall back to default
        pass
    return _DEFAULT_INSTALL_PATH


def _apply_summary(mod: WorkshopMod, s: ModSummary) -> None:
    """Copy fetched metadata onto a mod row (leaves a user-set name intact)."""
    mod.title = s.title or mod.title
    mod.author_id = s.author_id or mod.author_id
    mod.author_name = s.author_name or mod.author_name
    mod.preview_url = s.preview_url or mod.preview_url
    mod.subscribers = s.subscribers or mod.subscribers
    mod.favorites = s.favorites or mod.favorites
    if s.file_size:
        mod.file_size = s.file_size
    mod.time_updated_remote = s.time_updated or mod.time_updated_remote


async def _fetch_summary(item_id: str, provider_id: str = "steam") -> ModSummary | None:
    """Best-effort metadata for one item; never raises."""
    try:
        rows = await _provider(provider_id).get_summaries([item_id])
        return rows[0] if rows else None
    except WorkshopProviderError as exc:
        logger.info("metadata lookup failed for %s: %s", item_id, exc)
        return None


async def get_mod_details(item_id: str, provider_id: str = "steam") -> ModDetails:
    """Full metadata + dependencies for the details drawer."""
    try:
        return await _provider(provider_id).get_details(item_id)
    except WorkshopProviderError as exc:
        raise WorkshopError(str(exc)) from exc


async def search(
    *,
    query: str,
    app_id: int,
    page: int = 1,
    page_size: int = 30,
    sort_by: str | None = None,
    provider_id: str = "steam",
) -> SearchResult:
    """Search a provider's catalog. Raises WorkshopError (e.g. when search needs
    an API key that isn't configured)."""
    try:
        sort = WorkshopSort(sort_by) if sort_by else WorkshopSort.POPULAR
    except ValueError:
        sort = WorkshopSort.POPULAR
    try:
        return await _provider(provider_id).search(
            query=query, app_id=app_id, page=max(1, page), page_size=page_size, sort=sort
        )
    except WorkshopProviderError as exc:
        raise WorkshopError(str(exc)) from exc


async def list_mods(session: AsyncSession, server_id: str) -> list[WorkshopMod]:
    result = await session.execute(
        select(WorkshopMod)
        .where(WorkshopMod.server_id == server_id)
        .order_by(WorkshopMod.created_at)
    )
    return list(result.scalars().all())


async def _existing_item_ids(session: AsyncSession, server_id: str) -> set[str]:
    rows = await session.execute(
        select(WorkshopMod.item_id).where(WorkshopMod.server_id == server_id)
    )
    return {r[0] for r in rows.all()}


async def _resolve_dependency_ids(root_item_id: str) -> list[str]:
    """Transitive dependency item ids for a mod (excludes the root). Best-effort:
    returns [] when the provider can't resolve deps (e.g. no API key). Guards
    against cycles and runaway depth."""
    provider = _provider()
    seen: set[str] = {root_item_id}
    order: list[str] = []
    frontier: list[tuple[str, int]] = [(root_item_id, 0)]
    while frontier:
        item, depth = frontier.pop(0)
        if depth >= _DEP_DEPTH_CAP:
            continue
        try:
            deps = await provider.get_dependencies(item)
        except WorkshopProviderError as exc:
            logger.info("dependency lookup failed for %s: %s", item, exc)
            continue
        for d in deps:
            if d.item_id not in seen:
                seen.add(d.item_id)
                order.append(d.item_id)
                frontier.append((d.item_id, depth + 1))
    return order


async def _create_mod(
    session: AsyncSession,
    server: Server,
    item_id: str,
    *,
    name: str | None = None,
    is_dependency: bool = False,
    required_by: str | None = None,
    resolve_deps: bool = True,
) -> WorkshopMod:
    """Create a mod row (with best-effort metadata), enqueue its download, and —
    for top-level mods — auto-enqueue any missing transitive dependencies."""
    mod = WorkshopMod(
        server_id=server.id,
        item_id=item_id,
        name=name,
        status="queued",
        is_dependency=is_dependency,
        required_by=required_by,
    )
    summary = await _fetch_summary(item_id)
    if summary is not None:
        _apply_summary(mod, summary)
    session.add(mod)
    await session.commit()
    await session.refresh(mod)
    asyncio.create_task(_download_job(server.id, mod.id))

    if resolve_deps:
        dep_ids = await _resolve_dependency_ids(item_id)
        if dep_ids:
            existing = await _existing_item_ids(session, server.id)
            for dep in dep_ids:
                if dep in existing:
                    continue
                existing.add(dep)
                await _create_mod(
                    session,
                    server,
                    dep,
                    is_dependency=True,
                    required_by=item_id,
                    resolve_deps=False,
                )
    return mod


async def add_mod(
    session: AsyncSession, server: Server, raw_item: str, name: str | None
) -> WorkshopMod:
    if server.workshop_app_id is None:
        raise WorkshopError("this game does not support Steam Workshop")
    item_id = parse_item_id(raw_item)
    if item_id in await _existing_item_ids(session, server.id):
        raise WorkshopError("that workshop item is already added")
    return await _create_mod(session, server, item_id, name=name)


async def import_preview(server: Server, raw: str) -> tuple[list[dict], list[str]]:
    """Parse a bulk-import blob into a preview (no install). Returns
    (items, unparsed) where each item is a dict matching ImportPreviewItem."""
    if server.workshop_app_id is None:
        raise WorkshopError("this game does not support Steam Workshop")
    ids, unparsed = parse_many(raw)
    if not ids:
        return [], unparsed

    # A single id may be a collection: expand it into its members.
    if len(ids) == 1:
        try:
            members = await _provider().resolve_collection(ids[0])
        except WorkshopProviderError:
            members = []
        if members:
            ids = members

    # Detect duplicates already filtered by parse_many; here flag installed ones.
    async with SessionLocal() as session:
        installed = await _existing_item_ids(session, server.id)

    summaries: dict[str, ModSummary] = {}
    try:
        for s in await _provider().get_summaries(ids):
            summaries[s.item_id] = s
    except WorkshopProviderError as exc:
        logger.info("import metadata lookup failed: %s", exc)

    items: list[dict] = []
    for iid in ids:
        s = summaries.get(iid)
        items.append(
            {
                "item_id": iid,
                "title": s.title if s else None,
                "preview_url": s.preview_url if s else None,
                "file_size": s.file_size if s else 0,
                "installed": iid in installed,
                "duplicate": False,
                "missing": s is None,
            }
        )
    return items, unparsed


async def import_install(
    session: AsyncSession, server: Server, item_ids: list[str]
) -> tuple[list[WorkshopMod], list[str]]:
    """Queue the given item ids for install, skipping already-installed ones."""
    if server.workshop_app_id is None:
        raise WorkshopError("this game does not support Steam Workshop")
    installed = await _existing_item_ids(session, server.id)
    queued: list[WorkshopMod] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for iid in item_ids:
        if iid in installed or iid in seen:
            skipped.append(iid)
            continue
        seen.add(iid)
        queued.append(await _create_mod(session, server, iid))
    return queued, skipped


async def remove_mod(session: AsyncSession, server: Server, mod: WorkshopMod) -> None:
    # Can't safely delete files mid-download; refuse until the job settles.
    if mod.status == "downloading":
        raise WorkshopError("this mod is downloading; wait for it to finish first")
    # A queued mod was never written to disk — just drop the row (its waiting job
    # no-ops when it finds the row gone).
    if mod.status != "queued":
        try:
            await run_in_threadpool(
                orchestrator.remove_workshop_item, server.id, _install_path_for(server), mod.item_id
            )
        except DockerError as exc:
            raise WorkshopError(str(exc)) from exc
    await session.delete(mod)
    await session.commit()


async def retry_mod(session: AsyncSession, server: Server, mod: WorkshopMod) -> WorkshopMod:
    if mod.status not in ("error", "missing_dependency"):
        raise WorkshopError("only failed mods can be retried")
    mod.status = "queued"
    mod.error_message = None
    await session.commit()
    await session.refresh(mod)
    asyncio.create_task(_download_job(server.id, mod.id))
    return mod


async def _download_job(server_id: str, mod_id: str) -> None:
    # Wait for a download slot (this is the "queue"); the row shows "queued" until
    # a slot is free, then flips to "downloading".
    async with _sem():
        async with SessionLocal() as session:
            mod = await session.get(WorkshopMod, mod_id)
            server = await session.get(Server, server_id)
            if mod is None or server is None:
                return  # cancelled while queued
            mod.status = "downloading"
            await session.commit()
            item_id = mod.item_id
            app_id = server.workshop_app_id
            install_path = _install_path_for(server)

        if app_id is None:
            await _finish(mod_id, code=2, logs="workshop is not configured for this server")
            return

        code, logs = -1, ""
        try:
            code, logs = await run_in_threadpool(
                orchestrator.download_workshop_item, server_id, app_id, item_id, install_path
            )
        except DockerError as exc:
            logs = f"orchestration error: {exc}"
            logger.error("workshop download failed for %s/%s: %s", server_id, item_id, exc)
        except Exception as exc:  # noqa: BLE001 — never let a job crash the panel
            logs = f"unexpected error: {exc}"
            logger.exception("workshop download crashed for %s/%s", server_id, item_id)

    await _finish(mod_id, code, logs)
    if code != 0:
        await notification_service.notify(
            "error", "Workshop install failed", f"Item {item_id} could not be downloaded.", server_id
        )


async def _finish(mod_id: str, code: int, logs: str) -> None:
    async with SessionLocal() as session:
        mod = await session.get(WorkshopMod, mod_id)
        if mod is None:
            return
        if code == 0:
            mod.status = "installed"
            mod.error_message = None
            # Record the version we just installed so update checks can compare.
            mod.installed_time_updated = mod.time_updated_remote
        else:
            mod.status = "error"
            mod.error_message = (logs or "download failed").strip()[-500:]
        await session.commit()


# -- updates ------------------------------------------------------------------


async def _requeue(session: AsyncSession, server: Server, mod: WorkshopMod) -> WorkshopMod:
    mod.status = "queued"
    mod.error_message = None
    await session.commit()
    await session.refresh(mod)
    asyncio.create_task(_download_job(server.id, mod.id))
    return mod


async def update_mod(session: AsyncSession, server: Server, mod: WorkshopMod) -> WorkshopMod:
    if mod.status not in ("installed", "update_available"):
        raise WorkshopError("only installed mods can be updated")
    return await _requeue(session, server, mod)


async def update_all(session: AsyncSession, server: Server) -> list[WorkshopMod]:
    rows = (
        await session.execute(
            select(WorkshopMod).where(
                WorkshopMod.server_id == server.id,
                WorkshopMod.status == "update_available",
            )
        )
    ).scalars().all()
    return [await _requeue(session, server, m) for m in rows]


async def check_updates(server_id: str) -> int:
    """Refresh remote metadata for installed mods and flag those with a newer
    remote version as ``update_available``. Returns how many were newly flagged."""
    async with SessionLocal() as session:
        mods = (
            await session.execute(
                select(WorkshopMod).where(
                    WorkshopMod.server_id == server_id,
                    WorkshopMod.status.in_(["installed", "update_available"]),
                )
            )
        ).scalars().all()
        if not mods:
            return 0
        try:
            summaries = {
                s.item_id: s for s in await _provider().get_summaries([m.item_id for m in mods])
            }
        except WorkshopProviderError as exc:
            logger.info("update check failed for %s: %s", server_id, exc)
            return 0

        flagged = 0
        for m in mods:
            s = summaries.get(m.item_id)
            if s is None or s.time_updated is None:
                continue
            _apply_summary(m, s)  # refreshes time_updated_remote + counts
            if m.installed_time_updated is None or s.time_updated > m.installed_time_updated:
                if m.status != "update_available":
                    flagged += 1
                m.status = "update_available"
        await session.commit()
        return flagged


async def run_auto_update(server_id: str, *, restart: bool = True) -> int:
    """Check for updates, download outdated mods to completion, then optionally
    restart the server if it's running. Used by the scheduler and startup hook."""
    from app.services import server_service  # late import avoids an import cycle

    await check_updates(server_id)
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(WorkshopMod).where(
                    WorkshopMod.server_id == server_id,
                    WorkshopMod.status == "update_available",
                )
            )
        ).scalars().all()
        for m in rows:
            m.status = "queued"
            m.error_message = None
        await session.commit()
        mod_ids = [m.id for m in rows]

    if not mod_ids:
        return 0

    # Await the downloads (bounded by the same semaphore) so updates are applied
    # before we restart.
    await asyncio.gather(*(_download_job(server_id, mid) for mid in mod_ids))
    await notification_service.notify(
        "success", "Workshop mods updated", f"{len(mod_ids)} mod(s) updated.", server_id
    )

    if restart:
        async with SessionLocal() as session:
            server = await session.get(Server, server_id)
            if server is not None and server.status == ServerStatus.RUNNING.value:
                try:
                    await server_service.restart_server(session, server)
                except Exception:  # noqa: BLE001 — update succeeded; restart is best-effort
                    logger.exception("post-update restart failed for %s", server_id)
    return len(mod_ids)


# -- sync ---------------------------------------------------------------------


async def sync_mods(session: AsyncSession, server: Server) -> dict[str, int]:
    """Reconcile DB rows against what's actually on disk: create rows for items
    found on disk but not tracked, and flag tracked rows whose files are gone."""
    if server.workshop_app_id is None:
        raise WorkshopError("this game does not support Steam Workshop")
    try:
        on_disk = set(
            await run_in_threadpool(
                orchestrator.list_workshop_items, server.id, _install_path_for(server)
            )
        )
    except DockerError as exc:
        raise WorkshopError(str(exc)) from exc

    rows = await list_mods(session, server.id)
    tracked = {m.item_id: m for m in rows}

    restored = 0
    missing = 0
    # Items on disk we don't know about -> create installed rows (hydrate later).
    new_ids = [iid for iid in on_disk if iid not in tracked]
    summaries: dict[str, ModSummary] = {}
    if new_ids:
        try:
            summaries = {s.item_id: s for s in await _provider().get_summaries(new_ids)}
        except WorkshopProviderError:
            summaries = {}
    for iid in new_ids:
        mod = WorkshopMod(server_id=server.id, item_id=iid, status="installed")
        s = summaries.get(iid)
        if s is not None:
            _apply_summary(mod, s)
            mod.installed_time_updated = s.time_updated
        session.add(mod)
        restored += 1

    # Tracked-but-installed rows whose files vanished -> flag as error.
    for m in rows:
        if m.status in ("installed", "update_available") and m.item_id not in on_disk:
            m.status = "error"
            m.error_message = "files missing on disk (removed outside the panel)"
            missing += 1

    await session.commit()
    return {"restored": restored, "missing": missing, "on_disk": len(on_disk)}
