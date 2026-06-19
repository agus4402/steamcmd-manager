"""Server CRUD + lifecycle endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db import get_db
from app.schemas.server import (
    BackupJobOut,
    CloneRequest,
    ProgressOut,
    ServerCreate,
    ServerOut,
    ServerUpdate,
    SnapshotOut,
    StatsOut,
    SteamCredentials,
)
from app.services import server_service
from app.services.docker_orchestrator import DockerError, orchestrator
from app.services.template_loader import TemplateError

router = APIRouter(prefix="/api/servers", tags=["servers"])


async def _get_or_404(db: AsyncSession, server_id: str):
    server = await server_service.get_server(db, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    return server


async def _serialize(server, *, with_progress: bool = False) -> ServerOut:
    out = ServerOut.model_validate(server)
    if with_progress:
        prog = await server_service.get_progress(server)
        if prog:
            out.progress = ProgressOut(**prog)
    return out


def _creds_dict(creds: SteamCredentials | None) -> dict[str, str] | None:
    return creds.model_dump() if creds else None


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(payload: ServerCreate, db: AsyncSession = Depends(get_db)) -> ServerOut:
    try:
        server = await server_service.create_server(db, payload)
    except TemplateError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except server_service.NameTaken as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ServerOut.model_validate(server)


@router.get("", response_model=list[ServerOut])
async def list_servers(db: AsyncSession = Depends(get_db)) -> list[ServerOut]:
    servers = await server_service.list_servers(db)
    out: list[ServerOut] = []
    for server in servers:
        await server_service.reconcile(db, server)
        out.append(await _serialize(server, with_progress=True))
    return out


@router.get("/{server_id}", response_model=ServerOut)
async def get_server(server_id: str, db: AsyncSession = Depends(get_db)) -> ServerOut:
    server = await _get_or_404(db, server_id)
    await server_service.reconcile(db, server)
    return await _serialize(server, with_progress=True)


@router.get("/{server_id}/stats", response_model=StatsOut)
async def server_stats(server_id: str, db: AsyncSession = Depends(get_db)) -> StatsOut:
    """Point-in-time CPU/memory/network/disk usage for the server container."""
    server = await _get_or_404(db, server_id)
    try:
        snapshot = await run_in_threadpool(orchestrator.stats, server.id)
    except DockerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return StatsOut(**asdict(snapshot))


@router.patch("/{server_id}", response_model=ServerOut)
async def update_server_config(
    server_id: str, payload: ServerUpdate, db: AsyncSession = Depends(get_db)
) -> ServerOut:
    server = await _get_or_404(db, server_id)
    try:
        server = await server_service.patch_server(
            db, server, payload.variables, payload.startup_template
        )
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ServerOut.model_validate(server)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: str, db: AsyncSession = Depends(get_db)) -> None:
    server = await _get_or_404(db, server_id)
    await server_service.delete_server(db, server)


# -- lifecycle ----------------------------------------------------------------


@router.post("/{server_id}/install", response_model=ServerOut, status_code=status.HTTP_202_ACCEPTED)
async def install_server(
    server_id: str,
    creds: SteamCredentials | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> ServerOut:
    server = await _get_or_404(db, server_id)
    try:
        await server_service.install_server(db, server, _creds_dict(creds))
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ServerOut.model_validate(server)


@router.post("/{server_id}/update", response_model=ServerOut, status_code=status.HTTP_202_ACCEPTED)
async def update_server(
    server_id: str,
    creds: SteamCredentials | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> ServerOut:
    server = await _get_or_404(db, server_id)
    try:
        await server_service.update_server(db, server, _creds_dict(creds))
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ServerOut.model_validate(server)


@router.post("/{server_id}/start", response_model=ServerOut)
async def start_server(
    server_id: str,
    creds: SteamCredentials | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> ServerOut:
    server = await _get_or_404(db, server_id)
    try:
        await server_service.start_server(db, server, _creds_dict(creds))
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ServerOut.model_validate(server)


@router.post("/{server_id}/stop", response_model=ServerOut)
async def stop_server(server_id: str, db: AsyncSession = Depends(get_db)) -> ServerOut:
    server = await _get_or_404(db, server_id)
    await server_service.stop_server(db, server)
    return ServerOut.model_validate(server)


@router.post("/{server_id}/restart", response_model=ServerOut)
async def restart_server(
    server_id: str,
    creds: SteamCredentials | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> ServerOut:
    server = await _get_or_404(db, server_id)
    try:
        await server_service.restart_server(db, server, _creds_dict(creds))
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ServerOut.model_validate(server)


@router.post("/{server_id}/reinstall", response_model=ServerOut, status_code=status.HTTP_202_ACCEPTED)
async def reinstall_server(
    server_id: str,
    creds: SteamCredentials | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> ServerOut:
    server = await _get_or_404(db, server_id)
    try:
        await server_service.reinstall_server(db, server, _creds_dict(creds))
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ServerOut.model_validate(server)


@router.post("/{server_id}/clone", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def clone_server(
    server_id: str, payload: CloneRequest, db: AsyncSession = Depends(get_db)
) -> ServerOut:
    server = await _get_or_404(db, server_id)
    try:
        clone = await server_service.clone_server(db, server, payload.name)
    except server_service.NameTaken as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except DockerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return ServerOut.model_validate(clone)


# -- backups ------------------------------------------------------------------


@router.get("/{server_id}/backups", response_model=list[SnapshotOut])
async def list_backups(server_id: str, db: AsyncSession = Depends(get_db)) -> list[SnapshotOut]:
    server = await _get_or_404(db, server_id)
    try:
        snaps = await server_service.list_snapshots(server)
    except DockerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return [SnapshotOut(id=s.id, created_at=s.created_at, size=s.size) for s in snaps]


@router.post("/{server_id}/backups", response_model=BackupJobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_backup(server_id: str, db: AsyncSession = Depends(get_db)) -> BackupJobOut:
    server = await _get_or_404(db, server_id)
    try:
        job = await server_service.start_backup(server)
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return BackupJobOut(**job)


@router.get("/{server_id}/backups/status", response_model=BackupJobOut)
async def backup_status(server_id: str, db: AsyncSession = Depends(get_db)) -> BackupJobOut:
    await _get_or_404(db, server_id)
    job = server_service.get_backup_job(server_id)
    return BackupJobOut(**job) if job else BackupJobOut(status="idle")


@router.post("/{server_id}/backups/{snapshot_id}/restore", response_model=ServerOut)
async def restore_backup(
    server_id: str, snapshot_id: str, db: AsyncSession = Depends(get_db)
) -> ServerOut:
    server = await _get_or_404(db, server_id)
    try:
        await server_service.restore_snapshot(db, server, snapshot_id)
    except server_service.ServerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except DockerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return ServerOut.model_validate(server)


@router.delete("/{server_id}/backups/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(server_id: str, snapshot_id: str, db: AsyncSession = Depends(get_db)) -> None:
    server = await _get_or_404(db, server_id)
    try:
        await server_service.delete_snapshot(server, snapshot_id)
    except DockerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
