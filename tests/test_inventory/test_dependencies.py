"""Tests for the DependencyExtractor."""

from pathlib import Path

from scry.inventory.dependencies import DependencyExtractor
from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


class TestDependencyExtractor:
    def test_extracts_shopify_deps(
        self, inventory_project_root: ProjectConfig
    ) -> None:
        """Extracts @shopify/* dependencies from package.json."""
        surface = AppSurface(api_version="")
        extractor = DependencyExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert "@shopify/polaris" in result.dependencies
        assert "@shopify/shopify-app-remix" in result.dependencies
        assert "@shopify/api-codegen-preset" in result.dependencies

    def test_ignores_non_matching_deps(
        self, inventory_project_root: ProjectConfig
    ) -> None:
        """Does not include dependencies that don't match configured prefixes."""
        surface = AppSurface(api_version="")
        extractor = DependencyExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert "@remix-run/react" not in result.dependencies
        assert "react" not in result.dependencies
        assert "typescript" not in result.dependencies

    def test_empty_prefixes_returns_empty(
        self, inventory_project_root: ProjectConfig
    ) -> None:
        """Returns empty dict when dependency_prefixes is empty."""
        inventory_project_root.dependency_prefixes = []
        surface = AppSurface(api_version="")
        extractor = DependencyExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert result.dependencies == {}

    def test_no_manifest_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty dict when no package manifest exists."""
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=[],
            dependency_prefixes=["@shopify/"],
        )
        surface = AppSurface(api_version="")
        extractor = DependencyExtractor()
        result = extractor.extract(config, surface)
        assert result.dependencies == {}

    def test_version_strings_preserved(
        self, inventory_project_root: ProjectConfig
    ) -> None:
        """Preserves the exact version string from package.json."""
        surface = AppSurface(api_version="")
        extractor = DependencyExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert result.dependencies["@shopify/polaris"] == "^12.0.0"

    def test_extracts_from_pyproject_toml(self, tmp_path: Path) -> None:
        """Extracts dependencies from pyproject.toml matching configured prefixes."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\n'
            'name = "myapp"\n'
            'dependencies = [\n'
            '    "shopify-api>=5.0",\n'
            '    "requests>=2.28",\n'
            '    "shopify-graphql>=1.0",\n'
            ']\n'
        )
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=[],
            dependency_prefixes=["shopify-"],
        )
        surface = AppSurface(api_version="")
        extractor = DependencyExtractor()
        result = extractor.extract(config, surface)
        assert "shopify-api" in result.dependencies
        assert "shopify-graphql" in result.dependencies
        assert "requests" not in result.dependencies

    def test_extracts_from_gemfile_lock(self, tmp_path: Path) -> None:
        """Extracts gem dependencies from Gemfile.lock."""
        gemfile_lock = tmp_path / "Gemfile.lock"
        gemfile_lock.write_text(
            "GEM\n"
            "  remote: https://rubygems.org/\n"
            "  specs:\n"
            "    shopify_api (13.4.0)\n"
            "    shopify_app (22.1.0)\n"
            "    rails (7.0.4)\n"
            "\n"
            "PLATFORMS\n"
            "  ruby\n"
        )
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=[],
            dependency_prefixes=["shopify_"],
        )
        surface = AppSurface(api_version="")
        extractor = DependencyExtractor()
        result = extractor.extract(config, surface)
        assert "shopify_api" in result.dependencies
        assert result.dependencies["shopify_api"] == "13.4.0"
        assert "shopify_app" in result.dependencies
        assert "rails" not in result.dependencies

    def test_extracts_from_go_mod(self, tmp_path: Path) -> None:
        """Extracts module dependencies from go.mod require block."""
        go_mod = tmp_path / "go.mod"
        go_mod.write_text(
            "module myapp\n"
            "\n"
            "go 1.21\n"
            "\n"
            "require (\n"
            "\tgithub.com/shopify/sarama v1.40.0\n"
            "\tgithub.com/shopify/toxiproxy v2.6.0\n"
            "\tgithub.com/stretchr/testify v1.8.4\n"
            ")\n"
        )
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=[],
            dependency_prefixes=["github.com/shopify/"],
        )
        surface = AppSurface(api_version="")
        extractor = DependencyExtractor()
        result = extractor.extract(config, surface)
        assert "github.com/shopify/sarama" in result.dependencies
        assert result.dependencies["github.com/shopify/sarama"] == "v1.40.0"
        assert "github.com/shopify/toxiproxy" in result.dependencies
        assert "github.com/stretchr/testify" not in result.dependencies

    def test_collects_from_multiple_manifests(self, tmp_path: Path) -> None:
        """Collects dependencies from all manifest types present."""
        # package.json
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"@shopify/polaris": "^12.0.0"}}'
        )
        # pyproject.toml
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = ["shopify-api>=5.0"]\n'
        )
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=[],
            dependency_prefixes=["@shopify/", "shopify-"],
        )
        surface = AppSurface(api_version="")
        extractor = DependencyExtractor()
        result = extractor.extract(config, surface)
        assert "@shopify/polaris" in result.dependencies
        assert "shopify-api" in result.dependencies
