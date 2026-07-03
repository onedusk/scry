"""Changelog matcher — correlates ChangeRecords with a project's AppSurface."""

from pathlib import Path

from scry.models.changes import ChangeRecord
from scry.models.enums import ChangeCategory, Severity
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface

_CATEGORY_SEVERITY: dict[ChangeCategory, Severity] = {
    ChangeCategory.BREAKING: Severity.HIGH,
    ChangeCategory.DEPRECATION: Severity.MEDIUM,
    ChangeCategory.SDK: Severity.LOW,
    ChangeCategory.FEATURE: Severity.LOW,
    ChangeCategory.PLATFORM: Severity.INFO,
}


def match_changelog_to_surface(
    changes: list[ChangeRecord], surface: AppSurface
) -> list[ImpactItem]:
    """Match changelog entries against the project's inventory and score them."""
    items: list[ImpactItem] = []

    for change in changes:
        search_text = f"{change.title} {change.description}".lower()
        affected_files: list[Path] = []
        affected_features: list[str] = []
        matched = False

        # Check GraphQL operations (name and field matches)
        for op in surface.graphql_operations:
            if op.name.lower() in search_text or any(
                field.lower() in search_text for field in op.fields
            ):
                affected_files.append(op.file)
                affected_features.append(op.name)
                matched = True

        # Check webhook topics
        for topic in surface.webhook_topics:
            if topic.lower() in search_text:
                affected_features.append(topic)
                matched = True

        # Check dependencies
        for pkg in surface.dependencies:
            if pkg.lower() in search_text:
                affected_features.append(pkg)
                matched = True

        # Check UI components
        for comp in surface.ui_components:
            if comp.lower() in search_text:
                affected_features.append(comp)
                matched = True

        severity = _CATEGORY_SEVERITY.get(change.category, Severity.INFO)
        if not matched:
            severity = Severity.INFO

        items.append(
            ImpactItem(
                change=change,
                severity=severity,
                affected_files=affected_files,
                affected_features=affected_features,
            )
        )

    return items
