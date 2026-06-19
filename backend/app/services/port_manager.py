"""Host port pool allocation with concurrency safety."""

from __future__ import annotations

import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.port_allocation import PortAllocation
from app.schemas.template import PortSpec

logger = logging.getLogger("steamcmd-manager.ports")
settings = get_settings()

# Arbitrary constant used as the Postgres advisory-lock key so that concurrent
# allocations are serialized within their transactions (no two creates can grab
# the same port). Released automatically at transaction end.
PORT_LOCK_KEY = 0x57434D44  # "WCMD"


class PortPoolExhausted(RuntimeError):
    pass


async def _lock(session: AsyncSession) -> None:
    if session.bind and session.bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": PORT_LOCK_KEY})


async def _used_host_ports(session: AsyncSession) -> set[int]:
    result = await session.execute(select(PortAllocation.host_port))
    return set(result.scalars().all())


async def allocate_ports(
    session: AsyncSession, server_id: str, ports: list[PortSpec]
) -> list[PortAllocation]:
    """Reserve a free host port for each template port within the active txn.

    Must be called inside the same transaction that persists the server, so the
    advisory lock and the inserted rows commit atomically.
    """
    await _lock(session)
    used = await _used_host_ports(session)

    allocations: list[PortAllocation] = []
    cursor = settings.port_pool_start
    for spec in ports:
        # Find a base where the whole consecutive block [base, base+count) is free
        # (Valheim needs port and port+1 for the UDP query port).
        base = _find_free_block(used, cursor, spec.count)
        for offset in range(spec.count):
            host_port = base + offset
            used.add(host_port)
            for proto in spec.protocols():
                allocations.append(
                    PortAllocation(
                        server_id=server_id,
                        name=spec.name,
                        protocol=proto,
                        host_port=host_port,
                        is_primary=(offset == 0),
                    )
                )
        # Next spec starts searching past this block.
        cursor = base + spec.count

    session.add_all(allocations)
    logger.info("allocated %d port rows for server %s", len(allocations), server_id)
    return allocations


def _find_free_block(used: set[int], start: int, count: int) -> int:
    """Return the lowest base >= start where base..base+count-1 are all free."""
    base = start
    while True:
        if base + count - 1 > settings.port_pool_end:
            raise PortPoolExhausted(
                f"no free block of {count} consecutive host ports in pool "
                f"{settings.port_pool_start}-{settings.port_pool_end}"
            )
        if all((base + offset) not in used for offset in range(count)):
            return base
        base += 1
