"""Game template ("egg") schema and placeholder validation."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Matches {{TOKEN}} with optional surrounding whitespace.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
# Template identifiers / variable keys must be simple tokens (no shell metachars).
TOKEN_RE = re.compile(r"^[A-Za-z0-9_]+$")
# Steam beta branch names (passed to steamcmd as `-beta <name>`).
BRANCH_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
# Where a panel-managed config key is edited (see ConfigFileSpec.managed_keys).
MANAGED_BY_RE = re.compile(r"^(variables(:[A-Za-z0-9_]+)?|workshop|network)$")
# One printable console line (no newlines/control chars), e.g. "quit".
STOP_COMMAND_RE = re.compile(r"^[ -~]{1,128}$")


class PortSpec(BaseModel):
    name: str
    protocol: Literal["tcp", "udp", "both"]
    default: int = Field(ge=1, le=65535)
    # Number of consecutive ports this entry needs (e.g. Valheim uses port and
    # port+1 for the UDP query port). The allocator reserves a contiguous block;
    # only the base port is exposed as the {{PORT_<name>}} placeholder.
    count: int = Field(default=1, ge=1, le=8)
    # Tunnel provider profile for exposing this port (playit "tunnel_type",
    # e.g. "project-zomboid"). Game profiles let the provider pass the game's
    # traffic and reserve the right number of ports; without one the panel uses
    # a generic default.
    tunnel_profile: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,32}$")

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not TOKEN_RE.match(v):
            raise ValueError(f"port name '{v}' must match [A-Za-z0-9_]+")
        return v

    def protocols(self) -> list[str]:
        return ["tcp", "udp"] if self.protocol == "both" else [self.protocol]


class VarSpec(BaseModel):
    key: str
    default: str = ""
    # Auto-generate a strong secret when the value is empty. None keeps the
    # legacy heuristic (keys ending in PASSWORD); false opts out, e.g. a game
    # password where empty means "public server".
    generate: bool | None = None

    def should_generate(self) -> bool:
        if self.generate is not None:
            return self.generate
        return self.key.upper().endswith("PASSWORD")

    @field_validator("key")
    @classmethod
    def _valid_key(cls, v: str) -> str:
        if not TOKEN_RE.match(v):
            raise ValueError(f"variable key '{v}' must match [A-Za-z0-9_]+")
        return v


# A workshop install path lives inside the data dir; reject anything that could
# escape it (absolute paths, "..", shell metacharacters).
WORKSHOP_PATH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")


class WorkshopSpec(BaseModel):
    """Steam Workshop support for a template.

    Presence of this block marks the game as workshop-capable (the UI shows the
    Workshop tab only then). `app_id` is the Steam app whose workshop items are
    downloaded — often the CLIENT game app id, which can differ from the
    dedicated-server `app_id`. Downloaded items are copied into the server's data
    dir under `install_path/<item_id>`.
    """

    app_id: int = Field(ge=1)
    install_path: str = "steamapps/workshop"
    # Shown in the Workshop tab: how downloaded mods get enabled in this game
    # (automatically by a prestart hook, or what the user must edit by hand).
    note: str | None = None
    # Game-specific inspector that discovers the mods inside each downloaded item
    # (enables per-mod-id toggles + load order), e.g. "project_zomboid".
    inspector: str | None = None

    @field_validator("inspector")
    @classmethod
    def _valid_inspector(cls, v: str | None) -> str | None:
        if v is not None and not TOKEN_RE.match(v):
            raise ValueError(f"workshop inspector '{v}' must match [A-Za-z0-9_]+")
        return v

    @field_validator("install_path")
    @classmethod
    def _valid_path(cls, v: str) -> str:
        if ".." in v or v.startswith("/") or not WORKSHOP_PATH_RE.match(v):
            raise ValueError(f"workshop install_path '{v}' is not a safe relative path")
        return v.strip("/")


def _safe_rel_path(v: str, what: str) -> str:
    if ".." in v.split("/") or v.startswith("/") or not WORKSHOP_PATH_RE.match(v):
        raise ValueError(f"{what} '{v}' is not a safe relative path")
    return v.strip("/")


class ConfigFileSpec(BaseModel):
    """A game config file shown in the panel's Config editor."""

    path: str  # relative to the data dir
    label: str
    # ini: `Key=value` + `# description`; pz_sandbox: PZ SandboxVars.lua table;
    # text: raw editor only.
    format: Literal["ini", "pz_sandbox", "text"] = "text"
    # Keys the panel writes itself on every start (read-only in the form), each
    # with where the user changes it instead: "variables:<VAR>", "variables",
    # "workshop" (mods / load order) or "network" (ports). A plain list means
    # "variables" for all of them.
    managed_keys: dict[str, str] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def _valid_path(cls, v: str) -> str:
        return _safe_rel_path(v, "config file path")

    @field_validator("managed_keys", mode="before")
    @classmethod
    def _valid_managed(cls, v: object) -> object:
        if isinstance(v, list):
            v = {k: "variables" for k in v}
        if isinstance(v, dict):
            for key, where in v.items():
                if not MANAGED_BY_RE.match(str(where)):
                    raise ValueError(
                        f"managed_keys.{key}: '{where}' must be variables[:VAR], workshop or network"
                    )
        return v


class GameTemplate(BaseModel):
    id: str
    name: str
    app_id: int = Field(ge=1)
    anonymous_login: bool = True
    install_dir: str = "/data"
    # Mark a template as known-not-working so it stays visible in the catalog
    # (as a reference / warning) but cannot be used to create a server. Use this
    # for games whose dedicated-server files aren't actually obtainable via
    # SteamCMD (e.g. Deadside: the depot exists but ships no binaries), or that
    # have no Linux server. `unsupported_reason` is shown to the user.
    supported: bool = True
    unsupported_reason: str | None = None
    ports: list[PortSpec] = Field(default_factory=list)
    startup: str
    variables: list[VarSpec] = Field(default_factory=list)
    # Static environment variables injected into the server container at runtime
    # (e.g. SteamAppId for Valheim). Defined by the operator in the YAML, NOT
    # user-editable, so they're trusted and not part of the placeholder whitelist.
    env: dict[str, str] = Field(default_factory=dict)
    update_on_start: bool = True
    # Optional Steam Workshop support; when set the game is "workshop-capable".
    workshop: WorkshopSpec | None = None
    # Console command that makes the game save and exit by itself (sent to
    # stdin on stop/restart). Without it the container is just docker-stopped.
    stop_command: str | None = None
    # Seconds to wait for `stop_command` to finish before forcing the stop.
    stop_timeout: int = Field(default=30, ge=5, le=600)
    # Name of a game-specific script baked into the gameserver image
    # (/opt/hooks/<name>.sh) that runs right before launch, e.g. to write the
    # game's config file from variables. Never user-supplied content.
    prestart_hook: str | None = None
    # Steam beta branches offered as suggestions in the UI (e.g. "legacy41").
    branches: list[str] = Field(default_factory=list)
    # Config editor: declared files (structured or raw) and directories whose
    # files can be browsed/edited raw (e.g. mods' own configs). This list is the
    # whitelist of what the panel may read/write in the data dir.
    config_files: list[ConfigFileSpec] = Field(default_factory=list)
    config_dirs: list[str] = Field(default_factory=list)

    @field_validator("config_dirs")
    @classmethod
    def _valid_config_dirs(cls, v: list[str]) -> list[str]:
        return [_safe_rel_path(d, "config dir") for d in v]

    @field_validator("stop_command")
    @classmethod
    def _valid_stop_command(cls, v: str | None) -> str | None:
        if v is not None and not STOP_COMMAND_RE.match(v):
            raise ValueError("stop_command must be a single printable line (max 128 chars)")
        return v

    @field_validator("prestart_hook")
    @classmethod
    def _valid_hook(cls, v: str | None) -> str | None:
        if v is not None and not TOKEN_RE.match(v):
            raise ValueError(f"prestart_hook '{v}' must match [A-Za-z0-9_]+")
        return v

    @field_validator("branches")
    @classmethod
    def _valid_branches(cls, v: list[str]) -> list[str]:
        for b in v:
            if not BRANCH_RE.match(b):
                raise ValueError(f"branch '{b}' must match {BRANCH_RE.pattern}")
        return v

    @property
    def workshop_supported(self) -> bool:
        return self.workshop is not None

    @field_validator("env")
    @classmethod
    def _valid_env(cls, v: dict[str, str]) -> dict[str, str]:
        for key in v:
            if not TOKEN_RE.match(key):
                raise ValueError(f"env key '{key}' must match [A-Za-z0-9_]+")
        return v

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not TOKEN_RE.match(v):
            raise ValueError(f"template id '{v}' must match [A-Za-z0-9_]+")
        return v

    @model_validator(mode="after")
    def _validate_placeholders(self) -> GameTemplate:
        """Every {{token}} in startup must be a known PORT_<name> or variable key.

        This whitelist is the core injection guard: nothing outside the declared
        ports/variables is ever interpolated into the startup command line.
        """
        allowed: set[str] = {f"PORT_{p.name}" for p in self.ports}
        allowed |= {v.key for v in self.variables}
        used = set(PLACEHOLDER_RE.findall(self.startup))
        unknown = used - allowed
        if unknown:
            raise ValueError(
                f"template '{self.id}' startup references unknown placeholders: "
                f"{sorted(unknown)}; allowed: {sorted(allowed)}"
            )
        return self

    def allowed_placeholders(self) -> set[str]:
        return {f"PORT_{p.name}" for p in self.ports} | {v.key for v in self.variables}


def render_startup(startup: str, values: dict[str, str], allowed: set[str]) -> str:
    """Render a startup command by substituting whitelisted placeholders only.

    `values` maps placeholder name -> string value. Any placeholder not in
    `allowed` (or missing from `values`) raises — never a silent passthrough,
    never a shell eval.
    """

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in allowed:
            raise ValueError(f"illegal placeholder '{token}' in startup")
        if token not in values:
            raise ValueError(f"no value provided for placeholder '{token}'")
        return str(values[token])

    return PLACEHOLDER_RE.sub(_sub, startup)
