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
    # Items to download in one steamcmd session (one login). `item_id` is the
    # single-item form older panels send.
    item_ids: list[str] = Field(default_factory=list, max_length=50)
    item_id: str | None = None
    install_path: str = "steamapps/workshop"

    def ids(self) -> list[str]:
        out = list(dict.fromkeys(self.item_ids))
        if self.item_id and self.item_id not in out:
            out.insert(0, self.item_id)
        return out


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
