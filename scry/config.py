"""Project manifest loading and resolution."""

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


def load_config(manifest_path: Path) -> ProjectConfig:
    """Load and validate a project manifest.

    Supports YAML (.yaml, .yml) and TOML (.toml) formats.

    Args:
        manifest_path: Path to the manifest file.

    Returns:
        Validated ProjectConfig.

    Raises:
        ValueError: If the manifest format is unsupported.
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

    return ProjectConfig.model_validate(raw)
