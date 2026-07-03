"""Models for a target project's API surface inventory."""

from pathlib import Path

from pydantic import BaseModel

from scry.models.enums import OperationType


class GraphQLOperation(BaseModel):
    """A parsed GraphQL operation found in source code."""

    name: str  # e.g. "ProductsWithVariants"
    operation_type: OperationType
    file: Path
    fields: list[str]  # Top-level fields, e.g. ["products"]
    raw_query: str


class AppSurface(BaseModel):
    """Snapshot of what a target project currently uses from the monitored platform."""

    api_version: str  # e.g. "2026-04"
    graphql_operations: list[GraphQLOperation] = []
    webhook_topics: list[str] = []
    dependencies: dict[str, str] = {}  # package name -> version
    ui_components: list[str] = []  # unique component tags
    scopes: list[str] = []  # OAuth/API scopes
