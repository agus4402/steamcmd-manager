"""HTTP client to the privileged agent — the backend never touches Docker.

This module keeps the exact same public interface the rest of the backend used
when it talked to docker-py directly (`DockerOrchestrator`, `orchestrator`,
`ContainerState`, `DockerError`, and the same method names/signatures), so
`server_service.py` and `console_ws.py` are unchanged. The actual Docker work
now happens in the agent, reachable only on the internal network with a token.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger("steamcmd-manager.agent-client")
settings = get_settings()

CONTAINER_PREFIX = "gs-"
INSTALL_PREFIX = "gs-install-"
DEFAULT_STOP_TIMEOUT = 30

# wait_install can block for a long time (big steamcmd downloads).
_DEFAULT_TIMEOUT = httpx.Timeout(30.0, read=30.0)
_INSTALL_WAIT_TIMEOUT = httpx.Timeout(30.0, read=None)
# Volume tar/copy over a large data dir can take minutes — don't cap the read.
_BACKUP_TIMEOUT = httpx.Timeout(30.0, read=None)


@dataclass(slots=True)
class ContainerState:
    exists: bool
    status: str
    exit_code: int | None = None


@dataclass(slots=True)
class FileEntry:
    path: str  # relative to the server's data dir
    type: str  # "file" | "dir"
    size: int
    mtime: int


@dataclass(slots=True)
class SnapshotInfo:
    id: str
    created_at: str
    size: int


@dataclass(slots=True)
class ContainerStats:
    running: bool
    cpu_pct: float = 0.0
    mem_used: int = 0
    mem_limit: int = 0
    mem_pct: float = 0.0
    net_rx: int = 0
    net_tx: int = 0
    blk_read: int = 0
    blk_write: int = 0
    pids: int = 0
    online_cpus: int = 0


class DockerError(RuntimeError):
    """Raised for orchestration failures the API layer can surface cleanly."""


class DockerOrchestrator:
    """Thin HTTP client to the agent, preserving the old orchestrator API."""

    def __init__(self) -> None:
        self._base = settings.agent_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {settings.agent_token}"}

    # -- request helpers ------------------------------------------------------

    def _request(self, method: str, path: str, *, timeout=_DEFAULT_TIMEOUT, **kwargs) -> httpx.Response:
        try:
            resp = httpx.request(
                method, f"{self._base}{path}", headers=self._headers, timeout=timeout, **kwargs
            )
        except httpx.HTTPError as exc:
            raise DockerError(f"agent unreachable: {exc}") from exc
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except Exception:  # noqa: BLE001
                pass
            raise DockerError(f"agent error {resp.status_code}: {detail}")
        return resp

    # -- naming (pure, no network) -------------------------------------------

    @staticmethod
    def container_name(server_id: str) -> str:
        return f"{CONTAINER_PREFIX}{server_id}"

    @staticmethod
    def install_name(server_id: str) -> str:
        return f"{INSTALL_PREFIX}{server_id}"

    @staticmethod
    def data_volume(server_id: str) -> str:
        return f"gsdata-{server_id}"

    # -- daemon ---------------------------------------------------------------

    def ping(self) -> dict[str, object]:
        return self._request("GET", "/ping").json()

    # -- volumes --------------------------------------------------------------

    def ensure_volume(self, name: str) -> None:
        self._request("POST", f"/volumes/{name}/ensure")

    # -- container lifecycle --------------------------------------------------

    def create_server_container(
        self, server_id: str, env: dict[str, str], port_bindings: dict[str, int]
    ) -> str:
        resp = self._request(
            "POST",
            f"/servers/{server_id}/container",
            json={"env": env, "port_bindings": port_bindings},
        )
        return resp.json()["container_id"]

    def start(self, server_id: str) -> None:
        self._request("POST", f"/servers/{server_id}/start")

    def stop(
        self, server_id: str, timeout: int = DEFAULT_STOP_TIMEOUT, command: str | None = None
    ) -> None:
        # The agent may wait `timeout` for a graceful exit, then up to ~10s more
        # for docker stop; keep the HTTP read open past that.
        self._request(
            "POST",
            f"/servers/{server_id}/stop",
            json={"command": command, "timeout": timeout},
            timeout=httpx.Timeout(30.0, read=timeout + 30),
        )

    def restart(self, server_id: str, timeout: int = DEFAULT_STOP_TIMEOUT) -> None:
        self._request("POST", f"/servers/{server_id}/restart")

    def remove(self, server_id: str, remove_data: bool = True) -> None:
        self._request("DELETE", f"/servers/{server_id}", params={"remove_data": remove_data})

    def state(self, server_id: str) -> ContainerState:
        return self._state("GET", f"/servers/{server_id}/state")

    def install_state(self, server_id: str) -> ContainerState:
        return self._state("GET", f"/servers/{server_id}/install/state")

    def _state(self, method: str, path: str) -> ContainerState:
        data = self._request(method, path).json()
        return ContainerState(
            exists=data["exists"], status=data["status"], exit_code=data.get("exit_code")
        )

    # -- stats ----------------------------------------------------------------

    def stats(self, server_id: str) -> ContainerStats:
        data = self._request("GET", f"/servers/{server_id}/stats").json()
        return ContainerStats(
            running=data["running"],
            cpu_pct=data.get("cpu_pct", 0.0),
            mem_used=data.get("mem_used", 0),
            mem_limit=data.get("mem_limit", 0),
            mem_pct=data.get("mem_pct", 0.0),
            net_rx=data.get("net_rx", 0),
            net_tx=data.get("net_tx", 0),
            blk_read=data.get("blk_read", 0),
            blk_write=data.get("blk_write", 0),
            pids=data.get("pids", 0),
            online_cpus=data.get("online_cpus", 0),
        )

    # -- backups / clone ------------------------------------------------------

    def create_snapshot(self, server_id: str) -> SnapshotInfo:
        data = self._request("POST", f"/servers/{server_id}/backups", timeout=_BACKUP_TIMEOUT).json()
        return SnapshotInfo(id=data["id"], created_at=data["created_at"], size=data["size"])

    def list_snapshots(self, server_id: str) -> list[SnapshotInfo]:
        data = self._request("GET", f"/servers/{server_id}/backups").json()
        return [
            SnapshotInfo(id=s["id"], created_at=s["created_at"], size=s["size"])
            for s in data.get("snapshots", [])
        ]

    def restore_snapshot(self, server_id: str, snapshot_id: str) -> None:
        self._request(
            "POST", f"/servers/{server_id}/backups/{snapshot_id}/restore", timeout=_BACKUP_TIMEOUT
        )

    def delete_snapshot(self, server_id: str, snapshot_id: str) -> None:
        self._request("DELETE", f"/servers/{server_id}/backups/{snapshot_id}")

    def copy_data(self, src_server_id: str, dst_server_id: str) -> None:
        self._request(
            "POST", f"/servers/{src_server_id}/copy/{dst_server_id}", timeout=_BACKUP_TIMEOUT
        )

    # -- workshop -------------------------------------------------------------

    def download_workshop_item(
        self, server_id: str, app_id: int, item_id: str, install_path: str
    ) -> tuple[int, str]:
        data = self._request(
            "POST",
            f"/servers/{server_id}/workshop/download",
            json={"app_id": app_id, "item_id": item_id, "install_path": install_path},
            timeout=_INSTALL_WAIT_TIMEOUT,
        ).json()
        return data["code"], data["logs"]

    def remove_workshop_item(self, server_id: str, install_path: str, item_id: str) -> None:
        self._request(
            "DELETE",
            f"/servers/{server_id}/workshop/{item_id}",
            params={"install_path": install_path},
        )

    def list_workshop_items(self, server_id: str, install_path: str) -> list[str]:
        """Item-id directories present on disk under the install path."""
        return self._request(
            "GET",
            f"/servers/{server_id}/workshop/installed",
            params={"install_path": install_path},
        ).json()

    # -- install / update -----------------------------------------------------

    def run_install(self, server_id: str, env: dict[str, str]) -> None:
        self._request("POST", f"/servers/{server_id}/install", json={"env": env})

    def wait_install(self, server_id: str) -> tuple[int, str]:
        data = self._request(
            "GET", f"/servers/{server_id}/install/wait", timeout=_INSTALL_WAIT_TIMEOUT
        ).json()
        return data["code"], data["logs"]

    # -- logs / stdin ---------------------------------------------------------

    def recent_logs(self, server_id: str, tail: int = 200) -> str:
        return self._request("GET", f"/servers/{server_id}/logs", params={"tail": tail}).json()[
            "logs"
        ]

    def recent_install_logs(self, server_id: str, tail: int = 50) -> str:
        return self._request(
            "GET", f"/servers/{server_id}/install/logs", params={"tail": tail}
        ).json()["logs"]

    def follow_logs(self, server_id: str, tail: int = 200) -> Iterator[bytes]:
        """Stream the agent's follow-logs endpoint as a byte iterator.

        Opens an httpx stream and yields chunks; the stream is closed when the
        consumer (console_ws pump thread) stops iterating.
        """
        url = f"{self._base}/servers/{server_id}/logs/follow"
        params = {"tail": tail}
        try:
            with httpx.stream(
                "GET",
                url,
                headers=self._headers,
                params=params,
                timeout=httpx.Timeout(30.0, read=None),
            ) as resp:
                if resp.status_code >= 400:
                    return
                yield from resp.iter_bytes()
        except httpx.HTTPError as exc:
            logger.info("follow_logs stream ended for %s: %s", server_id, exc)
            return

    # -- data-volume files (config editor) -------------------------------------

    def list_files(
        self,
        server_id: str,
        path: str,
        depth: int = 1,
        kind: str | None = None,
        name: str | None = None,
    ) -> list[FileEntry]:
        params: dict[str, str | int] = {"path": path, "depth": depth}
        if kind:
            params["kind"] = kind
        if name:
            params["name"] = name
        resp = self._request("GET", f"/servers/{server_id}/files", params=params)
        return [FileEntry(**e) for e in resp.json()]

    def read_file(self, server_id: str, path: str) -> tuple[bytes, int] | None:
        """(content, mtime), or None when the file doesn't exist."""
        try:
            resp = self._request(
                "GET", f"/servers/{server_id}/files/content", params={"path": path}
            )
        except DockerError as exc:
            if "agent error 404" in str(exc):
                return None
            raise
        return resp.content, int(resp.headers.get("X-Mtime", "0"))

    def write_file(self, server_id: str, path: str, content: bytes) -> int:
        resp = self._request(
            "PUT",
            f"/servers/{server_id}/files/content",
            params={"path": path},
            content=content,
            timeout=_BACKUP_TIMEOUT,
        )
        return int(resp.json()["mtime"])

    def send_stdin(self, server_id: str, data: str) -> None:
        self._request("POST", f"/servers/{server_id}/stdin", json={"data": data})

    # -- integrations: playit -------------------------------------------------
    #
    # The agent only runs the egress-less side: the playitd forwarder container.
    # All api.playit.gg calls (claim, tunnels) happen in the backend (see
    # app/integrations/playit/api.py). The backend passes the secret here so the
    # agent can (re)start the container from the backend's encrypted copy.

    def playit_run(self, integration_id: str, secret: str) -> None:
        self._request(
            "POST",
            f"/integrations/playit/{integration_id}/run",
            json={"secret": secret},
        )

    def playit_state(self, integration_id: str) -> dict:
        return self._request(
            "GET", f"/integrations/playit/{integration_id}/state"
        ).json()

    def playit_remove(self, integration_id: str) -> None:
        self._request("DELETE", f"/integrations/playit/{integration_id}")


orchestrator = DockerOrchestrator()
