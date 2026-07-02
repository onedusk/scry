"""Tests for the ComponentExtractor."""

from pathlib import Path

from scry.inventory.components import ComponentExtractor
from scry.models.config import ProjectConfig
from scry.models.surface import AppSurface


class TestComponentExtractor:
    def test_extracts_web_components(self, inventory_project_root: ProjectConfig) -> None:
        """Extracts <s-*> web component tags from source files."""
        surface = AppSurface(api_version="")
        extractor = ComponentExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert "s-card" in result.ui_components
        assert "s-button" in result.ui_components

    def test_extracts_polaris_react_imports(self, inventory_project_root: ProjectConfig) -> None:
        """Extracts named imports from @shopify/polaris."""
        surface = AppSurface(api_version="")
        extractor = ComponentExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert "Page" in result.ui_components
        assert "Card" in result.ui_components
        assert "Button" in result.ui_components

    def test_deduplicates_across_files(self, tmp_path: Path) -> None:
        """Components appearing in multiple files are listed once."""
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "a.tsx").write_text("<s-card>hello</s-card>\n")
        (app_dir / "b.tsx").write_text("<s-card>world</s-card>\n")
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=["app/**/*.tsx"],
            component_tag_pattern="<s-",
        )
        surface = AppSurface(api_version="")
        extractor = ComponentExtractor()
        result = extractor.extract(config, surface)
        assert result.ui_components.count("s-card") == 1

    def test_no_pattern_only_react_imports(self, tmp_path: Path) -> None:
        """With no component_tag_pattern, only React imports are found."""
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "page.tsx").write_text(
            'import { Page } from "@shopify/polaris";\n<s-card>hi</s-card>\n'
        )
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=["app/**/*.tsx"],
            component_tag_pattern=None,
        )
        surface = AppSurface(api_version="")
        extractor = ComponentExtractor()
        result = extractor.extract(config, surface)
        assert "Page" in result.ui_components
        assert "s-card" not in result.ui_components

    def test_handles_both_patterns_in_one_file(self, inventory_project_root: ProjectConfig) -> None:
        """A file with both web components and React imports extracts all."""
        surface = AppSurface(api_version="")
        extractor = ComponentExtractor()
        result = extractor.extract(inventory_project_root, surface)
        assert "s-card" in result.ui_components
        assert "Page" in result.ui_components

    def test_multiline_polaris_import(self, tmp_path: Path) -> None:
        """Extracts named imports that span multiple lines."""
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "multi.tsx").write_text(
            'import {\n  Page,\n  Card,\n  Button,\n  TextField,\n} from "@shopify/polaris";\n'
        )
        config = ProjectConfig(
            name="test",
            root=tmp_path,
            platform="shopify",
            api_version_source="x:y",
            source_patterns=["app/**/*.tsx"],
        )
        surface = AppSurface(api_version="")
        extractor = ComponentExtractor()
        result = extractor.extract(config, surface)
        assert "Page" in result.ui_components
        assert "Card" in result.ui_components
        assert "Button" in result.ui_components
        assert "TextField" in result.ui_components
