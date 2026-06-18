"""Game template ("egg") schema and placeholder validation."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Matches {{TOKEN}} with optional surrounding whitespace.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
# Template identifiers / variable keys must be simple tokens (no shell metachars).
TOKEN_RE = re.compile(r"^[A-Za-z0-9_]+$")


class PortSpec(BaseModel):
    name: str
    protocol: Literal["tcp", "udp", "both"]
    default: int = Field(ge=1, le=65535)

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

    @field_validator("key")
    @classmethod
    def _valid_key(cls, v: str) -> str:
        if not TOKEN_RE.match(v):
            raise ValueError(f"variable key '{v}' must match [A-Za-z0-9_]+")
        return v


class GameTemplate(BaseModel):
    id: str
    name: str
    app_id: int = Field(ge=1)
    anonymous_login: bool = True
    install_dir: str = "/data"
    ports: list[PortSpec] = Field(default_factory=list)
    startup: str
    variables: list[VarSpec] = Field(default_factory=list)
    update_on_start: bool = True

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
