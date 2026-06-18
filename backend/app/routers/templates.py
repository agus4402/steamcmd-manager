"""Template listing endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.server import TemplateOut
from app.services.template_loader import get_templates

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
async def list_templates() -> list[TemplateOut]:
    return [
        TemplateOut(
            id=t.id,
            name=t.name,
            app_id=t.app_id,
            anonymous_login=t.anonymous_login,
            ports=[{"name": p.name, "protocol": p.protocol, "default": p.default} for p in t.ports],
            variables=[{"key": v.key, "default": v.default} for v in t.variables],
            update_on_start=t.update_on_start,
        )
        for t in get_templates().values()
    ]
