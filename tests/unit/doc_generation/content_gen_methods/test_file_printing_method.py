from __future__ import annotations

from pathlib import Path

from docs.docs_generation.content_gen_methods.file_printing_method import FilePrintingDocContentGenMethod
from docs.docs_generation.content_gen_methods.mdx import MdxFile


class TestFilePrintingDocContentGenMethod:
    def test_apply_returns_file_content(self) -> None:
        # Arrange
        file = MdxFile(name="node.mdx", content="# Node API\n\nSome content", source_path=Path("node.py"))
        method = FilePrintingDocContentGenMethod(file=file)

        # Act
        result = method.apply()

        # Assert
        assert result == "# Node API\n\nSome content"

    def test_apply_returns_empty_string(self) -> None:
        # Arrange
        file = MdxFile(name="empty.mdx", content="", source_path=Path("empty.py"))
        method = FilePrintingDocContentGenMethod(file=file)

        # Act
        result = method.apply()

        # Assert
        assert not result
