from __future__ import annotations

from pathlib import Path

from docs.docs_generation import Jinja2DocContentGenMethod
from infrahub_sdk.template import Jinja2Template
from tests.unit.sdk.dummy_template import DummyTemplate


class TestJinja2DocContentGenMethod:
    def test_apply_calls_template(self) -> None:
        """Inject a DummyTemplate to verify the method renders
        using the template engine correctly."""
        # Arrange
        template = DummyTemplate(content="rendered content")
        method = Jinja2DocContentGenMethod(
            template=template,
            template_variables={"key": "value"},
        )

        # Act
        result = method.apply()

        # Assert
        assert result == "rendered content"

    def test_apply_renders_template(self, tmp_path: Path) -> None:
        # Arrange
        template_file = tmp_path / "test.j2"
        template_file.write_text("Hello {{ name }}!", encoding="utf-8")
        template = Jinja2Template(template=Path("test.j2"), template_directory=tmp_path)
        method = Jinja2DocContentGenMethod(
            template=template,
            template_variables={"name": "World"},
        )

        # Act
        result = method.apply()

        # Assert
        assert result == "Hello World!"

    def test_apply_renders_with_multiple_variables(self, tmp_path: Path) -> None:
        # Arrange
        template_file = tmp_path / "test.j2"
        template_file.write_text("{{ greeting }} {{ target }}!", encoding="utf-8")
        template = Jinja2Template(template=Path("test.j2"), template_directory=tmp_path)
        method = Jinja2DocContentGenMethod(
            template=template,
            template_variables={"greeting": "Hi", "target": "there"},
        )

        # Act
        result = method.apply()

        # Assert
        assert result == "Hi there!"

    def test_auto_escaping_is_disabled(self, tmp_path: Path) -> None:
        """HTML content in template variables must not be auto-escaped,
        since the SDK Jinja2 environment does not enable autoescape."""
        # Arrange
        template_file = tmp_path / "test.j2"
        template_file.write_text("{{ html_content }}", encoding="utf-8")
        html_input = '<a href="link">text</a>'
        template = Jinja2Template(template=Path("test.j2"), template_directory=tmp_path)
        method = Jinja2DocContentGenMethod(
            template=template,
            template_variables={"html_content": html_input},
        )

        # Act
        result: str = method.apply()

        # Assert
        assert result == html_input
