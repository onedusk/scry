"""GraphQL schema differ using graphql-core."""

import re

from graphql import build_schema, find_breaking_changes, find_dangerous_changes

from scry.models.changes import SchemaChange
from scry.models.enums import Criticality, SchemaChangeType

_TYPE_FIELD_PATTERN = re.compile(r"\b([A-Z]\w+\.\w+)\b")
_FIELD_ON_TYPE_PATTERN = re.compile(r"field (\w+) on (?:input )?type (\w+)")
_DIRECTIVE_PATTERN = re.compile(r"^(@\w+) was ")
_NAME_WAS_PATTERN = re.compile(r"^(\w+) was ")


def _extract_path(description: str) -> str:
    """Extract Type.field path from a graphql-core change description.

    Handles formats like:
    - "Product.barcode was removed." → "Product.barcode"
    - "A required field sku on input type ProductInput was added." → "ProductInput.sku"
    - "@deprecated was removed." → "@deprecated"
    - "ProductType was removed." → "ProductType"
    """
    match = _TYPE_FIELD_PATTERN.search(description)
    if match:
        return match.group(1)
    match = _FIELD_ON_TYPE_PATTERN.search(description)
    if match:
        return f"{match.group(2)}.{match.group(1)}"
    match = _DIRECTIVE_PATTERN.search(description)
    if match:
        return match.group(1)
    match = _NAME_WAS_PATTERN.search(description)
    if match:
        return match.group(1)
    return description


def diff_schemas(old_sdl: str, new_sdl: str) -> list[SchemaChange]:
    """Diff two GraphQL SDL schemas and return detected changes."""
    old_schema = build_schema(old_sdl)
    new_schema = build_schema(new_sdl)

    changes: list[SchemaChange] = []

    for change in find_breaking_changes(old_schema, new_schema):
        changes.append(
            SchemaChange(
                change_type=SchemaChangeType[change.type.name],
                criticality=Criticality.BREAKING,
                path=_extract_path(change.description),
                message=change.description,
            )
        )

    for change in find_dangerous_changes(old_schema, new_schema):
        changes.append(
            SchemaChange(
                change_type=SchemaChangeType[change.type.name],
                criticality=Criticality.DANGEROUS,
                path=_extract_path(change.description),
                message=change.description,
            )
        )

    return changes
