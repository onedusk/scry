"""Tests for scry.diff.triage — Claude relevance judgments for changelog impacts."""

import json
import logging
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scry.diff.triage import triage_changelog_impacts
from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.enums import (
    ChangeCategory,
    ChangeSource,
    Criticality,
    SchemaChangeType,
    Severity,
)
from scry.models.impact import ImpactItem
from scry.models.surface import AppSurface
from scry.models.triage import Judgment, TriageResponse


def _record(title: str, category: ChangeCategory = ChangeCategory.PLATFORM) -> ChangeRecord:
    return ChangeRecord(
        source=ChangeSource.RSS,
        title=title,
        description=f"<p>{title} details</p>",
        category=category,
    )


def _judgment(change_id: str, **overrides: Any) -> Judgment:
    fields: dict[str, Any] = {
        "change_id": change_id,
        "relevant": True,
        "severity": Severity.HIGH,
        "affected_features": ["GetProducts"],
        "deadline": None,
        "suggested_action": "Read barcodes from the barcodes connection.",
        "rationale": "The project selects Product.barcode.",
    }
    fields.update(overrides)
    return Judgment(**fields)


class _FakeClient:
    """Stands in for anthropic.Anthropic: records parse() calls, replays canned responses."""

    def __init__(self, responses: list[Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _response(*judgments: Judgment, stop_reason: str = "end_turn") -> Any:
    return SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=None
        if stop_reason == "refusal"
        else TriageResponse(judgments=list(judgments)),
        usage=SimpleNamespace(input_tokens=100, cache_read_input_tokens=40, output_tokens=20),
    )


class TestTriageChangelogImpacts:
    """Tests for triage_changelog_impacts()."""

    def test_relevant_judgment_rescored_with_files_and_action(
        self, sample_surface_with_operations: AppSurface
    ) -> None:
        change = _record("Variants now support multiple barcodes")
        item = ImpactItem(change=change, severity=Severity.INFO)
        client = _FakeClient(
            [_response(_judgment(change.id, deadline="2027-01-01", severity=Severity.CRITICAL))]
        )

        rescored, result = triage_changelog_impacts(
            [item], sample_surface_with_operations, "claude-opus-5", client=client
        )

        assert rescored[0].severity == Severity.CRITICAL
        assert rescored[0].affected_features == ["GetProducts"]
        assert rescored[0].affected_files == [Path("app/routes/products.ts")]
        assert rescored[0].deadline == date(2027, 1, 1)
        assert rescored[0].suggested_action == "Read barcodes from the barcodes connection."
        assert result.model == "claude-opus-5"
        assert [j.change_id for j in result.judgments] == [change.id]
        assert (result.input_tokens, result.cache_read_input_tokens, result.output_tokens) == (
            100,
            40,
            20,
        )

    def test_irrelevant_judgment_clears_substring_match(
        self, sample_surface_with_operations: AppSurface
    ) -> None:
        change = _record("Search discountNodes by exact code", ChangeCategory.BREAKING)
        item = ImpactItem(
            change=change,
            severity=Severity.HIGH,
            affected_files=[Path("app/routes/products.ts")],
            affected_features=["GetProducts"],
            suggested_action="Review required",
        )
        client = _FakeClient([_response(_judgment(change.id, relevant=False))])

        rescored, _ = triage_changelog_impacts(
            [item], sample_surface_with_operations, "claude-opus-5", client=client
        )

        assert rescored[0].severity == Severity.INFO
        assert rescored[0].affected_files == []
        assert rescored[0].affected_features == []
        assert rescored[0].suggested_action == ""

    def test_unknown_features_are_dropped_and_non_operation_features_have_no_file(
        self, sample_surface_with_operations: AppSurface
    ) -> None:
        change = _record("Webhook payload change")
        item = ImpactItem(change=change, severity=Severity.INFO)
        client = _FakeClient(
            [
                _response(
                    _judgment(
                        change.id,
                        affected_features=["products/update", "Hallucinated", "@shopify/polaris"],
                    )
                )
            ]
        )

        rescored, _ = triage_changelog_impacts(
            [item], sample_surface_with_operations, "claude-opus-5", client=client
        )

        assert rescored[0].affected_features == ["products/update", "@shopify/polaris"]
        assert rescored[0].affected_files == []

    def test_schema_and_sdk_impacts_are_not_sent_and_unchanged(
        self, sample_surface_with_operations: AppSurface, sample_schema_change: SchemaChange
    ) -> None:
        sdk = ImpactItem(
            change=_record("@shopify/polaris: ^12 → 13", ChangeCategory.SDK), severity=Severity.LOW
        )
        schema = ImpactItem(change=sample_schema_change, severity=Severity.HIGH)
        entry = _record("Something")
        judged = ImpactItem(change=entry, severity=Severity.INFO)
        client = _FakeClient([_response(_judgment(entry.id))])

        rescored, _ = triage_changelog_impacts(
            [sdk, schema, judged], sample_surface_with_operations, "claude-opus-5", client=client
        )

        sent = json.loads(client.calls[0]["messages"][0]["content"].split("\n", 1)[1])
        assert [e["id"] for e in sent] == [entry.id]
        assert rescored[0] == sdk
        assert rescored[1] == schema
        assert rescored[2].severity == Severity.HIGH

    def test_chunks_requests_and_caches_inventory(
        self, sample_surface_with_operations: AppSurface
    ) -> None:
        records = [_record(f"Entry {i}") for i in range(3)]
        items = [ImpactItem(change=r, severity=Severity.INFO) for r in records]
        client = _FakeClient(
            [
                _response(_judgment(records[0].id), _judgment(records[1].id, relevant=False)),
                _response(_judgment(records[2].id)),
            ]
        )

        rescored, result = triage_changelog_impacts(
            items, sample_surface_with_operations, "claude-opus-5", client=client, chunk_size=2
        )

        assert len(client.calls) == 2
        first = client.calls[0]
        assert first["model"] == "claude-opus-5"
        assert first["output_format"] is TriageResponse
        assert first["fallbacks"] == "default"
        assert first["betas"] == ["server-side-fallback-2026-07-01"]
        assert first["system"][1]["cache_control"] == {"type": "ephemeral"}
        assert "query GetProducts" in first["system"][1]["text"]
        assert "Project context: none provided" in first["system"][1]["text"]
        assert [i.severity for i in rescored] == [Severity.HIGH, Severity.INFO, Severity.HIGH]
        assert len(result.judgments) == 3
        assert result.input_tokens == 200

    def test_context_and_date_are_in_the_cached_block(
        self, sample_surface_with_operations: AppSurface
    ) -> None:
        change = _record("Entry")
        client = _FakeClient([_response(_judgment(change.id))])
        triage_changelog_impacts(
            [ImpactItem(change=change, severity=Severity.INFO)],
            sample_surface_with_operations,
            "claude-opus-5",
            client=client,
            context="Custom app for one merchant; expiring offline tokens already enabled.",
            today=date(2026, 9, 15),
        )
        block = client.calls[0]["system"][1]["text"]
        assert block.startswith(
            "Today's date: 2026-09-15\nProject context: Custom app for one merchant"
        )
        assert "already passed" in client.calls[0]["system"][0]["text"]

    def test_refused_chunk_keeps_deterministic_scores(
        self, sample_surface_with_operations: AppSurface, caplog: Any
    ) -> None:
        change = _record("Entry")
        item = ImpactItem(change=change, severity=Severity.LOW, affected_features=["GetProducts"])
        client = _FakeClient([_response(stop_reason="refusal")])

        with caplog.at_level(logging.WARNING):
            rescored, result = triage_changelog_impacts(
                [item], sample_surface_with_operations, "claude-opus-5", client=client
            )

        assert rescored[0] == item
        assert result.judgments == []
        assert "Triage request declined" in caplog.text

    def test_missing_judgment_keeps_deterministic_score(
        self, sample_surface_with_operations: AppSurface
    ) -> None:
        change = _record("Entry")
        item = ImpactItem(change=change, severity=Severity.MEDIUM)
        client = _FakeClient([_response(_judgment("some-other-id"))])

        rescored, _ = triage_changelog_impacts(
            [item], sample_surface_with_operations, "claude-opus-5", client=client
        )

        assert rescored[0] == item

    def test_unparsable_deadline_is_ignored(
        self, sample_surface_with_operations: AppSurface
    ) -> None:
        change = _record("Entry")
        item = ImpactItem(change=change, severity=Severity.INFO, deadline=date(2026, 12, 1))
        client = _FakeClient([_response(_judgment(change.id, deadline="next quarter"))])

        rescored, _ = triage_changelog_impacts(
            [item], sample_surface_with_operations, "claude-opus-5", client=client
        )

        assert rescored[0].deadline == date(2026, 12, 1)

    def test_no_candidates_makes_no_requests(
        self, sample_surface_with_operations: AppSurface, sample_schema_change: SchemaChange
    ) -> None:
        client = _FakeClient([])
        rescored, result = triage_changelog_impacts(
            [ImpactItem(change=sample_schema_change, severity=Severity.HIGH)],
            sample_surface_with_operations,
            "claude-opus-5",
            client=client,
        )
        assert client.calls == []
        assert len(rescored) == 1
        assert result.judgments == []


class TestCriticalityImport:
    """Guard against the Criticality import being unused if fixtures change."""

    def test_schema_change_fixture_is_breaking(self, sample_schema_change: SchemaChange) -> None:
        assert sample_schema_change.criticality == Criticality.BREAKING
        assert sample_schema_change.change_type == SchemaChangeType.FIELD_REMOVED
