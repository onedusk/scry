"""Tests for scry.diff.changelog — changelog-to-surface matcher."""

from scry.diff.changelog import match_changelog_to_surface
from scry.models.changes import ChangeRecord
from scry.models.enums import ChangeCategory, ChangeSource, Severity
from scry.models.surface import AppSurface


class TestMatchChangelogToSurface:
    """Tests for match_changelog_to_surface()."""

    def test_matches_operation_field(
        self,
        sample_changelog_changes: list[ChangeRecord],
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """Barcode deprecation should match via the 'products' field in GetProducts op."""
        items = match_changelog_to_surface(sample_changelog_changes, sample_surface_with_operations)
        barcode_item = items[0]  # "Product barcode field deprecation"
        assert barcode_item.severity == Severity.MEDIUM  # DEPRECATION base
        assert len(barcode_item.affected_features) > 0
        assert "GetProducts" in barcode_item.affected_features

    def test_matches_webhook_topic(
        self,
        sample_changelog_changes: list[ChangeRecord],
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """orders/create webhook change should match the webhook topic."""
        items = match_changelog_to_surface(sample_changelog_changes, sample_surface_with_operations)
        webhook_item = items[1]  # "New orders/create webhook payload field"
        assert webhook_item.severity == Severity.LOW  # FEATURE base
        assert "orders/create" in webhook_item.affected_features

    def test_unmatched_change_gets_info(
        self,
        sample_changelog_changes: list[ChangeRecord],
        sample_surface_with_operations: AppSurface,
    ) -> None:
        """Platform maintenance should not match anything → INFO severity."""
        items = match_changelog_to_surface(sample_changelog_changes, sample_surface_with_operations)
        platform_item = items[2]  # "Platform maintenance window scheduled"
        assert platform_item.severity == Severity.INFO
        assert platform_item.affected_files == []

    def test_case_insensitive_matching(self, sample_surface_with_operations: AppSurface) -> None:
        """Matching should be case-insensitive."""
        changes = [
            ChangeRecord(
                source=ChangeSource.RSS,
                title="PRODUCTS endpoint updated",
                description="Changes to PRODUCTS query.",
                category=ChangeCategory.BREAKING,
            ),
        ]
        items = match_changelog_to_surface(changes, sample_surface_with_operations)
        assert items[0].severity == Severity.HIGH
        assert len(items[0].affected_features) > 0
