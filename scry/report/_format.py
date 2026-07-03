"""Shared render helpers for report generators."""

from scry.models.changes import SchemaChange
from scry.models.enums import Severity
from scry.models.impact import ImpactItem


def severity_rank(severity: Severity) -> int:
    return {
        Severity.CRITICAL: 4,
        Severity.HIGH: 3,
        Severity.MEDIUM: 2,
        Severity.LOW: 1,
        Severity.INFO: 0,
    }[severity]


def item_title(item: ImpactItem) -> str:
    if isinstance(item.change, SchemaChange):
        return item.change.path
    return item.change.title


def item_description(item: ImpactItem) -> str:
    if isinstance(item.change, SchemaChange):
        return item.change.message
    return item.change.description


def md_cell(value: str) -> str:
    """Escape pipe characters for markdown table cells."""
    return value.replace("|", "\\|")
