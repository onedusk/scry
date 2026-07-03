"""Typer CLI application — subcommands for each pipeline stage."""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUntypedFunctionDecorator=false

import logging
from pathlib import Path
from typing import Annotated, Any

import typer  # type: ignore[import-untyped]

app: Any = typer.Typer(
    name="scry",
    help="Detect API platform changes affecting your projects.",
    no_args_is_help=True,
)

# Common options reused across subcommands
ProjectOption = Annotated[
    Path | None,
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

QuietOption = Annotated[
    bool,
    typer.Option("--quiet", "-q", help="Only show warnings and errors."),
]

JsonOption = Annotated[
    bool,
    typer.Option("--json", "-j", help="Output results as JSON."),
]


def _version_callback(value: bool) -> None:
    """Print the scry version and exit."""
    if value:
        from scry import __version__

        typer.echo(f"scry {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the scry version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Detect API platform changes affecting your projects."""


def _setup_logging(verbose: bool, quiet: bool) -> None:
    """Configure logging based on verbosity flags. Verbose wins if both are set."""
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
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
    except ValueError as e:
        # e.g. missing FIRECRAWL_API_KEY with Firecrawl-dependent sources configured
        typer.echo(str(e), err=True)
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
    quiet: QuietOption = False,
    json: JsonOption = False,
) -> None:
    """Run the full pipeline: collect -> inventory -> diff -> report."""
    _setup_logging(verbose, quiet)
    config = _resolve_config(project)

    from scry.pipeline import run_pipeline
    from scry.report.summary import generate_cli_summary

    result = run_pipeline(config)

    if json:
        import json as json_mod

        paths = {
            "impact_report_path": result.report.impact_report_path,
            "change_plan_path": result.report.change_plan_path,
            "raw_changes_path": result.report.raw_changes_path,
        }
        data = {
            "impacts": [i.model_dump(mode="json") for i in result.diff.impacts],
            "report": {k: str(v) if v else None for k, v in paths.items()},
            "failed_stages": result.failed_stages,
        }
        typer.echo(json_mod.dumps(data, indent=2))
    else:
        typer.echo(generate_cli_summary(result.diff.impacts, config))
        if result.report.impact_report_path:
            typer.echo(f"Report written to {result.report.impact_report_path}")
    _exit_if_stages_failed(result.failed_stages)


@app.command()
def collect(
    project: ProjectOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    json: JsonOption = False,
) -> None:
    """Run the collect stage only. Fetches changes from all configured sources."""
    _setup_logging(verbose, quiet)
    config = _resolve_config(project)

    from scry.pipeline import run_collect

    result = run_collect(config)

    if json:
        import json as json_mod

        data = [c.model_dump(mode="json") for c in result.changes]
        typer.echo(json_mod.dumps(data, indent=2))
    else:
        sources = {c.source.value for c in result.changes}
        source_list = ", ".join(sorted(sources)) or "no sources"
        typer.echo(f"{len(result.changes)} changes collected from {source_list}")


@app.command()
def inventory(
    project: ProjectOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    json: JsonOption = False,
) -> None:
    """Run the inventory stage only. Scans the target project's API surface."""
    _setup_logging(verbose, quiet)
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
    quiet: QuietOption = False,
    json: JsonOption = False,
) -> None:
    """Run collect + inventory + diff stages (with dedup)."""
    _setup_logging(verbose, quiet)
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
    quiet: QuietOption = False,
) -> None:
    """Run the full pipeline through report generation."""
    _setup_logging(verbose, quiet)
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


@app.command()
def doctor(
    project: ProjectOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
) -> None:
    """Preflight checks: manifest, env vars, source patterns, endpoint reachability."""
    _setup_logging(verbose, quiet)

    import httpx

    from scry.config import check_firecrawl_env, find_manifest, load_config

    failed = False

    # Manifest is found and parses
    try:
        manifest_path = project or find_manifest()
        config = load_config(manifest_path, check_env=False)
    except Exception as e:
        typer.echo(f"[FAIL] manifest: {e}", err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"[ok]   manifest: {manifest_path} parsed")

    # FIRECRAWL_API_KEY present when Firecrawl-dependent config is set
    try:
        check_firecrawl_env(config)
    except ValueError as e:
        typer.echo(f"[FAIL] env: {e}", err=True)
        failed = True
    else:
        typer.echo("[ok]   env: FIRECRAWL_API_KEY present or not required")

    # Each source pattern matches at least one file
    for pattern in config.source_patterns:
        if next(config.root.glob(pattern), None) is None:
            typer.echo(
                f"[FAIL] source pattern '{pattern}' matched no files under {config.root}",
                err=True,
            )
            failed = True
        else:
            typer.echo(f"[ok]   source pattern '{pattern}' matches files")

    # Endpoint reachability (network problems are warnings, not failures)
    for label, url in (
        ("changelog_rss_url", config.changelog_rss_url),
        ("schema_base_url", config.schema_base_url),
    ):
        if not url:
            typer.echo(f"[skip] {label}: not configured")
            continue
        try:
            response = httpx.get(url, timeout=5.0, follow_redirects=True)
        except httpx.HTTPError as e:
            typer.echo(f"[warn] {label}: {url} unreachable ({e})")
        else:
            typer.echo(f"[ok]   {label}: {url} responded (HTTP {response.status_code})")

    if failed:
        typer.echo("doctor: problems found", err=True)
        raise typer.Exit(code=1)
    typer.echo("doctor: all checks passed")


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
# design_system_urls:
#   - "https://polaris.shopify.com/whats-new"
# disabled_collectors: []

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
