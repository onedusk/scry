"""Task list generator — progressive-decomposition Stage 3/4 files from scored impacts.

Writes the layout the `decompose` skill and binary expect
(`docs/decompose/<name>/stage-3-task-index.md` plus `tasks_mNN.md`) so a
run's findings can be picked up with `/decompose <name> review` or refined
with `/decompose <name> 4`. Stages 1 and 2 (design pack, skeletons) do not
apply: the work is applying upstream changes to an existing project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from scry.models.changes import SchemaChange
from scry.models.config import ProjectConfig
from scry.models.enums import Criticality, SchemaChangeType, Severity
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface
from scry.report._format import item_description, item_title

_MILESTONES: list[tuple[str, tuple[Severity, ...]]] = [
    ("Action required", (Severity.CRITICAL, Severity.HIGH)),
    ("Review", (Severity.MEDIUM,)),
    ("Optional", (Severity.LOW,)),
]
_DEPENDENCY_MANIFESTS = ("package.json", "pyproject.toml", "Gemfile.lock", "go.mod")
_DEPRECATION_TYPES = {
    SchemaChangeType.FIELD_DEPRECATED,
    SchemaChangeType.ENUM_VALUE_DEPRECATED,
}
_REQUIRED_TYPES = {
    SchemaChangeType.REQUIRED_INPUT_FIELD_ADDED,
    SchemaChangeType.REQUIRED_ARG_ADDED,
    SchemaChangeType.REQUIRED_DIRECTIVE_ARG_ADDED,
}


def decomposition_name(config: ProjectConfig, when: date) -> str:
    """Kebab-case decomposition name for a run, e.g. "shopify-changes-2026-09"."""
    platform = re.sub(r"[^a-z0-9]+", "-", config.platform.lower()).strip("-") or "platform"
    return f"{platform}-changes-{when:%Y-%m}"


@dataclass
class _Task:
    id: str
    title: str
    file: str | None
    outline: list[str]
    acceptance: str


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _task_files(item: ImpactItem, config: ProjectConfig, surface: AppSurface) -> list[str | None]:
    """Files a task should name: matched operations, else the config a cited feature lives in."""
    files = [_relative(f, config.root) for f in item.affected_files]
    if files:
        return list(dict.fromkeys(files))
    features = set(item.affected_features)
    candidates: list[str] = []
    if config.webhook_config_path and features & set(surface.webhook_topics):
        candidates.append(config.webhook_config_path)
    if features & set(surface.dependencies):
        candidates.extend(name for name in _DEPENDENCY_MANIFESTS if (config.root / name).is_file())
    return list(dict.fromkeys(candidates)) or [None]


def _title(item: ImpactItem) -> str:
    change = item.change
    if not isinstance(change, SchemaChange):
        return change.title
    if change.change_type in _DEPRECATION_TYPES:
        return f"Stop using deprecated {change.path}"
    if change.change_type in _REQUIRED_TYPES:
        return f"Supply required {change.path}"
    if change.criticality == Criticality.BREAKING:
        return f"Remove use of {change.path}"
    return f"Review {change.path} change"


def _outline(item: ImpactItem, surface: AppSurface, next_api_version: str | None) -> list[str]:
    change = item.change
    lines = [f"What changed: {item_description(item)}"]
    if isinstance(change, SchemaChange):
        lines.append(f"Source: schema diff {surface.api_version} to {next_api_version or 'latest'}")
    else:
        lines.append(f"Source: {change.url or change.source.value}")
    severity = f"Severity: {item.severity.value}"
    if item.deadline:
        severity += f", deadline {item.deadline}"
    lines.append(severity)
    if item.affected_features:
        lines.append("Affected: " + ", ".join(item.affected_features))
    if item.suggested_action:
        lines.append(f"Suggested action: {item.suggested_action}")
    else:
        lines.append(
            "Suggested action: none recorded; determine the migration path before starting"
        )
    return lines


def _acceptance(item: ImpactItem, config: ProjectConfig, next_api_version: str | None) -> str:
    change = item.change
    if isinstance(change, SchemaChange):
        ops = ", ".join(f"`{f}`" for f in item.affected_features) or "The affected operations"
        target = next_api_version or "the target"
        if change.change_type in _DEPRECATION_TYPES:
            return (
                f"{ops} no longer reference `{change.path}`; the replacement named in the "
                "deprecation reason is used instead."
            )
        if change.change_type in _REQUIRED_TYPES:
            return f"{ops} supply `{change.path}` and validate against the {target} schema."
        if change.criticality == Criticality.BREAKING:
            return (
                f"{ops} validate against the {target} schema with no reference to `{change.path}`."
            )
        return f"{ops} handle `{change.path}` explicitly and validate against the {target} schema."
    if item.deadline:
        return (
            f'The change in "{change.title}" is applied and verified in {config.name} '
            f"before {item.deadline}."
        )
    return (
        f'The change in "{change.title}" is applied and verified; the entry no longer '
        f"applies to {config.name}."
    )


def _render_index(
    name: str,
    milestones: list[tuple[str, list[_Task]]],
    config: ProjectConfig,
    when: date,
) -> str:
    lines = [
        f"# Stage 3: Task Index — {name}",
        "",
        f"> Generated by scry on {when} from the impact report in "
        f"{config.report_dir}/{when:%Y-%m}/. This decomposition applies upstream "
        f"{config.platform} changes to {config.name}; Stages 1 and 2 (design pack, "
        f"implementation skeletons) do not apply. Review with `/decompose {name} review`.",
        "",
        "---",
        "",
        "## Legend",
        "",
        "- `[ ]` — Not started",
        "- `[x]` — Complete",
        "- **MODIFY** — edit existing file",
        "- Task IDs: `T-{milestone}.{sequence}` (e.g., T-01.03 = Milestone 1, task 3)",
        "",
        "---",
        "",
        "## Progress",
        "",
        "| # | Milestone | File | Tasks | Done |",
        "|---|-----------|------|:-----:|:----:|",
    ]
    total = 0
    for number, (label, tasks) in enumerate(milestones, 1):
        total += len(tasks)
        lines.append(
            f"| M{number:02d} | {label} | [tasks_m{number:02d}.md](tasks_m{number:02d}.md) "
            f"| {len(tasks)} | 0 |"
        )
    lines.extend(
        [
            f"| | **Total** | | **{total}** | **0** |",
            "",
            "---",
            "",
            "## Milestone Dependencies",
            "",
            "```mermaid",
            "graph LR",
        ]
    )
    if len(milestones) == 1:
        lines.append("    M01")
    for number in range(1, len(milestones)):
        lines.append(f"    M{number:02d} --> M{number + 1:02d}")
    lines.extend(
        [
            "```",
            "",
            "**Critical path:** M01 (required before the next API version or a stated deadline).",
            "",
            "**Parallelizable:** tasks within a milestone address independent changes; later "
            "milestones can start once M01's schema changes are understood.",
            "",
            "---",
            "",
            "## Target Directory Tree",
            "",
            "```",
            f"{config.name}/",
        ]
    )
    by_file: dict[str, list[str]] = {}
    unidentified = 0
    for number, (_, tasks) in enumerate(milestones, 1):
        for task in tasks:
            if task.file is None:
                unidentified += 1
                continue
            tags = by_file.setdefault(task.file, [])
            if f"M{number:02d}" not in tags:
                tags.append(f"M{number:02d}")
    width = max((len(f) for f in by_file), default=0) + 4
    for file, tags in sorted(by_file.items()):
        lines.append(f"  {file.ljust(width)}MODIFY ({', '.join(tags)})")
    lines.extend(
        [
            "```",
            "",
            f"**Totals:** 0 files created, {len(by_file)} modifications, 0 deletions; "
            f"{unidentified} tasks have no file identified yet.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_tasks(number: int, label: str, tasks: list[_Task], config: ProjectConfig) -> str:
    lines = [
        f"# Stage 4: Task Specifications — Milestone {number}: {label}",
        "",
        f"> {len(tasks)} tasks for {config.name}. Generated by scry; refine each outline "
        "against the code before executing.",
        "",
        "---",
        "",
    ]
    for task in tasks:
        file_line = (
            f"  - **File:** `{task.file}` (MODIFY)"
            if task.file
            else "  - **File:** (not identified; see Affected in the outline)"
        )
        lines.extend(
            [
                f"- [ ] **{task.id} — {task.title}**",
                file_line,
                "  - **Depends on:** None",
                "  - **Outline:**",
                *[f"    - {entry}" for entry in task.outline],
                f"  - **Acceptance:** {task.acceptance}",
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)


def generate_task_files(
    impacts: list[ImpactItem],
    config: ProjectConfig,
    surface: AppSurface,
    next_api_version: str | None = None,
    when: date | None = None,
) -> dict[str, str]:
    """Return {filename: markdown} for the task index and one task file per milestone.

    Milestones follow severity: Action required (CRITICAL, HIGH), Review
    (MEDIUM), Optional (LOW); INFO items are not tasks. Each affected file
    of an impact becomes one MODIFY task. Empty when nothing scores LOW or
    higher.
    """
    when = when or datetime.now().date()
    name = decomposition_name(config, when)
    milestones: list[tuple[str, list[_Task]]] = []
    for label, severities in _MILESTONES:
        items = sorted(
            (i for i in impacts if i.severity in severities),
            key=lambda i: (i.deadline or date.max, item_title(i)),
        )
        if not items:
            continue
        number = len(milestones) + 1
        tasks: list[_Task] = []
        for item in items:
            for file in _task_files(item, config, surface):
                tasks.append(
                    _Task(
                        id=f"T-{number:02d}.{len(tasks) + 1:02d}",
                        title=_title(item),
                        file=file,
                        outline=_outline(item, surface, next_api_version),
                        acceptance=_acceptance(item, config, next_api_version),
                    )
                )
        milestones.append((label, tasks))
    if not milestones:
        return {}

    files = {"stage-3-task-index.md": _render_index(name, milestones, config, when)}
    for number, (label, tasks) in enumerate(milestones, 1):
        files[f"tasks_m{number:02d}.md"] = _render_tasks(number, label, tasks, config)
    return files


def write_task_files(
    impacts: list[ImpactItem],
    config: ProjectConfig,
    surface: AppSurface,
    next_api_version: str | None = None,
) -> Path | None:
    """Write this run's decomposition under config.decompose_dir; return the index path.

    A rerun in the same month replaces the directory's task files, so stale
    `tasks_m*.md` from a run with more milestones are removed first.
    """
    when = datetime.now().date()
    files = generate_task_files(impacts, config, surface, next_api_version, when)
    if not files:
        return None
    task_dir = config.root / config.decompose_dir / decomposition_name(config, when)
    task_dir.mkdir(parents=True, exist_ok=True)
    for stale in task_dir.glob("tasks_m*.md"):
        stale.unlink()
    for filename, content in files.items():
        (task_dir / filename).write_text(content)
    return task_dir / "stage-3-task-index.md"
