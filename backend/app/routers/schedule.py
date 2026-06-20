"""Scheduled-action endpoints: per-server CRUD + a global listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.scheduled_action import ScheduledAction
from app.schemas.schedule import ScheduledActionCreate, ScheduledActionOut, ScheduledActionUpdate
from app.services import scheduler_service, server_service

router = APIRouter(prefix="/api", tags=["schedule"])


async def _server_or_404(db: AsyncSession, server_id: str):
    server = await server_service.get_server(db, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    return server


async def _action_or_404(db: AsyncSession, server_id: str, action_id: str) -> ScheduledAction:
    action = await db.get(ScheduledAction, action_id)
    if action is None or action.server_id != server_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scheduled action not found")
    return action


@router.get("/servers/{server_id}/schedule", response_model=list[ScheduledActionOut])
async def list_schedule(server_id: str, db: AsyncSession = Depends(get_db)) -> list[ScheduledAction]:
    await _server_or_404(db, server_id)
    return await scheduler_service.list_for_server(db, server_id)


@router.post(
    "/servers/{server_id}/schedule",
    response_model=ScheduledActionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule(
    server_id: str, payload: ScheduledActionCreate, db: AsyncSession = Depends(get_db)
) -> ScheduledAction:
    await _server_or_404(db, server_id)
    try:
        scheduler_service.validate_cron(payload.cron)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await scheduler_service.create_action(
        db, server_id, payload.action, payload.cron, payload.enabled
    )


@router.patch(
    "/servers/{server_id}/schedule/{action_id}", response_model=ScheduledActionOut
)
async def update_schedule(
    server_id: str,
    action_id: str,
    payload: ScheduledActionUpdate,
    db: AsyncSession = Depends(get_db),
) -> ScheduledAction:
    action = await _action_or_404(db, server_id, action_id)
    if payload.cron is not None:
        try:
            scheduler_service.validate_cron(payload.cron)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await scheduler_service.update_action(
        db, action, action=payload.action, cron=payload.cron, enabled=payload.enabled
    )


@router.delete(
    "/servers/{server_id}/schedule/{action_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_schedule(
    server_id: str, action_id: str, db: AsyncSession = Depends(get_db)
) -> None:
    action = await _action_or_404(db, server_id, action_id)
    await scheduler_service.delete_action(db, action)


@router.get("/schedule", response_model=list[ScheduledActionOut])
async def list_all_schedule(db: AsyncSession = Depends(get_db)) -> list[ScheduledActionOut]:
    rows = await scheduler_service.list_all(db)
    out: list[ScheduledActionOut] = []
    for row in rows:
        item = ScheduledActionOut.model_validate(row)
        item.server_name = row.server.name if row.server else None
        out.append(item)
    return out
