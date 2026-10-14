"""Sub-mods of workshop items: discovery, per-mod-id toggles and load order.

Games like Project Zomboid enable mods by *mod id* (one workshop item can hold
several), in an order that matters. When the template has a
`workshop.inspector`, every downloaded item is inspected and its mods become
WorkshopSubmod rows; the enabled ones, in `load_order`, are what the server
receives on start (WORKSHOP_MOD_IDS / WORKSHOP_MAPS for the prestart hook).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.server import Server
from app.models.workshop_mod import WorkshopMod
from app.models.workshop_submod import WorkshopSubmod
from app.services.docker_orchestrator import DockerError
from app.services.template_loader import get_template
from app.workshop.inspectors import INSPECTORS, SubmodInfo, inspect_item

logger = logging.getLogger("steamcmd-manager.load-order")

PUBLIC_BRANCH = "public"
# Item states whose files are on disk (an update in progress keeps the old ones).
_ON_DISK = ("installed", "update_available", "queued", "downloading")


class LoadOrderError(RuntimeError):
    """Domain error the API layer turns into a 4xx."""


def inspector_for(server: Server) -> str | None:
    try:
        workshop = get_template(server.template_id).workshop
    except Exception:  # noqa: BLE001 — unknown/removed template
        return None
    name = workshop.inspector if workshop else None
    return name if name in INSPECTORS else None


def _branch_key(server: Server) -> str:
    return server.steam_branch or PUBLIC_BRANCH


# -- discovery ------------------------------------------------------------------


async def inspect_mod(
    session: AsyncSession, server: Server, mod: WorkshopMod
) -> list[WorkshopSubmod]:
    """(Re)discover the mods inside one downloaded item and sync its rows.

    Existing mod ids keep their toggle and position; new ones are placed (see
    `_place_new`); ids no longer present are dropped.
    """
    from app.services.workshop_service import _install_path_for  # avoid import cycle

    inspector = inspector_for(server)
    if inspector is None:
        return []
    item_root = f"{_install_path_for(server)}/{mod.item_id}"
    found: list[SubmodInfo] = await run_in_threadpool(
        inspect_item, inspector, server.id, item_root, server.steam_branch
    )

    existing = {
        s.mod_id: s
        for s in (
            await session.scalars(
                select(WorkshopSubmod).where(WorkshopSubmod.workshop_mod_id == mod.id)
            )
        ).all()
    }
    taken_elsewhere = set(
        (
            await session.scalars(
                select(WorkshopSubmod.mod_id).where(
                    WorkshopSubmod.server_id == server.id, WorkshopSubmod.workshop_mod_id != mod.id
                )
            )
        ).all()
    )
    seen: set[str] = set()
    new_rows: list[WorkshopSubmod] = []
    for info in found:
        if info.mod_id in seen or info.mod_id in taken_elsewhere:
            continue  # same mod id shipped twice: first one wins
        seen.add(info.mod_id)
        row = existing.get(info.mod_id)
        if row is None:
            row = WorkshopSubmod(server_id=server.id, workshop_mod_id=mod.id, mod_id=info.mod_id)
            new_rows.append(row)
            session.add(row)
        row.name = info.name
        row.folder = info.folder
        row.requires = info.requires
        row.maps = info.maps
    for mod_id, row in existing.items():
        if mod_id not in seen:
            await session.delete(row)

    await session.flush()
    if new_rows:
        await _place_new(session, server, mod, new_rows)
    mod.inspected_branch = _branch_key(server)
    await session.commit()
    logger.info("inspected %s on %s: %d mod(s)", mod.item_id, server.id, len(seen))
    return await submods_of(session, mod)


async def _place_new(
    session: AsyncSession, server: Server, mod: WorkshopMod, rows: list[WorkshopSubmod]
) -> None:
    """Append new mods at the end — except an auto-added dependency, which goes
    right before the first mod of the item that required it."""
    position: int | None = None
    if mod.is_dependency and mod.required_by:
        position = await session.scalar(
            select(func.min(WorkshopSubmod.load_order))
            .join(WorkshopMod, WorkshopMod.id == WorkshopSubmod.workshop_mod_id)
            .where(
                WorkshopSubmod.server_id == server.id,
                WorkshopMod.item_id == mod.required_by,
            )
        )
    if position is None:
        last = await session.scalar(
            select(func.max(WorkshopSubmod.load_order)).where(
                WorkshopSubmod.server_id == server.id,
                WorkshopSubmod.id.not_in([r.id for r in rows]),
            )
        )
        position = (last + 1) if last is not None else 0
    else:
        await session.execute(
            update(WorkshopSubmod)
            .where(
                WorkshopSubmod.server_id == server.id,
                WorkshopSubmod.load_order >= position,
                WorkshopSubmod.id.not_in([r.id for r in rows]),
            )
            .values(load_order=WorkshopSubmod.load_order + len(rows))
        )
    for i, row in enumerate(rows):
        row.load_order = position + i


async def ensure_inspected(session: AsyncSession, server: Server) -> None:
    """Inspect downloaded items never inspected (or inspected for another branch).
    Best-effort: a failing item is logged and retried next time."""
    if inspector_for(server) is None:
        return
    mods = (
        await session.scalars(
            select(WorkshopMod).where(
                WorkshopMod.server_id == server.id,
                WorkshopMod.status.in_(_ON_DISK),
                (WorkshopMod.inspected_branch.is_(None))
                | (WorkshopMod.inspected_branch != _branch_key(server)),
            )
        )
    ).all()
    for mod in mods:
        if mod.status in ("queued", "downloading") and mod.inspected_branch is None:
            continue  # nothing on disk yet
        try:
            await inspect_mod(session, server, mod)
        except DockerError as exc:
            await session.rollback()
            logger.warning("could not inspect %s on %s: %s", mod.item_id, server.id, exc)


async def submods_of(session: AsyncSession, mod: WorkshopMod) -> list[WorkshopSubmod]:
    return list(
        (
            await session.scalars(
                select(WorkshopSubmod)
                .where(WorkshopSubmod.workshop_mod_id == mod.id)
                .order_by(WorkshopSubmod.load_order)
            )
        ).all()
    )


# -- load order -----------------------------------------------------------------


@dataclass(slots=True)
class LoadOrderEntry:
    id: str
    mod_id: str
    name: str | None
    enabled: bool
    load_order: int
    item_id: str
    item_title: str | None
    workshop_mod_id: str
    requires: list[str]
    maps: list[str]
    warnings: list[str] = field(default_factory=list)


def compute_warnings(entries: list[LoadOrderEntry]) -> None:
    """Flag enabled mods whose required mods are missing, disabled, or load later."""
    position = {e.mod_id: i for i, e in enumerate(entries)}
    by_id = {e.mod_id: e for e in entries}
    for i, e in enumerate(entries):
        e.warnings = []
        if not e.enabled:
            continue
        for req in e.requires:
            dep = by_id.get(req)
            if dep is None:
                e.warnings.append(f"requires {req}, which is not installed")
            elif not dep.enabled:
                e.warnings.append(f"requires {req}, which is disabled")
            elif position[req] > i:
                e.warnings.append(f"requires {req}, which loads after it")


async def load_order(session: AsyncSession, server: Server) -> list[LoadOrderEntry]:
    await ensure_inspected(session, server)
    rows = (
        await session.execute(
            select(WorkshopSubmod, WorkshopMod)
            .join(WorkshopMod, WorkshopMod.id == WorkshopSubmod.workshop_mod_id)
            .where(WorkshopSubmod.server_id == server.id)
            .order_by(WorkshopSubmod.load_order, WorkshopSubmod.mod_id)
        )
    ).all()
    entries = [
        LoadOrderEntry(
            id=s.id,
            mod_id=s.mod_id,
            name=s.name,
            enabled=s.enabled,
            load_order=s.load_order,
            item_id=m.item_id,
            item_title=m.title or m.name,
            workshop_mod_id=m.id,
            requires=list(s.requires or []),
            maps=list(s.maps or []),
        )
        for s, m in rows
    ]
    compute_warnings(entries)
    return entries


async def set_load_order(
    session: AsyncSession, server: Server, order: list[tuple[str, bool]]
) -> list[LoadOrderEntry]:
    """Replace the whole order: `order` lists every sub-mod id with its toggle."""
    rows = {
        s.id: s
        for s in (
            await session.scalars(
                select(WorkshopSubmod).where(WorkshopSubmod.server_id == server.id)
            )
        ).all()
    }
    ids = [i for i, _ in order]
    if len(set(ids)) != len(ids) or set(ids) != set(rows):
        raise LoadOrderError("the load order must list every mod exactly once; reload and retry")
    for index, (sid, enabled) in enumerate(order):
        rows[sid].load_order = index
        rows[sid].enabled = enabled
    await session.commit()
    return await load_order(session, server)


async def set_enabled(session: AsyncSession, server: Server, submod_id: str, enabled: bool) -> None:
    row = await session.get(WorkshopSubmod, submod_id)
    if row is None or row.server_id != server.id:
        raise LoadOrderError("mod not found")
    row.enabled = enabled
    await session.commit()


# -- start ----------------------------------------------------------------------


@dataclass(slots=True)
class WorkshopRuntime:
    items: list[str]
    mod_ids: list[str] | None  # None: no inspector → the hook auto-detects
    maps: list[str] | None


async def runtime(session: AsyncSession, server: Server) -> WorkshopRuntime | None:
    """What a start passes to the game: items to keep, mod ids in order, maps."""
    if server.workshop_app_id is None:
        return None
    mods = (
        await session.scalars(
            select(WorkshopMod)
            .where(
                WorkshopMod.server_id == server.id,
                WorkshopMod.status.not_in(("error", "missing_dependency")),
            )
            .order_by(WorkshopMod.is_dependency.desc(), WorkshopMod.created_at)
        )
    ).all()
    if inspector_for(server) is None:
        return WorkshopRuntime(items=[m.item_id for m in mods], mod_ids=None, maps=None)

    await ensure_inspected(session, server)
    entries = await load_order(session, server)
    enabled = [e for e in entries if e.enabled]
    with_submods = {e.workshop_mod_id for e in entries}
    items: list[str] = []
    for e in enabled:
        if e.item_id not in items:
            items.append(e.item_id)
    # Items never inspected (e.g. inspection failed) still get downloaded by the
    # game; they just contribute no mod ids until inspected.
    items += [m.item_id for m in mods if m.id not in with_submods and m.item_id not in items]
    maps: list[str] = []
    for e in enabled:
        maps += [m for m in e.maps if m not in maps]
    return WorkshopRuntime(items=items, mod_ids=[e.mod_id for e in enabled], maps=maps)
