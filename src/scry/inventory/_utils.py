"""Shared utilities for inventory extractors."""

from __future__ import annotations

from pathlib import Path

from scry.models.config import ProjectConfig


def glob_source_files(config: ProjectConfig) -> list[Path]:
    """Collect all source files matching config patterns, deduplicated."""
    seen: set[Path] = set()
    result: list[Path] = []
    for pattern in config.source_patterns:
        for path in config.root.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                result.append(path)
    return result


def read_source_files(config: ProjectConfig) -> dict[Path, str]:
    """Glob source files once and return a path -> content map."""
    return {path: path.read_text(encoding="utf-8") for path in glob_source_files(config)}
