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
