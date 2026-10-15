"""Request/response schemas for Steam Workshop mods."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkshopModCreate(BaseModel):
    # Workshop item id or a full workshop URL; parsed server-side.
    item: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)


class WorkshopModOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    server_id: str
    provider: str
    item_id: str
    name: str | None
    status: str
    size: int
    error_message: str | None
    # Cached metadata.
    title: str | None
    author_id: str | None
    author_name: str | None
    preview_url: str | None
    subscribers: int
    favorites: int
    file_size: int
    time_updated_remote: datetime | None
    installed_time_updated: datetime | None
    is_dependency: bool
    required_by: str | None
    created_at: datetime


# -- catalog (provider metadata, server-independent) --------------------------


class DependencyOut(BaseModel):
    item_id: str
    title: str | None = None


class ModSummaryOut(BaseModel):
    item_id: str
    title: str | None = None
    author_id: str | None = None
    author_name: str | None = None
    preview_url: str | None = None
    subscribers: int = 0
    favorites: int = 0
    file_size: int = 0
    time_updated: datetime | None = None
    time_created: datetime | None = None


class ModDetailsOut(ModSummaryOut):
    description: str | None = None
    images: list[str] = Field(default_factory=list)
    dependencies: list[DependencyOut] = Field(default_factory=list)


class SearchResultOut(BaseModel):
    items: list[ModSummaryOut]
    total: int
    page: int


# -- bulk import --------------------------------------------------------------


class ImportRequest(BaseModel):
    # Raw text: collection URL/id, mod URLs, or a list of ids (comma/space/newline).
    input: str = Field(min_length=1, max_length=20000)
    # When provided, install exactly these ids; when omitted, return a preview only.
    install: list[str] | None = None


class ImportPreviewItem(BaseModel):
    item_id: str
    title: str | None = None
    preview_url: str | None = None
    file_size: int = 0
    # already installed on this server?
    installed: bool = False
    # appeared more than once in the parsed input?
    duplicate: bool = False
    # metadata lookup failed / item not found?
    missing: bool = False


class ImportPreview(BaseModel):
    items: list[ImportPreviewItem]
    # ids that could not be parsed from the input at all.
    unparsed: list[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    queued: list[WorkshopModOut]
    skipped: list[str] = Field(default_factory=list)


# -- auto-update + sync -------------------------------------------------------

AutoUpdateMode = Literal["disabled", "15min", "daily", "weekly", "startup"]


class AutoUpdateRequest(BaseModel):
    mode: AutoUpdateMode


class AutoUpdateOut(BaseModel):
    mode: AutoUpdateMode


class SyncResult(BaseModel):
    restored: int
    missing: int
    on_disk: int


# -- sub-mods / load order ------------------------------------------------------


class LoadOrderEntryOut(BaseModel):
    id: str
    mod_id: str
    name: str | None = None
    enabled: bool
    load_order: int
    item_id: str
    item_title: str | None = None
    workshop_mod_id: str
    requires: list[str] = Field(default_factory=list)
    maps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MapEntryOut(BaseModel):
    name: str
    enabled: bool
    mod_ids: list[str] = Field(default_factory=list)
    # False when every mod providing it is disabled (then it isn't loaded).
    active: bool = True


class LoadOrderOut(BaseModel):
    # False when the game has no inspector (mods can't be toggled individually).
    supported: bool
    entries: list[LoadOrderEntryOut] = Field(default_factory=list)
    # Game maps from the mods, in load order (first wins; vanilla map is last).
    maps: list[MapEntryOut] = Field(default_factory=list)


class LoadOrderItem(BaseModel):
    id: str
    enabled: bool


class MapOrderItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    enabled: bool


class LoadOrderUpdate(BaseModel):
    # Every sub-mod of the server, in the desired load order.
    order: list[LoadOrderItem] = Field(max_length=2000)
    # Optional map order; omitted = keep the current one.
    maps: list[MapOrderItem] | None = Field(default=None, max_length=500)


class SubmodToggle(BaseModel):
    enabled: bool
