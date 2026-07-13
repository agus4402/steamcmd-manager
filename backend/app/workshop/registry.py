"""Registry of available Workshop providers.

Providers self-register at import time (see ``app/workshop/__init__.py``); the
core looks them up by id. Adding a provider is: implement ``WorkshopProvider``
then ``register_provider(MyProvider())`` — no changes to the service or router.
"""

from __future__ import annotations

from app.workshop.base import WorkshopProvider

DEFAULT_PROVIDER = "steam"

_REGISTRY: dict[str, WorkshopProvider] = {}


def register_provider(provider: WorkshopProvider) -> None:
    _REGISTRY[provider.id] = provider


def get_provider(provider_id: str | None = None) -> WorkshopProvider | None:
    return _REGISTRY.get(provider_id or DEFAULT_PROVIDER)


def list_providers() -> list[WorkshopProvider]:
    return list(_REGISTRY.values())
