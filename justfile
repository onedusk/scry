# Task runner for scry — https://github.com/casey/just
# Recipes mirror the CI gates in .github/workflows/ci.yml.

# List available recipes
default:
    @just --list

# Run the test suite with coverage (mirrors CI)
test:
    uv run pytest -q --cov=scry --cov-report=term

# Lint and check formatting
lint:
    uv run ruff check .
    uv run ruff format --check .

# Type-check the package
typecheck:
    uv run pyright src/scry

# Run every CI gate
check: lint typecheck test

# Run the CLI, e.g. `just run doctor`
run *args:
    uv run scry {{args}}
