"""Tests for scry.report.change_plan — change plan draft generator."""

from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.config import ProjectConfig
from scry.models.enums import (
    ChangeCategory,
    ChangeSource,
    Criticality,
    SchemaChangeType,
    Severity,
)
from scry.models.impact import ImpactItem
from scry.report.change_plan import generate_change_plan


class TestGenerateChangePlan:
    """Tests for generate_change_plan()."""

    def test_groups_by_feature_area(
        self,
        sample_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
    ) -> None:
        """Impacts sharing affected_features are grouped into one milestone."""
        plan = generate_change_plan(sample_impact_items, sample_config)
        assert "barcode-sync" in plan
        # Should have a milestone table
        assert "| Task |" in plan

    def test_deduplicates_files_highest_severity(
        self,
        sample_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
    ) -> None:
        """Affected Files table deduplicates, keeping highest severity."""
        plan = generate_change_plan(sample_impact_items, sample_config)
        assert "## Affected Files" in plan
        # Extract just the Affected Files section
        af_section = plan.split("## Affected Files")[1].split("##")[0]
        file_rows = [
            line for line in af_section.split("\n") if "products.ts" in line and "|" in line
        ]
        assert len(file_rows) == 1
        assert "CRITICAL" in file_rows[0]

    def test_open_questions_for_missing_action(self, sample_config: ProjectConfig) -> None:
        """Items without suggested_action generate open questions."""
        items = [
            ImpactItem(
                change=SchemaChange(
                    change_type=SchemaChangeType.FIELD_REMOVED,
                    criticality=Criticality.BREAKING,
                    path="Product.barcode",
                    message="Product.barcode was removed.",
                ),
                severity=Severity.CRITICAL,
                suggested_action="",
            ),
        ]
        plan = generate_change_plan(items, sample_config)
        assert "## Open Questions" in plan
        assert "migration path" in plan.lower()
        assert "unlisted files" in plan.lower()

    def test_severity_grouping_fallback(self, sample_config: ProjectConfig) -> None:
        """When no affected_features, falls back to severity grouping."""
        items = [
            ImpactItem(
                change=SchemaChange(
                    change_type=SchemaChangeType.FIELD_REMOVED,
                    criticality=Criticality.BREAKING,
                    path="Product.barcode",
                    message="Product.barcode was removed.",
                ),
                severity=Severity.CRITICAL,
            ),
            ImpactItem(
                change=ChangeRecord(
                    source=ChangeSource.RSS,
                    title="Some breaking change",
                    description="Details.",
                    category=ChangeCategory.BREAKING,
                ),
                severity=Severity.HIGH,
            ),
        ]
        plan = generate_change_plan(items, sample_config)
        assert "CRITICAL items" in plan
        assert "HIGH items" in plan
