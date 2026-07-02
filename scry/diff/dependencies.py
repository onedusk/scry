"""Dependency differ — compares current vs latest package versions."""

import re

from scry.models.changes import ChangeRecord
from scry.models.enums import ChangeCategory, ChangeSource, Severity
from scry.models.impact import ImpactItem

_VERSION_PREFIX = re.compile(r"^[^0-9]*")


def _clean_version(v: str) -> str:
    """Strip non-numeric prefixes like ^, ~, >= from a version string."""
    return _VERSION_PREFIX.sub("", v)


def diff_dependencies(current: dict[str, str], latest: dict[str, str]) -> list[ImpactItem]:
    """Compare current dependency versions against latest and return impacts."""
    items: list[ImpactItem] = []

    for pkg, cur_ver in current.items():
        if pkg not in latest:
            continue

        lat_ver = latest[pkg]
        cur_clean = _clean_version(cur_ver)
        lat_clean = _clean_version(lat_ver)

        if not cur_clean or not lat_clean or cur_clean == lat_clean:
            continue

        cur_major = cur_clean.split(".")[0]
        lat_major = lat_clean.split(".")[0]

        severity = Severity.MEDIUM if cur_major != lat_major else Severity.LOW

        change = ChangeRecord(
            source=ChangeSource.REGISTRY,
            title=f"{pkg} {cur_clean} → {lat_clean}",
            version=lat_clean,
            category=ChangeCategory.SDK,
        )
        items.append(ImpactItem(change=change, severity=severity))

    return items
