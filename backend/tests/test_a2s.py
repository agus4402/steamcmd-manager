"""A2S client against a fake UDP game server on localhost."""

from __future__ import annotations

import asyncio
import struct
from types import SimpleNamespace

import pytest

from app.schemas.template import GameTemplate, QuerySpec
from app.services import a2s
from app.services.query_service import default_gateway, query_port

CHALLENGE = b"\x11\x22\x33\x44"


def _info_payload() -> bytes:
    return (
        b"\xff\xff\xff\xffI"
        + b"\x11"  # protocol
        + b"My Server\x00de_dust2\x00csgo\x00Counter-Strike 2\x00"
        + struct.pack("<H", 730)
        + bytes([3, 16, 1])  # players, max, bots
        + b"dl"  # dedicated, linux
        + bytes([1, 0])  # password, vac
        + b"1.0.0\x00"
        + bytes([0x80 | 0x20])  # EDF: port + keywords
        + struct.pack("<H", 27015)
        + b"tag1,tag2\x00"
    )


def _player_payload() -> bytes:
    out = b"\xff\xff\xff\xffD" + bytes([2])
    for name, score, dur in [("alice", 5, 61.5), ("", 0, 2.0)]:
        out += b"\x00" + name.encode() + b"\x00" + struct.pack("<if", score, dur)
    return out


def _split(payload: bytes, size: int) -> list[bytes]:
    chunks = [payload[i : i + size] for i in range(0, len(payload), size)]
    return [
        b"\xfe\xff\xff\xff" + struct.pack("<iBBH", 7, len(chunks), n, 1248) + c
        for n, c in enumerate(chunks)
    ]


class FakeServer(asyncio.DatagramProtocol):
    """Challenges every request first, like modern Source/Steam servers."""

    def __init__(self, *, split: bool = False) -> None:
        self.split = split

    def connection_made(self, transport) -> None:  # noqa: ANN001
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        assert data[:4] == b"\xff\xff\xff\xff"
        kind, rest = data[4:5], data[5:]
        if not rest.endswith(CHALLENGE):
            self.transport.sendto(b"\xff\xff\xff\xffA" + CHALLENGE, addr)
            return
        payload = _info_payload() if kind == b"T" else _player_payload()
        packets = _split(payload, 16) if self.split else [payload]
        # Out of order on purpose: reassembly must sort by packet number.
        for p in reversed(packets):
            self.transport.sendto(p, addr)


async def _serve(**kw) -> tuple[asyncio.DatagramTransport, int]:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: FakeServer(**kw), local_addr=("127.0.0.1", 0)
    )
    return transport, transport.get_extra_info("sockname")[1]


@pytest.mark.parametrize("split", [False, True])
def test_info_and_players(split: bool) -> None:
    async def run():
        transport, port = await _serve(split=split)
        try:
            return await a2s.info("127.0.0.1", port), await a2s.players("127.0.0.1", port)
        finally:
            transport.close()

    info, players = asyncio.run(run())
    assert info.name == "My Server"
    assert info.map == "de_dust2"
    assert (info.players, info.max_players, info.bots) == (3, 16, 1)
    assert info.password and not info.vac
    assert info.version == "1.0.0"
    assert info.port == 27015 and info.keywords == "tag1,tag2"
    assert [p.name for p in players] == ["alice", ""]
    assert players[0].score == 5 and players[0].duration == pytest.approx(61.5)


def test_timeout_when_nobody_answers() -> None:
    async def run():
        # Bind a socket that never replies.
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
        )
        port = transport.get_extra_info("sockname")[1]
        try:
            await a2s.info("127.0.0.1", port, timeout=0.3)
        finally:
            transport.close()

    with pytest.raises(a2s.A2SError, match="timed out"):
        asyncio.run(run())


def _template(**query) -> dict:
    return {
        "id": "g",
        "name": "G",
        "app_id": 1,
        "startup": "./run",
        "ports": [{"name": "game", "protocol": "udp", "default": 2456, "count": 2}],
        "query": query,
    }


def test_query_spec_validation() -> None:
    assert GameTemplate(**_template(port="game", offset=1)).query.offset == 1
    with pytest.raises(ValueError, match="not a declared port"):
        GameTemplate(**_template(port="nope"))
    with pytest.raises(ValueError, match="outside port"):
        GameTemplate(**_template(port="game", offset=2))


def test_query_port_picks_offset_in_block() -> None:
    ports = [
        SimpleNamespace(name="game", protocol="udp", host_port=27031),
        SimpleNamespace(name="game", protocol="udp", host_port=27030),
        SimpleNamespace(name="rcon", protocol="tcp", host_port=27032),
    ]
    server = SimpleNamespace(ports=ports)
    assert query_port(server, QuerySpec(port="game")) == 27030
    assert query_port(server, QuerySpec(port="game", offset=1)) == 27031
    assert query_port(server, QuerySpec(port="rcon")) is None


def test_default_gateway_from_route_table() -> None:
    table = (
        "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
        "eth1\t0000A8C0\t00000000\t0001\t0\t0\t0\t00F0FFFF\t0\t0\t0\n"
        "eth0\t00000000\t010012AC\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"
    )
    assert default_gateway(table) == "172.18.0.1"
    assert default_gateway(table.splitlines()[0]) is None
