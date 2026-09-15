"""Tests for scry.report.generate_all_reports — files written to the report directory."""

import json
from pathlib import Path

from scry.models.changes import SchemaChange
from scry.models.config import ProjectConfig
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface
from scry.models.triage import Judgment, TriageResult
from scry.report import generate_all_reports


def _config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="diode",
        root=tmp_path,
        platform="shopify",
        api_version_source="shopify.app.toml:webhooks.api_version",
        source_patterns=["app/**/*.ts"],
    )


class TestGenerateAllReports:
    def test_writes_triage_json_when_triage_ran(
        self,
        tmp_path: Path,
        sample_impact_items: list[ImpactItem],
        sample_surface_with_operations: AppSurface,
    ) -> None:
        triage = TriageResult(
            model="claude-opus-5",
            judgments=[
                Judgment(
                    change_id="abc",
                    relevant=True,
                    severity="high",
                    affected_features=["GetProducts"],
                    deadline=None,
                    suggested_action="Move reads to barcodes.",
                    rationale="Selects Product.barcode.",
                )
            ],
        )
        result = generate_all_reports(
            sample_impact_items,
            [],
            _config(tmp_path),
            sample_surface_with_operations,
            triage=triage,
        )
        assert result.triage_path is not None
        assert result.triage_path.name == "triage.json"
        assert result.task_index_path is not None
        assert result.task_index_path.parent.parent == tmp_path / "docs" / "decompose"
        assert (result.task_index_path.parent / "tasks_m01.md").is_file()
        assert result.triage_path.parent == result.impact_report_path.parent
        assert TriageResult.model_validate_json(result.triage_path.read_text()) == triage
        assert "> Triage: claude-opus-5, 1 entries judged" in result.impact_report_path.read_text()

    def test_no_triage_file_without_triage(
        self,
        tmp_path: Path,
        sample_impact_items: list[ImpactItem],
        sample_surface_with_operations: AppSurface,
    ) -> None:
        result = generate_all_reports(
            sample_impact_items, [], _config(tmp_path), sample_surface_with_operations
        )
        assert result.triage_path is None
        assert result.raw_changes_path is not None
        assert not (result.raw_changes_path.parent / "triage.json").exists()

    def test_writes_schema_changes_json_when_diff_ran(
        self,
        tmp_path: Path,
        sample_impact_items: list[ImpactItem],
        sample_surface_with_operations: AppSurface,
        sample_schema_change: SchemaChange,
    ) -> None:
        result = generate_all_reports(
            sample_impact_items,
            [],
            _config(tmp_path),
            sample_surface_with_operations,
            schema_changes=[sample_schema_change],
        )
        assert result.schema_changes_path is not None
        assert result.schema_changes_path.name == "schema-changes.json"
        rows = json.loads(result.schema_changes_path.read_text())
        assert [SchemaChange.model_validate(r) for r in rows] == [sample_schema_change]

    def test_no_schema_changes_file_when_diff_did_not_run(
        self,
        tmp_path: Path,
        sample_impact_items: list[ImpactItem],
        sample_surface_with_operations: AppSurface,
    ) -> None:
        result = generate_all_reports(
            sample_impact_items, [], _config(tmp_path), sample_surface_with_operations
        )
        assert result.schema_changes_path is None
