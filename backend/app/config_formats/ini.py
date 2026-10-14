"""Line-preserving parser/editor for `Key=value` files with `# description` comments
(e.g. Project Zomboid's server .ini).

Parsing turns the file into form fields; applying changes rewrites only the value
part of the affected lines, so comments, ordering, unknown keys and the file's
line endings survive untouched.
"""

from __future__ import annotations

import re

from app.config_formats.base import ConfigField, infer_type

_KEY_RE = re.compile(r"^([A-Za-z0-9_.]+)=(.*)$")


def _split_lines(text: str) -> tuple[list[str], str]:
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.split(newline), newline


def parse(text: str, managed: set[str] | frozenset[str] = frozenset()) -> list[ConfigField]:
    lines, _ = _split_lines(text)
    fields: list[ConfigField] = []
    comments: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            comments.append(stripped.lstrip("#").strip())
            continue
        m = _KEY_RE.match(stripped)
        if m:
            key, value = m.group(1), m.group(2)
            fields.append(
                ConfigField(
                    path=key,
                    section="Server",
                    value=value,
                    type=infer_type(value),
                    description=" ".join(c for c in comments if c) or None,
                    managed=key in managed,
                )
            )
        comments = []
    return fields


def apply(text: str, changes: dict[str, str]) -> str:
    """Return `text` with each `key` set to `value`; missing keys are appended."""
    lines, newline = _split_lines(text)
    pending = dict(changes)
    for i, line in enumerate(lines):
        m = _KEY_RE.match(line.strip())
        if m and m.group(1) in pending:
            lines[i] = f"{m.group(1)}={_clean(pending.pop(m.group(1)))}"
    if pending:
        if lines and lines[-1] == "":
            lines.pop()
        lines.extend(f"{k}={_clean(v)}" for k, v in pending.items())
        lines.append("")
    return newline.join(lines)


def _clean(value: str) -> str:
    # A value can never span lines (it would inject extra keys).
    return value.replace("\r", "").replace("\n", "")
