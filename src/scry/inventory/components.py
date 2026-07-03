"""Extractor for UI components (web components and React imports)."""

from __future__ import annotations

import re
from pathlib import Path

from scry.inventory._utils import read_source_files
from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


class ComponentExtractor:
    """Extracts UI component usage from source files."""

    def __init__(self, source_files: dict[Path, str] | None = None) -> None:
        """Optionally accept a pre-read path -> content map to avoid re-reading files."""
        self._source_files = source_files

    def extract(self, config: ProjectConfig, surface: AppSurface) -> AppSurface:
        """Scan source files for web component tags and React imports."""
        components: set[str] = set()

        # Build web component regex from config pattern
        web_component_re: re.Pattern[str] | None = None
        if config.component_tag_pattern is not None:
            # Strip leading '<' if present to get the prefix
            prefix = config.component_tag_pattern
            if prefix.startswith("<"):
                prefix = prefix[1:]
            web_component_re = re.compile(r"<(" + re.escape(prefix) + r"[\w-]+)")

        # React import pattern for @shopify/polaris — supports multi-line imports
        polaris_import_re = re.compile(
            r"import\s*\{([\s\S]+?)\}\s*from\s*[\"']@shopify/polaris[\"']"
        )

        source_files = self._source_files
        if source_files is None:
            source_files = read_source_files(config)
        for content in source_files.values():
            # Web component detection
            if web_component_re is not None:
                for match in web_component_re.finditer(content):
                    components.add(match.group(1))

            # React import detection
            for match in polaris_import_re.finditer(content):
                imports_str = match.group(1)
                for name in imports_str.split(","):
                    name = name.strip()
                    if name:
                        components.add(name)

        surface.ui_components = sorted(components)
        return surface
