# Changelog

All notable changes to scry are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Remediation of the April and June 2026 codebase audits.

### Added

- GitHub Actions CI running `ruff check`, `ruff format --check`, `pyright`, and
  `pytest` with coverage on every push and pull request to `main`.
- `scry doctor` preflight command: manifest parsing, required environment
  variables, source-pattern matches, and endpoint reachability.
- `--version` flag, `--json` output on `scry run`, and a `--quiet` flag.
- Per-stage duration logging (`<stage> stage completed in X.Xs`).
- Collector gating via the `disabled_collectors` and `design_system_urls`
  manifest fields, plus a `scry.collectors` entry-point group so third-party
  collectors can register without modifying the orchestrator.
- State-file schema versioning (`schema_version: 1`) with automatic migration
  of legacy `history.json` files.
- Coverage enforcement (93% threshold via pytest-cov) and strict pytest
  configuration.
- `py.typed` marker and complete pyproject metadata (license, authors, URLs,
  keywords, classifiers).
- Developer tooling: `justfile`, pre-commit config (ruff + ruff-format),
  `CONTRIBUTING.md`, and `.env.example`.
- Test suite grew from 170 to 247 tests: request-URL assertions for networked
  collectors, one test per graphql-core schema-change type, negative-path
  collector tests (timeouts, malformed payloads, HTTP errors), and byte-exact
  golden-file tests for both report generators.

### Changed

- Default log level is now INFO (was WARNING); `--verbose` remains DEBUG.
- Invalid manifests exit with code 3 and per-field guidance instead of a raw
  validation dump.
- Dependency checks are routed to the registry matching each dependency's
  source manifest (package.json to npm, pyproject to PyPI); the PyPI-to-npm
  fallback was removed and gem/go dependencies are skipped explicitly.
- PolarisCollector is disabled unless `design_system_urls` is configured
  (previously always ran against hardcoded Shopify URLs).
- Package moved to src layout (`src/scry`); version is single-sourced from
  `scry.__init__`.
- Internal reorganization: pipeline result models moved to
  `scry.models.results`, shared dependency-manifest reading to
  `scry.manifests`, and shared report render helpers to `scry.report._format`.
- Inventory globs and reads the source tree once per run instead of once per
  extractor.
- Ruff lint rules made explicit (E, F, I, B, UP, SIM, RUF), the whole tree
  ruff-formatted, and dev tools pinned with lower bounds.
- Starter manifest from `scry init` is platform-neutral with typed comments
  that double as a schema reference; the shipped example config uses a
  portable path.
- Repository URL references unified to `onedusk/scry`.

### Fixed

- `scry run` and `scry report` exited 0 even when every pipeline stage failed;
  stage failures are now tracked, summarized in a footer, and produce a
  non-zero exit.
- The SDK Updates report table rendered a stray colon after package names and
  a blank Latest column; it now parses the live RegistryCollector title
  format.
- E402 import-order violations in the RSS collector.

### Removed

- Dead `diff_dependencies` function and its export (superseded by
  RegistryCollector version checks).

## [0.1.0] - 2026-03-12

Initial release.

### Added

- Four-stage pipeline (collect, inventory, diff, report) behind a Typer CLI
  with `run`, `collect`, `inventory`, `diff`, `report`, and `init`
  subcommands.
- Collectors: RSS changelog, Firecrawl-scraped changelog pages, GraphQL schema
  introspection with per-version SDL caching, package registries, and Polaris
  changelog.
- Inventory extractors: GraphQL operations, webhooks, dependencies, UI
  components, and API version, driven by a per-project YAML/TOML manifest.
- graphql-core schema diffing, changelog-to-inventory matching, and
  config-driven severity escalation rules.
- Markdown impact report and draft change plan generators writing to
  `docs/api-changes/{YYYY-MM}/`.
- File-based state store with cross-run dedup and corrupt-file recovery.
- 170-test pytest suite.
