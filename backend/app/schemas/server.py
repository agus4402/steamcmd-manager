"""Request/response schemas for servers and templates."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PortOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    protocol: str
    host_port: int
    is_primary: bool = True


class ProgressOut(BaseModel):
    percent: float
    downloaded: int
    total: int


class StatsOut(BaseModel):
    """Point-in-time container resource usage."""

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


class SnapshotOut(BaseModel):
    id: str
    created_at: str
    size: int


class BackupJobOut(BaseModel):
    """State of a backup creation job (polled by the UI)."""

    status: str  # idle | creating | done | error
    id: str | None = None
    size: int = 0
    error: str | None = None


class CloneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


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
    supported: bool = True
    unsupported_reason: str | None = None
    workshop_supported: bool = False
    ports: list[TemplatePortOut]
    variables: list[TemplateVarOut]
    update_on_start: bool
    branches: list[str] = []
    workshop_note: str | None = None
    # Declared config files (Config tab), e.g. to deep-link a mod's sandbox options.
    config_files: list[dict[str, str]] = []


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
    # Steam beta branch; "" or null resets to the public branch. Only applied
    # when the field is present in the request.
    steam_branch: str | None = Field(default=None, pattern=r"^([A-Za-z0-9_.-]{1,64})?$")


class BackupConfigUpdate(BaseModel):
    max_backups: int = Field(ge=0)


class RestoreRequest(BaseModel):
    start_after: bool = False


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
    max_backups: int = 0
    steam_branch: str | None = None
    # Non-null when the game supports Steam Workshop (drives the Workshop tab).
    workshop_app_id: int | None = None
    workshop_auto_update: str = "disabled"
    error_message: str | None
    ports: list[PortOut]
    created_at: datetime
    # Populated by the router only while installing/updating.
    progress: ProgressOut | None = None
