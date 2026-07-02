"""Tests for the WebhookExtractor."""

from pathlib import Path

from scry.inventory.webhooks import WebhookExtractor
from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


class TestWebhookExtractor:
    def test_extracts_topics(self, inventory_project_root: ProjectConfig) -> None:
        """Extracts webhook topics from subscriptions."""
        surface = AppSurface(api_version="")
        extractor = WebhookExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert "app/uninstalled" in result.webhook_topics
        assert "app/scopes_update" in result.webhook_topics

    def test_extracts_compliance_topics(self, inventory_project_root: ProjectConfig) -> None:
        """Extracts compliance_topics from subscriptions that use them."""
        surface = AppSurface(api_version="")
        extractor = WebhookExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert "customers/data_request" in result.webhook_topics
        assert "customers/redact" in result.webhook_topics

    def test_extracts_scopes(self, inventory_project_root: ProjectConfig) -> None:
        """Extracts scopes from access_scopes.scopes comma-separated string."""
        surface = AppSurface(api_version="")
        extractor = WebhookExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert "write_products" in result.scopes
        assert "read_orders" in result.scopes

    def test_none_config_path_is_noop(self, tmp_path: Path) -> None:
        """Returns surface unchanged when webhook_config_path is None."""
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=[],
            webhook_config_path=None,
        )
        surface = AppSurface(api_version="")
        extractor = WebhookExtractor()
        result = extractor.extract(config, surface)
        assert result.webhook_topics == []
        assert result.scopes == []

    def test_missing_file_is_noop(self, tmp_path: Path) -> None:
        """Returns surface unchanged when the webhook config file is missing."""
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=[],
            webhook_config_path="nonexistent.toml",
        )
        surface = AppSurface(api_version="")
        extractor = WebhookExtractor()
        result = extractor.extract(config, surface)
        assert result.webhook_topics == []

    def test_deduplicates_topics(self, tmp_path: Path) -> None:
        """Deduplicates topics appearing in multiple subscriptions."""
        toml_content = """
[webhooks]
api_version = "2024-10"

[[webhooks.subscriptions]]
topics = ["app/uninstalled"]
uri = "/a"

[[webhooks.subscriptions]]
topics = ["app/uninstalled"]
uri = "/b"
"""
        (tmp_path / "shopify.app.toml").write_text(toml_content)
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=[],
            webhook_config_path="shopify.app.toml",
        )
        surface = AppSurface(api_version="")
        extractor = WebhookExtractor()
        result = extractor.extract(config, surface)
        assert result.webhook_topics.count("app/uninstalled") == 1
