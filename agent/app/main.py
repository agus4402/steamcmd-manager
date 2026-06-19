"""Agent API — the only service that talks to Docker.

Security model (Pterodactyl "Wings"-style): this is a tiny, auditable service
reachable only on the internal compose network, authenticated with a shared
token. Its API exposes ONLY high-level, structured operations and validates all
inputs, so a compromised backend cannot coerce it into a host-root escape:
no privileged flag, no arbitrary bind mounts, fixed image, port bindings limited
to the pool, volume names limited to the managed prefix.
"""

from __future__ import annotations

import re
import secrets

from fastapi import Depends, FastAPI, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.responses import StreamingResponse

from app.config import get_settings, verify_secrets
from app.orchestrator import DockerError, orchestrator
from app.schemas import (
    CreateContainerRequest,
    CreateResponse,
    InstallRequest,
    InstallResultResponse,
    LogsResponse,
    StateResponse,
    StdinRequest,
)

settings = get_settings()
verify_secrets(settings)
app = FastAPI(title="SteamCMD Manager Agent", version="0.1.0")

bearer = HTTPBearer(auto_error=True)

SERVER_ID_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")
PORT_BINDING_RE = re.compile(r"^(\d{1,5})/(tcp|udp)$")


async def require_token(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> None:
    if not secrets.compare_digest(creds.credentials, settings.agent_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid agent token")


def valid_server_id(server_id: str = Path(...)) -> str:
    if not SERVER_ID_RE.match(server_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid server id")
    return server_id


def _validate_port_bindings(bindings: dict[str, int]) -> None:
    lo, hi = settings.port_pool_start, settings.port_pool_end
    for key, host_port in bindings.items():
        m = PORT_BINDING_RE.match(key)
        if not m:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"bad port binding '{key}'")
        container_port = int(m.group(1))
        # Both the container port and the host port must stay inside the pool.
        for p in (container_port, host_port):
            if not (lo <= p <= hi):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"port {p} outside pool {lo}-{hi}",
                )


def _validate_volume_name(name: str) -> None:
    if name != settings.steamcmd_cache_volume and not name.startswith("gsdata-"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"refusing volume '{name}'")


def _wrap(exc: DockerError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Everything below requires the agent token.
authed = [Depends(require_token)]


@app.get("/ping", dependencies=authed)
async def ping() -> dict[str, object]:
    version = await run_in_threadpool(orchestrator.ping)
    return {"docker_version": version.get("Version", "?")}


@app.post("/volumes/{name}/ensure", dependencies=authed, status_code=204)
async def ensure_volume(name: str) -> None:
    _validate_volume_name(name)
    await run_in_threadpool(orchestrator.ensure_volume, name)


@app.post("/servers/{server_id}/container", dependencies=authed, response_model=CreateResponse)
async def create_container(
    payload: CreateContainerRequest, server_id: str = Depends(valid_server_id)
) -> CreateResponse:
    _validate_port_bindings(payload.port_bindings)
    try:
        cid = await run_in_threadpool(
            orchestrator.create_server_container, server_id, payload.env, payload.port_bindings
        )
    except DockerError as exc:
        raise _wrap(exc) from exc
    return CreateResponse(container_id=cid)


@app.post("/servers/{server_id}/start", dependencies=authed, status_code=204)
async def start(server_id: str = Depends(valid_server_id)) -> None:
    try:
        await run_in_threadpool(orchestrator.start, server_id)
    except DockerError as exc:
        raise _wrap(exc) from exc


@app.post("/servers/{server_id}/stop", dependencies=authed, status_code=204)
async def stop(server_id: str = Depends(valid_server_id)) -> None:
    await run_in_threadpool(orchestrator.stop, server_id)


@app.post("/servers/{server_id}/restart", dependencies=authed, status_code=204)
async def restart(server_id: str = Depends(valid_server_id)) -> None:
    try:
        await run_in_threadpool(orchestrator.restart, server_id)
    except DockerError as exc:
        raise _wrap(exc) from exc


@app.delete("/servers/{server_id}", dependencies=authed, status_code=204)
async def remove(server_id: str = Depends(valid_server_id), remove_data: bool = True) -> None:
    try:
        await run_in_threadpool(orchestrator.remove, server_id, remove_data)
    except DockerError as exc:
        raise _wrap(exc) from exc


@app.get("/servers/{server_id}/state", dependencies=authed, response_model=StateResponse)
async def state(server_id: str = Depends(valid_server_id)) -> StateResponse:
    st = await run_in_threadpool(orchestrator.state, server_id)
    return StateResponse(exists=st.exists, status=st.status, exit_code=st.exit_code)


@app.get("/servers/{server_id}/logs", dependencies=authed, response_model=LogsResponse)
async def recent_logs(server_id: str = Depends(valid_server_id), tail: int = 200) -> LogsResponse:
    logs = await run_in_threadpool(orchestrator.recent_logs, server_id, tail)
    return LogsResponse(logs=logs)


@app.get("/servers/{server_id}/install/logs", dependencies=authed, response_model=LogsResponse)
async def install_logs(server_id: str = Depends(valid_server_id), tail: int = 50) -> LogsResponse:
    logs = await run_in_threadpool(orchestrator.recent_install_logs, server_id, tail)
    return LogsResponse(logs=logs)


@app.get("/servers/{server_id}/logs/follow", dependencies=authed)
async def follow_logs(server_id: str = Depends(valid_server_id), tail: int = 200) -> StreamingResponse:
    # Blocking docker log iterator -> streamed response (iterated in a threadpool).
    gen = orchestrator.follow_logs(server_id, tail)
    return StreamingResponse(iterate_in_threadpool(gen), media_type="application/octet-stream")


@app.post("/servers/{server_id}/install", dependencies=authed, status_code=202)
async def install(
    payload: InstallRequest, server_id: str = Depends(valid_server_id)
) -> dict[str, str]:
    try:
        await run_in_threadpool(orchestrator.run_install, server_id, payload.env)
    except DockerError as exc:
        raise _wrap(exc) from exc
    return {"status": "started"}


@app.get("/servers/{server_id}/install/wait", dependencies=authed, response_model=InstallResultResponse)
async def install_wait(server_id: str = Depends(valid_server_id)) -> InstallResultResponse:
    code, logs = await run_in_threadpool(orchestrator.wait_install, server_id)
    return InstallResultResponse(code=code, logs=logs)


@app.get("/servers/{server_id}/install/state", dependencies=authed, response_model=StateResponse)
async def install_state(server_id: str = Depends(valid_server_id)) -> StateResponse:
    st = await run_in_threadpool(orchestrator.install_state, server_id)
    return StateResponse(exists=st.exists, status=st.status, exit_code=st.exit_code)


@app.post("/servers/{server_id}/stdin", dependencies=authed, status_code=204)
async def stdin(payload: StdinRequest, server_id: str = Depends(valid_server_id)) -> None:
    try:
        await run_in_threadpool(orchestrator.send_stdin, server_id, payload.data)
    except DockerError as exc:
        raise _wrap(exc) from exc
