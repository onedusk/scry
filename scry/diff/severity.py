"""Severity scorer — applies escalation rules and deadlines to ImpactItems."""

from scry.models.changes import ChangeRecord, SchemaChange
from scry.models.config import EscalationRule
from scry.models.enums import Severity
from scry.models.impact import ImpactItem

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


def score_severity(
    impacts: list[ImpactItem], rules: list[EscalationRule]
) -> list[ImpactItem]:
    """Apply escalation rules and sunset deadlines to a list of ImpactItems.

    Rules can only raise severity, never lower it. Returns a new list
    with updated severity and deadline fields (original items are not mutated).
    """
    result: list[ImpactItem] = []

    for item in impacts:
        path = (
            item.change.path
            if isinstance(item.change, SchemaChange)
            else item.change.title
        )

        severity = item.severity
        for rule in rules:
            if rule.matches(path) and _SEVERITY_RANK[rule.floor] > _SEVERITY_RANK[severity]:
                severity = rule.floor

        deadline = item.deadline
        if isinstance(item.change, ChangeRecord) and item.change.sunset_date is not None:
            deadline = item.change.sunset_date

        result.append(
            item.model_copy(update={"severity": severity, "deadline": deadline})
        )

    return result
