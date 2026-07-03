"""Tests for the scry doctor preflight command and CLI fail-fast config loading."""

from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from scry.cli import app

runner = CliRunner()


def _write_project(tmp_path: Path, extra: str = "", source_pattern: str = "app/**/*.ts") -> Path:
    """Create a minimal project with one source file and a manifest, return manifest path."""
    src_dir = tmp_path / "app"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "index.ts").write_text("export {};\n")
    manifest = tmp_path / "scry.yaml"
    manifest.write_text(
        f"name: test\n"
        f"root: {tmp_path}\n"
        f"platform: shopify\n"
        f'api_version_source: "x:y"\n'
        f"source_patterns:\n"
        f'  - "{source_pattern}"\n' + extra
    )
    return manifest


def _mock_response(
    url: str, timeout: float = 5.0, follow_redirects: bool = False
) -> httpx.Response:
    return httpx.Response(200, request=httpx.Request("GET", url))


class TestDoctor:
    def test_all_checks_pass(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """doctor exits 0 when manifest, patterns, and endpoints are all healthy."""
        manifest = _write_project(
            tmp_path,
            'changelog_rss_url: "https://example.com/feed.xml"\n'
            'schema_base_url: "https://example.com/graphql"\n',
        )
        monkeypatch.setattr(httpx, "get", _mock_response)
        result = runner.invoke(app, ["doctor", "--project", str(manifest)])
        assert result.exit_code == 0
        assert "doctor: all checks passed" in result.output
        assert "HTTP 200" in result.output

    def test_fails_on_invalid_manifest(self, tmp_path: Path) -> None:
        """doctor exits 1 when the manifest is missing required fields."""
        manifest = tmp_path / "scry.yaml"
        manifest.write_text("name: broken\n")
        result = runner.invoke(app, ["doctor", "--project", str(manifest)])
        assert result.exit_code == 1
        assert "[FAIL] manifest" in result.output

    def test_fails_without_firecrawl_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """doctor exits 1 when Firecrawl sources are set but the API key is missing."""
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        manifest = _write_project(
            tmp_path, 'changelog_page_urls: ["https://example.com/changelog"]\n'
        )
        result = runner.invoke(app, ["doctor", "--project", str(manifest)])
        assert result.exit_code == 1
        assert "FIRECRAWL_API_KEY" in result.output

    def test_passes_with_firecrawl_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """doctor exits 0 when Firecrawl sources are set and the API key is present."""
        monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")
        manifest = _write_project(
            tmp_path, 'changelog_page_urls: ["https://example.com/changelog"]\n'
        )
        result = runner.invoke(app, ["doctor", "--project", str(manifest)])
        assert result.exit_code == 0
        assert "doctor: all checks passed" in result.output

    def test_fails_on_unmatched_source_pattern(self, tmp_path: Path) -> None:
        """doctor exits 1 when a source pattern matches no files."""
        manifest = _write_project(tmp_path, source_pattern="missing/**/*.py")
        result = runner.invoke(app, ["doctor", "--project", str(manifest)])
        assert result.exit_code == 1
        assert "matched no files" in result.output

    def test_unreachable_endpoint_is_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Network errors on endpoint checks are warnings, not failures."""
        manifest = _write_project(tmp_path, 'changelog_rss_url: "https://example.com/feed.xml"\n')

        def _raise_connect_error(
            url: str, timeout: float = 5.0, follow_redirects: bool = False
        ) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "get", _raise_connect_error)
        result = runner.invoke(app, ["doctor", "--project", str(manifest)])
        assert result.exit_code == 0
        assert "[warn] changelog_rss_url" in result.output
        assert "doctor: all checks passed" in result.output

    def test_skips_unconfigured_endpoints(self, tmp_path: Path) -> None:
        """Endpoints that are not configured are reported as skipped."""
        manifest = _write_project(tmp_path)
        result = runner.invoke(app, ["doctor", "--project", str(manifest)])
        assert result.exit_code == 0
        assert "[skip] changelog_rss_url" in result.output
        assert "[skip] schema_base_url" in result.output


class TestConfigLoadFailFast:
    def test_collect_fails_fast_without_firecrawl_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pipeline commands exit 1 with a clear error before running any collectors."""
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        manifest = _write_project(
            tmp_path, 'changelog_page_urls: ["https://example.com/changelog"]\n'
        )
        result = runner.invoke(app, ["collect", "--project", str(manifest)])
        assert result.exit_code == 1
        assert "FIRECRAWL_API_KEY" in result.output

    def test_malformed_manifest_exits_3_with_field_guidance(self, tmp_path: Path) -> None:
        """Pipeline commands exit 3 and name each bad field when the manifest is invalid."""
        manifest = tmp_path / "scry.yaml"
        manifest.write_text("name: broken\nsource_patterns: 42\n")
        result = runner.invoke(app, ["collect", "--project", str(manifest)])
        assert result.exit_code == 3
        assert "Invalid manifest" in result.output
        # Missing required field is named with an actionable hint
        assert "platform: Field required" in result.output
        assert "hint: add 'platform' to the manifest" in result.output
        # Wrong-type field is named with a type hint
        assert "source_patterns" in result.output
        assert "hint: change the value of 'source_patterns' to the expected type" in result.output
