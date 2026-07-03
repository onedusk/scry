"""Protocol definition for change collectors."""

from typing import Protocol

from scry.models.changes import ChangeRecord
from scry.models.config import ProjectConfig


class BaseCollector(Protocol):
    """Protocol that all collectors must satisfy.

    A collector fetches changes from a single external source
    (RSS feed, changelog page, schema endpoint, package registry, etc.)
    and returns them as a list of ChangeRecord objects.
    """

    def collect(self, config: ProjectConfig) -> list[ChangeRecord]:
        """Fetch changes from this source."""
        ...
