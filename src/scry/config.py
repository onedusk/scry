"""Project manifest loading and resolution."""

import os
from pathlib import Path

from scry.models.config import ProjectConfig

# Manifest filenames searched in order
MANIFEST_FILENAMES = ("scry.yaml", "scry.yml", "scry.toml")


def find_manifest(start: Path | None = None) -> Path:
    """Search for a project manifest file.

    Looks in the given directory (or cwd) for scry.yaml / scry.yml / scry.toml.

    Args:
        start: Directory to search in. Defaults to cwd.

    Returns:
        Path to the found manifest file.

    Raises:
        FileNotFoundError: If no manifest is found.
    """
    search_dir = start or Path.cwd()
    for name in MANIFEST_FILENAMES:
        candidate = search_dir / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No scry manifest found in {search_dir}. "
        f"Expected one of: {', '.join(MANIFEST_FILENAMES)}. "
        "Run 'scry init' to generate one."
    )


def check_firecrawl_env(config: ProjectConfig) -> None:
    """Ensure FIRECRAWL_API_KEY is set when Firecrawl-dependent sources are configured.

    changelog_page_urls and design_system_urls are scraped via Firecrawl. A field
    only requires the key when its collector is not listed in disabled_collectors.

    Raises:
        ValueError: If FIRECRAWL_API_KEY is missing but required.
    """
    if os.environ.get("FIRECRAWL_API_KEY"):
        return

    disabled = set(config.disabled_collectors)
    required_by: list[str] = []
    if config.changelog_page_urls and "changelog" not in disabled:
        required_by.append("changelog_page_urls")
    if config.design_system_urls and "polaris" not in disabled:
        required_by.append("design_system_urls")

    if required_by:
        raise ValueError(
            f"FIRECRAWL_API_KEY is not set, but the manifest sets {', '.join(required_by)} "
            "(scraped via Firecrawl). Set FIRECRAWL_API_KEY or disable the corresponding "
            "collector(s) via disabled_collectors."
        )


def load_config(manifest_path: Path, *, check_env: bool = True) -> ProjectConfig:
    """Load and validate a project manifest.

    Supports YAML (.yaml, .yml) and TOML (.toml) formats.

    Args:
        manifest_path: Path to the manifest file.
        check_env: Also validate required environment variables
            (see check_firecrawl_env). Pass False to parse only.

    Returns:
        Validated ProjectConfig.

    Raises:
        ValueError: If the manifest format is unsupported, or if a required
            environment variable is missing (when check_env is True).
        pydantic.ValidationError: If the manifest content fails validation.
    """
    suffix = manifest_path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        import yaml

        raw = yaml.safe_load(manifest_path.read_text())
    elif suffix == ".toml":
        import tomllib

        raw = tomllib.loads(manifest_path.read_text())
    else:
        raise ValueError(f"Unsupported manifest format: {suffix}")

    config = ProjectConfig.model_validate(raw)
    if check_env:
        check_firecrawl_env(config)
    return config
