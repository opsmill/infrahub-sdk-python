from __future__ import annotations

from pathlib import Path

from doc_generation.content_gen_methods import SDKJinja2DocContentGenMethod
from infrahub_sdk.template import Jinja2Template
from tests.unit.sdk.dummy_template import DummyTemplate


class TestSDKJinja2DocContentGenMethod:
    def test_apply_calls_sdk_template(self) -> None:
        """Inject a DummyTemplate to verify the method renders
        using the template engine correctly."""
        # Arrange
        template = DummyTemplate(content="rendered content")
        method = SDKJinja2DocContentGenMethod(
            template=template,
            template_variables={"key": "value"},
        )

        # Act
        result = method.apply()

        # Assert
        assert result == "rendered content"

    def test_auto_escaping_is_disabled(self, tmp_path: Path) -> None:
        """HTML content in template variables must not be auto-escaped,
        since the SDK Jinja2 environment does not enable autoescape."""
        # Arrange
        template_file = tmp_path / "test.j2"
        template_file.write_text("{{ html_content }}")
        html_input = '<a href="link">text</a>'
        template = Jinja2Template(template=Path("test.j2"), template_directory=tmp_path)
        method = SDKJinja2DocContentGenMethod(
            template=template,
            template_variables={"html_content": html_input},
        )

        # Act
        result: str = method.apply()

        # Assert
        assert result == html_input
