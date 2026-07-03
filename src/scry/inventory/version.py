"""Extractor for the project's current API version."""

from __future__ import annotations

import tomllib
from typing import Any

from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


def _navigate_dotted_key(data: dict[str, Any], key_path: str) -> str:
    """Walk a nested dict using a dotted key path and return the leaf value as str."""
    current: dict[str, Any] = data
    for segment in key_path.split("."):
        value: object = current.get(segment)
        if value is None:
            msg = f"Key '{segment}' not found in {list(current.keys())}"
            raise KeyError(msg)
        if isinstance(value, dict):
            current = value  # pyright: ignore[reportUnknownVariableType]
        else:
            return str(value)
    return str(current)


class VersionExtractor:
    """Extracts the project's current API version from a config file."""

    def extract(self, config: ProjectConfig, surface: AppSurface) -> AppSurface:
        """Parse api_version_source as 'file:dotted.key' and extract the version."""
        source = config.api_version_source
        if ":" not in source:
            msg = (
                f"Invalid api_version_source format: '{source}'. "
                "Expected 'file:dotted.key' (e.g., 'shopify.app.toml:webhooks.api_version')."
            )
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

        surface.api_version = _navigate_dotted_key(data, key_path)
        return surface
