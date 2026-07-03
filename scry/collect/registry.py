"""Collector for package registry version checks."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from scry.manifests import read_project_dependencies
from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource

logger = logging.getLogger(__name__)

_NPM_BASE = "https://registry.npmjs.org"
_PYPI_BASE = "https://pypi.org/pypi"


def _encode_npm_package(name: str) -> str:
    """URL-encode an npm package name (handle scoped packages)."""
    if name.startswith("@"):
        # @scope/pkg → @scope%2Fpkg
        return quote(name, safe="@")
    return name


def _check_npm(name: str, client: httpx.Client) -> str | None:
    """Check npm registry for latest version. Returns version or None."""
    encoded = _encode_npm_package(name)
    url = f"{_NPM_BASE}/{encoded}/latest"
    try:
        response = client.get(url, timeout=10.0)
        response.raise_for_status()
        # npm returns string "Not Found" (not a JSON object) for nonexistent packages
        body: Any = response.json()
        if isinstance(body, str):
            logger.warning("npm returned string for %s: %s", name, body)
            return None
        result: str = body["version"]
        return result
    except Exception:
        logger.warning("npm check failed for %s", name, exc_info=True)
        return None


def _check_pypi(name: str, client: httpx.Client) -> str | None:
    """Check PyPI registry for latest version. Returns version or None."""
    url = f"{_PYPI_BASE}/{name}/json"
    try:
        response = client.get(url, timeout=10.0)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        info: dict[str, Any] = data["info"]
        result: str = info["version"]
        return result
    except Exception:
        logger.warning("PyPI check failed for %s", name, exc_info=True)
        return None


class RegistryCollector:
    """Checks package registries for dependency version updates."""

    def collect(self, config: ProjectConfig) -> list[ChangeRecord]:
        """Compare tracked dependencies against latest registry versions."""
        if not config.dependency_prefixes:
            return []

        # Read current deps from project manifests, tagged with source ecosystem
        manifests = read_project_dependencies(config.root)

        # Filter by configured prefixes, carrying each dep's ecosystem
        tracked: dict[str, tuple[str, str]] = {
            name: (version, ecosystem)
            for ecosystem, deps in manifests.items()
            for name, version in deps.items()
            if any(name.startswith(p) for p in config.dependency_prefixes)
        }

        if not tracked:
            return []

        records: list[ChangeRecord] = []
        with httpx.Client() as client:
            for name, (current_version, ecosystem) in tracked.items():
                # Route to the registry matching the dep's source manifest
                if ecosystem == "npm":
                    latest = _check_npm(name, client)
                elif ecosystem == "pypi":
                    latest = _check_pypi(name, client)
                else:
                    logger.debug("no registry checker for %s dep %s, skipping", ecosystem, name)
                    continue

                if latest is None:
                    continue

                if latest != current_version:
                    records.append(
                        ChangeRecord(
                            source=ChangeSource.REGISTRY,
                            title=f"{name}: {current_version} → {latest}",
                            category=ChangeCategory.SDK,
                            description=f"Package {name} has a newer version available: {latest} (current: {current_version})",
                        )
                    )

        return records
