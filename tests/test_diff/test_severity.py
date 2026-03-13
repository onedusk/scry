"""Tests for scry.diff.severity — severity scorer with escalation rules."""

from datetime import date

from scry.diff.severity import score_severity
from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.config import EscalationRule
from scry.models.enums import (
    ChangeCategory,
    ChangeSource,
    Criticality,
    SchemaChangeType,
    Severity,
)
from scry.models.impact import ImpactItem


class TestScoreSeverity:
    """Tests for score_severity()."""

    def test_escalation_raises_severity(
        self, sample_escalation_rules: list[EscalationRule]
    ) -> None:
        """A rule matching 'barcode' should escalate from HIGH to CRITICAL."""
        item = ImpactItem(
            change=SchemaChange(
                change_type=SchemaChangeType.FIELD_REMOVED,
                criticality=Criticality.BREAKING,
                path="Product.barcode",
                message="Product.barcode was removed.",
            ),
            severity=Severity.HIGH,
        )
        scored = score_severity([item], sample_escalation_rules)
        assert scored[0].severity == Severity.CRITICAL

    def test_escalation_does_not_lower_severity(
        self, sample_escalation_rules: list[EscalationRule]
    ) -> None:
        """A rule with floor=HIGH should not lower an already-CRITICAL item."""
        item = ImpactItem(
            change=SchemaChange(
                change_type=SchemaChangeType.FIELD_REMOVED,
                criticality=Criticality.BREAKING,
                path="productVariantsBulkUpdate.variants",
                message="Field removed.",
            ),
            severity=Severity.CRITICAL,
        )
        scored = score_severity([item], sample_escalation_rules)
        assert scored[0].severity == Severity.CRITICAL

    def test_multiple_rules_highest_wins(self) -> None:
        """When multiple rules match, the highest floor wins."""
        rules = [
            EscalationRule(pattern="Product", floor=Severity.MEDIUM),
            EscalationRule(pattern="barcode", floor=Severity.CRITICAL),
        ]
        item = ImpactItem(
            change=SchemaChange(
                change_type=SchemaChangeType.FIELD_REMOVED,
                criticality=Criticality.BREAKING,
                path="Product.barcode",
                message="Product.barcode was removed.",
            ),
            severity=Severity.LOW,
        )
        scored = score_severity([item], rules)
        assert scored[0].severity == Severity.CRITICAL

    def test_no_match_preserves_base_severity(self) -> None:
        """Items that don't match any rule keep their original severity."""
        rules = [EscalationRule(pattern="barcode", floor=Severity.CRITICAL)]
        item = ImpactItem(
            change=SchemaChange(
                change_type=SchemaChangeType.FIELD_REMOVED,
                criticality=Criticality.BREAKING,
                path="Shop.name",
                message="Shop.name was removed.",
            ),
            severity=Severity.HIGH,
        )
        scored = score_severity([item], rules)
        assert scored[0].severity == Severity.HIGH

    def test_deadline_from_sunset_date(self) -> None:
        """ChangeRecords with sunset_date should populate the deadline field."""
        item = ImpactItem(
            change=ChangeRecord(
                source=ChangeSource.RSS,
                title="barcode deprecation",
                category=ChangeCategory.DEPRECATION,
                sunset_date=date(2026, 7, 1),
            ),
            severity=Severity.MEDIUM,
        )
        scored = score_severity([item], [])
        assert scored[0].deadline == date(2026, 7, 1)
