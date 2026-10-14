"""Unit tests for template lifecycle fields + runtime env (no DB, no network)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.port_allocation import PortAllocation
from app.models.server import Server
from app.schemas.server import ServerUpdate
from app.schemas.template import GameTemplate, VarSpec
from app.services import server_service as ss
from app.services.template_loader import get_template


def _tpl(**extra) -> GameTemplate:
    return GameTemplate(id="t", name="T", app_id=1, startup="./run", **extra)


# -- template schema ----------------------------------------------------------


def test_lifecycle_fields_default_off():
    t = _tpl()
    assert t.stop_command is None and t.stop_timeout == 30
    assert t.prestart_hook is None and t.branches == []


@pytest.mark.parametrize("cmd", ["quit\nrm -rf /", "", "x" * 129, "save\x00"])
def test_stop_command_rejects_non_single_line(cmd):
    with pytest.raises(ValidationError):
        _tpl(stop_command=cmd)


@pytest.mark.parametrize("hook", ["../evil", "a b", "x;y", "hook.sh"])
def test_prestart_hook_must_be_token(hook):
    with pytest.raises(ValidationError):
        _tpl(prestart_hook=hook)


@pytest.mark.parametrize("branch", ["bad branch", "a;b", "", "x" * 65])
def test_branches_validated(branch):
    with pytest.raises(ValidationError):
        _tpl(branches=[branch])


def test_server_update_branch_pattern():
    assert ServerUpdate(steam_branch="legacy41").steam_branch == "legacy41"
    assert ServerUpdate(steam_branch="").steam_branch == ""
    with pytest.raises(ValidationError):
        ServerUpdate(steam_branch="-beta x; rm")


# -- variable generation ------------------------------------------------------


def test_generate_heuristic_and_override():
    assert VarSpec(key="RCON_PASSWORD").should_generate()
    assert not VarSpec(key="SERVER_PASSWORD", generate=False).should_generate()
    assert VarSpec(key="TOKEN", generate=True).should_generate()
    assert not VarSpec(key="NAME").should_generate()


def test_resolve_variables_respects_generate_false():
    t = _tpl(
        variables=[
            VarSpec(key="SERVER_PASSWORD", generate=False),
            VarSpec(key="ADMIN_PASSWORD"),
        ]
    )
    values = ss._resolve_variables(t, {})
    assert values["SERVER_PASSWORD"] == ""
    assert len(values["ADMIN_PASSWORD"]) >= 12


# -- runtime env ----------------------------------------------------------------


def _pz_server(**extra) -> Server:
    s = Server(
        id="abc123",
        name="pz",
        template_id="project_zomboid",
        app_id=380870,
        variables={"PUBLIC_NAME": "Hi", "ADMIN_PASSWORD": "a", "SERVER_PASSWORD": ""},
        startup_template=get_template("project_zomboid").startup,
        anonymous_login=True,
        **extra,
    )
    s.ports = [
        PortAllocation(name="game", protocol="udp", host_port=16300, is_primary=True),
        PortAllocation(name="game", protocol="udp", host_port=16301, is_primary=False),
        PortAllocation(name="rcon", protocol="tcp", host_port=27100, is_primary=True),
    ]
    return s


def test_runtime_env_exposes_ports_hook_and_mods():
    env = ss.build_runtime_env(_pz_server(), None, ["111", "222"])
    assert env["PORT_game"] == "16300" and env["PORT_rcon"] == "27100"
    assert env["PRESTART_HOOK"] == "project_zomboid"
    assert env["WORKSHOP_ITEMS"] == "111;222"
    assert env["PUBLIC_NAME"] == "Hi"
    assert "-cachedir=/data/Zomboid" in env["STARTUP_CMD"]
    assert "-port 16300" in env["STARTUP_CMD"]
    assert "STEAM_BRANCH" not in env


def test_runtime_env_without_workshop_omits_items():
    env = ss.build_runtime_env(_pz_server(), None, None)
    assert "WORKSHOP_ITEMS" not in env


def test_install_env_passes_branch():
    env = ss.build_install_env(_pz_server(steam_branch="legacy41"))
    assert env["STEAM_BRANCH"] == "legacy41"


def test_pz_template_lifecycle():
    t = get_template("project_zomboid")
    assert t.stop_command == "quit" and t.stop_timeout >= 60
    assert t.prestart_hook == "project_zomboid"
    assert "legacy41" in t.branches
