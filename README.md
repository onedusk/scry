# scry

Detect API platform changes affecting your projects, score their impact, and generate change plans.

Your code depends on someone else's API, and that API changes on their schedule, not yours. Most teams find out about a breaking change when it breaks. scry closes that gap.

scry monitors external API sources (changelogs, GraphQL schemas, package registries) and cross-references them against what your project actually uses. The result is a prioritized impact report showing exactly what changed, whether it affects you, and what to do about it. scry never modifies your source; it reads your project and writes reports.

## How it works

```
collect          inventory          diff              report
   |                 |                |                  |
   |  RSS feeds      |  GraphQL ops   |  Schema diff     |  impact-report.md
   |  Schemas        |  Webhooks      |  Changelog match  |  change-plan-draft.md
   |  npm registry   |  Dependencies  |  Severity score   |  raw-changes.json
   |  Changelogs     |  UI components |  Claude triage   |  triage.json
   |  Polaris        |  API version   |                  |  stage-3-task-index.md
```

**Collect** gathers changes from external sources. **Inventory** scans your project to build an API surface map. **Diff** cross-references them and scores severity: each schema change is attributed to the GraphQL operations that select the field, pass the input type, or use the enum value (newly deprecated members are detected alongside breaking and dangerous changes), and changelog entries are matched against operation names, fields, webhook topics, packages, and components. With `triage_model` set, Claude reads every changelog entry against the full inventory and replaces that substring match with a judgment: relevant or not, severity, the operations affected, any stated deadline, and a suggested action. Schema changes stay deterministic, and the substring scoring remains the fallback when triage is off or fails. **Report** generates markdown reports with action items.

The cross-reference is the point. A platform changelog has hundreds of entries, and most touch things your project never calls. Only the intersection of what changed and what you use makes it into the report, ranked by how much it will hurt.

## Install

```bash
uv pip install -e .
```

Requires Python >= 3.12.

## Quick start

```bash
# Generate a starter manifest in your project
cd your-project/
scry init

# Edit scry.yaml for your project, then run
scry run
```

## Configuration

scry is configured via a `scry.yaml` (or `scry.toml`) manifest in your project root:

```yaml
name: my-app
root: .
platform: shopify

# What to scan
api_version_source: "shopify.app.toml:webhooks.api_version"
source_patterns:
  - "app/**/*.ts"
  - "app/**/*.tsx"
graphql_tag: "#graphql"
dependency_prefixes:
  - "@shopify/"
webhook_config_path: "shopify.app.toml"

# What to monitor
changelog_rss_url: "https://shopify.dev/changelog/feed.xml"
# schema_base_url: "https://shopify.dev/admin-graphql-direct-proxy"
# changelog_page_urls: []
# design_system_urls:
#   - "https://polaris.shopify.com/whats-new"
# disabled_collectors: []

# Claude triage of changelog entries (needs ANTHROPIC_API_KEY)
# triage_model: "claude-opus-5"

# Severity overrides
escalation_rules:
  - pattern: "productVariants|barcode"
    floor: CRITICAL
    reason: "Core product sync functionality"

# Output
report_dir: "docs/api-changes"
# decompose_dir: "docs/decompose"
```

A complete Shopify-flavored example lives in [`examples/sonit.yaml`](examples/sonit.yaml) — copy it and set `root` to the path of the project you want scry to scan, then adjust the platform-specific fields.

Shopify is the platform scry was built against. The RSS and changelog-page collectors work with any URL. The schema collector assumes Shopify-style quarterly `YYYY-MM` API versions and probes forward from the pinned version to find the newest one the endpoint serves, the registry collector reads npm only, and the Polaris collector is Shopify-specific. Other platforms work to the degree their conventions match; see the entry-point note below for adding collectors.

### Manifest fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Project name (used in reports) |
| `root` | Yes | Project root directory |
| `platform` | Yes | Platform identifier (e.g. `shopify`) |
| `api_version_source` | Yes | `file:dotted.key` path to API version |
| `source_patterns` | Yes | Glob patterns for source files to scan |
| `graphql_tag` | No | Tag pattern for GraphQL literals (default: `#graphql`) |
| `dependency_prefixes` | No | Package prefixes to track (e.g. `@shopify/`) |
| `webhook_config_path` | No | Path to webhook config file |
| `component_tag_pattern` | No | Regex for UI component tags (e.g. `<s-`) |
| `changelog_rss_url` | No | RSS feed URL for changelog monitoring |
| `schema_base_url` | No | Base URL for GraphQL schema introspection; the pinned API version is diffed against the newest published version found by probing forward |
| `changelog_page_urls` | No | URLs to scrape via Firecrawl |
| `design_system_urls` | No | Design-system changelog URLs to scrape (e.g. Polaris) |
| `disabled_collectors` | No | Collector names to skip (`rss`, `changelog`, `schema`, `registry`, `polaris`, or an entry-point name) |
| `triage_model` | No | Claude model that judges changelog relevance against the inventory (e.g. `claude-opus-5`); off when unset |
| `escalation_rules` | No | Severity override rules |
| `report_dir` | No | Report output directory (default: `docs/api-changes`) |
| `decompose_dir` | No | Task index and spec output directory in the progressive-decomposition layout (default: `docs/decompose`) |

Third-party packages can add collectors by registering a zero-arg factory under
the `scry.collectors` entry-point group; no scry code changes needed.

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FIRECRAWL_API_KEY` | If `changelog_page_urls` or `design_system_urls` is set | Enables changelog and design-system page scraping |
| `ANTHROPIC_API_KEY` | If `triage_model` is set | Credentials for Claude triage (an `ant auth login` profile also works) |

## CLI commands

```
scry run         # Full pipeline: collect -> inventory -> diff -> report
scry collect     # Fetch changes from configured sources
scry inventory   # Scan project API surface
scry diff        # Collect + inventory + diff (with dedup)
scry report      # Full pipeline through report generation
scry init        # Generate starter scry.yaml
scry doctor      # Preflight checks: manifest, env vars, source patterns, endpoints
scry verify      # Validate operations against the pinned and target schemas; list deprecated members in use
```

All commands accept `--project/-p` to specify a manifest path, `--verbose/-v` for debug output, and `--quiet/-q` to show only warnings and errors (the default is INFO-level progress logging). `collect`, `inventory`, and `diff` accept `--json/-j` for JSON output.

## Reports

Reports are written to `{report_dir}/{YYYY-MM}/`:

- **impact-report.md** -- Action Required and Review sections, deprecation tracker, SDK update table, and one-line low-priority items; entries that touch nothing in the inventory are counted, not listed
- **change-plan-draft.md** -- Generated when action-required items exist; groups MEDIUM-or-higher changes by feature area with affected files and suggested milestones
- **raw-changes.json** -- Machine-readable export of all collected changes
- **schema-changes.json** -- Machine-readable export of the schema diff (breaking, dangerous, and deprecation entries) when a schema was diffed
- **docs/decompose/{platform}-changes-{YYYY-MM}/** -- Task index (`stage-3-task-index.md`) and per-milestone task specs (`tasks_m01.md`, ...) in the [progressive-decomposition](https://github.com/onedusk/pd) Stage 3/4 layout: one MODIFY task per affected file, grouped into Action required, Review, and Optional milestones, each with an outline and acceptance criteria. Pick up with `/decompose <name> review` or refine with `/decompose <name> 4`. The change plan draft is still written alongside.
- **triage.json** -- Claude's per-entry judgments (relevance, severity, affected features, deadline, suggested action, rationale) when `triage_model` is set; the impact report header records the model and token usage

## Verify

`scry verify` is the deterministic acceptance check behind the schema tasks. It validates every inventoried GraphQL operation against the schema the project pins and against the newest published version, and lists members the operations use that the pinned version already deprecates (deprecation debt the diff alone cannot see). It exits 1 when any operation is invalid on either version, so it can gate a migration branch. `--json` prints the same result as data.

## Dedup

scry tracks seen changes in `.scry/history.json`. Subsequent runs only report new changes, so you can run it on a schedule without noise.

## Stack

- [typer](https://typer.tiangolo.com/) for CLI
- [pydantic](https://docs.pydantic.dev/) for models and validation
- [graphql-core](https://github.com/graphql-python/graphql-core) for schema parsing and diffing
- [feedparser](https://feedparser.readthedocs.io/) for RSS
- [httpx](https://www.python-httpx.org/) for HTTP
- [firecrawl](https://firecrawl.dev/) for web scraping (optional)
- [anthropic](https://github.com/anthropics/anthropic-sdk-python) for Claude triage (optional)

## Development

```bash
uv sync --extra dev
just check    # ruff check, ruff format --check, pyright, pytest — mirrors CI
```

See the [`justfile`](justfile) for individual recipes (`test`, `lint`, `typecheck`, `run`) and
[CONTRIBUTING.md](CONTRIBUTING.md) for setup, gates, and the commit flow. Pre-commit hooks
(ruff lint + format) are configured in [`.pre-commit-config.yaml`](.pre-commit-config.yaml);
enable them with `pre-commit install`.

## License

[PolyForm Noncommercial 1.0.0](LICENSE)
