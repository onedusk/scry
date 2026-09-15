"""Tests for the SchemaCollector."""

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from scry.collect.schema import CACHE_MARKER, SchemaCollector, _next_quarterly_version
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


def _serve_versions(available: set[str], requested: list[str] | None = None) -> Any:
    """Build an httpx.Client.post replacement that serves introspection JSON for
    `available` versions and answers 400 (Shopify's "Invalid API version") otherwise."""
    intro_json = _introspection_json()

    def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
        if requested is not None:
            requested.append(url)
        version = url.rsplit("/", 1)[-1]
        if version in available:
            return _MockResponse(intro_json)
        return _MockResponse({"error": "Invalid API version"}, status_code=400)

    return mock_post


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
        monkeypatch.setattr(httpx.Client, "post", _serve_versions({"2026-04", "2026-07"}))
        collector = SchemaCollector()
        collector.collect(config)
        assert collector.old_schema_sdl is not None
        assert collector.new_schema_sdl is not None
        assert collector.current_api_version == "2026-04"
        assert collector.next_api_version == "2026-07"

    def test_diffs_against_latest_published_version(
        self, tmp_path: Path, monkeypatch: Any, caplog: Any
    ) -> None:
        """A project two versions behind is diffed against the newest published version."""
        config = _make_config(tmp_path)
        monkeypatch.setattr(
            httpx.Client, "post", _serve_versions({"2026-04", "2026-07", "2026-10"})
        )
        collector = SchemaCollector()
        with caplog.at_level(logging.INFO):
            collector.collect(config)
        assert collector.next_api_version == "2026-10"
        assert collector.new_schema_sdl is not None
        assert "Diffing API version 2026-04 against latest published 2026-10" in caplog.text

    def test_no_newer_version_skips_diff(
        self, tmp_path: Path, monkeypatch: Any, caplog: Any
    ) -> None:
        """When only the pinned version is published there is nothing to diff against."""
        config = _make_config(tmp_path)
        monkeypatch.setattr(httpx.Client, "post", _serve_versions({"2026-04"}))
        collector = SchemaCollector()
        with caplog.at_level(logging.INFO):
            collector.collect(config)
        assert collector.old_schema_sdl is not None
        assert collector.new_schema_sdl is None
        assert collector.next_api_version is None
        assert "No API version newer than 2026-04 is published" in caplog.text

    def test_lookahead_is_capped(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Probing stops after eight quarters even if the endpoint keeps answering."""
        config = _make_config(tmp_path)
        intro_json = _introspection_json()

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse(intro_json)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        collector.collect(config)
        assert collector.next_api_version == "2028-04"

    def test_probe_5xx_is_a_fetch_failure(
        self, tmp_path: Path, monkeypatch: Any, caplog: Any
    ) -> None:
        """A server error while probing is reported, not mistaken for "no newer version"."""
        config = _make_config(tmp_path)
        intro_json = _introspection_json()

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            if url.endswith("/2026-04"):
                return _MockResponse(intro_json)
            return _MockResponse({}, status_code=503)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        with caplog.at_level(logging.WARNING):
            collector.collect(config)
        assert collector.new_schema_sdl is None
        assert collector.next_api_version is None
        assert "Schema fetch failed" in caplog.text

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

    def test_posts_to_versioned_urls(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Fetch the pinned version, probe forward until a version is refused, fetch the latest."""
        config = _make_config(tmp_path)
        requested: list[str] = []
        monkeypatch.setattr(
            httpx.Client, "post", _serve_versions({"2026-04", "2026-07", "2026-10"}, requested)
        )
        SchemaCollector().collect(config)
        assert requested == [
            "https://proxy.test/2026-04",
            "https://proxy.test/2026-07",
            "https://proxy.test/2026-10",
            "https://proxy.test/2027-01",
            "https://proxy.test/2026-10",
        ]

    def test_caches_schema_files(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Schema SDL is cached to .cache/schemas/ directory."""
        config = _make_config(tmp_path)
        monkeypatch.setattr(httpx.Client, "post", _serve_versions({"2026-04", "2026-07"}))
        collector = SchemaCollector()
        collector.collect(config)

        cache_dir = tmp_path / ".cache" / "schemas"
        assert cache_dir.is_dir()
        assert (cache_dir / "2026-04.graphql").is_file()
        assert (cache_dir / "2026-07.graphql").is_file()

    def test_introspection_requests_deprecated_input_values(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """The introspection query must ask for deprecated input fields and arguments."""
        config = _make_config(tmp_path)
        intro_json = _introspection_json()
        queries: list[str] = []

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            queries.append(kwargs["json"]["query"])
            return _MockResponse(intro_json)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        SchemaCollector().collect(config)
        assert "inputFields(includeDeprecated: true)" in queries[0]
        assert "args(includeDeprecated: true)" in queries[0]

    def test_cached_schema_carries_marker_and_is_reused(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A cache file written by this version starts with the marker and skips the fetch."""
        config = _make_config(tmp_path)
        requested: list[str] = []
        monkeypatch.setattr(httpx.Client, "post", _serve_versions({"2026-04"}, requested))
        SchemaCollector().collect(config)
        cached = (tmp_path / ".cache" / "schemas" / "2026-04.graphql").read_text()
        assert cached.startswith(CACHE_MARKER)

        requested.clear()
        SchemaCollector().collect(config)
        assert "https://proxy.test/2026-04" not in requested

    def test_stale_cache_without_marker_is_refetched(
        self, tmp_path: Path, monkeypatch: Any, caplog: Any
    ) -> None:
        """Cache files from before the fix lack deprecated inputs and are replaced."""
        config = _make_config(tmp_path)
        cache_dir = tmp_path / ".cache" / "schemas"
        cache_dir.mkdir(parents=True)
        (cache_dir / "2026-04.graphql").write_text("type Query { stale: String }")
        requested: list[str] = []
        monkeypatch.setattr(httpx.Client, "post", _serve_versions({"2026-04"}, requested))
        collector = SchemaCollector()
        with caplog.at_level(logging.INFO):
            collector.collect(config)
        assert "https://proxy.test/2026-04" in requested
        assert "predates deprecated input values" in caplog.text
        assert (cache_dir / "2026-04.graphql").read_text().startswith(CACHE_MARKER)
        assert "stale" not in (collector.old_schema_sdl or "")

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

    def test_handles_timeout(self, tmp_path: Path, monkeypatch: Any, caplog: Any) -> None:
        """Request timeout doesn't crash — warning logged, SDL attrs stay None."""
        config = _make_config(tmp_path)

        def mock_post(self: Any, url: str, **kwargs: Any) -> None:
            raise httpx.ReadTimeout("timed out")

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        with caplog.at_level(logging.WARNING):
            result = collector.collect(config)
        assert result == []
        assert collector.old_schema_sdl is None
        assert collector.new_schema_sdl is None
        assert "Schema fetch failed" in caplog.text

    def test_handles_http_4xx(self, tmp_path: Path, monkeypatch: Any, caplog: Any) -> None:
        """HTTP 403 doesn't crash — warning logged, SDL attrs stay None."""
        config = _make_config(tmp_path)

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse({}, status_code=403)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        with caplog.at_level(logging.WARNING):
            result = collector.collect(config)
        assert result == []
        assert collector.old_schema_sdl is None
        assert "Schema fetch failed" in caplog.text

    def test_handles_http_5xx(self, tmp_path: Path, monkeypatch: Any, caplog: Any) -> None:
        """HTTP 500 doesn't crash — warning logged, SDL attrs stay None."""
        config = _make_config(tmp_path)

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse({}, status_code=500)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        with caplog.at_level(logging.WARNING):
            result = collector.collect(config)
        assert result == []
        assert collector.old_schema_sdl is None
        assert "Schema fetch failed" in caplog.text

    def test_handles_missing_data_key(self, tmp_path: Path, monkeypatch: Any, caplog: Any) -> None:
        """Response JSON without a 'data' key doesn't crash — SDL attrs stay None."""
        config = _make_config(tmp_path)

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse({"errors": [{"message": "access denied"}]})

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        with caplog.at_level(logging.WARNING):
            result = collector.collect(config)
        assert result == []
        assert collector.old_schema_sdl is None
        assert "Schema fetch failed" in caplog.text

    def test_handles_malformed_introspection_json(
        self, tmp_path: Path, monkeypatch: Any, caplog: Any
    ) -> None:
        """A 'data' payload that isn't an introspection result doesn't crash or cache."""
        config = _make_config(tmp_path)

        def mock_post(self: Any, url: str, **kwargs: Any) -> _MockResponse:
            return _MockResponse({"data": {"not": "an introspection result"}})

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        collector = SchemaCollector()
        with caplog.at_level(logging.WARNING):
            result = collector.collect(config)
        assert result == []
        assert collector.old_schema_sdl is None
        assert "Schema fetch failed" in caplog.text
        assert not (tmp_path / ".cache" / "schemas").exists()

    def test_returns_empty_when_no_base_url(self, tmp_path: Path) -> None:
        """Returns empty list when schema_base_url is None."""
        config = _make_config(tmp_path, schema_base_url=None)
        collector = SchemaCollector()
        result = collector.collect(config)
        assert result == []
