"""Inventory extraction — scan a target project and build an AppSurface."""

import logging

from scry.inventory.base import BaseExtractor
from scry.inventory.components import ComponentExtractor
from scry.inventory.dependencies import DependencyExtractor
from scry.inventory.graphql import GraphQLExtractor
from scry.inventory.version import VersionExtractor
from scry.inventory.webhooks import WebhookExtractor
from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface

__all__ = [
    "BaseExtractor",
    "ComponentExtractor",
    "DependencyExtractor",
    "GraphQLExtractor",
    "VersionExtractor",
    "WebhookExtractor",
    "run_all_extractors",
]

logger = logging.getLogger(__name__)


def run_all_extractors(config: ProjectConfig) -> AppSurface:
    """Instantiate all extractors, chain them, and return the populated surface."""
    surface = AppSurface(api_version="")

    extractors: list[BaseExtractor] = [
        VersionExtractor(),
        GraphQLExtractor(),
        WebhookExtractor(),
        DependencyExtractor(),
        ComponentExtractor(),
    ]

    for extractor in extractors:
        name = type(extractor).__name__
        try:
            surface = extractor.extract(config, surface)
        except Exception:
            # VersionExtractor is load-bearing — propagate its failures
            if name == "VersionExtractor":
                raise
            logger.warning("Extractor %s failed", name, exc_info=True)

    return surface
