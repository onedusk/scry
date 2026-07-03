"""Shared readers for dependency manifest files (package.json, pyproject.toml, etc.)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _parse_pep508_name(dep_str: str) -> str:
    """Extract package name from a PEP 508 dependency string."""
    match = re.match(r"^([a-zA-Z0-9._-]+)", dep_str.strip())
    return match.group(1) if match else ""


def _read_package_json(path: Any) -> dict[str, str]:  # noqa: ANN401
    """Extract dependencies from package.json."""
    p = Path(path)  # pyright: ignore[reportUnknownArgumentType]
    if not p.is_file():
        return {}
    data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    deps: dict[str, str] = data.get("dependencies", {})  # pyright: ignore[reportAny]
    dev_deps: dict[str, str] = data.get("devDependencies", {})  # pyright: ignore[reportAny]
    result: dict[str, str] = {}
    result.update(deps)
    result.update(dev_deps)
    return result


def _read_pyproject_toml(path: Any) -> dict[str, str]:  # noqa: ANN401
    """Extract dependencies from pyproject.toml."""
    import tomllib

    p = Path(path)  # pyright: ignore[reportUnknownArgumentType]
    if not p.is_file():
        return {}
    toml_data: dict[str, Any] = tomllib.loads(p.read_text(encoding="utf-8"))
    project: dict[str, Any] = toml_data.get("project", {})  # pyright: ignore[reportAny]
    result: dict[str, str] = {}
    for dep_str in project.get("dependencies", []):  # pyright: ignore[reportAny]
        name = _parse_pep508_name(dep_str)  # pyright: ignore[reportUnknownArgumentType]
        if name:
            result[name] = dep_str  # pyright: ignore[reportUnknownArgumentType]
    for group_deps in project.get("optional-dependencies", {}).values():  # pyright: ignore[reportAny]
        for dep_str in group_deps:  # pyright: ignore[reportUnknownVariableType]
            name = _parse_pep508_name(dep_str)  # pyright: ignore[reportUnknownArgumentType]
            if name:
                result[name] = dep_str  # pyright: ignore[reportUnknownArgumentType]
    return result


def _read_gemfile_lock(path: Any) -> dict[str, str]:  # noqa: ANN401
    """Extract gem names and versions from Gemfile.lock."""
    p = Path(path)  # pyright: ignore[reportUnknownArgumentType]
    if not p.is_file():
        return {}
    result: dict[str, str] = {}
    in_specs = False
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "specs:":
            in_specs = True
            continue
        if in_specs:
            if not stripped or not line.startswith(" "):
                in_specs = False
                continue
            # Lines like "    rails (7.0.4)" at 4-space indent are gem entries
            match = re.match(r"^\s{4}(\S+)\s+\(([^)]+)\)", line)
            if match:
                result[match.group(1)] = match.group(2)
    return result


def _read_go_mod(path: Any) -> dict[str, str]:  # noqa: ANN401
    """Extract module dependencies from go.mod require block."""
    p = Path(path)  # pyright: ignore[reportUnknownArgumentType]
    if not p.is_file():
        return {}
    result: dict[str, str] = {}
    in_require = False
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require = True
            continue
        if in_require:
            if stripped == ")":
                in_require = False
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                result[parts[0]] = parts[1]
    return result


def read_project_dependencies(root: Path) -> dict[str, dict[str, str]]:
    """Read dependencies from every recognized manifest under root, keyed by ecosystem."""
    return {
        "npm": _read_package_json(root / "package.json"),
        "pypi": _read_pyproject_toml(root / "pyproject.toml"),
        "gem": _read_gemfile_lock(root / "Gemfile.lock"),
        "go": _read_go_mod(root / "go.mod"),
    }
