"""Encrypted credential storage helpers shared by all providers.

Wraps the existing Fernet helpers in ``app.services.crypto`` so a provider only
deals with plain dicts; the ciphertext lives in the 1:1 ``integration_credentials``
row and is never logged or returned to the frontend.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import Integration, IntegrationCredential
from app.services.crypto import decrypt_credentials, encrypt_credentials


async def store_credentials(
    session: AsyncSession, integration: Integration, data: dict[str, str]
) -> None:
    token = encrypt_credentials(data)
    if integration.credentials is None:
        integration.credentials = IntegrationCredential(
            integration_id=integration.id, encrypted_credentials=token
        )
        session.add(integration.credentials)
    else:
        integration.credentials.encrypted_credentials = token


def read_credentials(integration: Integration) -> dict[str, str] | None:
    if integration.credentials is None:
        return None
    return decrypt_credentials(integration.credentials.encrypted_credentials)
