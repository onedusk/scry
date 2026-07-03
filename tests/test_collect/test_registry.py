"""Tests for the RegistryCollector."""

import json
from pathlib import Path
from typing import Any

import httpx

from scry.collect.registry import RegistryCollector, _encode_npm_package
from scry.models.config import ProjectConfig
from scry.models.enums import ChangeCategory, ChangeSource

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _make_config(
    tmp_path: Path,
    prefixes: list[str] | None = None,  # None means default @shopify/
    with_package_json: bool = True,
) -> ProjectConfig:
    if with_package_json:
        (tmp_path / "package.json").write_text((FIXTURES_DIR / "sample_package.json").read_text())
    return ProjectConfig(
        name="test",
        root=tmp_path,
        platform="shopify",
        api_version_source="x:y",
        source_patterns=[],
        dependency_prefixes=["@shopify/"] if prefixes is None else prefixes,
    )


class _MockResponse:
    """Minimal mock for httpx.Response."""

    def __init__(self, data: Any, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> Any:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("GET", "https://test"),
                response=self,  # type: ignore[arg-type]
            )


class TestRegistryCollector:
    def test_detects_npm_update(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Produces a ChangeRecord when npm has a newer version."""
        config = _make_config(tmp_path)
        npm_response = json.loads((FIXTURES_DIR / "registry_response.json").read_text())

        def mock_get(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(npm_response)

        monkeypatch.setattr(httpx.Client, "get", mock_get)
        records = RegistryCollector().collect(config)
        # @shopify/polaris is at ^12.0.0 in fixture, npm returns 12.5.0
        polaris_records = [r for r in records if "@shopify/polaris" in r.title]
        assert len(polaris_records) >= 1
        assert polaris_records[0].source == ChangeSource.REGISTRY
        assert polaris_records[0].category == ChangeCategory.SDK

    def test_requests_encoded_scoped_package_url(self, tmp_path: Path, monkeypatch: Any) -> None:
        """npm request URLs encode the scoped-package slash as %2F."""
        config = _make_config(tmp_path)
        requested: list[str] = []

        def mock_get(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            requested.append(url)
            return _MockResponse({"version": "99.0.0"})

        monkeypatch.setattr(httpx.Client, "get", mock_get)
        RegistryCollector().collect(config)
        assert "https://registry.npmjs.org/@shopify%2Fpolaris/latest" in requested

    def test_handles_npm_not_found_string(self, tmp_path: Path, monkeypatch: Any) -> None:
        """npm returns string 'Not Found' for nonexistent packages — skip without crash."""
        config = _make_config(tmp_path)

        def mock_get(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse("Not Found")

        monkeypatch.setattr(httpx.Client, "get", mock_get)
        records = RegistryCollector().collect(config)
        assert records == []

    def test_returns_empty_without_prefixes(self, tmp_path: Path) -> None:
        """Returns empty list when dependency_prefixes is empty."""
        config = _make_config(tmp_path, prefixes=[])
        records = RegistryCollector().collect(config)
        assert records == []

    def test_returns_empty_without_manifest(self, tmp_path: Path) -> None:
        """Returns empty list when no dependency manifest exists."""
        config = _make_config(tmp_path, with_package_json=False)
        records = RegistryCollector().collect(config)
        assert records == []

    def test_handles_network_error(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Network errors don't crash — just skip that package."""
        config = _make_config(tmp_path)

        def mock_get(self: Any, url: str, **kwargs: Any) -> None:
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx.Client, "get", mock_get)
        records = RegistryCollector().collect(config)
        assert records == []

    def test_routes_package_json_deps_to_npm_only(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Deps from package.json hit npm — one request each, never PyPI."""
        config = _make_config(tmp_path)
        requested: list[str] = []

        def mock_get(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            requested.append(url)
            return _MockResponse({"version": "99.0.0"})

        monkeypatch.setattr(httpx.Client, "get", mock_get)
        records = RegistryCollector().collect(config)
        # Fixture has 3 @shopify/ deps (incl. devDependencies)
        assert len(requested) == 3
        assert all(url.startswith("https://registry.npmjs.org/") for url in requested)
        assert len(records) == 3

    def test_routes_pyproject_deps_to_pypi(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Deps from pyproject.toml hit PyPI, not npm."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0"\ndependencies = ["shopify-api>=12.0"]\n'
        )
        config = _make_config(tmp_path, prefixes=["shopify-api"], with_package_json=False)
        requested: list[str] = []

        def mock_get(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            requested.append(url)
            return _MockResponse({"info": {"version": "12.6.0"}})

        monkeypatch.setattr(httpx.Client, "get", mock_get)
        records = RegistryCollector().collect(config)
        assert requested == ["https://pypi.org/pypi/shopify-api/json"]
        assert len(records) == 1
        assert "shopify-api" in records[0].title

    def test_pypi_miss_does_not_fall_back_to_npm(self, tmp_path: Path, monkeypatch: Any) -> None:
        """A PyPI 404 makes exactly one request — no npm fallback round-trip."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0"\ndependencies = ["shopify-api>=12.0"]\n'
        )
        config = _make_config(tmp_path, prefixes=["shopify-api"], with_package_json=False)
        requested: list[str] = []

        def mock_get(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            requested.append(url)
            return _MockResponse({}, status_code=404)

        monkeypatch.setattr(httpx.Client, "get", mock_get)
        records = RegistryCollector().collect(config)
        assert records == []
        assert requested == ["https://pypi.org/pypi/shopify-api/json"]

    def test_skips_gem_and_go_deps_without_requests(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Gemfile.lock and go.mod deps have no checker — skipped, zero requests."""
        (tmp_path / "Gemfile.lock").write_text("GEM\n  specs:\n    shopify_api (12.0.0)\n")
        (tmp_path / "go.mod").write_text(
            "module x\n\nrequire (\n\tgithub.com/Shopify/sarama v1.38.0\n)\n"
        )
        config = _make_config(
            tmp_path,
            prefixes=["shopify_api", "github.com/Shopify/"],
            with_package_json=False,
        )

        def mock_get(self: Any, url: str, **kwargs: Any) -> None:
            raise AssertionError(f"unexpected registry request: {url}")

        monkeypatch.setattr(httpx.Client, "get", mock_get)
        records = RegistryCollector().collect(config)
        assert records == []


class TestEncodeNpmPackage:
    def test_scoped_package(self) -> None:
        assert _encode_npm_package("@shopify/polaris") == "@shopify%2Fpolaris"

    def test_unscoped_package(self) -> None:
        assert _encode_npm_package("lodash") == "lodash"
