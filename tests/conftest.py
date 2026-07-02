"""Shared pytest fixtures for scry tests."""

from datetime import date
from pathlib import Path

import pytest

from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.config import EscalationRule, ProjectConfig
from scry.models.enums import (
    ChangeCategory,
    ChangeSource,
    Criticality,
    OperationType,
    SchemaChangeType,
    Severity,
)
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface, GraphQLOperation

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Re-export for use in test modules
__all__ = ["FIXTURES_DIR"]


@pytest.fixture()
def sample_config() -> ProjectConfig:
    """ProjectConfig built from the Diode example."""
    return ProjectConfig(
        name="diode",
        root=Path("/tmp/diode"),
        platform="shopify",
        api_version_source="shopify.app.toml:webhooks.api_version",
        source_patterns=["app/**/*.ts", "app/**/*.tsx"],
        graphql_tag="#graphql",
        dependency_prefixes=["@shopify/"],
        component_tag_pattern="<s-",
        webhook_config_path="shopify.app.toml",
        changelog_rss_url="https://shopify.dev/changelog/feed.xml",
        schema_base_url="https://shopify.dev/admin-graphql",
        escalation_rules=[],
        report_dir="docs/api-changes",
    )


@pytest.fixture()
def sample_manifest_path() -> Path:
    """Path to the YAML sample manifest fixture."""
    return FIXTURES_DIR / "sample_manifest.yaml"


@pytest.fixture()
def sample_change_record() -> ChangeRecord:
    """A valid ChangeRecord instance."""
    return ChangeRecord(
        source=ChangeSource.RSS,
        title="productVariantsBulkUpdate input type changes in 2026-07",
        version="2026-07",
        description="The variants argument now requires an explicit sku field.",
        category=ChangeCategory.BREAKING,
        action_required=True,
        url="https://shopify.dev/changelog/product-variants-bulk-update-input-change",
    )


@pytest.fixture()
def sample_schema_change() -> SchemaChange:
    """A valid SchemaChange instance."""
    return SchemaChange(
        change_type=SchemaChangeType.FIELD_REMOVED,
        criticality=Criticality.BREAKING,
        path="Product.barcode",
        message="Field Product.barcode was removed.",
    )


@pytest.fixture()
def inventory_project_root(tmp_path: Path) -> ProjectConfig:
    """Create a temp project directory with all inventory fixtures, return its config."""
    # Create directory structure
    app_routes = tmp_path / "app" / "routes"
    app_routes.mkdir(parents=True)

    # Copy fixture files into the temp project
    (app_routes / "products.ts").write_text((FIXTURES_DIR / "sample_source.ts").read_text())
    (app_routes / "components.tsx").write_text((FIXTURES_DIR / "sample_component.tsx").read_text())
    (tmp_path / "shopify.app.toml").write_text(
        (FIXTURES_DIR / "sample_shopify_app.toml").read_text()
    )
    (tmp_path / "package.json").write_text((FIXTURES_DIR / "sample_package.json").read_text())

    return ProjectConfig(
        name="diode",
        root=tmp_path,
        platform="shopify",
        api_version_source="shopify.app.toml:webhooks.api_version",
        source_patterns=["app/**/*.ts", "app/**/*.tsx"],
        graphql_tag="#graphql",
        dependency_prefixes=["@shopify/"],
        component_tag_pattern="<s-",
        webhook_config_path="shopify.app.toml",
        escalation_rules=[],
        report_dir="docs/api-changes",
    )


# ── Diff-engine fixtures ──────────────────────────────────────────────


@pytest.fixture()
def sample_old_schema() -> str:
    """SDL string for the older schema version."""
    return (FIXTURES_DIR / "schema_2026_04.graphql").read_text()


@pytest.fixture()
def sample_new_schema() -> str:
    """SDL string for the newer schema version."""
    return (FIXTURES_DIR / "schema_2026_07.graphql").read_text()


@pytest.fixture()
def sample_surface_with_operations() -> AppSurface:
    """AppSurface with GraphQL ops referencing products and Product.barcode."""
    return AppSurface(
        api_version="2026-04",
        graphql_operations=[
            GraphQLOperation(
                name="GetProducts",
                operation_type=OperationType.QUERY,
                file=Path("app/routes/products.ts"),
                fields=["products"],
                raw_query="query GetProducts { products(first: 10) { nodes { id title barcode } } }",
            ),
        ],
        webhook_topics=["orders/create", "products/update"],
        dependencies={"@shopify/polaris": "^12.0.0", "@shopify/app-bridge": "^4.1.0"},
        ui_components=["s-card", "s-button"],
    )


@pytest.fixture()
def sample_escalation_rules() -> list[EscalationRule]:
    """Escalation rules matching Diode-relevant patterns."""
    return [
        EscalationRule(
            pattern="barcode",
            floor=Severity.CRITICAL,
            reason="Barcode field is critical to product sync",
        ),
        EscalationRule(
            pattern="productVariantsBulkUpdate",
            floor=Severity.HIGH,
            reason="Bulk update used in nightly sync job",
        ),
    ]


@pytest.fixture()
def sample_changelog_changes() -> list[ChangeRecord]:
    """ChangeRecord list with various categories for changelog matching tests."""
    return [
        ChangeRecord(
            source=ChangeSource.RSS,
            title="Products barcode field deprecation",
            description="The barcode field on products will be removed in 2026-07.",
            category=ChangeCategory.DEPRECATION,
            sunset_date=date(2026, 7, 1),
        ),
        ChangeRecord(
            source=ChangeSource.CHANGELOG,
            title="New orders/create webhook payload field",
            description="orders/create webhook now includes fulfillment_status.",
            category=ChangeCategory.FEATURE,
        ),
        ChangeRecord(
            source=ChangeSource.CHANGELOG,
            title="Platform maintenance window scheduled",
            description="Scheduled maintenance for internal tooling.",
            category=ChangeCategory.PLATFORM,
        ),
    ]


# ── Report-engine fixtures ─────────────────────────────────────────────


@pytest.fixture()
def sample_impact_items() -> list[ImpactItem]:
    """Mixed-severity ImpactItems for report tests."""
    return [
        ImpactItem(
            change=SchemaChange(
                change_type=SchemaChangeType.FIELD_REMOVED,
                criticality=Criticality.BREAKING,
                path="Product.barcode",
                message="Field Product.barcode was removed.",
            ),
            severity=Severity.CRITICAL,
            affected_files=[Path("/tmp/diode/app/routes/products.ts")],
            affected_features=["barcode-sync"],
        ),
        ImpactItem(
            change=ChangeRecord(
                source=ChangeSource.RSS,
                title="productVariantsBulkUpdate input change",
                version="2026-07",
                description="The variants argument now requires an explicit sku field.",
                category=ChangeCategory.BREAKING,
                action_required=True,
                url="https://shopify.dev/changelog/variants-bulk-update",
            ),
            severity=Severity.HIGH,
            affected_files=[Path("/tmp/diode/app/routes/products.ts")],
            affected_features=["barcode-sync"],
            suggested_action="Add sku field to all productVariantsBulkUpdate calls.",
        ),
        ImpactItem(
            change=ChangeRecord(
                source=ChangeSource.RSS,
                title="Products barcode field deprecation",
                description="The barcode field on products will be removed in 2026-07.",
                category=ChangeCategory.DEPRECATION,
                sunset_date=date(2026, 7, 1),
            ),
            severity=Severity.MEDIUM,
            affected_files=[Path("/tmp/diode/app/routes/products.ts")],
            affected_features=["barcode-sync"],
            deadline=date(2026, 7, 1),
        ),
        ImpactItem(
            change=ChangeRecord(
                source=ChangeSource.CHANGELOG,
                title="New webhook payload field",
                description="orders/create webhook now includes fulfillment_status.",
                category=ChangeCategory.FEATURE,
            ),
            severity=Severity.LOW,
        ),
    ]
