"""Line-preserving parser/editor for Project Zomboid's `<server>_SandboxVars.lua`.

The file is one Lua table the game writes in a fixed, self-documenting shape:

    SandboxVars = {
        -- Description text. Min: 0.00 Max: 4.00 Default: 0.80
        FoodLoot = 0.8,
        -- How zombies are distributed. Default = Urban Focused
        -- 1 = Urban Focused
        -- 2 = Uniform
        Distribution = 1,
        ZombieLore = {
            Speed = 2,
        },
    }

Each `key = literal,` line becomes a ConfigField addressed by its dotted path
(e.g. "ZombieLore.Speed"); nested tables become form sections. Tables that the
base game doesn't define are mod sandbox options. Applying changes rewrites only
the value literal on the affected lines.
"""

from __future__ import annotations

import re

from app.config_formats.base import ConfigField, EnumOption, infer_type

# Nested tables written by the base game (Build 42); anything else is a mod's.
VANILLA_TABLES = frozenset({"Basement", "Map", "ZombieLore", "ZombieConfig", "MultiplierConfig"})
GENERAL = "General"
# Read-only bookkeeping keys the game manages itself.
_READONLY = frozenset({"VERSION"})

_OPEN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{\s*$")
_CLOSE_RE = re.compile(r"^\s*\}\s*,?\s*$")
_OPTION_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.+?)(\s*,?\s*)$")
_ENUM_RE = re.compile(r"^(-?\d+)\s*=\s*(.+)$")
_DEFAULT_LABEL_RE = re.compile(r"\s*Default\s*=\s*(.+)$")
_RANGE_RE = re.compile(
    r"\s*Min:\s*(-?[\d.]+)\s+Max:\s*(-?[\d.]+)(?:\s+Default:\s*(-?[\d.]+))?\s*$"
)


def _split_lines(text: str) -> tuple[list[str], str]:
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.split(newline), newline


def _unquote(literal: str) -> tuple[str, bool]:
    if len(literal) >= 2 and literal[0] == literal[-1] == '"':
        inner = literal[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\"), True
    return literal, False


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _walk(lines: list[str]):
    """Yield (index, path, match) for every option line, tracking table nesting."""
    stack: list[str] = []
    for i, line in enumerate(lines):
        if _OPEN_RE.match(line):
            stack.append(_OPEN_RE.match(line).group(1))
            continue
        if _CLOSE_RE.match(line):
            if stack:
                stack.pop()
            continue
        m = _OPTION_RE.match(line)
        if m and not line.strip().startswith("--") and stack:
            yield i, ".".join([*stack[1:], m.group(2)]), m


def parse(text: str) -> list[ConfigField]:
    lines, _ = _split_lines(text)
    fields: list[ConfigField] = []
    comments: dict[int, list[str]] = {}
    pending: list[str] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("--"):
            pending.append(s[2:].strip())
        else:
            comments[i] = pending
            pending = []

    for i, path, m in _walk(lines):
        key = m.group(2)
        if key in _READONLY and "." not in path:
            continue
        value, quoted = _unquote(m.group(4))
        section = path.rsplit(".", 1)[0] if "." in path else GENERAL
        enum: list[EnumOption] = []
        desc_parts: list[str] = []
        default_label = None
        lo = hi = None
        default = None
        for c in comments.get(i, []):
            em = _ENUM_RE.match(c)
            if em:
                enum.append(EnumOption(value=em.group(1), label=em.group(2).strip()))
                continue
            dm = _DEFAULT_LABEL_RE.search(c)
            if dm:
                default_label = dm.group(1).strip()
                c = c[: dm.start()].rstrip(". ").strip()
            rm = _RANGE_RE.search(c)
            if rm:
                lo, hi = float(rm.group(1)), float(rm.group(2))
                default = rm.group(3)
                c = c[: rm.start()].strip()
            if c:
                desc_parts.append(c)
        if default_label and enum:
            default = next((o.value for o in enum if o.label == default_label), None)
        fields.append(
            ConfigField(
                path=path,
                section=section,
                value=value,
                type="string" if quoted else infer_type(value),
                description=" ".join(desc_parts) or None,
                enum=enum,
                min=lo,
                max=hi,
                default=default,
                mod=section.split(".")[0] not in VANILLA_TABLES and section != GENERAL,
            )
        )
    return fields


def apply(text: str, changes: dict[str, str]) -> str:
    """Return `text` with the options at the given dotted paths set to new values.

    String-typed options (quoted in the file) stay quoted; others are written raw
    (the caller validates them against the parsed field types first).
    """
    lines, newline = _split_lines(text)
    pending = dict(changes)
    for i, path, m in _walk(lines):
        if path not in pending:
            continue
        _, quoted = _unquote(m.group(4))
        new = pending.pop(path)
        literal = _quote(new) if quoted else new
        lines[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{literal}{m.group(5)}"
    if pending:
        raise KeyError(f"unknown sandbox options: {sorted(pending)}")
    return newline.join(lines)
