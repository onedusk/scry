# Contributing to scry

## Setup

Requires Python >= 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
```

## Gates

CI (`.github/workflows/ci.yml`) runs four gates on every push and pull request; all must pass:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright scry/
uv run pytest -q --cov=scry --cov-report=term
```

With [just](https://github.com/casey/just) installed, `just check` runs all of them. See the
`justfile` for individual recipes: `just test`, `just lint`, `just typecheck`, `just run ...`.

## Pre-commit hooks

Optional but recommended — runs ruff lint and format on staged files:

```bash
uv tool install pre-commit
pre-commit install
```

## Commit flow

1. Branch from `main`.
2. Make your change; add or update tests alongside it (`tests/` mirrors the package structure).
3. Run `just check` (or the four gate commands above) until green.
4. Commit. `uv.lock` is tracked — include it whenever dependency changes regenerate it.
5. Push and open a pull request against `main`; CI must pass before merge.
