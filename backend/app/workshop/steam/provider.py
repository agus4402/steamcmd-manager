"""Steam Workshop provider — maps Steam Web API payloads to the common types."""

from __future__ import annotations

from datetime import datetime, timezone

from app.workshop.base import (
    Dependency,
    ModDetails,
    ModSummary,
    SearchResult,
    WorkshopProvider,
    WorkshopSort,
)
from app.workshop.steam import api


def _ts(value: object) -> datetime | None:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(n, tz=timezone.utc) if n > 0 else None


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _subscribers(d: dict) -> int:
    # QueryFiles/GetPublishedFileDetails expose live + lifetime counters.
    return _int(d.get("subscriptions") or d.get("lifetime_subscriptions"))


def _to_summary(d: dict) -> ModSummary:
    return ModSummary(
        item_id=str(d.get("publishedfileid") or ""),
        title=d.get("title") or None,
        author_id=str(d.get("creator")) if d.get("creator") else None,
        preview_url=d.get("preview_url") or None,
        subscribers=_subscribers(d),
        favorites=_int(d.get("favorited") or d.get("lifetime_favorited")),
        file_size=_int(d.get("file_size")),
        time_updated=_ts(d.get("time_updated")),
        time_created=_ts(d.get("time_created")),
    )


def _dependencies(d: dict) -> list[Dependency]:
    # GetDetails returns children; file_type 0 marks a required workshop item.
    out: list[Dependency] = []
    for c in d.get("children") or []:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("publishedfileid") or "")
        if cid:
            out.append(Dependency(item_id=cid))
    return out


def _to_details(d: dict) -> ModDetails:
    base = _to_summary(d)
    return ModDetails(
        item_id=base.item_id,
        title=base.title,
        author_id=base.author_id,
        author_name=base.author_name,
        preview_url=base.preview_url,
        subscribers=base.subscribers,
        favorites=base.favorites,
        file_size=base.file_size,
        time_updated=base.time_updated,
        time_created=base.time_created,
        description=d.get("description") or d.get("file_description") or None,
        images=[base.preview_url] if base.preview_url else [],
        dependencies=_dependencies(d),
    )


class SteamWorkshopProvider(WorkshopProvider):
    id = "steam"
    name = "Steam Workshop"
    description = "Valve's Steam Workshop, downloaded via SteamCMD."
    icon = "boxes"

    async def search(
        self,
        *,
        query: str,
        app_id: int,
        page: int = 1,
        page_size: int = 30,
        sort: WorkshopSort = WorkshopSort.POPULAR,
    ) -> SearchResult:
        items, total = await api.query_files(
            query=query, app_id=app_id, page=page, page_size=page_size, sort=sort
        )
        ids = [str(i.get("publishedfileid")) for i in items if i.get("publishedfileid")]
        if not ids:
            return SearchResult(items=[], total=total, page=page)
        # QueryFiles ranks/orders; hydrate counts/size/preview via the keyless
        # batch endpoint (more reliably populated), preserving search order.
        hydrated = {
            str(h.get("publishedfileid")): h
            for h in await api.get_published_file_details(ids)
            if h.get("result") == 1
        }
        by_id = {str(i.get("publishedfileid")): i for i in items}
        summaries = [_to_summary(hydrated.get(iid) or by_id[iid]) for iid in ids]
        return SearchResult(items=summaries, total=total, page=page)

    async def get_summaries(self, item_ids: list[str]) -> list[ModSummary]:
        rows = await api.get_published_file_details(item_ids)
        # result == 1 means the item exists and is visible.
        return [_to_summary(r) for r in rows if r.get("result") == 1]

    async def get_details(self, item_id: str) -> ModDetails:
        if api.has_api_key():
            rows = await api.get_details([item_id])
        else:
            rows = await api.get_published_file_details([item_id])
        if not rows:
            raise api.SteamApiError(f"workshop item {item_id} not found")
        return _to_details(rows[0])

    async def get_dependencies(self, item_id: str) -> list[Dependency]:
        if not api.has_api_key():
            return []
        rows = await api.get_details([item_id])
        return _dependencies(rows[0]) if rows else []

    async def resolve_collection(self, collection_id: str) -> list[str]:
        result = await api.get_collection_details([collection_id])
        return result.get(collection_id, [])

    async def resolve_collections(self, ids: list[str]) -> dict[str, list[str]]:
        # One keyless call for all ids; plain items come back with no children.
        result = await api.get_collection_details(ids)
        return {cid: members for cid, members in result.items() if members}
