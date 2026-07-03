"""Diff engine — schema diffing, changelog matching, and severity scoring."""

from scry.diff.changelog import match_changelog_to_surface
from scry.diff.schema import diff_schemas
from scry.diff.severity import score_severity

__all__ = [
    "diff_schemas",
    "match_changelog_to_surface",
    "score_severity",
]
