"""WebSocket console: live server output + commands to the server's stdin.

One socket lasts the whole page visit. It follows whichever container produces
the server's output (see ``console_stream.pick_target``) and switches when that
changes — install → game server, recreated or restarted containers — sending
every line once: the client never reconnects to catch up, so nothing replays.

Frames (JSON, server → client):
  {"t": "reset"}                                 first frame: start a fresh buffer
  {"t": "lines", "src", "lines": [[ts, text]]}   output lines (ANSI kept, ts may be null)
  {"t": "source", "src"}                         now following another container
  {"t": "state", "src", "status", "running"}     target container state (input on/off)
  {"t": "ended", "src", "exit_code"}             the followed container stopped
  {"t": "info" | "error", "msg"}                 panel messages
  {"t": "ping"}                                  keepalive
Client → server: {"t": "cmd", "data"} (or a plain text frame) → server stdin.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.models.server import Server
from app.services.auth import decode_token
from app.services.console_stream import LineSplitter, pick_target, ts_to_unix
from app.services.docker_orchestrator import ContainerState, orchestrator

logger = logging.getLogger("steamcmd-manager.console")

router = APIRouter(tags=["console"])

HISTORY_LINES = 1000
POLL_SECS = 2.0
KEEPALIVE_SECS = 30


async def _states(server_id: str) -> tuple[ContainerState, ContainerState]:
    server = await run_in_threadpool(orchestrator.state, server_id)
    install = await run_in_threadpool(orchestrator.install_state, server_id)
    return server, install


@router.websocket("/api/servers/{server_id}/console")
async def console(websocket: WebSocket, server_id: str) -> None:
    # Authenticate from the ?token= query param (WS can't send Authorization).
    token = websocket.query_params.get("token")
    if not token or decode_token(token) is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    async with SessionLocal() as session:
        server = await session.get(Server, server_id)
    if server is None:
        await websocket.send_text(json.dumps({"t": "error", "msg": "server not found"}))
        await websocket.close()
        return

    send_lock = asyncio.Lock()

    async def send(frame: dict) -> None:
        async with send_lock:
            await websocket.send_text(json.dumps(frame))

    await send({"t": "reset"})

    async def stream(src: str, tail: int | str, since: float | None, splitter: LineSplitter) -> None:
        """Forward one container's log stream until it ends (container stopped)."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        stop = threading.Event()

        def pump() -> None:  # blocking iterator -> asyncio queue (runs in a thread)
            try:
                for chunk in orchestrator.follow_logs(
                    server_id, tail, source=src, since=since, timestamps=True
                ):
                    if stop.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as exc:  # noqa: BLE001
                logger.info("console stream for %s ended: %s", server_id, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=pump, daemon=True).start()
        try:
            while (chunk := await queue.get()) is not None:
                lines = splitter.feed(chunk)
                if lines:
                    await send({"t": "lines", "src": src, "lines": lines})
            rest = splitter.flush()
            if rest:
                await send({"t": "lines", "src": src, "lines": rest})
        finally:
            stop.set()

    async def follow() -> None:
        # Instance already streamed: (src, container id, started_at).
        streamed: tuple[str, str | None, str | None] | None = None
        last_state: tuple | None = None
        first = True
        told_empty = False
        agent_down = False
        # One per session: flushed after every stream, keeps the last timestamp
        # to resume a dropped stream without repeating lines.
        splitter = LineSplitter()

        while True:
            try:
                server_st, install_st = await _states(server_id)
            except Exception as exc:  # noqa: BLE001 — agent unreachable: keep the socket, retry
                if not agent_down:
                    agent_down = True
                    await send({"t": "error", "msg": f"cannot reach the agent: {exc}"})
                await asyncio.sleep(POLL_SECS)
                continue
            agent_down = False
            target = pick_target(server_st, install_st)
            if target is None:
                if not told_empty:
                    told_empty = True
                    await send({
                        "t": "info",
                        "msg": "No container yet — output appears here when the server is installed or started.",
                    })
                    await send({"t": "state", "src": None, "status": "absent", "running": False})
                    last_state = None
                await asyncio.sleep(POLL_SECS)
                continue

            told_empty = False
            src, st = target
            running = st.status == "running"
            state_key = (src, st.status)
            if state_key != last_state:
                last_state = state_key
                await send({"t": "state", "src": src, "status": st.status, "running": running})

            key = (src, st.id, st.started_at)
            tail: int | str
            since: float | None = None
            if first:
                # What the user lands on: recent history, even if it already stopped.
                tail = HISTORY_LINES
            elif key == streamed:
                if not running:
                    await asyncio.sleep(POLL_SECS)  # stopped and fully shown: wait for a change
                    continue
                # Same instance still running but our stream dropped: resume after the last line.
                last = ts_to_unix(splitter.last_ts)
                tail, since = "all", (last + 1e-6 if last is not None else None)
            elif not running:
                # A different container that isn't running (e.g. the previous game
                # container while an update replaces it): nothing new to show.
                await asyncio.sleep(POLL_SECS)
                continue
            elif streamed is not None and streamed[:2] == key[:2]:
                # Same container restarted (crash + restart policy): only the new run.
                tail, since = "all", ts_to_unix(st.started_at)
            else:
                tail = "all"  # a new container: all of it, from the first line

            if not first and (streamed is None or streamed[0] != src or streamed[1] != st.id):
                await send({"t": "source", "src": src})
            first = False
            streamed = key

            await stream(src, tail, since, splitter)

            try:
                server_st, install_st = await _states(server_id)
            except Exception:  # noqa: BLE001 — retried by the loop
                continue
            now = install_st if src == "install" else server_st
            if now.exists and now.status != "running" and now.id == st.id:
                await send({"t": "ended", "src": src, "exit_code": now.exit_code})
                last_state = None  # re-announce the state after the stop
            await asyncio.sleep(0.5)

    async def receiver() -> None:
        # Inbound frames are commands for the game server's stdin.
        while True:
            raw = await websocket.receive_text()
            command = raw
            if raw.startswith("{"):
                try:
                    msg = json.loads(raw)
                except ValueError:
                    msg = None
                if isinstance(msg, dict):
                    if msg.get("t") != "cmd":
                        continue
                    command = str(msg.get("data", ""))
            if not command.strip():
                continue
            try:
                await run_in_threadpool(orchestrator.send_stdin, server_id, command)
            except Exception as exc:  # noqa: BLE001
                await send({"t": "error", "msg": f"command failed: {exc}"})

    async def keepalive() -> None:
        """Periodic ping to detect dead TCP connections."""
        while True:
            await asyncio.sleep(KEEPALIVE_SECS)
            await send({"t": "ping"})

    tasks = [asyncio.create_task(c()) for c in (follow, receiver, keepalive)]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.warning("console for %s failed: %r", server_id, exc)
    finally:
        for task in tasks:
            task.cancel()
        logger.info("console closed for %s", server_id)
