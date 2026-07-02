"""Summary generator and raw changes exporter."""

import json
from pathlib import Path

from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.enums import Severity
from scry.models.impact import ImpactItem


def generate_summary(impacts: list[ImpactItem], config: ProjectConfig) -> str:
    """Produce a single-paragraph summary of the run results."""
    if not impacts:
        return f"No changes detected that affect {config.name}."

    total = len(impacts)
    affecting = sum(1 for i in impacts if i.affected_files)
    action_required = sum(1 for i in impacts if i.severity in (Severity.CRITICAL, Severity.HIGH))

    deadlines = [i.deadline for i in impacts if i.deadline is not None]
    deadline_clause = ""
    if deadlines:
        earliest = min(deadlines)
        deadline_clause = f" before {earliest}"

    return (
        f"{total} changes detected, {affecting} affect {config.name}, "
        f"{action_required} require action{deadline_clause}."
    )


def generate_cli_summary(impacts: list[ImpactItem], config: ProjectConfig) -> str:
    """Produce a short CLI-friendly summary line."""
    total = len(impacts)
    action_required = sum(1 for i in impacts if i.severity in (Severity.CRITICAL, Severity.HIGH))
    other = total - action_required
    return f"{total} changes | {action_required} action required | {other} other"


def export_raw_changes(changes: list[ChangeRecord], output_path: Path) -> Path:
    """Serialize ChangeRecords to JSON and write to a file."""
    data = [c.model_dump(mode="json") for c in changes]
    output_path.write_text(json.dumps(data, indent=2))
    return output_path


def export_raw_changes_json(changes: list[ChangeRecord]) -> str:
    """Serialize ChangeRecords to a JSON string."""
    data = [c.model_dump(mode="json") for c in changes]
    return json.dumps(data, indent=2)
