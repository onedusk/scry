"""Tests for scry.pipeline and scry.cli — orchestration and CLI integration."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from scry.cli import app
from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource
from scry.models.surface import AppSurface
from scry.models.state import RunState
from scry.pipeline import CollectResult, DiffResult, run_collect, run_diff, run_inventory

runner = CliRunner()


def _make_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test-project",
        root=tmp_path,
        platform="shopify",
        api_version_source="shopify.app.toml:webhooks.api_version",
        source_patterns=["app/**/*.ts"],
    )


class TestPipelineStages:
    """Tests for individual pipeline stage functions."""

    def test_run_collect_returns_collect_result(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        with patch("scry.collect.run_all_collectors") as mock:
            mock.return_value = CollectResult()
            result = run_collect(config)
        assert isinstance(result, CollectResult)

    def test_run_inventory_returns_app_surface(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        with patch("scry.inventory.run_all_extractors") as mock:
            mock.return_value = AppSurface(api_version="2026-04")
            result = run_inventory(config)
        assert isinstance(result, AppSurface)

    def test_run_diff_returns_diff_result(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        collect = CollectResult()
        surface = AppSurface(api_version="2026-04")
        result = run_diff(collect, surface, config)
        assert isinstance(result, DiffResult)
        assert result.impacts == []

    def test_run_diff_with_schema_changes(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        old_sdl = "type Query { products(first: Int): String }"
        new_sdl = "type Query { items(first: Int): String }"
        collect = CollectResult(old_schema_sdl=old_sdl, new_schema_sdl=new_sdl)
        surface = AppSurface(api_version="2026-04")
        result = run_diff(collect, surface, config)
        assert len(result.schema_changes) > 0

    def test_collector_failure_does_not_crash(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        fresh_state = RunState()
        with (
            patch("scry.pipeline.run_collect", side_effect=Exception("network error")),
            patch("scry.pipeline.run_inventory") as mock_inv,
            patch("scry.pipeline.run_diff") as mock_diff,
            patch("scry.report.generate_all_reports") as mock_report,
            patch("scry.store.load_state", return_value=fresh_state),
            patch("scry.store.filter_new_changes", return_value=[]),
            patch("scry.store.record_run", return_value=fresh_state),
            patch("scry.store.save_state"),
        ):
            mock_inv.return_value = AppSurface(api_version="2026-04")
            mock_diff.return_value = DiffResult()
            mock_report.return_value = __import__(
                "scry.pipeline", fromlist=["ReportResult"]
            ).ReportResult()

            from scry.pipeline import run_pipeline

            result = run_pipeline(config)
            assert result.collect.changes == []


class TestCli:
    """Tests for CLI subcommands via CliRunner."""

    def test_help_shows_all_subcommands(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("run", "collect", "inventory", "diff", "report", "init"):
            assert cmd in result.output

    def test_run_help_shows_options(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--project" in result.output
        assert "--verbose" in result.output

    def test_init_creates_manifest(self, tmp_path: Path) -> None:
        with patch("scry.cli.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Created scry.yaml" in result.output
        assert (tmp_path / "scry.yaml").exists()

    def test_init_warns_existing(self, tmp_path: Path) -> None:
        manifest = tmp_path / "scry.yaml"
        manifest.write_text("name: existing")
        with patch("scry.cli.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_run_without_manifest_exits_with_error(self, tmp_path: Path) -> None:
        # Point to a directory with no manifest
        result = runner.invoke(app, ["run", "--project", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code != 0


class TestCliCollect:
    """Tests for the collect subcommand."""

    def test_collect_json_output(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        changes = [
            ChangeRecord(
                source=ChangeSource.RSS,
                title="test change",
                category=ChangeCategory.FEATURE,
            )
        ]
        with (
            patch("scry.cli._resolve_config", return_value=config),
            patch("scry.pipeline.run_collect") as mock_collect,
        ):
            mock_collect.return_value = CollectResult(changes=changes)
            result = runner.invoke(app, ["collect", "--json"])

        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["title"] == "test change"
