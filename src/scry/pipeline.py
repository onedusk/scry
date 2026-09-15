"""Pipeline orchestrator — wires stages, manages execution order."""

import logging
import time

from scry import collect, inventory, report, store
from scry.diff import (
    diff_schemas,
    match_changelog_to_surface,
    match_schema_changes_to_surface,
    score_severity,
    triage_changelog_impacts,
)
from scry.models.changes import SchemaChange
from scry.models.config import ProjectConfig
from scry.models.impact import ImpactItem
from scry.models.results import CollectResult, DiffResult, PipelineResult, ReportResult
from scry.models.surface import AppSurface
from scry.models.triage import TriageResult

logger = logging.getLogger(__name__)


def run_collect(config: ProjectConfig) -> CollectResult:
    """Run the collect stage independently."""
    logger.info("Starting collect stage")
    start = time.perf_counter()
    result = collect.run_all_collectors(config)
    logger.info("collect stage completed in %.1fs", time.perf_counter() - start)
    return result


def run_inventory(config: ProjectConfig) -> AppSurface:
    """Run the inventory stage independently."""
    logger.info("Starting inventory stage")
    start = time.perf_counter()
    surface = inventory.run_all_extractors(config)
    logger.info("inventory stage completed in %.1fs", time.perf_counter() - start)
    return surface


def run_diff(
    collect_result: CollectResult,
    surface: AppSurface,
    config: ProjectConfig,
) -> DiffResult:
    """Run the diff stage independently."""
    logger.info("Starting diff stage")
    start = time.perf_counter()

    schema_changes: list[SchemaChange] = []
    schema_impacts: list[ImpactItem] = []
    if collect_result.old_schema_sdl and collect_result.new_schema_sdl:
        schema_changes = diff_schemas(collect_result.old_schema_sdl, collect_result.new_schema_sdl)
        schema_impacts = match_schema_changes_to_surface(
            schema_changes, collect_result.old_schema_sdl, surface
        )
        logger.info(
            "Schema diff found %d changes, %d touching inventoried operations",
            len(schema_changes),
            sum(1 for item in schema_impacts if item.affected_features),
        )

    # Match changelog entries against project surface
    changelog_impacts = match_changelog_to_surface(collect_result.changes, surface)

    # Let Claude override the substring match when a triage model is configured
    triage: TriageResult | None = None
    if config.triage_model and changelog_impacts:
        try:
            changelog_impacts, triage = triage_changelog_impacts(
                changelog_impacts, surface, config.triage_model
            )
        except Exception:
            logger.warning("Claude triage failed; keeping deterministic scores", exc_info=True)

    all_impacts = changelog_impacts + schema_impacts

    # Apply escalation rules
    scored = score_severity(all_impacts, config.escalation_rules)

    logger.info("diff stage completed in %.1fs", time.perf_counter() - start)
    return DiffResult(schema_changes=schema_changes, impacts=scored, triage=triage)


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
            start = time.perf_counter()
            report_result = report.generate_all_reports(
                diff_result.impacts,
                collect_result.changes,
                config,
                surface,
                collect_result,
                triage=diff_result.triage,
            )
            logger.info("report stage completed in %.1fs", time.perf_counter() - start)
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
