"""Extractor for tracked project dependencies."""

from __future__ import annotations

from scry.manifests import read_project_dependencies
from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


class DependencyExtractor:
    """Extracts dependencies filtered by configured prefixes."""

    def extract(self, config: ProjectConfig, surface: AppSurface) -> AppSurface:
        """Auto-detect dependency manifest and extract matching packages."""
        if not config.dependency_prefixes:
            return surface

        # Try each manifest type — collect from all that exist
        all_deps: dict[str, str] = {}
        for deps in read_project_dependencies(config.root).values():
            all_deps.update(deps)

        # Filter by configured prefixes
        filtered = {
            name: version
            for name, version in all_deps.items()
            if any(name.startswith(prefix) for prefix in config.dependency_prefixes)
        }

        surface.dependencies = filtered
        return surface
