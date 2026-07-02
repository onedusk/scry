"""Tests for the RssCollector."""

from pathlib import Path
from typing import Any

import feedparser  # type: ignore[import-untyped]

from scry.collect.rss import RssCollector, _classify_entry
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _make_config(
    tmp_path: Path, rss_url: str | None = "https://example.com/feed.xml"
) -> ProjectConfig:
    return ProjectConfig(
        name="test",
        root=tmp_path,
        platform="shopify",
        api_version_source="x:y",
        source_patterns=[],
        changelog_rss_url=rss_url,
    )


def _parsed_feed() -> Any:
    """Parse the RSS fixture file."""
    xml = (FIXTURES_DIR / "rss_feed.xml").read_text()
    return feedparser.parse(xml)


class TestRssCollector:
    def test_parses_rss_entries(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Parses RSS fixture into ChangeRecord instances."""
        feed = _parsed_feed()
        monkeypatch.setattr("scry.collect.rss.feedparser.parse", lambda _url, **_kw: feed)

        config = _make_config(tmp_path)
        collector = RssCollector()
        records = collector.collect(config)
        assert len(records) == 5

    def test_maps_summary_to_description(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Maps entry.summary (not .description) to ChangeRecord.description."""
        feed = _parsed_feed()
        monkeypatch.setattr("scry.collect.rss.feedparser.parse", lambda _url, **_kw: feed)

        config = _make_config(tmp_path)
        records = RssCollector().collect(config)
        breaking = next(r for r in records if "productVariantsBulkUpdate" in r.title)
        assert "variants argument" in breaking.description

    def test_classifies_action_required(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Entries tagged 'Action Required' get action_required=True."""
        feed = _parsed_feed()
        monkeypatch.setattr("scry.collect.rss.feedparser.parse", lambda _url, **_kw: feed)

        records = RssCollector().collect(_make_config(tmp_path))
        action_records = [r for r in records if r.action_required]
        assert len(action_records) == 2

    def test_classifies_breaking_change(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Entries tagged 'Breaking API Change' get category=BREAKING."""
        feed = _parsed_feed()
        monkeypatch.setattr("scry.collect.rss.feedparser.parse", lambda _url, **_kw: feed)

        records = RssCollector().collect(_make_config(tmp_path))
        breaking = next(r for r in records if "productVariantsBulkUpdate" in r.title)
        assert breaking.category == ChangeCategory.BREAKING

    def test_extracts_version_from_tags(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Extracts YYYY-MM version from category tags."""
        feed = _parsed_feed()
        monkeypatch.setattr("scry.collect.rss.feedparser.parse", lambda _url, **_kw: feed)

        records = RssCollector().collect(_make_config(tmp_path))
        breaking = next(r for r in records if "productVariantsBulkUpdate" in r.title)
        assert breaking.version == "2026-07"

    def test_returns_empty_when_url_none(self, tmp_path: Path) -> None:
        """Returns empty list when changelog_rss_url is None."""
        config = _make_config(tmp_path, rss_url=None)
        records = RssCollector().collect(config)
        assert records == []

    def test_all_records_have_rss_source(self, tmp_path: Path, monkeypatch: Any) -> None:
        """All records have source=RSS."""
        feed = _parsed_feed()
        monkeypatch.setattr("scry.collect.rss.feedparser.parse", lambda _url, **_kw: feed)

        records = RssCollector().collect(_make_config(tmp_path))
        assert all(r.source == ChangeSource.RSS for r in records)


class TestClassifyEntry:
    def test_deprecation(self) -> None:
        tags = [{"term": "Deprecation Announcement"}]
        category, action_required, version = _classify_entry(tags)
        assert category == ChangeCategory.DEPRECATION
        assert not action_required

    def test_new_feature(self) -> None:
        tags = [{"term": "New"}]
        category, _, _ = _classify_entry(tags)
        assert category == ChangeCategory.FEATURE

    def test_default_platform(self) -> None:
        tags = [{"term": "Update"}]
        category, _, _ = _classify_entry(tags)
        assert category == ChangeCategory.PLATFORM

    def test_version_extraction(self) -> None:
        tags = [{"term": "2026-07"}, {"term": "Update"}]
        _, _, version = _classify_entry(tags)
        assert version == "2026-07"
