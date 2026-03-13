"""Tests for scry.diff.dependencies — dependency version differ."""

from scry.diff.dependencies import diff_dependencies
from scry.models.enums import Severity


class TestDiffDependencies:
    """Tests for diff_dependencies()."""

    def test_major_bump_is_medium(self) -> None:
        current = {"@shopify/polaris": "^12.0.0"}
        latest = {"@shopify/polaris": "^13.0.0"}
        items = diff_dependencies(current, latest)
        assert len(items) == 1
        assert items[0].severity == Severity.MEDIUM
        assert "12.0.0" in items[0].change.title
        assert "13.0.0" in items[0].change.title

    def test_minor_bump_is_low(self) -> None:
        current = {"@shopify/polaris": "^12.0.0"}
        latest = {"@shopify/polaris": "^12.3.0"}
        items = diff_dependencies(current, latest)
        assert len(items) == 1
        assert items[0].severity == Severity.LOW

    def test_identical_versions_skipped(self) -> None:
        current = {"@shopify/polaris": "^12.0.0"}
        latest = {"@shopify/polaris": "^12.0.0"}
        items = diff_dependencies(current, latest)
        assert items == []

    def test_missing_from_latest_skipped(self) -> None:
        current = {"@shopify/polaris": "^12.0.0", "some-pkg": "1.0.0"}
        latest = {"@shopify/polaris": "^12.0.0"}
        items = diff_dependencies(current, latest)
        assert items == []

    def test_non_semver_versions_skipped(self) -> None:
        current = {"some-pkg": "latest"}
        latest = {"some-pkg": "1.0.0"}
        items = diff_dependencies(current, latest)
        assert items == []
