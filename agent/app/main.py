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
from app.playit import playit
from app.schemas import (
    CreateContainerRequest,
    CreateResponse,
    InstallRequest,
    InstallResultResponse,
    LogsResponse,
    PlayitSecretRequest,
    PlayitStateResponse,
    SnapshotListResponse,
    SnapshotResponse,
    StateResponse,
    StatsResponse,
    StdinRequest,
    StopRequest,
    WorkshopDownloadRequest,
)

settings = get_settings()
verify_secrets(settings)
app = FastAPI(title="SteamCMD Manager Agent", version="0.1.0")

bearer = HTTPBearer(auto_error=True)

SERVER_ID_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")
PORT_BINDING_RE = re.compile(r"^(\d{1,5})/(tcp|udp)$")
WORKSHOP_ITEM_RE = re.compile(r"^\d{1,20}$")
WORKSHOP_PATH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
# One printable console line (no newlines/control chars), e.g. "quit".
STOP_COMMAND_RE = re.compile(r"^[ -~]{1,128}$")


def _validate_workshop(item_id: str, install_path: str) -> None:
    if not WORKSHOP_ITEM_RE.match(item_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid workshop item id")
    if ".." in install_path or install_path.startswith("/") or not WORKSHOP_PATH_RE.match(install_path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid install path")


async def require_token(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> None:
    if not secrets.compare_digest(creds.credentials, settings.agent_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid agent token")


def valid_server_id(server_id: str = Path(...)) -> str:
    if not SERVER_ID_RE.match(server_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid server id")
    return server_id


def valid_dst_id(dst_id: str = Path(...)) -> str:
    if not SERVER_ID_RE.match(dst_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid destination id")
    return dst_id


def valid_integration_id(integration_id: str = Path(...)) -> str:
    if not SERVER_ID_RE.match(integration_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid integration id")
    return integration_id


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
async def stop(
    payload: StopRequest | None = None, server_id: str = Depends(valid_server_id)
) -> None:
    req = payload or StopRequest()
    if req.command is not None and not STOP_COMMAND_RE.match(req.command):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid stop command")
    await run_in_threadpool(orchestrator.stop, server_id, req.timeout, req.command)


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


@app.get("/servers/{server_id}/stats", dependencies=authed, response_model=StatsResponse)
async def stats(server_id: str = Depends(valid_server_id)) -> StatsResponse:
    try:
        s = await run_in_threadpool(orchestrator.stats, server_id)
    except DockerError as exc:
        raise _wrap(exc) from exc
    return StatsResponse(
        running=s.running,
        cpu_pct=s.cpu_pct,
        mem_used=s.mem_used,
        mem_limit=s.mem_limit,
        mem_pct=s.mem_pct,
        net_rx=s.net_rx,
        net_tx=s.net_tx,
        blk_read=s.blk_read,
        blk_write=s.blk_write,
        pids=s.pids,
        online_cpus=s.online_cpus,
    )


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


# -- backups / clone ----------------------------------------------------------


@app.post("/servers/{server_id}/backups", dependencies=authed, response_model=SnapshotResponse)
async def create_backup(server_id: str = Depends(valid_server_id)) -> SnapshotResponse:
    try:
        snap = await run_in_threadpool(orchestrator.create_snapshot, server_id)
    except DockerError as exc:
        raise _wrap(exc) from exc
    return SnapshotResponse(id=snap.id, created_at=snap.created_at, size=snap.size)


@app.get("/servers/{server_id}/backups", dependencies=authed, response_model=SnapshotListResponse)
async def list_backups(server_id: str = Depends(valid_server_id)) -> SnapshotListResponse:
    try:
        snaps = await run_in_threadpool(orchestrator.list_snapshots, server_id)
    except DockerError as exc:
        raise _wrap(exc) from exc
    return SnapshotListResponse(
        snapshots=[SnapshotResponse(id=s.id, created_at=s.created_at, size=s.size) for s in snaps]
    )


@app.post("/servers/{server_id}/backups/{snapshot_id}/restore", dependencies=authed, status_code=204)
async def restore_backup(snapshot_id: str, server_id: str = Depends(valid_server_id)) -> None:
    try:
        await run_in_threadpool(orchestrator.restore_snapshot, server_id, snapshot_id)
    except DockerError as exc:
        raise _wrap(exc) from exc


@app.delete("/servers/{server_id}/backups/{snapshot_id}", dependencies=authed, status_code=204)
async def delete_backup(snapshot_id: str, server_id: str = Depends(valid_server_id)) -> None:
    try:
        await run_in_threadpool(orchestrator.delete_snapshot, server_id, snapshot_id)
    except DockerError as exc:
        raise _wrap(exc) from exc


@app.post("/servers/{server_id}/copy/{dst_id}", dependencies=authed, status_code=204)
async def copy_data(
    server_id: str = Depends(valid_server_id), dst_id: str = Depends(valid_dst_id)
) -> None:
    try:
        await run_in_threadpool(orchestrator.copy_data, server_id, dst_id)
    except DockerError as exc:
        raise _wrap(exc) from exc


# -- workshop -----------------------------------------------------------------


@app.post(
    "/servers/{server_id}/workshop/download",
    dependencies=authed,
    response_model=InstallResultResponse,
)
async def workshop_download(
    payload: WorkshopDownloadRequest, server_id: str = Depends(valid_server_id)
) -> InstallResultResponse:
    _validate_workshop(payload.item_id, payload.install_path)
    try:
        code, logs = await run_in_threadpool(
            orchestrator.download_workshop_item,
            server_id,
            payload.app_id,
            payload.item_id,
            payload.install_path,
        )
    except DockerError as exc:
        raise _wrap(exc) from exc
    return InstallResultResponse(code=code, logs=logs)


@app.get("/servers/{server_id}/workshop/installed", dependencies=authed, response_model=list[str])
async def workshop_installed(
    install_path: str = "steamapps/workshop", server_id: str = Depends(valid_server_id)
) -> list[str]:
    if ".." in install_path or install_path.startswith("/") or not WORKSHOP_PATH_RE.match(install_path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid install path")
    try:
        return await run_in_threadpool(orchestrator.list_workshop_items, server_id, install_path)
    except DockerError as exc:
        raise _wrap(exc) from exc


@app.delete("/servers/{server_id}/workshop/{item_id}", dependencies=authed, status_code=204)
async def workshop_remove(
    item_id: str, install_path: str = "steamapps/workshop", server_id: str = Depends(valid_server_id)
) -> None:
    _validate_workshop(item_id, install_path)
    try:
        await run_in_threadpool(orchestrator.remove_workshop_item, server_id, install_path, item_id)
    except DockerError as exc:
        raise _wrap(exc) from exc


# -- integrations: playit (data-plane only; control-plane lives in backend) ---


@app.post("/integrations/playit/{integration_id}/run", dependencies=authed, status_code=204)
async def playit_run(
    payload: PlayitSecretRequest, integration_id: str = Depends(valid_integration_id)
) -> None:
    try:
        await run_in_threadpool(playit.ensure_running, integration_id, payload.secret)
    except DockerError as exc:
        raise _wrap(exc) from exc


@app.get(
    "/integrations/playit/{integration_id}/state",
    dependencies=authed,
    response_model=PlayitStateResponse,
)
async def playit_state(
    integration_id: str = Depends(valid_integration_id),
) -> PlayitStateResponse:
    data = await run_in_threadpool(playit.state, integration_id)
    return PlayitStateResponse(**data)


@app.delete("/integrations/playit/{integration_id}", dependencies=authed, status_code=204)
async def playit_remove(
    integration_id: str = Depends(valid_integration_id),
) -> None:
    try:
        await run_in_threadpool(playit.remove, integration_id)
    except DockerError as exc:
        raise _wrap(exc) from exc
