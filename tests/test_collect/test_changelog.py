"""Tests for the ChangelogCollector."""

import logging
from pathlib import Path
from typing import Any

import httpx
from firecrawl.v2.client import FirecrawlClient  # type: ignore[import-untyped]

from scry.collect.changelog import ChangelogCollector, _classify_markdown
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource


def _make_config(tmp_path: Path, urls: list[str] | None = None) -> ProjectConfig:
    return ProjectConfig(
        name="test",
        root=tmp_path,
        platform="shopify",
        api_version_source="x:y",
        source_patterns=[],
        changelog_page_urls=urls or ["https://example.com/changelog"],
    )


class _MockDocument:
    """Minimal mock for firecrawl Document."""

    def __init__(
        self, markdown: str, title: str = "Test Page", source_url: str = "https://example.com"
    ) -> None:
        self.markdown = markdown
        self.metadata = _MockMetadata(title, source_url)


class _MockMetadata:
    def __init__(self, title: str, source_url: str) -> None:
        self.title = title
        self.source_url = source_url


class TestChangelogCollector:
    def test_produces_change_record(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Produces a ChangeRecord from a mocked Firecrawl response."""
        config = _make_config(tmp_path)
        monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

        def mock_scrape(self: Any, url: str, **kwargs: Any) -> _MockDocument:
            return _MockDocument("Some changelog content about updates.")

        monkeypatch.setattr(FirecrawlClient, "scrape", mock_scrape)
        records = ChangelogCollector().collect(config)
        assert len(records) == 1
        assert records[0].source == ChangeSource.CHANGELOG
        assert records[0].title == "Test Page"

    def test_detects_action_required(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Detects 'Action Required' in markdown body."""
        config = _make_config(tmp_path)
        monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

        def mock_scrape(self: Any, url: str, **kwargs: Any) -> _MockDocument:
            return _MockDocument("This change is Action Required for all merchants.")

        monkeypatch.setattr(FirecrawlClient, "scrape", mock_scrape)
        records = ChangelogCollector().collect(config)
        assert records[0].action_required is True

    def test_returns_empty_without_urls(self, tmp_path: Path) -> None:
        """Returns empty list when changelog_page_urls is empty."""
        config = _make_config(tmp_path, urls=[])
        records = ChangelogCollector().collect(config)
        assert records == []

    def test_returns_empty_without_api_key(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Returns empty list when FIRECRAWL_API_KEY is not set."""
        config = _make_config(tmp_path)
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        records = ChangelogCollector().collect(config)
        assert records == []

    def test_handles_scrape_failure(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Scrape failure for a URL is handled gracefully."""
        config = _make_config(tmp_path)
        monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

        def mock_scrape(self: Any, url: str, **kwargs: Any) -> None:
            raise RuntimeError("scrape failed")

        monkeypatch.setattr(FirecrawlClient, "scrape", mock_scrape)
        records = ChangelogCollector().collect(config)
        assert records == []

    def test_handles_timeout(self, tmp_path: Path, monkeypatch: Any, caplog: Any) -> None:
        """Request timeout during scrape degrades to a warning and empty result."""
        config = _make_config(tmp_path)
        monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

        def mock_scrape(self: Any, url: str, **kwargs: Any) -> None:
            raise httpx.ConnectTimeout("timed out")

        monkeypatch.setattr(FirecrawlClient, "scrape", mock_scrape)
        with caplog.at_level(logging.WARNING):
            records = ChangelogCollector().collect(config)
        assert records == []
        assert "Failed to scrape" in caplog.text


class TestClassifyMarkdown:
    def test_breaking(self) -> None:
        category, action_required = _classify_markdown("This is a breaking change.")
        assert category == ChangeCategory.BREAKING
        assert not action_required

    def test_deprecation(self) -> None:
        category, _ = _classify_markdown("Field deprecated in next version.")
        assert category == ChangeCategory.DEPRECATION

    def test_action_required(self) -> None:
        _, action_required = _classify_markdown("Action Required: update your code.")
        assert action_required is True

    def test_default_platform(self) -> None:
        category, _ = _classify_markdown("Minor update to the platform.")
        assert category == ChangeCategory.PLATFORM
