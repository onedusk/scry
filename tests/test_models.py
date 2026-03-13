"""Tests for scry Pydantic models."""

import json

import pytest
from pydantic import ValidationError

from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.config import EscalationRule
from scry.models.enums import (
    ChangeCategory,
    ChangeSource,
    Severity,
)
from scry.models.impact import ImpactItem
from scry.models.state import RunState


# --- ChangeRecord ---


class TestChangeRecord:
    def test_id_determinism(self, sample_change_record: ChangeRecord) -> None:
        """Same inputs produce the same id."""
        duplicate = ChangeRecord(
            source=sample_change_record.source,
            title=sample_change_record.title,
            version=sample_change_record.version,
            category=sample_change_record.category,
        )
        assert sample_change_record.id == duplicate.id

    def test_id_uniqueness(self, sample_change_record: ChangeRecord) -> None:
        """Different inputs produce different ids."""
        other = ChangeRecord(
            source=ChangeSource.RSS,
            title="Different title",
            category=ChangeCategory.FEATURE,
        )
        assert sample_change_record.id != other.id

    def test_json_round_trip(self, sample_change_record: ChangeRecord) -> None:
        """ChangeRecord survives JSON serialization and deserialization."""
        json_str = sample_change_record.model_dump_json()
        restored = ChangeRecord.model_validate_json(json_str)
        assert restored.id == sample_change_record.id
        assert restored.title == sample_change_record.title
        assert restored.source == sample_change_record.source

    def test_model_dump_includes_id(self, sample_change_record: ChangeRecord) -> None:
        """The computed id field appears in model_dump output."""
        data = sample_change_record.model_dump()
        assert "id" in data
        assert isinstance(data["id"], str)
        assert len(data["id"]) == 16


# --- ImpactItem ---


class TestImpactItem:
    def test_with_change_record(self, sample_change_record: ChangeRecord) -> None:
        """ImpactItem validates with a ChangeRecord as the change field."""
        item = ImpactItem(
            change=sample_change_record,
            severity=Severity.HIGH,
        )
        assert isinstance(item.change, ChangeRecord)
        assert item.severity == Severity.HIGH

    def test_with_schema_change(self, sample_schema_change: SchemaChange) -> None:
        """ImpactItem validates with a SchemaChange as the change field."""
        item = ImpactItem(
            change=sample_schema_change,
            severity=Severity.CRITICAL,
        )
        assert isinstance(item.change, SchemaChange)

    def test_change_record_round_trip(self, sample_change_record: ChangeRecord) -> None:
        """ImpactItem with ChangeRecord survives JSON round-trip."""
        item = ImpactItem(change=sample_change_record, severity=Severity.HIGH)
        json_str = item.model_dump_json()
        restored = ImpactItem.model_validate_json(json_str)
        assert isinstance(restored.change, ChangeRecord)
        assert restored.change.id == sample_change_record.id

    def test_schema_change_round_trip(self, sample_schema_change: SchemaChange) -> None:
        """ImpactItem with SchemaChange survives JSON round-trip."""
        item = ImpactItem(change=sample_schema_change, severity=Severity.CRITICAL)
        json_str = item.model_dump_json()
        restored = ImpactItem.model_validate_json(json_str)
        assert isinstance(restored.change, SchemaChange)
        assert restored.change.path == "Product.barcode"


# --- RunState ---


class TestRunState:
    def test_empty_defaults(self) -> None:
        """RunState creates with empty defaults."""
        state = RunState()
        assert state.last_run is None
        assert len(state.known_change_ids) == 0
        assert len(state.runs) == 0

    def test_is_known_and_record_change(self) -> None:
        """is_known and record_change work correctly."""
        state = RunState()
        assert not state.is_known("abc")
        state.record_change("abc")
        assert state.is_known("abc")
        assert not state.is_known("xyz")

    def test_json_round_trip_set_serialization(self) -> None:
        """set[str] serializes as JSON list and deserializes back to set."""
        state = RunState()
        state.record_change("id1")
        state.record_change("id2")

        json_str = state.model_dump_json()
        data = json.loads(json_str)
        # Serialized as a list
        assert isinstance(data["known_change_ids"], list)
        assert set(data["known_change_ids"]) == {"id1", "id2"}

        # Round-trip back to RunState
        restored = RunState.model_validate_json(json_str)
        assert restored.is_known("id1")
        assert restored.is_known("id2")
        assert isinstance(restored.known_change_ids, set)


# --- EscalationRule ---


class TestEscalationRule:
    def test_valid_pattern(self) -> None:
        """EscalationRule validates with a valid regex pattern."""
        rule = EscalationRule(pattern="foo|bar", floor=Severity.CRITICAL)
        assert rule.pattern == "foo|bar"

    def test_invalid_regex_raises(self) -> None:
        """EscalationRule rejects invalid regex patterns."""
        with pytest.raises(ValidationError):
            EscalationRule(pattern="[invalid", floor=Severity.CRITICAL)

    def test_matches_positive(self) -> None:
        """matches returns True for matching paths."""
        rule = EscalationRule(pattern="productVariantsBulkUpdate|barcode", floor=Severity.CRITICAL)
        assert rule.matches("Mutation.productVariantsBulkUpdate")
        assert rule.matches("something_barcode_else")

    def test_matches_negative(self) -> None:
        """matches returns False for non-matching paths."""
        rule = EscalationRule(pattern="productVariantsBulkUpdate|barcode", floor=Severity.CRITICAL)
        assert not rule.matches("completely_unrelated")
