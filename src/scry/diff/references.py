"""Schema-change cross-reference — attributes schema changes to the operations that use them."""

from __future__ import annotations

import logging

from graphql import (
    EnumValueNode,
    FieldNode,
    GraphQLError,
    GraphQLSchema,
    ObjectFieldNode,
    OperationDefinitionNode,
    StringValueNode,
    TypeInfo,
    TypeInfoVisitor,
    VariableDefinitionNode,
    Visitor,
    build_schema,
    get_named_type,
    is_input_object_type,
    parse,
    visit,
)

from scry.models.changes import SchemaChange
from scry.models.enums import Criticality, Severity
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface, GraphQLOperation

logger = logging.getLogger(__name__)

_CRITICALITY_SEVERITY: dict[Criticality, Severity] = {
    Criticality.BREAKING: Severity.HIGH,
    Criticality.DANGEROUS: Severity.MEDIUM,
    # Deprecations: same footing as a DEPRECATION changelog entry.
    Criticality.NON_BREAKING: Severity.MEDIUM,
}


def embedded_documents(raw_query: str) -> list[str]:
    """GraphQL documents passed as string arguments inside an operation.

    Shopify's bulkOperationRunQuery takes the whole query to run as a
    string; the fields it selects are part of the project's API surface
    even though they are not selections of the outer document.
    """
    found: list[str] = []

    class _Strings(Visitor):
        def enter_string_value(self, node: StringValueNode, *_: object) -> None:
            if "{" not in node.value:
                return
            try:
                document = parse(node.value)
            except GraphQLError:
                return
            if any(isinstance(d, OperationDefinitionNode) for d in document.definitions):
                found.append(node.value)

    try:
        visit(parse(raw_query), _Strings())
    except GraphQLError:
        return []
    return found


class _ReferenceVisitor(Visitor):
    """Collects the schema paths an operation touches, resolved through TypeInfo."""

    def __init__(self, type_info: TypeInfo) -> None:
        super().__init__()
        self._type_info = type_info
        self.references: set[str] = set()

    def enter_field(self, node: FieldNode, *_: object) -> None:
        parent = self._type_info.get_parent_type()
        if parent is not None:
            self.references.add(f"{parent.name}.{node.name.value}")

    def enter_object_field(self, node: ObjectFieldNode, *_: object) -> None:
        parent = get_named_type(self._type_info.get_parent_input_type())  # pyright: ignore[reportUnknownMemberType]
        if parent is not None:
            self.references.add(f"{parent.name}.{node.name.value}")

    def enter_enum_value(self, node: EnumValueNode, *_: object) -> None:
        enum_type = get_named_type(self._type_info.get_input_type())  # pyright: ignore[reportUnknownMemberType]
        if enum_type is not None:
            self.references.add(f"{enum_type.name}.{node.value}")

    def enter_variable_definition(self, node: VariableDefinitionNode, *_: object) -> None:
        named = get_named_type(self._type_info.get_input_type())  # pyright: ignore[reportUnknownMemberType]
        if named is not None and is_input_object_type(named):
            # The fields of an input object passed through a variable are supplied
            # at runtime, so the whole type is recorded rather than its fields.
            self.references.add(named.name)


def operation_references(schema: GraphQLSchema, raw_query: str) -> set[str]:
    """Return the schema paths an operation references.

    Selected fields are recorded as "Type.field" (fields inside fragments
    resolve to the fragment's type), inline input objects as
    "InputType.field", enum literals as "EnumType.VALUE", and input object
    types passed through variables by bare type name. GraphQL documents
    embedded in string arguments (bulk operations) are followed. Selections
    that do not exist in `schema` are skipped.

    Raises GraphQLSyntaxError when `raw_query` cannot be parsed.
    """
    type_info = TypeInfo(schema)
    visitor = _ReferenceVisitor(type_info)
    visit(parse(raw_query), TypeInfoVisitor(type_info, visitor))
    references = visitor.references
    for document in embedded_documents(raw_query):
        references |= operation_references(schema, document)
    return references


def change_affects(change_path: str, references: set[str]) -> bool:
    """Whether a schema change at `change_path` touches any of `references`.

    A "Type.field" path matches the same field reference, or a bare "Type"
    reference (an input object whose fields are set at runtime). A bare
    "Type" path matches the type itself or any field referenced on it.
    """
    if change_path in references:
        return True
    type_name, sep, _ = change_path.partition(".")
    if sep:
        return type_name in references
    return any(ref.startswith(f"{change_path}.") for ref in references)


def match_schema_changes_to_surface(
    changes: list[SchemaChange], old_schema_sdl: str, surface: AppSurface
) -> list[ImpactItem]:
    """Score schema changes by the inventoried operations that reference them.

    Operations are resolved against the schema they were written for (the
    project's current version), so removed members still resolve. Breaking
    changes to referenced members score HIGH, dangerous changes and
    deprecations MEDIUM; changes that touch nothing in the inventory score
    INFO.
    """
    schema = build_schema(old_schema_sdl)
    resolved: list[tuple[GraphQLOperation, set[str]]] = []
    for op in surface.graphql_operations:
        try:
            resolved.append((op, operation_references(schema, op.raw_query)))
        except GraphQLError:
            logger.warning("Skipping operation %s in %s: not valid GraphQL", op.name, op.file)

    items: list[ImpactItem] = []
    for change in changes:
        affected = [op for op, refs in resolved if change_affects(change.path, refs)]
        severity = _CRITICALITY_SEVERITY[change.criticality] if affected else Severity.INFO
        items.append(
            ImpactItem(
                change=change,
                severity=severity,
                affected_files=list(dict.fromkeys(op.file for op in affected)),
                affected_features=list(dict.fromkeys(op.name for op in affected)),
            )
        )
    return items
