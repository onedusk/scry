"""Collector for changelog pages via Firecrawl scraping."""

from __future__ import annotations

import logging
import os

from firecrawl import FirecrawlApp  # type: ignore[import-untyped]

from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource

logger = logging.getLogger(__name__)


def _classify_markdown(content: str) -> tuple[ChangeCategory, bool]:
    """Classify changelog content by scanning for keywords.

    Returns (category, action_required).
    """
    lower = content.lower()
    action_required = "action required" in lower

    if "breaking" in lower:
        category = ChangeCategory.BREAKING
    elif "deprecat" in lower:
        category = ChangeCategory.DEPRECATION
    else:
        category = ChangeCategory.PLATFORM

    return category, action_required


class ChangelogCollector:
    """Scrapes changelog pages via Firecrawl for change detection."""

    def collect(self, config: ProjectConfig) -> list[ChangeRecord]:
        """Scrape configured changelog URLs and produce ChangeRecords."""
        if not config.changelog_page_urls:
            return []

        api_key = os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            logger.warning("FIRECRAWL_API_KEY not set, skipping changelog scrape")
            return []

        app = FirecrawlApp(api_key=api_key)  # pyright: ignore[reportUnknownVariableType]
        records: list[ChangeRecord] = []

        for url in config.changelog_page_urls:
            try:
                doc = app.scrape(url, formats=["markdown"])  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

                markdown: str = doc.markdown or ""  # pyright: ignore[reportUnknownMemberType]
                title: str = ""
                source_url: str = url
                if doc.metadata:  # pyright: ignore[reportUnknownMemberType]
                    title = doc.metadata.title or ""  # pyright: ignore[reportUnknownMemberType]
                    source_url = doc.metadata.source_url or url  # pyright: ignore[reportUnknownMemberType]

                if not markdown:
                    continue

                category, action_required = _classify_markdown(markdown)

                records.append(
                    ChangeRecord(
                        source=ChangeSource.CHANGELOG,
                        title=title or f"Changelog: {url}",
                        description=markdown[:500],
                        category=category,
                        action_required=action_required,
                        url=source_url,
                    )
                )
            except Exception:
                logger.warning("Failed to scrape %s", url, exc_info=True)

        return records
