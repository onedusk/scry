"""Change collectors — fetch changes from external sources."""

import logging

from scry.collect.base import BaseCollector
from scry.collect.changelog import ChangelogCollector
from scry.collect.polaris import PolarisCollector
from scry.collect.registry import RegistryCollector
from scry.collect.rss import RssCollector
from scry.collect.schema import SchemaCollector
from scry.models.config import ProjectConfig
from scry.models.results import CollectResult

__all__ = [
    "BaseCollector",
    "ChangelogCollector",
    "PolarisCollector",
    "RegistryCollector",
    "RssCollector",
    "SchemaCollector",
    "run_all_collectors",
]

logger = logging.getLogger(__name__)


def run_all_collectors(config: ProjectConfig) -> CollectResult:
    """Instantiate all collectors, run them, and return a merged CollectResult."""
    result = CollectResult()

    # SchemaCollector is special — we need its instance attrs after collect()
    schema_collector = SchemaCollector()

    collectors: list[BaseCollector] = [
        RssCollector(),
        ChangelogCollector(),
        schema_collector,
        RegistryCollector(),
        PolarisCollector(),
    ]

    for collector in collectors:
        name = type(collector).__name__
        try:
            changes = collector.collect(config)
            result.changes.extend(changes)
        except Exception:
            logger.warning("Collector %s failed", name, exc_info=True)

    # Populate schema fields from the SchemaCollector instance
    result.old_schema_sdl = schema_collector.old_schema_sdl
    result.new_schema_sdl = schema_collector.new_schema_sdl
    result.current_api_version = schema_collector.current_api_version
    result.next_api_version = schema_collector.next_api_version

    return result
