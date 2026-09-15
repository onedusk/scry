"""Models for Claude triage of changelog entries."""

from pydantic import BaseModel

from scry.models.enums import Severity


class Judgment(BaseModel):
    """Claude's verdict on one changelog entry for one project.

    Structured-output shape: every field is required so the schema has no
    optional properties.
    """

    change_id: str
    relevant: bool
    severity: Severity
    affected_features: list[str]  # identifiers copied verbatim from the inventory
    deadline: str | None  # ISO date stated by the entry, if any
    suggested_action: str
    rationale: str


class TriageResponse(BaseModel):
    """One request's worth of judgments."""

    judgments: list[Judgment]


class TriageResult(BaseModel):
    """Everything a triage run produced, persisted next to the reports."""

    model: str
    judgments: list[Judgment] = []
    input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0
