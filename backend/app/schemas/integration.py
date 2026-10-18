"""Request/response schemas for integrations and tunnels.

Credential material is NEVER part of any response schema — secrets stay in the
backend and are only ever handed to the agent over the internal network.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IntegrationOut(BaseModel):
    """A provider card: static catalog info merged with connection state."""

    id: str | None  # null until a connection row exists for this provider
    provider: str
    name: str
    description: str
    icon: str
    capabilities: list[str]
    status: str  # not_connected | pending | connected | error
    account_label: str | None = None
    last_sync_at: datetime | None = None
    error_message: str | None = None
    tunnel_count: int = 0


class ConnectStartOut(BaseModel):
    integration_id: str
    claim_url: str | None = None
    expires_at: str | None = None


class ConnectStatusOut(BaseModel):
    integration_id: str
    status: str
    account_label: str | None = None
    error_message: str | None = None


class TunnelCreate(BaseModel):
    server_id: str | None = None
    local_port: int = Field(ge=1, le=65535)
    protocol: str = Field(pattern=r"^(tcp|udp)$")
    name: str | None = Field(default=None, max_length=128)


class TunnelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    integration_id: str
    server_id: str | None
    name: str
    remote_domain: str | None
    local_port: int
    protocol: str
    status: str
    error_message: str | None
    created_at: datetime


class PanelTunnelCreate(BaseModel):
    local_port: int = Field(ge=1, le=65535)


class PanelTunnelOut(BaseModel):
    """Public access to the web panel through a tunnel provider (Playit)."""

    # Connected integration able to create tunnels; null = none connected.
    integration_id: str | None
    provider_name: str | None = None
    tunnel: TunnelOut | None = None
    # Host port the panel is published on (from FRONTEND_ORIGIN), as a default.
    default_port: int | None = None
