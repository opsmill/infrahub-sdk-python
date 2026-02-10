from __future__ import annotations

from pathlib import Path

from doc_generation.content_gen_methods.file_printing_method import FilePrintingDocContentGenMethod
from doc_generation.content_gen_methods.mdx.mdx_code_doc import MdxFile


class TestFilePrintingDocContentGenMethod:
    def test_apply_returns_file_content(self) -> None:
        file = MdxFile(path=Path("node.mdx"), content="# Node API\n\nSome content")
        method = FilePrintingDocContentGenMethod(file=file)

        assert method.apply() == "# Node API\n\nSome content"

    def test_apply_returns_empty_string(self) -> None:
        file = MdxFile(path=Path("empty.mdx"), content="")
        method = FilePrintingDocContentGenMethod(file=file)

        assert not method.apply()
