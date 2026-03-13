"""Tests for scry config loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from scry.config import find_manifest, load_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestFindManifest:
    def test_finds_yaml(self, tmp_path: Path) -> None:
        """find_manifest locates scry.yaml in a directory."""
        manifest = tmp_path / "scry.yaml"
        manifest.write_text("name: test\n")
        result = find_manifest(tmp_path)
        assert result == manifest

    def test_finds_yml(self, tmp_path: Path) -> None:
        """find_manifest locates scry.yml if scry.yaml doesn't exist."""
        manifest = tmp_path / "scry.yml"
        manifest.write_text("name: test\n")
        result = find_manifest(tmp_path)
        assert result == manifest

    def test_finds_toml(self, tmp_path: Path) -> None:
        """find_manifest locates scry.toml."""
        manifest = tmp_path / "scry.toml"
        manifest.write_text('name = "test"\n')
        result = find_manifest(tmp_path)
        assert result == manifest

    def test_prefers_yaml_over_toml(self, tmp_path: Path) -> None:
        """find_manifest prefers scry.yaml when both exist."""
        (tmp_path / "scry.yaml").write_text("name: test\n")
        (tmp_path / "scry.toml").write_text('name = "test"\n')
        result = find_manifest(tmp_path)
        assert result.name == "scry.yaml"

    def test_raises_when_not_found(self, tmp_path: Path) -> None:
        """find_manifest raises FileNotFoundError in empty directory."""
        with pytest.raises(FileNotFoundError, match="No scry manifest found"):
            find_manifest(tmp_path)


class TestLoadConfig:
    def test_load_yaml(self) -> None:
        """load_config parses a valid YAML manifest."""
        config = load_config(FIXTURES_DIR / "sample_manifest.yaml")
        assert config.name == "diode"
        assert config.platform == "shopify"
        assert len(config.escalation_rules) == 3
        assert config.escalation_rules[0].floor == "critical"

    def test_load_toml(self) -> None:
        """load_config parses a valid TOML manifest."""
        config = load_config(FIXTURES_DIR / "sample_manifest.toml")
        assert config.name == "diode"
        assert config.platform == "shopify"
        assert len(config.escalation_rules) == 3
        assert config.source_patterns == ["app/**/*.ts", "app/**/*.tsx"]

    def test_invalid_yaml_raises_validation_error(self) -> None:
        """load_config raises ValidationError for manifest missing required fields."""
        with pytest.raises(ValidationError):
            load_config(FIXTURES_DIR / "sample_manifest_invalid.yaml")

    def test_unsupported_format_raises_value_error(self, tmp_path: Path) -> None:
        """load_config raises ValueError for unsupported file extensions."""
        bad_file = tmp_path / "manifest.json"
        bad_file.write_text("{}")
        with pytest.raises(ValueError, match="Unsupported manifest format"):
            load_config(bad_file)
