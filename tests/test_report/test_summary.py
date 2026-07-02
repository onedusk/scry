"""Tests for scry.report.summary — summary generator and raw exporter."""

import json
from pathlib import Path

from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.impact import ImpactItem
from scry.report.summary import (
    export_raw_changes,
    export_raw_changes_json,
    generate_cli_summary,
    generate_summary,
)


class TestGenerateSummary:
    """Tests for generate_summary()."""

    def test_includes_counts_and_deadline(
        self, sample_impact_items: list[ImpactItem], sample_config: ProjectConfig
    ) -> None:
        result = generate_summary(sample_impact_items, sample_config)
        assert "4 changes detected" in result
        assert "diode" in result
        assert "2 require action" in result
        assert "2026-07-01" in result

    def test_zero_impacts(self, sample_config: ProjectConfig) -> None:
        result = generate_summary([], sample_config)
        assert result == "No changes detected that affect diode."


class TestGenerateCliSummary:
    """Tests for generate_cli_summary()."""

    def test_single_line_format(
        self, sample_impact_items: list[ImpactItem], sample_config: ProjectConfig
    ) -> None:
        result = generate_cli_summary(sample_impact_items, sample_config)
        assert "4 changes" in result
        assert "2 action required" in result
        assert "2 other" in result
        assert "\n" not in result


class TestExportRawChanges:
    """Tests for export_raw_changes() and export_raw_changes_json()."""

    def test_writes_valid_json(self, tmp_path: Path, sample_change_record: ChangeRecord) -> None:
        output = tmp_path / "changes.json"
        result = export_raw_changes([sample_change_record], output)
        assert result == output
        data = json.loads(output.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        roundtripped = ChangeRecord.model_validate(data[0])
        assert roundtripped.title == sample_change_record.title

    def test_empty_list_produces_empty_array(self, tmp_path: Path) -> None:
        output = tmp_path / "empty.json"
        export_raw_changes([], output)
        data = json.loads(output.read_text())
        assert data == []

    def test_json_string_variant(self, sample_change_record: ChangeRecord) -> None:
        result = export_raw_changes_json([sample_change_record])
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["title"] == sample_change_record.title
