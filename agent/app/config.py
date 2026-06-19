"""Agent configuration. The agent is the only component that talks to Docker."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


_INSECURE_AGENT_TOKEN = "dev-agent-token-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "development" | "production". In production an insecure token aborts boot.
    app_env: str = "development"

    # Shared secret the backend must present (Authorization: Bearer <token>).
    agent_token: str = _INSECURE_AGENT_TOKEN

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    # Docker
    docker_host: str = "unix:///var/run/docker.sock"
    gameserver_image: str = "steamcmd-manager/gameserver:latest"
    steamcmd_cache_volume: str = "steamcmd-cache"
    # Shared volume holding per-server backup tarballs, and the tiny image used
    # for volume operations (tar/copy) — runs with no network and no privileges.
    backups_volume: str = "steamcmd-backups"
    helper_image: str = "alpine:3.20"

    # Host port pool — used to validate that requested port bindings stay in range
    # (a compromised backend can't ask the agent to bind privileged ports like 22).
    port_pool_start: int = 27015
    port_pool_end: int = 27200

    # Worker (game-server) resource limits — least-privilege blast-radius control.
    worker_mem_limit: str = "4g"
    worker_pids_limit: int = 512
    worker_cpus: float = 2.0

    # Hard cap on a single install/update (seconds). Generous for large depots,
    # but bounded so a stalled steamcmd never blocks the waiter forever.
    install_timeout: int = 3600


class InsecureConfigError(RuntimeError):
    """Raised when the agent boots in production with a default token."""


def verify_secrets(settings: "Settings") -> None:
    if settings.agent_token == _INSECURE_AGENT_TOKEN:
        msg = "AGENT_TOKEN is still the insecure default"
        if settings.is_production:
            raise InsecureConfigError(f"refusing to start in production: {msg}")
        import logging

        logging.getLogger("steamcmd-agent.config").warning(
            "INSECURE CONFIG (ok for development only): %s", msg
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
