"""Tests for scry config loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from scry.config import check_firecrawl_env, find_manifest, load_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_BASE_MANIFEST = """\
name: test
root: .
platform: shopify
api_version_source: "x:y"
source_patterns: []
"""


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


class TestFirecrawlEnvCheck:
    def _write_manifest(self, tmp_path: Path, extra: str) -> Path:
        manifest = tmp_path / "scry.yaml"
        manifest.write_text(_BASE_MANIFEST + extra)
        return manifest

    def test_raises_without_key_when_changelog_pages_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_config fails fast when changelog_page_urls is set without the API key."""
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        manifest = self._write_manifest(
            tmp_path, 'changelog_page_urls: ["https://example.com/changelog"]\n'
        )
        with pytest.raises(ValueError, match="FIRECRAWL_API_KEY"):
            load_config(manifest)

    def test_raises_without_key_when_design_system_urls_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_config fails fast when design_system_urls is set without the API key."""
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        manifest = self._write_manifest(
            tmp_path, 'design_system_urls: ["https://example.com/whats-new"]\n'
        )
        with pytest.raises(ValueError, match="FIRECRAWL_API_KEY"):
            load_config(manifest)

    def test_loads_with_key_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_config succeeds when the API key is present."""
        monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")
        manifest = self._write_manifest(
            tmp_path, 'changelog_page_urls: ["https://example.com/changelog"]\n'
        )
        config = load_config(manifest)
        assert config.changelog_page_urls == ["https://example.com/changelog"]

    def test_loads_without_key_when_collectors_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No key needed when the Firecrawl-dependent collectors are disabled."""
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        manifest = self._write_manifest(
            tmp_path,
            'changelog_page_urls: ["https://example.com/changelog"]\n'
            'design_system_urls: ["https://example.com/whats-new"]\n'
            'disabled_collectors: ["changelog", "polaris"]\n',
        )
        config = load_config(manifest)
        assert config.disabled_collectors == ["changelog", "polaris"]

    def test_loads_without_key_when_no_firecrawl_sources(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No key needed when no Firecrawl-dependent fields are configured."""
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        manifest = self._write_manifest(tmp_path, "")
        config = load_config(manifest)
        assert config.changelog_page_urls == []

    def test_check_env_false_skips_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_config(check_env=False) parses without requiring the API key."""
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        manifest = self._write_manifest(
            tmp_path, 'changelog_page_urls: ["https://example.com/changelog"]\n'
        )
        config = load_config(manifest, check_env=False)
        with pytest.raises(ValueError, match="FIRECRAWL_API_KEY"):
            check_firecrawl_env(config)
