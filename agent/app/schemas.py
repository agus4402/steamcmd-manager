"""Request/response models for the agent's narrow API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateContainerRequest(BaseModel):
    env: dict[str, str] = {}
    # {"27015/udp": 27015, ...} — validated against the pool in main.py
    port_bindings: dict[str, int] = {}


class InstallRequest(BaseModel):
    env: dict[str, str] = {}


class StdinRequest(BaseModel):
    data: str


class StopRequest(BaseModel):
    # Console command that makes the game save + exit on its own (e.g. "quit").
    # Validated to a single short line in main.py.
    command: str | None = None
    # Seconds to wait for a clean exit before docker-stopping the container.
    timeout: int = Field(default=30, ge=1, le=600)


class WorkshopDownloadRequest(BaseModel):
    app_id: int
    item_id: str
    install_path: str = "steamapps/workshop"


class CreateResponse(BaseModel):
    container_id: str


class StateResponse(BaseModel):
    exists: bool
    status: str
    exit_code: int | None = None
    # Identify a container instance: a recreated container has a new id, a
    # restarted one keeps it with a new started_at (the console follows both).
    id: str | None = None
    started_at: str | None = None


class InstallResultResponse(BaseModel):
    code: int
    logs: str


class LogsResponse(BaseModel):
    logs: str


class StatsResponse(BaseModel):
    running: bool
    cpu_pct: float = 0.0
    mem_used: int = 0
    mem_limit: int = 0
    mem_pct: float = 0.0
    net_rx: int = 0
    net_tx: int = 0
    blk_read: int = 0
    blk_write: int = 0
    pids: int = 0
    online_cpus: int = 0


class SnapshotResponse(BaseModel):
    id: str
    created_at: str
    size: int


class SnapshotListResponse(BaseModel):
    snapshots: list[SnapshotResponse]


class FileEntryResponse(BaseModel):
    path: str
    type: str
    size: int
    mtime: int


# -- integrations: playit (data-plane only) -----------------------------------


class PlayitSecretRequest(BaseModel):
    secret: str


class PlayitStateResponse(BaseModel):
    running: bool
