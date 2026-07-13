"""Workshop provider framework.

Importing this package registers every available provider. Add new mod sources
(CurseForge, Mod.io, Nexus, ...) here the same way — implement ``WorkshopProvider``
and ``register_provider(...)`` — without touching the service or router.
"""

from app.workshop.registry import register_provider
from app.workshop.steam.provider import SteamWorkshopProvider

register_provider(SteamWorkshopProvider())

# Future providers register the same way, e.g.:
# from app.workshop.curseforge.provider import CurseForgeProvider
# register_provider(CurseForgeProvider())
