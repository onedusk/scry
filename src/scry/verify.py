"""Verification pass — checks the inventory against the pinned and target schemas.

The deterministic counterpart to reviewing scry's findings by hand: every
inventoried operation is validated against the schema the project pins and
against the newest published one, and members the operations use that are
already deprecated on the pinned version are listed. Schema tasks in the
generated task files are accepted by exactly this check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from graphql import GraphQLError, build_schema, parse, validate

from scry.collect.schema import SchemaCollector
from scry.diff.references import operation_references
from scry.diff.schema import deprecated_members
from scry.inventory import run_all_extractors
from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


@dataclass
class OperationCheck:
    operation: str
    file: Path
    version: str
    errors: list[str]


@dataclass
class DeprecatedUse:
    operation: str
    file: Path
    path: str
    reason: str


@dataclass
class VerifyResult:
    current_version: str
    target_version: str | None = None
    checks: list[OperationCheck] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    deprecated_uses: list[DeprecatedUse] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]

    @property
    def failed(self) -> list[OperationCheck]:
        return [check for check in self.checks if check.errors]


def check_operations(surface: AppSurface, sdl: str, version: str) -> list[OperationCheck]:
    """Validate every inventoried operation against the schema for `version`."""
    schema = build_schema(sdl)
    checks: list[OperationCheck] = []
    for op in surface.graphql_operations:
        try:
            errors = [error.message for error in validate(schema, parse(op.raw_query))]
        except GraphQLError as error:
            errors = [error.message]
        checks.append(OperationCheck(op.name, op.file, version, errors))
    return checks


def deprecation_debt(surface: AppSurface, sdl: str) -> list[DeprecatedUse]:
    """Members the project's operations reference that `sdl` already marks deprecated."""
    schema = build_schema(sdl)
    deprecated = deprecated_members(schema)
    uses: list[DeprecatedUse] = []
    for op in surface.graphql_operations:
        try:
            refs = operation_references(schema, op.raw_query)
        except GraphQLError:
            continue
        for path in sorted(refs):
            if path in deprecated:
                uses.append(DeprecatedUse(op.name, op.file, path, deprecated[path][1]))
    return uses


def run_verify(config: ProjectConfig) -> VerifyResult:
    """Fetch (or reuse cached) schemas, inventory the project, and run every check."""
    collector = SchemaCollector()
    collector.collect(config)
    if collector.old_schema_sdl is None or collector.current_api_version is None:
        msg = "no schema for the pinned API version; set schema_base_url and run `scry doctor`"
        raise RuntimeError(msg)
    surface = run_all_extractors(config)
    result = VerifyResult(
        current_version=collector.current_api_version,
        target_version=collector.next_api_version,
    )
    result.checks = check_operations(surface, collector.old_schema_sdl, result.current_version)
    if collector.new_schema_sdl is not None and collector.next_api_version is not None:
        result.checks += check_operations(
            surface, collector.new_schema_sdl, collector.next_api_version
        )
    result.deprecated_uses = deprecation_debt(surface, collector.old_schema_sdl)
    return result


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def render_verify(result: VerifyResult, config: ProjectConfig) -> str:
    """Render the result as markdown."""
    versions = [result.current_version]
    if result.target_version:
        versions.append(result.target_version)
    lines = [
        f"# Verification -- {config.name}",
        "",
        f"> Pinned API version: {result.current_version}",
        f"> Target version: {result.target_version or 'none newer published'}",
        "",
        "## Operations",
        "",
    ]
    by_op: dict[tuple[str, Path], dict[str, list[str]]] = {}
    for check in result.checks:
        by_op.setdefault((check.operation, check.file), {})[check.version] = check.errors
    if by_op:
        lines.append("| Operation | File | " + " | ".join(versions) + " |")
        lines.append("|---|---|" + "---|" * len(versions))
        for (operation, file), outcomes in by_op.items():
            cells = [
                "valid" if not outcomes.get(v) else "invalid: " + "; ".join(outcomes[v])
                for v in versions
            ]
            lines.append(
                f"| {operation} | {_relative(file, config.root)} | " + " | ".join(cells) + " |"
            )
    else:
        lines.append("No GraphQL operations inventoried.")
    lines.extend(["", f"## Deprecated members in use ({result.current_version})", ""])
    if result.deprecated_uses:
        lines.append("| Operation | File | Member | Reason |")
        lines.append("|---|---|---|---|")
        for use in result.deprecated_uses:
            lines.append(
                f"| {use.operation} | {_relative(use.file, config.root)} | `{use.path}` "
                f"| {use.reason} |"
            )
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)
