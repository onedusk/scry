"""Shared enumerations used across all scry models."""

from enum import StrEnum


class ChangeSource(StrEnum):
    """Where a change was detected."""

    RSS = "rss"
    CHANGELOG = "changelog"
    SCHEMA = "schema"
    REGISTRY = "registry"
    POLARIS = "polaris"


class ChangeCategory(StrEnum):
    """Classification of a detected change."""

    BREAKING = "breaking"
    DEPRECATION = "deprecation"
    FEATURE = "feature"
    PLATFORM = "platform"
    SDK = "sdk"


class SchemaChangeType(StrEnum):
    """Kind of GraphQL schema change.

    Aligned with graphql-core's BreakingChangeType and DangerousChangeType enums.
    """

    # Breaking changes (from graphql-core BreakingChangeType)
    TYPE_REMOVED = "type_removed"
    TYPE_CHANGED_KIND = "type_changed_kind"
    TYPE_REMOVED_FROM_UNION = "type_removed_from_union"
    VALUE_REMOVED_FROM_ENUM = "value_removed_from_enum"
    REQUIRED_INPUT_FIELD_ADDED = "required_input_field_added"
    IMPLEMENTED_INTERFACE_REMOVED = "implemented_interface_removed"
    FIELD_REMOVED = "field_removed"
    FIELD_CHANGED_KIND = "field_changed_kind"
    REQUIRED_ARG_ADDED = "required_arg_added"
    ARG_REMOVED = "arg_removed"
    ARG_CHANGED_KIND = "arg_changed_kind"
    DIRECTIVE_REMOVED = "directive_removed"
    DIRECTIVE_ARG_REMOVED = "directive_arg_removed"
    REQUIRED_DIRECTIVE_ARG_ADDED = "required_directive_arg_added"
    DIRECTIVE_REPEATABLE_REMOVED = "directive_repeatable_removed"
    DIRECTIVE_LOCATION_REMOVED = "directive_location_removed"

    # Dangerous changes (from graphql-core DangerousChangeType)
    VALUE_ADDED_TO_ENUM = "value_added_to_enum"
    TYPE_ADDED_TO_UNION = "type_added_to_union"
    OPTIONAL_INPUT_FIELD_ADDED = "optional_input_field_added"
    OPTIONAL_ARG_ADDED = "optional_arg_added"
    IMPLEMENTED_INTERFACE_ADDED = "implemented_interface_added"
    ARG_DEFAULT_VALUE_CHANGE = "arg_default_value_change"


class Criticality(StrEnum):
    """GraphQL schema change criticality level."""

    BREAKING = "breaking"
    DANGEROUS = "dangerous"
    NON_BREAKING = "non_breaking"


class OperationType(StrEnum):
    """GraphQL operation type."""

    QUERY = "query"
    MUTATION = "mutation"


class Severity(StrEnum):
    """Impact severity on a target project, ordered high to low."""

    # Ordered intentionally for display — CRITICAL first
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
