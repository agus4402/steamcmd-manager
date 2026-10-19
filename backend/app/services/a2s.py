"""Minimal async Steam server query (A2S) client: A2S_INFO and A2S_PLAYER.

Protocol: https://developer.valvesoftware.com/wiki/Server_queries
Handles the challenge handshake and Source-style split responses (without
bzip2 compression, which modern servers don't use for INFO/PLAYER).
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

_SINGLE = b"\xff\xff\xff\xff"
_SPLIT = b"\xfe\xff\xff\xff"

_INFO_REQUEST = b"T" + b"Source Engine Query\x00"
_PLAYER_REQUEST = b"U"
_NO_CHALLENGE = b"\xff\xff\xff\xff"

_CHALLENGE = 0x41  # 'A'
_INFO_RESPONSE = 0x49  # 'I'
_PLAYER_RESPONSE = 0x44  # 'D'

# Each response is one datagram; bound the work a hostile/broken peer can cause.
_MAX_PACKET = 65535
_MAX_SPLIT_PACKETS = 32
_MAX_CHALLENGES = 3


class A2SError(RuntimeError):
    """The server didn't answer, or answered something we can't parse."""


@dataclass(slots=True)
class ServerInfo:
    name: str
    map: str
    folder: str
    game: str
    app_id: int
    players: int
    max_players: int
    bots: int
    server_type: str  # "d" dedicated, "l" listen, "p" SourceTV
    os: str  # "l" linux, "w" windows, "m"/"o" mac
    password: bool
    vac: bool
    version: str
    port: int | None = None
    keywords: str | None = None
    game_id: int | None = None


@dataclass(slots=True)
class Player:
    name: str
    score: int
    duration: float  # seconds connected


@dataclass(slots=True)
class _Reader:
    data: bytes
    pos: int = 0

    def _take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise A2SError("truncated response")
        chunk = self.data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def byte(self) -> int:
        return self._take(1)[0]

    def short(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def long(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def longlong(self) -> int:
        return struct.unpack("<Q", self._take(8))[0]

    def float(self) -> float:
        return struct.unpack("<f", self._take(4))[0]

    def string(self) -> str:
        end = self.data.find(b"\x00", self.pos)
        if end < 0:
            raise A2SError("unterminated string")
        raw = self.data[self.pos : end]
        self.pos = end + 1
        return raw.decode("utf-8", errors="replace")


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        self.queue.put_nowait(data[:_MAX_PACKET])

    def error_received(self, exc: Exception) -> None:
        # ICMP port unreachable etc. — surfaces as a timeout on the reader.
        pass


async def _receive(proto: _Protocol) -> bytes:
    """One logical response (reassembling split packets) without the FFFFFFFF header."""
    first = await proto.queue.get()
    if first.startswith(_SINGLE):
        return first[4:]
    if not first.startswith(_SPLIT):
        raise A2SError("unexpected packet header")

    parts: dict[int, bytes] = {}
    total = None
    packet = first
    while True:
        r = _Reader(packet, 4)
        if r.long() < 0:
            # High bit set => bzip2-compressed payload (Source engine only).
            raise A2SError("compressed split responses are not supported")
        count = r.byte()
        number = r.byte()
        r.short()  # max packet size (Source engine)
        if not 0 < count <= _MAX_SPLIT_PACKETS or number >= count:
            raise A2SError("bad split packet header")
        total = total or count
        parts[number] = packet[r.pos :]
        if len(parts) == total:
            break
        packet = await proto.queue.get()
        if not packet.startswith(_SPLIT):
            raise A2SError("expected a split packet")
    payload = b"".join(parts[i] for i in range(total))
    if not payload.startswith(_SINGLE):
        raise A2SError("bad reassembled payload")
    return payload[4:]


async def _request(
    host: str, port: int, request: bytes, expect: int, timeout: float, *, challenge_suffix: bytes
) -> _Reader:
    """Send `request`, answer challenges, return a reader positioned after the type byte.

    `challenge_suffix` is what to append on the first try (A2S_PLAYER sends
    FFFFFFFF to ask for a challenge; A2S_INFO sends nothing).
    """
    loop = asyncio.get_running_loop()
    transport, proto = await loop.create_datagram_endpoint(_Protocol, remote_addr=(host, port))
    try:
        async with asyncio.timeout(timeout):
            payload = request + challenge_suffix
            for _ in range(_MAX_CHALLENGES + 1):
                transport.sendto(_SINGLE + payload)
                data = await _receive(proto)
                if not data:
                    raise A2SError("empty response")
                if data[0] == _CHALLENGE:
                    if len(data) < 5:
                        raise A2SError("bad challenge")
                    payload = request + data[1:5]
                    continue
                if data[0] != expect:
                    raise A2SError(f"unexpected response type 0x{data[0]:02x}")
                return _Reader(data, 1)
            raise A2SError("too many challenges")
    except TimeoutError as exc:
        raise A2SError("no response (timed out)") from exc
    finally:
        transport.close()


async def info(host: str, port: int, timeout: float = 2.0) -> ServerInfo:
    r = await _request(host, port, _INFO_REQUEST, _INFO_RESPONSE, timeout, challenge_suffix=b"")
    r.byte()  # protocol version
    name, map_, folder, game = r.string(), r.string(), r.string(), r.string()
    app_id = r.short()
    players, max_players, bots = r.byte(), r.byte(), r.byte()
    server_type, os_ = chr(r.byte()), chr(r.byte())
    password, vac = bool(r.byte()), bool(r.byte())
    if app_id == 2400:  # The Ship: mode, witnesses, duration
        r.byte(), r.byte(), r.byte()
    version = r.string()
    out = ServerInfo(
        name=name, map=map_, folder=folder, game=game, app_id=app_id,
        players=players, max_players=max_players, bots=bots,
        server_type=server_type, os=os_, password=password, vac=vac, version=version,
    )
    if r.remaining():
        edf = r.byte()
        if edf & 0x80:
            out.port = r.short()
        if edf & 0x10:
            r.longlong()  # server SteamID
        if edf & 0x40:
            r.short(), r.string()  # SourceTV port + name
        if edf & 0x20:
            out.keywords = r.string()
        if edf & 0x01:
            out.game_id = r.longlong()
    return out


async def players(host: str, port: int, timeout: float = 2.0) -> list[Player]:
    r = await _request(
        host, port, _PLAYER_REQUEST, _PLAYER_RESPONSE, timeout, challenge_suffix=_NO_CHALLENGE
    )
    count = r.byte()
    out: list[Player] = []
    for _ in range(count):
        if not r.remaining():
            break  # some servers advertise more players than they list
        r.byte()  # index (always 0 on most games)
        out.append(Player(name=r.string(), score=r.long(), duration=r.float()))
    return out
