"""Playit.gg data-plane (runs inside the privileged, egress-less agent).

The agent's ONLY Playit job is to run the shared ``playitd`` forwarder container
(``playit-{integration_id}``) with the account secret. It uses
``network_mode=host`` so it can forward to the game-server ports published on
``127.0.0.1`` and so it gets its own internet egress (the agent's own network is
``internal``). All control-plane calls (claim, tunnel allocation) live in the
backend, which has egress — see ``backend/app/integrations/playit/api.py``.
"""

from __future__ import annotations

import logging

from docker.errors import APIError, NotFound

from app.config import get_settings
from app.orchestrator import DockerError, orchestrator

logger = logging.getLogger("steamcmd-agent.playit")
settings = get_settings()

RUN_PREFIX = "playit-"
CONFIG_DIR = "/etc/playit"


def _run_name(integration_id: str) -> str:
    return f"{RUN_PREFIX}{integration_id}"


def _volume(integration_id: str) -> str:
    return f"playit-{integration_id}"


class PlayitManager:
    @property
    def _client(self):
        return orchestrator.client

    def _get(self, name: str):
        try:
            return self._client.containers.get(name)
        except NotFound:
            return None

    def _hardening(self) -> dict:
        # Host network (reach published game ports + own egress), but no extra
        # capabilities and no privilege escalation.
        return {
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "network_mode": "host",
            "mem_limit": "256m",
            "pids_limit": 128,
        }

    def ensure_running(self, integration_id: str, secret: str) -> None:
        """Ensure the shared playitd forwarder runs with the account secret."""
        name = _run_name(integration_id)
        container = self._get(name)
        if container is not None:
            container.reload()
            if container.status == "running":
                return
            container.remove(force=True)

        orchestrator.ensure_volume(_volume(integration_id))
        try:
            self._client.containers.run(
                image=settings.playit_image,
                name=name,
                environment={"SECRET_KEY": secret},
                volumes={_volume(integration_id): {"bind": CONFIG_DIR, "mode": "rw"}},
                detach=True,
                restart_policy={"Name": "unless-stopped"},
                **self._hardening(),
            )
        except APIError as exc:  # noqa: BLE001
            raise DockerError(f"failed to start playit agent: {exc}") from exc
        logger.info("playit forwarder running for %s", integration_id)

    def state(self, integration_id: str) -> dict:
        container = self._get(_run_name(integration_id))
        running = container is not None and container.status == "running"
        return {"running": running}

    def remove(self, integration_id: str) -> None:
        c = self._get(_run_name(integration_id))
        if c is not None:
            c.remove(force=True)
        orchestrator.remove_volume(_volume(integration_id))


playit = PlayitManager()
