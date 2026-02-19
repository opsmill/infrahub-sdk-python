from __future__ import annotations

from pathlib import Path

from docs.docs_generation.content_gen_methods import ADocContentGenMethod
from docs.docs_generation.pages import DocPage, MDXDocPage


class StubContentGenMethod(ADocContentGenMethod):
    def __init__(self, content: str) -> None:
        self._content = content

    def apply(self) -> str:
        return self._content


class TestDocPage:
    def test_content_delegates_to_method(self) -> None:
        # Arrange
        page = DocPage(content_gen_method=StubContentGenMethod("test content"))

        # Act
        result = page.content()

        # Assert
        assert result == "test content"


class TestMDXDocPage:
    def test_to_mdx_writes_file(self, tmp_path: Path) -> None:
        # Arrange
        page = DocPage(content_gen_method=StubContentGenMethod("# Hello MDX"))
        output_path = tmp_path / "output.mdx"

        # Act
        MDXDocPage(page=page, output_path=output_path).to_mdx()

        # Assert
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8") == "# Hello MDX"

    def test_to_mdx_creates_parent_directories(self, tmp_path: Path) -> None:
        # Arrange
        page = DocPage(content_gen_method=StubContentGenMethod("content"))
        output_path = tmp_path / "nested" / "dir" / "output.mdx"

        # Act
        MDXDocPage(page=page, output_path=output_path).to_mdx()

        # Assert
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8") == "content"
