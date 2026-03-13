"""Collector for RSS changelog feeds."""

from __future__ import annotations

import logging
import re
import ssl
from calendar import timegm
from datetime import datetime, timezone
from typing import Any
from urllib.request import HTTPSHandler

import certifi
import feedparser  # type: ignore[import-untyped]

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_HTTPS_HANDLER = HTTPSHandler(context=_SSL_CONTEXT)

from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^\d{4}-\d{2}$")


def _classify_entry(
    tags: list[dict[str, Any]],
) -> tuple[ChangeCategory, bool, str | None]:
    """Classify an RSS entry by its category tags.

    Returns (category, action_required, version).
    """
    terms: list[str] = [tag.get("term", "") for tag in tags]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]

    action_required = "Action Required" in terms
    version: str | None = None

    category = ChangeCategory.PLATFORM  # default
    if "Breaking API Change" in terms:
        category = ChangeCategory.BREAKING
    elif "Deprecation Announcement" in terms:
        category = ChangeCategory.DEPRECATION
    elif "New" in terms:
        category = ChangeCategory.FEATURE

    for term in terms:
        if _VERSION_RE.match(term):
            version = term
            break

    return category, action_required, version


class RssCollector:
    """Collects change records from an RSS changelog feed."""

    def collect(self, config: ProjectConfig) -> list[ChangeRecord]:
        """Fetch and parse the RSS feed, returning ChangeRecord instances."""
        if config.changelog_rss_url is None:
            return []

        d: Any = feedparser.parse(config.changelog_rss_url, handlers=[_HTTPS_HANDLER])  # pyright: ignore[reportUnknownMemberType]

        if d.bozo:
            logger.warning(
                "RSS feed parsing had issues: %s",
                d.get("bozo_exception", "unknown"),
            )

        records: list[ChangeRecord] = []
        entries: list[Any] = d.entries
        for entry in entries:
            tags: list[dict[str, Any]] = entry.get("tags", [])
            category, action_required, version = _classify_entry(tags)

            # Convert published_parsed (time.struct_time) to datetime
            detected_at = datetime.now(tz=timezone.utc)
            published: Any = entry.get("published_parsed")
            if published is not None:
                detected_at = datetime.fromtimestamp(
                    timegm(published),
                    tz=timezone.utc,
                )

            title: str = entry.get("title", "")
            description: str = entry.get("summary", "")
            link: str | None = entry.get("link")

            records.append(
                ChangeRecord(
                    source=ChangeSource.RSS,
                    title=title,
                    description=description,
                    category=category,
                    action_required=action_required,
                    version=version,
                    url=link,
                    detected_at=detected_at,
                )
            )

        return records
