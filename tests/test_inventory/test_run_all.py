"""Tests for run_all_extractors integration."""

from pathlib import Path

import pytest

from scry.inventory import run_all_extractors
from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


class TestRunAllExtractors:
    def test_populates_all_fields(self, inventory_project_root: ProjectConfig) -> None:
        """run_all_extractors returns a surface with all fields populated."""
        surface = run_all_extractors(inventory_project_root)
        assert surface.api_version == "2024-10"
        assert len(surface.graphql_operations) >= 2
        assert len(surface.webhook_topics) >= 2
        assert len(surface.dependencies) >= 1
        assert len(surface.ui_components) >= 1
        assert len(surface.scopes) >= 1

    def test_returns_app_surface(self, inventory_project_root: ProjectConfig) -> None:
        """run_all_extractors returns an AppSurface instance."""
        result = run_all_extractors(inventory_project_root)
        assert isinstance(result, AppSurface)

    def test_source_files_read_once(
        self, inventory_project_root: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each globbed source file is read exactly once across all extractors."""
        read_counts: dict[Path, int] = {}
        original_read_text = Path.read_text

        def counting_read_text(
            path: Path, encoding: str | None = None, errors: str | None = None
        ) -> str:
            read_counts[path] = read_counts.get(path, 0) + 1
            return original_read_text(path, encoding=encoding, errors=errors)

        monkeypatch.setattr(Path, "read_text", counting_read_text)
        surface = run_all_extractors(inventory_project_root)

        source_reads = {p: n for p, n in read_counts.items() if p.suffix in (".ts", ".tsx")}
        assert len(source_reads) == 2
        assert all(count == 1 for count in source_reads.values())
        # The shared contents still reach both source-scanning extractors.
        assert len(surface.graphql_operations) >= 2
        assert len(surface.ui_components) >= 1

    def test_with_minimal_config(self, tmp_path: Path) -> None:
        """Runs without error with minimal config (no webhook path, no components)."""
        # Create a minimal TOML for version extraction
        (tmp_path / "config.toml").write_text('[api]\nversion = "2025-01"\n')
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="config.toml:api.version",
            source_patterns=[],
        )
        surface = run_all_extractors(config)
        assert isinstance(surface, AppSurface)
        assert surface.api_version == "2025-01"
