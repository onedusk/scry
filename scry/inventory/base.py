"""Protocol definition for inventory extractors."""

from typing import Protocol

from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


class BaseExtractor(Protocol):
    """Protocol that all inventory extractors must satisfy.

    An extractor reads the target project's source files and
    populates a portion of the AppSurface model.
    """

    def extract(self, config: ProjectConfig, surface: AppSurface) -> AppSurface:
        """Extract inventory from the target project and update the surface.

        Each extractor is responsible for populating its own fields on the
        surface. It receives the current surface state (which may already
        have fields populated by other extractors) and returns the updated
        surface.

        Args:
            config: Project configuration with file patterns and settings.
            surface: Current surface state to update.

        Returns:
            Updated AppSurface with this extractor's fields populated.
        """
        ...
