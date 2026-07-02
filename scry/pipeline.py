"""Pipeline orchestrator — wires stages, manages execution order."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.config import ProjectConfig
from scry.models.enums import Criticality, Severity
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface

logger = logging.getLogger(__name__)


@dataclass
class CollectResult:
    """Output of the collect stage."""

    changes: list[ChangeRecord] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    old_schema_sdl: str | None = None  # Current version schema
    new_schema_sdl: str | None = None  # Next version schema
    current_api_version: str | None = None  # Version string for old schema
    next_api_version: str | None = None  # Version string for new schema


@dataclass
class DiffResult:
    """Output of the diff stage."""

    schema_changes: list[SchemaChange] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    impacts: list[ImpactItem] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]


@dataclass
class ReportResult:
    """Output of the report stage."""

    impact_report_path: Path | None = None
    change_plan_path: Path | None = None
    raw_changes_path: Path | None = None


@dataclass
class PipelineResult:
    """Aggregate result of a full pipeline run."""

    config: ProjectConfig
    collect: CollectResult
    surface: AppSurface
    diff: DiffResult
    report: ReportResult


def run_collect(config: ProjectConfig) -> CollectResult:
    """Run the collect stage independently."""
    from scry.collect import run_all_collectors

    logger.info("Starting collect stage")
    return run_all_collectors(config)


def run_inventory(config: ProjectConfig) -> AppSurface:
    """Run the inventory stage independently."""
    from scry.inventory import run_all_extractors

    logger.info("Starting inventory stage")
    return run_all_extractors(config)


def run_diff(
    collect_result: CollectResult,
    surface: AppSurface,
    config: ProjectConfig,
) -> DiffResult:
    """Run the diff stage independently."""
    from scry.diff import diff_schemas, match_changelog_to_surface, score_severity

    logger.info("Starting diff stage")

    schema_changes: list[SchemaChange] = []
    if collect_result.old_schema_sdl and collect_result.new_schema_sdl:
        schema_changes = diff_schemas(collect_result.old_schema_sdl, collect_result.new_schema_sdl)
        logger.info("Schema diff found %d changes", len(schema_changes))

    # Match changelog entries against project surface
    changelog_impacts = match_changelog_to_surface(collect_result.changes, surface)

    # Convert schema changes to ImpactItems
    schema_impacts = [
        ImpactItem(
            change=sc,
            severity=(Severity.HIGH if sc.criticality == Criticality.BREAKING else Severity.MEDIUM),
        )
        for sc in schema_changes
    ]

    all_impacts = changelog_impacts + schema_impacts

    # Apply escalation rules
    scored = score_severity(all_impacts, config.escalation_rules)

    return DiffResult(schema_changes=schema_changes, impacts=scored)


def run_pipeline(config: ProjectConfig) -> PipelineResult:
    """Execute the full pipeline: collect → inventory → diff → report."""
    from scry.report import generate_all_reports
    from scry.store import filter_new_changes, load_state, record_run, save_state

    # Load state for dedup
    state = load_state(config)

    # Collect
    raw_change_count = 0
    try:
        collect_result = run_collect(config)
        raw_change_count = len(collect_result.changes)
        collect_result.changes = filter_new_changes(collect_result.changes, state)
        logger.info(
            "Collected %d raw, %d new (after dedup)",
            raw_change_count,
            len(collect_result.changes),
        )
    except Exception:
        logger.warning("Collect stage failed", exc_info=True)
        collect_result = CollectResult()

    # Inventory
    try:
        surface = run_inventory(config)
    except Exception:
        logger.warning("Inventory stage failed", exc_info=True)
        surface = AppSurface(api_version="unknown")

    # Diff
    try:
        diff_result = run_diff(collect_result, surface, config)
    except Exception:
        logger.warning("Diff stage failed", exc_info=True)
        diff_result = DiffResult()

    # Report — skip if no new changes to avoid overwriting a previous report
    report_result = ReportResult()
    if collect_result.changes or diff_result.impacts:
        try:
            report_result = generate_all_reports(
                diff_result.impacts, collect_result.changes, config, surface, collect_result
            )
        except Exception:
            logger.warning("Report stage failed", exc_info=True)
            report_result = ReportResult()
    else:
        logger.info("No new changes — skipping report generation")

    # Update state
    report_path = ""
    if report_result.impact_report_path:
        try:
            report_path = str(report_result.impact_report_path.relative_to(config.root))
        except ValueError:
            report_path = str(report_result.impact_report_path)
    state = record_run(
        state,
        config,
        collect_result.changes,
        changes_detected=raw_change_count,
        impacts_found=len(diff_result.impacts),
        report_path=report_path,
    )
    save_state(state, config)

    return PipelineResult(
        config=config,
        collect=collect_result,
        surface=surface,
        diff=diff_result,
        report=report_result,
    )
