"""Unit tests for Workshop parsing + Steam metadata mapping (no DB, no network)."""

from __future__ import annotations

import asyncio

import pytest

from app.services import workshop_service as ws
from app.workshop.base import Dependency, WorkshopSort
from app.workshop.steam import api, provider


@pytest.fixture(autouse=True)
def _no_db_settle(monkeypatch):
    """The queue worker settles stranded mods in the DB after each batch; these
    unit tests have no DB."""

    async def noop(mod_ids):
        return None

    monkeypatch.setattr(ws, "_settle_stranded", noop)


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
    """Graph with a cycle (A->B->C->A), a duplicate edge (A->B twice) and a
    second root (X->Y->B) sharing a dependency with the first."""

    id = "steam"
    _graph = {
        "A": ["B", "C", "B"],
        "B": ["C", "D"],
        "C": ["A"],  # cycle back to root
        "X": ["Y"],
        "Y": ["B"],
    }

    def __init__(self):
        self.calls: list[list[str]] = []

    async def get_dependencies_many(self, item_ids):
        self.calls.append(list(item_ids))
        return {
            i: [Dependency(item_id=d) for d in self._graph[i]]
            for i in item_ids
            if i in self._graph
        }


def test_resolve_dependencies_handles_cycle_and_dedup(monkeypatch):
    monkeypatch.setattr(ws, "get_provider", lambda *_: _FakeProvider())
    result = asyncio.run(ws._resolve_dependencies(["A"]))
    # Root excluded, each dep once, no infinite loop from the cycle.
    assert result == {"B": "A", "C": "A", "D": "A"}


def test_resolve_dependencies_batches_per_level(monkeypatch):
    fake = _FakeProvider()
    monkeypatch.setattr(ws, "get_provider", lambda *_: fake)
    result = asyncio.run(ws._resolve_dependencies(["A", "X"]))
    assert result == {"B": "A", "C": "A", "D": "A", "Y": "X"}
    # One lookup per depth level, never one per item.
    assert fake.calls == [["A", "X"], ["B", "C", "Y"], ["D"]]


def test_resolve_dependencies_empty_when_no_deps(monkeypatch):
    class _Empty:
        async def get_dependencies_many(self, item_ids):
            return {}

    monkeypatch.setattr(ws, "get_provider", lambda *_: _Empty())
    assert asyncio.run(ws._resolve_dependencies(["A"])) == {}


def test_steam_dependencies_many_is_chunked(monkeypatch):
    calls: list[int] = []

    async def fake_get_details(ids):
        calls.append(len(ids))
        return [{"publishedfileid": i, "children": [{"publishedfileid": "9"}]} for i in ids]

    monkeypatch.setattr(api.settings, "steam_api_key", "KEY")
    monkeypatch.setattr(api, "get_details", fake_get_details)
    ids = [str(i) for i in range(1, 251)]
    out = asyncio.run(provider.SteamWorkshopProvider().get_dependencies_many(ids))
    assert calls == [100, 100, 50]
    assert len(out) == 250 and out["1"][0].item_id == "9"


def test_steam_dependencies_many_without_key(monkeypatch):
    monkeypatch.setattr(api.settings, "steam_api_key", "")
    assert asyncio.run(provider.SteamWorkshopProvider().get_dependencies_many(["1"])) == {}


# -- bulk install is non-blocking ---------------------------------------------


class _FakeSession:
    def __init__(self, existing: list[str]):
        self.added: list = []
        self.commits = 0
        self._existing = existing

    async def execute(self, _stmt):
        class _Rows:
            def __init__(self, ids):
                self._ids = ids

            def all(self):
                return [(i,) for i in self._ids]

        return _Rows(self._existing)

    def add(self, obj):
        obj.id = f"row-{len(self.added)}"
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        pass


def test_import_install_batches_and_defers_dependencies(monkeypatch):
    summary_calls: list[list[str]] = []
    downloads: list[str] = []
    dep_jobs: list[list[str]] = []

    class _Provider:
        async def get_summaries(self, ids):
            summary_calls.append(list(ids))
            return []

    async def fake_download(server_id, mod_id):
        downloads.append(mod_id)

    async def fake_deps(server_id, root_ids):
        dep_jobs.append(root_ids)

    monkeypatch.setattr(ws, "get_provider", lambda *_: _Provider())
    monkeypatch.setattr(ws, "_download_job", fake_download)
    monkeypatch.setattr(ws, "_enqueue_dependencies", fake_deps)

    class _Server:
        id = "srv"
        workshop_app_id = 108600

    ids = [str(1000 + i) for i in range(120)]

    async def run():
        session = _FakeSession(existing=["1005"])
        queued, skipped = await ws.import_install(session, _Server(), ids + ["1001"])
        await asyncio.sleep(0)  # let the spawned background tasks run
        return session, queued, skipped

    session, queued, skipped = asyncio.run(run())
    assert skipped == ["1005", "1001"]  # already installed + repeated
    assert [m.item_id for m in queued] == [i for i in ids if i != "1005"]
    assert session.commits == 1
    assert summary_calls == [[i for i in ids if i != "1005"]]  # one batched lookup
    # Creation order is kept in created_at (sorting by "added" keeps the collection order).
    stamps = [m.created_at for m in queued]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)
    assert len(downloads) == 119
    assert dep_jobs == [[i for i in ids if i != "1005"]]


# -- batched download queue ---------------------------------------------------


def test_parse_download_results():
    logs = (
        "[entrypoint] steamcmd attempt 1/6\n"
        "[workshop-result] 111 ok\n"
        "Success. Downloaded item 111\n"
        "[workshop-result] 444 failed ERROR! Download item 444 failed (Timeout).\n"
        "[workshop-result] 555 failed\n"
    )
    assert ws.parse_download_results(logs) == {
        "111": (True, None),
        "444": (False, "ERROR! Download item 444 failed (Timeout)."),
        "555": (False, None),
    }
    assert ws.parse_download_results("") == {}


def test_queue_batches_per_server_and_waits(monkeypatch):
    batches: list[tuple[str, list[str]]] = []

    async def fake_batch(server_id, mod_ids):
        batches.append((server_id, list(mod_ids)))
        await asyncio.sleep(0)

    monkeypatch.setattr(ws, "_download_batch", fake_batch)
    monkeypatch.setattr(ws, "_BATCH_SIZE", 3)
    monkeypatch.setattr(ws, "_pending", [])
    monkeypatch.setattr(ws, "_worker", None)

    async def run():
        jobs = [ws._download_job("s1", f"m{i}") for i in range(5)]
        jobs += [ws._download_job("s2", "x1"), ws._download_job("s1", "m0")]  # m0 twice
        await asyncio.wait_for(asyncio.gather(*jobs), timeout=2)  # every caller is released

    asyncio.run(run())
    # One session at a time; same-server batches of 3; the repeated m0 rides along.
    assert batches == [("s1", ["m0", "m1", "m2"]), ("s1", ["m3", "m4"]), ("s2", ["x1"])]


def test_queue_survives_a_crashing_batch(monkeypatch):
    calls: list[list[str]] = []

    async def boom(server_id, mod_ids):
        calls.append(mod_ids)
        if len(calls) == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(ws, "_download_batch", boom)
    monkeypatch.setattr(ws, "_BATCH_SIZE", 1)
    monkeypatch.setattr(ws, "_pending", [])
    monkeypatch.setattr(ws, "_worker", None)

    async def run():
        await asyncio.wait_for(
            asyncio.gather(ws._download_job("s", "a"), ws._download_job("s", "b")), timeout=2
        )

    asyncio.run(run())
    assert calls == [["a"], ["b"]]


def test_cancel_server_downloads_drops_only_that_server(monkeypatch):
    async def run():
        loop = asyncio.get_running_loop()
        a, b, c = loop.create_future(), loop.create_future(), loop.create_future()
        monkeypatch.setattr(ws, "_pending", [("s1", "m1", a), ("s2", "x", b), ("s1", "m2", c)])
        assert ws.cancel_server_downloads("s1") == 2
        assert [e[1] for e in ws._pending] == ["x"]
        assert a.done() and c.done() and not b.done()  # waiters of s1 are released

    asyncio.run(run())


# -- download progress ---------------------------------------------------------


def _mod(mid, item, status, size):
    from app.models.workshop_mod import WorkshopMod

    return WorkshopMod(id=mid, server_id="s", item_id=item, status=status, file_size=size)


def test_build_progress_overall_and_per_mod():
    mods = [
        _mod("a", "1", "installed", 100),
        _mod("b", "2", "error", 50),
        _mod("c", "3", "downloading", 200),  # half on disk
        _mod("d", "4", "downloading", 300),  # already copied in (batch still running)
        _mod("e", "5", "downloading", 0),  # unknown size, not in the agent's view yet
        _mod("f", "6", "queued", 400),
    ]
    live = {
        "attempt": 2,
        "max_attempts": 6,
        "items": {"3": {"bytes": 100, "state": "downloading"}, "4": {"bytes": 300, "state": "ok"}},
    }
    p = ws.build_progress(mods, ["c", "d", "e"], live)
    assert (p["total"], p["done"], p["failed"]) == (6, 2, 1)
    assert p["bytes_total"] == 1050
    assert p["bytes_done"] == 100 + 50 + 100 + 300
    assert (p["attempt"], p["max_attempts"]) == (2, 6)
    assert set(p["items"]) == {"c", "d", "e"}  # only the running batch
    assert p["items"]["c"] == {"state": "downloading", "bytes": 100, "total": 200, "fraction": 0.5}
    assert p["items"]["d"]["fraction"] == 1.0
    assert p["items"]["e"] == {"state": "starting", "bytes": 0, "total": 0, "fraction": 0.0}


def test_build_progress_caps_unfinished_mod_under_full():
    # du can exceed Steam's size (an update next to the old copy): never show 100%.
    p = ws.build_progress([_mod("c", "3", "downloading", 100)], ["c"],
                          {"items": {"3": {"bytes": 250, "state": "downloading"}}})
    assert p["items"]["c"]["fraction"] == 0.99


def test_build_progress_idle():
    p = ws.build_progress([], [], {})
    assert p["active"] is False and p["total"] == 0 and p["items"] == {}


def test_run_tracking_spans_batches_and_ends_when_drained(monkeypatch):
    seen: list[tuple[set[str], list[str]]] = []

    async def fake_batch(server_id, mod_ids):
        seen.append((set(ws._runs.get(server_id, set())), ws._active[server_id][0]))
        await asyncio.sleep(0)

    monkeypatch.setattr(ws, "_download_batch", fake_batch)
    monkeypatch.setattr(ws, "_BATCH_SIZE", 2)
    monkeypatch.setattr(ws, "_pending", [])
    monkeypatch.setattr(ws, "_worker", None)
    monkeypatch.setattr(ws, "_runs", {})
    monkeypatch.setattr(ws, "_active", {})

    async def run():
        await asyncio.wait_for(
            asyncio.gather(*(ws._download_job("s1", f"m{i}") for i in range(3))), timeout=2
        )

    asyncio.run(run())
    # The run holds all 3 mods through both batches, then is dropped.
    assert seen == [({"m0", "m1", "m2"}, ["m0", "m1"]), ({"m0", "m1", "m2"}, ["m2"])]
    assert ws._runs == {} and ws._active == {}


def test_batch_records_every_mod_even_if_one_fails(monkeypatch):
    """A mod whose result can't be recorded (e.g. its inspection collided) must
    not leave the rest of its batch stuck on "downloading"."""
    finished: list[str] = []

    async def flaky_finish(mod_id, code, logs):
        finished.append(mod_id)
        if mod_id == "m2":
            raise RuntimeError("IntegrityError: duplicate submod")

    class FakeSession:
        def __init__(self):
            self.mods = {
                f"m{i}": _mod(f"m{i}", str(100 + i), "queued", 1) for i in range(1, 5)
            }

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, model, key):
            if model is ws.Server:
                srv = ws.Server(id="s", template_id="project_zomboid")
                srv.workshop_app_id = 108600
                return srv
            return self.mods.get(key)

        async def commit(self):
            pass

    logs = "\n".join(f"[workshop-result] {100 + i} ok" for i in range(1, 5))
    monkeypatch.setattr(ws, "SessionLocal", FakeSession)
    monkeypatch.setattr(ws, "_finish", flaky_finish)
    monkeypatch.setattr(ws.orchestrator, "download_workshop_items", lambda *a: (0, logs))

    asyncio.run(ws._download_batch("s", ["m1", "m2", "m3", "m4"]))
    assert finished == ["m1", "m2", "m3", "m4"]
