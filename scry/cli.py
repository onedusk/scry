"""Typer CLI application — subcommands for each pipeline stage."""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUntypedFunctionDecorator=false

import logging
from pathlib import Path
from typing import Annotated, Any, Optional

import typer  # type: ignore[import-untyped]

app: Any = typer.Typer(
    name="scry",
    help="Detect API platform changes affecting your projects.",
    no_args_is_help=True,
)

# Common options reused across subcommands
ProjectOption = Annotated[
    Optional[Path],
    typer.Option(
        "--project",
        "-p",
        help="Path to project manifest file (scry.yaml or scry.toml).",
        exists=True,
        readable=True,
    ),
]

VerboseOption = Annotated[
    bool,
    typer.Option("--verbose", "-v", help="Enable debug logging."),
]

JsonOption = Annotated[
    bool,
    typer.Option("--json", "-j", help="Output results as JSON."),
]


def _setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity flag."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(name)s: %(message)s")


def _resolve_config(project: Path | None) -> Any:
    """Find and load the project config, or exit with a helpful message."""
    from pydantic import ValidationError

    from scry.config import find_manifest, load_config

    try:
        manifest_path = project or find_manifest()
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    try:
        return load_config(manifest_path)
    except ValidationError as e:
        typer.echo(f"Invalid manifest: {e}", err=True)
        raise typer.Exit(code=1) from e


def _exit_if_stages_failed(failed_stages: list[str]) -> None:
    """Print a failure footer and exit non-zero if any pipeline stage failed."""
    if not failed_stages:
        return
    typer.echo(
        f"{len(failed_stages)} stage(s) failed: {', '.join(failed_stages)}",
        err=True,
    )
    raise typer.Exit(code=1)


@app.command()
def run(
    project: ProjectOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Run the full pipeline: collect -> inventory -> diff -> report."""
    _setup_logging(verbose)
    config = _resolve_config(project)

    from scry.pipeline import run_pipeline
    from scry.report.summary import generate_cli_summary

    result = run_pipeline(config)

    typer.echo(generate_cli_summary(result.diff.impacts, config))
    if result.report.impact_report_path:
        typer.echo(f"Report written to {result.report.impact_report_path}")
    _exit_if_stages_failed(result.failed_stages)


@app.command()
def collect(
    project: ProjectOption = None,
    verbose: VerboseOption = False,
    json: JsonOption = False,
) -> None:
    """Run the collect stage only. Fetches changes from all configured sources."""
    _setup_logging(verbose)
    config = _resolve_config(project)

    from scry.pipeline import run_collect

    result = run_collect(config)

    if json:
        import json as json_mod

        data = [c.model_dump(mode="json") for c in result.changes]
        typer.echo(json_mod.dumps(data, indent=2))
    else:
        sources = {c.source.value for c in result.changes}
        typer.echo(
            f"{len(result.changes)} changes collected from {', '.join(sorted(sources)) or 'no sources'}"
        )


@app.command()
def inventory(
    project: ProjectOption = None,
    verbose: VerboseOption = False,
    json: JsonOption = False,
) -> None:
    """Run the inventory stage only. Scans the target project's API surface."""
    _setup_logging(verbose)
    config = _resolve_config(project)

    from scry.pipeline import run_inventory

    surface = run_inventory(config)

    if json:
        typer.echo(surface.model_dump_json(indent=2))
    else:
        typer.echo(
            f"{len(surface.graphql_operations)} operations, "
            f"{len(surface.webhook_topics)} webhooks, "
            f"{len(surface.dependencies)} dependencies, "
            f"{len(surface.ui_components)} components"
        )


@app.command()
def diff(
    project: ProjectOption = None,
    verbose: VerboseOption = False,
    json: JsonOption = False,
) -> None:
    """Run collect + inventory + diff stages (with dedup)."""
    _setup_logging(verbose)
    config = _resolve_config(project)

    from scry.pipeline import run_collect, run_diff, run_inventory
    from scry.report.summary import generate_cli_summary
    from scry.store import filter_new_changes, load_state

    collect_result = run_collect(config)
    state = load_state(config)
    collect_result.changes = filter_new_changes(collect_result.changes, state)
    surface = run_inventory(config)
    diff_result = run_diff(collect_result, surface, config)

    if json:
        import json as json_mod

        data = [i.model_dump(mode="json") for i in diff_result.impacts]
        typer.echo(json_mod.dumps(data, indent=2))
    else:
        typer.echo(generate_cli_summary(diff_result.impacts, config))


@app.command()
def report(
    project: ProjectOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Run the full pipeline through report generation."""
    _setup_logging(verbose)
    config = _resolve_config(project)

    from scry.pipeline import run_pipeline

    result = run_pipeline(config)

    if result.report.impact_report_path:
        typer.echo(f"Impact report: {result.report.impact_report_path}")
    if result.report.change_plan_path:
        typer.echo(f"Change plan: {result.report.change_plan_path}")
    if result.report.raw_changes_path:
        typer.echo(f"Raw changes: {result.report.raw_changes_path}")
    _exit_if_stages_failed(result.failed_stages)


_STARTER_MANIFEST = """\
# scry project manifest
# See https://github.com/dusk-indust/scry for documentation

name: my-project
root: .
platform: shopify

# Inventory extraction settings
api_version_source: "shopify.app.toml:webhooks.api_version"
source_patterns:
  - "app/**/*.ts"
  - "app/**/*.tsx"
graphql_tag: "#graphql"
dependency_prefixes:
  - "@shopify/"
# component_tag_pattern: "<s-"
# webhook_config_path: "shopify.app.toml"

# Severity overrides
escalation_rules: []

# Collect settings
# changelog_rss_url: "https://shopify.dev/changelog/feed.xml"
# changelog_page_urls: []
# schema_base_url: "https://shopify.dev/admin-graphql"

# Report output
report_dir: "docs/api-changes"
"""


@app.command()
def init() -> None:
    """Generate a starter project manifest (scry.yaml) in the current directory."""
    target = Path.cwd() / "scry.yaml"
    if target.exists():
        typer.echo(f"scry.yaml already exists at {target}", err=True)
        raise typer.Exit(code=1)

    target.write_text(_STARTER_MANIFEST)
    typer.echo("Created scry.yaml — edit it for your project, then run 'scry run'")
