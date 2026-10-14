"""Workshop item inspectors: discover the game-level mods inside a downloaded item.

Selected per template via `workshop.inspector`. Each inspector turns directory
listings + mod metadata files into SubmodInfo rows (see workshop_service).
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.docker_orchestrator import orchestrator
from app.workshop.inspectors import project_zomboid
from app.workshop.inspectors.base import SubmodInfo

__all__ = ["INSPECTORS", "SubmodInfo", "inspect_item"]

# name -> (info file glob, max depth for info files, max depth for dirs, builder)
INSPECTORS: dict[str, tuple[str, int, int, Callable[..., list[SubmodInfo]]]] = {
    "project_zomboid": ("mod.info", 3, 5, project_zomboid.build_submods),
}


def inspect_item(
    inspector: str, server_id: str, item_root: str, branch: str | None
) -> list[SubmodInfo]:
    """Blocking (agent calls): list the item's files and build its sub-mods."""
    info_name, info_depth, dir_depth, build = INSPECTORS[inspector]
    mods_root = f"{item_root}/mods"
    infos = [
        e.path
        for e in orchestrator.list_files(
            server_id, mods_root, info_depth, kind="file", name=info_name
        )
    ]
    dirs = [e.path for e in orchestrator.list_files(server_id, mods_root, dir_depth, kind="dir")]

    def read(path: str) -> str | None:
        result = orchestrator.read_file(server_id, path)
        return result[0].decode("utf-8", "replace") if result else None

    return build(item_root, infos, dirs, read, branch)
