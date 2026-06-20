"""Request/response schemas for scheduled actions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ScheduleAction = Literal["start", "stop", "restart", "update", "backup"]


class ScheduledActionCreate(BaseModel):
    action: ScheduleAction
    cron: str = Field(min_length=1, max_length=64)
    enabled: bool = True


class ScheduledActionUpdate(BaseModel):
    action: ScheduleAction | None = None
    cron: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None


class ScheduledActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    server_id: str
    action: str
    cron: str
    enabled: bool
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    created_at: datetime
    # Populated only by the global listing so the UI can show which server.
    server_name: str | None = None
