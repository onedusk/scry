# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

scry — a Python CLI tool and library that detects API platform changes affecting your projects, scores their impact, and generates change plans for review. Project-agnostic by design; configured per-target via YAML/TOML manifest files.

**Status:** Implemented. CLI runs end-to-end (`scry run`); all four pipeline modules (`collect/`, `inventory/`, `diff/`, `report/`) are present. See README for usage.

## Architecture

Installable Python package (`scry`) with a Typer CLI entry point. Four-stage pipeline (`collect → inventory → diff → report`), each stage an independent module with typed inputs/outputs and protocol-based extensibility.

- **Collect**: Gathers changes from RSS feed, Firecrawl-scraped changelog pages, GraphQL schema introspection, package registries, Polaris changelog
- **Inventory**: Extracts what a project uses — GraphQL operations, webhooks, dependencies, UI components, API version — driven by the project manifest
- **Diff**: Runs `graphql-core` schema diff, matches changelog entries to inventory, scores severity using configurable escalation rules
- **Report**: Generates impact report + draft change plan as markdown in `docs/api-changes/{YYYY-MM}/`

All state is file-based (JSON + markdown). No database.

## Stack

- Python >=3.12, managed with `uv`
- `typer` for CLI, `pydantic` for models
- `graphql-core` for schema parsing/diffing
- `firecrawl-py` for web scraping (supplemental, not primary)
- `feedparser` for RSS, `httpx` for HTTP
- `ruff` for linting/formatting, `pyright` for type checking, `pytest` for tests

## Key Design Decisions

- `graphql-core` schema diff is the primary, highest-confidence data source (ADR-001)
- Python over TypeScript — best library coverage, first-party Firecrawl SDK, fastest development (ADR-005)
- Project-agnostic via configuration manifests — onboard new projects with a config file, not code (ADR-006)
- Regex extraction for GraphQL operations — language-agnostic, tag pattern configurable per manifest (ADR-003)
- Escalation rules are config-driven, not hardcoded (defined in project manifest)
- Monthly cadence (PDR-001), reports in repo (PDR-002), never auto-modifies source (PDR-003)

## Package Structure

```
src/scry/             # Main package
  cli.py              # Typer subcommands (run, collect, inventory, diff, report, init)
  config.py           # Project manifest loader
  models/             # Pydantic models for all entities
  collect/            # Collector protocol + implementations
  inventory/          # Extractor protocol + implementations
  diff/               # Schema diffing, changelog matching, severity scoring
  report/             # Impact report + change plan generators
  pipeline.py         # Orchestrator
  store/              # State management
tests/                # pytest, mirrors package structure
pyproject.toml        # Package metadata, deps, CLI entry point
```

## Implementation Milestones

1. M01: Package scaffolding, Pydantic models, config, CLI skeleton
2. M02: Inventory extractors (protocol + implementations)
3. M03: Collectors (protocol + implementations)
4. M04: Diff engine (graphql-core + severity scorer)
5. M05: Report generator
6. M06: Pipeline orchestrator, state, e2e testing
