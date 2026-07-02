"""Impact report generator — produces a markdown impact assessment."""

from datetime import datetime, timezone
from pathlib import Path

import scry
from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, Severity
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface
from scry.report.summary import generate_summary


def _item_title(item: ImpactItem) -> str:
    if isinstance(item.change, SchemaChange):
        return item.change.path
    return item.change.title


def _item_description(item: ImpactItem) -> str:
    if isinstance(item.change, SchemaChange):
        return item.change.message
    return item.change.description


def _item_source(item: ImpactItem) -> str:
    if isinstance(item.change, SchemaChange):
        return "schema diff"
    return item.change.url or item.change.source.value


def _md_cell(value: str) -> str:
    """Escape pipe characters for markdown table cells."""
    return value.replace("|", "\\|")


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _severity_rank(severity: Severity) -> int:
    return {
        Severity.CRITICAL: 4,
        Severity.HIGH: 3,
        Severity.MEDIUM: 2,
        Severity.LOW: 1,
        Severity.INFO: 0,
    }[severity]


def generate_impact_report(
    impacts: list[ImpactItem],
    config: ProjectConfig,
    surface: AppSurface,
    next_api_version: str | None = None,
) -> str:
    """Generate a full markdown impact report."""
    now = datetime.now(tz=timezone.utc)
    lines: list[str] = []

    # Header
    lines.append(f"# API Change Impact Report -- {now.strftime('%B %Y')}")
    lines.append("")
    lines.append(f"> Generated: {now.isoformat()}")
    lines.append(f"> {config.name} API version: {surface.api_version}")
    if next_api_version:
        lines.append(f"> Next {config.platform} version: {next_api_version}")
    lines.append(f"> scry version: {scry.__version__}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(generate_summary(impacts, config))
    lines.append("")

    # Action Required
    action_items = sorted(
        [i for i in impacts if i.severity in (Severity.CRITICAL, Severity.HIGH)],
        key=lambda i: _severity_rank(i.severity),
        reverse=True,
    )
    if action_items:
        lines.append("## Action Required")
        lines.append("")
        for item in action_items:
            lines.append(f"### [{item.severity.value.upper()}] {_item_title(item)}")
            lines.append("")
            lines.append(f"- **Source**: {_item_source(item)}")
            lines.append(f"- **Deadline**: {item.deadline or 'N/A'}")
            files_str = (
                ", ".join(_relative_path(f, config.root) for f in item.affected_files)
                if item.affected_files
                else "None identified"
            )
            lines.append(f"- **Affected files**: {files_str}")
            features_str = (
                ", ".join(item.affected_features) if item.affected_features else "None identified"
            )
            lines.append(f"- **Affected features**: {features_str}")
            lines.append(f"- **What changed**: {_item_description(item)}")
            lines.append(f"- **Suggested action**: {item.suggested_action or 'Review required'}")
            lines.append("")

    # Deprecation Tracker
    deprecation_items = [
        i
        for i in impacts
        if isinstance(i.change, ChangeRecord) and i.change.category == ChangeCategory.DEPRECATION
    ]
    if deprecation_items:
        lines.append("## Deprecation Tracker")
        lines.append("")
        lines.append("| Field/Feature | Deprecated In | Removed In | Project Uses? | Status |")
        lines.append("|---|---|---|---|---|")
        for item in deprecation_items:
            change = item.change
            if not isinstance(change, ChangeRecord):
                continue
            title = _md_cell(change.title)
            deprecated_in = change.version or "Unknown"
            removed_in = str(change.sunset_date) if change.sunset_date else "TBD"
            uses = "Yes" if item.affected_files else "Unknown"
            status = item.severity.value.upper()
            lines.append(f"| {title} | {deprecated_in} | {removed_in} | {uses} | {status} |")
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
            # Title format from diff_dependencies: "pkg current → latest"
            parts = change.title.split(" ")
            package = parts[0] if parts else change.title
            version_info = change.version or ""
            # diff_dependencies: MEDIUM = major bump, LOW = minor/patch
            update_type = "major" if item.severity == Severity.MEDIUM else "minor/patch"
            lines.append(
                f"| {package} | - | {version_info} | {update_type} | {_md_cell(change.description)} |"
            )
        lines.append("")

    # Informational
    info_items = [i for i in impacts if i.severity in (Severity.LOW, Severity.INFO)]
    if info_items:
        lines.append("## Informational")
        lines.append("")
        for item in info_items:
            lines.append(f"- {_item_title(item)}: {_item_description(item)}")
        lines.append("")

    return "\n".join(lines)
