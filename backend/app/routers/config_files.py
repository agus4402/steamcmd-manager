"""Config editor endpoints: a server's game config files (raw + structured)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services import config_service, server_service
from app.services.docker_orchestrator import DockerError

router = APIRouter(prefix="/api/servers", tags=["config"])


class ConfigWrite(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    # Exactly one of: the whole file, or {setting path: new value}.
    content: str | None = None
    changes: dict[str, str] | None = None
    # mtime the client loaded; a mismatch means someone else changed the file.
    base_mtime: int | None = None
    # On a running server: graceful stop → write → start.
    restart: bool = False


class ConfigRestore(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    restart: bool = False


async def _server(db: AsyncSession, server_id: str):
    server = await server_service.get_server(db, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    return server


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, config_service.NotAllowed):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    if isinstance(exc, config_service.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, config_service.Conflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, DockerError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/{server_id}/config/files")
async def list_config_files(server_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    server = await _server(db, server_id)
    try:
        return await config_service.list_files(server)
    except (config_service.ConfigError, DockerError) as exc:
        raise _http(exc) from exc


@router.get("/{server_id}/config/file")
async def read_config_file(server_id: str, path: str, db: AsyncSession = Depends(get_db)) -> dict:
    server = await _server(db, server_id)
    try:
        return await config_service.read(server, path)
    except (config_service.ConfigError, DockerError) as exc:
        raise _http(exc) from exc


@router.put("/{server_id}/config/file")
async def write_config_file(
    server_id: str, payload: ConfigWrite, db: AsyncSession = Depends(get_db)
) -> dict:
    server = await _server(db, server_id)
    try:
        return await config_service.write(
            db,
            server,
            payload.path,
            content=payload.content,
            changes=payload.changes,
            base_mtime=payload.base_mtime,
            restart=payload.restart,
        )
    except (config_service.ConfigError, DockerError) as exc:
        raise _http(exc) from exc


@router.post("/{server_id}/config/file/restore")
async def restore_config_file(
    server_id: str, payload: ConfigRestore, db: AsyncSession = Depends(get_db)
) -> dict:
    server = await _server(db, server_id)
    try:
        return await config_service.restore_backup(db, server, payload.path, payload.restart)
    except (config_service.ConfigError, DockerError) as exc:
        raise _http(exc) from exc
