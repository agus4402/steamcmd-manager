"""Steam Web API client for Workshop metadata.

Runs in the **backend** (which has internet egress). Four endpoints are used:

* ``IPublishedFileService/QueryFiles``      — search (needs an API key)
* ``IPublishedFileService/GetDetails``      — details + ``children`` deps (needs key)
* ``ISteamRemoteStorage/GetPublishedFileDetails`` — batch metadata (keyless)
* ``ISteamRemoteStorage/GetCollectionDetails``    — collection members (keyless)

All responses use a ``{"response": {...}}`` envelope. Search and dependency data
require ``settings.steam_api_key``; the keyless endpoints are the fallback for
metadata and collection resolution.
"""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.workshop.base import WorkshopProviderError, WorkshopSort

settings = get_settings()

_BASE = "https://api.steampowered.com"
_TIMEOUT = httpx.Timeout(20.0)

# UI sort -> EPublishedFileQueryType integer.
_QUERY_TYPE = {
    WorkshopSort.POPULAR: 0,  # RankedByVote
    WorkshopSort.SUBSCRIBED: 12,  # RankedByTotalUniqueSubscriptions
    WorkshopSort.TRENDING: 3,  # RankedByTrend
    WorkshopSort.UPDATED: 21,  # RankedByLastUpdatedDate
    WorkshopSort.NEWEST: 1,  # RankedByPublicationDate
}


class SteamApiError(WorkshopProviderError):
    """A Steam Web API call failed (network, key, or API-level)."""


def has_api_key() -> bool:
    return bool(settings.steam_api_key.strip())


def _require_key() -> str:
    key = settings.steam_api_key.strip()
    if not key:
        raise SteamApiError(
            "this feature requires a Steam Web API key (set STEAM_API_KEY)"
        )
    return key


async def _get(path: str, params: dict) -> dict:
    url = f"{_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise SteamApiError(f"steam api unreachable: {exc}") from exc
    if resp.status_code == 403:
        raise SteamApiError("steam api rejected the request (check STEAM_API_KEY)")
    return _envelope(resp)


async def _post(path: str, data: dict) -> dict:
    url = f"{_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, data=data)
    except httpx.HTTPError as exc:
        raise SteamApiError(f"steam api unreachable: {exc}") from exc
    return _envelope(resp)


def _envelope(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
    except ValueError as exc:
        raise SteamApiError(f"{resp.status_code}: non-JSON response") from exc
    response = body.get("response")
    if not isinstance(response, dict):
        raise SteamApiError(f"{resp.status_code}: unexpected response shape")
    return response


def _ids_payload(item_ids: list[str], count_key: str) -> dict:
    payload: dict[str, str | int] = {count_key: len(item_ids)}
    for i, iid in enumerate(item_ids):
        payload[f"publishedfileids[{i}]"] = iid
    return payload


# -- search + details (need an API key) ---------------------------------------


async def query_files(
    *,
    query: str,
    app_id: int,
    page: int,
    page_size: int,
    sort: WorkshopSort,
) -> tuple[list[dict], int]:
    """Search workshop items for ``app_id``. Returns (items, total)."""
    response = await _get(
        "/IPublishedFileService/QueryFiles/v1/",
        {
            "key": _require_key(),
            "query_type": _QUERY_TYPE.get(sort, 0),
            "appid": app_id,
            "search_text": query,
            "page": max(1, page),
            "numperpage": page_size,
            "return_previews": "true",
            "return_short_description": "true",
            "return_vote_data": "false",
            "return_metadata": "true",
        },
    )
    items = response.get("publishedfiledetails") or []
    total = int(response.get("total") or 0)
    return [i for i in items if isinstance(i, dict)], total


async def get_details(item_ids: list[str]) -> list[dict]:
    """Detailed metadata incl. ``children`` (dependencies). Needs an API key."""
    if not item_ids:
        return []
    params: dict[str, str | int] = {
        "key": _require_key(),
        "includechildren": "true",
        "includetags": "false",
        "includevotes": "false",
        "includeforsaledata": "false",
        "includemetadata": "true",
    }
    for i, iid in enumerate(item_ids):
        params[f"publishedfileids[{i}]"] = iid
    response = await _get("/IPublishedFileService/GetDetails/v1/", params)
    items = response.get("publishedfiledetails") or []
    return [i for i in items if isinstance(i, dict)]


# -- keyless metadata + collections -------------------------------------------


async def get_published_file_details(item_ids: list[str]) -> list[dict]:
    """Batch metadata for items (keyless). No ``children`` field."""
    if not item_ids:
        return []
    response = await _post(
        "/ISteamRemoteStorage/GetPublishedFileDetails/v1/",
        _ids_payload(item_ids, "itemcount"),
    )
    items = response.get("publishedfiledetails") or []
    return [i for i in items if isinstance(i, dict)]


async def get_collection_details(collection_ids: list[str]) -> dict[str, list[str]]:
    """Member item ids per collection id (keyless)."""
    if not collection_ids:
        return {}
    response = await _post(
        "/ISteamRemoteStorage/GetCollectionDetails/v1/",
        _ids_payload(collection_ids, "collectioncount"),
    )
    out: dict[str, list[str]] = {}
    for coll in response.get("collectiondetails") or []:
        if not isinstance(coll, dict) or coll.get("result") != 1:
            continue
        cid = str(coll.get("publishedfileid") or "")
        children = [
            str(c.get("publishedfileid"))
            for c in (coll.get("children") or [])
            if isinstance(c, dict) and c.get("publishedfileid")
        ]
        if cid:
            out[cid] = children
    return out
