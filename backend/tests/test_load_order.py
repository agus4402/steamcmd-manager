"""Sub-mod discovery (PZ inspector), load-order warnings and start env. No DB."""

from __future__ import annotations

from app.services.load_order_service import LoadOrderEntry, WorkshopRuntime, compute_warnings
from app.workshop.inspectors import project_zomboid as pz

ROOT = "steamapps/workshop/content/108600/111"
M = f"{ROOT}/mods"


def test_choose_newest_version_folder_or_b41_root():
    infos = [
        f"{M}/Cool Map [x]/42.0/mod.info",
        f"{M}/Cool Map [x]/42.12/mod.info",
        f"{M}/Cool Map [x]/42.2/mod.info",
        f"{M}/Old/mod.info",
        f"{M}/Both/42/mod.info",
        f"{M}/Both/mod.info",
        f"{M}/Both/common/mod.info",  # version folder wins over common/
        f"{M}/CommonOnly/common/mod.info",  # B42 fallback when version dirs lack it
        f"{M}/CommonOnly/mod.info",
    ]
    chosen = pz.choose_mod_infos(infos, M, None)
    assert chosen[f"{M}/Cool Map [x]"].endswith("/42.12/mod.info")
    assert chosen[f"{M}/Old"].endswith("/Old/mod.info")
    assert chosen[f"{M}/Both"].endswith("/42/mod.info")
    assert chosen[f"{M}/CommonOnly"].endswith("/common/mod.info")
    assert pz.choose_mod_infos(infos, M, "legacy41")[f"{M}/Both"] == f"{M}/Both/mod.info"


def test_parse_mod_info_and_requires():
    info = pz.parse_mod_info(
        "name=Cool Mod\r\nid= CoolId \nrequire=\\tsarslib,\\ModOptions; Other\n"
    )
    assert info["id"] == "CoolId" and info["name"] == "Cool Mod"
    assert pz.parse_requires(info["require"]) == ["tsarslib", "ModOptions", "Other"]
    assert pz.parse_requires(None) == []


def test_build_submods_maps_and_skips():
    infos = [f"{M}/A/42/mod.info", f"{M}/B/mod.info", f"{M}/NoId/42/mod.info"]
    dirs = [
        f"{M}/A/42/media/maps/CoolTown",
        f"{M}/A/common/Media/maps/RavenCreek",
        f"{M}/A/42/media/maps/Muldraugh, KY",
        f"{M}/A/42/media/maps/CoolTown/sub",
    ]
    files = {
        f"{M}/A/42/mod.info": "id=AId\nname=A\nrequire=\\BId,\\AId",
        f"{M}/B/mod.info": "id=BId",
        f"{M}/NoId/42/mod.info": "name=broken",
    }
    subs = pz.build_submods(ROOT, infos, dirs, files.get, None)
    assert [s.mod_id for s in subs] == ["AId", "BId"]
    a = subs[0]
    assert a.folder == "mods/A" and a.requires == ["BId"]  # self-require dropped
    assert a.maps == ["CoolTown", "RavenCreek"]


def _entry(mod_id, enabled=True, requires=()):
    return LoadOrderEntry(
        id=mod_id,
        mod_id=mod_id,
        name=None,
        enabled=enabled,
        load_order=0,
        item_id="1",
        item_title=None,
        workshop_mod_id="w",
        requires=list(requires),
        maps=[],
    )


def test_warnings():
    entries = [
        _entry("A", requires=["lib"]),  # lib loads after A
        _entry("lib"),
        _entry("B", requires=["off"]),
        _entry("off", enabled=False),
        _entry("C", requires=["missing"]),
        _entry("D", enabled=False, requires=["missing"]),  # disabled: no warnings
    ]
    compute_warnings(entries)
    w = {e.mod_id: e.warnings for e in entries}
    assert w["A"] == ["requires lib, which loads after it"]
    assert w["B"] == ["requires off, which is disabled"]
    assert w["C"] == ["requires missing, which is not installed"]
    assert w["D"] == [] and w["lib"] == []


def test_runtime_env_explicit_mods():
    from app.services import server_service as ss
    from tests.test_template_runtime import _pz_server

    env = ss.build_runtime_env(
        _pz_server(), None, WorkshopRuntime(items=["1", "2"], mod_ids=["B", "A"], maps=["Town"])
    )
    assert env["WORKSHOP_ITEMS"] == "1;2"
    assert env["WORKSHOP_MOD_IDS"] == "B;A" and env["WORKSHOP_MAPS"] == "Town"

    env = ss.build_runtime_env(
        _pz_server(), None, WorkshopRuntime(items=["1"], mod_ids=None, maps=None)
    )
    assert "WORKSHOP_MOD_IDS" not in env
