"""Unit tests for Workshop parsing + Steam metadata mapping (no DB, no network)."""

from __future__ import annotations

import asyncio

import pytest

from app.services import workshop_service as ws
from app.workshop.base import Dependency, WorkshopSort
from app.workshop.steam import api, provider


# -- parse_item_id ------------------------------------------------------------


def test_parse_item_id_raw():
    assert ws.parse_item_id("2289615") == "2289615"


def test_parse_item_id_url():
    url = "https://steamcommunity.com/sharedfiles/filedetails/?id=2289615&searchtext=x"
    assert ws.parse_item_id(url) == "2289615"


def test_parse_item_id_embedded():
    assert ws.parse_item_id("mod 987654321 here") == "987654321"


def test_parse_item_id_invalid():
    with pytest.raises(ws.WorkshopError):
        ws.parse_item_id("no-digits-here")


# -- parse_many ---------------------------------------------------------------


def test_parse_many_comma_space_newline_and_dedup():
    ids, unparsed = ws.parse_many("111,222 333\n111\n444")
    assert ids == ["111", "222", "333", "444"]  # 111 de-duplicated, order kept
    assert unparsed == []


def test_parse_many_urls_and_unparsed():
    raw = "https://steamcommunity.com/sharedfiles/filedetails/?id=2289615 hello 987654321"
    ids, unparsed = ws.parse_many(raw)
    assert ids == ["2289615", "987654321"]
    assert unparsed == ["hello"]


def test_parse_many_empty():
    assert ws.parse_many("   \n  ") == ([], [])


# -- Steam metadata mapping ---------------------------------------------------


SAMPLE = {
    "publishedfileid": "2289615",
    "result": 1,
    "creator": "76561198000000000",
    "title": "Cool Mod",
    "description": "A description",
    "preview_url": "https://img/preview.jpg",
    "file_size": "1048576",
    "time_created": 1600000000,
    "time_updated": 1700000000,
    "subscriptions": 1234,
    "favorited": 56,
    "children": [
        {"publishedfileid": "111", "file_type": 0},
        {"publishedfileid": "222", "file_type": 0},
    ],
}


def test_to_summary_maps_fields():
    s = provider._to_summary(SAMPLE)
    assert s.item_id == "2289615"
    assert s.title == "Cool Mod"
    assert s.author_id == "76561198000000000"
    assert s.subscribers == 1234
    assert s.favorites == 56
    assert s.file_size == 1048576
    assert s.time_updated is not None and s.time_updated.year == 2023


def test_to_details_includes_dependencies():
    d = provider._to_details(SAMPLE)
    assert d.description == "A description"
    assert [dep.item_id for dep in d.dependencies] == ["111", "222"]
    assert d.images == ["https://img/preview.jpg"]


def test_ts_handles_zero_and_garbage():
    assert provider._ts(0) is None
    assert provider._ts("not-a-number") is None
    assert provider._ts(1700000000) is not None


# -- sort map + key gating ----------------------------------------------------


def test_query_type_covers_all_sorts():
    for sort in WorkshopSort:
        assert sort in api._QUERY_TYPE


def test_require_key_raises_without_key(monkeypatch):
    monkeypatch.setattr(api.settings, "steam_api_key", "")
    assert api.has_api_key() is False
    with pytest.raises(api.SteamApiError):
        api._require_key()


def test_require_key_ok_with_key(monkeypatch):
    monkeypatch.setattr(api.settings, "steam_api_key", "ABC123")
    assert api.has_api_key() is True
    assert api._require_key() == "ABC123"


# -- recursive dependency resolution -----------------------------------------


class _FakeProvider:
    """Graph with a cycle (A->B->C->A) and a duplicate edge (A->B twice)."""

    id = "steam"
    _graph = {
        "A": ["B", "C", "B"],
        "B": ["C"],
        "C": ["A"],  # cycle back to root
    }

    async def get_dependencies(self, item_id: str):
        return [Dependency(item_id=i) for i in self._graph.get(item_id, [])]


def test_resolve_dependency_ids_handles_cycle_and_dedup(monkeypatch):
    monkeypatch.setattr(ws, "get_provider", lambda *_: _FakeProvider())
    result = asyncio.run(ws._resolve_dependency_ids("A"))
    # Root excluded, each dep once, no infinite loop from the cycle.
    assert sorted(result) == ["B", "C"]


def test_resolve_dependency_ids_empty_when_no_deps(monkeypatch):
    class _Empty:
        async def get_dependencies(self, item_id: str):
            return []

    monkeypatch.setattr(ws, "get_provider", lambda *_: _Empty())
    assert asyncio.run(ws._resolve_dependency_ids("A")) == []
