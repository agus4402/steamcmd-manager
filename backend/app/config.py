"""Application configuration loaded from environment variables."""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("steamcmd-manager.config")

# Default values that MUST be overridden before running outside development.
_INSECURE_DEFAULTS = {
    "admin_password": "changeme",
    "jwt_secret": "dev-jwt-secret-change-me",
    "panel_secret": "dev-panel-secret-change-me-32bytes!!",
    "agent_token": "dev-agent-token-change-me",
}
# Minimum length for the secret used to derive the Fernet credential key.
_MIN_PANEL_SECRET_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "development" | "production". In production, insecure defaults abort boot.
    app_env: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://steam:steam@db:5432/steammanager"

    # Auth
    admin_user: str = "admin"
    admin_password: str = "changeme"
    jwt_secret: str = "dev-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # Secret used to derive the Fernet key for encrypting Steam credentials.
    panel_secret: str = "dev-panel-secret-change-me-32bytes!!"

    # Port pool for game-server host ports (used by the port allocator)
    port_pool_start: int = 27015
    port_pool_end: int = 27200

    # Orchestration agent (the only component with Docker socket access).
    # The backend reaches it over the internal network with a shared token.
    agent_url: str = "http://agent:8001"
    agent_token: str = "dev-agent-token-change-me"

    # Integrations
    # Docker image used by the agent to run the Playit.gg program (one shared
    # container per connected account). Per-integration secrets are stored
    # Fernet-encrypted using panel_secret — no extra secret needed here.
    playit_image: str = "ghcr.io/playit-cloud/playit-agent:latest"
    playit_api_base: str = "https://api.playit.gg"
    # How often the periodic reconciliation loop runs (seconds); 0 disables it.
    integration_sync_interval: int = 120

    # Steam Web API key (https://steamcommunity.com/dev/apikey). Optional: when
    # empty, Workshop search and recursive dependency resolution are unavailable
    # (they require IPublishedFileService/QueryFiles + GetDetails), but keyless
    # metadata (GetPublishedFileDetails) and collection resolution still work.
    steam_api_key: str = ""

    # CORS / frontend origin
    frontend_origin: str = "http://localhost:3000"

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"


class InsecureConfigError(RuntimeError):
    """Raised when production boots with default/insecure secrets."""


def verify_secrets(settings: Settings) -> None:
    """Abort boot in production if any secret is still at its insecure default.

    In development the same problems are logged as warnings so local runs are
    frictionless while still being visible.
    """
    problems: list[str] = []
    for field, default in _INSECURE_DEFAULTS.items():
        if getattr(settings, field) == default:
            problems.append(f"{field.upper()} is still the insecure default")
    if len(settings.panel_secret) < _MIN_PANEL_SECRET_LEN:
        problems.append(
            f"PANEL_SECRET must be at least {_MIN_PANEL_SECRET_LEN} chars "
            f"(got {len(settings.panel_secret)})"
        )

    if not problems:
        return
    detail = "; ".join(problems)
    if settings.is_production:
        raise InsecureConfigError(
            "refusing to start in production with insecure config: "
            + detail
            + ". Set strong values (see .env.example)."
        )
    logger.warning("INSECURE CONFIG (ok for development only): %s", detail)


@lru_cache
def get_settings() -> Settings:
    return Settings()
