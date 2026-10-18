"""All Docker interaction lives here (inside the privileged agent).

Every game server is a dedicated sibling container created against the host
Docker daemon (the agent mounts /var/run/docker.sock). This module is the ONLY
place in the whole system that talks to docker-py — and it lives in the small,
auditable agent, never in the internet-facing backend.

Game-server containers are hardened: all capabilities dropped, no-new-privileges,
and resource limits — so a compromised game server cannot escalate.
"""

from __future__ import annotations

import io
import logging
import re
import secrets
import tarfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

import docker
from docker.errors import APIError, ContainerError, ImageNotFound, NotFound
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

# Config editor: files are read/written as the game's user, up to this size.
GAME_USER = "1000:1000"
MAX_FILE_BYTES = 2 * 1024 * 1024

# Snapshot ids look like "snap-20260618-143015-a1b2" (timestamp + random suffix).
SNAPSHOT_ID_RE = re.compile(r"^snap-\d{8}-\d{6}-[0-9a-f]{4}$")


def _new_snapshot_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"snap-{ts}-{secrets.token_hex(2)}"


def _created_from_id(snapshot_id: str) -> str:
    try:
        dt = datetime.strptime(snapshot_id[5:20], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, IndexError):
        return ""


@dataclass(slots=True)
class ContainerState:
    exists: bool
    status: str
    exit_code: int | None = None
    id: str | None = None
    started_at: str | None = None


@dataclass(slots=True)
class FileEntry:
    path: str  # relative to the data volume root
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
        st = c.attrs.get("State", {})
        return ContainerState(
            exists=True,
            status=c.status,
            exit_code=st.get("ExitCode"),
            id=c.short_id,
            started_at=st.get("StartedAt"),
        )

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

    def stop(
        self, server_id: str, timeout: int = DEFAULT_STOP_TIMEOUT, command: str | None = None
    ) -> None:
        """Stop the server container.

        With `command` (e.g. "quit"), first ask the game to save and exit on its
        own via stdin and wait up to `timeout` for it; only a server that ignores
        it gets docker-stopped (SIGTERM, then SIGKILL). Without it, plain stop.
        """
        c = self._get(self.container_name(server_id))
        if c is None:
            return
        if command:
            c.reload()
            if c.status == "running":
                try:
                    # A self-initiated exit would otherwise be undone by the
                    # unless-stopped policy. Safe to drop: the container is
                    # recreated (with the policy) on every start.
                    c.update(restart_policy={"Name": "no"})
                    self.send_stdin(server_id, command)
                    c.wait(timeout=timeout)
                    logger.info("server %s exited after %r", server_id, command)
                    return
                except (ReadTimeout, RequestsConnectionError):
                    logger.warning(
                        "server %s still running %ss after %r; forcing stop",
                        server_id, timeout, command,
                    )
                except (APIError, DockerError) as exc:
                    logger.warning("graceful stop of %s failed (%s); forcing stop", server_id, exc)
            timeout = 10
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
            self._purge_backups(server_id)

    def _require(self, server_id: str) -> Container:
        c = self._get(self.container_name(server_id))
        if c is None:
            raise DockerError(f"container for server {server_id} does not exist")
        return c

    # -- backups / volume ops -------------------------------------------------

    @staticmethod
    def _helper_image(as_game_user: bool) -> dict[str, object]:
        """Image/user for a helper container.

        Helpers drop every capability, so root inside them can NOT write into the
        game's directories (owned by uid 1000, mode 755) nor chown what it
        creates. Anything that modifies a server's /data therefore runs as the
        game user, on the gameserver image: when an empty volume is first mounted
        at its /data, Docker seeds it with that image's steam-owned /data, so even
        fresh volumes (clones) are writable. `env` replaces the image's entrypoint
        so the command runs as given.
        """
        if as_game_user:
            return {
                "image": settings.gameserver_image,
                "user": GAME_USER,
                "entrypoint": ["env"],
            }
        return {"image": settings.helper_image}

    def _run_helper(
        self,
        command: list[str],
        volumes: dict[str, dict[str, str]],
        *,
        as_game_user: bool = False,
        raw: bool = False,
    ) -> str | bytes:
        """Run a one-shot, network-less, unprivileged helper container for volume
        work (tar/copy). Returns its stdout (bytes when `raw`); raises DockerError
        on failure. Use `as_game_user` for anything that writes a server's /data."""
        try:
            out = self.client.containers.run(
                command=command,
                volumes=volumes,
                remove=True,
                network_mode="none",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                stdout=True,
                stderr=False if raw else True,
                **self._helper_image(as_game_user),
            )
        except ContainerError as exc:
            detail = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else exc.stderr
            raise DockerError(f"volume helper failed: {detail or exc}") from exc
        except (APIError, ImageNotFound) as exc:  # noqa: BLE001
            raise DockerError(f"volume helper error: {exc}") from exc
        if raw:
            return bytes(out)
        return out.decode("utf-8", "replace") if isinstance(out, (bytes, bytearray)) else str(out)

    # -- data-volume files (config editor) -------------------------------------
    #
    # Paths are relative to the server's /data and pre-validated by main.py
    # (FILE_PATH_RE: no "..", no leading "/", no quotes). Helpers run as the
    # game's user (uid 1000) so they can only touch what the game itself owns,
    # and anything they create stays writable by the game.

    def list_files(
        self,
        server_id: str,
        path: str,
        depth: int,
        kind: str | None = None,
        name: str | None = None,
    ) -> list[FileEntry]:
        """Entries under `path` up to `depth` levels. `kind` ("file"|"dir") and
        `name` (a find -name glob, pre-validated) narrow deep scans, e.g. finding
        every mod.info in a workshop item without listing all of its assets."""
        target = f"/data/{path}".rstrip("/")
        types = {"file": "-type f", "dir": "-type d"}.get(kind or "", "\\( -type f -o -type d \\)")
        name_filter = f"-name '{name}' " if name else ""
        out = self._run_helper(
            [
                "sh",
                "-c",
                f"[ -d '{target}' ] || exit 0; "
                f"find '{target}' -mindepth 1 -maxdepth {int(depth)} {types} {name_filter}"
                "-exec stat -c '%F|%s|%Y|%n' {} +",
            ],
            {self.data_volume(server_id): {"bind": "/data", "mode": "ro"}},
            as_game_user=True,
        )
        entries: list[FileEntry] = []
        for line in str(out).splitlines():
            parts = line.split("|", 3)
            if len(parts) != 4 or not parts[3].startswith("/data/"):
                continue
            kind, size, mtime, name = parts
            entries.append(
                FileEntry(
                    path=name[len("/data/"):],
                    type="dir" if kind == "directory" else "file",
                    size=int(size) if size.isdigit() else 0,
                    mtime=int(mtime) if mtime.isdigit() else 0,
                )
            )
        entries.sort(key=lambda e: e.path)
        return entries

    def read_file(self, server_id: str, path: str) -> tuple[bytes, int] | None:
        """Return (content, mtime) or None if the file does not exist."""
        target = f"/data/{path}"
        out = self._run_helper(
            [
                "sh",
                "-c",
                f"[ -f '{target}' ] || {{ echo missing; exit 0; }}; "
                f"[ $(stat -c %s '{target}') -le {MAX_FILE_BYTES} ] || {{ echo toolarge; exit 0; }}; "
                f"echo ok $(stat -c %Y '{target}'); cat '{target}'",
            ],
            {self.data_volume(server_id): {"bind": "/data", "mode": "ro"}},
            as_game_user=True,
            raw=True,
        )
        assert isinstance(out, bytes)
        header, _, content = out.partition(b"\n")
        if header == b"missing":
            return None
        if header == b"toolarge":
            raise DockerError(f"file is larger than {MAX_FILE_BYTES} bytes")
        _, _, mtime = header.decode().partition(" ")
        return content, int(mtime) if mtime.isdigit() else 0

    def write_file(self, server_id: str, path: str, content: bytes) -> int:
        """Write a file (keeping the previous version as <file>.panel-bak) and
        return its new mtime.

        The content is uploaded into the helper's own /tmp (put_archive on the
        not-yet-started container), then the helper copies it into place running
        as the game user, so ownership and created parent dirs stay the game's.
        """
        if len(content) > MAX_FILE_BYTES:
            raise DockerError(f"file is larger than {MAX_FILE_BYTES} bytes")
        target = f"/data/{path}"
        parent = target.rsplit("/", 1)[0]
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name="panel-upload")
            info.size = len(content)
            info.mode = 0o644
            info.uid = info.gid = 1000
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(content))
        script = (
            f"mkdir -p '{parent}' && "
            f"{{ [ ! -f '{target}' ] || cp -p '{target}' '{target}.panel-bak'; }} && "
            f"cat /tmp/panel-upload > '{target}' && stat -c %Y '{target}'"
        )
        helper = None
        try:
            helper = self.client.containers.create(
                command=["sh", "-c", script],
                volumes={self.data_volume(server_id): {"bind": "/data", "mode": "rw"}},
                network_mode="none",
                **self._helper_image(as_game_user=True),
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
            )
            if not helper.put_archive("/tmp", buf.getvalue()):
                raise DockerError(f"could not upload {path}")
            helper.start()
            result = helper.wait(timeout=60)
            logs = helper.logs(stdout=True, stderr=True).decode("utf-8", "replace").strip()
            if result.get("StatusCode") != 0:
                raise DockerError(f"could not write {path}: {logs}")
        except (APIError, ImageNotFound, ReadTimeout) as exc:  # noqa: BLE001
            raise DockerError(f"write failed: {exc}") from exc
        finally:
            if helper is not None:
                helper.remove(force=True)
        last = logs.splitlines()[-1] if logs else ""
        return int(last) if last.isdigit() else info.mtime

    def create_snapshot(self, server_id: str) -> SnapshotInfo:
        """Tar the server's data volume into a new backup tarball."""
        self.ensure_volume(self.data_volume(server_id))
        self.ensure_volume(settings.backups_volume)
        snap_id = _new_snapshot_id()
        dest_dir = f"/backups/{server_id}"
        archive = f"{dest_dir}/{snap_id}.tar.gz"
        # Write to a .partial file and atomically rename on success, so a backup
        # in progress (or a failed one) never appears as a complete snapshot.
        cmd = [
            "sh",
            "-c",
            f"mkdir -p '{dest_dir}' && rm -f '{dest_dir}'/*.partial 2>/dev/null; "
            f"tar czf '{archive}.partial' -C /data . && mv '{archive}.partial' '{archive}' && stat -c '%s' '{archive}'",
        ]
        out = self._run_helper(
            cmd,
            {
                self.data_volume(server_id): {"bind": "/data", "mode": "ro"},
                settings.backups_volume: {"bind": "/backups", "mode": "rw"},
            },
        )
        size = 0
        for tok in reversed(out.split()):
            if tok.isdigit():
                size = int(tok)
                break
        logger.info("created snapshot %s for %s (%d bytes)", snap_id, server_id, size)
        return SnapshotInfo(id=snap_id, created_at=_created_from_id(snap_id), size=size)

    def list_snapshots(self, server_id: str) -> list[SnapshotInfo]:
        self.ensure_volume(settings.backups_volume)
        dest_dir = f"/backups/{server_id}"
        cmd = [
            "sh",
            "-c",
            f"cd '{dest_dir}' 2>/dev/null && for f in *.tar.gz; do [ -e \"$f\" ] && stat -c '%n %s' \"$f\"; done || true",
        ]
        out = self._run_helper(cmd, {settings.backups_volume: {"bind": "/backups", "mode": "ro"}})
        snapshots: list[SnapshotInfo] = []
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) != 2:
                continue
            name, size = parts
            sid = name[:-7] if name.endswith(".tar.gz") else name
            if not SNAPSHOT_ID_RE.match(sid):
                continue
            snapshots.append(SnapshotInfo(id=sid, created_at=_created_from_id(sid), size=int(size) if size.isdigit() else 0))
        snapshots.sort(key=lambda s: s.id, reverse=True)
        return snapshots

    def restore_snapshot(self, server_id: str, snapshot_id: str) -> None:
        if not SNAPSHOT_ID_RE.match(snapshot_id):
            raise DockerError("invalid snapshot id")
        self.ensure_volume(self.data_volume(server_id))
        archive = f"/backups/{server_id}/{snapshot_id}.tar.gz"
        cmd = [
            "sh",
            "-c",
            f"test -f '{archive}' || {{ echo 'snapshot not found' >&2; exit 2; }}; "
            f"rm -rf /data/* /data/.[!.]* 2>/dev/null; tar xzf '{archive}' -C /data",
        ]
        # As the game user: files end up owned by it (root here couldn't delete
        # the game's files, and couldn't chown what it extracts).
        self._run_helper(
            cmd,
            {
                self.data_volume(server_id): {"bind": "/data", "mode": "rw"},
                settings.backups_volume: {"bind": "/backups", "mode": "ro"},
            },
            as_game_user=True,
        )
        logger.info("restored snapshot %s into %s", snapshot_id, server_id)

    def delete_snapshot(self, server_id: str, snapshot_id: str) -> None:
        if not SNAPSHOT_ID_RE.match(snapshot_id):
            raise DockerError("invalid snapshot id")
        archive = f"/backups/{server_id}/{snapshot_id}.tar.gz"
        self._run_helper(
            ["sh", "-c", f"rm -f '{archive}'"],
            {settings.backups_volume: {"bind": "/backups", "mode": "rw"}},
        )

    def copy_data(self, src_server_id: str, dst_server_id: str) -> None:
        """Copy the contents of one server's data volume into another's (clone)."""
        self.ensure_volume(self.data_volume(src_server_id))
        self.ensure_volume(self.data_volume(dst_server_id))
        # Destination at /data as the game user: a fresh volume gets the image's
        # steam-owned /data, and copies stay owned by the game (no ownership
        # preserve needed, which an unprivileged helper couldn't do anyway).
        self._run_helper(
            ["sh", "-c", "cp -R --preserve=mode,timestamps /from/. /data/"],
            {
                self.data_volume(src_server_id): {"bind": "/from", "mode": "ro"},
                self.data_volume(dst_server_id): {"bind": "/data", "mode": "rw"},
            },
            as_game_user=True,
        )

    def _purge_backups(self, server_id: str) -> None:
        """Best-effort removal of a server's backup tarballs (on delete)."""
        try:
            self._run_helper(
                ["sh", "-c", f"rm -rf '/backups/{server_id}'"],
                {settings.backups_volume: {"bind": "/backups", "mode": "rw"}},
            )
        except DockerError as exc:  # noqa: BLE001 — never block deletion on backup cleanup
            logger.warning("could not purge backups for %s: %s", server_id, exc)

    # -- workshop -------------------------------------------------------------

    def download_workshop_item(
        self, server_id: str, app_id: int, item_id: str, install_path: str
    ) -> tuple[int, str]:
        """Run a one-shot gameserver container that downloads a workshop item via
        steamcmd and copies it into the server's data volume. Returns (code, logs)."""
        name = f"gs-ws-{server_id}-{item_id}"
        old = self._get(name)
        if old is not None:
            old.remove(force=True)

        self.ensure_volume(settings.steamcmd_cache_volume)
        self.ensure_volume(self.data_volume(server_id))

        env = {
            "WORKSHOP_DOWNLOAD": "1",
            "WORKSHOP_APP_ID": str(app_id),
            "WORKSHOP_ITEM_ID": item_id,
            "WORKSHOP_INSTALL_PATH": install_path,
            "STEAM_LOGIN_USER": "anonymous",
            "INSTALL_DIR": "/data",
        }
        try:
            container = self.client.containers.run(
                image=settings.gameserver_image,
                name=name,
                environment=env,
                volumes=self._volumes_for(server_id),
                labels=self._labels_for(server_id),
                detach=True,
                **self._hardening(),
            )
        except APIError as exc:  # noqa: BLE001
            raise DockerError(f"failed to start workshop download for {server_id}: {exc}") from exc

        def _logs() -> str:
            try:
                return container.logs(stdout=True, stderr=True).decode("utf-8", "replace")
            except APIError:
                return ""

        try:
            try:
                result = container.wait(timeout=settings.install_timeout)
            except (ReadTimeout, RequestsConnectionError):
                logs = _logs() + f"\n[agent] workshop download timed out after {settings.install_timeout}s"
                try:
                    container.stop(timeout=10)
                except APIError:
                    pass
                return 124, logs
            code = int(result.get("StatusCode", -1))
            logs = _logs()
        finally:
            try:
                container.remove(force=True)
            except APIError:
                pass
        return code, logs

    def remove_workshop_item(self, server_id: str, install_path: str, item_id: str) -> None:
        target = f"/data/{install_path}/{item_id}"
        self._run_helper(
            ["sh", "-c", f"rm -rf '{target}'"],
            {self.data_volume(server_id): {"bind": "/data", "mode": "rw"}},
            as_game_user=True,
        )

    def list_workshop_items(self, server_id: str, install_path: str) -> list[str]:
        """Return the numeric item-id directories present under the install path
        on the server's data volume (used by the sync feature)."""
        target = f"/data/{install_path}"
        # List immediate child dir names; empty/non-existent dir prints nothing.
        out = self._run_helper(
            [
                "sh",
                "-c",
                f"[ -d '{target}' ] && ls -1 '{target}' 2>/dev/null || true",
            ],
            {self.data_volume(server_id): {"bind": "/data", "mode": "ro"}},
        )
        return [
            line.strip()
            for line in out.splitlines()
            if line.strip().isdigit()
        ]

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

    def follow_logs(
        self,
        server_id: str,
        tail: int | str = 200,
        source: str = "auto",
        since: float | None = None,
        timestamps: bool = False,
    ) -> Iterator[bytes]:
        """Follow one container's output.

        source: "server" (game container), "install" (one-shot steamcmd
        container) or "auto" — the install container while it runs (installs and
        update-on-start), otherwise the game container.
        """
        server = self._get(self.container_name(server_id))
        install = self._get(self.install_name(server_id))
        if source == "server":
            c = server
        elif source == "install":
            c = install
        else:
            c = install if install is not None and install.status == "running" else (server or install)
        if c is None:
            return iter(())
        kwargs: dict = {"stream": True, "follow": True, "stdout": True, "stderr": True,
                        "tail": tail, "timestamps": timestamps}
        if since is not None:
            kwargs["since"] = since
        return c.logs(**kwargs)

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
