"""GraphQL schema differ using graphql-core."""

import re

from graphql import (
    GraphQLEnumType,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLObjectType,
    GraphQLSchema,
    build_schema,
    find_breaking_changes,
    find_dangerous_changes,
)

from scry.models.changes import SchemaChange
from scry.models.enums import Criticality, SchemaChangeType

_TYPE_FIELD_PATTERN = re.compile(r"\b([A-Z]\w+\.\w+)\b")
_FIELD_ON_TYPE_PATTERN = re.compile(r"field (\w+) on (?:input )?type (\w+)")
_DIRECTIVE_PATTERN = re.compile(r"^(@\w+) was ")
_ENUM_VALUE_PATTERN = re.compile(r"^(\w+) was (?:removed from|added to) enum type (\w+)\.")
_NAME_WAS_PATTERN = re.compile(r"^(\w+) was ")


def _extract_path(description: str) -> str:
    """Extract Type.field path from a graphql-core change description.

    Handles formats like:
    - "Product.barcode was removed." → "Product.barcode"
    - "A required field sku on input type ProductInput was added." → "ProductInput.sku"
    - "@deprecated was removed." → "@deprecated"
    - "RED was removed from enum type Color." → "Color.RED"
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
    match = _ENUM_VALUE_PATTERN.search(description)
    if match:
        return f"{match.group(2)}.{match.group(1)}"
    match = _NAME_WAS_PATTERN.search(description)
    if match:
        return match.group(1)
    return description


def deprecated_members(schema: GraphQLSchema) -> dict[str, tuple[SchemaChangeType, str]]:
    """Map "Type.member" to (change type, reason) for every deprecated field,
    input field, and enum value in the schema."""
    members: dict[str, tuple[SchemaChangeType, str]] = {}
    for type_name, gql_type in schema.type_map.items():
        if type_name.startswith("__"):
            continue
        if isinstance(gql_type, GraphQLObjectType | GraphQLInterfaceType | GraphQLInputObjectType):
            for field_name, field in gql_type.fields.items():
                if field.deprecation_reason is not None:
                    members[f"{type_name}.{field_name}"] = (
                        SchemaChangeType.FIELD_DEPRECATED,
                        field.deprecation_reason,
                    )
        elif isinstance(gql_type, GraphQLEnumType):
            for value_name, value in gql_type.values.items():
                if value.deprecation_reason is not None:
                    members[f"{type_name}.{value_name}"] = (
                        SchemaChangeType.ENUM_VALUE_DEPRECATED,
                        value.deprecation_reason,
                    )
    return members


def _find_deprecations(old_schema: GraphQLSchema, new_schema: GraphQLSchema) -> list[SchemaChange]:
    """Return members deprecated in new_schema that were not deprecated in old_schema.

    graphql-core's find_breaking_changes/find_dangerous_changes only cover
    removals and additions, so a field that merely gains @deprecated would
    otherwise go unreported until it is removed.
    """
    already = deprecated_members(old_schema)
    return [
        SchemaChange(
            change_type=change_type,
            criticality=Criticality.NON_BREAKING,
            path=path,
            message=f"{path} was deprecated: {reason}",
        )
        for path, (change_type, reason) in deprecated_members(new_schema).items()
        if path not in already
    ]


def diff_schemas(old_sdl: str, new_sdl: str) -> list[SchemaChange]:
    """Diff two GraphQL SDL schemas and return detected changes.

    Breaking and dangerous changes come from graphql-core; newly deprecated
    fields, input fields, and enum values are added by scry's own pass.
    """
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

    changes.extend(_find_deprecations(old_schema, new_schema))

    return changes
