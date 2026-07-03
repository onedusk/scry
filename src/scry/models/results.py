"""Result models for pipeline stage outputs."""

from dataclasses import dataclass, field
from pathlib import Path

from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.config import ProjectConfig
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface


@dataclass
class CollectResult:
    """Output of the collect stage."""

    changes: list[ChangeRecord] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    old_schema_sdl: str | None = None  # Current version schema
    new_schema_sdl: str | None = None  # Next version schema
    current_api_version: str | None = None  # Version string for old schema
    next_api_version: str | None = None  # Version string for new schema


@dataclass
class DiffResult:
    """Output of the diff stage."""

    schema_changes: list[SchemaChange] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    impacts: list[ImpactItem] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]


@dataclass
class ReportResult:
    """Output of the report stage."""

    impact_report_path: Path | None = None
    change_plan_path: Path | None = None
    raw_changes_path: Path | None = None


@dataclass
class PipelineResult:
    """Aggregate result of a full pipeline run."""

    config: ProjectConfig
    collect: CollectResult
    surface: AppSurface
    diff: DiffResult
    report: ReportResult
    failed_stages: list[str] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
