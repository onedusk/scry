"""Models for detected changes from all sources."""

from datetime import date, datetime
from hashlib import sha256

from pydantic import BaseModel, Field, computed_field

from scry.models.enums import (
    ChangeCategory,
    ChangeSource,
    Criticality,
    SchemaChangeType,
)


class ChangeRecord(BaseModel):
    """A single change detected from any source."""

    source: ChangeSource
    title: str
    version: str | None = None
    description: str = ""
    category: ChangeCategory
    action_required: bool = False
    url: str | None = None
    detected_at: datetime = Field(default_factory=datetime.now)
    sunset_date: date | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        """Deterministic hash of source + title + version for dedup."""
        key = f"{self.source}:{self.title}:{self.version or ''}"
        return sha256(key.encode()).hexdigest()[:16]


class SchemaChange(BaseModel):
    """A specific field/type change from GraphQL schema diffing."""

    change_type: SchemaChangeType
    criticality: Criticality
    path: str  # e.g. "Mutation.productVariantsBulkUpdate.variants"
    message: str
