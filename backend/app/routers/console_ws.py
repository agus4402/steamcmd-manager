"""WebSocket console: live log streaming + command-to-stdin."""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.models.server import Server
from app.services.auth import decode_token
from app.services.docker_orchestrator import orchestrator

logger = logging.getLogger("steamcmd-manager.console")

router = APIRouter(tags=["console"])


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
        await websocket.send_text("[error] server not found")
        await websocket.close()
        return

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    stop = threading.Event()

    def pump_logs() -> None:
        """Blocking docker log iterator -> asyncio queue (runs in a thread).

        Polls for the container to appear if it doesn't exist yet (race between
        the Install button being clicked and the WS connection that was already
        open from page load).
        """
        MAX_WAIT_SECS = 120
        POLL_SECS = 2.0
        waited = 0.0

        while not stop.is_set():
            streamed = False
            try:
                for chunk in orchestrator.follow_logs(server_id, tail=200):
                    streamed = True
                    if stop.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, f"[stream ended] {exc}".encode())
                break

            if not streamed:
                # No container yet — wait and try again.
                if waited >= MAX_WAIT_SECS:
                    break
                time.sleep(POLL_SECS)
                waited += POLL_SECS
                continue

            break  # stream finished normally (container exited)

        loop.call_soon_threadsafe(queue.put_nowait, None)

    thread = threading.Thread(target=pump_logs, daemon=True)
    thread.start()

    async def sender() -> None:
        while True:
            chunk = await queue.get()
            if chunk is None:
                await websocket.send_text("[log stream closed]")
                await websocket.close()
                return
            await websocket.send_text(chunk.decode("utf-8", errors="replace"))

    async def receiver() -> None:
        # Inbound text frames are commands to forward to the server's stdin.
        while True:
            command = await websocket.receive_text()
            if not command.strip():
                continue
            try:
                await run_in_threadpool(orchestrator.send_stdin, server_id, command)
            except Exception as exc:  # noqa: BLE001
                await websocket.send_text(f"[command failed] {exc}")

    async def keepalive() -> None:
        """Periodic empty-frame ping to detect dead TCP connections."""
        while True:
            await asyncio.sleep(30)
            try:
                await websocket.send_text("")
            except Exception:  # noqa: BLE001
                return

    try:
        await asyncio.gather(sender(), receiver(), keepalive())
    except WebSocketDisconnect:
        logger.info("console disconnected for %s", server_id)
    finally:
        stop.set()
