"""Tests for scry.store — state persistence and dedup."""

import json
from pathlib import Path

from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource
from scry.store import (
    filter_new_changes,
    load_state,
    record_run,
    save_state,
    state_path,
)


def _make_config(tmp_path: Path) -> ProjectConfig:
    """Create a ProjectConfig rooted at tmp_path."""
    return ProjectConfig(
        name="test-project",
        root=tmp_path,
        platform="shopify",
        api_version_source="shopify.app.toml:webhooks.api_version",
        source_patterns=["app/**/*.ts"],
    )


def _make_change(title: str = "test change") -> ChangeRecord:
    return ChangeRecord(
        source=ChangeSource.RSS,
        title=title,
        category=ChangeCategory.FEATURE,
    )


class TestStateStore:
    """Tests for load_state, save_state, state_path."""

    def test_state_path(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        assert state_path(config) == tmp_path / ".scry" / "history.json"

    def test_load_fresh_state(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        state = load_state(config)
        assert state.last_run is None
        assert state.known_change_ids == set()
        assert state.runs == []

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        state = load_state(config)
        state.record_change("abc123")

        save_state(state, config)
        loaded = load_state(config)

        assert "abc123" in loaded.known_change_ids

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        state = load_state(config)
        path = save_state(state, config)
        assert path.exists()
        assert (tmp_path / ".scry").is_dir()

    def test_corrupt_json_returns_fresh_state(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        scry_dir = tmp_path / ".scry"
        scry_dir.mkdir()
        history = scry_dir / "history.json"
        history.write_text("not valid json {{{")

        state = load_state(config)
        assert state.last_run is None
        # Backup uses timestamped suffix
        bak_files = list(scry_dir.glob("history.*.bak"))
        assert len(bak_files) == 1

    def test_legacy_unversioned_state_round_trips(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        scry_dir = tmp_path / ".scry"
        scry_dir.mkdir()
        legacy = {
            "last_run": "2026-05-01T12:00:00",
            "known_change_ids": ["id1", "id2"],
            "runs": [
                {
                    "timestamp": "2026-05-01T12:00:00",
                    "project": "test-project",
                    "changes_detected": 2,
                    "impacts_found": 1,
                    "report_path": "docs/report.md",
                }
            ],
        }
        (scry_dir / "history.json").write_text(json.dumps(legacy))

        state = load_state(config)
        assert state.schema_version == 1
        assert state.known_change_ids == {"id1", "id2"}
        assert len(state.runs) == 1
        # Migration is not the corrupt-file path — no backup created
        assert list(scry_dir.glob("history.*.bak")) == []

        save_state(state, config)
        assert '"schema_version": 1' in (scry_dir / "history.json").read_text()
        assert load_state(config) == state

    def test_known_change_ids_serialization(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        state = load_state(config)
        state.record_change("id1")
        state.record_change("id2")
        save_state(state, config)

        loaded = load_state(config)
        assert loaded.known_change_ids == {"id1", "id2"}


class TestFilterNewChanges:
    """Tests for filter_new_changes."""

    def test_excludes_known_ids(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        change = _make_change("known change")
        state = load_state(config)
        state.record_change(change.id)

        result = filter_new_changes([change], state)
        assert result == []

    def test_fresh_state_returns_all(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        changes = [_make_change("a"), _make_change("b")]
        state = load_state(config)

        result = filter_new_changes(changes, state)
        assert len(result) == 2

    def test_empty_changes_returns_empty(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        state = load_state(config)
        assert filter_new_changes([], state) == []


class TestRecordRun:
    """Tests for record_run."""

    def test_adds_change_ids_and_run_record(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        state = load_state(config)
        changes = [_make_change("c1"), _make_change("c2")]

        updated = record_run(state, config, changes, 2, 1, "docs/report.md")

        assert changes[0].id in updated.known_change_ids
        assert changes[1].id in updated.known_change_ids
        assert len(updated.runs) == 1
        assert updated.runs[0].changes_detected == 2
        assert updated.runs[0].impacts_found == 1
        assert updated.last_run is not None
