"""Tests for scry.report.tasks — progressive-decomposition task index and specs."""

from datetime import date, datetime
from pathlib import Path

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
from scry.report.tasks import decomposition_name, generate_task_files, write_task_files

WHEN = date(2026, 9, 15)


def _schema_item(
    change_type: SchemaChangeType,
    criticality: Criticality,
    path: str = "Product.barcode",
    **overrides: object,
) -> ImpactItem:
    fields: dict[str, object] = {
        "severity": Severity.HIGH,
        "affected_files": [Path("/tmp/diode/app/routes/products.ts")],
        "affected_features": ["GetProducts"],
    }
    fields.update(overrides)
    return ImpactItem(
        change=SchemaChange(
            change_type=change_type,
            criticality=criticality,
            path=path,
            message=f"{path} changed.",
        ),
        **fields,  # type: ignore[arg-type]
    )


def _record_item(title: str, **overrides: object) -> ImpactItem:
    fields: dict[str, object] = {"severity": Severity.HIGH}
    fields.update(overrides)
    return ImpactItem(
        change=ChangeRecord(
            source=ChangeSource.RSS,
            title=title,
            description="<p>Details.</p>",
            category=ChangeCategory.PLATFORM,
            url="https://example.com/entry",
        ),
        **fields,  # type: ignore[arg-type]
    )


class TestDecompositionName:
    def test_platform_and_month(self, sample_config: ProjectConfig) -> None:
        assert decomposition_name(sample_config, WHEN) == "shopify-changes-2026-09"

    def test_platform_is_kebab_cased(self, sample_config: ProjectConfig) -> None:
        config = sample_config.model_copy(update={"platform": "Shopify Admin API"})
        assert decomposition_name(config, WHEN) == "shopify-admin-api-changes-2026-09"


class TestGenerateTaskFiles:
    def test_milestones_follow_severity_and_skip_info(
        self,
        sample_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        noise = _record_item("Checkout change", severity=Severity.INFO)
        files = generate_task_files(
            [*sample_impact_items, noise], sample_config, sample_surface_with_operations, when=WHEN
        )
        assert set(files) == {
            "stage-3-task-index.md",
            "tasks_m01.md",
            "tasks_m02.md",
            "tasks_m03.md",
        }
        assert (
            "# Stage 4: Task Specifications — Milestone 1: Action required" in files["tasks_m01.md"]
        )
        assert "**T-01.01 — Remove use of Product.barcode**" in files["tasks_m01.md"]
        assert "**T-01.02 — productVariantsBulkUpdate input change**" in files["tasks_m01.md"]
        assert "Milestone 2: Review" in files["tasks_m02.md"]
        assert "Milestone 3: Optional" in files["tasks_m03.md"]
        assert all("Checkout change" not in content for content in files.values())

    def test_one_task_per_impact_listing_all_files(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        item = _schema_item(
            SchemaChangeType.FIELD_REMOVED,
            Criticality.BREAKING,
            affected_files=[
                Path("/tmp/diode/app/a.ts"),
                Path("/tmp/diode/app/b.ts"),
            ],
        )
        files = generate_task_files(
            [item], sample_config, sample_surface_with_operations, when=WHEN
        )
        tasks = files["tasks_m01.md"]
        assert "**T-01.01 — Remove use of Product.barcode**" in tasks
        assert "T-01.02" not in tasks
        assert "- **Files:** `app/a.ts`, `app/b.ts` (MODIFY)" in tasks
        index = files["stage-3-task-index.md"]
        assert "app/a.ts" in index and "app/b.ts" in index
        assert (
            "**Totals:** 0 files created, 2 modifications, 0 deletions; 0 tasks have no file"
            in (index)
        )

    def test_webhook_and_package_features_map_to_config_files(
        self,
        tmp_path: Path,
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        (tmp_path / "package.json").write_text("{}")
        config = sample_config.model_copy(update={"root": tmp_path})
        item = _record_item(
            "Expiring tokens", affected_features=["products/update", "@shopify/polaris"]
        )
        files = generate_task_files([item], config, sample_surface_with_operations, when=WHEN)
        tasks = files["tasks_m01.md"]
        assert "- **Files:** `shopify.app.toml`, `package.json` (MODIFY)" in tasks
        assert "**T-01.01 — Expiring tokens**" in tasks
        assert "T-01.02" not in tasks

    def test_feature_without_file_is_marked_unidentified(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        item = _record_item("Polaris refresh", affected_features=["s-card"])
        files = generate_task_files(
            [item], sample_config, sample_surface_with_operations, when=WHEN
        )
        assert "- **File:** (not identified; see Affected in the outline)" in files["tasks_m01.md"]
        assert "1 tasks have no file identified yet." in files["stage-3-task-index.md"]

    def test_schema_acceptance_criteria(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        items = [
            _schema_item(SchemaChangeType.FIELD_REMOVED, Criticality.BREAKING),
            _schema_item(
                SchemaChangeType.REQUIRED_INPUT_FIELD_ADDED, Criticality.BREAKING, path="In.sku"
            ),
            _schema_item(
                SchemaChangeType.FIELD_DEPRECATED,
                Criticality.NON_BREAKING,
                path="Product.legacy",
                severity=Severity.MEDIUM,
            ),
            _schema_item(
                SchemaChangeType.OPTIONAL_ARG_ADDED,
                Criticality.DANGEROUS,
                path="Query.products",
                severity=Severity.MEDIUM,
            ),
        ]
        files = generate_task_files(
            items,
            sample_config,
            sample_surface_with_operations,
            next_api_version="2026-07",
            when=WHEN,
        )
        action = files["tasks_m01.md"]
        review = files["tasks_m02.md"]
        assert (
            "**Acceptance:** `GetProducts` validate against the 2026-07 schema with no "
            "reference to `Product.barcode`." in action
        )
        assert "**T-01.01 — Supply required In.sku**" in action
        assert "**T-01.02 — Remove use of Product.barcode**" in action
        assert "`GetProducts` supply `In.sku` and validate against the 2026-07 schema." in action
        assert "**T-02.01 — Stop using deprecated Product.legacy**" in review
        assert "**T-02.02 — Review Query.products change**" in review
        assert "`GetProducts` no longer reference `Product.legacy`" in review
        assert "`GetProducts` handle `Query.products` explicitly" in review

    def test_changelog_outline_and_deadline_acceptance(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        item = _record_item(
            "Expiring tokens",
            deadline=date(2027, 1, 1),
            affected_features=["GetProducts"],
            affected_files=[Path("/tmp/diode/app/auth.ts")],
            suggested_action="Upgrade the auth library.",
        )
        files = generate_task_files(
            [item], sample_config, sample_surface_with_operations, when=WHEN
        )
        tasks = files["tasks_m01.md"]
        assert "    - What changed: Details." in tasks
        assert "    - Source: https://example.com/entry" in tasks
        assert "    - Severity: high, deadline 2027-01-01" in tasks
        assert "    - Affected: GetProducts" in tasks
        assert "    - Suggested action: Upgrade the auth library." in tasks
        assert (
            '**Acceptance:** The change in "Expiring tokens" is applied and verified in diode '
            "before 2027-01-01." in tasks
        )

    def test_missing_action_is_called_out(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        files = generate_task_files(
            [_record_item("Entry")], sample_config, sample_surface_with_operations, when=WHEN
        )
        assert (
            "Suggested action: none recorded; determine the migration path" in files["tasks_m01.md"]
        )

    def test_index_lists_files_with_milestones_and_totals(
        self,
        sample_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        files = generate_task_files(
            sample_impact_items, sample_config, sample_surface_with_operations, when=WHEN
        )
        index = files["stage-3-task-index.md"]
        assert "# Stage 3: Task Index — shopify-changes-2026-09" in index
        assert "| M01 | Action required | [tasks_m01.md](tasks_m01.md) | 2 | 0 |" in index
        assert "| | **Total** | | **4** | **0** |" in index
        assert "    M01 --> M02" in index and "    M02 --> M03" in index
        assert "app/routes/products.ts" in index and "MODIFY (M01, M02)" in index
        assert (
            "**Totals:** 0 files created, 1 modifications, 0 deletions; 1 tasks have no file"
            in (index)
        )
        assert "`/decompose shopify-changes-2026-09 review`" in index

    def test_empty_when_nothing_relevant(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        noise = _record_item("Checkout change", severity=Severity.INFO)
        assert generate_task_files([noise], sample_config, sample_surface_with_operations) == {}


class TestFoldingSchemaChanges:
    """Schema changes named by a changelog entry become part of that entry's task."""

    @staticmethod
    def _entry(text: str, **overrides: object) -> ImpactItem:
        fields: dict[str, object] = {
            "severity": Severity.HIGH,
            "affected_files": [Path("/tmp/diode/app/graphql/b.ts")],
            "affected_features": ["BulkUpdate"],
        }
        fields.update(overrides)
        return ImpactItem(
            change=ChangeRecord(
                source=ChangeSource.RSS,
                title="Variants now support multiple barcodes",
                description=f"<p>{text}</p>",
                category=ChangeCategory.PLATFORM,
                url="https://example.com/barcodes",
            ),
            **fields,  # type: ignore[arg-type]
        )

    def test_named_schema_change_folds_into_the_entry_task(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        entry = self._entry("ProductVariant.barcode is now deprecated; use barcodes instead.")
        deprecation = _schema_item(
            SchemaChangeType.FIELD_DEPRECATED,
            Criticality.NON_BREAKING,
            path="ProductVariant.barcode",
            severity=Severity.MEDIUM,
            affected_files=[Path("/tmp/diode/app/graphql/a.ts")],
        )
        files = generate_task_files(
            [entry, deprecation], sample_config, sample_surface_with_operations, when=WHEN
        )
        assert set(files) == {"stage-3-task-index.md", "tasks_m01.md"}
        tasks = files["tasks_m01.md"]
        assert "**T-01.01 — Variants now support multiple barcodes**" in tasks
        assert "T-01.02" not in tasks
        assert "- **Files:** `app/graphql/b.ts`, `app/graphql/a.ts` (MODIFY)" in tasks
        assert (
            "    - Also covers schema change: ProductVariant.barcode (field_deprecated): "
            "ProductVariant.barcode changed." in tasks
        )
        assert "`GetProducts` no longer reference `ProductVariant.barcode`" in tasks

    def test_unnamed_schema_change_stays_separate(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        entry = self._entry("Variants can now carry several barcodes.")
        deprecation = _schema_item(
            SchemaChangeType.FIELD_DEPRECATED,
            Criticality.NON_BREAKING,
            path="ProductVariant.barcode",
            severity=Severity.MEDIUM,
        )
        files = generate_task_files(
            [entry, deprecation], sample_config, sample_surface_with_operations, when=WHEN
        )
        assert "tasks_m02.md" in files
        assert "Stop using deprecated ProductVariant.barcode" in files["tasks_m02.md"]

    def test_path_match_is_whole_token(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        entry = self._entry("Read ProductVariant.barcodes for the full set.")
        deprecation = _schema_item(
            SchemaChangeType.FIELD_DEPRECATED,
            Criticality.NON_BREAKING,
            path="ProductVariant.barcode",
            severity=Severity.MEDIUM,
        )
        files = generate_task_files(
            [entry, deprecation], sample_config, sample_surface_with_operations, when=WHEN
        )
        assert "tasks_m02.md" in files

    def test_folded_task_takes_the_higher_severity(
        self, sample_config: ProjectConfig, sample_surface_with_operations: AppSurface
    ) -> None:
        entry = self._entry(
            "ProductVariantsBulkInput.barcode was removed.", severity=Severity.MEDIUM
        )
        removal = _schema_item(
            SchemaChangeType.FIELD_REMOVED,
            Criticality.BREAKING,
            path="ProductVariantsBulkInput.barcode",
            severity=Severity.HIGH,
        )
        files = generate_task_files(
            [entry, removal], sample_config, sample_surface_with_operations, when=WHEN
        )
        assert set(files) == {"stage-3-task-index.md", "tasks_m01.md"}
        assert "Milestone 1: Action required" in files["tasks_m01.md"]
        assert "**T-01.01 — Variants now support multiple barcodes**" in files["tasks_m01.md"]


class TestWriteTaskFiles:
    def test_writes_under_decompose_dir_and_removes_stale_task_files(
        self,
        tmp_path: Path,
        sample_impact_items: list[ImpactItem],
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        config = sample_config.model_copy(update={"root": tmp_path})
        name = decomposition_name(config, datetime.now().date())
        task_dir = tmp_path / "docs" / "decompose" / name
        task_dir.mkdir(parents=True)
        (task_dir / "tasks_m09.md").write_text("stale")

        index = write_task_files(
            [sample_impact_items[0]], config, sample_surface_with_operations, "2026-07"
        )

        assert index == task_dir / "stage-3-task-index.md"
        assert index.read_text().startswith(f"# Stage 3: Task Index — {name}")
        assert (task_dir / "tasks_m01.md").is_file()
        assert not (task_dir / "tasks_m09.md").exists()

    def test_none_when_nothing_relevant(
        self,
        tmp_path: Path,
        sample_config: ProjectConfig,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        config = sample_config.model_copy(update={"root": tmp_path})
        assert write_task_files([], config, sample_surface_with_operations) is None
        assert not (tmp_path / "docs" / "decompose").exists()
