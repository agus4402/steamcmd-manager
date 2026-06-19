"""Registry of available integration providers.

Providers self-register at import time (see ``app/integrations/__init__.py``);
the core looks them up by id. Adding a provider is: implement
``IntegrationProvider`` then ``register_provider(MyProvider())`` — no changes to
the service, router, or models.
"""

from __future__ import annotations

from app.integrations.base import IntegrationProvider

_REGISTRY: dict[str, IntegrationProvider] = {}


def register_provider(provider: IntegrationProvider) -> None:
    _REGISTRY[provider.id] = provider


def get_provider(provider_id: str) -> IntegrationProvider | None:
    return _REGISTRY.get(provider_id)


def list_providers() -> list[IntegrationProvider]:
    return list(_REGISTRY.values())
