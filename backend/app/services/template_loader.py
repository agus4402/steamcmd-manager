"""Load and validate game templates from YAML files."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

from app.schemas.template import GameTemplate

logger = logging.getLogger("steamcmd-manager.templates")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class TemplateError(RuntimeError):
    pass


def _load_all() -> dict[str, GameTemplate]:
    templates: dict[str, GameTemplate] = {}
    if not TEMPLATES_DIR.exists():
        logger.warning("templates dir %s does not exist", TEMPLATES_DIR)
        return templates
    for path in sorted(TEMPLATES_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            tpl = GameTemplate.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            raise TemplateError(f"invalid template {path.name}: {exc}") from exc
        if tpl.id in templates:
            raise TemplateError(f"duplicate template id '{tpl.id}' in {path.name}")
        templates[tpl.id] = tpl
    logger.info("loaded %d templates: %s", len(templates), list(templates))
    return templates


@lru_cache
def get_templates() -> dict[str, GameTemplate]:
    return _load_all()


def get_template(template_id: str) -> GameTemplate:
    tpl = get_templates().get(template_id)
    if tpl is None:
        raise TemplateError(f"unknown template '{template_id}'")
    return tpl
