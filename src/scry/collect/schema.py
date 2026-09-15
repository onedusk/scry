"""Collector for GraphQL schema introspection."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

import httpx
from graphql import build_client_schema, get_introspection_query, print_schema

from scry.inventory.version import _navigate_dotted_key  # pyright: ignore[reportPrivateUsage]
from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig

logger = logging.getLogger(__name__)


def _next_quarterly_version(current: str) -> str:
    """Calculate the next quarterly API version from a YYYY-MM string.

    E.g., 2026-01 → 2026-04, 2026-10 → 2027-01.
    """
    year, month = int(current[:4]), int(current[5:7])
    month += 3
    if month > 12:
        month -= 12
        year += 1
    return f"{year:04d}-{month:02d}"


def _read_api_version(config: ProjectConfig) -> str:
    """Read the current API version from the project config file.

    Uses the same file:dotted.key format as VersionExtractor.
    """
    source = config.api_version_source
    if ":" not in source:
        msg = f"Invalid api_version_source format: '{source}'"
        raise ValueError(msg)

    sep_idx = source.index(":")
    file_part = source[:sep_idx]
    key_path = source[sep_idx + 1 :]

    file_path = config.root / file_part
    if not file_path.is_file():
        msg = f"Version source file not found: {file_path}"
        raise FileNotFoundError(msg)

    suffix = file_path.suffix.lower()
    if suffix == ".toml":
        data: dict[str, Any] = tomllib.loads(file_path.read_text(encoding="utf-8"))
    elif suffix in (".yaml", ".yml"):
        import yaml

        raw: object = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        data = dict(raw) if isinstance(raw, dict) else {}  # pyright: ignore[reportUnknownArgumentType]
    else:
        msg = f"Unsupported config file format: {suffix}"
        raise ValueError(msg)

    return _navigate_dotted_key(data, key_path)


_MAX_VERSION_PROBES = 8  # quarterly versions to look ahead (two years)
_PROBE_QUERY = "{ __schema { queryType { name } } }"


def _version_available(version: str, base_url: str, client: httpx.Client) -> bool:
    """Return True when the endpoint serves a schema for `version`.

    Sends a minimal query instead of a full introspection. A 4xx response
    (Shopify answers 400 for unpublished versions) means the version is not
    available; a 5xx response is raised so it surfaces as a fetch failure.
    """
    response = client.post(f"{base_url}/{version}", json={"query": _PROBE_QUERY}, timeout=30.0)
    if response.status_code >= 500:
        response.raise_for_status()
    if response.status_code != 200:
        return False
    try:
        return "data" in response.json()
    except ValueError:
        return False


def _latest_available_version(current: str, base_url: str, client: httpx.Client) -> str:
    """Walk forward one quarter at a time from `current` and return the newest published version.

    Stops at the first version the endpoint does not serve, or after
    _MAX_VERSION_PROBES steps. Returns `current` when nothing newer exists.
    """
    latest = current
    candidate = _next_quarterly_version(current)
    for _ in range(_MAX_VERSION_PROBES):
        if not _version_available(candidate, base_url, client):
            break
        latest = candidate
        candidate = _next_quarterly_version(candidate)
    return latest


# Leading SDL comment marking caches fetched with deprecated input values included.
# Older cache files lack it and are refetched, since they silently drop those fields.
CACHE_MARKER = "# scry schema cache v2: deprecated input values included\n"


def _fetch_schema_sdl(
    version: str,
    base_url: str,
    cache_dir: Path,
    client: httpx.Client,
) -> str:
    """Fetch a schema SDL by introspection, with file-based caching.

    Introspection omits deprecated input fields and arguments unless asked
    for them, which would make a deprecation look like a removal in the
    diff, so the query requests them explicitly.
    """
    cache_file = cache_dir / f"{version}.graphql"
    if cache_file.is_file():
        cached = cache_file.read_text(encoding="utf-8")
        if cached.startswith(CACHE_MARKER):
            return cached
        logger.info("Refetching %s schema: cached copy predates deprecated input values", version)

    url = f"{base_url}/{version}"
    query = get_introspection_query(input_value_deprecation=True)
    response = client.post(url, json={"query": query}, timeout=30.0)
    response.raise_for_status()

    introspection_data: dict[str, Any] = response.json()["data"]
    schema = build_client_schema(introspection_data)  # pyright: ignore[reportArgumentType]
    sdl = CACHE_MARKER + print_schema(schema)

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(sdl, encoding="utf-8")

    return sdl


class SchemaCollector:
    """Fetches GraphQL schemas for the project's API version and the newest published one.

    The target version is found by probing forward quarter by quarter from
    the project's pinned version, so a project several versions behind is
    diffed against the latest release rather than only the next quarter.

    After collect() is called, the SDL strings and version info are
    available as instance attributes for run_all_collectors to read.
    """

    def __init__(self) -> None:
        self.old_schema_sdl: str | None = None
        self.new_schema_sdl: str | None = None
        self.current_api_version: str | None = None
        self.next_api_version: str | None = None

    def collect(self, config: ProjectConfig) -> list[ChangeRecord]:
        """Fetch schemas via introspection. Returns empty list (no ChangeRecords)."""
        if config.schema_base_url is None:
            return []

        try:
            current_version = _read_api_version(config)
        except Exception:
            logger.warning("Failed to read API version from config", exc_info=True)
            return []

        cache_dir = config.root / ".cache" / "schemas"
        self.current_api_version = current_version

        try:
            with httpx.Client() as client:
                self.old_schema_sdl = _fetch_schema_sdl(
                    current_version, config.schema_base_url, cache_dir, client
                )
                next_version = _latest_available_version(
                    current_version, config.schema_base_url, client
                )
                if next_version == current_version:
                    logger.info(
                        "No API version newer than %s is published; skipping schema diff",
                        current_version,
                    )
                    return []
                self.next_api_version = next_version
                logger.info(
                    "Diffing API version %s against latest published %s",
                    current_version,
                    next_version,
                )
                self.new_schema_sdl = _fetch_schema_sdl(
                    next_version, config.schema_base_url, cache_dir, client
                )
        except Exception:
            logger.warning("Schema fetch failed", exc_info=True)

        return []
