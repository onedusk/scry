"""Extractor for webhook topics and OAuth/API scopes."""

from __future__ import annotations

import tomllib
from typing import Any

from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


class WebhookExtractor:
    """Extracts webhook subscription topics and scopes from a Shopify app TOML."""

    def extract(self, config: ProjectConfig, surface: AppSurface) -> AppSurface:
        """Read webhook_config_path and populate webhook_topics + scopes."""
        if config.webhook_config_path is None:
            return surface

        file_path = config.root / config.webhook_config_path
        if not file_path.is_file():
            return surface

        data: dict[str, Any] = tomllib.loads(file_path.read_text(encoding="utf-8"))

        # Extract webhook topics
        topics: set[str] = set()
        webhooks: dict[str, Any] = data.get("webhooks", {})  # pyright: ignore[reportAny]
        subscriptions: list[dict[str, Any]] = webhooks.get("subscriptions", [])  # pyright: ignore[reportAny]
        for sub in subscriptions:  # pyright: ignore[reportAny]
            for topic in sub.get("topics", []):  # pyright: ignore[reportAny]
                topics.add(topic)  # pyright: ignore[reportUnknownArgumentType]
            for topic in sub.get("compliance_topics", []):  # pyright: ignore[reportAny]
                topics.add(topic)  # pyright: ignore[reportUnknownArgumentType]

        surface.webhook_topics = sorted(topics)

        # Extract scopes
        access_scopes: dict[str, Any] = data.get("access_scopes", {})  # pyright: ignore[reportAny]
        scopes_str: str = access_scopes.get("scopes", "")  # pyright: ignore[reportAny]
        if scopes_str:
            surface.scopes = sorted(s.strip() for s in scopes_str.split(",") if s.strip())

        return surface
