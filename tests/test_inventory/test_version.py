"""Tests for the VersionExtractor."""

from pathlib import Path

import pytest

from scry.inventory.version import VersionExtractor
from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


class TestVersionExtractor:
    def test_extracts_api_version_from_toml(
        self, inventory_project_root: ProjectConfig
    ) -> None:
        """Extracts api_version from nested TOML path webhooks.api_version."""
        surface = AppSurface(api_version="")
        extractor = VersionExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert result.api_version == "2024-10"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when source file does not exist."""
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="nonexistent.toml:key",
            source_patterns=[],
        )
        surface = AppSurface(api_version="")
        extractor = VersionExtractor()
        with pytest.raises(FileNotFoundError):
            extractor.extract(config, surface)

    def test_bad_key_path_raises(self, tmp_path: Path) -> None:
        """Raises KeyError when dotted key path does not resolve."""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[webhooks]\napi_version = "2024-10"\n')
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="config.toml:nonexistent.key",
            source_patterns=[],
        )
        surface = AppSurface(api_version="")
        extractor = VersionExtractor()
        with pytest.raises(KeyError):
            extractor.extract(config, surface)

    def test_yaml_config_supported(self, tmp_path: Path) -> None:
        """Extracts version from a YAML config file."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("webhooks:\n  api_version: '2025-01'\n")
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="config.yaml:webhooks.api_version",
            source_patterns=[],
        )
        surface = AppSurface(api_version="")
        extractor = VersionExtractor()
        result = extractor.extract(config, surface)
        assert result.api_version == "2025-01"

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        """Raises ValueError for unsupported config file formats."""
        json_file = tmp_path / "config.json"
        json_file.write_text('{"version": "2024-10"}')
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="config.json:version",
            source_patterns=[],
        )
        surface = AppSurface(api_version="")
        extractor = VersionExtractor()
        with pytest.raises(ValueError, match="Unsupported config file format"):
            extractor.extract(config, surface)

    def test_missing_colon_in_source_raises(self, tmp_path: Path) -> None:
        """Raises ValueError when api_version_source has no colon separator."""
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="config.toml",
            source_patterns=[],
        )
        surface = AppSurface(api_version="")
        extractor = VersionExtractor()
        with pytest.raises(ValueError, match="Invalid api_version_source format"):
            extractor.extract(config, surface)
