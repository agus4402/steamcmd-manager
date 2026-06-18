"""Request/response schemas for servers and templates."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PortOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    protocol: str
    host_port: int


class ProgressOut(BaseModel):
    percent: float
    downloaded: int
    total: int


class TemplatePortOut(BaseModel):
    name: str
    protocol: str
    default: int


class TemplateVarOut(BaseModel):
    key: str
    default: str


class TemplateOut(BaseModel):
    id: str
    name: str
    app_id: int
    anonymous_login: bool
    ports: list[TemplatePortOut]
    variables: list[TemplateVarOut]
    update_on_start: bool


class SteamCredentials(BaseModel):
    username: str
    password: str
    guard_code: str | None = None


class ServerCreate(BaseModel):
    template_id: str
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    variables: dict[str, str] = Field(default_factory=dict)


class ServerUpdate(BaseModel):
    variables: dict[str, str] | None = None
    startup_template: str | None = None


class ServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    template_id: str
    app_id: int
    status: str
    variables: dict
    anonymous_login: bool
    update_on_start: bool
    error_message: str | None
    ports: list[PortOut]
    created_at: datetime
    # Populated by the router only while installing/updating.
    progress: ProgressOut | None = None
