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


def _fetch_schema_sdl(
    version: str,
    base_url: str,
    cache_dir: Path,
    client: httpx.Client,
) -> str:
    """Fetch a schema SDL by introspection, with file-based caching."""
    cache_file = cache_dir / f"{version}.graphql"
    if cache_file.is_file():
        return cache_file.read_text(encoding="utf-8")

    url = f"{base_url}/{version}"
    query = get_introspection_query()
    response = client.post(url, json={"query": query}, timeout=30.0)
    response.raise_for_status()

    introspection_data: dict[str, Any] = response.json()["data"]
    schema = build_client_schema(introspection_data)  # pyright: ignore[reportArgumentType]
    sdl = print_schema(schema)

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(sdl, encoding="utf-8")

    return sdl


class SchemaCollector:
    """Fetches GraphQL schemas for the current and next API versions.

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

        next_version = _next_quarterly_version(current_version)
        cache_dir = config.root / ".cache" / "schemas"

        self.current_api_version = current_version
        self.next_api_version = next_version

        try:
            with httpx.Client() as client:
                self.old_schema_sdl = _fetch_schema_sdl(
                    current_version, config.schema_base_url, cache_dir, client
                )
                self.new_schema_sdl = _fetch_schema_sdl(
                    next_version, config.schema_base_url, cache_dir, client
                )
        except Exception:
            logger.warning("Schema fetch failed", exc_info=True)

        return []
