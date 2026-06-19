"""Request/response models for the agent's narrow API."""

from __future__ import annotations

from pydantic import BaseModel


class CreateContainerRequest(BaseModel):
    env: dict[str, str] = {}
    # {"27015/udp": 27015, ...} — validated against the pool in main.py
    port_bindings: dict[str, int] = {}


class InstallRequest(BaseModel):
    env: dict[str, str] = {}


class StdinRequest(BaseModel):
    data: str


class CreateResponse(BaseModel):
    container_id: str


class StateResponse(BaseModel):
    exists: bool
    status: str
    exit_code: int | None = None


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
