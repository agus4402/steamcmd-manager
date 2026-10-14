"""Shared types for structured config editors (see ini.py, pz_sandbox.py)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


@dataclass(slots=True)
class EnumOption:
    value: str
    label: str


@dataclass(slots=True)
class ConfigField:
    """One editable setting, as rendered by the panel's config form."""

    path: str  # unique key used to address the field when applying changes
    section: str  # grouping in the form (e.g. "Server", "ZombieLore")
    value: str  # current raw value (strings unquoted)
    type: str  # bool | int | float | string
    description: str | None = None
    enum: list[EnumOption] = field(default_factory=list)
    min: float | None = None
    max: float | None = None
    default: str | None = None
    # Written by the panel itself on every start (read-only in the form).
    managed: bool = False
    # Section added by a mod rather than the base game.
    mod: bool = False


def infer_type(value: str) -> str:
    if value in ("true", "false"):
        return "bool"
    if _INT_RE.match(value):
        return "int"
    if _FLOAT_RE.match(value):
        return "float"
    return "string"


def validate_value(f: ConfigField, value: str) -> str:
    """Check a new value against the field's type/limits; return it normalized."""
    value = value.strip() if f.type != "string" else value
    if f.type == "bool":
        if value not in ("true", "false"):
            raise ValueError(f"{f.path}: expected true or false")
    elif f.type == "int":
        if not _INT_RE.match(value):
            raise ValueError(f"{f.path}: expected an integer")
    elif f.type == "float":
        if not (_FLOAT_RE.match(value) or _INT_RE.match(value)):
            raise ValueError(f"{f.path}: expected a number")
    if f.type in ("int", "float"):
        num = float(value)
        if f.min is not None and num < f.min or f.max is not None and num > f.max:
            raise ValueError(f"{f.path}: must be between {f.min} and {f.max}")
        if f.type == "float" and "." not in value:
            value = f"{value}.0"
    if f.enum and value not in {o.value for o in f.enum}:
        raise ValueError(f"{f.path}: not one of the allowed options")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{f.path}: value cannot contain line breaks")
    return value
