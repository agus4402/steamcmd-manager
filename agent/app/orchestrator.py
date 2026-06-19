"""All Docker interaction lives here (inside the privileged agent).

Every game server is a dedicated sibling container created against the host
Docker daemon (the agent mounts /var/run/docker.sock). This module is the ONLY
place in the whole system that talks to docker-py — and it lives in the small,
auditable agent, never in the internet-facing backend.

Game-server containers are hardened: all capabilities dropped, no-new-privileges,
and resource limits — so a compromised game server cannot escalate.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import docker
from docker.errors import APIError, NotFound
from docker.models.containers import Container
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout

from app.config import get_settings

logger = logging.getLogger("steamcmd-agent.docker")
settings = get_settings()

LABEL_MANAGED = "steamcmd-manager.managed"
LABEL_SERVER_ID = "steamcmd-manager.server-id"

CONTAINER_PREFIX = "gs-"
INSTALL_PREFIX = "gs-install-"

DEFAULT_STOP_TIMEOUT = 30


@dataclass(slots=True)
class ContainerState:
    exists: bool
    status: str
    exit_code: int | None = None


@dataclass(slots=True)
class ContainerStats:
    """Point-in-time resource usage snapshot for a server container."""

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
    pass


class DockerOrchestrator:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or settings.docker_host
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self._base_url)
        return self._client

    def ping(self) -> dict[str, object]:
        return self.client.version()

    # -- naming ---------------------------------------------------------------

    @staticmethod
    def container_name(server_id: str) -> str:
        return f"{CONTAINER_PREFIX}{server_id}"

    @staticmethod
    def install_name(server_id: str) -> str:
        return f"{INSTALL_PREFIX}{server_id}"

    @staticmethod
    def data_volume(server_id: str) -> str:
        return f"gsdata-{server_id}"

    # -- volumes --------------------------------------------------------------

    def ensure_volume(self, name: str) -> None:
        try:
            self.client.volumes.get(name)
        except NotFound:
            self.client.volumes.create(name=name)
            logger.info("created volume %s", name)

    def remove_volume(self, name: str) -> None:
        try:
            self.client.volumes.get(name).remove(force=True)
            logger.info("removed volume %s", name)
        except NotFound:
            pass
        except APIError as exc:  # noqa: BLE001
            raise DockerError(f"failed to remove volume {name}: {exc}") from exc

    # -- container lookup -----------------------------------------------------

    def _get(self, name: str) -> Container | None:
        try:
            return self.client.containers.get(name)
        except NotFound:
            return None

    def state(self, server_id: str) -> ContainerState:
        return self._state_of(self._get(self.container_name(server_id)))

    def install_state(self, server_id: str) -> ContainerState:
        return self._state_of(self._get(self.install_name(server_id)))

    @staticmethod
    def _state_of(c: Container | None) -> ContainerState:
        if c is None:
            return ContainerState(exists=False, status="absent")
        c.reload()
        exit_code = c.attrs.get("State", {}).get("ExitCode")
        return ContainerState(exists=True, status=c.status, exit_code=exit_code)

    # -- stats ----------------------------------------------------------------

    def stats(self, server_id: str) -> ContainerStats:
        """One-shot resource snapshot (CPU/mem/net/block) for the server container.

        Returns running=False (with zeros) when the container is absent or not
        running, so the caller can render an empty state instead of an error.
        """
        c = self._get(self.container_name(server_id))
        if c is None:
            return ContainerStats(running=False)
        c.reload()
        if c.status != "running":
            return ContainerStats(running=False)
        try:
            # stream=False does a single read; Docker populates precpu_stats from
            # an internal prior sample so CPU% can be computed from one call.
            raw = c.stats(stream=False)
        except APIError as exc:  # noqa: BLE001
            raise DockerError(f"failed to read stats for {server_id}: {exc}") from exc
        return _parse_stats(raw)

    # -- mounts / hardening helpers -------------------------------------------

    def _volumes_for(self, server_id: str) -> dict[str, dict[str, str]]:
        """Fixed mount set: shared steamcmd cache + per-server data volume.

        No arbitrary host paths are ever mounted — this is hardcoded, not caller-
        supplied, so the agent's API cannot be coerced into mounting `/`.
        """
        return {
            settings.steamcmd_cache_volume: {"bind": "/home/steam/Steam", "mode": "rw"},
            self.data_volume(server_id): {"bind": "/data", "mode": "rw"},
        }

    def _labels_for(self, server_id: str) -> dict[str, str]:
        return {LABEL_MANAGED: "true", LABEL_SERVER_ID: server_id}

    def _hardening(self) -> dict[str, object]:
        """Least-privilege options applied to every game-server container."""
        return {
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "mem_limit": settings.worker_mem_limit,
            "pids_limit": settings.worker_pids_limit,
            "nano_cpus": int(settings.worker_cpus * 1_000_000_000),
        }

    # -- server container lifecycle ------------------------------------------

    def create_server_container(
        self, server_id: str, env: dict[str, str], port_bindings: dict[str, int]
    ) -> str:
        """Create (but do not start) the long-lived server container.

        Image and mounts are fixed by the agent; only env + port bindings come
        from the caller. Capabilities are dropped and resources are bounded.
        """
        name = self.container_name(server_id)
        existing = self._get(name)
        if existing is not None:
            existing.remove(force=True)

        self.ensure_volume(settings.steamcmd_cache_volume)
        self.ensure_volume(self.data_volume(server_id))

        try:
            container = self.client.containers.create(
                image=settings.gameserver_image,
                name=name,
                environment=env,
                ports=dict(port_bindings),
                volumes=self._volumes_for(server_id),
                labels=self._labels_for(server_id),
                detach=True,
                tty=True,
                stdin_open=True,
                restart_policy={"Name": "unless-stopped"},
                **self._hardening(),
            )
        except APIError as exc:  # noqa: BLE001
            raise DockerError(f"failed to create container {name}: {exc}") from exc
        logger.info("created server container %s (%s)", name, container.short_id)
        return container.id

    def start(self, server_id: str) -> None:
        self._require(server_id).start()

    def stop(self, server_id: str, timeout: int = DEFAULT_STOP_TIMEOUT) -> None:
        c = self._get(self.container_name(server_id))
        if c is None:
            return
        c.stop(timeout=timeout)

    def restart(self, server_id: str, timeout: int = DEFAULT_STOP_TIMEOUT) -> None:
        self._require(server_id).restart(timeout=timeout)

    def remove(self, server_id: str, remove_data: bool = True) -> None:
        c = self._get(self.container_name(server_id))
        if c is not None:
            c.remove(force=True)
        install = self._get(self.install_name(server_id))
        if install is not None:
            install.remove(force=True)
        if remove_data:
            self.remove_volume(self.data_volume(server_id))

    def _require(self, server_id: str) -> Container:
        c = self._get(self.container_name(server_id))
        if c is None:
            raise DockerError(f"container for server {server_id} does not exist")
        return c

    # -- install / update (one-shot) -----------------------------------------

    def run_install(self, server_id: str, env: dict[str, str]) -> None:
        name = self.install_name(server_id)
        old = self._get(name)
        if old is not None:
            old.remove(force=True)

        self.ensure_volume(settings.steamcmd_cache_volume)
        self.ensure_volume(self.data_volume(server_id))

        install_env = {**env, "INSTALL_ONLY": "1", "RUN_INSTALL": "1"}
        try:
            self.client.containers.run(
                image=settings.gameserver_image,
                name=name,
                environment=install_env,
                volumes=self._volumes_for(server_id),
                labels=self._labels_for(server_id),
                detach=True,
                **self._hardening(),
            )
        except APIError as exc:  # noqa: BLE001
            raise DockerError(f"failed to start install for {server_id}: {exc}") from exc
        logger.info("install container started %s", name)

    def wait_install(self, server_id: str, timeout: int | None = None) -> tuple[int, str]:
        timeout = timeout if timeout is not None else settings.install_timeout
        c = self._get(self.install_name(server_id))
        if c is None:
            return 0, ""

        def _logs() -> str:
            try:
                return c.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            except APIError:
                return ""

        try:
            try:
                result = c.wait(timeout=timeout)
            except (ReadTimeout, RequestsConnectionError):
                # Install ran past the cap — stop it and report a clean failure
                # instead of blocking the waiter (and the panel) forever.
                logs = _logs() + f"\n[agent] install timed out after {timeout}s"
                try:
                    c.stop(timeout=10)
                except APIError:
                    pass
                return 124, logs
            code = int(result.get("StatusCode", -1))
            logs = _logs()
        finally:
            try:
                c.remove(force=True)
            except APIError:  # noqa: BLE001
                pass
        return code, logs

    # -- logs / stdin ---------------------------------------------------------

    def follow_logs(self, server_id: str, tail: int = 200) -> Iterator[bytes]:
        c = self._get(self.container_name(server_id)) or self._get(self.install_name(server_id))
        if c is None:
            return iter(())
        return c.logs(stream=True, follow=True, stdout=True, stderr=True, tail=tail)

    def recent_logs(self, server_id: str, tail: int = 200) -> str:
        c = self._get(self.container_name(server_id))
        if c is None:
            return ""
        return c.logs(stdout=True, stderr=True, tail=tail).decode("utf-8", errors="replace")

    def recent_install_logs(self, server_id: str, tail: int = 50) -> str:
        """Tail of the one-shot install container (source of download progress)."""
        c = self._get(self.install_name(server_id))
        if c is None:
            return ""
        return c.logs(stdout=True, stderr=True, tail=tail).decode("utf-8", errors="replace")

    def send_stdin(self, server_id: str, data: str) -> None:
        c = self._require(server_id)
        sock = c.attach_socket(params={"stdin": 1, "stream": 1})
        try:
            payload = data if data.endswith("\n") else data + "\n"
            os_sock = sock._sock if hasattr(sock, "_sock") else sock
            os_sock.send(payload.encode("utf-8"))
        finally:
            sock.close()


def _parse_stats(raw: dict) -> ContainerStats:
    """Compute usage metrics from a Docker stats snapshot (defensive on shape).

    Mirrors the formulas the `docker stats` CLI uses; tolerates cgroup v1/v2
    differences and missing keys (returns 0 for anything unavailable).
    """
    cpu = raw.get("cpu_stats", {}) or {}
    precpu = raw.get("precpu_stats", {}) or {}
    cpu_usage = cpu.get("cpu_usage", {}) or {}
    precpu_usage = precpu.get("cpu_usage", {}) or {}

    online = cpu.get("online_cpus") or len(cpu_usage.get("percpu_usage") or []) or 1
    cpu_delta = cpu_usage.get("total_usage", 0) - precpu_usage.get("total_usage", 0)
    system_delta = cpu.get("system_cpu_usage", 0) - precpu.get("system_cpu_usage", 0)
    cpu_pct = (cpu_delta / system_delta) * online * 100.0 if system_delta > 0 and cpu_delta > 0 else 0.0

    mem = raw.get("memory_stats", {}) or {}
    detail = mem.get("stats", {}) or {}
    # Exclude reclaimable page cache (cgroup v2: inactive_file, v1: cache).
    cache = detail.get("inactive_file", detail.get("cache", 0))
    mem_limit = mem.get("limit", 0)
    mem_used = max(mem.get("usage", 0) - cache, 0)
    mem_pct = (mem_used / mem_limit * 100.0) if mem_limit else 0.0

    net_rx = net_tx = 0
    for nic in (raw.get("networks") or {}).values():
        net_rx += nic.get("rx_bytes", 0)
        net_tx += nic.get("tx_bytes", 0)

    blk_read = blk_write = 0
    for entry in (raw.get("blkio_stats", {}) or {}).get("io_service_bytes_recursive") or []:
        op = str(entry.get("op", "")).lower()
        if op == "read":
            blk_read += entry.get("value", 0)
        elif op == "write":
            blk_write += entry.get("value", 0)

    return ContainerStats(
        running=True,
        cpu_pct=round(cpu_pct, 2),
        mem_used=mem_used,
        mem_limit=mem_limit,
        mem_pct=round(mem_pct, 2),
        net_rx=net_rx,
        net_tx=net_tx,
        blk_read=blk_read,
        blk_write=blk_write,
        pids=(raw.get("pids_stats", {}) or {}).get("current", 0) or 0,
        online_cpus=int(online),
    )


orchestrator = DockerOrchestrator()
