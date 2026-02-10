from __future__ import annotations

from pathlib import Path

from doc_generation.content_gen_methods import Jinja2DocContentGenMethod


class TestJinja2DocContentGenMethod:
    def test_apply_renders_template(self, tmp_path: Path) -> None:
        # Arrange
        template_file = tmp_path / "test.j2"
        template_file.write_text("Hello {{ name }}!", encoding="utf-8")
        method = Jinja2DocContentGenMethod(
            template_path=template_file,
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
        method = Jinja2DocContentGenMethod(
            template_path=template_file,
            template_variables={"greeting": "Hi", "target": "there"},
        )

        # Act
        result = method.apply()

        # Assert
        assert result == "Hi there!"

    def test_apply_trim_blocks(self, tmp_path: Path) -> None:
        """Verify that trim_blocks removes the newline after block tags."""
        # Arrange
        template_file = tmp_path / "test.j2"
        template_file.write_text("{% if true %}\nline\n{% endif %}\n", encoding="utf-8")
        method = Jinja2DocContentGenMethod(
            template_path=template_file,
            template_variables={},
        )

        # Act
        result = method.apply()

        # Assert — without trim_blocks this would be "\nline\n\n"
        assert result == "line\n"

    def test_auto_escaping_is_disabled(self, tmp_path: Path) -> None:
        """HTML content in template variables must not be auto-escaped,
        since the Jinja2 environment uses default_for_string=False."""
        # Arrange
        template_file = tmp_path / "test.j2"
        template_file.write_text("{{ html_content }}", encoding="utf-8")
        html_input = '<a href="link">text</a>'
        method = Jinja2DocContentGenMethod(
            template_path=template_file,
            template_variables={"html_content": html_input},
        )

        # Act
        result: str = method.apply()

        # Assert
        assert result == html_input
