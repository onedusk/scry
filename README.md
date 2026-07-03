# scry

Detect API platform changes affecting your projects, score their impact, and generate change plans.

scry monitors external API sources (changelogs, GraphQL schemas, package registries) and cross-references them against what your project actually uses. The result is a prioritized impact report showing exactly what changed, whether it affects you, and what to do about it.

## How it works

```
collect          inventory          diff              report
   |                 |                |                  |
   |  RSS feeds      |  GraphQL ops   |  Schema diff     |  impact-report.md
   |  Schemas        |  Webhooks      |  Changelog match  |  change-plan-draft.md
   |  npm registry   |  Dependencies  |  Severity score   |  raw-changes.json
   |  Changelogs     |  UI components |                  |
   |  Polaris        |  API version   |                  |
```

**Collect** gathers changes from external sources. **Inventory** scans your project to build an API surface map. **Diff** cross-references them and scores severity. **Report** generates markdown reports with action items.

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
# schema_base_url: "https://shopify.dev/admin-graphql"
# changelog_page_urls: []
# design_system_urls:
#   - "https://polaris.shopify.com/whats-new"
# disabled_collectors: []

# Severity overrides
escalation_rules:
  - pattern: "productVariants|barcode"
    floor: CRITICAL
    reason: "Core product sync functionality"

# Output
report_dir: "docs/api-changes"
```

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
| `schema_base_url` | No | Base URL for GraphQL schema introspection |
| `changelog_page_urls` | No | URLs to scrape via Firecrawl |
| `design_system_urls` | No | Design-system changelog URLs to scrape (e.g. Polaris) |
| `disabled_collectors` | No | Collector names to skip (`rss`, `changelog`, `schema`, `registry`, `polaris`, or an entry-point name) |
| `escalation_rules` | No | Severity override rules |
| `report_dir` | No | Report output directory (default: `docs/api-changes`) |

Third-party packages can add collectors by registering a zero-arg factory under
the `scry.collectors` entry-point group; no scry code changes needed.

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FIRECRAWL_API_KEY` | If `changelog_page_urls` or `design_system_urls` is set | Enables changelog and design-system page scraping |

## CLI commands

```
scry run         # Full pipeline: collect -> inventory -> diff -> report
scry collect     # Fetch changes from configured sources
scry inventory   # Scan project API surface
scry diff        # Collect + inventory + diff (with dedup)
scry report      # Full pipeline through report generation
scry init        # Generate starter scry.yaml
scry doctor      # Preflight checks: manifest, env vars, source patterns, endpoints
```

All commands accept `--project/-p` to specify a manifest path, `--verbose/-v` for debug output, and `--quiet/-q` to show only warnings and errors (the default is INFO-level progress logging). `collect`, `inventory`, and `diff` accept `--json/-j` for JSON output.

## Reports

Reports are written to `{report_dir}/{YYYY-MM}/`:

- **impact-report.md** -- Prioritized list of changes with severity ratings, deprecation tracker, and SDK update tables
- **change-plan-draft.md** -- Generated when action-required items exist; groups changes by feature area with affected files and suggested milestones
- **raw-changes.json** -- Machine-readable export of all collected changes

## Dedup

scry tracks seen changes in `.scry/history.json`. Subsequent runs only report new changes, so you can run it on a schedule without noise.

## Stack

- [typer](https://typer.tiangolo.com/) for CLI
- [pydantic](https://docs.pydantic.dev/) for models and validation
- [graphql-core](https://github.com/graphql-python/graphql-core) for schema parsing and diffing
- [feedparser](https://feedparser.readthedocs.io/) for RSS
- [httpx](https://www.python-httpx.org/) for HTTP
- [firecrawl](https://firecrawl.dev/) for web scraping (optional)

## Development

```bash
uv sync --extra dev
uv run pytest tests/ -v
uv run ruff check .
uv run pyright
```

## License

[PolyForm Noncommercial 1.0.0](LICENSE)
