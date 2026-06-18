"""Agent configuration. The agent is the only component that talks to Docker."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Shared secret the backend must present (Authorization: Bearer <token>).
    agent_token: str = "dev-agent-token-change-me"

    # Docker
    docker_host: str = "unix:///var/run/docker.sock"
    gameserver_image: str = "steamcmd-manager/gameserver:latest"
    steamcmd_cache_volume: str = "steamcmd-cache"

    # Host port pool — used to validate that requested port bindings stay in range
    # (a compromised backend can't ask the agent to bind privileged ports like 22).
    port_pool_start: int = 27015
    port_pool_end: int = 27200

    # Worker (game-server) resource limits — least-privilege blast-radius control.
    worker_mem_limit: str = "4g"
    worker_pids_limit: int = 512
    worker_cpus: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
