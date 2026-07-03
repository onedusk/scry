"""Change collectors — fetch changes from external sources."""

import logging
from collections.abc import Callable
from importlib.metadata import entry_points

from scry.collect.base import BaseCollector
from scry.collect.changelog import ChangelogCollector
from scry.collect.polaris import PolarisCollector
from scry.collect.registry import RegistryCollector
from scry.collect.rss import RssCollector
from scry.collect.schema import SchemaCollector
from scry.models.config import ProjectConfig
from scry.models.results import CollectResult

__all__ = [
    "BUILTIN_COLLECTORS",
    "ENTRY_POINT_GROUP",
    "BaseCollector",
    "ChangelogCollector",
    "PolarisCollector",
    "RegistryCollector",
    "RssCollector",
    "SchemaCollector",
    "load_collectors",
    "run_all_collectors",
]

logger = logging.getLogger(__name__)

# Built-in collectors, keyed by the short name used in ProjectConfig.disabled_collectors.
BUILTIN_COLLECTORS: dict[str, Callable[[], BaseCollector]] = {
    "rss": RssCollector,
    "changelog": ChangelogCollector,
    "schema": SchemaCollector,
    "registry": RegistryCollector,
    "polaris": PolarisCollector,
}

# Entry-point group third-party packages use to register extra collectors.
ENTRY_POINT_GROUP = "scry.collectors"


def load_collectors(config: ProjectConfig) -> list[BaseCollector]:
    """Instantiate enabled built-in collectors plus any entry-point plugins.

    Third-party packages register a zero-arg collector factory under the
    "scry.collectors" entry-point group. Names listed in
    config.disabled_collectors (built-in short names or entry-point names)
    are skipped.
    """
    disabled = set(config.disabled_collectors)
    known = set(BUILTIN_COLLECTORS)
    collectors: list[BaseCollector] = [
        factory() for name, factory in BUILTIN_COLLECTORS.items() if name not in disabled
    ]

    for ep in entry_points(group=ENTRY_POINT_GROUP):
        known.add(ep.name)
        if ep.name in disabled:
            continue
        try:
            factory = ep.load()
            collectors.append(factory())
        except Exception:
            logger.warning("Failed to load collector plugin %s", ep.name, exc_info=True)

    for name in sorted(disabled - known):
        logger.warning("Unknown collector name in disabled_collectors: %s", name)

    return collectors


def run_all_collectors(config: ProjectConfig) -> CollectResult:
    """Instantiate the enabled collectors, run them, and return a merged CollectResult."""
    result = CollectResult()

    collectors = load_collectors(config)

    for collector in collectors:
        name = type(collector).__name__
        try:
            changes = collector.collect(config)
            result.changes.extend(changes)
        except Exception:
            logger.warning("Collector %s failed", name, exc_info=True)

    # Populate schema fields from the SchemaCollector instance, if enabled.
    # SchemaCollector is special — we need its instance attrs after collect().
    schema_collector = next((c for c in collectors if isinstance(c, SchemaCollector)), None)
    if schema_collector is not None:
        result.old_schema_sdl = schema_collector.old_schema_sdl
        result.new_schema_sdl = schema_collector.new_schema_sdl
        result.current_api_version = schema_collector.current_api_version
        result.next_api_version = schema_collector.next_api_version

    return result
