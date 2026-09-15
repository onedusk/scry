"""Tests for scry.verify and the scry verify command."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from scry.cli import app
from scry.models.config import ProjectConfig
from scry.models.enums import OperationType
from scry.models.surface import AppSurface, GraphQLOperation
from scry.verify import (
    DeprecatedUse,
    OperationCheck,
    VerifyResult,
    check_operations,
    deprecation_debt,
    render_verify,
    run_verify,
)

runner = CliRunner()


def _op(name: str, raw_query: str) -> GraphQLOperation:
    return GraphQLOperation(
        name=name,
        operation_type=OperationType.QUERY,
        file=Path("/tmp/diode/app/routes/products.ts"),
        fields=[],
        raw_query=raw_query,
    )


class TestCheckOperations:
    def test_valid_on_pinned_and_invalid_on_target(
        self,
        sample_old_schema: str,
        sample_new_schema: str,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        current = check_operations(sample_surface_with_operations, sample_old_schema, "2026-04")
        target = check_operations(sample_surface_with_operations, sample_new_schema, "2026-07")
        assert current == [
            OperationCheck("GetProducts", Path("app/routes/products.ts"), "2026-04", [])
        ]
        assert target[0].version == "2026-07"
        assert target[0].errors == ["Cannot query field 'barcode' on type 'Product'."]

    def test_unparsable_operation_reports_syntax_error(self, sample_old_schema: str) -> None:
        surface = AppSurface(api_version="2026-04", graphql_operations=[_op("Broken", "query {")])
        checks = check_operations(surface, sample_old_schema, "2026-04")
        assert len(checks[0].errors) == 1
        assert "Syntax Error" in checks[0].errors[0]


class TestDeprecationDebt:
    _SDL = (
        "type Query { products: [Product!]! }"
        'type Product { id: ID! barcode: String @deprecated(reason: "Use barcodes") '
        "barcodes: [String!] title: String }"
    )

    def test_lists_deprecated_members_the_operations_use(self) -> None:
        surface = AppSurface(
            api_version="2026-04",
            graphql_operations=[
                _op("WithBarcode", "query WithBarcode { products { id barcode } }"),
                _op("Clean", "query Clean { products { id title } }"),
            ],
        )
        uses = deprecation_debt(surface, self._SDL)
        assert uses == [
            DeprecatedUse(
                "WithBarcode",
                Path("/tmp/diode/app/routes/products.ts"),
                "Product.barcode",
                "Use barcodes",
            )
        ]

    def test_unparsable_operation_is_skipped(self) -> None:
        surface = AppSurface(api_version="2026-04", graphql_operations=[_op("Broken", "query {")])
        assert deprecation_debt(surface, self._SDL) == []


class TestRunVerify:
    def test_checks_both_versions_and_debt(
        self,
        sample_config: ProjectConfig,
        sample_old_schema: str,
        sample_new_schema: str,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        class _Collector:
            old_schema_sdl = sample_old_schema
            new_schema_sdl = sample_new_schema
            current_api_version = "2026-04"
            next_api_version = "2026-07"

            def collect(self, config: ProjectConfig) -> list[Any]:
                return []

        with (
            patch("scry.verify.SchemaCollector", _Collector),
            patch("scry.verify.run_all_extractors", return_value=sample_surface_with_operations),
        ):
            result = run_verify(sample_config)
        assert (result.current_version, result.target_version) == ("2026-04", "2026-07")
        assert [c.version for c in result.checks] == ["2026-04", "2026-07"]
        assert [c.version for c in result.failed] == ["2026-07"]
        assert result.deprecated_uses == []

    def test_missing_schema_raises(self, sample_config: ProjectConfig) -> None:
        class _Collector:
            old_schema_sdl = None
            new_schema_sdl = None
            current_api_version = None
            next_api_version = None

            def collect(self, config: ProjectConfig) -> list[Any]:
                return []

        with patch("scry.verify.SchemaCollector", _Collector):
            try:
                run_verify(sample_config)
            except RuntimeError as e:
                assert "schema_base_url" in str(e)
            else:  # pragma: no cover
                raise AssertionError("expected RuntimeError")


class TestRenderVerify:
    def test_tables(self, sample_config: ProjectConfig) -> None:
        result = VerifyResult(
            current_version="2026-04",
            target_version="2026-10",
            checks=[
                OperationCheck("A", Path("/tmp/diode/app/a.ts"), "2026-04", []),
                OperationCheck(
                    "A", Path("/tmp/diode/app/a.ts"), "2026-10", ["Cannot query field 'x'."]
                ),
            ],
            deprecated_uses=[
                DeprecatedUse(
                    "A", Path("/tmp/diode/app/a.ts"), "Product.featuredImage", "Use featuredMedia"
                )
            ],
        )
        text = render_verify(result, sample_config)
        assert "| Operation | File | 2026-04 | 2026-10 |" in text
        assert "| A | app/a.ts | valid | invalid: Cannot query field 'x'. |" in text
        assert "| A | app/a.ts | `Product.featuredImage` | Use featuredMedia |" in text

    def test_empty(self, sample_config: ProjectConfig) -> None:
        text = render_verify(VerifyResult(current_version="2026-04"), sample_config)
        assert "> Target version: none newer published" in text
        assert "No GraphQL operations inventoried." in text
        assert "None." in text


class TestVerifyCommand:
    @staticmethod
    def _manifest(tmp_path: Path) -> Path:
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "index.ts").write_text("export {};\n")
        manifest = tmp_path / "scry.yaml"
        manifest.write_text(
            f"name: test\nroot: {tmp_path}\nplatform: shopify\n"
            'api_version_source: "x:y"\nsource_patterns:\n  - "app/**/*.ts"\n'
        )
        return manifest

    def test_exit_1_when_an_operation_is_invalid(self, tmp_path: Path) -> None:
        result = VerifyResult(
            current_version="2026-04",
            checks=[OperationCheck("A", tmp_path / "a.ts", "2026-04", ["bad"])],
        )
        with patch("scry.verify.run_verify", return_value=result):
            outcome = runner.invoke(app, ["verify", "--project", str(self._manifest(tmp_path))])
        assert outcome.exit_code == 1
        assert "invalid: bad" in outcome.output

    def test_exit_0_and_json(self, tmp_path: Path) -> None:
        result = VerifyResult(current_version="2026-04", target_version="2026-07")
        with patch("scry.verify.run_verify", return_value=result):
            outcome = runner.invoke(
                app, ["verify", "--project", str(self._manifest(tmp_path)), "--json"]
            )
        assert outcome.exit_code == 0
        assert '"target_version": "2026-07"' in outcome.output

    def test_missing_schema_is_reported(self, tmp_path: Path) -> None:
        with patch("scry.verify.run_verify", side_effect=RuntimeError("no schema")):
            outcome = runner.invoke(app, ["verify", "--project", str(self._manifest(tmp_path))])
        assert outcome.exit_code == 1
        assert "verify: no schema" in outcome.output
