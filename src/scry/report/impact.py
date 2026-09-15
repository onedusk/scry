"""Impact report generator — produces a markdown impact assessment."""

import re
from datetime import UTC, datetime
from pathlib import Path

import scry
from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, SchemaChangeType, Severity
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface
from scry.models.triage import TriageResult
from scry.report._format import item_description, item_title, md_cell, severity_rank
from scry.report.summary import generate_summary

_DEPRECATION_CHANGE_TYPES = {
    SchemaChangeType.FIELD_DEPRECATED,
    SchemaChangeType.ENUM_VALUE_DEPRECATED,
}


def _is_deprecation(item: ImpactItem) -> bool:
    if isinstance(item.change, SchemaChange):
        return item.change.change_type in _DEPRECATION_CHANGE_TYPES
    return item.change.category == ChangeCategory.DEPRECATION


def _item_source(item: ImpactItem) -> str:
    if isinstance(item.change, SchemaChange):
        return "schema diff"
    return item.change.url or item.change.source.value


_VERSION_PREFIX = re.compile(r"^[^0-9]*")


def _parse_sdk_title(title: str) -> tuple[str, str, str]:
    """Split a RegistryCollector title "pkg: current → latest" into its parts.

    Returns the full title and empty version strings when the title does not
    match that format.
    """
    package, _, versions = title.partition(": ")
    current, arrow, latest = versions.partition(" → ")
    if not arrow:
        return title, "", ""
    return package, current, latest


def _update_type(current: str, latest: str) -> str:
    """Classify a version bump as major or minor/patch by major component."""
    cur_major = _VERSION_PREFIX.sub("", current).split(".")[0]
    lat_major = _VERSION_PREFIX.sub("", latest).split(".")[0]
    if not cur_major.isdigit() or not lat_major.isdigit():
        return "unknown"
    return "major" if cur_major != lat_major else "minor/patch"


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _render_item(item: ImpactItem, config: ProjectConfig) -> list[str]:
    """Render one impact as a headed block with source, deadline, files, and action."""
    files_str = (
        ", ".join(_relative_path(f, config.root) for f in item.affected_files)
        if item.affected_files
        else "None identified"
    )
    features_str = (
        ", ".join(item.affected_features) if item.affected_features else "None identified"
    )
    return [
        f"### [{item.severity.value.upper()}] {item_title(item)}",
        "",
        f"- **Source**: {_item_source(item)}",
        f"- **Deadline**: {item.deadline or 'N/A'}",
        f"- **Affected files**: {files_str}",
        f"- **Affected features**: {features_str}",
        f"- **What changed**: {item_description(item)}",
        f"- **Suggested action**: {item.suggested_action or 'Review required'}",
        "",
    ]


def generate_impact_report(
    impacts: list[ImpactItem],
    config: ProjectConfig,
    surface: AppSurface,
    next_api_version: str | None = None,
    triage: TriageResult | None = None,
) -> str:
    """Generate a full markdown impact report."""
    now = datetime.now(tz=UTC)
    lines: list[str] = []

    # Header
    lines.append(f"# API Change Impact Report -- {now.strftime('%B %Y')}")
    lines.append("")
    lines.append(f"> Generated: {now.isoformat()}")
    lines.append(f"> {config.name} API version: {surface.api_version}")
    if next_api_version:
        lines.append(f"> Next {config.platform} version: {next_api_version}")
    lines.append(f"> scry version: {scry.__version__}")
    if triage is not None:
        lines.append(
            f"> Triage: {triage.model}, {len(triage.judgments)} entries judged "
            f"({triage.input_tokens} input, {triage.cache_read_input_tokens} cached, "
            f"{triage.output_tokens} output tokens)"
        )
    lines.append("")

    # Summary. Entries that touch nothing in the inventory are counted, not listed.
    lines.append("## Summary")
    lines.append("")
    lines.append(generate_summary(impacts, config))
    omitted = sum(1 for i in impacts if i.severity == Severity.INFO)
    if omitted:
        where = "raw-changes.json and triage.json" if triage is not None else "raw-changes.json"
        lines.append(
            f"{omitted} entries do not touch the inventory and are listed only in {where}."
        )
    lines.append("")

    # Action Required
    action_items = sorted(
        [i for i in impacts if i.severity in (Severity.CRITICAL, Severity.HIGH)],
        key=lambda i: severity_rank(i.severity),
        reverse=True,
    )
    if action_items:
        lines.append("## Action Required")
        lines.append("")
        for item in action_items:
            lines.extend(_render_item(item, config))

    # Review
    review_items = [i for i in impacts if i.severity == Severity.MEDIUM]
    if review_items:
        lines.append("## Review")
        lines.append("")
        for item in review_items:
            lines.extend(_render_item(item, config))

    # Deprecation Tracker
    deprecation_items = [i for i in impacts if _is_deprecation(i) and i.severity != Severity.INFO]
    unused_deprecations = sum(
        1 for i in impacts if _is_deprecation(i) and i.severity == Severity.INFO
    )
    if deprecation_items:
        lines.append("## Deprecation Tracker")
        lines.append("")
        lines.append("| Field/Feature | Deprecated In | Removed In | Project Uses? | Status |")
        lines.append("|---|---|---|---|---|")
        for item in deprecation_items:
            change = item.change
            if isinstance(change, SchemaChange):
                # Schema deprecations are cross-referenced, so usage is definite.
                title = md_cell(change.path)
                deprecated_in = next_api_version or "Unknown"
                removed_in = "TBD"
                uses = "Yes" if item.affected_files else "No"
            else:
                title = md_cell(change.title)
                deprecated_in = change.version or "Unknown"
                removed_in = str(change.sunset_date) if change.sunset_date else "TBD"
                uses = "Yes" if item.affected_files else "Unknown"
            status = item.severity.value.upper()
            lines.append(f"| {title} | {deprecated_in} | {removed_in} | {uses} | {status} |")
        if unused_deprecations:
            plural = "s" if unused_deprecations != 1 else ""
            lines.append("")
            lines.append(
                f"{unused_deprecations} other deprecation{plural} do not touch the inventory."
            )
        lines.append("")

    # SDK Updates
    sdk_items = [
        i
        for i in impacts
        if isinstance(i.change, ChangeRecord) and i.change.category == ChangeCategory.SDK
    ]
    if sdk_items:
        lines.append("## SDK Updates")
        lines.append("")
        lines.append("| Package | Current | Latest | Type | Notes |")
        lines.append("|---|---|---|---|---|")
        for item in sdk_items:
            change = item.change
            if not isinstance(change, ChangeRecord):
                continue
            # Title format from RegistryCollector: "pkg: current → latest"
            package, current, latest = _parse_sdk_title(change.title)
            latest = latest or change.version or ""
            update_type = _update_type(current, latest)
            lines.append(
                f"| {md_cell(package)} | {current or '-'} | {latest or '-'} "
                f"| {update_type} | {md_cell(change.description)} |"
            )
        lines.append("")

    # Low Priority: optional changes, one line each (SDK bumps already have their table)
    low_items = [
        i
        for i in impacts
        if i.severity == Severity.LOW
        and not (isinstance(i.change, ChangeRecord) and i.change.category == ChangeCategory.SDK)
    ]
    if low_items:
        lines.append("## Low Priority")
        lines.append("")
        for item in low_items:
            lines.append(f"- {item_title(item)}: {item_description(item, limit=200)}")
        lines.append("")

    return "\n".join(lines)
