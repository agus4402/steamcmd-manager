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
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

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

# Download queue: ONE worker drains it, taking up to _BATCH_SIZE queued mods of
# the same server per steamcmd session. One session at a time because every
# download shares the steamcmd cache volume (concurrent steamcmd processes on
# the same Steam root clobber each other), and one login per batch instead of
# per item because Steam throttles bursts of logins.
_BATCH_SIZE = 10
_DEP_DEPTH_CAP = 5
_pending: list[tuple[str, str, asyncio.Future[None]]] = []  # (server_id, mod_id, done)
_worker: asyncio.Task | None = None
_RESULT_RE = re.compile(r"^\[workshop-result\] (\d+) (ok|failed)(?: (.*))?$", re.MULTILINE)


# Strong refs to fire-and-forget tasks: the loop only keeps weak ones, so an
# unreferenced task can be garbage-collected mid-run.
_background: set[asyncio.Task] = set()


def _spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


class IsCollection(RuntimeError):
    """The item is a Workshop collection: import its members instead."""


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


async def _fetch_summaries(
    item_ids: list[str], provider_id: str = "steam"
) -> dict[str, ModSummary]:
    """Best-effort batch metadata keyed by item id; never raises."""
    if not item_ids:
        return {}
    try:
        return {s.item_id: s for s in await _provider(provider_id).get_summaries(item_ids)}
    except WorkshopProviderError as exc:
        logger.info("metadata lookup failed for %d item(s): %s", len(item_ids), exc)
        return {}


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


async def _resolve_dependencies(root_ids: list[str]) -> dict[str, str]:
    """Transitive dependencies of several items as ``{dep_id: required_by}``,
    where ``required_by`` is the root item that pulled it in (discovery order;
    roots excluded). One batched lookup per depth level. Best-effort: {} when
    the provider can't resolve deps (e.g. no API key). Guards against cycles
    and runaway depth."""
    provider = _provider()
    seen: set[str] = set(root_ids)
    found: dict[str, str] = {}
    frontier: dict[str, str] = {r: r for r in root_ids}  # item -> its root
    for _ in range(_DEP_DEPTH_CAP):
        if not frontier:
            break
        try:
            deps_by_item = await provider.get_dependencies_many(list(frontier))
        except WorkshopProviderError as exc:
            logger.info("dependency lookup failed: %s", exc)
            break
        nxt: dict[str, str] = {}
        for item, root in frontier.items():
            for d in deps_by_item.get(item, []):
                if d.item_id not in seen:
                    seen.add(d.item_id)
                    found[d.item_id] = root
                    nxt[d.item_id] = root
        frontier = nxt
    return found


@dataclass(slots=True)
class _NewMod:
    item_id: str
    name: str | None = None
    is_dependency: bool = False
    required_by: str | None = None


async def _enqueue(
    session: AsyncSession, server: Server, new: list[_NewMod], *, resolve_deps: bool = True
) -> list[WorkshopMod]:
    """Create rows for ``new`` (one batched metadata lookup, one commit), queue
    their downloads and return right away. Missing transitive dependencies are
    resolved and queued in the background, so a big collection never holds the
    request open."""
    if not new:
        return []
    summaries = await _fetch_summaries([n.item_id for n in new])
    # Distinct, increasing timestamps keep the given order (e.g. a collection's)
    # wherever mods are sorted by when they were added.
    base = datetime.now(timezone.utc)
    mods: list[WorkshopMod] = []
    for i, n in enumerate(new):
        mod = WorkshopMod(
            server_id=server.id,
            item_id=n.item_id,
            name=n.name,
            status="queued",
            is_dependency=n.is_dependency,
            required_by=n.required_by,
            created_at=base + timedelta(microseconds=i),
        )
        if (s := summaries.get(n.item_id)) is not None:
            _apply_summary(mod, s)
        session.add(mod)
        mods.append(mod)
    await session.commit()
    for mod in mods:
        await session.refresh(mod)
        _spawn(_download_job(server.id, mod.id))
    if resolve_deps:
        _spawn(_enqueue_dependencies(server.id, [n.item_id for n in new]))
    return mods


async def _enqueue_dependencies(server_id: str, root_ids: list[str]) -> None:
    """Background job: queue the missing transitive dependencies of ``root_ids``."""
    try:
        found = await _resolve_dependencies(root_ids)
        if not found:
            return
        async with SessionLocal() as session:
            server = await session.get(Server, server_id)
            if server is None:
                return
            existing = await _existing_item_ids(session, server_id)
            new = [
                _NewMod(item_id=dep, is_dependency=True, required_by=root)
                for dep, root in found.items()
                if dep not in existing
            ]
            if new:
                await _enqueue(session, server, new, resolve_deps=False)
                logger.info("queued %d dependency item(s) on %s", len(new), server_id)
    except Exception:  # noqa: BLE001 — background job: never crash the panel
        logger.exception("dependency resolution failed on %s", server_id)


async def add_mod(
    session: AsyncSession, server: Server, raw_item: str, name: str | None
) -> WorkshopMod:
    if server.workshop_app_id is None:
        raise WorkshopError("this game does not support Steam Workshop")
    item_id = parse_item_id(raw_item)
    if item_id in await _existing_item_ids(session, server.id):
        raise WorkshopError("that workshop item is already added")
    try:
        if await _provider().resolve_collection(item_id):
            raise IsCollection(item_id)
    except WorkshopProviderError:
        pass  # can't tell: treat it as a plain item
    return (await _enqueue(session, server, [_NewMod(item_id=item_id, name=name)]))[0]


async def import_preview(server: Server, raw: str) -> tuple[list[dict], list[str]]:
    """Parse a bulk-import blob into a preview (no install). Returns
    (items, unparsed) where each item is a dict matching ImportPreviewItem."""
    if server.workshop_app_id is None:
        raise WorkshopError("this game does not support Steam Workshop")
    ids, unparsed = parse_many(raw)
    if not ids:
        return [], unparsed

    # Any id may be a collection (alone or mixed with items): expand each one in
    # place into its members, keeping the order and dropping repeats.
    try:
        collections = await _provider().resolve_collections(ids)
    except WorkshopProviderError:
        collections = {}
    if collections:
        expanded: list[str] = []
        for iid in ids:
            for member in collections.get(iid, [iid]):
                if member not in expanded:
                    expanded.append(member)
        ids = expanded

    # Detect duplicates already filtered by parse_many; here flag installed ones.
    async with SessionLocal() as session:
        installed = await _existing_item_ids(session, server.id)

    summaries = await _fetch_summaries(ids)

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
    """Queue the given item ids for install, skipping already-installed ones.
    Returns as soon as the rows exist; downloads and dependency resolution run
    in the background."""
    if server.workshop_app_id is None:
        raise WorkshopError("this game does not support Steam Workshop")
    installed = await _existing_item_ids(session, server.id)
    to_add: list[str] = []
    skipped: list[str] = []
    for iid in item_ids:
        if iid in installed or iid in to_add:
            skipped.append(iid)
            continue
        to_add.append(iid)
    queued = await _enqueue(session, server, [_NewMod(item_id=i) for i in to_add])
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
    _spawn(_download_job(server.id, mod.id))
    return mod


async def retry_failed(session: AsyncSession, server: Server) -> list[WorkshopMod]:
    """Re-queue every failed mod of the server (they go out in batches)."""
    rows = (
        await session.execute(
            select(WorkshopMod)
            .where(
                WorkshopMod.server_id == server.id,
                WorkshopMod.status.in_(["error", "missing_dependency"]),
            )
            .order_by(WorkshopMod.created_at)
        )
    ).scalars().all()
    for m in rows:
        m.status = "queued"
        m.error_message = None
    await session.commit()
    for m in rows:
        _spawn(_download_job(server.id, m.id))
    return list(rows)


async def resume_queue_on_boot() -> int:
    """Re-queue downloads a restart interrupted (the queue lives in memory)."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(WorkshopMod)
                .where(WorkshopMod.status.in_(["queued", "downloading"]))
                .order_by(WorkshopMod.created_at)
            )
        ).scalars().all()
        for m in rows:
            m.status = "queued"
        await session.commit()
        for m in rows:
            _spawn(_download_job(m.server_id, m.id))
    if rows:
        logger.info("resumed %d interrupted workshop download(s)", len(rows))
    return len(rows)


async def _download_job(server_id: str, mod_id: str) -> None:
    """Queue a mod for download and wait until its batch is done. The row shows
    "queued" until its batch starts, then "downloading"."""
    done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    _pending.append((server_id, mod_id, done))
    global _worker
    if _worker is None or _worker.done():
        _worker = _spawn(_download_worker())
    await done


def _take_batch() -> tuple[str, list[str], list[asyncio.Future[None]]]:
    """Pop up to _BATCH_SIZE distinct mods of the oldest pending server."""
    server_id = _pending[0][0]
    mod_ids: list[str] = []
    waiters: list[asyncio.Future[None]] = []
    for entry in list(_pending):
        sid, mod_id, done = entry
        if sid != server_id:
            continue
        if mod_id not in mod_ids:
            if len(mod_ids) >= _BATCH_SIZE:
                continue  # next batch (keep scanning: repeats of taken mods ride along)
            mod_ids.append(mod_id)
        _pending.remove(entry)
        waiters.append(done)
    return server_id, mod_ids, waiters


async def _download_worker() -> None:
    while _pending:
        server_id, mod_ids, waiters = _take_batch()
        try:
            await _download_batch(server_id, mod_ids)
        except Exception:  # noqa: BLE001 — never let the queue die
            logger.exception("workshop batch crashed for %s", server_id)
        finally:
            for done in waiters:
                if not done.done():
                    done.set_result(None)


def parse_download_results(logs: str) -> dict[str, tuple[bool, str | None]]:
    """Per-item outcome from the download container's ``[workshop-result]`` lines."""
    return {
        m.group(1): (m.group(2) == "ok", (m.group(3) or "").strip() or None)
        for m in _RESULT_RE.finditer(logs or "")
    }


def _tail(logs: str, lines: int = 6) -> str:
    return "\n".join((logs or "").strip().splitlines()[-lines:])


async def _download_batch(server_id: str, mod_ids: list[str]) -> None:
    async with SessionLocal() as session:
        server = await session.get(Server, server_id)
        mods = [m for mid in mod_ids if (m := await session.get(WorkshopMod, mid)) is not None]
        if server is None or not mods:
            return  # removed while queued
        for m in mods:
            m.status = "downloading"
        await session.commit()
        targets = {m.id: m.item_id for m in mods}
        app_id = server.workshop_app_id
        install_path = _install_path_for(server)

    if app_id is None:
        for mod_id in targets:
            await _finish(mod_id, code=2, logs="workshop is not configured for this server")
        return

    item_ids = list(dict.fromkeys(targets.values()))
    code, logs = -1, ""
    try:
        code, logs = await run_in_threadpool(
            orchestrator.download_workshop_items, server_id, app_id, item_ids, install_path
        )
    except DockerError as exc:
        logs = f"orchestration error: {exc}"
        logger.error("workshop download failed for %s %s: %s", server_id, item_ids, exc)
    except Exception as exc:  # noqa: BLE001 — never let a job crash the panel
        logs = f"unexpected error: {exc}"
        logger.exception("workshop download crashed for %s %s", server_id, item_ids)

    results = parse_download_results(logs)
    stale_image = not results and "[entrypoint]" in logs
    if stale_image and code == 0 and len(item_ids) == 1:
        results = {item_ids[0]: (True, None)}  # old image, but a single item: it's done
    failed: list[str] = []
    for mod_id, item_id in targets.items():
        ok, reason = results.get(item_id, (False, None))
        if ok:
            await _finish(mod_id, 0, "")
        else:
            failed.append(item_id)
            if stale_image and not reason:
                reason = (
                    "the game-server image is outdated (no per-item results); restart the "
                    "agent or pull the -gameserver image, then retry.\n" + _tail(logs, 3)
                )
            await _finish(mod_id, 1, reason or _tail(logs) or "download failed")
    logger.info(
        "workshop batch on %s: %d ok, %d failed", server_id, len(targets) - len(failed), len(failed)
    )
    if failed:
        shown = ", ".join(failed[:5]) + ("…" if len(failed) > 5 else "")
        await notification_service.notify(
            "error",
            "Workshop install failed",
            f"{len(failed)} item(s) could not be downloaded ({shown}). Use Retry failed.",
            server_id,
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
        if code == 0:
            # Discover the game-level mods inside (per-mod toggles + load order).
            from app.services import load_order_service  # late import avoids a cycle

            server = await session.get(Server, mod.server_id)
            if server is not None and load_order_service.inspector_for(server):
                try:
                    await load_order_service.inspect_mod(session, server, mod)
                except DockerError as exc:
                    await session.rollback()
                    logger.warning("could not inspect %s: %s", mod.item_id, exc)


# -- updates ------------------------------------------------------------------


async def _requeue(session: AsyncSession, server: Server, mod: WorkshopMod) -> WorkshopMod:
    mod.status = "queued"
    mod.error_message = None
    await session.commit()
    await session.refresh(mod)
    _spawn(_download_job(server.id, mod.id))
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
