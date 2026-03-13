"""Tests for scry.diff.schema — GraphQL schema differ."""

import pytest

from scry.diff.schema import _extract_path, diff_schemas
from scry.models.enums import Criticality, SchemaChangeType


class TestDiffSchemas:
    """Tests for diff_schemas()."""

    def test_detects_field_removed(
        self, sample_old_schema: str, sample_new_schema: str
    ) -> None:
        changes = diff_schemas(sample_old_schema, sample_new_schema)
        removed = [c for c in changes if c.change_type == SchemaChangeType.FIELD_REMOVED]
        assert len(removed) == 1
        assert removed[0].criticality == Criticality.BREAKING
        assert removed[0].path == "Product.barcode"

    def test_detects_required_input_field_added(
        self, sample_old_schema: str, sample_new_schema: str
    ) -> None:
        changes = diff_schemas(sample_old_schema, sample_new_schema)
        added = [
            c
            for c in changes
            if c.change_type == SchemaChangeType.REQUIRED_INPUT_FIELD_ADDED
        ]
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

    def test_identical_schemas_produce_no_changes(
        self, sample_old_schema: str
    ) -> None:
        changes = diff_schemas(sample_old_schema, sample_old_schema)
        assert changes == []

    def test_invalid_sdl_raises_error(self) -> None:
        with pytest.raises(Exception):
            diff_schemas("not valid graphql", "type Query { x: Int }")


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
