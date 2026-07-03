"""Models for impact analysis results."""

from datetime import date
from pathlib import Path

from pydantic import BaseModel

from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.enums import Severity


class ImpactItem(BaseModel):
    """A change filtered and scored against a target project's actual usage."""

    change: ChangeRecord | SchemaChange
    severity: Severity
    affected_files: list[Path] = []
    affected_features: list[str] = []  # e.g. ["product-sync", "barcode-update"]
    deadline: date | None = None
    suggested_action: str = ""
