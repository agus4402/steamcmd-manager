"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    # CORS / frontend origin
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
