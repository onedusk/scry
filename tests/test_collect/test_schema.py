"""Tests for the SchemaCollector."""

import json
from pathlib import Path
from typing import Any

import httpx

from scry.collect.schema import SchemaCollector, _next_quarterly_version
from scry.models.config import ProjectConfig

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _make_config(
    tmp_path: Path, schema_base_url: str | None = "https://proxy.test"
) -> ProjectConfig:
    """Create a config with a version source file."""
    toml_file = tmp_path / "shopify.app.toml"
    toml_file.write_text('[webhooks]\napi_version = "2026-04"\n')
    return ProjectConfig(
        name="test",
        root=tmp_path,
        platform="shopify",
        api_version_source="shopify.app.toml:webhooks.api_version",
        source_patterns=[],
        schema_base_url=schema_base_url,
    )


def _introspection_json() -> dict[str, Any]:
    """Load the introspection response fixture."""
    return json.loads((FIXTURES_DIR / "introspection_response.json").read_text())  # type: ignore[no-any-return]


class _MockResponse:
    """Minimal mock for httpx.Response."""

    def __init__(self, data: dict[str, Any], status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("POST", "https://test"),
                response=self,  # type: ignore[arg-type]
            )


class TestNextQuarterlyVersion:
    def test_q1_to_q2(self) -> None:
        assert _next_quarterly_version("2026-01") == "2026-04"

    def test_q2_to_q3(self) -> None:
        assert _next_quarterly_version("2026-04") == "2026-07"

    def test_q3_to_q4(self) -> None:
        assert _next_quarterly_version("2026-07") == "2026-10"

    def test_q4_to_next_year(self) -> None:
        assert _next_quarterly_version("2026-10") == "2027-01"


class TestSchemaCollector:
    def test_collect_returns_empty_list(self, tmp_path: Path, monkeypatch: Any) -> None:
        """collect() always returns empty list — SDL goes on instance attrs."""
        config = _make_config(tmp_path)
        intro_json = _introspection_json()

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(intro_json)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        result = collector.collect(config)
        assert result == []

    def test_populates_instance_attrs(self, tmp_path: Path, monkeypatch: Any) -> None:
        """After collect(), instance has SDL and version strings."""
        config = _make_config(tmp_path)
        intro_json = _introspection_json()

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(intro_json)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        collector.collect(config)
        assert collector.old_schema_sdl is not None
        assert collector.new_schema_sdl is not None
        assert collector.current_api_version == "2026-04"
        assert collector.next_api_version == "2026-07"

    def test_sdl_contains_types(self, tmp_path: Path, monkeypatch: Any) -> None:
        """The generated SDL contains the expected types from the fixture."""
        config = _make_config(tmp_path)
        intro_json = _introspection_json()

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(intro_json)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        collector.collect(config)
        assert "Product" in (collector.old_schema_sdl or "")
        assert "Query" in (collector.old_schema_sdl or "")

    def test_caches_schema_files(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Schema SDL is cached to .cache/schemas/ directory."""
        config = _make_config(tmp_path)
        intro_json = _introspection_json()

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(intro_json)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        collector.collect(config)

        cache_dir = tmp_path / ".cache" / "schemas"
        assert cache_dir.is_dir()
        assert (cache_dir / "2026-04.graphql").is_file()
        assert (cache_dir / "2026-07.graphql").is_file()

    def test_handles_network_error(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Network error doesn't crash — SDL attrs stay None."""
        config = _make_config(tmp_path)

        def mock_post(self: Any, url: str, **kwargs: Any) -> None:
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        result = collector.collect(config)
        assert result == []
        assert collector.old_schema_sdl is None

    def test_returns_empty_when_no_base_url(self, tmp_path: Path) -> None:
        """Returns empty list when schema_base_url is None."""
        config = _make_config(tmp_path, schema_base_url=None)
        collector = SchemaCollector()
        result = collector.collect(config)
        assert result == []
