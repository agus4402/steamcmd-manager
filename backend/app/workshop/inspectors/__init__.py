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

# name -> (mod info glob, its max depth, map marker glob, its max depth, builder);
# depths are relative to <item>/mods.
INSPECTORS: dict[str, tuple[str, int, str, int, Callable[..., list[SubmodInfo]]]] = {
    # mod.info: <Mod>/[<ver>/]mod.info; map.info: <Mod>/[<ver>/]media/maps/<Map>/map.info
    "project_zomboid": ("mod.info", 3, "map.info", 6, project_zomboid.build_submods),
}


def inspect_item(
    inspector: str, server_id: str, item_root: str, branch: str | None
) -> list[SubmodInfo]:
    """Blocking (agent calls): list the item's files and build its sub-mods."""
    info_name, info_depth, map_name, map_depth, build = INSPECTORS[inspector]
    mods_root = f"{item_root}/mods"
    infos = [
        e.path
        for e in orchestrator.list_files(
            server_id, mods_root, info_depth, kind="file", name=info_name
        )
    ]
    maps = [
        e.path
        for e in orchestrator.list_files(server_id, mods_root, map_depth, kind="file", name=map_name)
    ]

    def read(path: str) -> str | None:
        result = orchestrator.read_file(server_id, path)
        return result[0].decode("utf-8", "replace") if result else None

    return build(item_root, infos, maps, read, branch)
