"""Cron scheduler for server automation.

Schedule definitions live in the ``scheduled_actions`` table; APScheduler is used
purely as the in-memory trigger engine. On boot we load every enabled row and
register a job; CRUD operations keep the engine in sync. Each job opens its own
DB session (it outlives any request) and runs the matching server_service action,
writing the outcome back to the row.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models.scheduled_action import ScheduledAction
from app.models.server import Server
from app.services import server_service

logger = logging.getLogger("steamcmd-manager.scheduler")

ACTIONS = ("start", "stop", "restart", "update", "backup")

_scheduler: AsyncIOScheduler | None = None


def validate_cron(expr: str) -> None:
    """Raise ValueError if `expr` is not a valid 5-field crontab."""
    try:
        CronTrigger.from_crontab(expr, timezone="UTC")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid cron expression: {exc}") from exc


# -- engine lifecycle ---------------------------------------------------------


async def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.start()
    await _load_all()
    logger.info("scheduler started")


async def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


async def _load_all() -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(ScheduledAction).where(ScheduledAction.enabled.is_(True)))
        ).scalars().all()
        for action in rows:
            _schedule_job(action)
    logger.info("scheduler loaded enabled actions")


# -- job registration ---------------------------------------------------------


def _schedule_job(action: ScheduledAction) -> None:
    if _scheduler is None:
        return
    try:
        trigger = CronTrigger.from_crontab(action.cron, timezone="UTC")
    except (ValueError, TypeError):
        logger.error("skipping action %s: bad cron %r", action.id, action.cron)
        return
    _scheduler.add_job(
        _run_action,
        trigger=trigger,
        id=action.id,
        args=[action.id],
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )


def _unschedule_job(action_id: str) -> None:
    if _scheduler is None:
        return
    if _scheduler.get_job(action_id) is not None:
        _scheduler.remove_job(action_id)


def sync_action(action: ScheduledAction) -> None:
    """(Re)register or remove a job to match the action's enabled state/cron."""
    if action.enabled:
        _schedule_job(action)
    else:
        _unschedule_job(action.id)


# -- job execution ------------------------------------------------------------


async def _dispatch(session: AsyncSession, server: Server, action: str) -> None:
    if action == "start":
        await server_service.start_server(session, server, None)
    elif action == "stop":
        await server_service.stop_server(session, server)
    elif action == "restart":
        await server_service.restart_server(session, server, None)
    elif action == "update":
        await server_service.update_server(session, server, None)
    elif action == "backup":
        await server_service.start_backup(server)
    else:
        raise ValueError(f"unknown scheduled action: {action}")


async def _run_action(action_id: str) -> None:
    async with SessionLocal() as session:
        action = await session.get(ScheduledAction, action_id)
        if action is None or not action.enabled:
            return
        server = await session.get(Server, action.server_id)
        if server is None:
            return
        status, error = "ok", None
        try:
            await _dispatch(session, server, action.action)
            logger.info("scheduled %s on %s ran", action.action, server.id)
        except Exception as exc:  # noqa: BLE001 — record failure, never crash the loop
            status, error = "error", str(exc)
            logger.exception("scheduled %s on %s failed", action.action, server.id)
        action.last_run_at = datetime.now(timezone.utc)
        action.last_status = status
        action.last_error = error
        await session.commit()


# -- CRUD ---------------------------------------------------------------------


async def list_for_server(session: AsyncSession, server_id: str) -> list[ScheduledAction]:
    result = await session.execute(
        select(ScheduledAction)
        .where(ScheduledAction.server_id == server_id)
        .order_by(ScheduledAction.created_at)
    )
    return list(result.scalars().all())


async def list_all(session: AsyncSession) -> list[ScheduledAction]:
    result = await session.execute(select(ScheduledAction).order_by(ScheduledAction.created_at))
    return list(result.scalars().all())


async def create_action(
    session: AsyncSession, server_id: str, action: str, cron: str, enabled: bool
) -> ScheduledAction:
    row = ScheduledAction(server_id=server_id, action=action, cron=cron, enabled=enabled)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    sync_action(row)
    return row


async def update_action(
    session: AsyncSession,
    row: ScheduledAction,
    *,
    action: str | None,
    cron: str | None,
    enabled: bool | None,
) -> ScheduledAction:
    if action is not None:
        row.action = action
    if cron is not None:
        row.cron = cron
    if enabled is not None:
        row.enabled = enabled
    await session.commit()
    await session.refresh(row)
    sync_action(row)
    return row


async def delete_action(session: AsyncSession, row: ScheduledAction) -> None:
    _unschedule_job(row.id)
    await session.delete(row)
    await session.commit()
