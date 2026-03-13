"""Collector for Polaris component changelog via Firecrawl scraping."""

from __future__ import annotations

import logging
import os

from firecrawl import FirecrawlApp  # type: ignore[import-untyped]

from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource

logger = logging.getLogger(__name__)

_POLARIS_URLS = [
    "https://polaris.shopify.com/whats-new",
]


def _classify_polaris_content(content: str) -> ChangeCategory:
    """Classify Polaris changelog content by scanning for keywords."""
    lower = content.lower()
    if "removed" in lower or "breaking" in lower:
        return ChangeCategory.BREAKING
    if "deprecat" in lower:
        return ChangeCategory.DEPRECATION
    if "new" in lower or "added" in lower:
        return ChangeCategory.FEATURE
    return ChangeCategory.PLATFORM


class PolarisCollector:
    """Scrapes Polaris changelog pages for component change detection."""

    def collect(self, config: ProjectConfig) -> list[ChangeRecord]:
        """Scrape Polaris pages and produce ChangeRecords."""
        api_key = os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            logger.warning("FIRECRAWL_API_KEY not set, skipping Polaris scrape")
            return []

        app = FirecrawlApp(api_key=api_key)  # pyright: ignore[reportUnknownVariableType]
        records: list[ChangeRecord] = []

        for url in _POLARIS_URLS:
            try:
                doc = app.scrape(url, formats=["markdown"])  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

                markdown: str = doc.markdown or ""  # pyright: ignore[reportUnknownMemberType]
                if not markdown:
                    continue

                title: str = ""
                source_url: str = url
                if doc.metadata:  # pyright: ignore[reportUnknownMemberType]
                    title = doc.metadata.title or ""  # pyright: ignore[reportUnknownMemberType]
                    source_url = doc.metadata.source_url or url  # pyright: ignore[reportUnknownMemberType]

                category = _classify_polaris_content(markdown)

                records.append(
                    ChangeRecord(
                        source=ChangeSource.POLARIS,
                        title=title or f"Polaris: {url}",
                        description=markdown[:500],
                        category=category,
                        url=source_url,
                    )
                )
            except Exception:
                logger.warning("Failed to scrape Polaris page %s", url, exc_info=True)

        return records
