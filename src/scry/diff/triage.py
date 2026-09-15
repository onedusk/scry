"""Claude triage — semantic relevance judgments for changelog impacts.

The substring matcher in scry.diff.changelog cannot tell "node" in a discount
post from the project's node query. With a model configured, every changelog
entry is judged against the full inventory and the deterministic scoring is
replaced by the model's verdict. Schema changes are not sent: the TypeInfo
cross-reference is already exact.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import anthropic
from anthropic.types.beta import BetaTextBlockParam

from scry.models.changes import ChangeRecord
from scry.models.enums import ChangeCategory, Severity
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface
from scry.models.triage import Judgment, TriageResponse, TriageResult
from scry.text import plain_text

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50
_MAX_DESCRIPTION_CHARS = 4000
_BETAS = ["server-side-fallback-2026-07-01"]

_SYSTEM_PROMPT = """\
You triage a platform's changelog for one specific project. You receive the \
project's inventory (its GraphQL operations with full query text, webhook \
subscriptions, tracked packages, UI components, and pinned API version) and a \
batch of changelog entries. For each entry, decide whether it affects this \
project's code or behavior and return one judgment per entry.

An entry is relevant when it changes something the inventory actually uses: a \
field, type, argument, mutation, or query in one of the operations; a webhook \
topic the project subscribes to; a package it depends on; a component it \
renders; or a platform behavior (authentication, API versioning, rate limits, \
webhook delivery, bulk operations) that every app on this API version must \
handle. Sharing a generic word with the inventory ("node", "products") does not \
make an entry relevant. Entries about surfaces the project does not use are not \
relevant unless they change something the inventory uses.

Judgment fields:
- change_id: copy the entry's id.
- relevant: as above.
- severity: critical when the project's core function breaks without a code \
change; high when code must change to stay correct or before a deadline; medium \
for a deprecation or behavior change to adapt to; low for an optional \
improvement; info when not relevant.
- affected_features: identifiers copied verbatim from the inventory (operation \
names, webhook topics, package names, component tags). Empty when not relevant.
- deadline: the ISO date (YYYY-MM-DD) the entry states for removal or \
enforcement, or null.
- suggested_action: one or two sentences naming what to change in this project, \
empty when not relevant.
- rationale: one sentence.

Two more rules:
- The project context lists facts (distribution model, deployment path, features \
already enabled). Use it to rule out entries that do not apply to this project.
- Today's date is given. An entry whose stated deadline has already passed is a \
requirement the project already meets, is exempt from, or is currently violating. \
Mark it relevant only when the context or inventory shows the requirement is unmet, \
and say which case applies in the rationale.
"""


def _inventory_json(surface: AppSurface) -> str:
    """Serialize the inventory deterministically so the cached prefix is stable."""
    inventory = {
        "api_version": surface.api_version,
        "graphql_operations": [
            {"name": op.name, "file": str(op.file), "operation": op.raw_query}
            for op in surface.graphql_operations
        ],
        "webhook_topics": surface.webhook_topics,
        "dependencies": sorted(surface.dependencies),
        "ui_components": surface.ui_components,
    }
    return json.dumps(inventory, indent=1, sort_keys=True)


def _entry(change: ChangeRecord) -> dict[str, object]:
    return {
        "id": change.id,
        "title": change.title,
        "version": change.version,
        "category": change.category.value,
        "action_required": change.action_required,
        "url": change.url,
        "description": plain_text(change.description)[:_MAX_DESCRIPTION_CHARS],
    }


def _feature_files(surface: AppSurface) -> dict[str, Path | None]:
    """Map every inventory identifier the model may cite to its file, if any."""
    files: dict[str, Path | None] = {op.name: op.file for op in surface.graphql_operations}
    for name in (*surface.webhook_topics, *surface.dependencies, *surface.ui_components):
        files.setdefault(name, None)
    return files


def _parse_deadline(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _apply(item: ImpactItem, judgment: Judgment, features: dict[str, Path | None]) -> ImpactItem:
    if not judgment.relevant:
        return item.model_copy(
            update={
                "severity": Severity.INFO,
                "affected_files": [],
                "affected_features": [],
                "suggested_action": "",
            }
        )
    cited = [name for name in judgment.affected_features if name in features]
    files = [features[name] for name in cited if features[name] is not None]
    return item.model_copy(
        update={
            "severity": judgment.severity,
            "affected_files": list(dict.fromkeys(files)),
            "affected_features": cited,
            "deadline": _parse_deadline(judgment.deadline) or item.deadline,
            "suggested_action": judgment.suggested_action,
        }
    )


def triage_changelog_impacts(
    impacts: list[ImpactItem],
    surface: AppSurface,
    model: str,
    client: anthropic.Anthropic | None = None,
    chunk_size: int = CHUNK_SIZE,
    context: str | None = None,
    today: date | None = None,
) -> tuple[list[ImpactItem], TriageResult]:
    """Ask Claude which changelog impacts affect the project and rescore them.

    Only ChangeRecord impacts other than SDK version bumps are judged. Entries
    the model does not return (a declined or failed chunk) keep their
    deterministic scoring. `context` is free text about the project (see
    ProjectConfig.triage_context) and `today` anchors deadline judgments.
    Returns the rescored impacts and the raw judgments.
    """
    client = client or anthropic.Anthropic()
    today = today or date.today()
    candidates: list[tuple[ImpactItem, ChangeRecord]] = [
        (item, item.change)
        for item in impacts
        if isinstance(item.change, ChangeRecord) and item.change.category != ChangeCategory.SDK
    ]
    system: list[BetaTextBlockParam] = [
        {"type": "text", "text": _SYSTEM_PROMPT},
        {
            "type": "text",
            "text": (
                f"Today's date: {today.isoformat()}\n"
                f"Project context: {context or 'none provided'}\n"
                "Project inventory:\n" + _inventory_json(surface)
            ),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    result = TriageResult(model=model)
    judgments: dict[str, Judgment] = {}

    for start in range(0, len(candidates), chunk_size):
        chunk = candidates[start : start + chunk_size]
        entries = [_entry(change) for _, change in chunk]
        logger.info(
            "Triaging changelog entries %d-%d of %d with %s",
            start + 1,
            start + len(chunk),
            len(candidates),
            model,
        )
        response = client.beta.messages.parse(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[
                {"role": "user", "content": "Changelog entries:\n" + json.dumps(entries, indent=1)}
            ],
            output_format=TriageResponse,
            betas=_BETAS,
            fallbacks="default",
        )
        result.input_tokens += response.usage.input_tokens
        result.cache_read_input_tokens += response.usage.cache_read_input_tokens or 0
        result.output_tokens += response.usage.output_tokens
        if response.stop_reason == "refusal" or response.parsed_output is None:
            logger.warning(
                "Triage request declined (stop_reason=%s); keeping deterministic scores for "
                "%d entries",
                response.stop_reason,
                len(chunk),
            )
            continue
        for judgment in response.parsed_output.judgments:
            judgments[judgment.change_id] = judgment

    result.judgments = [judgments[c.id] for _, c in candidates if c.id in judgments]
    features = _feature_files(surface)
    rescored = [
        _apply(item, judgments[item.change.id], features)
        if isinstance(item.change, ChangeRecord) and item.change.id in judgments
        else item
        for item in impacts
    ]
    return rescored, result
