"""Verification pass — checks the inventory against the pinned and target schemas.

The deterministic counterpart to reviewing scry's findings by hand: every
inventoried operation is validated against the schema the project pins and
against the newest published one, and members the operations use that are
already deprecated on the pinned version are listed. Schema tasks in the
generated task files are accepted by exactly this check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from graphql import GraphQLError, build_schema, parse, validate

from scry.collect.schema import SchemaCollector
from scry.diff.references import operation_references
from scry.diff.schema import deprecated_members
from scry.inventory import read_source_files, run_all_extractors
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
class VersionPin:
    file: Path
    line: int
    value: str


@dataclass
class VerifyResult:
    current_version: str
    target_version: str | None = None
    checks: list[OperationCheck] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    deprecated_uses: list[DeprecatedUse] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    pins: list[VersionPin] | None = None  # None when no version_pin_pattern is configured

    @property
    def failed(self) -> list[OperationCheck]:
        return [check for check in self.checks if check.errors]

    @property
    def pin_values(self) -> list[str]:
        """Distinct pinned values, the api_version_source first."""
        values = [self.current_version]
        for pin in self.pins or []:
            if pin.value not in values:
                values.append(pin.value)
        return values


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


def find_version_pins(config: ProjectConfig, source_files: dict[Path, str]) -> list[VersionPin]:
    """Every match of version_pin_pattern in the given files, as (file, line, value).

    The value is the first non-empty capture group, or the whole match when
    the pattern has no groups.
    """
    if not config.version_pin_pattern:
        return []
    pattern = re.compile(config.version_pin_pattern)
    pins: list[VersionPin] = []
    for path in sorted(source_files):
        for lineno, line in enumerate(source_files[path].splitlines(), 1):
            for match in pattern.finditer(line):
                value = next((g for g in match.groups() if g), match.group(0))
                pins.append(VersionPin(path, lineno, value))
    return pins


def _pin_scan_files(config: ProjectConfig) -> dict[Path, str]:
    """Source files plus any version_pin_globs (config files outside source_patterns)."""
    files = dict(read_source_files(config))
    for glob in config.version_pin_globs:
        for path in sorted(config.root.glob(glob)):
            if path.is_file() and path not in files:
                files[path] = path.read_text(encoding="utf-8", errors="replace")
    return files


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
    if config.version_pin_pattern:
        result.pins = find_version_pins(config, _pin_scan_files(config))
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
    lines.extend(["", "## Version pins", ""])
    if result.pins is None:
        lines.append("Set `version_pin_pattern` in the manifest to audit pinned API versions.")
    else:
        lines.append(f"- `api_version_source`: {result.current_version}")
        if result.pins:
            lines.extend(["", "| File | Line | Value |", "|---|---|---|"])
            for pin in result.pins:
                lines.append(f"| {_relative(pin.file, config.root)} | {pin.line} | {pin.value} |")
        lines.append("")
        values = result.pin_values
        if len(values) > 1:
            lines.append("Pinned versions disagree: " + ", ".join(values) + ".")
        else:
            lines.append(f"All pins agree on {values[0]}.")
    lines.append("")
    return "\n".join(lines)
