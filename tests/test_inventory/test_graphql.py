"""Tests for the GraphQLExtractor."""

from pathlib import Path

from scry.inventory.graphql import GraphQLExtractor, _extract_top_level_fields
from scry.models.config import ProjectConfig
from scry.models.enums import OperationType
from scry.models.surface import AppSurface


class TestGraphQLExtractor:
    def test_extracts_query_operation(
        self, inventory_project_root: ProjectConfig
    ) -> None:
        """Extracts query name, type, and top-level fields."""
        surface = AppSurface(api_version="")
        extractor = GraphQLExtractor()
        result = extractor.extract(inventory_project_root, surface)
        queries = [
            op for op in result.graphql_operations
            if op.operation_type == OperationType.QUERY
        ]
        assert len(queries) >= 1
        query = queries[0]
        assert query.name == "ProductsWithVariants"
        assert "products" in query.fields

    def test_extracts_mutation_operation(
        self, inventory_project_root: ProjectConfig
    ) -> None:
        """Extracts mutation name, type, and fields."""
        surface = AppSurface(api_version="")
        extractor = GraphQLExtractor()
        result = extractor.extract(inventory_project_root, surface)
        mutations = [
            op for op in result.graphql_operations
            if op.operation_type == OperationType.MUTATION
        ]
        assert len(mutations) >= 1
        mutation = mutations[0]
        assert mutation.name == "productCreate"
        assert "productCreate" in mutation.fields

    def test_handles_multiple_operations_per_file(
        self, inventory_project_root: ProjectConfig
    ) -> None:
        """Extracts all operations from a file with multiple #graphql blocks."""
        surface = AppSurface(api_version="")
        extractor = GraphQLExtractor()
        result = extractor.extract(inventory_project_root, surface)
        names = [op.name for op in result.graphql_operations]
        assert "ProductsWithVariants" in names
        assert "productCreate" in names

    def test_no_tag_returns_unchanged(self, tmp_path: Path) -> None:
        """Returns surface unchanged when no files contain the graphql tag."""
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "plain.ts").write_text("const x = 42;\n")
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=["app/**/*.ts"],
        )
        surface = AppSurface(api_version="")
        extractor = GraphQLExtractor()
        result = extractor.extract(config, surface)
        assert result.graphql_operations == []

    def test_raw_query_captured(
        self, inventory_project_root: ProjectConfig
    ) -> None:
        """Verifies raw_query contains the full operation text."""
        surface = AppSurface(api_version="")
        extractor = GraphQLExtractor()
        result = extractor.extract(inventory_project_root, surface)
        query = next(
            op for op in result.graphql_operations
            if op.name == "ProductsWithVariants"
        )
        assert "query ProductsWithVariants" in query.raw_query
        assert "products" in query.raw_query

    def test_respects_custom_tag(self, tmp_path: Path) -> None:
        """A different graphql_tag does not match #graphql tagged files."""
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "source.ts").write_text(
            'const q = `#graphql\n  query Foo { bar }\n`;'
        )
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=["app/**/*.ts"],
            graphql_tag="/* @gql */",
        )
        surface = AppSurface(api_version="")
        extractor = GraphQLExtractor()
        result = extractor.extract(config, surface)
        assert result.graphql_operations == []


class TestExtractTopLevelFields:
    """Unit tests for _extract_top_level_fields edge cases."""

    def test_field_after_nested_block(self) -> None:
        """A standalone field at depth 0 after a nested block is captured."""
        raw = (
            "query Foo {\n"
            "  products {\n"
            "    nodes { id }\n"
            "  }\n"
            "  shop\n"
            "}"
        )
        fields = _extract_top_level_fields(raw)
        assert "products" in fields
        assert "shop" in fields

    def test_fragment_spread_ignored(self) -> None:
        """Fragment spreads (starting with ...) are not extracted as fields."""
        raw = (
            "query Bar {\n"
            "  products { id }\n"
            "  ...ProductFields\n"
            "}"
        )
        fields = _extract_top_level_fields(raw)
        assert "products" in fields
        assert "ProductFields" not in fields

    def test_empty_body(self) -> None:
        """An operation with no body returns no fields."""
        raw = "query Empty {}"
        fields = _extract_top_level_fields(raw)
        assert fields == []

    def test_deeply_nested_fields_excluded(self) -> None:
        """Fields inside nested blocks are not included at top level."""
        raw = (
            "mutation Create {\n"
            "  productCreate {\n"
            "    product {\n"
            "      id\n"
            "      title\n"
            "    }\n"
            "    userErrors { field message }\n"
            "  }\n"
            "}"
        )
        fields = _extract_top_level_fields(raw)
        assert fields == ["productCreate"]
        assert "product" not in fields
        assert "id" not in fields
