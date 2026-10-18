"""Pure helpers for the console WebSocket (no I/O, unit-tested).

The console follows whichever container is producing the server's output: the
one-shot steamcmd install container while it runs (install, update, update on
start), otherwise the long-lived game container. Docker is asked for
timestamped logs, which this module turns back into (timestamp, line) pairs.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.services.docker_orchestrator import ContainerState

# Docker's `logs --timestamps` prefix: RFC 3339 with nanoseconds, then a space.
_TS = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})) ")


def pick_target(
    server: ContainerState, install: ContainerState
) -> tuple[str, ContainerState] | None:
    """Which container's output the console should show right now."""
    if install.exists and install.status == "running":
        return "install", install
    if server.exists:
        return "server", server
    if install.exists:  # finished/failed install not cleaned up yet
        return "install", install
    return None


def ts_to_unix(ts: str | None) -> float | None:
    """RFC 3339 (nanoseconds allowed) -> unix seconds; None if unparseable."""
    if not ts or ts.startswith("0001-"):
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})$", ts)
    if not m:
        return None
    base, frac, tz = m.groups()
    try:
        dt = datetime.fromisoformat(base + ("+00:00" if tz == "Z" else tz))
    except ValueError:
        return None
    return dt.timestamp() + (float(frac) if frac else 0.0)


class LineSplitter:
    """Turns a timestamped Docker log byte stream into complete lines.

    Docker splits container output on newlines and prefixes every line with its
    timestamp. Chunks can end mid-line, so the tail is carried over to the next
    feed() and only complete lines are returned; flush() returns the rest.
    """

    def __init__(self) -> None:
        self._carry = ""
        self.last_ts: str | None = None

    def feed(self, chunk: bytes | str) -> list[tuple[str | None, str]]:
        text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
        text = self._carry + text
        *complete, self._carry = text.split("\n")
        return [self._line(raw) for raw in complete]

    def flush(self) -> list[tuple[str | None, str]]:
        if not self._carry:
            return []
        raw, self._carry = self._carry, ""
        return [self._line(raw)]

    def _line(self, raw: str) -> tuple[str | None, str]:
        m = _TS.match(raw)
        if m:
            self.last_ts = m.group(1)
            raw = raw[m.end():]
        # A TTY ends lines with \r\n; keep any other \r (progress redraws) for the client.
        if raw.endswith("\r"):
            raw = raw[:-1]
        return self.last_ts, raw
