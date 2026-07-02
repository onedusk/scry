"""Report generator — impact reports, change plans, summaries, and raw exports."""

from datetime import datetime

from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.enums import Severity
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface
from scry.pipeline import CollectResult, ReportResult
from scry.report.change_plan import generate_change_plan
from scry.report.impact import generate_impact_report
from scry.report.summary import (
    export_raw_changes,
    export_raw_changes_json,
    generate_cli_summary,
    generate_summary,
)

__all__ = [
    "export_raw_changes",
    "export_raw_changes_json",
    "generate_all_reports",
    "generate_change_plan",
    "generate_cli_summary",
    "generate_impact_report",
    "generate_summary",
    "severity_icon",
]

_SEVERITY_ICONS: dict[Severity, str] = {
    Severity.CRITICAL: "\U0001f534",
    Severity.HIGH: "\U0001f7e0",
    Severity.MEDIUM: "\U0001f7e1",
    Severity.LOW: "\U0001f535",
    Severity.INFO: "\u26aa",
}


def severity_icon(severity: Severity) -> str:
    """Map a severity level to its display icon."""
    return _SEVERITY_ICONS.get(severity, "\u26aa")


def generate_all_reports(
    impacts: list[ImpactItem],
    changes: list[ChangeRecord],
    config: ProjectConfig,
    surface: AppSurface,
    collect_result: CollectResult | None = None,
) -> ReportResult:
    """Orchestrate all report generation and write files to the report directory."""
    report_dir = config.root / config.report_dir / datetime.now().strftime("%Y-%m")
    report_dir.mkdir(parents=True, exist_ok=True)

    next_api_version = collect_result.next_api_version if collect_result else None

    # Impact report
    impact_md = generate_impact_report(impacts, config, surface, next_api_version)
    impact_path = report_dir / "impact-report.md"
    impact_path.write_text(impact_md)

    # Change plan (only if critical/high items exist)
    change_plan_path = None
    has_action_required = any(i.severity in (Severity.CRITICAL, Severity.HIGH) for i in impacts)
    if has_action_required:
        plan_md = generate_change_plan(impacts, config)
        change_plan_path = report_dir / "change-plan-draft.md"
        change_plan_path.write_text(plan_md)

    # Raw changes
    raw_path = report_dir / "raw-changes.json"
    export_raw_changes(changes, raw_path)

    return ReportResult(
        impact_report_path=impact_path,
        change_plan_path=change_plan_path,
        raw_changes_path=raw_path,
    )
