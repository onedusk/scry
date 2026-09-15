"""Tests for scry.diff.references — schema-change cross-reference."""

import logging
from pathlib import Path
from typing import Any

import pytest
from graphql import GraphQLSchema, GraphQLSyntaxError, build_schema

from scry.diff.references import (
    change_affects,
    embedded_documents,
    match_schema_changes_to_surface,
    operation_references,
)
from scry.diff.schema import diff_schemas
from scry.models.changes import SchemaChange
from scry.models.enums import Criticality, OperationType, SchemaChangeType, Severity
from scry.models.surface import AppSurface, GraphQLOperation

_SDL = """
type Query {
  products(first: Int, status: Status): ProductConnection
  node(id: ID!): Node
}
interface Node { id: ID! }
type ProductConnection { nodes: [Product!]! }
type Product implements Node { id: ID! title: String! barcode: String }
enum Status { ACTIVE DRAFT }
type Mutation {
  productUpdate(input: ProductInput!, variants: [VariantInput!]): Product
  bulkOperationRunQuery(query: String!): Product
}
input ProductInput { title: String }
input VariantInput { id: ID! barcode: String }
"""


@pytest.fixture()
def schema() -> GraphQLSchema:
    return build_schema(_SDL)


def _op(name: str, raw_query: str, file: str = "app/routes/products.ts") -> GraphQLOperation:
    return GraphQLOperation(
        name=name,
        operation_type=OperationType.QUERY,
        file=Path(file),
        fields=[],
        raw_query=raw_query,
    )


class TestOperationReferences:
    """Tests for operation_references()."""

    def test_selected_fields(self, schema: GraphQLSchema) -> None:
        refs = operation_references(
            schema, "query Q { products(first: 1) { nodes { id barcode } } }"
        )
        assert refs == {
            "Query.products",
            "ProductConnection.nodes",
            "Product.id",
            "Product.barcode",
        }

    def test_inline_fragment_fields_resolve_to_fragment_type(self, schema: GraphQLSchema) -> None:
        refs = operation_references(
            schema, "query Q($id: ID!) { node(id: $id) { ... on Product { barcode } } }"
        )
        assert {"Query.node", "Product.barcode"} <= refs

    def test_variable_input_types_recorded_whole(self, schema: GraphQLSchema) -> None:
        refs = operation_references(
            schema,
            "mutation M($input: ProductInput!, $variants: [VariantInput!]) "
            "{ productUpdate(input: $input, variants: $variants) { id } }",
        )
        assert {"ProductInput", "VariantInput", "Mutation.productUpdate", "Product.id"} <= refs
        assert "VariantInput.barcode" not in refs

    def test_inline_input_object_fields(self, schema: GraphQLSchema) -> None:
        refs = operation_references(
            schema,
            'mutation M { productUpdate(input: {title: "x"}, variants: [{id: "1", barcode: "b"}])'
            " { id } }",
        )
        assert {"ProductInput.title", "VariantInput.id", "VariantInput.barcode"} <= refs
        assert "ProductInput" not in refs

    def test_enum_literal(self, schema: GraphQLSchema) -> None:
        refs = operation_references(schema, "query Q { products(status: ACTIVE) { nodes { id } } }")
        assert "Status.ACTIVE" in refs

    def test_unknown_selections_are_skipped(self, schema: GraphQLSchema) -> None:
        refs = operation_references(schema, "query Q { nope { id } }")
        assert refs == {"Query.nope"}

    def test_follows_documents_embedded_in_string_arguments(self, schema: GraphQLSchema) -> None:
        raw = (
            'mutation Bulk { bulkOperationRunQuery(query: """\n'
            "      { products { nodes { id barcode } } }\n"
            '      """) { id } }'
        )
        refs = operation_references(schema, raw)
        assert {"Mutation.bulkOperationRunQuery", "Query.products", "Product.barcode"} <= refs

    def test_embedded_documents_ignores_plain_strings(self) -> None:
        raw = 'mutation M { productUpdate(input: {title: "not { a query"}) { id } }'
        assert embedded_documents(raw) == []
        assert embedded_documents("query {") == []

    def test_invalid_query_raises(self, schema: GraphQLSchema) -> None:
        with pytest.raises(GraphQLSyntaxError):
            operation_references(schema, "query {")


class TestChangeAffects:
    """Tests for change_affects()."""

    @pytest.mark.parametrize(
        ("path", "refs", "expected"),
        [
            ("Product.barcode", {"Product.barcode"}, True),
            ("Product.barcode", {"Product.id"}, False),
            ("VariantInput.barcode", {"VariantInput"}, True),
            ("VariantInput.barcode", {"VariantInput.id"}, False),
            ("Product", {"Product.id"}, True),
            ("VariantInput", {"VariantInput"}, True),
            ("Product", {"ProductConnection.nodes"}, False),
            ("@deprecated", {"Product.id"}, False),
        ],
    )
    def test_rules(self, path: str, refs: set[str], expected: bool) -> None:
        assert change_affects(path, refs) is expected


class TestMatchSchemaChangesToSurface:
    """Tests for match_schema_changes_to_surface()."""

    def test_breaking_change_to_selected_field_is_high_with_file(
        self,
        sample_old_schema: str,
        sample_new_schema: str,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        changes = diff_schemas(sample_old_schema, sample_new_schema)
        items = match_schema_changes_to_surface(
            changes, sample_old_schema, sample_surface_with_operations
        )
        barcode = next(i for i in items if i.change.path == "Product.barcode")
        assert barcode.severity == Severity.HIGH
        assert barcode.affected_files == [Path("app/routes/products.ts")]
        assert barcode.affected_features == ["GetProducts"]

    def test_change_to_unreferenced_member_is_info(
        self,
        sample_old_schema: str,
        sample_new_schema: str,
        sample_surface_with_operations: AppSurface,
    ) -> None:
        changes = diff_schemas(sample_old_schema, sample_new_schema)
        items = match_schema_changes_to_surface(
            changes, sample_old_schema, sample_surface_with_operations
        )
        sku = next(i for i in items if i.change.path == "ProductInput.sku")
        assert sku.severity == Severity.INFO
        assert sku.affected_files == []
        assert sku.affected_features == []

    def test_dangerous_change_to_referenced_field_is_medium(
        self, sample_old_schema: str, sample_surface_with_operations: AppSurface
    ) -> None:
        change = SchemaChange(
            change_type=SchemaChangeType.OPTIONAL_ARG_ADDED,
            criticality=Criticality.DANGEROUS,
            path="Query.products",
            message="An optional arg filter on Query.products was added.",
        )
        items = match_schema_changes_to_surface(
            [change], sample_old_schema, sample_surface_with_operations
        )
        assert items[0].severity == Severity.MEDIUM
        assert items[0].affected_features == ["GetProducts"]

    def test_deprecation_of_selected_field_is_medium(
        self, sample_old_schema: str, sample_surface_with_operations: AppSurface
    ) -> None:
        change = SchemaChange(
            change_type=SchemaChangeType.FIELD_DEPRECATED,
            criticality=Criticality.NON_BREAKING,
            path="Product.barcode",
            message="Product.barcode was deprecated: Use barcodes",
        )
        items = match_schema_changes_to_surface(
            [change], sample_old_schema, sample_surface_with_operations
        )
        assert items[0].severity == Severity.MEDIUM
        assert items[0].affected_features == ["GetProducts"]

    def test_input_type_passed_by_variable_attributes_its_field_changes(
        self, sample_old_schema: str, sample_new_schema: str
    ) -> None:
        """A required field added to an input the mutation passes by variable is attributed."""
        surface = AppSurface(
            api_version="2026-04",
            graphql_operations=[
                _op(
                    "CreateProduct",
                    "mutation CreateProduct($input: ProductInput!) "
                    "{ productCreate(input: $input) { product { id } } }",
                    file="app/routes/create.ts",
                )
            ],
        )
        changes = diff_schemas(sample_old_schema, sample_new_schema)
        items = match_schema_changes_to_surface(changes, sample_old_schema, surface)
        sku = next(i for i in items if i.change.path == "ProductInput.sku")
        assert sku.severity == Severity.HIGH
        assert sku.affected_files == [Path("app/routes/create.ts")]
        assert sku.affected_features == ["CreateProduct"]

    def test_unparsable_operation_is_skipped_with_warning(
        self, sample_old_schema: str, sample_schema_change: SchemaChange, caplog: Any
    ) -> None:
        surface = AppSurface(
            api_version="2026-04",
            graphql_operations=[_op("Broken", "query Broken {")],
        )
        with caplog.at_level(logging.WARNING):
            items = match_schema_changes_to_surface(
                [sample_schema_change], sample_old_schema, surface
            )
        assert items[0].severity == Severity.INFO
        assert "Skipping operation Broken" in caplog.text

    def test_files_and_features_are_deduplicated(
        self, sample_old_schema: str, sample_schema_change: SchemaChange
    ) -> None:
        surface = AppSurface(
            api_version="2026-04",
            graphql_operations=[
                _op("A", "query A { products { nodes { barcode } } }"),
                _op("B", "query B { products { nodes { barcode } } }"),
            ],
        )
        items = match_schema_changes_to_surface([sample_schema_change], sample_old_schema, surface)
        assert items[0].affected_files == [Path("app/routes/products.ts")]
        assert items[0].affected_features == ["A", "B"]

    def test_no_operations_scores_everything_info(
        self, sample_old_schema: str, sample_schema_change: SchemaChange
    ) -> None:
        items = match_schema_changes_to_surface(
            [sample_schema_change], sample_old_schema, AppSurface(api_version="2026-04")
        )
        assert items[0].severity == Severity.INFO
