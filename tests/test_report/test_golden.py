"""Golden-file tests for report markdown output.

Renders the impact report and change plan from a representative fixture and
compares the result byte-for-byte against committed golden files under
tests/fixtures/. After an intentional output change, regenerate the goldens
with:

    UPDATE_GOLDEN=1 uv run pytest tests/test_report/test_golden.py

then review the golden diff before committing.
"""

import os
from datetime import datetime, tzinfo
from pathlib import Path

import pytest

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
from scry.report.change_plan import generate_change_plan
from scry.report.impact import generate_impact_report

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class _FrozenDatetime(datetime):
    """datetime replacement whose now() is pinned for reproducible output."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> "_FrozenDatetime":
        return cls(2026, 6, 15, 12, 0, 0, tzinfo=tz)


def _assert_matches_golden(rendered: str, golden_name: str) -> None:
    golden_path = FIXTURES_DIR / golden_name
    if os.environ.get("UPDATE_GOLDEN") == "1":
        golden_path.write_text(rendered)
    assert rendered == golden_path.read_text(), (
        f"Rendered markdown does not match {golden_name}. If the change is "
        "intentional, regenerate with: UPDATE_GOLDEN=1 uv run pytest tests/test_report"
    )


@pytest.fixture()
def golden_impact_items(sample_impact_items: list[ImpactItem]) -> list[ImpactItem]:
    """sample_impact_items extended so every report section renders."""
    return [
        *sample_impact_items,
        ImpactItem(
            change=ChangeRecord(
                source=ChangeSource.REGISTRY,
                title="@shopify/polaris: ^12.0.0 → 13.1.0",
                category=ChangeCategory.SDK,
                description="Package @shopify/polaris has a newer version available.",
            ),
            severity=Severity.LOW,
        ),
        ImpactItem(
            change=SchemaChange(
                change_type=SchemaChangeType.TYPE_REMOVED,
                criticality=Criticality.BREAKING,
                path="SubscriptionContract",
                message="Type SubscriptionContract was removed.",
            ),
            severity=Severity.HIGH,
        ),
    ]


class TestGoldenReports:
    """Byte-exact golden-file comparisons for the report generators."""

    def test_impact_report_matches_golden(
        self,
        golden_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Impact report markdown matches tests/fixtures/golden_impact_report.md."""
        monkeypatch.setattr("scry.report.impact.datetime", _FrozenDatetime)
        monkeypatch.setattr("scry.__version__", "0.1.0-golden")
        report = generate_impact_report(
            golden_impact_items,
            sample_config,
            sample_surface_with_operations,
            next_api_version="2026-07",
        )
        _assert_matches_golden(report, "golden_impact_report.md")

    def test_change_plan_matches_golden(
        self,
        golden_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
    ) -> None:
        """Change plan markdown matches tests/fixtures/golden_change_plan.md."""
        plan = generate_change_plan(golden_impact_items, sample_config)
        _assert_matches_golden(plan, "golden_change_plan.md")
