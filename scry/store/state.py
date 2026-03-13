"""State persistence — load, save, filter, and record pipeline runs."""

import logging
import os
from datetime import datetime
from pathlib import Path

from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.state import RunRecord, RunState

logger = logging.getLogger(__name__)


def state_path(config: ProjectConfig) -> Path:
    """Return the path to the project's history.json state file."""
    return config.root / ".scry" / "history.json"


def load_state(config: ProjectConfig) -> RunState:
    """Load run state from disk, or return a fresh state if missing/corrupt."""
    path = state_path(config)
    if not path.exists():
        return RunState()

    try:
        return RunState.model_validate_json(path.read_text())
    except Exception:
        logger.warning("Corrupt state file at %s, starting fresh", path, exc_info=True)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        bak = path.with_suffix(f".{timestamp}.bak")
        path.rename(bak)
        return RunState()


def save_state(state: RunState, config: ProjectConfig) -> Path:
    """Persist run state to disk atomically, creating .scry/ directory if needed."""
    path = state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(state.model_dump_json(indent=2))
    os.replace(tmp, path)
    return path


def filter_new_changes(
    changes: list[ChangeRecord], state: RunState
) -> list[ChangeRecord]:
    """Return only changes not already seen in previous runs."""
    return [c for c in changes if not state.is_known(c.id)]


def record_run(
    state: RunState,
    config: ProjectConfig,
    changes: list[ChangeRecord],
    changes_detected: int,
    impacts_found: int,
    report_path: str,
) -> RunState:
    """Update state with a new run record. Does NOT save to disk."""
    now = datetime.now()

    for change in changes:
        state.record_change(change.id)

    state.runs.append(
        RunRecord(
            timestamp=now,
            project=config.name,
            changes_detected=changes_detected,
            impacts_found=impacts_found,
            report_path=report_path,
        )
    )
    state.last_run = now

    return state
