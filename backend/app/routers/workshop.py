"""Steam Workshop mod endpoints (per server) + provider catalog (metadata)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.workshop_mod import WorkshopMod
from app.schemas.workshop import (
    AutoUpdateOut,
    AutoUpdateRequest,
    DependencyOut,
    ImportPreview,
    ImportPreviewItem,
    ImportRequest,
    ImportResult,
    LoadOrderEntryOut,
    LoadOrderOut,
    LoadOrderUpdate,
    ModDetailsOut,
    ModSummaryOut,
    SearchResultOut,
    SubmodToggle,
    SyncResult,
    WorkshopModCreate,
    WorkshopModOut,
)
from app.services import load_order_service, scheduler_service, server_service, workshop_service
from app.services.docker_orchestrator import DockerError
from app.workshop.base import ModDetails, ModSummary

router = APIRouter(prefix="/api/servers", tags=["workshop"])
# Server-independent provider metadata (search lands here in Phase 3).
catalog_router = APIRouter(prefix="/api/workshop", tags=["workshop"])


async def _server_or_404(db: AsyncSession, server_id: str):
    server = await server_service.get_server(db, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "server not found")
    return server


async def _mod_or_404(db: AsyncSession, server_id: str, mod_id: str) -> WorkshopMod:
    mod = await db.get(WorkshopMod, mod_id)
    if mod is None or mod.server_id != server_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mod not found")
    return mod


def _summary_out(s: ModSummary) -> ModSummaryOut:
    return ModSummaryOut(
        item_id=s.item_id,
        title=s.title,
        author_id=s.author_id,
        author_name=s.author_name,
        preview_url=s.preview_url,
        subscribers=s.subscribers,
        favorites=s.favorites,
        file_size=s.file_size,
        time_updated=s.time_updated,
        time_created=s.time_created,
    )


def _details_out(d: ModDetails) -> ModDetailsOut:
    return ModDetailsOut(
        item_id=d.item_id,
        title=d.title,
        author_id=d.author_id,
        author_name=d.author_name,
        preview_url=d.preview_url,
        subscribers=d.subscribers,
        favorites=d.favorites,
        file_size=d.file_size,
        time_updated=d.time_updated,
        time_created=d.time_created,
        description=d.description,
        images=d.images,
        dependencies=[DependencyOut(item_id=x.item_id, title=x.title) for x in d.dependencies],
    )


# -- per-server installed mods ------------------------------------------------


@router.get("/{server_id}/mods", response_model=list[WorkshopModOut])
async def list_mods(server_id: str, db: AsyncSession = Depends(get_db)) -> list[WorkshopMod]:
    await _server_or_404(db, server_id)
    return await workshop_service.list_mods(db, server_id)


@router.post("/{server_id}/mods", response_model=WorkshopModOut, status_code=status.HTTP_202_ACCEPTED)
async def add_mod(
    server_id: str, payload: WorkshopModCreate, db: AsyncSession = Depends(get_db)
) -> WorkshopMod:
    server = await _server_or_404(db, server_id)
    try:
        return await workshop_service.add_mod(db, server, payload.item, payload.name)
    except workshop_service.IsCollection as exc:
        # The UI catches this and opens the import preview with the collection.
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"collection:{exc.args[0]} is a Workshop collection"
        ) from exc
    except workshop_service.WorkshopError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/{server_id}/mods/import", status_code=status.HTTP_200_OK)
async def import_mods(
    server_id: str, payload: ImportRequest, db: AsyncSession = Depends(get_db)
):
    """Without ``install`` → returns a preview. With ``install`` → queues those ids."""
    server = await _server_or_404(db, server_id)
    try:
        if payload.install is None:
            items, unparsed = await workshop_service.import_preview(server, payload.input)
            return ImportPreview(
                items=[ImportPreviewItem(**i) for i in items], unparsed=unparsed
            )
        queued, skipped = await workshop_service.import_install(db, server, payload.install)
        return ImportResult(
            queued=[WorkshopModOut.model_validate(m) for m in queued], skipped=skipped
        )
    except workshop_service.WorkshopError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/{server_id}/mods/check-updates", response_model=list[WorkshopModOut])
async def check_updates(server_id: str, db: AsyncSession = Depends(get_db)) -> list[WorkshopMod]:
    await _server_or_404(db, server_id)
    await workshop_service.check_updates(server_id)
    return await workshop_service.list_mods(db, server_id)


@router.post("/{server_id}/mods/update-all", response_model=list[WorkshopModOut])
async def update_all(server_id: str, db: AsyncSession = Depends(get_db)) -> list[WorkshopMod]:
    server = await _server_or_404(db, server_id)
    return await workshop_service.update_all(db, server)


@router.post("/{server_id}/mods/sync", response_model=SyncResult)
async def sync_mods(server_id: str, db: AsyncSession = Depends(get_db)) -> SyncResult:
    server = await _server_or_404(db, server_id)
    try:
        result = await workshop_service.sync_mods(db, server)
    except workshop_service.WorkshopError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return SyncResult(**result)


@router.put("/{server_id}/workshop/auto-update", response_model=AutoUpdateOut)
async def set_auto_update(
    server_id: str, payload: AutoUpdateRequest, db: AsyncSession = Depends(get_db)
) -> AutoUpdateOut:
    server = await _server_or_404(db, server_id)
    server.workshop_auto_update = payload.mode
    await db.commit()
    scheduler_service.sync_workshop_auto_update(server)
    return AutoUpdateOut(mode=payload.mode)


@router.post("/{server_id}/mods/{mod_id}/retry", response_model=WorkshopModOut)
async def retry_mod(
    server_id: str, mod_id: str, db: AsyncSession = Depends(get_db)
) -> WorkshopMod:
    server = await _server_or_404(db, server_id)
    mod = await _mod_or_404(db, server_id, mod_id)
    try:
        return await workshop_service.retry_mod(db, server, mod)
    except workshop_service.WorkshopError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/{server_id}/mods/{mod_id}/update", response_model=WorkshopModOut)
async def update_mod(
    server_id: str, mod_id: str, db: AsyncSession = Depends(get_db)
) -> WorkshopMod:
    server = await _server_or_404(db, server_id)
    mod = await _mod_or_404(db, server_id, mod_id)
    try:
        return await workshop_service.update_mod(db, server, mod)
    except workshop_service.WorkshopError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.delete("/{server_id}/mods/{mod_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_mod(server_id: str, mod_id: str, db: AsyncSession = Depends(get_db)) -> None:
    server = await _server_or_404(db, server_id)
    mod = await _mod_or_404(db, server_id, mod_id)
    try:
        await workshop_service.remove_mod(db, server, mod)
    except workshop_service.WorkshopError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


# -- sub-mods / load order ---------------------------------------------------------


def _entries(entries: list[load_order_service.LoadOrderEntry]) -> list[LoadOrderEntryOut]:
    return [LoadOrderEntryOut.model_validate(e, from_attributes=True) for e in entries]


@router.get("/{server_id}/mods/load-order", response_model=LoadOrderOut)
async def get_load_order(server_id: str, db: AsyncSession = Depends(get_db)) -> LoadOrderOut:
    server = await _server_or_404(db, server_id)
    if load_order_service.inspector_for(server) is None:
        return LoadOrderOut(supported=False)
    try:
        entries = await load_order_service.load_order(db, server)
    except DockerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return LoadOrderOut(supported=True, entries=_entries(entries))


@router.put("/{server_id}/mods/load-order", response_model=LoadOrderOut)
async def put_load_order(
    server_id: str, payload: LoadOrderUpdate, db: AsyncSession = Depends(get_db)
) -> LoadOrderOut:
    server = await _server_or_404(db, server_id)
    try:
        entries = await load_order_service.set_load_order(
            db, server, [(i.id, i.enabled) for i in payload.order]
        )
    except load_order_service.LoadOrderError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return LoadOrderOut(supported=True, entries=_entries(entries))


@router.patch("/{server_id}/mods/submods/{submod_id}", status_code=status.HTTP_204_NO_CONTENT)
async def toggle_submod(
    server_id: str, submod_id: str, payload: SubmodToggle, db: AsyncSession = Depends(get_db)
) -> None:
    server = await _server_or_404(db, server_id)
    try:
        await load_order_service.set_enabled(db, server, submod_id, payload.enabled)
    except load_order_service.LoadOrderError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/{server_id}/mods/{mod_id}/inspect", response_model=LoadOrderOut)
async def inspect_mod(
    server_id: str, mod_id: str, db: AsyncSession = Depends(get_db)
) -> LoadOrderOut:
    """Re-scan one item's files for its mods (e.g. after editing them by hand)."""
    server = await _server_or_404(db, server_id)
    mod = await _mod_or_404(db, server_id, mod_id)
    if load_order_service.inspector_for(server) is None:
        return LoadOrderOut(supported=False)
    try:
        await load_order_service.inspect_mod(db, server, mod)
        entries = await load_order_service.load_order(db, server)
    except DockerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return LoadOrderOut(supported=True, entries=_entries(entries))


# -- provider catalog (server-independent) ------------------------------------


@catalog_router.get("/search", response_model=SearchResultOut)
async def search(
    gameId: int,
    query: str = "",
    page: int = 1,
    pageSize: int = 30,
    sortBy: str | None = None,
    provider: str = "steam",
) -> SearchResultOut:
    try:
        result = await workshop_service.search(
            query=query,
            app_id=gameId,
            page=page,
            page_size=min(max(pageSize, 1), 50),
            sort_by=sortBy,
            provider_id=provider,
        )
    except workshop_service.WorkshopError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return SearchResultOut(
        items=[_summary_out(s) for s in result.items], total=result.total, page=result.page
    )


@catalog_router.get("/mod/{item_id}", response_model=ModDetailsOut)
async def mod_details(item_id: str, provider: str = "steam") -> ModDetailsOut:
    try:
        details = await workshop_service.get_mod_details(item_id, provider)
    except workshop_service.WorkshopError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _details_out(details)
