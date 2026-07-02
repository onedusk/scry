"""Tests for the PolarisCollector."""

from pathlib import Path
from typing import Any

from firecrawl.v2.client import FirecrawlClient  # type: ignore[import-untyped]

from scry.collect.polaris import PolarisCollector, _classify_polaris_content
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource


def _make_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test",
        root=tmp_path,
        platform="shopify",
        api_version_source="x:y",
        source_patterns=[],
    )


class _MockDocument:
    """Minimal mock for firecrawl Document."""

    def __init__(
        self,
        markdown: str,
        title: str = "Polaris Page",
        source_url: str = "https://polaris.shopify.com",
    ) -> None:
        self.markdown = markdown
        self.metadata = _MockMetadata(title, source_url)


class _MockMetadata:
    def __init__(self, title: str, source_url: str) -> None:
        self.title = title
        self.source_url = source_url


class TestPolarisCollector:
    def test_produces_change_record(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Produces a ChangeRecord from a mocked Polaris page."""
        config = _make_config(tmp_path)
        monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

        def mock_scrape(self: Any, url: str, **kwargs: Any) -> _MockDocument:
            return _MockDocument("New component added to Polaris.")

        monkeypatch.setattr(FirecrawlClient, "scrape", mock_scrape)
        records = PolarisCollector().collect(config)
        assert len(records) >= 1
        assert records[0].source == ChangeSource.POLARIS

    def test_returns_empty_without_api_key(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Returns empty list when FIRECRAWL_API_KEY is not set."""
        config = _make_config(tmp_path)
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        records = PolarisCollector().collect(config)
        assert records == []

    def test_handles_scrape_failure(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Scrape failure is handled gracefully."""
        config = _make_config(tmp_path)
        monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

        def mock_scrape(self: Any, url: str, **kwargs: Any) -> None:
            raise RuntimeError("scrape failed")

        monkeypatch.setattr(FirecrawlClient, "scrape", mock_scrape)
        records = PolarisCollector().collect(config)
        assert records == []


class TestClassifyPolarisContent:
    def test_breaking(self) -> None:
        assert _classify_polaris_content("Component removed in v13.") == ChangeCategory.BREAKING

    def test_deprecation(self) -> None:
        assert (
            _classify_polaris_content("Badge deprecated, use StatusBadge.")
            == ChangeCategory.DEPRECATION
        )

    def test_feature(self) -> None:
        assert _classify_polaris_content("New Tooltip component added.") == ChangeCategory.FEATURE

    def test_default(self) -> None:
        assert _classify_polaris_content("Minor style updates.") == ChangeCategory.PLATFORM
