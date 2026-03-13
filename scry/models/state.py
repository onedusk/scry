"""Models for persistent run state."""

from datetime import datetime

from pydantic import BaseModel, Field


class RunRecord(BaseModel):
    """Record of a single monitor run."""

    timestamp: datetime
    project: str  # Project name from manifest
    changes_detected: int
    impacts_found: int
    report_path: str  # Relative path to generated report


class RunState(BaseModel):
    """Persistent state across runs, stored in history.json."""

    last_run: datetime | None = None
    known_change_ids: set[str] = Field(default_factory=set)
    runs: list[RunRecord] = []

    def is_known(self, change_id: str) -> bool:
        """Check if a change has already been seen in a previous run."""
        return change_id in self.known_change_ids

    def record_change(self, change_id: str) -> None:
        """Mark a change as known."""
        self.known_change_ids.add(change_id)
