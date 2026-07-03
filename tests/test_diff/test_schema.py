"""Tests for scry.diff.schema — GraphQL schema differ."""

import pytest
from graphql import GraphQLSyntaxError

from scry.diff.schema import _extract_path, diff_schemas
from scry.models.enums import Criticality, SchemaChangeType


class TestDiffSchemas:
    """Tests for diff_schemas()."""

    def test_detects_field_removed(self, sample_old_schema: str, sample_new_schema: str) -> None:
        changes = diff_schemas(sample_old_schema, sample_new_schema)
        removed = [c for c in changes if c.change_type == SchemaChangeType.FIELD_REMOVED]
        assert len(removed) == 1
        assert removed[0].criticality == Criticality.BREAKING
        assert removed[0].path == "Product.barcode"

    def test_detects_required_input_field_added(
        self, sample_old_schema: str, sample_new_schema: str
    ) -> None:
        changes = diff_schemas(sample_old_schema, sample_new_schema)
        added = [c for c in changes if c.change_type == SchemaChangeType.REQUIRED_INPUT_FIELD_ADDED]
        assert len(added) == 1
        assert added[0].criticality == Criticality.BREAKING
        assert added[0].path == "ProductInput.sku"

    def test_optional_arg_is_dangerous(self) -> None:
        old_sdl = "type Query { products(first: Int): String }"
        new_sdl = "type Query { products(first: Int, filter: String): String }"
        changes = diff_schemas(old_sdl, new_sdl)
        assert len(changes) == 1
        assert changes[0].change_type == SchemaChangeType.OPTIONAL_ARG_ADDED
        assert changes[0].criticality == Criticality.DANGEROUS

    def test_identical_schemas_produce_no_changes(self, sample_old_schema: str) -> None:
        changes = diff_schemas(sample_old_schema, sample_old_schema)
        assert changes == []

    def test_invalid_sdl_raises_error(self) -> None:
        with pytest.raises(GraphQLSyntaxError):
            diff_schemas("not valid graphql", "type Query { x: Int }")


# One minimal SDL pair per graphql-core breaking/dangerous change type:
# (old_sdl, new_sdl, expected change_type, expected criticality).
_CHANGE_TYPE_CASES: list[tuple[str, str, SchemaChangeType, Criticality]] = [
    # Breaking changes
    (
        "type Query { a: String } type Legacy { x: String }",
        "type Query { a: String }",
        SchemaChangeType.TYPE_REMOVED,
        Criticality.BREAKING,
    ),
    (
        "type Query { a: String } type Thing { x: Int }",
        "type Query { a: String } interface Thing { x: Int }",
        SchemaChangeType.TYPE_CHANGED_KIND,
        Criticality.BREAKING,
    ),
    (
        "type Query { s: Result } type A { x: Int } type B { y: Int } union Result = A | B",
        "type Query { s: Result } type A { x: Int } type B { y: Int } union Result = A",
        SchemaChangeType.TYPE_REMOVED_FROM_UNION,
        Criticality.BREAKING,
    ),
    (
        "type Query { c: Color } enum Color { RED GREEN }",
        "type Query { c: Color } enum Color { RED }",
        SchemaChangeType.VALUE_REMOVED_FROM_ENUM,
        Criticality.BREAKING,
    ),
    (
        "type Query { a(i: Filter): String } input Filter { name: String }",
        "type Query { a(i: Filter): String } input Filter { name: String sku: String! }",
        SchemaChangeType.REQUIRED_INPUT_FIELD_ADDED,
        Criticality.BREAKING,
    ),
    (
        "interface Node { id: ID } type Query { p: Item } type Item implements Node { id: ID }",
        "interface Node { id: ID } type Query { p: Item } type Item { id: ID }",
        SchemaChangeType.IMPLEMENTED_INTERFACE_REMOVED,
        Criticality.BREAKING,
    ),
    (
        "type Query { a: String b: String }",
        "type Query { a: String }",
        SchemaChangeType.FIELD_REMOVED,
        Criticality.BREAKING,
    ),
    (
        "type Query { a: String }",
        "type Query { a: Int }",
        SchemaChangeType.FIELD_CHANGED_KIND,
        Criticality.BREAKING,
    ),
    (
        "type Query { products: String }",
        "type Query { products(first: Int!): String }",
        SchemaChangeType.REQUIRED_ARG_ADDED,
        Criticality.BREAKING,
    ),
    (
        "type Query { products(first: Int): String }",
        "type Query { products: String }",
        SchemaChangeType.ARG_REMOVED,
        Criticality.BREAKING,
    ),
    (
        "type Query { products(first: Int): String }",
        "type Query { products(first: String): String }",
        SchemaChangeType.ARG_CHANGED_KIND,
        Criticality.BREAKING,
    ),
    (
        "directive @track on FIELD_DEFINITION type Query { a: String }",
        "type Query { a: String }",
        SchemaChangeType.DIRECTIVE_REMOVED,
        Criticality.BREAKING,
    ),
    (
        "directive @track(label: String) on FIELD_DEFINITION type Query { a: String }",
        "directive @track on FIELD_DEFINITION type Query { a: String }",
        SchemaChangeType.DIRECTIVE_ARG_REMOVED,
        Criticality.BREAKING,
    ),
    (
        "directive @track on FIELD_DEFINITION type Query { a: String }",
        "directive @track(label: String!) on FIELD_DEFINITION type Query { a: String }",
        SchemaChangeType.REQUIRED_DIRECTIVE_ARG_ADDED,
        Criticality.BREAKING,
    ),
    (
        "directive @tag repeatable on FIELD_DEFINITION type Query { a: String }",
        "directive @tag on FIELD_DEFINITION type Query { a: String }",
        SchemaChangeType.DIRECTIVE_REPEATABLE_REMOVED,
        Criticality.BREAKING,
    ),
    (
        "directive @tag on FIELD_DEFINITION | OBJECT type Query { a: String }",
        "directive @tag on FIELD_DEFINITION type Query { a: String }",
        SchemaChangeType.DIRECTIVE_LOCATION_REMOVED,
        Criticality.BREAKING,
    ),
    # Dangerous changes
    (
        "type Query { c: Color } enum Color { RED }",
        "type Query { c: Color } enum Color { RED GREEN }",
        SchemaChangeType.VALUE_ADDED_TO_ENUM,
        Criticality.DANGEROUS,
    ),
    (
        "type Query { s: Result } type A { x: Int } type B { y: Int } union Result = A",
        "type Query { s: Result } type A { x: Int } type B { y: Int } union Result = A | B",
        SchemaChangeType.TYPE_ADDED_TO_UNION,
        Criticality.DANGEROUS,
    ),
    (
        "type Query { a(i: Filter): String } input Filter { name: String }",
        "type Query { a(i: Filter): String } input Filter { name: String note: String }",
        SchemaChangeType.OPTIONAL_INPUT_FIELD_ADDED,
        Criticality.DANGEROUS,
    ),
    (
        "type Query { products(first: Int): String }",
        "type Query { products(first: Int, filter: String): String }",
        SchemaChangeType.OPTIONAL_ARG_ADDED,
        Criticality.DANGEROUS,
    ),
    (
        "interface Node { id: ID } type Query { p: Item } type Item { id: ID }",
        "interface Node { id: ID } type Query { p: Item } type Item implements Node { id: ID }",
        SchemaChangeType.IMPLEMENTED_INTERFACE_ADDED,
        Criticality.DANGEROUS,
    ),
    (
        "type Query { products(first: Int = 10): String }",
        "type Query { products(first: Int = 20): String }",
        SchemaChangeType.ARG_DEFAULT_VALUE_CHANGE,
        Criticality.DANGEROUS,
    ),
]


class TestAllChangeTypes:
    """One focused case per breaking and dangerous change type graphql-core can emit."""

    @pytest.mark.parametrize(
        ("old_sdl", "new_sdl", "change_type", "criticality"),
        _CHANGE_TYPE_CASES,
        ids=[case[2].value for case in _CHANGE_TYPE_CASES],
    )
    def test_change_type_maps_to_criticality(
        self,
        old_sdl: str,
        new_sdl: str,
        change_type: SchemaChangeType,
        criticality: Criticality,
    ) -> None:
        changes = diff_schemas(old_sdl, new_sdl)
        matches = [c for c in changes if c.change_type == change_type]
        assert len(matches) == 1
        assert matches[0].criticality == criticality

    def test_cases_cover_every_schema_change_type(self) -> None:
        covered = {case[2] for case in _CHANGE_TYPE_CASES}
        assert covered == set(SchemaChangeType)


class TestExtractPath:
    """Tests for _extract_path() helper."""

    def test_type_dot_field(self) -> None:
        assert _extract_path("Product.barcode was removed.") == "Product.barcode"

    def test_field_on_input_type(self) -> None:
        desc = "A required field sku on input type ProductInput was added."
        assert _extract_path(desc) == "ProductInput.sku"

    def test_type_name_only(self) -> None:
        assert _extract_path("OldType was removed.") == "OldType"

    def test_directive_removed(self) -> None:
        assert _extract_path("@deprecated was removed.") == "@deprecated"

    def test_fallback_to_full_description(self) -> None:
        desc = "something unexpected happened"
        assert _extract_path(desc) == desc
