"""Project Zomboid: discover the mods inside a downloaded workshop item.

Layout of an item (under the workshop install path):

    <item>/mods/<ModFolder>/mod.info                 Build 41
    <item>/mods/<ModFolder>/<version>/mod.info       Build 42 (42, 42.0, 42.12, …)
    <item>/mods/<ModFolder>/common/mod.info          Build 42 fallback (version
                                                     folders present but empty)
    <item>/mods/<ModFolder>/[<version>/|common/]media/maps/<MapName>/

`mod.info` is `key=value` lines: `id=` (what goes in the server's Mods=),
`name=`, `require=` (comma-separated mod ids, B42 prefixes them with "\\").
Mirrors docker/gameserver/hooks/project_zomboid.sh: on the legacy41 branch the
B41 root mod.info wins; otherwise the newest version folder that has one, then
common/, then the root.
"""

from __future__ import annotations

import re

from app.workshop.inspectors.base import SubmodInfo

LEGACY_B41_BRANCH = "legacy41"
_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")
_MAP_RE = re.compile(r"/media/maps/([^/]+)$", re.IGNORECASE)


def _version_key(name: str) -> tuple[int, ...]:
    return tuple(int(p) for p in name.split("."))


def choose_mod_infos(info_paths: list[str], mods_root: str, branch: str | None) -> dict[str, str]:
    """Pick one mod.info per mod folder. Returns {mod folder path: mod.info path}."""
    candidates: dict[str, dict[str, str]] = {}
    prefix = mods_root.rstrip("/") + "/"
    for path in info_paths:
        if not path.startswith(prefix):
            continue
        parts = path[len(prefix) :].split("/")
        if len(parts) == 2:  # <Mod>/mod.info
            candidates.setdefault(prefix + parts[0], {})["root"] = path
        elif len(parts) == 3 and (parts[1] == "common" or _VERSION_RE.match(parts[1])):
            candidates.setdefault(prefix + parts[0], {})[parts[1]] = path
    chosen: dict[str, str] = {}
    for folder, by_version in candidates.items():
        versions = sorted(
            (v for v in by_version if v not in ("root", "common")), key=_version_key, reverse=True
        )
        if branch == LEGACY_B41_BRANCH and "root" in by_version:
            chosen[folder] = by_version["root"]
        elif versions:
            chosen[folder] = by_version[versions[0]]
        else:
            chosen[folder] = by_version.get("common") or by_version["root"]
    return chosen


def parse_mod_info(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        key = key.strip().lower()
        if sep and key and key not in values:
            values[key] = value.strip()
    return values


def parse_requires(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for part in re.split(r"[,;]", raw):
        mod = part.strip().lstrip("\\").strip()
        if mod and mod not in out:
            out.append(mod)
    return out


def maps_in(folder: str, dir_paths: list[str]) -> list[str]:
    """Map folder names under one mod folder (any version/common), vanilla excluded."""
    found: list[str] = []
    prefix = folder.rstrip("/") + "/"
    for path in sorted(dir_paths):
        if not path.startswith(prefix):
            continue
        m = _MAP_RE.search(path)
        if m and m.group(1) != "Muldraugh, KY" and m.group(1) not in found:
            found.append(m.group(1))
    return found


def build_submods(
    item_root: str,
    info_paths: list[str],
    dir_paths: list[str],
    read_info,
    branch: str | None,
) -> list[SubmodInfo]:
    """Pure assembly from listings; `read_info(path) -> str | None` fetches a mod.info."""
    mods_root = f"{item_root.rstrip('/')}/mods"
    result: list[SubmodInfo] = []
    for folder, info_path in sorted(choose_mod_infos(info_paths, mods_root, branch).items()):
        text = read_info(info_path)
        if text is None:
            continue
        info = parse_mod_info(text)
        mod_id = info.get("id")
        if not mod_id:
            continue
        result.append(
            SubmodInfo(
                mod_id=mod_id,
                name=info.get("name") or None,
                folder=folder[len(item_root.rstrip("/")) + 1 :],
                requires=[r for r in parse_requires(info.get("require")) if r != mod_id],
                maps=maps_in(folder, dir_paths),
            )
        )
    return result
