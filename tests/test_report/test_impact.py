"""Tests for scry.report.impact — impact report generator."""

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
from scry.models.surface import AppSurface
from scry.report.impact import generate_impact_report


class TestGenerateImpactReport:
    """Tests for generate_impact_report()."""

    def test_action_required_section(
        self,
        sample_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """CRITICAL and HIGH items appear in Action Required section."""
        report = generate_impact_report(
            sample_impact_items, sample_config, sample_surface_with_operations
        )
        assert "## Action Required" in report
        assert "[CRITICAL] Product.barcode" in report
        assert "[HIGH] productVariantsBulkUpdate" in report

    def test_deprecation_tracker_table(
        self,
        sample_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """DEPRECATION category items appear in the Deprecation Tracker table."""
        report = generate_impact_report(
            sample_impact_items, sample_config, sample_surface_with_operations
        )
        assert "## Deprecation Tracker" in report
        assert "Products barcode field deprecation" in report
        assert "2026-07-01" in report

    def test_omits_empty_sdk_section(
        self,
        sample_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """No SDK items → no SDK Updates section."""
        report = generate_impact_report(
            sample_impact_items, sample_config, sample_surface_with_operations
        )
        assert "## SDK Updates" not in report

    def test_empty_impacts_no_changes(
        self,
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """Empty impacts list produces 'No changes detected' in summary."""
        report = generate_impact_report(
            [], sample_config, sample_surface_with_operations
        )
        assert "No changes detected" in report
        assert "## Action Required" not in report

    def test_affected_files_relative(
        self,
        sample_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """Affected file paths are relative to project root, not absolute."""
        report = generate_impact_report(
            sample_impact_items, sample_config, sample_surface_with_operations
        )
        assert "app/routes/products.ts" in report
        assert "/tmp/diode/app/routes/products.ts" not in report

    def test_handles_both_change_types(
        self,
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """Report handles both ChangeRecord and SchemaChange in impacts."""
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
                    source=ChangeSource.CHANGELOG,
                    title="New feature added",
                    description="A new feature.",
                    category=ChangeCategory.FEATURE,
                ),
                severity=Severity.LOW,
            ),
        ]
        report = generate_impact_report(
            items, sample_config, sample_surface_with_operations
        )
        assert "Product.barcode" in report
        assert "New feature added" in report

    def test_header_includes_metadata(
        self,
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """Header includes project name, API version, and scry version."""
        report = generate_impact_report(
            [], sample_config, sample_surface_with_operations, next_api_version="2026-07"
        )
        assert "diode API version: 2026-04" in report
        assert "Next shopify version: 2026-07" in report
        assert "scry version:" in report
