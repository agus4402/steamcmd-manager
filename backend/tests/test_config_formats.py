"""Config editor: parsers (against real PZ files) + path whitelist. No DB/network."""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from app.config_formats import ini, pz_sandbox
from app.config_formats.base import ConfigField, validate_value
from app.services import config_service
from app.services.template_loader import get_template

FIXTURES = Path(__file__).parent / "fixtures"
INI = (FIXTURES / "pzserver.ini").read_text(encoding="utf-8")
SANDBOX = (FIXTURES / "pzserver_SandboxVars.lua").read_text(encoding="utf-8")


def _changed_lines(before: str, after: str) -> list[str]:
    return [
        line
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


# -- ini ------------------------------------------------------------------------


def test_ini_parse_descriptions_types_managed():
    fields = {f.path: f for f in ini.parse(INI, {"PVP"})}
    assert fields["PauseEmpty"].type == "bool"
    assert fields["PauseEmpty"].description == "Game time stops when there are no players online"
    assert fields["PVP"].managed and not fields["PauseEmpty"].managed
    assert fields["MaxPlayers"].type == "int"


def test_ini_apply_touches_only_that_line():
    out = ini.apply(INI, {"PauseEmpty": "false"})
    assert _changed_lines(INI, out) == ["-PauseEmpty=true", "+PauseEmpty=false"]


def test_ini_apply_appends_unknown_and_strips_newlines():
    out = ini.apply("A=1\n", {"B": "x\nEvil=1"})
    assert out == "A=1\nB=xEvil=1\n"


def test_ini_preserves_crlf():
    assert ini.apply("A=1\r\nB=2\r\n", {"B": "3"}) == "A=1\r\nB=3\r\n"


# -- pz sandbox ---------------------------------------------------------------------


def test_sandbox_enum_default_and_sections():
    fields = {f.path: f for f in pz_sandbox.parse(SANDBOX)}
    speed = fields["ZombieLore.Speed"]
    assert speed.section == "ZombieLore" and not speed.mod
    assert [o.label for o in speed.enum][:2] == ["Sprinters", "Fast Shamblers"]
    assert fields["Zombies"].default == "4" and fields["Zombies"].section == "General"
    assert "VERSION" not in fields


def test_sandbox_range():
    f = next(f for f in pz_sandbox.parse(SANDBOX) if f.path == "FoodLootNew")
    assert (f.min, f.max, f.default, f.type) == (0.0, 4.0, "0.80", "float")
    assert f.description == "Any food that can rot or spoil."


def test_sandbox_apply_only_changed_lines_and_quotes_strings():
    out = pz_sandbox.apply(SANDBOX, {"ZombieLore.Speed": "1", "WorldItemRemovalList": 'Base."Hat'})
    changed = _changed_lines(SANDBOX, out)
    assert "+        Speed = 1," in changed
    assert '+    WorldItemRemovalList = "Base.\\"Hat",' in changed
    assert len(changed) == 4


def test_sandbox_mod_tables_flagged():
    text = SANDBOX.rstrip().rstrip("}") + "    BetterLockpicking = {\n        Chance = 30,\n    },\n}\n"
    f = next(f for f in pz_sandbox.parse(text) if f.path == "BetterLockpicking.Chance")
    assert f.mod and f.section == "BetterLockpicking"


def test_sandbox_unknown_path_rejected():
    with pytest.raises(KeyError):
        pz_sandbox.apply(SANDBOX, {"Nope.Missing": "1"})


# -- validation ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ftype", "value", "ok"),
    [("bool", "true", True), ("bool", "yes", False), ("int", "5", True), ("int", "5.5", False),
     ("float", "2", True), ("float", "abc", False), ("string", "a\nb", False)],
)
def test_validate_value_types(ftype, value, ok):
    f = ConfigField(path="x", section="s", value="", type=ftype)
    if ok:
        validate_value(f, value)
    else:
        with pytest.raises(ValueError):
            validate_value(f, value)


def test_validate_value_range_and_float_normalized():
    f = ConfigField(path="x", section="s", value="1.0", type="float", min=0, max=4)
    assert validate_value(f, "2") == "2.0"
    with pytest.raises(ValueError):
        validate_value(f, "5")


# -- whitelist --------------------------------------------------------------------------


def test_whitelist():
    t = get_template("project_zomboid")
    assert config_service.check_allowed(t, "Zomboid/Server/pzserver.ini").format == "ini"
    assert config_service.check_allowed(t, "Zomboid/Lua/SomeMod/config.ini") is None
    for bad in ["../x", "/etc/passwd", "Zomboid/db/pzserver.db", "Zomboid/Lua/../db/x", "Zomboid/Lua//x"]:
        with pytest.raises(config_service.NotAllowed):
            config_service.check_allowed(t, bad)
