"""Schemas for the public per-server control page (no panel login)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ControlMeta(BaseModel):
    """What the password screen shows before signing in."""

    name: str
    game: str
    # False when the server has no SERVER_PASSWORD: the page is disabled.
    enabled: bool


class ControlLogin(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ControlToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ControlPortOut(BaseModel):
    name: str
    protocol: str
    host_port: int
    # Public address of this port's tunnel (e.g. Playit), when it has one.
    public_address: str | None = None


class PublicServerOut(BaseModel):
    """Basic, secret-free server info for the control page."""

    id: str
    name: str
    game: str
    status: str
    ports: list[ControlPortOut]
    # Host of the panel's own tunnel: when the page is opened through it, the
    # LAN host:port of a game port is meaningless (only its tunnel works).
    panel_public_host: str | None = None
