"""Extractor for tracked project dependencies."""

from __future__ import annotations

import json
import re
from typing import Any

from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


def _parse_pep508_name(dep_str: str) -> str:
    """Extract package name from a PEP 508 dependency string."""
    match = re.match(r"^([a-zA-Z0-9._-]+)", dep_str.strip())
    return match.group(1) if match else ""


def _read_package_json(path: Any) -> dict[str, str]:  # noqa: ANN401
    """Extract dependencies from package.json."""
    from pathlib import Path

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
    from pathlib import Path

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
    from pathlib import Path

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
    from pathlib import Path

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


class DependencyExtractor:
    """Extracts dependencies filtered by configured prefixes."""

    def extract(self, config: ProjectConfig, surface: AppSurface) -> AppSurface:
        """Auto-detect dependency manifest and extract matching packages."""
        if not config.dependency_prefixes:
            return surface

        all_deps: dict[str, str] = {}

        # Try each manifest type — collect from all that exist
        all_deps.update(_read_package_json(config.root / "package.json"))
        all_deps.update(_read_pyproject_toml(config.root / "pyproject.toml"))
        all_deps.update(_read_gemfile_lock(config.root / "Gemfile.lock"))
        all_deps.update(_read_go_mod(config.root / "go.mod"))

        # Filter by configured prefixes
        filtered = {
            name: version
            for name, version in all_deps.items()
            if any(name.startswith(prefix) for prefix in config.dependency_prefixes)
        }

        surface.dependencies = filtered
        return surface
