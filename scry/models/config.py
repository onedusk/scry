"""Models for project configuration (manifest) and escalation rules."""

import re
from pathlib import Path

from pydantic import BaseModel, field_validator

from scry.models.enums import Severity


class EscalationRule(BaseModel):
    """Maps a regex path pattern to a minimum severity floor."""

    pattern: str  # Regex pattern, e.g. "productVariantsBulkUpdate|barcode"
    floor: Severity
    reason: str = ""

    @field_validator("pattern")
    @classmethod
    def validate_regex(cls, v: str) -> str:
        """Ensure pattern is a valid regex."""
        try:
            re.compile(v)
        except re.error as e:
            msg = f"Invalid regex pattern: {e}"
            raise ValueError(msg) from e
        return v

    def matches(self, path: str) -> bool:
        """Check if a change path matches this escalation rule."""
        return bool(re.search(self.pattern, path))


class ProjectConfig(BaseModel):
    """Declares what a target project uses and how to scan it.

    Loaded from a project manifest file (YAML or TOML).
    """

    name: str
    root: Path
    platform: str  # e.g. "shopify"

    # Inventory extraction settings
    api_version_source: str  # "shopify.app.toml:webhooks.api_version" (file:dotted.key format)
    source_patterns: list[str]  # e.g. ["app/**/*.ts", "app/**/*.tsx"]
    graphql_tag: str = "#graphql"  # Tag pattern to find GraphQL strings
    dependency_prefixes: list[str] = []  # e.g. ["@shopify/"]
    component_tag_pattern: str | None = None  # e.g. r"<s-"
    webhook_config_path: str | None = None  # e.g. "shopify.app.toml"

    # Severity overrides
    escalation_rules: list[EscalationRule] = []

    # Collect settings
    changelog_rss_url: str | None = None  # e.g. "https://shopify.dev/changelog/feed.xml"
    changelog_page_urls: list[str] = []  # Firecrawl targets
    schema_base_url: str | None = None  # Base URL for schema introspection
    design_system_urls: list[str] = []  # Design-system changelog pages (Firecrawl targets)
    disabled_collectors: list[str] = []  # Collector names to skip, e.g. ["polaris"]

    # Report output
    report_dir: str = "docs/api-changes"  # Relative to project root
