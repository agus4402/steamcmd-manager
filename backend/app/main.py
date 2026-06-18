"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import SessionLocal, engine
from app.routers import auth, console_ws, servers, templates
from app.routers.auth import require_user
from app.services.auth import seed_admin
from app.services.docker_orchestrator import orchestrator

logger = logging.getLogger("steamcmd-manager")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Seed the admin user on boot (idempotent).
    async with SessionLocal() as session:
        try:
            await seed_admin(session)
        except Exception:  # noqa: BLE001 — don't block startup if DB not migrated yet
            logger.exception("admin seed skipped")
    yield


app = FastAPI(title="SteamCMD Server Manager", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public: health + auth. Protected: everything else (token required).
app.include_router(auth.router)
app.include_router(templates.router, dependencies=[Depends(require_user)])
app.include_router(servers.router, dependencies=[Depends(require_user)])
# WebSocket validates its token from the query string (see console_ws).
app.include_router(console_ws.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/api/health/full")
async def health_full() -> dict[str, object]:
    """Verifies connectivity to Postgres and the orchestration agent.

    The backend has no Docker access of its own — it checks Docker reachability
    indirectly by pinging the agent.
    """
    result: dict[str, object] = {"status": "ok", "db": "unknown", "agent": "unknown"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        result["db"] = "connected"
    except Exception as exc:  # noqa: BLE001
        result["db"] = f"error: {exc}"
        result["status"] = "degraded"

    try:
        info = await run_in_threadpool(orchestrator.ping)
        result["agent"] = f"connected (docker v{info.get('docker_version', '?')})"
    except Exception as exc:  # noqa: BLE001
        result["agent"] = f"error: {exc}"
        result["status"] = "degraded"

    return result
