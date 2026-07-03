"""State store — persistence for pipeline run history and dedup."""

from scry.store.state import (
    filter_new_changes,
    load_state,
    record_run,
    save_state,
    state_path,
)

__all__ = [
    "filter_new_changes",
    "load_state",
    "record_run",
    "save_state",
    "state_path",
]
