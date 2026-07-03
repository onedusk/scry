"""Tests for collector gating and entry-point registration."""

import logging
from pathlib import Path
from typing import Any

import scry.collect
from scry.collect import (
    BUILTIN_COLLECTORS,
    ENTRY_POINT_GROUP,
    PolarisCollector,
    load_collectors,
    run_all_collectors,
)
from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource

_ALL_BUILTIN_NAMES = list(BUILTIN_COLLECTORS)


def _make_config(tmp_path: Path, disabled: list[str] | None = None) -> ProjectConfig:
    return ProjectConfig(
        name="test",
        root=tmp_path,
        platform="shopify",
        api_version_source="x:y",
        source_patterns=[],
        disabled_collectors=disabled or [],
    )


class _PluginCollector:
    """Minimal third-party collector for entry-point tests."""

    def collect(self, config: ProjectConfig) -> list[ChangeRecord]:
        return [
            ChangeRecord(
                source=ChangeSource.CHANGELOG,
                title="plugin change",
                description="from a plugin collector",
                category=ChangeCategory.PLATFORM,
            )
        ]


class _RaisingCollector:
    """Collector whose collect() always raises, for failure-isolation tests."""

    def collect(self, config: ProjectConfig) -> list[ChangeRecord]:
        raise RuntimeError("collector blew up")


class _FakeEntryPoint:
    def __init__(self, name: str, factory: Any) -> None:
        self.name = name
        self._factory = factory

    def load(self) -> Any:
        return self._factory


def _patch_entry_points(monkeypatch: Any, eps: list[_FakeEntryPoint]) -> None:
    def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        assert group == ENTRY_POINT_GROUP
        return eps

    monkeypatch.setattr(scry.collect, "entry_points", fake_entry_points)


class TestLoadCollectors:
    def test_all_builtins_enabled_by_default(self, tmp_path: Path) -> None:
        """Default config instantiates every built-in collector."""
        collectors = load_collectors(_make_config(tmp_path))
        types = {type(c) for c in collectors}
        assert types == {type(factory()) for factory in BUILTIN_COLLECTORS.values()}

    def test_disabled_collector_is_skipped(self, tmp_path: Path) -> None:
        """A name in disabled_collectors gates that built-in off."""
        collectors = load_collectors(_make_config(tmp_path, disabled=["polaris"]))
        assert not any(isinstance(c, PolarisCollector) for c in collectors)
        assert len(collectors) == len(BUILTIN_COLLECTORS) - 1

    def test_all_builtins_can_be_disabled(self, tmp_path: Path) -> None:
        """Disabling every built-in leaves no collectors."""
        collectors = load_collectors(_make_config(tmp_path, disabled=_ALL_BUILTIN_NAMES))
        assert collectors == []

    def test_entry_point_plugin_is_loaded(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Collectors registered under the entry-point group are instantiated."""
        _patch_entry_points(monkeypatch, [_FakeEntryPoint("myplugin", _PluginCollector)])
        collectors = load_collectors(_make_config(tmp_path, disabled=_ALL_BUILTIN_NAMES))
        assert len(collectors) == 1
        assert isinstance(collectors[0], _PluginCollector)

    def test_entry_point_plugin_can_be_disabled(self, tmp_path: Path, monkeypatch: Any) -> None:
        """disabled_collectors also gates entry-point collectors by name."""
        _patch_entry_points(monkeypatch, [_FakeEntryPoint("myplugin", _PluginCollector)])
        disabled = [*_ALL_BUILTIN_NAMES, "myplugin"]
        collectors = load_collectors(_make_config(tmp_path, disabled=disabled))
        assert collectors == []

    def test_entry_point_load_failure_is_tolerated(self, tmp_path: Path, monkeypatch: Any) -> None:
        """A plugin that fails to load does not break the built-ins."""

        def _boom() -> None:
            raise RuntimeError("bad plugin")

        class _BrokenEntryPoint(_FakeEntryPoint):
            def load(self) -> Any:
                raise ImportError("cannot import plugin")

        _patch_entry_points(
            monkeypatch,
            [_BrokenEntryPoint("broken", None), _FakeEntryPoint("exploding", _boom)],
        )
        collectors = load_collectors(_make_config(tmp_path))
        assert len(collectors) == len(BUILTIN_COLLECTORS)


class TestRunAllCollectors:
    def test_all_disabled_returns_empty_result(self, tmp_path: Path) -> None:
        """With every collector disabled, the result is empty and schema fields unset."""
        result = run_all_collectors(_make_config(tmp_path, disabled=_ALL_BUILTIN_NAMES))
        assert result.changes == []
        assert result.old_schema_sdl is None
        assert result.new_schema_sdl is None

    def test_plugin_changes_are_merged(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Changes from an entry-point collector land in the merged result."""
        _patch_entry_points(monkeypatch, [_FakeEntryPoint("myplugin", _PluginCollector)])
        result = run_all_collectors(_make_config(tmp_path, disabled=_ALL_BUILTIN_NAMES))
        assert len(result.changes) == 1
        assert result.changes[0].title == "plugin change"

    def test_raising_collector_is_recorded_and_isolated(
        self, tmp_path: Path, monkeypatch: Any, caplog: Any
    ) -> None:
        """A collector that raises is logged as failed; others still contribute."""
        _patch_entry_points(
            monkeypatch,
            [_FakeEntryPoint("bad", _RaisingCollector), _FakeEntryPoint("good", _PluginCollector)],
        )
        with caplog.at_level(logging.WARNING):
            result = run_all_collectors(_make_config(tmp_path, disabled=_ALL_BUILTIN_NAMES))
        assert len(result.changes) == 1
        assert result.changes[0].title == "plugin change"
        assert "Collector _RaisingCollector failed" in caplog.text
