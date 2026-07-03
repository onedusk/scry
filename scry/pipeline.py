"""Pipeline orchestrator — wires stages, manages execution order."""

import logging

from scry import collect, inventory, report, store
from scry.diff import diff_schemas, match_changelog_to_surface, score_severity
from scry.models.changes import SchemaChange
from scry.models.config import ProjectConfig
from scry.models.enums import Criticality, Severity
from scry.models.impact import ImpactItem
from scry.models.results import CollectResult, DiffResult, PipelineResult, ReportResult
from scry.models.surface import AppSurface

logger = logging.getLogger(__name__)


def run_collect(config: ProjectConfig) -> CollectResult:
    """Run the collect stage independently."""
    logger.info("Starting collect stage")
    return collect.run_all_collectors(config)


def run_inventory(config: ProjectConfig) -> AppSurface:
    """Run the inventory stage independently."""
    logger.info("Starting inventory stage")
    return inventory.run_all_extractors(config)


def run_diff(
    collect_result: CollectResult,
    surface: AppSurface,
    config: ProjectConfig,
) -> DiffResult:
    """Run the diff stage independently."""
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
    # Load state for dedup
    state = store.load_state(config)

    failed_stages: list[str] = []

    # Collect
    raw_change_count = 0
    try:
        collect_result = run_collect(config)
        raw_change_count = len(collect_result.changes)
        collect_result.changes = store.filter_new_changes(collect_result.changes, state)
        logger.info(
            "Collected %d raw, %d new (after dedup)",
            raw_change_count,
            len(collect_result.changes),
        )
    except Exception:
        logger.warning("Collect stage failed", exc_info=True)
        collect_result = CollectResult()
        failed_stages.append("collect")

    # Inventory
    try:
        surface = run_inventory(config)
    except Exception:
        logger.warning("Inventory stage failed", exc_info=True)
        surface = AppSurface(api_version="unknown")
        failed_stages.append("inventory")

    # Diff
    try:
        diff_result = run_diff(collect_result, surface, config)
    except Exception:
        logger.warning("Diff stage failed", exc_info=True)
        diff_result = DiffResult()
        failed_stages.append("diff")

    # Report — skip if no new changes to avoid overwriting a previous report
    report_result = ReportResult()
    if collect_result.changes or diff_result.impacts:
        try:
            report_result = report.generate_all_reports(
                diff_result.impacts, collect_result.changes, config, surface, collect_result
            )
        except Exception:
            logger.warning("Report stage failed", exc_info=True)
            report_result = ReportResult()
            failed_stages.append("report")
    else:
        logger.info("No new changes — skipping report generation")

    # Update state
    report_path = ""
    if report_result.impact_report_path:
        try:
            report_path = str(report_result.impact_report_path.relative_to(config.root))
        except ValueError:
            report_path = str(report_result.impact_report_path)
    state = store.record_run(
        state,
        config,
        collect_result.changes,
        changes_detected=raw_change_count,
        impacts_found=len(diff_result.impacts),
        report_path=report_path,
    )
    store.save_state(state, config)

    return PipelineResult(
        config=config,
        collect=collect_result,
        surface=surface,
        diff=diff_result,
        report=report_result,
        failed_stages=failed_stages,
    )
